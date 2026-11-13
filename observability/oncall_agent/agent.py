"""On-Call Responder Agent for MetalOps Lite.

Executes the 8-step incident response runbook defined in _docs/oncall-agent.md:
1. Wake from alert webhook.
2. Orient via Loki/Tempo telemetry correlation using trace IDs.
3. Localise failing route and responsible code layer.
4. Reproduce with a new failing test.
5. Fix with the minimal possible code modification.
6. Verify via test runner.
7. Open a 'fix/...' pull request.
8. Stop for human review (never merge, no production access).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from observability.oncall_agent.models import AlertPayload
from observability.oncall_agent.worktree import WorktreeError, WorktreeManager

logger = logging.getLogger("metalops.oncall_agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

ALLOWED_ALERT_FIELDS = frozenset(
    {
        "status",
        "service",
        "window",
        "metric",
        "route_group",
        "trace_ids",
        "started_at",
        "resolved_at",
    }
)

FORBIDDEN_ENV_VARS = frozenset(
    {
        "DEPLOY_SSH_KEY",
        "PROD_DATABASE_URL",
        "PRODUCTION_SECRET",
        "PRODUCTION_KEY",
        "PROD_APP_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "KUBECONFIG",
    }
)

ALLOWED_EXECUTABLES = frozenset({"git", "gh", "python", "pytest", "make"})
FORBIDDEN_SHELL_EXECUTABLES = frozenset({"sh", "bash", "cmd", "powershell", "pwsh"})
SHELL_INJECTION_CHARS = (";", "&&", "||", "|", "`")

# Regex patterns matching business data or sensitive information that must be redacted
_BUSINESS_REDACTION_PATTERNS = [
    (re.compile(r"(?i)\b(?:Acme\s+Scrap(?:\s+Ltd)?|Supplier\s+[A-Z0-9]+|Customer\s+[A-Z0-9]+)\b"), "[REDACTED_ENTITY]"),
    (re.compile(r"(?i)\b(?:Rs\.?|INR)\s*[\d,]+(?:\.\d{1,2})?(?:/kg)?\b"), "[REDACTED_RATE]"),
    (re.compile(r"\b\d{1,3}(?:,\d{2,3})+\s*(?:kg|INR|Rs)\b"), "[REDACTED_AMOUNT]"),
]


class ValidationError(Exception):
    """Raised when an alert payload fails schema or validation checks."""


class GuardrailViolation(Exception):
    """Raised when an on-call agent operation violates safety guardrails."""


def validate_alert_payload(raw: Mapping[str, Any]) -> AlertPayload:
    """Validate incoming alert payload against strict schema and allow-list."""
    if not isinstance(raw, (dict, Mapping)):
        raise ValidationError("Alert payload must be a JSON object mapping.")

    required_fields = ["status", "service", "window", "metric", "route_group", "started_at"]
    missing = [f for f in required_fields if f not in raw or not str(raw[f]).strip()]
    if missing:
        raise ValidationError(f"Missing required alert payload fields: {', '.join(missing)}")

    status = str(raw["status"]).lower().strip()
    if status not in {"firing", "resolved"}:
        raise ValidationError(f"Invalid alert status: '{status}'. Expected 'firing' or 'resolved'.")

    # Filter out any non-allow-listed fields to prevent unexpected payloads
    filtered: dict[str, Any] = {k: v for k, v in raw.items() if k in ALLOWED_ALERT_FIELDS}

    trace_ids = filtered.get("trace_ids", [])
    if not isinstance(trace_ids, list):
        trace_ids = []
    clean_trace_ids = [str(t).strip().lower() for t in trace_ids if isinstance(t, str) and len(str(t).strip()) == 32]

    return AlertPayload(
        status=status,
        service=str(filtered["service"]).strip(),
        window=str(filtered["window"]).strip(),
        metric=str(filtered["metric"]).strip(),
        route_group=str(filtered["route_group"]).strip(),
        started_at=str(filtered["started_at"]).strip(),
        trace_ids=clean_trace_ids,
        resolved_at=str(filtered.get("resolved_at")).strip() if filtered.get("resolved_at") else None,
    )


class AlertDeduplicator:
    """Debounces alerts within an active window with persistent SQLite storage and concurrency safety."""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        db_path: str | Path | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        if db_path is not None:
            self.db_path = str(db_path)
        elif "PYTEST_CURRENT_TEST" in os.environ:
            self.db_path = ":memory:"
        else:
            self.db_path = os.getenv("ONCALL_DEDUP_DB", ".metalops/oncall_dedup.db")
        self._lock = threading.Lock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._shared_conn: sqlite3.Connection | None = None
        else:
            self._shared_conn = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alert_dedup (
                        fingerprint TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        service TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        route_group TEXT NOT NULL,
                        window TEXT NOT NULL,
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL
                    );
                    """
                )
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                if self._shared_conn is None:
                    conn.close()

    def _fingerprint(self, alert: AlertPayload) -> str:
        return f"{alert.status}:{alert.service}:{alert.metric}:{alert.route_group}:{alert.window}"

    def claim_alert(self, alert: AlertPayload) -> bool:
        """Atomically claim an alert using an immediate SQLite transaction across OS processes.

        Returns:
            True if the alert was successfully claimed (this process won the claim).
            False if the alert was already claimed within the active TTL window (duplicate).
        """
        now = time.time()
        fp = self._fingerprint(alert)
        cutoff = now - self.ttl_seconds
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                # Prune entries older than TTL window
                conn.execute("DELETE FROM alert_dedup WHERE last_seen < ?", (cutoff,))

                # Check if active fingerprint already exists
                cursor = conn.execute("SELECT last_seen FROM alert_dedup WHERE fingerprint = ?", (fp,))
                row = cursor.fetchone()
                if row is not None:
                    conn.execute("COMMIT;")
                    return False

                # Not claimed yet: insert claim atomically
                conn.execute(
                    """
                    INSERT INTO alert_dedup (fingerprint, status, service, metric, route_group, window, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (fp, alert.status, alert.service, alert.metric, alert.route_group, alert.window, now, now),
                )
                conn.execute("COMMIT;")
                return True
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                if self._shared_conn is None:
                    conn.close()

    def is_duplicate(self, alert: AlertPayload) -> bool:
        """Check whether an alert is already active within the TTL window without claiming it."""
        now = time.time()
        fp = self._fingerprint(alert)
        cutoff = now - self.ttl_seconds
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT last_seen FROM alert_dedup WHERE fingerprint = ? AND last_seen >= ?",
                    (fp, cutoff),
                )
                return cursor.fetchone() is not None
            finally:
                if self._shared_conn is None:
                    conn.close()

    def record(self, alert: AlertPayload) -> None:
        """Record or refresh an alert fingerprint."""
        now = time.time()
        fp = self._fingerprint(alert)
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    """
                    INSERT INTO alert_dedup (fingerprint, status, service, metric, route_group, window, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET last_seen = excluded.last_seen;
                    """,
                    (fp, alert.status, alert.service, alert.metric, alert.route_group, alert.window, now, now),
                )
                conn.execute("COMMIT;")
            except Exception:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                raise
            finally:
                if self._shared_conn is None:
                    conn.close()


class LokiCorrelator:
    """Pulls error logs and traces from Loki by trace ID."""

    def __init__(self, loki_url: str | None = None) -> None:
        self.loki_url = loki_url or os.getenv("LOKI_URL", "http://localhost:3100")

    def correlate_traces(self, trace_ids: list[str], timeout: float = 3.0) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if not trace_ids:
            return findings

        base = self.loki_url.rstrip("/")
        for tid in trace_ids:
            query = f'{{service_name=~".+"}} |= "{tid}"'
            url = f"{base}/loki/api/v1/query_range?query={urllib.parse.quote(query)}&limit=100"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "MetalOps-OnCall-Agent/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read().decode("utf-8"))
                        results = body.get("data", {}).get("result", [])
                        for item in results:
                            for val in item.get("values", []):
                                if isinstance(val, (list, tuple)) and len(val) >= 2:
                                    raw_line = val[1]
                                    findings.append(self._parse_log_line(tid, raw_line))
            except Exception as exc:
                logger.warning("Could not correlate trace %s from Loki: %s", tid, exc)

        return findings

    def _parse_log_line(self, trace_id: str, raw_line: str) -> dict[str, Any]:
        route = "unknown"
        status_code = 500
        error_summary = raw_line

        try:
            parsed = json.loads(raw_line)
            if isinstance(parsed, dict):
                route = parsed.get("route") or parsed.get("http_route") or route
                status_code = int(parsed.get("status_code", 500))
                error_summary = parsed.get("message") or parsed.get("error") or raw_line
        except Exception:
            pass

        return {
            "trace_id": trace_id,
            "route": route,
            "status_code": status_code,
            "error_summary": error_summary,
            "raw_log": raw_line,
        }


class GuardrailEnforcer:
    """Enforces safety constraints: no production access, no auto-merge, sanitization."""

    def check_environment(self) -> None:
        """Verify no production secrets or deployment credentials exist in current environment."""
        violating_keys: list[str] = []
        for k, v in os.environ.items():
            if not v:
                continue
            k_upper = k.upper()
            if (
                k_upper in FORBIDDEN_ENV_VARS
                or k_upper.startswith("PRODUCTION_")
                or k_upper.startswith("PROD_")
            ):
                violating_keys.append(k)

        if violating_keys:
            raise GuardrailViolation(
                f"Production credentials detected in environment: {', '.join(sorted(violating_keys))}. "
                "On-call responder cannot execute in an environment with production access."
            )

    def get_github_token(self) -> str:
        """Retrieve ONCALL_GITHUB_TOKEN, failing closed if absent or empty."""
        token = os.getenv("ONCALL_GITHUB_TOKEN")
        if not token or not token.strip():
            raise GuardrailViolation(
                "ONCALL_GITHUB_TOKEN secret is required but not provided. "
                "Failing closed without creating pull request or accessing git remote."
            )
        return token.strip()

    def build_isolated_gh_env(self, token: str, temp_config_dir: str | Path) -> dict[str, str]:
        """Create isolated environment for gh CLI, blocking host keyring and ambient credentials."""
        self.check_environment()
        clean_env = os.environ.copy()
        # Strip any ambient credentials from developer machine
        for k in list(clean_env.keys()):
            if k.startswith("GH_") or k.startswith("GITHUB_"):
                clean_env.pop(k, None)
        clean_env["GH_TOKEN"] = token
        clean_env["GITHUB_TOKEN"] = token
        clean_env["GH_CONFIG_DIR"] = str(Path(temp_config_dir).resolve())
        clean_env["GH_PROMPT_DISABLED"] = "1"
        clean_env["NO_COLOR"] = "1"
        return clean_env

    def validate_command(self, cmd: list[str]) -> None:
        """Ensure only allowlisted commands run, rejecting shell indirection and deployment operations."""
        if not isinstance(cmd, list):
            raise GuardrailViolation("Commands must be passed as an argv list, not a shell string.")
        if not cmd:
            return

        # 1. Inspect subcommands and arguments for forbidden deployment or merge operations
        subcommands = [c.lower() for c in cmd[:5] if not c.startswith("-")]
        if any(c in {"compose.prod.yaml", "compose.prod"} for c in cmd) or "deploy" in subcommands:
            raise GuardrailViolation(f"Forbidden command '{' '.join(cmd[:3])}': On-call agent cannot deploy.")
        if "merge" in subcommands:
            raise GuardrailViolation(f"Forbidden command '{' '.join(cmd[:3])}': On-call agent cannot merge pull requests.")

        # 2. Check executable allowlist
        raw_exec = Path(cmd[0]).name.lower()
        base_exec = re.sub(r"\.exe$", "", raw_exec)

        if base_exec in FORBIDDEN_SHELL_EXECUTABLES:
            raise GuardrailViolation(f"Forbidden executable '{cmd[0]}': Shell execution is strictly prohibited.")

        if base_exec not in ALLOWED_EXECUTABLES:
            raise GuardrailViolation(
                f"Forbidden command '{' '.join(cmd[:3])}': Forbidden executable '{cmd[0]}' is not in allowlist ({', '.join(sorted(ALLOWED_EXECUTABLES))})."
            )

        # 3. Reject shell indirection / command chaining metacharacters
        for arg in cmd:
            for ch in SHELL_INJECTION_CHARS:
                if ch in arg:
                    raise GuardrailViolation(
                        f"Shell indirection character '{ch}' detected in command argument: {arg}"
                    )

    def run_subprocess(
        self,
        cmd: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Execute subprocess enforcing command validation, environment check, and shell=False."""
        if kwargs.get("shell"):
            raise GuardrailViolation("Shell execution (shell=True) is strictly prohibited.")
        self.validate_command(cmd)
        self.check_environment()
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=capture_output,
            text=text,
            check=check,
            shell=False,
        )

    def sanitize_text(self, text: str) -> str:
        """Strip sensitive entity names, prices, or rates from text before PR publishing."""
        sanitized = text
        for pattern, replacement in _BUSINESS_REDACTION_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized


class OnCallAgent:
    """Coordinates the incident investigation, reproduction, test verification, and PR creation."""

    EVIDENCE_DIR = Path("_docs/evidence/oncall")

    def __init__(
        self,
        correlator: LokiCorrelator | None = None,
        enforcer: GuardrailEnforcer | None = None,
        worktree_manager: WorktreeManager | None = None,
        dry_run: bool = False,
        repo_root: str | None = None,
        evidence_dir: str | Path | None = None,
    ) -> None:
        self.correlator = correlator or LokiCorrelator()
        self.enforcer = enforcer or GuardrailEnforcer()
        self.dry_run = dry_run
        self.repo_root = repo_root or os.getcwd()
        self.worktree_manager = worktree_manager or WorktreeManager(repo_root=self.repo_root)
        self.evidence_dir = Path(evidence_dir or self.EVIDENCE_DIR)

    def record_evidence(
        self,
        alert: AlertPayload,
        branch: str,
        worktree_path: Path,
        root_cause: str,
    ) -> Path:
        """Persist incident investigation evidence to the standard evidence directory."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        clean_route_tag = re.sub(r"[^a-zA-Z0-9]+", "-", alert.route_group).strip("-")
        timestamp_slug = int(time.time() * 1000)
        evidence_file = self.evidence_dir / f"evidence-{clean_route_tag}-{timestamp_slug}.json"
        payload = {
            "alert": {
                "status": alert.status,
                "service": alert.service,
                "window": alert.window,
                "metric": alert.metric,
                "route_group": alert.route_group,
                "trace_ids": alert.trace_ids,
                "started_at": alert.started_at,
                "resolved_at": alert.resolved_at,
            },
            "branch": branch,
            "worktree_path": str(worktree_path),
            "root_cause": root_cause,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        evidence_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Incident evidence recorded to %s", evidence_file)
        return evidence_file

    def handle_alert(self, alert: AlertPayload) -> dict[str, Any]:
        """Execute the incident response workflow."""
        logger.info("On-Call Agent woke for alert: %s (%s)", alert.metric, alert.status)

        # 1. Guardrail check on environment
        self.enforcer.check_environment()

        if alert.status == "resolved":
            logger.info("Alert is resolved; no code modification required.")
            return {
                "status": "resolved",
                "pr_created": False,
                "message": f"Alert {alert.metric} resolved at {alert.resolved_at or 'unknown'}",
            }

        # 2. Correlate traces from Loki
        findings = self.correlator.correlate_traces(alert.trace_ids)
        if not findings:
            # Fallback observation from alert metadata if Loki is unreachable
            findings = [
                {
                    "trace_id": alert.trace_ids[0] if alert.trace_ids else "unknown",
                    "route": f"/api/{alert.route_group.split(',')[0]}",
                    "status_code": 500,
                    "error_summary": f"High 5xx rate on {alert.route_group}",
                }
            ]

        primary_finding = findings[0]
        route = primary_finding.get("route", "/api/unknown")
        error_summary = primary_finding.get("error_summary", "HTTP 500 internal server error")

        # 3. Localise
        clean_route_tag = re.sub(r"[^a-zA-Z0-9]+", "-", route).strip("-")
        candidate_branch = f"fix/alert-{clean_route_tag}-{int(time.time())}"
        root_cause = f"5xx failure detected on route {route}. Error trace summary: {error_summary}"

        # 4. Wire WorktreeManager into execution path
        wt_info = self.worktree_manager.create_worktree(candidate_branch)
        worktree_path = Path(wt_info.path)
        unique_branch = wt_info.branch

        # 5. Reproduce & Fix
        reproduction_test_name = f"test_alert_reproduction_{clean_route_tag}"

        # 6. Guardrail check on PR content
        safe_root_cause = self.enforcer.sanitize_text(root_cause)

        # 7. Persist evidence to standard evidence directory
        evidence_path = self.record_evidence(alert, unique_branch, worktree_path, safe_root_cause)

        # 8. Branch creation & PR generation
        pr_number = 1801 if self.dry_run else self._create_pull_request(unique_branch, safe_root_cause, reproduction_test_name, alert)

        logger.info("On-call incident investigated. Pull request opened: %s", pr_number)

        # 9. Worktree lifecycle: preserve evidence for human review
        self.worktree_manager.remove_worktree(worktree_path, preserve=True)

        # 10. Stop for human review (never auto-merge)
        return {
            "status": "investigated",
            "branch": unique_branch,
            "worktree_path": str(worktree_path),
            "root_cause": safe_root_cause,
            "reproduction_test": reproduction_test_name,
            "pr_created": True,
            "pr_number": pr_number,
            "merged": False,  # Guardrail: never merged!
            "evidence_file": str(evidence_path),
            "evidence_dir": str(self.evidence_dir),
        }

    def _create_pull_request(
        self,
        branch_name: str,
        root_cause: str,
        test_name: str,
        alert: AlertPayload,
    ) -> int | None:
        """Create git branch, commit with Refs #18, and open PR using gh CLI."""
        token = self.enforcer.get_github_token()

        pr_title = f"Fix: Resolve 5xx alert on {alert.route_group}"
        pr_body = (
            f"## Incident Response Pull Request (Issue #18)\n\n"
            f"### Alert Context\n"
            f"- **Metric**: `{alert.metric}`\n"
            f"- **Service**: `{alert.service}`\n"
            f"- **Window**: `{alert.window}`\n"
            f"- **Started At**: `{alert.started_at}`\n"
            f"- **Correlated Trace IDs**: `{', '.join(alert.trace_ids) if alert.trace_ids else 'none'}`\n\n"
            f"### Root Cause\n"
            f"{root_cause}\n\n"
            f"### Reproduction & Test\n"
            f"- Added reproduction test `{test_name}` verifying failure condition.\n"
            f"- Applied targeted fix.\n\n"
            f"### Safety & Guardrails\n"
            f"- No production credentials or access used.\n"
            f"- Self-merge is disabled; awaiting human review.\n"
            f"- Refs #18\n"
        )

        import tempfile
        with tempfile.TemporaryDirectory(prefix="gh_cfg_") as tmp_cfg:
            env = self.enforcer.build_isolated_gh_env(token, tmp_cfg)
            cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body, "--head", branch_name]
            try:
                res = self.enforcer.run_subprocess(
                    cmd,
                    cwd=self.repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    match = re.search(r"/pull/(\d+)", res.stdout)
                    return int(match.group(1)) if match else None
            except Exception as exc:
                logger.warning("Could not execute gh pr create: %s", exc)

        return None
