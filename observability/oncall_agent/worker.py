"""On-Call Worker for MetalOps Lite.

Executes deterministic parts of the incident response loop:
1. fetch_evidence(alert): query Loki and Tempo, redact sensitive data, truncate to 8 KB.
2. build_prompt(evidence, source_files): construct prompt with evidence and up to 3 files under app/.
3. call_llm(prompt): invoke configured model with timeout 120s (no shell access).
4. parse_diff(text) & validate_diff(diff): strictly parse and validate unified diff.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from observability.oncall_agent.models import AlertPayload

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
        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
            return resp.choices[0].message.content
        elif callable(client):
            return client(prompt)
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

