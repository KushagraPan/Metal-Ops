"""Unit tests for observability.oncall_agent.worker.

Tests deterministic worker functions before code authoring:
1. fetch_evidence(alert)
2. build_prompt(evidence, source_files)
3. call_llm(prompt)
4. parse_diff(text) and validate_diff(diff)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from observability.oncall_agent.models import AlertPayload
from observability.oncall_agent.worker import (
    DiffValidationError,
    build_prompt,
    call_llm,
    fetch_evidence,
    parse_diff,
    validate_diff,
)


@pytest.fixture
def sample_alert() -> AlertPayload:
    return AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=["0123456789abcdef0123456789abcdef"],
        started_at="2026-11-13T12:00:00Z",
    )


# ==============================================================================
# 1. fetch_evidence
# ==============================================================================


def test_fetch_evidence_success(sample_alert):
    mock_loki = {
        "status": "success",
        "data": {
            "result": [
                {
                    "values": [
                        [
                            "1731412800000000000",
                            json.dumps(
                                {
                                    "message": "Error processing purchase from Acme Scrap Ltd at Rs 210/kg",
                                    "amount": "Rs 50,000",
                                }
                            ),
                        ]
                    ]
                }
            ]
        },
    }
    mock_tempo = {
        "batches": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "0123456789abcdef0123456789abcdef",
                                "name": "POST /api/reports/upload",
                                "status": {"code": 2},
                            }
                        ]
                    }
                ]
            }
        ]
    }

    def fake_urlopen(req, timeout=3.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        mock_resp = MagicMock()
        mock_resp.status = 200
        if "loki" in url:
            mock_resp.read.return_value = json.dumps(mock_loki).encode("utf-8")
        else:
            mock_resp.read.return_value = json.dumps(mock_tempo).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        evidence = fetch_evidence(sample_alert)
        assert isinstance(evidence, str)
        assert len(evidence.encode("utf-8")) <= 8192
        # Redaction check
        assert "Acme Scrap" not in evidence
        assert "Rs 210" not in evidence
        assert "[REDACTED" in evidence
        assert "POST /api/reports/upload" in evidence


def test_fetch_evidence_truncation_to_8kb(sample_alert):
    huge_log = "ERROR line message info " * 1000  # > 20 KB
    mock_loki = {
        "status": "success",
        "data": {"result": [{"values": [["1731412800000000000", huge_log]]}]},
    }

    def fake_urlopen(req, timeout=3.0):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_loki).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        evidence = fetch_evidence(sample_alert)
        assert len(evidence.encode("utf-8")) <= 8192


def test_fetch_evidence_handles_errors_gracefully(sample_alert):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        evidence = fetch_evidence(sample_alert)
        assert "evidence unavailable" in evidence.lower()

    alert_no_traces = AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=[],
        started_at="2026-11-13T12:00:00Z",
    )
    evidence_none = fetch_evidence(alert_no_traces)
    assert "evidence unavailable" in evidence_none.lower()


# ==============================================================================
# 2. build_prompt
# ==============================================================================


def test_build_prompt_with_source_files():
    evidence = "HTTP 500 error on /api/reports/upload trace 123"
    source_files = {
        "app/routers/reports.py": "# reports router content\ndef upload(): pass\n",
        "app/services/reports.py": "# reports service content\nclass ReportService: pass\n",
        "app/storage/local.py": "# local storage content\nclass LocalStorage: pass\n",
        "app/models/report.py": "# 4th file should be ignored",
    }
    prompt = build_prompt(evidence, source_files=source_files)
    assert evidence in prompt
    assert "app/routers/reports.py" in prompt
    assert "app/services/reports.py" in prompt
    assert "app/storage/local.py" in prompt
    # Maximum 3 files included
    assert "app/models/report.py" not in prompt


def test_build_prompt_selects_files_by_alert_route(sample_alert):
    evidence = "HTTP 500 failure"
    repo_root = Path(__file__).resolve().parents[2]
    prompt = build_prompt(evidence, alert=sample_alert, repo_root=repo_root)
    assert evidence in prompt
    assert "app/" in prompt
    # Must contain at least one relevant app file text
    assert "reports.py" in prompt


# ==============================================================================
# 3. call_llm
# ==============================================================================


def test_call_llm_with_fake_client():
    fake_client = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = "```diff\n--- a/tests/test_foo.py\n+++ b/tests/test_foo.py\n@@ -1 +1 @@\n-old\n+new\n```"
    fake_client.chat.completions.create.return_value = MagicMock(choices=[fake_choice])

    prompt = "Fix the alert"
    resp = call_llm(prompt, client=fake_client, timeout=120.0)

    assert "--- a/tests/test_foo.py" in resp
    fake_client.chat.completions.create.assert_called_once()
    call_kwargs = fake_client.chat.completions.create.call_args[1]
    assert call_kwargs["timeout"] == 120.0


def test_call_llm_uses_env_vars(monkeypatch):
    monkeypatch.setenv("ONCALL_LLM_ENDPOINT", "http://mock-llm:8000/v1/chat")
    monkeypatch.setenv("ONCALL_LLM_MODEL", "custom-model-x")

    def fake_urlopen(req, timeout=120.0):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "diff --git a/tests/test_x.py b/tests/test_x.py"}}]}
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = call_llm("test prompt", client=None)
        assert "diff --git" in res


# ==============================================================================
# 4. parse_diff & validate_diff
# ==============================================================================


def test_parse_diff_extracts_unified_diff():
    wrapped_text = (
        "Here is the candidate fix:\n\n"
        "```diff\n"
        "--- a/tests/unit/test_foo.py\n"
        "+++ b/tests/unit/test_foo.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def test_one():\n"
        "+    assert True\n"
        "--- a/app/foo.py\n"
        "+++ b/app/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
        "```\n"
        "End of response."
    )
    diff = parse_diff(wrapped_text)
    assert diff.startswith("--- a/tests/unit/test_foo.py")
    assert "+new" in diff


def test_parse_diff_rejects_non_diff():
    with pytest.raises(ValueError, match="No unified diff found"):
        parse_diff("Just regular explanation without any unified diff headers.")


def test_validate_diff_success():
    valid_diff = (
        "--- a/tests/unit/test_reproduction.py\n"
        "+++ b/tests/unit/test_reproduction.py\n"
        "@@ -0,0 +1,5 @@\n"
        "+def test_reproduce():\n"
        "+    assert False\n"
        "--- a/app/storage/local.py\n"
        "+++ b/app/storage/local.py\n"
        "@@ -10,2 +10,3 @@\n"
        "-    pass\n"
        "+    self.root.mkdir(parents=True, exist_ok=True)\n"
    )
    assert validate_diff(valid_diff) is True


def test_validate_diff_rejects_missing_tests_file():
    app_only_diff = (
        "--- a/app/storage/local.py\n"
        "+++ b/app/storage/local.py\n"
        "@@ -10,2 +10,3 @@\n"
        "-    pass\n"
        "+    return True\n"
    )
    with pytest.raises(DiffValidationError, match="Must contain at least one new or changed file under tests/"):
        validate_diff(app_only_diff)


def test_validate_diff_rejects_forbidden_directories():
    forbidden_targets = [
        (".github/workflows/ci.yml", "--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("scripts/dev.py", "--- a/scripts/dev.py\n+++ b/scripts/dev.py\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("compose.yaml", "--- a/compose.yaml\n+++ b/compose.yaml\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("compose.prod.yaml", "--- a/compose.prod.yaml\n+++ b/compose.prod.yaml\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("Dockerfile", "--- a/Dockerfile\n+++ b/Dockerfile\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("requirements.txt", "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        (".env.example", "--- a/.env.example\n+++ b/.env.example\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("observability/worker.py", "--- a/observability/worker.py\n+++ b/observability/worker.py\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("migrations/env.py", "--- a/migrations/env.py\n+++ b/migrations/env.py\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
        ("Makefile", "--- a/Makefile\n+++ b/Makefile\n@@ -1 +1 @@\n-a\n+b\n--- a/tests/t.py\n+++ b/tests/t.py\n@@ -0,0 +1 @@\n+x\n"),
    ]
    for name, diff in forbidden_targets:
        with pytest.raises(DiffValidationError, match="Forbidden path modified"):
            validate_diff(diff)


def test_validate_diff_rejects_path_traversal():
    traversal_diff = (
        "--- a/tests/../etc/passwd\n"
        "+++ b/tests/../etc/passwd\n"
        "@@ -1 +1 @@\n"
        "+evil\n"
        "--- a/tests/unit/test_ok.py\n"
        "+++ b/tests/unit/test_ok.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_ok(): pass\n"
    )
    with pytest.raises(DiffValidationError, match="Path traversal"):
        validate_diff(traversal_diff)


def test_validate_diff_rejects_binary_patches():
    binary_diff = (
        "--- a/tests/unit/test_ok.py\n"
        "+++ b/tests/unit/test_ok.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_ok(): pass\n"
        "GIT binary patch\n"
        "literal 12\n"
        "zc$@0\n"
    )
    with pytest.raises(DiffValidationError, match="Binary patches are not allowed"):
        validate_diff(binary_diff)


def test_validate_diff_rejects_symlinks():
    symlink_diff = (
        "--- a/tests/unit/test_ok.py\n"
        "+++ b/tests/unit/test_ok.py\n"
        "@@ -0,0 +1 @@\n"
        "+def test_ok(): pass\n"
        "diff --git a/app/link b/app/link\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/app/link\n"
        "@@ -0,0 +1 @@\n"
        "+/etc/passwd\n"
    )
    with pytest.raises(DiffValidationError, match="Symlinks are not allowed"):
        validate_diff(symlink_diff)


def test_validate_diff_rejects_over_200_changed_lines():
    added_lines = "\n".join(f"+line {i}" for i in range(205))
    huge_diff = (
        "--- a/tests/unit/test_huge.py\n"
        "+++ b/tests/unit/test_huge.py\n"
        f"@@ -0,0 +1,205 @@\n"
        f"{added_lines}\n"
    )
    with pytest.raises(DiffValidationError, match="exceeds maximum allowed changed lines"):
        validate_diff(huge_diff)

