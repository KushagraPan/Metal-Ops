"""On-Call Agent Webhook Listener for MetalOps Lite.

Receives webhook notifications from alert-adapter (or Alertmanager), deduplicates,
and invokes the On-Call Responder Agent.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from observability.oncall_agent.agent import (
    AlertDeduplicator,
    GuardrailViolation,
    OnCallAgent,
    ValidationError,
    validate_alert_payload,
)

logger = logging.getLogger("metalops.oncall_webhook")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class OnCallWebhookHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for On-Call Webhook calls."""

    agent: OnCallAgent = OnCallAgent()
    deduplicator: AlertDeduplicator = AlertDeduplicator(ttl_seconds=300.0)
    history: list[dict[str, Any]] = []

    def do_GET(self) -> None:
        if self.path in {"/health", "/api/health", "/"}:
            self._send_json(200, {"status": "ok", "service": "oncall-agent-webhook"})
            return
        if self.path in {"/history", "/api/history"}:
            self._send_json(200, {"history": self.history})
            return
        self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json(400, {"error": "Empty request body"})
            return

        try:
            body_bytes = self.rfile.read(content_length)
            raw_data = json.loads(body_bytes.decode("utf-8"))
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid JSON body: {exc}"})
            return

        try:
            alert = validate_alert_payload(raw_data)
        except ValidationError as err:
            logger.warning("Rejected invalid alert payload: %s", err)
            self._send_json(400, {"error": str(err)})
            return

        # Deduplicate alert
        if self.deduplicator.is_duplicate(alert):
            logger.info("Deduplicating duplicate alert: %s (%s)", alert.metric, alert.window)
            self._send_json(429, {"status": "deduplicated", "message": "Alert currently being handled or handled recently"})
            return

        self.deduplicator.record(alert)

        try:
            result = self.agent.handle_alert(alert)
            self.history.append(result)
            if len(self.history) > 50:
                self.history.pop(0)
            self._send_json(200, {"status": "accepted", "result": result})
        except GuardrailViolation as gv:
            logger.error("Guardrail violation in on-call agent: %s", gv)
            self._send_json(500, {"error": f"Guardrail violation: {gv}"})
        except Exception as exc:
            logger.error("Failed handling alert in on-call agent: %s", exc)
            self._send_json(500, {"error": f"Internal agent error: {exc}"})

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Prevent default stderr logging clutter
        logger.info("%s - %s", self.address_string(), format % args)


def run_webhook_server(port: int = 9098, host: str = "0.0.0.0") -> None:
    server = HTTPServer((host, port), OnCallWebhookHandler)
    logger.info("On-Call Agent Webhook listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down On-Call Agent Webhook server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(os.getenv("ONCALL_WEBHOOK_PORT", "9098"))
    run_webhook_server(port=port)

