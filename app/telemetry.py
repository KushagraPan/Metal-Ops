"""Deny-by-default OpenTelemetry instrumentation for MetalOps Lite.

Telemetry is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. When it is on,
every span attribute, metric label and log field passes through an allow-list
before it leaves the process. Anything else is dropped.

The exporter runs on background batch processors, so a missing Collector adds
no request latency and never raises into a request.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Status, format_span_id, format_trace_id

# Deny by default: only these keys survive export.
SPAN_ATTRIBUTE_ALLOWLIST = frozenset(
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

# Request metrics use the first three; upload failures use `reason`.
METRIC_LABEL_ALLOWLIST = frozenset(
    {
        "http.route",
        "http.method",
        "http.status_class",
        "reason",
    }
)

# Only these five metric names are exported. Instrumentation extras are dropped.
METRIC_NAME_ALLOWLIST = frozenset(
    {
        "http.server.request.count",
        "http.server.request.duration",
        "report.upload.count",
        "report.upload.failures",
        "report.upload.bytes",
    }
)

LOG_FIELD_ALLOWLIST = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
        "trace_id",
        "span_id",
    }
)

UPLOAD_FAILURE_REASONS = frozenset(
    {
        "validation",
        "storage",
        "not_found",
        "unknown",
    }
)

_METHOD_RE = re.compile(r"^[A-Z]{1,10}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_DIGITS_RE = re.compile(r"^[0-9]+$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DB_ATTRIBUTE_KEYS = frozenset({"db.system", "db.operation"})
_ID_ATTRIBUTE_KEYS = frozenset(
    {"http.status_code", "app.heat.id", "app.report.id", "app.report.size_bytes"}
)

_request_counter: metrics.Counter | None = None
_request_duration: metrics.Histogram | None = None
_upload_counter: metrics.Counter | None = None
_upload_failures: metrics.Counter | None = None
_upload_bytes: metrics.Histogram | None = None

_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_configured = False

_JSON_HANDLER_ATTR = "_metalops_json_handler"
logger = logging.getLogger(__name__)


def otlp_endpoint() -> str | None:
    """Return the configured OTLP endpoint, or None when telemetry is off."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint is None:
        return None
    endpoint = endpoint.strip()
    return endpoint or None


def configure_telemetry(
    app: FastAPI | None = None,
    engine: Any | None = None,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
    endpoint: str | None = None,
    json_logs: bool = True,
) -> bool:
    """Install tracing, metrics and JSON logs. False means telemetry is off."""
    global _configured, _tracer_provider, _meter_provider

    if _configured:
        if app is not None:
            _instrument_app(app, _tracer_provider, _meter_provider)
        if engine is not None:
            _instrument_engine(engine, _tracer_provider)
        return True

    resolved_endpoint = endpoint if endpoint is not None else otlp_endpoint()
    if resolved_endpoint is None and span_exporter is None and metric_reader is None:
        return False

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME") or "metalops-lite",
        }
    )

    tracer_provider: TracerProvider | None = None
    if span_exporter is not None:
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(SanitizingSpanExporter(span_exporter))
        )
    elif resolved_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                SanitizingSpanExporter(
                    OTLPSpanExporter(
                        endpoint=_signal_endpoint(resolved_endpoint, "/v1/traces"),
                        timeout=2,
                    )
                )
            )
        )

    if tracer_provider is not None:
        trace.set_tracer_provider(tracer_provider)
        _tracer_provider = tracer_provider

    readers: list[MetricReader] = []
    if metric_reader is not None:
        readers.append(metric_reader)
    elif resolved_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )

        readers.append(
            PeriodicExportingMetricReader(
                SanitizingMetricExporter(
                    OTLPMetricExporter(
                        endpoint=_signal_endpoint(resolved_endpoint, "/v1/metrics"),
                        timeout=2,
                    )
                ),
                export_interval_millis=30_000,
                export_timeout_millis=2_000,
            )
        )

    if readers:
        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(meter_provider)
        _meter_provider = meter_provider
        _create_instruments(metrics.get_meter("app.telemetry", version="0.1.0"))

    if app is not None:
        _instrument_app(app, tracer_provider, _meter_provider)
    if engine is not None:
        _instrument_engine(engine, tracer_provider)

    if json_logs:
        configure_json_logging()

    _configured = True
    return True


def shutdown_telemetry() -> None:
    """Flush and stop providers. Safe to call when telemetry is off."""
    global _configured, _tracer_provider, _meter_provider
    global _request_counter, _request_duration, _upload_counter
    global _upload_failures, _upload_bytes

    if _tracer_provider is not None:
        _tracer_provider.shutdown()
    if _meter_provider is not None:
        _meter_provider.shutdown()

    _configured = False
    _tracer_provider = None
    _meter_provider = None
    _request_counter = None
    _request_duration = None
    _upload_counter = None
    _upload_failures = None
    _upload_bytes = None


def _signal_endpoint(base: str, path: str) -> str:
    base = base.rstrip("/")
    return base if base.endswith(path) else f"{base}{path}"


def _create_instruments(meter: metrics.Meter) -> None:
    global _request_counter, _request_duration, _upload_counter
    global _upload_failures, _upload_bytes

    _request_counter = meter.create_counter(
        "http.server.request.count",
        description="HTTP requests handled, by route template.",
    )
    _request_duration = meter.create_histogram(
        "http.server.request.duration",
        unit="s",
        description="HTTP request latency, by route template.",
    )
    _upload_counter = meter.create_counter(
        "report.upload.count",
        description="Successful spectro report uploads.",
    )
    _upload_failures = meter.create_counter(
        "report.upload.failures",
        description="Failed spectro report uploads, by fixed reason category.",
    )
    _upload_bytes = meter.create_histogram(
        "report.upload.bytes",
        unit="By",
        description="Size of successfully stored report files.",
    )


def _instrument_app(
    app: FastAPI,
    tracer_provider: TracerProvider | None,
    meter_provider: MeterProvider | None,
) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    if not getattr(app, "_metalops_metrics_middleware", False):
        app.add_middleware(RequestMetricsMiddleware, fastapi_app=app)
        app._metalops_metrics_middleware = True  # type: ignore[attr-defined]


def _instrument_engine(
    engine: Any, tracer_provider: TracerProvider | None
) -> None:
    if getattr(engine, "_metalops_sqlalchemy_instrumented", False):
        return
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        tracer_provider=tracer_provider,
    )
    engine._metalops_sqlalchemy_instrumented = True


def record_created_heat(heat_id: int) -> None:
    _set_span_attribute("app.heat.id", heat_id)


def record_report_upload_success(
    *, heat_id: int, report_id: int, size_bytes: int
) -> None:
    if _upload_counter is not None:
        _upload_counter.add(1)
    if _upload_bytes is not None:
        _upload_bytes.record(size_bytes)
    _set_span_attribute("app.heat.id", heat_id)
    _set_span_attribute("app.report.id", report_id)
    _set_span_attribute("app.report.size_bytes", size_bytes)
    logger.info("Report upload stored")


def record_report_upload_failure(reason: str) -> None:
    safe_reason = reason if reason in UPLOAD_FAILURE_REASONS else "unknown"
    if _upload_failures is not None:
        _upload_failures.add(1, attributes={"reason": safe_reason})
    logger.info("Report upload failed: %s", safe_reason)


def _set_span_attribute(key: str, value: int) -> None:
    span: Span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(key, value)


def record_request(
    route: str | None, method: str, status_code: int, duration_seconds: float
) -> None:
    if _request_counter is None or _request_duration is None:
        return
    labels = {
        "http.route": normalize_route(route),
        "http.method": normalize_method(method),
        "http.status_class": normalize_status_class(status_code),
    }
    _request_counter.add(1, attributes=labels)
    _request_duration.record(max(duration_seconds, 0.0), attributes=labels)


def normalize_route(route: str | None) -> str:
    """Return a route template with query strings and concrete IDs removed."""
    if not route:
        return "unmatched"
    value = str(route).split("?", 1)[0].split("#", 1)[0]
    if not value.startswith("/"):
        return "unmatched"
    parts: list[str] = []
    for part in value.split("/"):
        if _DIGITS_RE.fullmatch(part) or _UUID_RE.fullmatch(part):
            parts.append("{id}")
        else:
            parts.append(part)
    return "/".join(parts)[:200] or "unmatched"


def normalize_method(method: str | None) -> str:
    value = (method or "").strip().upper()
    return value if _METHOD_RE.fullmatch(value) else "OTHER"


def normalize_status_class(status_code: int | str) -> str:
    text = str(status_code).strip().lower()
    if text in {"1xx", "2xx", "3xx", "4xx", "5xx"}:
        return text
    try:
        code = int(text)
    except (TypeError, ValueError):
        return "unknown"
    if 100 <= code <= 599:
        return f"{code // 100}xx"
    return "unknown"


def sanitize_span_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep only allow-listed span keys with safe values."""
    safe: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if key not in SPAN_ATTRIBUTE_ALLOWLIST:
            continue
        cleaned = _clean_span_value(key, value)
        if cleaned is not None:
            safe[key] = cleaned
    return safe


def _clean_span_value(key: str, value: Any) -> Any | None:
    if key == "http.method":
        method = normalize_method(str(value))
        return None if method == "OTHER" else method
    if key == "http.route":
        return normalize_route(str(value))
    if key == "http.status_code":
        return _clean_int(value, minimum=100, maximum=599)
    if key == "http.status_class":
        return normalize_status_class(value)
    if key in _DB_ATTRIBUTE_KEYS:
        text = str(value)
        return text if _TOKEN_RE.fullmatch(text) else None
    if key in _ID_ATTRIBUTE_KEYS:
        return _clean_int(value, minimum=0)
    return None


def _clean_int(value: Any, *, minimum: int, maximum: int | None = None) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def safe_span_name(attributes: Mapping[str, Any]) -> str:
    """Build a span name from safe values only, never the raw incoming path."""
    if "db.system" in attributes:
        operation = attributes.get("db.operation", "query")
        return f"{operation} {attributes['db.system']}"[:200]
    method = attributes.get("http.method")
    if method:
        route = attributes.get("http.route", "unmatched")
        return f"{method} {route}"[:200]
    return "internal"


def sanitize_resource(resource: Resource) -> Resource:
    """Keep only the service identity and SDK identity on the resource."""
    attributes = {
        key: value
        for key, value in resource.attributes.items()
        if key == "service.name" or key.startswith("telemetry.sdk.")
    }
    return Resource(attributes, schema_url=resource.schema_url)


def sanitize_span(span: ReadableSpan) -> ReadableSpan:
    attributes = sanitize_span_attributes(span.attributes)
    return ReadableSpan(
        name=safe_span_name(attributes),
        context=span.context,
        parent=span.parent,
        resource=sanitize_resource(span.resource),
        attributes=attributes,
        events=(),
        links=(),
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def sanitize_metric_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep only allow-listed metric labels with fixed values."""
    safe: dict[str, Any] = {}
    for key, value in (attributes or {}).items():
        if key not in METRIC_LABEL_ALLOWLIST:
            continue
        if key == "http.route":
            safe[key] = normalize_route(str(value))
        elif key == "http.method":
            method = normalize_method(str(value))
            if method != "OTHER":
                safe[key] = method
        elif key == "http.status_class":
            safe[key] = normalize_status_class(value)
        elif key == "reason" and str(value) in UPLOAD_FAILURE_REASONS:
            safe[key] = str(value)
    return safe


class SanitizingSpanExporter(SpanExporter):
    """Drop private span data immediately before the real exporter sees it."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> Any:
        return self._inner.export([sanitize_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


class SanitizingMetricExporter(MetricExporter):
    """Drop private metric labels immediately before export."""

    def __init__(self, inner: MetricExporter) -> None:
        super().__init__(
            preferred_temporality=getattr(inner, "_preferred_temporality", None),
            preferred_aggregation=getattr(inner, "_preferred_aggregation", None),
        )
        self._inner = inner

    def export(
        self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any
    ) -> Any:
        return self._inner.export(
            _sanitize_metrics_data(metrics_data), timeout_millis, **kwargs
        )

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._inner.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        self._inner.shutdown(timeout_millis, **kwargs)


def _sanitize_metrics_data(metrics_data: Any) -> Any:
    sanitized_metrics = []
    for resource_metrics in metrics_data.resource_metrics:
        scope_metrics = []
        for scope in resource_metrics.scope_metrics:
            metrics_list = []
            for metric in scope.metrics:
                if metric.name not in METRIC_NAME_ALLOWLIST:
                    continue
                data = metric.data
                points = tuple(
                    replace(
                        point,
                        attributes=sanitize_metric_attributes(
                            getattr(point, "attributes", None)
                        ),
                    )
                    for point in data.data_points
                )
                metrics_list.append(
                    replace(metric, data=replace(data, data_points=points))
                )
            scope_metrics.append(replace(scope, metrics=metrics_list))
        sanitized_metrics.append(
            replace(
                resource_metrics,
                resource=sanitize_resource(resource_metrics.resource),
                scope_metrics=scope_metrics,
            )
        )
    return replace(metrics_data, resource_metrics=sanitized_metrics)


class RequestMetricsMiddleware:
    """Record request count and latency with route-template-only labels."""

    def __init__(self, app: Any, fastapi_app: FastAPI) -> None:
        self.app = app
        self.fastapi_app = fastapi_app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            record_request(
                _route_template(scope, self.fastapi_app),
                scope.get("method", ""),
                status_code,
                time.perf_counter() - started,
            )


def _route_template(scope: Any, app: FastAPI) -> str | None:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)

    endpoint = scope.get("endpoint")
    if endpoint is None:
        return None
    for candidate in app.routes:
        if getattr(candidate, "endpoint", None) is endpoint:
            path = getattr(candidate, "path", None)
            if path:
                return str(path)
    return None


class JsonLogFormatter(logging.Formatter):
    """Emit JSON with only the allow-listed fields plus trace context."""

    def format(self, record: logging.LogRecord) -> str:
        span_context = trace.get_current_span().get_span_context()
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": (
                format_trace_id(span_context.trace_id)
                if span_context.is_valid
                else ""
            ),
            "span_id": (
                format_span_id(span_context.span_id)
                if span_context.is_valid
                else ""
            ),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_json_logging() -> None:
    """Install one JSON handler on the app logger and silence access logs."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    handler = getattr(app_logger, _JSON_HANDLER_ATTR, None)
    if handler is None:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        setattr(app_logger, _JSON_HANDLER_ATTR, handler)
        app_logger.addHandler(handler)
    app_logger.propagate = False
    logging.getLogger("uvicorn.access").disabled = True
