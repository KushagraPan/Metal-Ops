"""Alert Adapter for MetalOps Lite.

Receives alerts from Alertmanager, enriches them with recent trace IDs from Loki,
formats the payload according to _docs/oncall-agent.md, and dispatches firing and
resolved notifications to ALERT_WEBHOOK_URL.

Privacy & Security:
- Payloads are strictly sanitized: only allow-listed fields are dispatched.
- Webhook credentials and tokens are redacted from all log messages.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("metalops.alert_adapter")

# Deny-by-default allow-list for outgoing webhook alert payloads.
ALLOWED_ALERT_PAYLOAD_FIELDS = frozenset(
    {
        "status",
        "service",
        "window",
        "metric",
        "route_group",
        "trace_ids",
        "started_at",
        "resolved_at",
    }
)

_TRACE_ID_RE = re.compile(r'"trace_id"\s*:\s*"([a-fA-F0-9]{32})"')
_SENSITIVE_PARAM_NAMES = frozenset(
    {"token", "key", "secret", "auth", "password", "code", "apikey", "access_token"}
)


def mask_credentials(url: str | None) -> str:
    """Mask username, password and sensitive query parameters from a URL."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        netloc = parts.netloc
        if "@" in netloc:
            user_info, _, host = netloc.partition("@")
            user, _, _ = user_info.partition(":")
            netloc = f"{user}:***@{host}" if user else f"***@{host}"

        query_params = parse_qsl(parts.query, keep_blank_values=True)
        masked_params = []
        for k, v in query_params:
            if k.lower() in _SENSITIVE_PARAM_NAMES or "secret" in k.lower() or "token" in k.lower():
                masked_params.append((k, "***"))
            else:
                masked_params.append((k, v))
        masked_query = urlencode(masked_params)
        return urlunsplit((parts.scheme, netloc, parts.path, masked_query, parts.fragment))
    except Exception:
        return "<redacted-url>"


def extract_trace_ids_from_loki(data: Mapping[str, Any] | None) -> list[str]:
    """Extract up to 5 unique trace IDs from a Loki query_range response."""
    if not data or not isinstance(data, dict):
        return []

    results = data.get("data", {}).get("result", [])
    trace_ids: list[str] = []
    seen = set()

    for item in results:
        values = item.get("values", [])
        for val in values:
            if not (isinstance(val, (list, tuple)) and len(val) >= 2):
                continue
            log_line = val[1]
            if not isinstance(log_line, str):
                continue
            matches = _TRACE_ID_RE.findall(log_line)
            for tid in matches:
                normalized = tid.lower()
                if normalized not in seen and normalized != "0" * 32:
                    seen.add(normalized)
                    trace_ids.append(normalized)
                    if len(trace_ids) >= 5:
                        return trace_ids

    return trace_ids


def fetch_recent_trace_ids(loki_url: str, timeout: float = 2.0) -> list[str]:
    """Query Loki for recent log lines containing trace IDs."""
    if not loki_url:
        return []
    base = loki_url.rstrip("/")
    # Query logs from the last 15 minutes
    query_url = f"{base}/loki/api/v1/query_range?query=%7Bservice_name%3D~%22.%2B%22%7D&limit=100"
    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "MetalOps-Alert-Adapter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return extract_trace_ids_from_loki(body)
    except Exception as exc:
        logger.warning("Could not fetch recent trace IDs from Loki (%s): %s", mask_credentials(loki_url), type(exc).__name__)
    return []


def format_alert_payload(
    status: str,
    alert: Mapping[str, Any],
    trace_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build the exact payload required by _docs/oncall-agent.md."""
    labels = alert.get("labels", {})
    service = labels.get("service") or "metalops-api"
    window = labels.get("window") or "5m"
    metric = labels.get("metric") or "http_5xx_rate"
    route_group = labels.get("route_group") or "heats,reports"
    starts_at = alert.get("startsAt") or datetime.now(timezone.utc).isoformat()

    clean_trace_ids = (trace_ids or [])[:5]

    payload: dict[str, Any] = {
        "status": status,
        "service": str(service),
        "window": str(window),
        "metric": str(metric),
        "route_group": str(route_group),
        "trace_ids": clean_trace_ids,
        "started_at": str(starts_at),
    }

    if status == "resolved":
        ends_at = alert.get("endsAt") or datetime.now(timezone.utc).isoformat()
        payload["resolved_at"] = str(ends_at)
        payload["trace_ids"] = []

    # Filter out anything not in the allow-list
    return {k: v for k, v in payload.items() if k in ALLOWED_ALERT_PAYLOAD_FIELDS}


def send_webhook_notification(
    webhook_url: str | None,
    payload: dict[str, Any],
    timeout: float = 3.0,
) -> bool:
    """Send an HTTP POST notification to the configured webhook URL."""
    clean_url = (webhook_url or "").strip()
    if not clean_url:
        logger.info("ALERT_WEBHOOK_URL is unset; skipping webhook notification.")
        return False

    safe_url = mask_credentials(clean_url)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        clean_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MetalOps-Alert-Adapter/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = getattr(response, "status", getattr(response, "code", 200))
            if 200 <= status_code < 300:
                logger.info(
                    "Alert notification sent to %s (status=%s, alert_status=%s)",
                    safe_url,
                    status_code,
                    payload.get("status"),
                )
                return True
            logger.warning(
                "Webhook responded with non-2xx status: %s to %s",
                status_code,
                safe_url,
            )
            return False
    except Exception as exc:
        logger.error(
            "Failed sending alert notification to %s: %s",
            safe_url,
            type(exc).__name__,
        )
        return False


class AlertAdapter:
    """Core adapter service coordinating Alertmanager inputs, Loki lookups and Webhook dispatches."""

    def __init__(
        self,
        webhook_url: str | None = None,
        loki_url: str | None = None,
        threshold: float = 0.0,
    ) -> None:
        self.webhook_url = webhook_url if webhook_url is not None else os.getenv("ALERT_WEBHOOK_URL")
        self.loki_url = loki_url if loki_url is not None else os.getenv("LOKI_URL", "http://loki:3100")
        self.threshold = threshold
        self.history: list[dict[str, Any]] = []

    def handle_alertmanager_payload(self, body: Mapping[str, Any]) -> list[dict[str, Any]]:
        status = body.get("status", "firing").lower()
        alerts = body.get("alerts", [])
        dispatched: list[dict[str, Any]] = []

        if not alerts:
            # Single alert structure fallback
            alerts = [body]

        trace_ids = fetch_recent_trace_ids(self.loki_url) if (status == "firing" and self.loki_url) else []

        for item in alerts:
            item_status = item.get("status", status).lower()
            formatted = format_alert_payload(status=item_status, alert=item, trace_ids=trace_ids)
            send_webhook_notification(self.webhook_url, formatted)
            self.history.append(formatted)
            if len(self.history) > 50:
                self.history.pop(0)
            dispatched.append(formatted)

        return dispatched


def make_handler(adapter: AlertAdapter):
    class AdapterHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in {"/health", "/api/health"}:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"healthy","service":"alert-adapter"}')
            elif self.path in {"/api/alerts/history", "/alerts/history"}:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(adapter.history).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path in {"/alerts", "/api/v2/alerts", "/webhook"}:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                try:
                    data = json.loads(post_body.decode("utf-8"))
                except Exception:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error":"Invalid JSON"}')
                    return

                dispatched = adapter.handle_alertmanager_payload(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "dispatched_count": len(dispatched)}).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            # Safe internal logger
            logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    return AdapterHTTPHandler


def main() -> None:
    port = int(os.getenv("PORT", "9097"))
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    loki_url = os.getenv("LOKI_URL", "http://loki:3100")
    threshold = float(os.getenv("ALERT_5XX_THRESHOLD", "0.0"))

    logger.info("Starting MetalOps Alert Adapter on port %s", port)
    logger.info("Configured Webhook: %s", mask_credentials(webhook_url) or "<unset>")
    logger.info("Loki URL: %s", mask_credentials(loki_url))
    logger.info("5xx Rate Threshold: %s", threshold)

    adapter = AlertAdapter(webhook_url=webhook_url, loki_url=loki_url, threshold=threshold)
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, make_handler(adapter))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Alert Adapter.")
        httpd.server_close()


if __name__ == "__main__":
    main()
