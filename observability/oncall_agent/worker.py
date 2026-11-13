"""On-Call Worker for MetalOps Lite.

Executes deterministic parts of the incident response loop:
1. fetch_evidence(alert): query Loki and Tempo, redact sensitive data, truncate to 8 KB.
2. build_prompt(evidence, source_files): construct prompt with evidence and up to 3 files under app/.
3. call_llm(prompt): invoke configured model with timeout 120s (no shell access).
4. parse_diff(text) & validate_diff(diff): strictly parse and validate unified diff.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from observability.oncall_agent.models import AlertPayload
from observability.oncall_agent.worktree import WorktreeManager

logger = logging.getLogger("metalops.oncall_worker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

MAX_EVIDENCE_BYTES = 8192
MAX_CHANGED_LINES = 200

# Redaction patterns for sensitive business data
_BUSINESS_REDACTION_PATTERNS = [
    (re.compile(r"(?i)\b(?:Acme\s+Scrap(?:\s+Ltd)?|Supplier\s+[A-Z0-9]+|Customer\s+[A-Z0-9]+)\b"), "[REDACTED_ENTITY]"),
    (re.compile(r"(?i)\b(?:Rs\.?|INR)\s*[\d,]+(?:\.\d{1,2})?(?:/kg)?\b"), "[REDACTED_RATE]"),
    (re.compile(r"\b\d{1,3}(?:,\d{2,3})+\s*(?:kg|INR|Rs)\b"), "[REDACTED_AMOUNT]"),
]

FORBIDDEN_PATH_PREFIXES = (
    ".github/",
    "scripts/",
    "observability/",
    "migrations/",
)

FORBIDDEN_FILE_PATTERNS = (
    "compose",
    "Dockerfile",
    "requirements",
    ".env",
)


class DiffValidationError(ValueError):
    """Raised when a unified diff fails validation rules."""


class DiffApplyError(RuntimeError):
    """Raised when git apply fails to apply a diff hunk."""


def redact_business_info(text: str) -> str:
    """Redact customer/supplier names, rates, and monetary amounts."""
    sanitized = text
    for pattern, replacement in _BUSINESS_REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def fetch_evidence(
    alert: AlertPayload,
    loki_url: str | None = None,
    tempo_url: str | None = None,
    timeout: float = 3.0,
) -> str:
    """Query Loki and Tempo by the alert's trace IDs, redact, and truncate to 8 KB."""
    if not alert.trace_ids:
        return "evidence unavailable: no trace IDs provided in alert payload"

    loki_base = (loki_url or os.getenv("LOKI_URL", "http://localhost:3100")).rstrip("/")
    tempo_base = (tempo_url or os.getenv("TEMPO_URL", "http://localhost:3200")).rstrip("/")

    evidence_sections: list[str] = [
        f"Alert Context: metric={alert.metric}, service={alert.service}, route_group={alert.route_group}, window={alert.window}"
    ]

    for tid in alert.trace_ids:
        # 1. Query Loki
        loki_query = f'{{service_name=~".+"}} |= "{tid}"'
        loki_endpoint = f"{loki_base}/loki/api/v1/query_range?query={urllib.parse.quote(loki_query)}&limit=50"
        try:
            req = urllib.request.Request(loki_endpoint, headers={"User-Agent": "MetalOps-OnCall-Worker/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    results = data.get("data", {}).get("result", [])
                    for stream_item in results:
                        for entry in stream_item.get("values", []):
                            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                                evidence_sections.append(f"Loki [{tid}]: {entry[1]}")
        except Exception as exc:
            logger.warning("Could not fetch Loki logs for trace %s: %s", tid, exc)

        # 2. Query Tempo
        tempo_endpoint = f"{tempo_base}/api/traces/{tid}"
        try:
            req = urllib.request.Request(tempo_endpoint, headers={"User-Agent": "MetalOps-OnCall-Worker/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    raw_tempo = resp.read().decode("utf-8")
                    data = json.loads(raw_tempo)
                    batches = data.get("batches", [])
                    for batch in batches:
                        for scope in batch.get("scopeSpans", []):
                            for span in scope.get("spans", []):
                                span_name = span.get("name", "span")
                                status_code = span.get("status", {}).get("code", 0)
                                evidence_sections.append(f"Tempo [{tid}]: span={span_name}, status={status_code}")
        except Exception as exc:
            logger.warning("Could not fetch Tempo trace %s: %s", tid, exc)

    if len(evidence_sections) <= 1:
        return "evidence unavailable: Loki and Tempo queries returned zero records"

    full_evidence = "\n".join(evidence_sections)
    redacted = redact_business_info(full_evidence)
    encoded = redacted.encode("utf-8")
    if len(encoded) > MAX_EVIDENCE_BYTES:
        return encoded[:MAX_EVIDENCE_BYTES].decode("utf-8", errors="ignore")
    return redacted


def select_relevant_source_files(route_group: str, repo_root: Path | str | None = None) -> dict[str, str]:
    """Select up to 3 relevant application source files under app/ based on route group."""
    root = Path(repo_root or os.getcwd()).resolve()

    route_lower = route_group.lower()
    candidate_paths: list[str] = []

    if "report" in route_lower:
        candidate_paths = ["app/routers/reports.py", "app/services/reports.py", "app/storage/local.py"]
    elif "heat" in route_lower:
        candidate_paths = ["app/routers/heats.py", "app/services/heats.py", "app/calc.py"]
    elif "sale" in route_lower:
        candidate_paths = ["app/routers/sales.py", "app/services/sales.py", "app/calc.py"]
    elif "purchase" in route_lower:
        candidate_paths = ["app/routers/purchases.py", "app/services/purchases.py", "app/calc.py"]
    else:
        candidate_paths = ["app/routers/reports.py", "app/services/reports.py", "app/calc.py"]

    selected: dict[str, str] = {}
    for rel_path in candidate_paths[:3]:
        full_file = root / rel_path
        if full_file.is_file():
            try:
                selected[rel_path] = full_file.read_text(encoding="utf-8")
            except Exception:
                pass
    return selected


def build_prompt(
    evidence: str,
    source_files: dict[str, str] | None = None,
    alert: AlertPayload | None = None,
    repo_root: Path | str | None = None,
) -> str:
    """Build prompt containing the evidence and full text of up to 3 relevant files under app/."""
    files_to_include: dict[str, str] = {}

    if source_files is not None:
        # Filter down to at most 3 files under app/
        for p, content in source_files.items():
            clean_p = p.replace("\\", "/")
            if clean_p.startswith("app/") and len(files_to_include) < 3:
                files_to_include[clean_p] = content
    elif alert is not None:
        files_to_include = select_relevant_source_files(alert.route_group, repo_root=repo_root)

    prompt_lines = [
        "You are an on-call software engineer responding to an active 5xx alert.",
        "Your task: produce a minimal unified diff fixing the root cause, accompanied by a reproduction test.",
        "",
        "### CRITICAL CONSTRAINTS",
        "1. You only receive text and return text. You do NOT have shell or command execution access.",
        "2. The diff MUST contain at least one new or updated test under `tests/` reproducing the issue.",
        "3. Any modified application code must strictly reside under `app/`.",
        "4. Modifying configuration, build files, scripts, migrations, or CI is strictly forbidden.",
        "5. Output ONLY the unified diff (starting with `--- a/...` and `+++ b/...`).",
        "",
        "### INCIDENT EVIDENCE",
        evidence,
        "",
        "### RELEVANT APPLICATION SOURCE FILES",
    ]

    for fpath, fcontent in files_to_include.items():
        prompt_lines.append(f"\n--- File: {fpath} ---")
        prompt_lines.append(fcontent)

    prompt_lines.append("\n### CANDIDATE FIX UNIFIED DIFF")
    return "\n".join(prompt_lines)


def call_llm(
    prompt: str,
    endpoint: str | None = None,
    model: str | None = None,
    timeout: float = 120.0,
    client: Any | None = None,
) -> str:
    """Invoke LLM endpoint with 120s timeout, returning response text."""
    resolved_model = model or os.getenv("ONCALL_LLM_MODEL", "gemini-1.5-pro")
    resolved_endpoint = endpoint or os.getenv("ONCALL_LLM_ENDPOINT", "http://localhost:8000/v1/chat/completions")
    api_key = os.getenv("ONCALL_LLM_API_KEY", "")

    if client is not None:
        if callable(client):
            try:
                res = client(prompt)
                if isinstance(res, str):
                    return res
            except Exception:
                pass

        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            return resp.choices[0].message.content
        elif callable(client):
            return str(client(prompt))
        elif hasattr(client, "generate"):
            return client.generate(prompt=prompt, model=resolved_model, timeout=timeout)
        raise ValueError(f"Unsupported fake client interface: {type(client)}")

    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "MetalOps-OnCall-Worker/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        resolved_endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices and "message" in choices[0]:
            return choices[0]["message"].get("content", "")
        return json.dumps(body)


def parse_diff(text: str) -> str:
    """Extract and parse unified diff from text output."""
    clean = text.strip()

    # If wrapped in markdown code fence, extract fence content
    fence_match = re.search(r"```(?:diff|patch)?\s*\n([\s\S]*?)\n```", clean, re.IGNORECASE)
    if fence_match:
        clean = fence_match.group(1).strip()

    # Must contain unified diff file headers
    if not (("--- " in clean and "+++ " in clean) or "diff --git " in clean):
        raise ValueError("No unified diff found in text response.")

    return clean


def _extract_diff_paths(diff: str) -> list[str]:
    """Extract touched relative file paths from unified diff."""
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                target = parts[1].strip()
                if target == "/dev/null":
                    continue
                # Strip standard prefixes like a/ and b/
                cleaned = re.sub(r"^[ab]/", "", target).replace("\\", "/")
                paths.append(cleaned)
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                p_b = re.sub(r"^[ab]/", "", parts[3]).replace("\\", "/")
                paths.append(p_b)
    return list(dict.fromkeys(paths))  # preserve order, unique


def validate_diff(diff: str) -> bool:
    """Enforce strict validation rules on the unified diff.

    Rules:
    - Only paths under tests/ or app/
    - Reject .github/, scripts/, compose*.yaml, Dockerfile, requirements*.txt, .env*, observability/, migrations/
    - Max 200 changed lines
    - No binary patches
    - No path traversal
    - No symlinks
    - Must contain at least one new or changed file under tests/
    """
    # 1. No binary patches
    if "GIT binary patch" in diff or "Binary files " in diff:
        raise DiffValidationError("Binary patches are not allowed in fix diff.")

    # 2. No symlinks (mode 120000 in git diff)
    if "120000" in diff:
        raise DiffValidationError("Symlinks are not allowed in fix diff.")

    # 3. Path inspection
    touched_paths = _extract_diff_paths(diff)
    if not touched_paths:
        raise DiffValidationError("No modified file paths found in diff.")

    has_test_file = False
    for p in touched_paths:
        # Check path traversal
        normalized = Path(p)
        if ".." in normalized.parts or p.startswith(("/", "\\")) or ":" in p:
            raise DiffValidationError(f"Path traversal detected in diff target: {p}")

        # Check forbidden directory prefixes
        if any(p.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES):
            raise DiffValidationError(f"Forbidden path modified in diff: {p}")

        # Check forbidden file patterns
        if any(pat in p for pat in FORBIDDEN_FILE_PATTERNS):
            raise DiffValidationError(f"Forbidden path modified in diff: {p}")

        # Only tests/ or app/
        if not (p.startswith("tests/") or p.startswith("app/")):
            raise DiffValidationError(f"Forbidden path modified in diff: {p}. Only paths under app/ and tests/ are allowed.")

        if p.startswith("tests/"):
            has_test_file = True

    # 4. Must contain at least one new or changed file under tests/
    if not has_test_file:
        raise DiffValidationError("Must contain at least one new or changed file under tests/.")

    # 5. Max 200 changed lines (added + removed lines, excluding headers)
    changed_line_count = 0
    for line in diff.splitlines():
        if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")):
            changed_line_count += 1

    if changed_line_count > MAX_CHANGED_LINES:
        raise DiffValidationError(
            f"Diff exceeds maximum allowed changed lines (200): observed {changed_line_count} changed lines."
        )

    return True


def build_minimal_env(worktree_path: Path) -> dict[str, str]:
    """Construct minimal clean environment for worktree subprocess execution."""
    env: dict[str, str] = {}
    for k in ["PATH", "SystemRoot", "WINDIR", "TMP", "TEMP"]:
        val = os.environ.get(k)
        if val:
            env[k] = val

    env["HOME"] = str(worktree_path.resolve())
    env["USERPROFILE"] = str(worktree_path.resolve())

    # Purge all tokens and production credentials
    for k in list(env.keys()):
        k_upper = k.upper()
        if (
            "TOKEN" in k_upper
            or "KEY" in k_upper
            or "SECRET" in k_upper
            or k_upper.startswith("PRODUCTION_")
            or k_upper.startswith("PROD_")
        ):
            env.pop(k, None)

    return env


def split_diff(diff: str) -> tuple[str, str]:
    """Split validated unified diff into tests_diff and app_diff."""
    lines = diff.splitlines(keepends=True)
    chunks: list[list[str]] = []
    current_chunk: list[str] = []

    for line in lines:
        if line.startswith("diff --git ") or (
            line.startswith("--- ") and (not current_chunk or not current_chunk[-1].startswith("diff --git "))
        ):
            if current_chunk and any(l.startswith(("--- ", "+++ ")) for l in current_chunk):
                chunks.append(current_chunk)
                current_chunk = []
        current_chunk.append(line)

    if current_chunk:
        chunks.append(current_chunk)

    tests_chunks: list[str] = []
    app_chunks: list[str] = []

    for chunk in chunks:
        chunk_text = "".join(chunk).rstrip() + "\n"
        paths = _extract_diff_paths(chunk_text)
        if any(p.startswith("tests/") for p in paths):
            tests_chunks.append(chunk_text)
        elif any(p.startswith("app/") for p in paths):
            app_chunks.append(chunk_text)

    tests_diff = "\n".join(tests_chunks).strip()
    if tests_diff:
        tests_diff += "\n"

    app_diff = "\n".join(app_chunks).strip()
    if app_diff:
        app_diff += "\n"

    return tests_diff, app_diff


def apply_diff(worktree_path: Path, patch_text: str, timeout: float = 30.0) -> None:
    """Apply a unified diff patch to the worktree using git apply with fixed command."""
    if not patch_text.strip():
        return
    formatted_patch = patch_text.rstrip() + "\n"
    res = subprocess.run(
        ["git", "apply", "--recount", "--whitespace=nowarn", "--ignore-whitespace", "-"],
        input=formatted_patch,
        cwd=worktree_path,
        env=build_minimal_env(worktree_path),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip() or "git apply failed"
        raise DiffApplyError(f"Failed to apply patch: {err_msg}")


def extract_test_files(tests_diff: str) -> list[str]:
    """Extract paths of test files (.py under tests/) modified in the diff."""
    paths = _extract_diff_paths(tests_diff)
    return [p for p in paths if p.startswith("tests/") and p.endswith(".py")]


def run_incident(
    alert: AlertPayload,
    llm: Any = None,
    worktree_manager: WorktreeManager | None = None,
    repo_root: Path | str | None = None,
    make_test_runner: Callable[[Path, dict[str, str]], tuple[int, str]] | None = None,
) -> dict[str, Any]:
    """Execute incident reproduction and patch workflow in an isolated worktree."""
    root_path = Path(repo_root or os.getcwd()).resolve()
    mgr = worktree_manager or WorktreeManager(repo_root=root_path)

    # 1. Alert fingerprint & isolated worktree branch creation
    raw_fp = f"{alert.status}:{alert.service}:{alert.metric}:{alert.route_group}:{alert.window}"
    fingerprint8 = hashlib.sha256(raw_fp.encode("utf-8")).hexdigest()[:8]
    branch_target = f"oncall/{fingerprint8}"

    wt_info = mgr.create_worktree(branch_target)
    wt_path = wt_info.path
    unique_branch = wt_info.branch
    env = build_minimal_env(wt_path)

    failing_output = ""
    full_test_output_tail = ""

    try:
        # Evidence & LLM query
        evidence = fetch_evidence(alert)
        prompt = build_prompt(evidence, alert=alert, repo_root=wt_path)
        llm_text = call_llm(prompt, client=llm)

        # Diff parsing & validation
        raw_diff = parse_diff(llm_text)
        validate_diff(raw_diff)

        # 2. Split diff into tests/ and app/ parts
        tests_diff, app_diff = split_diff(raw_diff)

        # 3. Apply tests part and run reproduction test (MUST FAIL)
        apply_diff(wt_path, tests_diff, timeout=30.0)
        test_files = extract_test_files(tests_diff)
        if not test_files:
            return {
                "status": "apply_failure",
                "branch": unique_branch,
                "worktree_path": str(wt_path),
                "message": "No valid test file found in tests diff.",
            }

        test_target = test_files[0]
        repro_run = subprocess.run(
            [sys.executable, "-m", "pytest", test_target],
            cwd=wt_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60.0,
        )

        # It MUST FAIL; if it passes, stop with result "not_reproduced", push nothing
        if repro_run.returncode == 0:
            return {
                "status": "not_reproduced",
                "branch": unique_branch,
                "worktree_path": str(wt_path),
                "message": f"Reproduction test {test_target} passed unexpectedly before applying fix.",
                "failing_output": "",
            }

        failing_output = repro_run.stdout + "\n" + repro_run.stderr

        # 4. Apply app part; reproduction test MUST PASS
        if app_diff.strip():
            apply_diff(wt_path, app_diff, timeout=30.0)

        verify_run = subprocess.run(
            [sys.executable, "-m", "pytest", test_target],
            cwd=wt_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        if verify_run.returncode != 0:
            return {
                "status": "fix_failed_to_resolve_test",
                "branch": unique_branch,
                "worktree_path": str(wt_path),
                "message": f"Reproduction test {test_target} still failed after applying fix: {verify_run.stderr.strip() or verify_run.stdout.strip()}",
                "failing_output": failing_output,
            }

        # Run make test (full), save last 40 lines
        if make_test_runner is not None:
            make_code, make_output = make_test_runner(wt_path, env)
        else:
            make_cmd = ["make", "test"]
            res_make = subprocess.run(
                make_cmd,
                cwd=wt_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=300.0,
            )
            make_code = res_make.returncode
            make_output = res_make.stdout + "\n" + res_make.stderr

        make_lines = make_output.strip().splitlines()
        full_test_output_tail = "\n".join(make_lines[-40:])

        if make_code != 0:
            return {
                "status": "full_suite_failed",
                "branch": unique_branch,
                "worktree_path": str(wt_path),
                "message": f"Full test suite failed after applying fix (exit code {make_code})",
                "failing_output": failing_output,
                "full_test_output_tail": full_test_output_tail,
            }

        # 5. Git commit in worktree with fixed message template
        commit_msg = (
            f"Fix: Resolve {alert.metric} on {alert.route_group}\n\n"
            f"Refs #18\n\n"
            f"Incident oncall/{fingerprint8}\n"
            f"Service: {alert.service}\n"
            f"Window: {alert.window}\n"
        )
        subprocess.run(["git", "add", "tests", "app"], cwd=wt_path, env=env, capture_output=True, timeout=30.0, check=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=wt_path, env=env, capture_output=True, timeout=30.0, check=True)

        rev_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt_path, env=env, capture_output=True, text=True, timeout=10.0, check=True)
        commit_sha = rev_res.stdout.strip()

        return {
            "status": "success",
            "branch": unique_branch,
            "worktree_path": str(wt_path),
            "commit_sha": commit_sha,
            "failing_output": failing_output,
            "full_test_output_tail": full_test_output_tail,
            "message": f"Incident successfully reproduced, fixed, and verified on branch {unique_branch}",
            "alert": alert,
            "fingerprint": fingerprint8,
            "evidence": evidence,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "branch": unique_branch,
            "worktree_path": str(wt_path),
            "message": f"Subprocess timed out after {exc.timeout}s: {' '.join(exc.cmd) if isinstance(exc.cmd, list) else exc.cmd}",
        }
    except DiffValidationError as exc:
        return {
            "status": "invalid_diff",
            "branch": unique_branch,
            "worktree_path": str(wt_path),
            "message": f"Generated diff failed validation: {exc}",
        }
    except DiffApplyError as exc:
        return {
            "status": "apply_failure",
            "branch": unique_branch,
            "worktree_path": str(wt_path),
            "message": f"Failed to apply patch: {exc}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "branch": unique_branch,
            "worktree_path": str(wt_path),
            "message": f"Unexpected error during incident processing: {exc}",
        }


ALLOWED_PR_ENV_KEYS = frozenset(
    {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "PROMPT",
        "TMP",
        "TEMP",
        "HOME",
        "USERPROFILE",
        "GH_TOKEN",
        "GH_CONFIG_DIR",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_TERMINAL_PROMPT",
    }
)


def format_pr_body(
    alert_name: str,
    fingerprint: str,
    trace_ids: list[str],
    evidence_summary: str,
    failing_output: str,
    passing_output: str,
    make_test_tail: str,
) -> str:
    """Format PR body adhering strictly to the fixed incident response template."""
    trace_str = ", ".join(trace_ids) if trace_ids else "none"
    return (
        "## Incident Response Fix (Issue #18)\n\n"
        "### Alert Context\n"
        f"- **Alert Name**: `{alert_name}`\n"
        f"- **Fingerprint**: `{fingerprint}`\n"
        f"- **Correlated Trace IDs**: `{trace_str}`\n\n"
        "### Telemetry Evidence Summary\n"
        f"{evidence_summary.strip() or 'No trace evidence available'}\n\n"
        "### Reproduction (Failing Test Run)\n"
        "```text\n"
        f"{failing_output.strip() or 'No failing test output recorded'}\n"
        "```\n\n"
        "### Verification (Passing Test Run)\n"
        "```text\n"
        f"{passing_output.strip() or 'Reproduction test passed after applying fix'}\n"
        "```\n\n"
        "### Full Test Suite Gate (`make test`)\n"
        "```text\n"
        f"{make_test_tail.strip() or 'Full suite passed'}\n"
        "```\n\n"
        "---\n"
        "*Generated by MetalOps On-Call Agent. Never auto-merged. Awaiting human review.*\n"
        "*Refs #18*\n"
    )


def build_pr_env(token: str, temp_dir: Path) -> dict[str, str]:
    """Construct isolated environment for git push and gh pr create from scratch."""
    empty_global = temp_dir / "empty_git_config_global"
    empty_system = temp_dir / "empty_git_config_system"
    empty_global.touch(exist_ok=True)
    empty_system.touch(exist_ok=True)

    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "TMP": str(temp_dir),
        "TEMP": str(temp_dir),
        "HOME": str(temp_dir),
        "USERPROFILE": str(temp_dir),
        "GH_TOKEN": token,
        "GH_CONFIG_DIR": str(temp_dir),
        "GIT_CONFIG_GLOBAL": str(empty_global),
        "GIT_CONFIG_SYSTEM": str(empty_system),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }

    # Only include Windows system directories if present in parent environment
    for sys_key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT"):
        if sys_key in os.environ:
            env[sys_key] = os.environ[sys_key]

    return env


def open_pr(
    result: dict[str, Any],
    repo_root: Path | str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Open a GitHub fix pull request using ONCALL_GITHUB_TOKEN without ambient credential fallback."""
    # 1. Read ONCALL_GITHUB_TOKEN; if missing, fail closed immediately
    token = os.environ.get("ONCALL_GITHUB_TOKEN")
    if not token or not token.strip():
        raise ValueError("ONCALL_GITHUB_TOKEN is missing. Failing closed without credential fallback.")
    token = token.strip()

    # 2. Validate branch ref: refuse any other ref or main
    branch = result.get("branch")
    if not branch:
        raise ValueError("Missing branch in incident result.")

    if branch in ("main", "master") or branch.startswith("main"):
        raise ValueError(f"Push to {branch} is refused. Only oncall/<fingerprint8> branches may be pushed.")

    if not re.match(r"^oncall/[a-zA-Z0-9_\-]+$", branch):
        raise ValueError(f"Refusing ref '{branch}'. Only oncall/<fingerprint8> branches may be pushed.")

    # 3. Isolated environment built from scratch in a fresh temp dir
    with tempfile.TemporaryDirectory(prefix="oncall_gh_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        env = build_pr_env(token, temp_dir)
        cwd = Path(result.get("worktree_path") or repo_root or os.getcwd()).resolve()

        # Locate git and gh binaries (handling .bat / .cmd on Windows when fake bins are used)
        git_bin = shutil.which("git", path=env.get("PATH")) or "git"
        gh_bin = shutil.which("gh", path=env.get("PATH")) or "gh"

        # 4. Push only the oncall branch to origin
        push_cmd = [git_bin, "-c", "credential.helper=!gh auth git-credential", "push", "origin", branch]
        res_push = subprocess.run(
            push_cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res_push.returncode != 0:
            err = res_push.stderr.strip() or res_push.stdout.strip()
            raise RuntimeError(f"git push failed: {err}")

        # 5. Build PR metadata
        alert = result.get("alert")
        if isinstance(alert, AlertPayload):
            alert_name = alert.metric
            route_group = alert.route_group
            trace_ids = alert.trace_ids
        elif isinstance(alert, dict):
            alert_name = alert.get("metric", "5xx_impact")
            route_group = alert.get("route_group", "unknown_route")
            trace_ids = alert.get("trace_ids", [])
        else:
            alert_name = result.get("alert_name", "5xx_impact")
            route_group = result.get("route_group", "unknown_route")
            trace_ids = result.get("trace_ids", [])

        fingerprint = result.get("fingerprint") or branch.split("/")[-1]
        pr_title = f"Fix: Resolve {alert_name} on {route_group}"
        pr_body = format_pr_body(
            alert_name=alert_name,
            fingerprint=fingerprint,
            trace_ids=trace_ids,
            evidence_summary=result.get("evidence", ""),
            failing_output=result.get("failing_output", ""),
            passing_output=result.get("passing_output", "Reproduction test passed after fix applied"),
            make_test_tail=result.get("full_test_output_tail", ""),
        )

        # 6. Open normal OPEN PR (not draft), base main
        pr_cmd = [
            gh_bin,
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            pr_title,
            "--body",
            pr_body,
        ]
        res_pr = subprocess.run(
            pr_cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if res_pr.returncode != 0:
            err = res_pr.stderr.strip() or res_pr.stdout.strip()
            raise RuntimeError(f"gh pr create failed: {err}")

        pr_url = res_pr.stdout.strip()
        match = re.search(r"/pull/(\d+)", pr_url)
        pr_number = int(match.group(1)) if match else None

        return {
            "status": "pr_opened",
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch": branch,
            "title": pr_title,
            "body": pr_body,
        }

