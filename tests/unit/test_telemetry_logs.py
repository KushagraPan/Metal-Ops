from __future__ import annotations

import json

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs._internal import LogRecord
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import format_span_id, format_trace_id

from app.telemetry import LOG_FIELD_ALLOWLIST, sanitize_log_record

SENTINEL = "SENTINEL-SUPPLIER-7f3a"
TRACE_ID = 0x7D9A2F0E31BC4A5D8E6F1234567890AB
SPAN_ID = 0x1234567890ABCDEF


def test_otlp_logs_keep_only_allowlisted_fields() -> None:
    record = LogRecord(
        timestamp=1_700_000_000_000_000_000,
        trace_id=TRACE_ID,
        span_id=SPAN_ID,
        severity_text="INFO",
        severity_number=9,
        body="Report upload stored",
        attributes={
            "supplier": SENTINEL,
            "customer": SENTINEL,
            "amount": SENTINEL,
            "filename": SENTINEL,
            "code.filepath": "private.py",
        },
        exception=ValueError(SENTINEL),
    )
    readable = ReadableLogRecord(
        log_record=record,
        resource=Resource.create(
            {"service.name": "metalops-lite", "supplier": SENTINEL}
        ),
    )

    clean = sanitize_log_record(readable)
    payload = json.loads(str(clean.log_record.body))
    serialized = json.dumps(
        {
            "body": clean.log_record.body,
            "attributes": dict(clean.log_record.attributes or {}),
            "resource": dict(clean.resource.attributes),
            "exception": str(clean.log_record.exception),
        }
    )

    assert set(payload) == LOG_FIELD_ALLOWLIST
    assert payload["message"] == "Report upload stored"
    assert payload["trace_id"] == format_trace_id(TRACE_ID)
    assert payload["span_id"] == format_span_id(SPAN_ID)
    assert clean.log_record.attributes == {}
    assert clean.log_record.exception is None
    assert clean.resource.attributes["service.name"] == "metalops-lite"
    assert "supplier" not in clean.resource.attributes
    assert SENTINEL not in serialized
