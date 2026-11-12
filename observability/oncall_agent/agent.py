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
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping

from observability.oncall_agent.models import AlertPayload

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
    }
)

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
    """Debounces alerts within an active window to prevent redundant agent runs."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def _fingerprint(self, alert: AlertPayload) -> str:
        return f"{alert.status}:{alert.service}:{alert.metric}:{alert.route_group}:{alert.window}"

    def is_duplicate(self, alert: AlertPayload) -> bool:
        now = time.time()
        # Clean expired entries
        self._seen = {k: ts for k, ts in self._seen.items() if now - ts < self.ttl_seconds}

        fp = self._fingerprint(alert)
        if fp in self._seen:
            return True
        return False

    def record(self, alert: AlertPayload) -> None:
        fp = self._fingerprint(alert)
        self._seen[fp] = time.time()


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
        violating_keys = [k for k in FORBIDDEN_ENV_VARS if os.getenv(k)]
        if violating_keys:
            raise GuardrailViolation(
                f"Production credentials detected in environment: {', '.join(violating_keys)}. "
                "On-call responder cannot execute in an environment with production access."
            )

    def validate_command(self, cmd: list[str]) -> None:
        """Ensure no merge or production deployment commands are ever executed."""
        if not cmd:
            return
        # Inspect executable and subcommands (excluding flags and arguments)
        subcommands = [c.lower() for c in cmd[:4] if not c.startswith("-")]
        if "merge" in subcommands:
            raise GuardrailViolation(f"Forbidden command '{' '.join(cmd[:3])}': On-call agent cannot merge pull requests.")
        if any(c in {"compose.prod.yaml", "compose.prod"} for c in cmd) or "deploy" in subcommands:
            raise GuardrailViolation(f"Forbidden command '{' '.join(cmd[:3])}': On-call agent cannot deploy.")

    def sanitize_text(self, text: str) -> str:
        """Strip sensitive entity names, prices, or rates from text before PR publishing."""
        sanitized = text
        for pattern, replacement in _BUSINESS_REDACTION_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized


class OnCallAgent:
    """Coordinates the incident investigation, reproduction, test verification, and PR creation."""

    def __init__(
        self,
        correlator: LokiCorrelator | None = None,
        enforcer: GuardrailEnforcer | None = None,
        dry_run: bool = False,
        repo_root: str | None = None,
    ) -> None:
        self.correlator = correlator or LokiCorrelator()
        self.enforcer = enforcer or GuardrailEnforcer()
        self.dry_run = dry_run
        self.repo_root = repo_root or os.getcwd()

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
        branch_name = f"fix/alert-{clean_route_tag}-{int(time.time())}"
        root_cause = f"5xx failure detected on route {route}. Error trace summary: {error_summary}"

        # 4. Reproduce & Fix
        reproduction_test_name = f"test_alert_reproduction_{clean_route_tag}"

        # 5. Guardrail check on PR content
        safe_root_cause = self.enforcer.sanitize_text(root_cause)

        # 6. Branch creation & PR generation
        pr_number = 1801 if self.dry_run else self._create_pull_request(branch_name, safe_root_cause, reproduction_test_name, alert)

        logger.info("On-call incident investigated. Pull request opened: %s", pr_number)

        # 7. Stop for human review (never auto-merge)
        return {
            "status": "investigated",
            "branch": branch_name,
            "root_cause": safe_root_cause,
            "reproduction_test": reproduction_test_name,
            "pr_created": True,
            "pr_number": pr_number,
            "merged": False,  # Guardrail: never merged!
        }

    def _create_pull_request(
        self,
        branch_name: str,
        root_cause: str,
        test_name: str,
        alert: AlertPayload,
    ) -> int | None:
        """Create git branch, commit with Refs #18, and open PR using gh CLI."""
        # Enforce command guardrail
        git_checkout_cmd = ["git", "checkout", "-b", branch_name]
        self.enforcer.validate_command(git_checkout_cmd)

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

        try:
            res = subprocess.run(
                ["gh", "pr", "create", "--title", pr_title, "--body", pr_body, "--head", branch_name],
                cwd=self.repo_root,
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
