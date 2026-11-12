"""Unit tests for Issue #17: Alert on user impact.

Tests:
1. Alert rules file exists, is valid YAML, and specifies HeatReportHigh5xxRate:
   - Evaluates 5xx rate on heat/report endpoints
   - Threshold condition
   - for: 5m continuous duration
   - Mandatory labels: service=metalops-api, route_group=heats,reports, metric=http_5xx_rate, window=5m
2. Prometheus config wires alert_rules.yml and points alerting to Alertmanager
3. Alertmanager config routes to alert-adapter with send_resolved: true
4. Alert adapter payload formatter produces the schema required by _docs/oncall-agent.md
   for both firing and resolved states
5. Trace IDs extraction from Loki logs (up to 5 unique trace IDs)
6. Webhook dispatch:
   - Sends HTTP POST with application/json
   - Safely handles unset/empty ALERT_WEBHOOK_URL
7. Telemetry privacy & credential protection:
   - Deny-by-default on alert payload fields (no supplier/customer/rate/amount/filename)
   - Webhook URL credentials (passwords, tokens) are redacted in log messages
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from observability.alert_adapter.adapter import (
    AlertAdapter,
    mask_credentials,
    extract_trace_ids_from_loki,
    format_alert_payload,
    send_webhook_notification,
    ALLOWED_ALERT_PAYLOAD_FIELDS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Prometheus Alert Rules Validation
# ---------------------------------------------------------------------------

def test_alert_rules_file_exists_and_is_valid_yaml():
    rules_path = REPO_ROOT / "observability" / "prometheus" / "alert_rules.yml"
    assert rules_path.is_file(), f"Expected rules file at {rules_path}"

    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert "groups" in data
    assert len(data["groups"]) > 0

    group = next(
        (g for g in data["groups"] if g.get("name") in {"metalops-impact-alerts", "metalops-alerts"}),
        None,
    )
    assert group is not None, "Alert group for metalops impact alerts not found"

    rule = next(
        (r for r in group.get("rules", []) if r.get("alert") == "HeatReportHigh5xxRate"),
        None,
    )
    assert rule is not None, "Alert 'HeatReportHigh5xxRate' not found in alert rules"

    # Expression must check 5xx rate on heats and reports
    expr = rule["expr"]
    assert "http_server_request_count_total" in expr or "http_server_request_count" in expr
    assert "heats" in expr and "reports" in expr
    assert "5xx" in expr

    # Duration must be 5 minutes
    assert rule.get("for") == "5m"

    # Required labels per _docs/oncall-agent.md
    labels = rule.get("labels", {})
    assert labels.get("service") == "metalops-api"
    assert labels.get("route_group") == "heats,reports"
    assert labels.get("metric") == "http_5xx_rate"
    assert labels.get("window") == "5m"
    assert labels.get("severity") in {"critical", "page"}

    # Annotations
    annotations = rule.get("annotations", {})
    assert "summary" in annotations


def test_prometheus_yml_configures_alert_rules_and_alertmanager():
    prom_path = REPO_ROOT / "observability" / "prometheus" / "prometheus.yml"
    assert prom_path.is_file()

    with open(prom_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Must include alert_rules.yml
    rule_files = data.get("rule_files", [])
    assert any("alert_rules.yml" in str(rf) for rf in rule_files), (
        f"prometheus.yml rule_files must include alert_rules.yml, got {rule_files}"
    )

    # Must configure alertmanagers
    alerting = data.get("alerting", {})
    alertmanagers = alerting.get("alertmanagers", [])
    assert len(alertmanagers) > 0, "prometheus.yml must configure alertmanagers"

    found_am = False
    for am in alertmanagers:
        for sc in am.get("static_configs", []):
            targets = sc.get("targets", [])
            if any("alertmanager:9093" in t for t in targets):
                found_am = True
    assert found_am, "alertmanager:9093 target must be configured in prometheus.yml"


def test_alertmanager_yml_configures_webhook_adapter():
    am_path = REPO_ROOT / "observability" / "alertmanager" / "alertmanager.yml"
    assert am_path.is_file(), f"Expected alertmanager.yml at {am_path}"

    with open(am_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    receivers = data.get("receivers", [])
    assert len(receivers) > 0

    adapter_receiver = next(
        (r for r in receivers if r.get("name") in {"alert-adapter", "metalops-webhook"}),
        None,
    )
    assert adapter_receiver is not None, "Receiver for alert-adapter not found in alertmanager.yml"

    webhook_configs = adapter_receiver.get("webhook_configs", [])
    assert len(webhook_configs) > 0
    wh = webhook_configs[0]
    assert "alert-adapter" in wh.get("url", "") or "9097" in wh.get("url", "")
    assert wh.get("send_resolved") is True, "send_resolved must be true to receive resolved alerts"


def test_compose_observability_includes_alertmanager_and_adapter():
    compose_path = REPO_ROOT / "compose.observability.yaml"
    assert compose_path.is_file()

    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "alertmanager" in services
    assert "alert-adapter" in services

    am = services["alertmanager"]
    assert am.get("image") == "prom/alertmanager:v0.28.1"
    assert am.get("mem_limit") == "128m"
    assert "observability" in am.get("profiles", [])
    assert "metalops_network" in am.get("networks", [])

    adapter = services["alert-adapter"]
    assert adapter.get("image") == "python:3.11.18-slim-bookworm"
    assert adapter.get("mem_limit") == "128m"
    assert "observability" in adapter.get("profiles", [])
    assert "metalops_network" in adapter.get("networks", [])


# ---------------------------------------------------------------------------
# 2. Alert Adapter Payload Formatting & Privacy Tests
# ---------------------------------------------------------------------------

def test_format_alert_payload_firing():
    am_alert = {
        "status": "firing",
        "labels": {
            "alertname": "HeatReportHigh5xxRate",
            "service": "metalops-api",
            "route_group": "heats,reports",
            "metric": "http_5xx_rate",
            "window": "5m",
        },
        "startsAt": "2026-11-12T10:00:00Z",
    }
    trace_ids = ["0123456789abcdef0123456789abcdef", "abcdef0123456789abcdef0123456789"]

    payload = format_alert_payload(status="firing", alert=am_alert, trace_ids=trace_ids)

    assert payload["status"] == "firing"
    assert payload["service"] == "metalops-api"
    assert payload["window"] == "5m"
    assert payload["metric"] == "http_5xx_rate"
    assert payload["route_group"] == "heats,reports"
    assert payload["trace_ids"] == trace_ids
    assert payload["started_at"] == "2026-11-12T10:00:00Z"
    assert "resolved_at" not in payload

    # Deny-by-default allow-list check
    assert set(payload.keys()).issubset(ALLOWED_ALERT_PAYLOAD_FIELDS)


def test_format_alert_payload_resolved():
    am_alert = {
        "status": "resolved",
        "labels": {
            "alertname": "HeatReportHigh5xxRate",
            "service": "metalops-api",
            "route_group": "heats,reports",
            "metric": "http_5xx_rate",
            "window": "5m",
        },
        "startsAt": "2026-11-12T10:00:00Z",
        "endsAt": "2026-11-12T10:08:00Z",
    }

    payload = format_alert_payload(status="resolved", alert=am_alert, trace_ids=[])

    assert payload["status"] == "resolved"
    assert payload["service"] == "metalops-api"
    assert payload["window"] == "5m"
    assert payload["metric"] == "http_5xx_rate"
    assert payload["route_group"] == "heats,reports"
    assert payload["trace_ids"] == []
    assert payload["started_at"] == "2026-11-12T10:00:00Z"
    assert payload["resolved_at"] == "2026-11-12T10:08:00Z"

    assert set(payload.keys()).issubset(ALLOWED_ALERT_PAYLOAD_FIELDS)


def test_format_alert_payload_caps_trace_ids_at_five():
    am_alert = {
        "status": "firing",
        "labels": {"service": "metalops-api"},
        "startsAt": "2026-11-12T10:00:00Z",
    }
    many_traces = [f"trace_{i:04d}" for i in range(10)]
    payload = format_alert_payload(status="firing", alert=am_alert, trace_ids=many_traces)

    assert len(payload["trace_ids"]) == 5
    assert payload["trace_ids"] == many_traces[:5]


def test_payload_never_leaks_sensitive_business_data():
    am_alert = {
        "status": "firing",
        "labels": {
            "service": "metalops-api",
            "supplier": "SecretSupplier",
            "customer": "SecretCustomer",
            "rate": "50000",
            "amount": "100000",
            "filename": "private_report.pdf",
        },
        "annotations": {
            "file_bytes": "abc12345",
        },
        "startsAt": "2026-11-12T10:00:00Z",
    }
    payload = format_alert_payload(status="firing", alert=am_alert, trace_ids=["trace_safe"])
    serialized = json.dumps(payload)

    for forbidden in ("SecretSupplier", "SecretCustomer", "50000", "100000", "private_report.pdf", "abc12345"):
        assert forbidden not in serialized


# ---------------------------------------------------------------------------
# 3. Loki Trace IDs Extraction Tests
# ---------------------------------------------------------------------------

def test_extract_trace_ids_from_loki_response():
    sample_loki_response = {
        "status": "success",
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"service_name": "metalops-lite"},
                    "values": [
                        [
                            "1700000000000000000",
                            json.dumps({
                                "message": "Storage error on report upload",
                                "level": "ERROR",
                                "trace_id": "aa11bb22cc33dd44ee55ff6600112233",
                                "span_id": "1122334455667788",
                            }),
                        ],
                        [
                            "1700000010000000000",
                            json.dumps({
                                "message": "Failed saving report file",
                                "level": "ERROR",
                                "trace_id": "bb22cc33dd44ee55ff66001122334455",
                                "span_id": "2233445566778899",
                            }),
                        ],
                        # Duplicate trace_id should be deduped
                        [
                            "1700000020000000000",
                            json.dumps({
                                "message": "Retry failed",
                                "level": "ERROR",
                                "trace_id": "aa11bb22cc33dd44ee55ff6600112233",
                            }),
                        ],
                    ],
                }
            ],
        },
    }

    traces = extract_trace_ids_from_loki(sample_loki_response)
    assert len(traces) == 2
    assert "aa11bb22cc33dd44ee55ff6600112233" in traces
    assert "bb22cc33dd44ee55ff66001122334455" in traces


def test_extract_trace_ids_graceful_on_empty_or_malformed():
    assert extract_trace_ids_from_loki(None) == []
    assert extract_trace_ids_from_loki({}) == []
    assert extract_trace_ids_from_loki({"status": "error"}) == []


# ---------------------------------------------------------------------------
# 4. Webhook Dispatch & Privacy Tests
# ---------------------------------------------------------------------------

def test_mask_credentials_in_url():
    # URL with basic auth
    assert "secretpass" not in mask_credentials("http://user:secretpass@webhook.example.com/hook")
    assert mask_credentials("http://user:secretpass@webhook.example.com/hook") == "http://user:***@webhook.example.com/hook"

    # URL with secret query token
    url_with_token = "https://webhook.site/abc-123?token=SUPERSECRETTOKEN&key=xyz"
    masked = mask_credentials(url_with_token)
    assert "SUPERSECRETTOKEN" not in masked
    assert "xyz" not in masked

    # Safe URL remains unchanged
    assert mask_credentials("http://alert-receiver:9999/webhook") == "http://alert-receiver:9999/webhook"


def test_send_webhook_notification_success():
    payload = {
        "status": "firing",
        "service": "metalops-api",
        "window": "5m",
        "metric": "http_5xx_rate",
        "route_group": "heats,reports",
        "trace_ids": ["abc1234567890defabc1234567890def"],
        "started_at": "2026-11-12T10:00:00Z",
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        ok = send_webhook_notification(
            webhook_url="https://hooks.example.com/alert?token=secret123",
            payload=payload,
            timeout=2.0,
        )
        assert ok is True

        assert mock_urlopen.called
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "POST"
        assert req.get_header("Content-type") == "application/json"
        body_sent = json.loads(req.data.decode("utf-8"))
        assert body_sent == payload


def test_send_webhook_notification_skips_when_url_empty():
    payload = {"status": "firing"}
    # When webhook url is empty or None, it returns False without attempting network call
    with patch("urllib.request.urlopen") as mock_urlopen:
        assert send_webhook_notification("", payload) is False
        assert send_webhook_notification(None, payload) is False
        assert not mock_urlopen.called


def test_send_webhook_notification_does_not_leak_credentials_on_error(caplog):
    payload = {"status": "firing"}
    secret_url = "https://user:TOPSECRET@error.example.com/hook?token=MYSECRETTOKEN"

    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with caplog.at_level(logging.ERROR):
            ok = send_webhook_notification(secret_url, payload, timeout=1.0)
            assert ok is False

            for record in caplog.records:
                assert "TOPSECRET" not in record.message
                assert "MYSECRETTOKEN" not in record.message
