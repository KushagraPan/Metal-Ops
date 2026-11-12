from __future__ import annotations

import io
import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import format_span_id, format_trace_id
from opentelemetry.util._once import Once
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session, make_engine
from app.main import create_app
from app.models import Base, Setting
from app.models.user import User
from app.routers.auth import require_session
from app.storage import LocalStorage, get_storage
from app.telemetry import (
    JsonLogFormatter,
    SanitizingMetricExporter,
    SanitizingSpanExporter,
    configure_json_logging,
    configure_telemetry,
    normalize_route,
    sanitize_metric_attributes,
    sanitize_span_attributes,
    shutdown_telemetry,
)

EXPECTED_SPAN_ATTRIBUTE_ALLOWLIST = frozenset(
    {
        "http.method",
        "http.route",
        "http.status_code",
        "http.status_class",
        "db.system",
        "db.operation",
        "app.heat.id",
        "app.report.id",
        "app.report.size_bytes",
    }
)

EXPECTED_METRIC_LABEL_ALLOWLIST = frozenset(
    {
        "http.route",
        "http.method",
        "http.status_class",
        "reason",
    }
)

EXPECTED_METRIC_NAME_ALLOWLIST = frozenset(
    {
        "http.server.request.count",
        "http.server.request.duration",
        "report.upload.count",
        "report.upload.failures",
        "report.upload.bytes",
    }
)

EXPECTED_LOG_FIELD_ALLOWLIST = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
        "trace_id",
        "span_id",
    }
)

SENTINEL_SUPPLIER = "SENTINEL-SUPPLIER-7f3a"
SENTINEL_CUSTOMER = "SENTINEL-CUSTOMER-9b2c"
SENTINEL_RATE = "987654.32"
SENTINEL_AMOUNT = "1350863.64"
SENTINEL_FILENAME = "SENTINEL-REPORT-4d8e.pdf"
SENTINEL_FILE_TEXT = "FILE-BYTES-SENTINEL-c1a9"
SENTINEL_PDF = f"%PDF-1.4\n{SENTINEL_FILE_TEXT}\n%%EOF\n".encode()

SENTINELS = (
    SENTINEL_SUPPLIER,
    SENTINEL_CUSTOMER,
    SENTINEL_RATE,
    SENTINEL_AMOUNT,
    SENTINEL_FILENAME,
    SENTINEL_FILE_TEXT,
)


def _reset_otel_globals() -> None:
    """Test-only reset so each scenario gets fresh providers."""
    trace._TRACER_PROVIDER_SET_ONCE = Once()  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    metrics_internal._METER_PROVIDER_SET_ONCE = Once()
    metrics_internal._METER_PROVIDER = None


@contextmanager
def telemetry_client(
    tmp_path: Path, *, endpoint: str | None = None
) -> Iterator[tuple[TestClient, InMemorySpanExporter, InMemoryMetricReader]]:
    shutdown_telemetry()
    _reset_otel_globals()

    engine = make_engine(f"sqlite:///{(tmp_path / 'telemetry.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        session.add(
            Setting(
                id=1,
                gst_rate=Decimal("0.18"),
                planned_yield_pct=Decimal("89.00"),
            )
        )
        session.commit()

    storage = LocalStorage(tmp_path / "storage")
    application = create_app()

    def override_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def override_storage() -> LocalStorage:
        return storage

    dummy_user = User(
        id=1,
        email="unit-test@workshop.local",
        password_hash="dummy_hash",
    )
    application.dependency_overrides[get_session] = override_session
    application.dependency_overrides[get_storage] = override_storage
    application.dependency_overrides[require_session] = lambda: dummy_user

    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    configured = configure_telemetry(
        application,
        engine,
        span_exporter=None if endpoint is not None else span_exporter,
        metric_reader=metric_reader,
        endpoint=endpoint,
        json_logs=False,
    )
    assert configured is True

    try:
        with TestClient(application) as client:
            yield client, span_exporter, metric_reader
    finally:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        FastAPIInstrumentor.uninstrument_app(application)
        SQLAlchemyInstrumentor().uninstrument()
        shutdown_telemetry()
        _reset_otel_globals()
        engine.dispose()


def _metric_points(reader: InMemoryMetricReader) -> list[Any]:
    data = reader.get_metrics_data()
    assert data is not None
    points: list[Any] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                for point in metric.data.data_points:
                    points.append((metric.name, point))
    return points


def _span_text(span: Any) -> str:
    return json.dumps(
        {
            "name": span.name,
            "attributes": dict(span.attributes or {}),
            "events": [
                {"name": event.name, "attributes": dict(event.attributes or {})}
                for event in span.events
            ],
            "status_description": span.status.description,
            "resource": dict(span.resource.attributes),
        },
        default=str,
    )


def test_telemetry_is_off_when_no_endpoint_or_exporter(
    monkeypatch: Any,
) -> None:
    shutdown_telemetry()
    _reset_otel_globals()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert configure_telemetry() is False


def test_span_allowlist_drops_private_keys() -> None:
    attributes = {
        "http.method": "post",
        "http.route": "/api/heats/42/reports?token=secret",
        "http.status_code": 201,
        "db.system": "sqlite",
        "db.operation": "INSERT",
        "db.statement": f"INSERT INTO purchases VALUES ('{SENTINEL_SUPPLIER}')",
        "db.query.text": f"UPDATE purchases SET rate = {SENTINEL_RATE}",
        "http.target": f"/api/reports?name={SENTINEL_FILENAME}",
        "http.url": f"http://example.test/{SENTINEL_FILENAME}",
        "http.request.header.cookie": "session=secret",
        "http.request.header.authorization": "Bearer secret",
        "http.request.body": SENTINEL_AMOUNT,
        "http.response.body": SENTINEL_FILE_TEXT,
        "exception.message": f"failed for {SENTINEL_CUSTOMER}",
        "supplier": SENTINEL_SUPPLIER,
        "customer": SENTINEL_CUSTOMER,
        "rate": SENTINEL_RATE,
        "amount": SENTINEL_AMOUNT,
        "filename": SENTINEL_FILENAME,
    }

    result = sanitize_span_attributes(attributes)

    assert set(result) == EXPECTED_SPAN_ATTRIBUTE_ALLOWLIST - {
        "http.status_class",
        "app.heat.id",
        "app.report.id",
        "app.report.size_bytes",
    }
    import app.telemetry as app_telemetry
    assert app_telemetry.SPAN_ATTRIBUTE_ALLOWLIST == EXPECTED_SPAN_ATTRIBUTE_ALLOWLIST
    assert result["http.method"] == "POST"
    assert result["http.route"] == "/api/heats/{id}/reports"
    assert result["http.status_code"] == 201
    assert result["db.system"] == "sqlite"
    assert result["db.operation"] == "INSERT"
    for private_key in (
        "db.statement",
        "db.query.text",
        "http.target",
        "http.url",
        "http.request.header.cookie",
        "http.request.header.authorization",
        "http.request.body",
        "http.response.body",
        "exception.message",
    ):
        assert private_key not in result
    text = json.dumps(result)
    assert not any(sentinel in text for sentinel in SENTINELS)


def test_metric_allowlist_is_exact_and_fixed() -> None:
    attributes = {
        "http.route": "/api/heats/42/reports?token=secret",
        "http.method": "post",
        "http.status_class": "2xx",
        "reason": "validation",
        "http.target": f"/api/reports?name={SENTINEL_FILENAME}",
        "supplier": SENTINEL_SUPPLIER,
    }

    result = sanitize_metric_attributes(attributes)

    assert set(result) == EXPECTED_METRIC_LABEL_ALLOWLIST
    import app.telemetry as app_telemetry
    assert app_telemetry.METRIC_LABEL_ALLOWLIST == EXPECTED_METRIC_LABEL_ALLOWLIST
    assert result == {
        "http.route": "/api/heats/{id}/reports",
        "http.method": "POST",
        "http.status_class": "2xx",
        "reason": "validation",
    }
    assert sanitize_metric_attributes({"reason": SENTINEL_SUPPLIER}) == {}


class _CapturingMetricExporter(MetricExporter):
    def __init__(self) -> None:
        super().__init__()
        self.batches: list[Any] = []

    def export(
        self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any
    ) -> Any:
        self.batches.append(metrics_data)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        pass


def test_metric_exporter_strips_private_labels() -> None:
    capture = _CapturingMetricExporter()
    reader = PeriodicExportingMetricReader(
        SanitizingMetricExporter(capture),
        export_interval_millis=60_000,
    )
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")
    meter.create_counter("http.server.request.count").add(
        1,
        attributes={
            "http.route": "/api/heats/42",
            "reason": "validation",
            "supplier": SENTINEL_SUPPLIER,
            "filename": SENTINEL_FILENAME,
        },
    )
    meter.create_histogram("http.server.duration").record(
        0.1, attributes={"http.target": "/api/heats/42?token=secret"}
    )

    try:
        reader.force_flush()
        assert capture.batches
        exported = [
            metric
            for resource_metrics in capture.batches[-1].resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        ]
        assert {metric.name for metric in exported} <= EXPECTED_METRIC_NAME_ALLOWLIST
        assert [metric.name for metric in exported] == [
            "http.server.request.count"
        ]
        points = [
            point
            for metric in exported
            for point in metric.data.data_points
        ]
        assert points
        assert points[0].attributes == {
            "http.route": "/api/heats/{id}",
            "reason": "validation",
        }
        assert not any(
            sentinel in json.dumps(dict(points[0].attributes))
            for sentinel in SENTINELS
        )
    finally:
        provider.shutdown()


def test_raw_paths_and_ids_are_normalised() -> None:
    assert normalize_route("/api/heats/42/reports?x=1") == (
        "/api/heats/{id}/reports"
    )
    assert normalize_route(
        "/api/reports/7d9a2f0e-31bc-4a5d-8e6f-1234567890ab"
    ) == "/api/reports/{id}"
    assert normalize_route("/api/heats/{heat_id}/reports") == (
        "/api/heats/{heat_id}/reports"
    )
    assert normalize_route(None) == "unmatched"


def test_json_logs_carry_trace_ids_and_drop_extra_fields() -> None:
    shutdown_telemetry()
    _reset_otel_globals()
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    assert configure_telemetry(
        span_exporter=span_exporter,
        metric_reader=metric_reader,
        json_logs=False,
    )

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("app.telemetry.test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    try:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("safe") as span:
            logger.info(
                "Report upload stored",
                extra={
                    "supplier_name": SENTINEL_SUPPLIER,
                    "customer_name": SENTINEL_CUSTOMER,
                    "report_rate": SENTINEL_RATE,
                    "report_amount": SENTINEL_AMOUNT,
                    "upload_filename": SENTINEL_FILENAME,
                    "file_contents": SENTINEL_FILE_TEXT,
                },
            )
        payload = json.loads(stream.getvalue().strip())
        context = span.get_span_context()

        assert set(payload) == EXPECTED_LOG_FIELD_ALLOWLIST
        import app.telemetry as app_telemetry
        assert app_telemetry.LOG_FIELD_ALLOWLIST == EXPECTED_LOG_FIELD_ALLOWLIST
        assert payload["message"] == "Report upload stored"
        assert payload["trace_id"] == format_trace_id(context.trace_id)
        assert payload["span_id"] == format_span_id(context.span_id)
        assert not any(sentinel in stream.getvalue() for sentinel in SENTINELS)
    finally:
        logger.removeHandler(handler)
        shutdown_telemetry()
        _reset_otel_globals()


def test_json_logging_is_idempotent_and_silences_access_logs() -> None:
    import app.telemetry as telemetry_module

    app_logger = logging.getLogger("app")
    access_logger = logging.getLogger("uvicorn.access")
    previous_propagate = app_logger.propagate
    previous_disabled = access_logger.disabled
    previous_handler = getattr(
        app_logger, telemetry_module._JSON_HANDLER_ATTR, None
    )

    try:
        configure_json_logging()
        configure_json_logging()
        handler = getattr(app_logger, telemetry_module._JSON_HANDLER_ATTR)
        assert isinstance(handler.formatter, JsonLogFormatter)
        assert app_logger.handlers.count(handler) == 1
        assert access_logger.disabled is True
    finally:
        if previous_handler is None:
            current = getattr(
                app_logger, telemetry_module._JSON_HANDLER_ATTR, None
            )
            if current is not None:
                app_logger.removeHandler(current)
            app_logger.propagate = previous_propagate
            access_logger.disabled = previous_disabled


def test_sentinel_values_never_reach_exported_telemetry(
    tmp_path: Path,
) -> None:
    with telemetry_client(tmp_path) as (client, span_exporter, metric_reader):
        log_stream = io.StringIO()
        log_handler = logging.StreamHandler(log_stream)
        log_handler.setFormatter(JsonLogFormatter())
        telemetry_logger = logging.getLogger("app.telemetry")
        telemetry_logger.addHandler(log_handler)
        telemetry_logger.setLevel(logging.INFO)
        telemetry_logger.propagate = False

        lot_response = client.post(
            "/api/purchases",
            json={
                "purchase_date": "2026-10-01",
                "supplier": SENTINEL_SUPPLIER,
                "notes": SENTINEL_AMOUNT,
                "weight_kg": "1000.00",
                "rate_per_kg": SENTINEL_RATE,
                "gst_mode": "WITH",
                "transport_mode": "WE_PAY",
                "transport_cost": "2000.00",
            },
        )
        assert lot_response.status_code == 201, lot_response.text
        lot = lot_response.json()

        heat_response = client.post(
            "/api/heats",
            json={
                "heat_no": "H-SENTINEL",
                "heat_date": "2026-10-15",
                "duration_hours": "5.50",
                "notes": "Fictional sentinel heat",
                "alloy": "ADC12",
                "output_kg": "890.00",
                "dross_kg": "60.00",
                "iron_scrap_kg": "5.00",
                "oil_cost": "6000.00",
                "power_cost": "3000.00",
                "labour_cost": "2000.00",
                "other_cost": "0.00",
                "inputs": [{"lot_id": lot["id"], "kg": "1000.00"}],
            },
        )
        assert heat_response.status_code == 201, heat_response.text
        heat = heat_response.json()

        sale_response = client.post(
            "/api/sales",
            json={
                "sale_date": "2026-10-20",
                "customer": SENTINEL_CUSTOMER,
                "item_type": "ADC12",
                "heat_id": heat["id"],
                "weight_kg": "100.00",
                "rate_per_kg": SENTINEL_RATE,
                "gst_mode": "WITH",
                "transport_mode": "WE_PAY_ABSORB",
                "transport_cost": "1000.00",
                "transport_billed": "0.00",
            },
        )
        assert sale_response.status_code == 201, sale_response.text

        upload_response = client.post(
            f"/api/heats/{heat['id']}/reports",
            files={
                "file": (
                    SENTINEL_FILENAME,
                    SENTINEL_PDF,
                    "application/pdf",
                )
            },
            data={"sample_no": "S-1", "result": "PENDING"},
        )
        assert upload_response.status_code == 201, upload_response.text

        failed_response = client.post(
            f"/api/heats/{heat['id']}/reports",
            files={
                "file": (
                    SENTINEL_FILENAME,
                    b"NOT-A-PDF",
                    "application/pdf",
                )
            },
            data={"sample_no": "S-2", "result": "PENDING"},
        )
        assert failed_response.status_code == 422, failed_response.text

        trace.get_tracer_provider().force_flush()  # type: ignore[attr-defined]
        spans = span_exporter.get_finished_spans()
        assert spans
        assert not any(
            sentinel in _span_text(span)
            for span in spans
            for sentinel in SENTINELS
        )

        routes = {
            span.attributes.get("http.route")
            for span in spans
            if "http.route" in span.attributes
        }
        assert "/api/heats" in routes
        assert "/api/heats/{heat_id}/reports" in routes
        assert "/api/purchases" in routes
        assert any("db.system" in span.attributes for span in spans)
        assert any(
            span.attributes.get("app.report.size_bytes") == len(SENTINEL_PDF)
            for span in spans
        )

        points = _metric_points(metric_reader)
        assert points
        assert {
            "http.server.request.count",
            "http.server.request.duration",
            "report.upload.count",
            "report.upload.failures",
            "report.upload.bytes",
        } <= {name for name, _point in points}
        assert not any(
            sentinel in json.dumps(
                {"name": name, "labels": dict(point.attributes)},
                default=str,
            )
            for name, point in points
            for sentinel in SENTINELS
        )

        request_points = [
            point
            for name, point in points
            if name == "http.server.request.count"
        ]
        assert request_points
        assert all(
            set(point.attributes)
            == {"http.route", "http.method", "http.status_class"}
            for point in request_points
        )
        assert all(
            "42" not in str(point.attributes.get("http.route"))
            for point in request_points
        )

        failure_points = [
            point
            for name, point in points
            if name == "report.upload.failures"
        ]
        assert failure_points
        assert all(
            set(point.attributes) == {"reason"} for point in failure_points
        )
        assert any(
            point.attributes.get("reason") == "validation"
            for point in failure_points
        )

        upload_points = [
            point for name, point in points if name == "report.upload.count"
        ]
        assert sum(point.value for point in upload_points) == 1
        assert all(set(point.attributes) == set() for point in upload_points)

        bytes_points = [
            point for name, point in points if name == "report.upload.bytes"
        ]
        assert sum(point.sum for point in bytes_points) == len(SENTINEL_PDF)
        assert all(set(point.attributes) == set() for point in bytes_points)

        log_lines = [
            json.loads(line)
            for line in log_stream.getvalue().splitlines()
            if line.strip()
        ]
        assert log_lines
        for line in log_lines:
            assert set(line) == EXPECTED_LOG_FIELD_ALLOWLIST
            assert line["trace_id"]
            assert line["span_id"]
        assert not any(
            sentinel in log_stream.getvalue() for sentinel in SENTINELS
        )

        telemetry_logger.removeHandler(log_handler)
        telemetry_logger.propagate = True


def test_filters_drop_forbidden_keys_and_sentinel_values() -> None:
    """Explicitly push forbidden keys and sentinels through span, metric and log filters."""
    # 1. Span attribute filter via SanitizingSpanExporter
    raw_span_attributes = {
        "http.method": "POST",
        "http.route": "/api/purchases",
        "supplier": SENTINEL_SUPPLIER,
        "customer": SENTINEL_CUSTOMER,
        "rate": SENTINEL_RATE,
        "amount": SENTINEL_AMOUNT,
        "filename": SENTINEL_FILENAME,
        "db.statement": f"SELECT * FROM lot WHERE supplier = '{SENTINEL_SUPPLIER}'",
        "notes": f"Payment to {SENTINEL_SUPPLIER}",
    }
    sanitized_spans = sanitize_span_attributes(raw_span_attributes)
    serialized_spans = json.dumps(sanitized_spans)
    for forbidden_key in (
        "supplier",
        "customer",
        "rate",
        "amount",
        "filename",
        "db.statement",
        "notes",
    ):
        assert forbidden_key not in sanitized_spans
    for sentinel in (
        SENTINEL_SUPPLIER,
        SENTINEL_CUSTOMER,
        SENTINEL_RATE,
        SENTINEL_AMOUNT,
        SENTINEL_FILENAME,
    ):
        assert sentinel not in serialized_spans

    # 2. Metric attribute filter via sanitize_metric_attributes
    raw_metric_attributes = {
        "http.route": "/api/heats/1",
        "http.method": "GET",
        "http.status_class": "2xx",
        "reason": "validation",
        "supplier": SENTINEL_SUPPLIER,
        "customer": SENTINEL_CUSTOMER,
        "rate": SENTINEL_RATE,
        "amount": SENTINEL_AMOUNT,
        "filename": SENTINEL_FILENAME,
    }
    sanitized_metrics = sanitize_metric_attributes(raw_metric_attributes)
    serialized_metrics = json.dumps(sanitized_metrics)
    for forbidden_key in ("supplier", "customer", "rate", "amount", "filename"):
        assert forbidden_key not in sanitized_metrics
    for sentinel in (
        SENTINEL_SUPPLIER,
        SENTINEL_CUSTOMER,
        SENTINEL_RATE,
        SENTINEL_AMOUNT,
        SENTINEL_FILENAME,
    ):
        assert sentinel not in serialized_metrics

    # 3. Log formatter filter via JsonLogFormatter
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Safe message with no sentinels",
        args=(),
        exc_info=None,
    )
    record.__dict__.update(
        {
            "supplier": SENTINEL_SUPPLIER,
            "customer": SENTINEL_CUSTOMER,
            "rate": SENTINEL_RATE,
            "amount": SENTINEL_AMOUNT,
            "filename": SENTINEL_FILENAME,
        }
    )
    formatted_log = formatter.format(record)
    parsed_log = json.loads(formatted_log)
    assert set(parsed_log) == EXPECTED_LOG_FIELD_ALLOWLIST
    for forbidden_key in ("supplier", "customer", "rate", "amount", "filename"):
        assert forbidden_key not in parsed_log
    for sentinel in (
        SENTINEL_SUPPLIER,
        SENTINEL_CUSTOMER,
        SENTINEL_RATE,
        SENTINEL_AMOUNT,
        SENTINEL_FILENAME,
    ):
        assert sentinel not in formatted_log


def test_collector_down_does_not_delay_or_break_requests(
    tmp_path: Path,
) -> None:
    with telemetry_client(
        tmp_path, endpoint="http://127.0.0.1:1"
    ) as (client, _span_exporter, _metric_reader):
        assert client.get("/api/health").status_code == 200

        started = time.perf_counter()
        response = client.get("/api/health")
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        assert elapsed < 1.0
