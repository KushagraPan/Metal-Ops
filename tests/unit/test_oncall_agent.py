"""Unit tests for the Issue #18 On-Call Agent and Webhook.

Verifies:
1. Webhook alert payload validation and allow-list sanitization.
2. Alert deduplication and atomic SQLite claim across OS processes.
3. Webhook fail-closed handling on SQLite storage failure.
4. Isolated Git worktree lifecycle, collision handling, and evidence preservation.
5. Integration of WorktreeManager into the actual agent execution path.
6. Guardrails:
   - Token isolation (ONCALL_GITHUB_TOKEN and GH_CONFIG_DIR) in actual subprocesses.
   - PRODUCTION_* and PROD_* prefix detection.
   - Command allowlisting and rejection of shell indirection and deployment operations.
   - Elimination of sensitive business/PII data in PR body and logs.
7. Evidence directory and .gitignore sidecar exclusions.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from observability.oncall_agent.agent import (
    AlertDeduplicator,
    GuardrailEnforcer,
    GuardrailViolation,
    LokiCorrelator,
    OnCallAgent,
    ValidationError,
    validate_alert_payload,
)
from observability.oncall_agent.models import AlertPayload
from observability.oncall_agent.worktree import WorktreeError, WorktreeInfo, WorktreeManager


def _multiprocess_claim_worker(db_path: str, alert_kwargs: dict, queue: Any) -> None:
    """Module-level worker function for multiprocessing test in spawn context."""
    from observability.oncall_agent.agent import AlertDeduplicator
    from observability.oncall_agent.models import AlertPayload

    alert = AlertPayload(**alert_kwargs)
    dedup = AlertDeduplicator(ttl_seconds=300.0, db_path=db_path)
    try:
        claimed = dedup.claim_alert(alert)
        queue.put(claimed)
    except Exception as exc:
        queue.put(f"ERROR: {exc}")


def test_validate_alert_payload_success():
    raw_payload = {
        "status": "firing",
        "service": "metalops-api",
        "window": "5m",
        "metric": "http_5xx_rate",
        "route_group": "heats,reports",
        "trace_ids": ["0123456789abcdef0123456789abcdef"],
        "started_at": "2026-11-12T12:00:00Z",
        # Extra sensitive fields that must be stripped:
        "supplier_name": "Classified Supplier",
        "rate": 210.50,
    }

    validated = validate_alert_payload(raw_payload)
    assert isinstance(validated, AlertPayload)
    assert validated.status == "firing"
    assert validated.service == "metalops-api"
    assert validated.route_group == "heats,reports"
    assert validated.trace_ids == ["0123456789abcdef0123456789abcdef"]
    assert validated.started_at == "2026-11-12T12:00:00Z"
    # Verify extra fields are not present
    assert not hasattr(validated, "supplier_name")
    assert not hasattr(validated, "rate")


def test_validate_alert_payload_missing_required_fields():
    incomplete = {
        "status": "firing",
        # missing service, window, metric, route_group, started_at
    }
    with pytest.raises(ValidationError):
        validate_alert_payload(incomplete)


def test_alert_deduplication():
    dedup = AlertDeduplicator(ttl_seconds=300)
    alert = AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=["trace-1"],
        started_at="2026-11-12T12:00:00Z",
    )

    # First time: not duplicate and successfully claimed
    assert dedup.is_duplicate(alert) is False
    assert dedup.claim_alert(alert) is True

    # Second time within window: duplicate and claim rejected
    assert dedup.claim_alert(alert) is False
    assert dedup.is_duplicate(alert) is True

    # Resolved status should not be blocked by firing
    resolved_alert = AlertPayload(
        status="resolved",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=[],
        started_at="2026-11-12T12:00:00Z",
    )
    assert dedup.is_duplicate(resolved_alert) is False
    assert dedup.claim_alert(resolved_alert) is True


def test_loki_correlator_extracts_trace_logs():
    correlator = LokiCorrelator(loki_url="http://mock-loki:3100")
    mock_loki_response = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"service_name": "metalops-api", "level": "ERROR"},
                    "values": [
                        [
                            "1731412800000000000",
                            json.dumps(
                                {
                                    "trace_id": "0123456789abcdef0123456789abcdef",
                                    "span_id": "0123456789abcdef",
                                    "message": "PermissionError: [Errno 13] Permission denied: '/app/storage/reports'",
                                    "route": "/api/reports/upload",
                                    "status_code": 500,
                                }
                            ),
                        ]
                    ],
                }
            ]
        },
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(mock_loki_response).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        findings = correlator.correlate_traces(["0123456789abcdef0123456789abcdef"])
        assert len(findings) == 1
        assert findings[0]["trace_id"] == "0123456789abcdef0123456789abcdef"
        assert "PermissionError" in findings[0]["error_summary"]
        assert findings[0]["route"] == "/api/reports/upload"


def test_guardrail_enforcer_blocks_production_credentials(monkeypatch):
    enforcer = GuardrailEnforcer()

    # Clean environment: passes
    enforcer.check_environment()

    # Injected production secret: must raise GuardrailViolation
    monkeypatch.setenv("DEPLOY_SSH_KEY", "-----BEGIN OPENSSH PRIVATE KEY-----...")
    with pytest.raises(GuardrailViolation, match="Production credentials detected"):
        enforcer.check_environment()

    monkeypatch.delenv("DEPLOY_SSH_KEY")
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://prod:secret@prod-db/metalops")
    with pytest.raises(GuardrailViolation, match="Production credentials detected"):
        enforcer.check_environment()


def test_guardrail_enforcer_blocks_merge_and_deploy_commands():
    enforcer = GuardrailEnforcer()

    allowed_cmd = ["git", "checkout", "-b", "fix/storage-permissions"]
    enforcer.validate_command(allowed_cmd)

    forbidden_merge_cmds = [
        ["git", "merge", "main"],
        ["gh", "pr", "merge", "123", "--auto"],
        ["gh", "pr", "merge", "--squash"],
        ["docker", "compose", "-f", "compose.prod.yaml", "up", "-d"],
    ]

    for cmd in forbidden_merge_cmds:
        with pytest.raises(GuardrailViolation, match="Forbidden command"):
            enforcer.validate_command(cmd)


def test_guardrail_sanitizes_pr_content():
    enforcer = GuardrailEnforcer()

    # Body containing forbidden business data (supplier, rate, amount)
    dirty_body = (
        "Root cause: Purchase from Acme Scrap Ltd at Rs 210/kg failed during report processing. "
        "Total amount Rs 50,000 was impacted."
    )
    clean_body = enforcer.sanitize_text(dirty_body)
    assert "Acme Scrap" not in clean_body
    assert "Rs 210" not in clean_body
    assert "Rs 50,000" not in clean_body
    assert "[REDACTED]" in clean_body


def test_oncall_agent_investigation_and_pr_generation(tmp_path):
    alert = AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=["0123456789abcdef0123456789abcdef"],
        started_at="2026-11-12T12:00:00Z",
    )

    mock_correlator = MagicMock(spec=LokiCorrelator)
    mock_correlator.correlate_traces.return_value = [
        {
            "trace_id": "0123456789abcdef0123456789abcdef",
            "route": "/api/reports/upload",
            "status_code": 500,
            "error_summary": "PermissionError: [Errno 13] Permission denied: '/app/storage/reports'",
        }
    ]

    mock_wt = MagicMock(spec=WorktreeManager)
    mock_wt.create_worktree.return_value = WorktreeInfo(
        Path("/mock/worktrees/wt-fix-alert-reports"), "fix/alert-reports-123"
    )

    agent = OnCallAgent(
        correlator=mock_correlator,
        enforcer=GuardrailEnforcer(),
        worktree_manager=mock_wt,
        dry_run=True,  # Dry run doesn't touch real git/gh remotes
        evidence_dir=tmp_path / "oncall_evidence",
    )

    result = agent.handle_alert(alert)

    assert result["status"] == "investigated"
    assert result["branch"] == "fix/alert-reports-123"
    assert result["reproduction_test"] is not None
    assert "PermissionError" in result["root_cause"]
    assert result["pr_created"] is True
    assert result["pr_number"] is not None
    assert result["merged"] is False  # Guardrail: never merged!


def test_webhook_listener_receives_and_processes_alert(tmp_path):
    from io import BytesIO
    from observability.oncall_agent.webhook import OnCallWebhookHandler

    valid_body = json.dumps(
        {
            "status": "firing",
            "service": "metalops-api",
            "window": "5m",
            "metric": "http_5xx_rate",
            "route_group": "heats,reports",
            "trace_ids": ["0123456789abcdef0123456789abcdef"],
            "started_at": "2026-11-12T12:00:00Z",
        }
    ).encode("utf-8")

    # Mock handler request
    handler = OnCallWebhookHandler.__new__(OnCallWebhookHandler)
    handler.headers = {"Content-Length": str(len(valid_body))}
    handler.rfile = BytesIO(valid_body)
    handler.wfile = BytesIO()

    mock_wt = MagicMock(spec=WorktreeManager)
    mock_wt.create_worktree.return_value = WorktreeInfo(
        Path("/mock/worktrees/wt-fix-alert-reports"), "fix/alert-reports-123"
    )
    handler.agent = OnCallAgent(dry_run=True, worktree_manager=mock_wt, evidence_dir=tmp_path / "oncall_evidence")
    handler.deduplicator = AlertDeduplicator(ttl_seconds=300.0)

    # Mock send_response, send_header, end_headers
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_POST()

    assert handler.send_response.call_args[0][0] == 200
    response_json = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert response_json["status"] == "accepted"
    assert response_json["result"]["pr_created"] is True


def test_alert_deduplication_persistent_sqlite_and_restart(tmp_path):
    """Verify SQLite alert deduplication persists across restarts and expires with TTL."""
    db_file = tmp_path / "test_dedup.db"
    alert = AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=["trace-persist-1"],
        started_at="2026-11-13T10:00:00Z",
    )

    # First instance records alert
    dedup1 = AlertDeduplicator(ttl_seconds=0.3, db_path=db_file)
    assert dedup1.is_duplicate(alert) is False
    assert dedup1.claim_alert(alert) is True
    assert dedup1.is_duplicate(alert) is True

    # Second instance (simulating daemon restart with same SQLite DB file)
    dedup2 = AlertDeduplicator(ttl_seconds=0.3, db_path=db_file)
    assert dedup2.is_duplicate(alert) is True
    assert dedup2.claim_alert(alert) is False

    # Wait for TTL expiration
    time.sleep(0.35)

    # After TTL, alert can be claimed again
    assert dedup2.is_duplicate(alert) is False
    assert dedup2.claim_alert(alert) is True


def test_alert_deduplication_concurrent_safety(tmp_path):
    """Verify concurrent reads and writes to SQLite deduplicator are safe and do not lock."""
    import concurrent.futures
    db_file = tmp_path / "concurrent_dedup.db"
    dedup = AlertDeduplicator(ttl_seconds=300.0, db_path=db_file)

    def worker(i: int):
        alert = AlertPayload(
            status="firing",
            service="metalops-api",
            window="5m",
            metric="http_5xx_rate",
            route_group=f"group-{i % 3}",
            trace_ids=[f"trace-{i}"],
            started_at="2026-11-13T10:00:00Z",
        )
        return dedup.claim_alert(alert)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(24)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 24
    # Because there are 3 distinct route groups, exactly 3 should succeed in claiming
    assert results.count(True) == 3
    assert results.count(False) == 21


def test_guardrail_missing_github_token_fails_closed(monkeypatch):
    """Verify On-Call agent fails closed when ONCALL_GITHUB_TOKEN is missing."""
    enforcer = GuardrailEnforcer()
    monkeypatch.delenv("ONCALL_GITHUB_TOKEN", raising=False)

    with pytest.raises(GuardrailViolation, match="ONCALL_GITHUB_TOKEN secret is required but not provided"):
        enforcer.get_github_token()

    # Empty/whitespace token also fails closed
    monkeypatch.setenv("ONCALL_GITHUB_TOKEN", "   ")
    with pytest.raises(GuardrailViolation, match="ONCALL_GITHUB_TOKEN secret is required but not provided"):
        enforcer.get_github_token()


def test_guardrail_isolated_gh_env(monkeypatch, tmp_path):
    """Verify build_isolated_gh_env isolates gh config dir and blocks host keyring fallback."""
    enforcer = GuardrailEnforcer()
    monkeypatch.setenv("GH_TOKEN", "ambient_user_token")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient_github_token")

    isolated_env = enforcer.build_isolated_gh_env("test_oncall_secret_token", tmp_path)

    assert isolated_env["GH_TOKEN"] == "test_oncall_secret_token"
    assert isolated_env["GITHUB_TOKEN"] == "test_oncall_secret_token"
    assert isolated_env["GH_CONFIG_DIR"] == str(tmp_path.resolve())
    assert isolated_env["GH_PROMPT_DISABLED"] == "1"
    assert isolated_env["NO_COLOR"] == "1"


def test_worktree_manager_lifecycle_and_evidence_preservation(tmp_path):
    """Verify git worktree creation, isolation, and evidence preservation."""
    import subprocess
    repo_root = Path(__file__).resolve().parents[2]
    mgr = WorktreeManager(repo_root=repo_root, worktree_base=tmp_path)

    branch_name = f"test-wt-branch-{int(time.time() * 1000)}"
    wt_dir = mgr.create_worktree(branch_name)

    try:
        assert wt_dir.exists()
        assert (wt_dir / ".git").is_file()  # Worktree has a .git pointer file
        assert (wt_dir / "app").is_dir()

        # Test evidence preservation: remove_worktree with preserve=True leaves directory intact
        preserved = mgr.remove_worktree(wt_dir, preserve=True)
        assert preserved is False
        assert wt_dir.exists(), "Worktree directory must be preserved when preserve=True"

        # Explicit removal
        removed = mgr.remove_worktree(wt_dir, force=True, preserve=False)
        assert removed is True
        assert not wt_dir.exists()
    finally:
        # Cleanup test branch
        subprocess.run(["git", "branch", "-D", branch_name], cwd=repo_root, capture_output=True, check=False)


# ==============================================================================
# Seven Acceptance Specification Regression Tests (Issue #18 Milestone 1 Repair)
# ==============================================================================


def test_area1_atomic_claim_multiprocessing_simultaneous(tmp_path):
    """Area 1: Verify exactly one winner in an 8-process simultaneous test."""
    import multiprocessing

    db_file = str(tmp_path / "multiprocess_dedup.db")
    alert_kwargs = {
        "status": "firing",
        "service": "metalops-api",
        "window": "5m",
        "metric": "http_5xx_rate",
        "route_group": "heats,reports",
        "trace_ids": ["0123456789abcdef0123456789abcdef"],
        "started_at": "2026-11-13T12:00:00Z",
    }

    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = [
        ctx.Process(target=_multiprocess_claim_worker, args=(db_file, alert_kwargs, queue))
        for _ in range(8)
    ]

    for p in processes:
        p.start()

    for p in processes:
        p.join(timeout=15.0)

    results = []
    while not queue.empty():
        results.append(queue.get())

    assert len(results) == 8, f"Expected 8 results from 8 processes, got {len(results)}: {results}"
    assert all(isinstance(r, bool) for r in results), f"Worker failed with exception: {results}"
    assert results.count(True) == 1, f"Expected exactly 1 winner, got {results.count(True)} True out of {results}"
    assert results.count(False) == 7, f"Expected 7 losers, got {results.count(False)} False out of {results}"


def test_area2_webhook_handles_sqlite_failure_fail_closed():
    """Area 2: Verify SQLite storage failure at webhook boundary triggers explicit HTTP 503 fail-closed."""
    from io import BytesIO
    import sqlite3
    from observability.oncall_agent.webhook import OnCallWebhookHandler

    valid_body = json.dumps(
        {
            "status": "firing",
            "service": "metalops-api",
            "window": "5m",
            "metric": "http_5xx_rate",
            "route_group": "heats,reports",
            "trace_ids": ["0123456789abcdef0123456789abcdef"],
            "started_at": "2026-11-13T12:00:00Z",
        }
    ).encode("utf-8")

    handler = OnCallWebhookHandler.__new__(OnCallWebhookHandler)
    handler.headers = {"Content-Length": str(len(valid_body))}
    handler.rfile = BytesIO(valid_body)
    handler.wfile = BytesIO()

    mock_dedup = MagicMock(spec=AlertDeduplicator)
    mock_dedup.claim_alert.side_effect = sqlite3.OperationalError("database disk image is malformed")
    handler.deduplicator = mock_dedup

    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_POST()

    assert handler.send_response.call_args[0][0] == 503
    response_json = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert response_json["status"] == "fail_closed"
    assert "Deduplication storage failure" in response_json["error"]


def test_area3_worktree_collision_handling_and_preservation(tmp_path):
    """Area 3: Unique branch names, collision handling without deleting preserved evidence, and pruning."""
    import subprocess
    repo_root = Path(__file__).resolve().parents[2]
    mgr = WorktreeManager(repo_root=repo_root, worktree_base=tmp_path)

    base_branch = f"test-col-branch-{int(time.time() * 1000)}"

    wt1 = mgr.create_worktree(base_branch)
    try:
        assert wt1.exists()
        assert wt1.branch == base_branch
        marker = wt1.path / "preserved_marker.txt"
        marker.write_text("critical incident evidence", encoding="utf-8")

        # Second creation with identical base branch name
        wt2 = mgr.create_worktree(base_branch)
        try:
            assert wt2.exists()
            # Must disambiguate branch and target dir
            assert wt2.branch != wt1.branch
            assert wt2.path != wt1.path
            assert wt2.branch == f"{base_branch}-1"

            # Preserved evidence in wt1 must NOT be deleted or overwritten
            assert wt1.exists()
            assert marker.exists()
            assert marker.read_text(encoding="utf-8") == "critical incident evidence"

            # Pruning metadata must succeed
            mgr.prune_worktrees()
        finally:
            mgr.remove_worktree(wt2, force=True, preserve=False)
            subprocess.run(["git", "branch", "-D", wt2.branch], cwd=repo_root, capture_output=True, check=False)
    finally:
        mgr.remove_worktree(wt1, force=True, preserve=False)
        subprocess.run(["git", "branch", "-D", base_branch], cwd=repo_root, capture_output=True, check=False)


def test_area4_oncall_agent_wires_worktree_manager_in_execution_path(tmp_path):
    """Area 4: Wire WorktreeManager into actual agent execution path and preserve worktree on disk."""
    import subprocess
    repo_root = Path(__file__).resolve().parents[2]
    worktree_base = tmp_path / "agent_worktrees"
    evidence_dir = tmp_path / "oncall_evidence"

    mgr = WorktreeManager(repo_root=repo_root, worktree_base=worktree_base)
    agent = OnCallAgent(
        worktree_manager=mgr,
        dry_run=True,
        repo_root=str(repo_root),
        evidence_dir=evidence_dir,
    )

    alert = AlertPayload(
        status="firing",
        service="metalops-api",
        window="5m",
        metric="http_5xx_rate",
        route_group="heats,reports",
        trace_ids=["0123456789abcdef0123456789abcdef"],
        started_at="2026-11-13T12:00:00Z",
    )

    result = agent.handle_alert(alert)

    created_branch = result["branch"]
    worktree_path = Path(result["worktree_path"])
    try:
        assert result["status"] == "investigated"
        assert worktree_path.exists(), "Worktree directory must exist on disk"
        assert (worktree_path / ".git").is_file(), "Worktree must have isolated .git pointer"
        assert result["evidence_dir"] == str(evidence_dir)
        assert Path(result["evidence_file"]).exists(), "Incident evidence file must be persisted"
    finally:
        mgr.remove_worktree(worktree_path, force=True, preserve=False)
        subprocess.run(["git", "branch", "-D", created_branch], cwd=repo_root, capture_output=True, check=False)


def test_area5_subprocess_boundary_enforces_tokens_and_blocks_keyring(monkeypatch, tmp_path):
    """Area 5: Enforce ONCALL_GITHUB_TOKEN and isolated GH_CONFIG_DIR in actual subprocesses."""
    enforcer = GuardrailEnforcer()

    # Ambient credentials in parent process
    monkeypatch.setenv("GH_TOKEN", "ambient_user_token")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient_github_token")
    monkeypatch.setenv("GH_ENTERPRISE_TOKEN", "ambient_enterprise_token")
    monkeypatch.setenv("ONCALL_GITHUB_TOKEN", "secret_oncall_token_xyz")

    config_dir = tmp_path / "isolated_gh_cfg"
    isolated_env = enforcer.build_isolated_gh_env("secret_oncall_token_xyz", config_dir)

    # Run actual Python subprocess to inspect the environment
    code = (
        "import os, sys\n"
        "sys.stdout.write(f'{os.environ.get(\"GH_CONFIG_DIR\", \"\")}:::'\n"
        "f'{os.environ.get(\"GH_TOKEN\", \"\")}:::'\n"
        "f'{os.environ.get(\"GH_ENTERPRISE_TOKEN\", \"\")}')\n"
    )
    cmd = [sys.executable, "-c", code]
    res = enforcer.run_subprocess(cmd, env=isolated_env)
    assert res.returncode == 0
    cfg_dir_out, token_out, enterprise_out = res.stdout.strip().split(":::")

    assert cfg_dir_out == str(config_dir.resolve())
    assert token_out == "secret_oncall_token_xyz"
    assert enterprise_out == ""  # Ambient variable stripped

    # Missing ONCALL_GITHUB_TOKEN fails closed
    monkeypatch.delenv("ONCALL_GITHUB_TOKEN")
    with pytest.raises(GuardrailViolation, match="ONCALL_GITHUB_TOKEN secret is required but not provided"):
        enforcer.get_github_token()


def test_area6_guardrail_blocks_production_prefixes_and_shell_indirection(monkeypatch):
    """Area 6: PRODUCTION_* prefix detection and command allowlisting at the actual execution boundary."""
    enforcer = GuardrailEnforcer()

    # 1. Prefix checks: PRODUCTION_* and PROD_*
    monkeypatch.setenv("PRODUCTION_DATABASE_PASSWORD", "supersecret")
    with pytest.raises(GuardrailViolation, match="Production credentials detected"):
        enforcer.check_environment()
    monkeypatch.delenv("PRODUCTION_DATABASE_PASSWORD")

    monkeypatch.setenv("PROD_REDIS_URL", "redis://prod:6379")
    with pytest.raises(GuardrailViolation, match="Production credentials detected"):
        enforcer.check_environment()
    monkeypatch.delenv("PROD_REDIS_URL")

    # 2. Executable allowlisting: unallowed executables blocked
    with pytest.raises(GuardrailViolation, match="Forbidden executable 'curl'"):
        enforcer.validate_command(["curl", "https://example.com"])

    with pytest.raises(GuardrailViolation, match="Shell execution is strictly prohibited"):
        enforcer.validate_command(["powershell", "-Command", "Get-Process"])

    with pytest.raises(GuardrailViolation, match="Shell execution is strictly prohibited"):
        enforcer.validate_command(["bash", "-c", "echo hello"])

    # 3. Shell metacharacters / indirection
    with pytest.raises(GuardrailViolation, match="Shell indirection character ';"):
        enforcer.validate_command(["git", "checkout", "fix-1; rm -rf /"])

    with pytest.raises(GuardrailViolation, match="Shell indirection character '&&'"):
        enforcer.validate_command(["git", "commit", "-m", "fix && make deploy"])

    # 4. Forbidden subcommands: merge and deploy
    with pytest.raises(GuardrailViolation, match="On-call agent cannot merge"):
        enforcer.validate_command(["gh", "pr", "merge", "18"])

    with pytest.raises(GuardrailViolation, match="On-call agent cannot deploy"):
        enforcer.validate_command(["docker", "compose", "-f", "compose.prod.yaml", "up"])

    # 5. Rejection of shell=True in run_subprocess
    with pytest.raises(GuardrailViolation, match="Shell execution .* is strictly prohibited"):
        enforcer.run_subprocess(["git", "status"], shell=True)


def test_area7_evidence_directory_and_gitignore_exclusions():
    """Area 7: Exclude .metalops and sidecars in .gitignore, and define standard evidence directory."""
    repo_root = Path(__file__).resolve().parents[2]
    gitignore_path = repo_root / ".gitignore"
    assert gitignore_path.exists()
    gitignore_content = gitignore_path.read_text(encoding="utf-8")

    assert ".metalops/" in gitignore_content
    assert "metalops-oncall-worktrees/" in gitignore_content
    assert "*.db-shm" in gitignore_content
    assert "*.db-wal" in gitignore_content
    assert "*.db-journal" in gitignore_content

    assert OnCallAgent.EVIDENCE_DIR == Path("_docs/evidence/oncall")


