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
from observability.oncall_agent.worktree import WorktreeManager
from observability.oncall_agent.worker import (
    DiffApplyError,
    DiffValidationError,
    build_minimal_env,
    build_prompt,
    call_llm,
    fetch_evidence,
    parse_diff,
    run_incident,
    split_diff,
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


# ==============================================================================
# 5. Milestone 2: run_incident & helpers
# ==============================================================================


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    import subprocess
    repo = tmp_path / "mock_repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "OnCall Test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "oncall@test.local"], cwd=repo, check=True, capture_output=True)

    app_dir = repo / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "calc.py").write_text("def compute():\n    return 0\n", encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)
    return repo


def test_build_minimal_env_purges_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "leak_gh_token")
    monkeypatch.setenv("ONCALL_GITHUB_TOKEN", "leak_oncall_token")
    monkeypatch.setenv("PRODUCTION_DATABASE_URL", "leak_prod_db")
    monkeypatch.setenv("PROD_SECRET", "leak_prod_secret")

    env = build_minimal_env(tmp_path)
    assert "PATH" in env
    assert env["HOME"] == str(tmp_path.resolve())
    assert "GH_TOKEN" not in env
    assert "ONCALL_GITHUB_TOKEN" not in env
    assert "PRODUCTION_DATABASE_URL" not in env
    assert "PROD_SECRET" not in env


def test_split_diff_separates_tests_and_app():
    combined_diff = (
        "--- a/tests/unit/test_foo.py\n"
        "+++ b/tests/unit/test_foo.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def test_repro(): pass\n"
        "--- a/app/calc.py\n"
        "+++ b/app/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
    )
    tests_diff, app_diff = split_diff(combined_diff)
    assert "tests/unit/test_foo.py" in tests_diff
    assert "app/calc.py" not in tests_diff
    assert "app/calc.py" in app_diff
    assert "tests/unit/test_foo.py" not in app_diff


def test_run_incident_not_reproduced(temp_git_repo, tmp_path, sample_alert):
    # Canned diff has test that immediately passes
    diff_text = (
        "--- a/tests/unit/test_repro.py\n"
        "+++ b/tests/unit/test_repro.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def test_passing_immediately():\n"
        "+    assert True\n"
        "--- a/app/calc.py\n"
        "+++ b/app/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def compute():\n"
        "-    return 0\n"
        "+    return 0\n"
    )
    fake_llm = MagicMock(return_value=diff_text)
    mgr = WorktreeManager(repo_root=temp_git_repo, worktree_base=tmp_path / "worktrees")

    result = run_incident(sample_alert, llm=fake_llm, worktree_manager=mgr, repo_root=temp_git_repo)
    assert result["status"] == "not_reproduced"
    assert "passed unexpectedly" in result["message"]
    assert result.get("commit_sha") is None


def test_run_incident_reproduced_and_fixed(temp_git_repo, tmp_path, sample_alert):
    # Canned diff has test that fails on compute() == 0, then passes on compute() == 42
    diff_text = (
        "--- a/tests/unit/test_repro.py\n"
        "+++ b/tests/unit/test_repro.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+from app.calc import compute\n"
        "+def test_repro():\n"
        "+    assert compute() == 42\n"
        "--- a/app/calc.py\n"
        "+++ b/app/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def compute():\n"
        "-    return 0\n"
        "+    return 42\n"
    )
    fake_llm = MagicMock(return_value=diff_text)
    mgr = WorktreeManager(repo_root=temp_git_repo, worktree_base=tmp_path / "worktrees")

    # Mock make test
    fake_make_lines = "\n".join(f"make test line {i}" for i in range(50))
    mock_make_runner = MagicMock(return_value=(0, fake_make_lines))

    result = run_incident(
        sample_alert,
        llm=fake_llm,
        worktree_manager=mgr,
        repo_root=temp_git_repo,
        make_test_runner=mock_make_runner,
    )

    assert result["status"] == "success"
    assert result["commit_sha"] is not None
    assert len(result["commit_sha"]) == 40
    assert "assert compute() == 42" in result["failing_output"]
    assert len(result["full_test_output_tail"].splitlines()) == 40
    mock_make_runner.assert_called_once()


def test_run_incident_fix_breaks_other_tests(temp_git_repo, tmp_path, sample_alert):
    diff_text = (
        "--- a/tests/unit/test_repro.py\n"
        "+++ b/tests/unit/test_repro.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+from app.calc import compute\n"
        "+def test_repro():\n"
        "+    assert compute() == 42\n"
        "--- a/app/calc.py\n"
        "+++ b/app/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def compute():\n"
        "-    return 0\n"
        "+    return 42\n"
    )
    fake_llm = MagicMock(return_value=diff_text)
    mgr = WorktreeManager(repo_root=temp_git_repo, worktree_base=tmp_path / "worktrees")

    # Mock make test failing
    mock_make_runner = MagicMock(return_value=(1, "ERROR: regression occurred in sales tests\nFailed 1 test"))

    result = run_incident(
        sample_alert,
        llm=fake_llm,
        worktree_manager=mgr,
        repo_root=temp_git_repo,
        make_test_runner=mock_make_runner,
    )

    assert result["status"] == "full_suite_failed"
    assert result.get("commit_sha") is None
    assert "Full test suite failed" in result["message"]
    mock_make_runner.assert_called_once()


def test_run_incident_apply_failure(temp_git_repo, tmp_path, sample_alert):
    # Canned diff with invalid context that fails git apply
    diff_text = (
        "--- a/tests/unit/test_repro.py\n"
        "+++ b/tests/unit/test_repro.py\n"
        "@@ -100,2 +100,2 @@\n"
        "-nonexistent line\n"
        "+new line\n"
    )
    fake_llm = MagicMock(return_value=diff_text)
    mgr = WorktreeManager(repo_root=temp_git_repo, worktree_base=tmp_path / "worktrees")

    result = run_incident(sample_alert, llm=fake_llm, worktree_manager=mgr, repo_root=temp_git_repo)
    assert result["status"] == "apply_failure"
    assert "Failed to apply" in result["message"]


def test_run_incident_timeout(temp_git_repo, tmp_path, sample_alert):
    import subprocess
    diff_text = (
        "--- a/tests/unit/test_repro.py\n"
        "+++ b/tests/unit/test_repro.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def test_repro(): assert False\n"
        "--- a/app/calc.py\n"
        "+++ b/app/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def compute(): return 0\n"
        "+def compute(): return 42\n"
    )
    fake_llm = MagicMock(return_value=diff_text)
    mgr = WorktreeManager(repo_root=temp_git_repo, worktree_base=tmp_path / "worktrees")

    # Mock subprocess.run raising TimeoutExpired when running pytest
    orig_run = subprocess.run

    def fake_subprocess_run(cmd, *args, **kwargs):
        if "pytest" in cmd:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60.0)
        return orig_run(cmd, *args, **kwargs)

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        result = run_incident(sample_alert, llm=fake_llm, worktree_manager=mgr, repo_root=temp_git_repo)
        assert result["status"] == "timeout"
        assert "timed out" in result["message"].lower()

