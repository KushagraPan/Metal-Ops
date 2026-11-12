"""Unit tests for the Issue #18 On-Call Agent and Webhook.

Verifies:
1. Webhook alert payload validation and allow-list sanitization.
2. Alert deduplication and debouncing per alert window.
3. Loki log and trace correlation by trace ID.
4. Guardrails:
   - Absence of production credentials.
   - Prohibition of merge/deploy commands.
   - Elimination of sensitive business/PII data in PR body and logs.
5. End-to-end investigation, reproduction, test verification, and PR creation.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
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

    # First time: not duplicate
    assert dedup.is_duplicate(alert) is False
    dedup.record(alert)

    # Second time within window: duplicate
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


def test_oncall_agent_investigation_and_pr_generation():
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

    agent = OnCallAgent(
        correlator=mock_correlator,
        enforcer=GuardrailEnforcer(),
        dry_run=True,  # Dry run doesn't touch real git/gh remotes
    )

    result = agent.handle_alert(alert)

    assert result["status"] == "investigated"
    assert result["branch"].startswith("fix/alert-")
    assert result["reproduction_test"] is not None
    assert "PermissionError" in result["root_cause"]
    assert result["pr_created"] is True
    assert result["pr_number"] is not None
    assert result["merged"] is False  # Guardrail: never merged!


def test_webhook_listener_receives_and_processes_alert():
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
    handler.agent = OnCallAgent(dry_run=True)
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

