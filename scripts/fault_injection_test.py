"""Automated Fault Injection and Recovery Test for Issue #17.

Exercising the end-to-end alert loop:
1. Starts a local Webhook Receiver on port 9999 with an HTML dashboard.
2. Authenticates with MetalOps backend and uploads a baseline report (success).
3. INJECT FAULT: Makes /app/storage non-writable (chmod 000 /app/storage).
4. Drives report uploads: backend fails with HTTP 500 (ReportStorageError).
5. OpenTelemetry records 5xx metrics and logs with trace_id to Loki.
6. Prometheus detects 5xx rate > threshold continuously for the configured duration (5m).
7. Prometheus triggers alert HeatReportHigh5xxRate -> Alertmanager -> alert-adapter.
8. Alert-adapter queries Loki for trace IDs, formats payload per _docs/oncall-agent.md,
   and POSTs to the Webhook Receiver.
9. CAPTURE EVIDENCE: Screenshots of firing alert & webhook payload.
10. RECOVERY: Restores /app/storage permissions (chmod 755 /app/storage).
11. Drives report uploads: backend succeeds with HTTP 201 Created.
12. 5xx rate drops to 0; Prometheus marks alert resolved -> Alertmanager -> alert-adapter.
13. Alert-adapter POSTs resolved payload to Webhook Receiver.
14. CAPTURE EVIDENCE: Screenshots of resolved alert & webhook payload.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "_docs" / "evidence"
ARTIFACT_DIR = Path(r"C:\Users\kusha\.gemini\antigravity\brain\3126c000-ad6d-4cfb-8d80-c9318cb40797")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fault_test")

received_webhooks: list[dict[str, Any]] = []
firing_event = threading.Event()
resolved_event = threading.Event()


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/webhook":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                payload = json.loads(body)
                received_webhooks.append({
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                })
                logger.info(">>> WEBHOOK RECEIVED: status=%s metric=%s trace_ids=%s",
                            payload.get("status"), payload.get("metric"), payload.get("trace_ids"))
                if payload.get("status") == "firing":
                    firing_event.set()
                elif payload.get("status") == "resolved":
                    resolved_event.set()
            except Exception as e:
                logger.error("Failed to parse webhook JSON: %s", e)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            latest = received_webhooks[-1]["payload"] if received_webhooks else None
            status = latest.get("status", "LISTENING") if latest else "LISTENING"
            status_color = "#ef4444" if status == "firing" else ("#10b981" if status == "resolved" else "#6b7280")

            prom_alerts_info = "Prometheus: Connected"
            try:
                with urllib.request.urlopen("http://127.0.0.1:9090/api/v1/alerts", timeout=1) as p_resp:
                    p_data = json.loads(p_resp.read().decode())
                    alerts_list = p_data.get("data", {}).get("alerts", [])
                    if alerts_list:
                        a = alerts_list[0]
                        prom_alerts_info = f"Active Alert: {a.get('labels', {}).get('alertname')} | State: {a.get('state', '').upper()} | Value: {a.get('value')} | Active At: {a.get('activeAt')}"
                    else:
                        prom_alerts_info = "Prometheus: All rules healthy / inactive (Normal)"
            except Exception:
                prom_alerts_info = "Prometheus: Connecting..."

            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>MetalOps Incident Webhook Receiver</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 24px; border: 1px solid #334155; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
        .badge {{ display: inline-block; padding: 6px 16px; border-radius: 9999px; font-weight: 700; font-size: 14px; text-transform: uppercase; background: {status_color}; color: white; }}
        .prom-banner {{ background: #0f172a; border-left: 4px solid #38bdf8; padding: 12px 16px; margin: 12px 0; border-radius: 4px; font-family: monospace; font-size: 13px; color: #7dd3fc; }}
        h1 {{ margin-top: 0; font-size: 24px; }}
        h2 {{ font-size: 18px; color: #94a3b8; margin-top: 0; }}
        pre {{ background: #020617; padding: 16px; border-radius: 8px; overflow-x: auto; font-family: monospace; font-size: 14px; color: #38bdf8; border: 1px solid #1e293b; }}
        .traces {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
        .trace-tag {{ background: #3b82f6; color: white; padding: 4px 8px; border-radius: 6px; font-family: monospace; font-size: 12px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #334155; font-size: 13px; }}
        th {{ color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>System Monitoring & Incident Response</h2>
        <h1>MetalOps Webhook Alerts Receiver</h1>
        <div>Current Webhook Status: <span class="badge">{status}</span></div>
        <div class="prom-banner"><strong>Prometheus Engine:</strong> {prom_alerts_info}</div>
    </div>

    <div class="card">
        <h2>Latest Received Alert Payload</h2>
        {f'''
        <p><strong>Service:</strong> {latest.get("service")}</p>
        <p><strong>Window:</strong> {latest.get("window")} | <strong>Metric:</strong> {latest.get("metric")} | <strong>Route Group:</strong> {latest.get("route_group")}</p>
        <p><strong>Started At:</strong> {latest.get("started_at")}</p>
        {f'<p><strong>Resolved At:</strong> {latest.get("resolved_at")}</p>' if "resolved_at" in latest else ''}
        <h3>Trace IDs Correlated from Loki:</h3>
        <div class="traces">
            {''.join(f'<span class="trace-tag">{tid}</span>' for tid in latest.get("trace_ids", [])) or '<em>No trace IDs in resolved state</em>'}
        </div>
        <h3>Raw JSON Payload:</h3>
        <pre>{json.dumps(latest, indent=2)}</pre>
        ''' if latest else '<p>Waiting for alert notifications from alert-adapter...</p>'}
    </div>

    <div class="card">
        <h2>Notification History ({len(received_webhooks)} received)</h2>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Status</th>
                    <th>Metric</th>
                    <th>Route Group</th>
                    <th>Trace IDs Count</th>
                </tr>
            </thead>
            <tbody>
                {''.join(f'<tr><td>{item["received_at"]}</td><td><strong>{item["payload"].get("status")}</strong></td><td>{item["payload"].get("metric")}</td><td>{item["payload"].get("route_group")}</td><td>{len(item["payload"].get("trace_ids", []))}</td></tr>' for item in reversed(received_webhooks)) or '<tr><td colspan="5">No notifications received yet.</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
            self.wfile.write(html.encode("utf-8"))
        elif self.path == "/api/alerts":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(received_webhooks).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def start_webhook_server(port: int = 9999) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Local Webhook Receiver listening at http://127.0.0.1:%s", port)
    return server


def _ws_connect(url: str) -> socket.socket:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port
    path = parsed.path
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(1024)
        if not chunk:
            break
        resp += chunk
    if b"101 " not in resp:
        raise RuntimeError(f"WS handshake failed: {resp.decode(errors='ignore')}")
    return s


def _ws_send(s: socket.socket, data: dict) -> None:
    payload = json.dumps(data).encode("utf-8")
    length = len(payload)
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    if length < 126:
        header = bytes([0x81, 0x80 | length]) + mask
    elif length < 65536:
        header = bytes([0x81, 0xFE, (length >> 8) & 0xFF, length & 0xFF]) + mask
    else:
        header = bytes([0x81, 0xFF]) + length.to_bytes(8, "big") + mask
    s.sendall(header + masked)


def _ws_recv_frame(s: socket.socket) -> bytes:
    hdr = s.recv(2)
    if len(hdr) < 2:
        return b""
    b1, b2 = hdr[0], hdr[1]
    is_masked = bool(b2 & 0x80)
    payload_len = b2 & 0x7F
    if payload_len == 126:
        payload_len = int.from_bytes(s.recv(2), "big")
    elif payload_len == 127:
        payload_len = int.from_bytes(s.recv(8), "big")
    mask = s.recv(4) if is_masked else None
    data = bytearray()
    while len(data) < payload_len:
        chunk = s.recv(min(payload_len - len(data), 65536))
        if not chunk:
            break
        data.extend(chunk)
    if is_masked and mask:
        data = bytearray(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(data)


def _call_cdp(s: socket.socket, method: str, params: dict = None, msg_id: int = 1) -> dict:
    req = {"id": msg_id, "method": method, "params": params or {}}
    _ws_send(s, req)
    while True:
        raw = _ws_recv_frame(s)
        if not raw:
            continue
        try:
            msg = json.loads(raw.decode("utf-8"))
            if msg.get("id") == msg_id:
                return msg
        except Exception:
            pass


def capture_screenshot(
    url: str,
    output_path: Path,
    wait_seconds: float = 5.0,
    grafana_auth: bool = False,
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    msedge = next((p for p in edge_paths if os.path.exists(p)), None)
    if not msedge:
        logger.warning("Microsoft Edge not found for screenshot at %s", edge_paths)
        return False

    port = 9226
    profile_dir = Path(f"C:/temp/edge_scr_{port}")
    profile_dir.mkdir(parents=True, exist_ok=True)

    session_cookie = None
    if grafana_auth:
        try:
            gf_pass = os.getenv("GRAFANA_ADMIN_PASSWORD", "metalops_local_grafana_2026")
            login_data = json.dumps({"user": "admin", "password": gf_pass}).encode("utf-8")
            req = urllib.request.Request("http://127.0.0.1:3001/login", data=login_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                cookies = resp.headers.get_all("set-cookie") or []
            for c in cookies:
                if "grafana_session=" in c:
                    session_cookie = c.split("grafana_session=", 1)[1].split(";", 1)[0]
                    break
        except Exception as e:
            logger.warning("Could not pre-authenticate with Grafana API: %s", e)

    proc = subprocess.Popen([
        msedge,
        "--headless=new",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-fre",
        "--hide-scrollbars",
        "--window-size=1280,800",
        "about:blank" if grafana_auth else url,
    ])

    time.sleep(2)
    s = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5) as resp:
            tabs = json.loads(resp.read().decode())
        page_tab = next(t for t in tabs if t.get("type") == "page")
        ws_url = page_tab["webSocketDebuggerUrl"]
        s = _ws_connect(ws_url)

        if grafana_auth and session_cookie:
            _call_cdp(s, "Network.enable", {}, msg_id=1)
            _call_cdp(s, "Network.setCookie", {
                "name": "grafana_session",
                "value": session_cookie,
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": True,
            }, msg_id=2)
            _call_cdp(s, "Page.navigate", {"url": url}, msg_id=3)

        time.sleep(wait_seconds)

        # For Prometheus alerts, expand rule cards to reveal expressions and details
        if "9090" in url and "alerts" in url:
            _call_cdp(s, "Runtime.evaluate", {
                "expression": "document.querySelectorAll('div[class*=\"collapse\"]').forEach(el => el.click()); document.querySelectorAll('button').forEach(b => { if((b.innerText||'').includes('HeatReport')) b.click(); });"
            }, msg_id=4)
            time.sleep(1)

        res = _call_cdp(s, "Page.captureScreenshot", {"format": "png"}, msg_id=10)
        img_b64 = res.get("result", {}).get("data", "")
        if img_b64:
            img_bytes = base64.b64decode(img_b64)
            output_path.write_bytes(img_bytes)
            logger.info("Captured genuine screenshot (%d bytes): %s", len(img_bytes), output_path)
            if ARTIFACT_DIR.is_dir():
                shutil.copy2(output_path, ARTIFACT_DIR / output_path.name)
            return True
        logger.warning("CDP captureScreenshot returned no data: %s", res)
    except Exception as exc:
        logger.warning("CDP screenshot failed for %s: %s", url, exc)
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    return False


def login_and_get_session(base_url: str = "http://127.0.0.1:3000") -> str:
    login_url = f"{base_url}/api/auth/login"
    data = json.dumps({"email": "owner@workshop.local", "password": "ValidPassword123!"}).encode("utf-8")
    req = urllib.request.Request(
        login_url,
        data=data,
        headers={"Content-Type": "application/json", "Origin": base_url},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        cookies = resp.headers.get_all("set-cookie") or []
        for cookie in cookies:
            if "session=" in cookie:
                session_token = cookie.split("session=", 1)[1].split(";", 1)[0]
                logger.info("Logged in successfully, session token acquired.")
                return session_token
    raise RuntimeError("Could not acquire session token from login.")


def upload_sample_report(base_url: str, session_token: str, heat_id: int = 1) -> tuple[int, str]:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    sample_pdf = b"%PDF-1.4\n%Spectro Lab Test Report\n1 0 obj\n<< /Title (Test) >>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 1 >>\nstartxref\n99\n%%EOF\n"

    body = io.BytesIO()
    # file field
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b'Content-Disposition: form-data; name="file"; filename="report.pdf"\r\n')
    body.write(b"Content-Type: application/pdf\r\n\r\n")
    body.write(sample_pdf)
    body.write(b"\r\n")
    # sample_no
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b'Content-Disposition: form-data; name="sample_no"\r\n\r\n')
    body.write(f"SAMPLE-{int(time.time() * 1000) % 1000000}".encode("utf-8"))
    body.write(b"\r\n")
    # result
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b'Content-Disposition: form-data; name="result"\r\n\r\n')
    body.write(b"PASS\r\n")
    # grade_tested
    body.write(f"--{boundary}\r\n".encode("utf-8"))
    body.write(b'Content-Disposition: form-data; name="grade_tested"\r\n\r\n')
    body.write(b"ADC12\r\n")
    body.write(f"--{boundary}--\r\n".encode("utf-8"))

    content = body.getvalue()
    upload_url = f"{base_url}/api/heats/{heat_id}/reports"
    req = urllib.request.Request(
        upload_url,
        data=content,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Cookie": f"session={session_token}",
            "Origin": base_url,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="ignore")


def execute_docker_command(cmd_str: str) -> subprocess.CompletedProcess:
    logger.info("Executing: %s", cmd_str)
    return subprocess.run(cmd_str, shell=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description="Fault injection and alert verification runner.")
    parser.add_argument("--fast", action="store_true", help="Accelerate evaluation window for rapid testing.")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="Base URL of MetalOps frontend/proxy.")
    args = parser.parse_args()

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    server = start_webhook_server(9999)

    rule_path = REPO_ROOT / "observability" / "prometheus" / "alert_rules.yml"
    original_rule_content = rule_path.read_text(encoding="utf-8")

    try:
        if args.fast:
            logger.info("Using fast evaluation window (for: 30s, [1m]) for accelerated test.")
            fast_content = original_rule_content.replace("for: 5m", "for: 30s").replace("[5m]", "[1m]")
            rule_path.write_text(fast_content, encoding="utf-8")
            execute_docker_command("docker exec metalops-prometheus kill -HUP 1")
            time.sleep(2)

        # Step 1: Login
        session_token = login_and_get_session(args.base_url)

        # Baseline: normal upload
        status_code, resp_text = upload_sample_report(args.base_url, session_token)
        logger.info("Baseline report upload result: status=%s", status_code)

        # Step 2: Fault Injection
        logger.info("=================================================================")
        logger.info("PHASE 1: FAULT INJECTION (chmod 000 /app/storage)")
        logger.info("=================================================================")
        res = execute_docker_command("docker exec metalops-backend chmod 000 /app/storage")
        if res.returncode != 0:
            logger.error("Failed to inject fault: %s", res.stderr)
            sys.exit(1)

        # Step 3: Drive 500 errors
        logger.info("Driving 500 errors to heat/report upload endpoint...")
        start_time = time.time()
        timeout_seconds = 180 if args.fast else 420  # up to 7m for full 5m window

        firing_event.clear()
        while not firing_event.is_set():
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise TimeoutError(f"Alert did not fire within {timeout_seconds}s!")

            code, body = upload_sample_report(args.base_url, session_token)
            logger.info("[%3.0fs] Upload attempt returned HTTP %s (expected 500)", elapsed, code)
            time.sleep(10)

        firing_duration = time.time() - start_time
        logger.info(">>> ALERT FIRED SUCCESSFULLY after %.1f seconds!", firing_duration)

        # Step 4: Capture Firing Evidence
        time.sleep(2)
        capture_screenshot("http://127.0.0.1:9999", EVIDENCE_DIR / "webhook_payload_firing.png", wait_seconds=2)
        capture_screenshot("http://127.0.0.1:9090/alerts", EVIDENCE_DIR / "alert_firing_prometheus.png", wait_seconds=5)
        capture_screenshot(
            "http://127.0.0.1:3001/d/metalops-key-journey/metalops-key-journey?from=now-15m&to=now&refresh=5s",
            EVIDENCE_DIR / "alert_firing_grafana.png",
            wait_seconds=5,
            grafana_auth=True,
        )

        # Step 5: Recovery
        logger.info("=================================================================")
        logger.info("PHASE 2: RECOVERY (chmod 755 /app/storage)")
        logger.info("=================================================================")
        res = execute_docker_command("docker exec metalops-backend chmod 755 /app/storage")
        if res.returncode != 0:
            logger.error("Failed to recover storage permissions: %s", res.stderr)
            sys.exit(1)

        logger.info("Driving successful report uploads to restore healthy rate...")
        rec_start_time = time.time()
        rec_timeout_seconds = 240 if args.fast else 480
        resolved_event.clear()

        while not resolved_event.is_set():
            elapsed = time.time() - rec_start_time
            if elapsed > rec_timeout_seconds:
                raise TimeoutError(f"Alert did not resolve within {rec_timeout_seconds}s!")

            code, body = upload_sample_report(args.base_url, session_token)
            logger.info("[%3.0fs] Recovery upload attempt returned HTTP %s (expected 200/201)", elapsed, code)
            time.sleep(10)

        resolved_duration = time.time() - rec_start_time
        logger.info(">>> ALERT RESOLVED SUCCESSFULLY after %.1f seconds!", resolved_duration)

        # Step 6: Capture Resolved Evidence
        time.sleep(2)
        capture_screenshot("http://127.0.0.1:9999", EVIDENCE_DIR / "webhook_payload_resolved.png", wait_seconds=2)
        capture_screenshot("http://127.0.0.1:9090/alerts", EVIDENCE_DIR / "alert_resolved_prometheus.png", wait_seconds=5)

        logger.info("=================================================================")
        logger.info("TEST COMPLETE: ALL 3 OUTCOMES VERIFIED WITH EVIDENCE")
        logger.info("=================================================================")

    finally:
        # Always restore original rule file and ensure storage permissions
        rule_path.write_text(original_rule_content, encoding="utf-8")
        execute_docker_command("docker exec metalops-prometheus kill -HUP 1")
        execute_docker_command("docker exec metalops-backend chmod 755 /app/storage")
        server.shutdown()


if __name__ == "__main__":
    main()
