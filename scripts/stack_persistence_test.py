"""Test upload persistence across Docker Compose stack restart (Issue #13).

Steps:
1. Health check the running Compose stack.
2. Log in and upload a spectro report PDF.
3. Compute SHA-256 hash of uploaded bytes.
4. Run 'docker compose down' (retaining named volumes).
5. Run 'docker compose up -d --wait'.
6. Log in again after restart.
7. Download the report file and verify identical bytes (checksum and length match).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.env  # noqa: F401

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:3000")
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "owner@workshop.local")
OWNER_PASSWORD = os.getenv("OWNER_PASSWORD", "change_this_demo_password_10chars")


def wait_for_health(client: httpx.Client, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            res = client.get("/api/health", timeout=3.0)
            if res.status_code == 200 and res.json().get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Service at {BASE_URL}/api/health did not become healthy within {timeout_sec}s")


def run_cmd(cmd: list[str]) -> None:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"STDOUT:\n{result.stdout}", file=sys.stderr)
        print(f"STDERR:\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed with code {result.returncode}: {' '.join(cmd)}")


def main() -> None:
    print(f"--- Stack Persistence Test against {BASE_URL} ---")

    client = httpx.Client(base_url=BASE_URL, follow_redirects=True)

    # 1. Wait for health
    print("1. Waiting for stack health...")
    wait_for_health(client)

    # 2. Login
    print("2. Logging in...")
    login_res = client.post(
        "/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    if login_res.status_code != 200:
        raise RuntimeError(f"Login failed: {login_res.status_code} - {login_res.text}")

    # 3. Find heat
    print("3. Querying heats...")
    heats_res = client.get("/api/heats")
    if heats_res.status_code != 200 or not heats_res.json():
        raise RuntimeError(f"Failed to query heats or no heats found: {heats_res.status_code} {heats_res.text}")
    heat_id = heats_res.json()[0]["id"]
    print(f"Using heat id: {heat_id}")

    # 4. Generate report bytes
    unique_token = uuid.uuid4().hex
    raw_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
        b"xref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n"
        b"trailer << /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF\n"
        + f"Token: {unique_token}\n".encode("utf-8")
    )
    expected_hash = hashlib.sha256(raw_pdf).hexdigest()
    expected_len = len(raw_pdf)

    # 5. Upload report
    sample_no = f"PERSIST-{unique_token[:6].upper()}"
    print(f"4. Uploading report '{sample_no}' ({expected_len} bytes, sha256={expected_hash})...")
    upload_res = client.post(
        f"/api/heats/{heat_id}/reports",
        files={"file": (f"{sample_no}.pdf", raw_pdf, "application/pdf")},
        data={"sample_no": sample_no, "result": "PASS", "notes": "Persistence test report"},
    )
    if upload_res.status_code != 201:
        raise RuntimeError(f"Upload failed: {upload_res.status_code} - {upload_res.text}")
    report_id = upload_res.json()["id"]
    print(f"Uploaded report ID: {report_id}")

    client.close()

    # 6. Restart stack (docker compose down, then up)
    print("5. Restarting stack with 'docker compose down' (preserving volumes)...")
    compose_cmd = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.test.yaml"]
    run_cmd(compose_cmd + ["down"])

    print("6. Bringing stack back up with 'docker compose up -d --wait'...")
    run_cmd(compose_cmd + ["up", "-d", "--wait"])

    # 7. Re-check health and re-login
    client2 = httpx.Client(base_url=BASE_URL, follow_redirects=True)
    print("7. Waiting for stack health after restart...")
    wait_for_health(client2)

    print("8. Re-authenticating...")
    login_res2 = client2.post(
        "/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
    )
    if login_res2.status_code != 200:
        raise RuntimeError(f"Login failed after restart: {login_res2.status_code} - {login_res2.text}")

    # 8. Download report and verify byte integrity
    print(f"9. Downloading report {report_id} and verifying bytes...")
    download_res = client2.get(f"/api/reports/{report_id}/download")
    if download_res.status_code != 200:
        raise RuntimeError(f"Download failed: {download_res.status_code} - {download_res.text}")

    downloaded_bytes = download_res.content
    downloaded_hash = hashlib.sha256(downloaded_bytes).hexdigest()
    downloaded_len = len(downloaded_bytes)

    print(f"Uploaded:   length={expected_len}, sha256={expected_hash}")
    print(f"Downloaded: length={downloaded_len}, sha256={downloaded_hash}")

    if downloaded_len != expected_len:
        raise AssertionError(f"Length mismatch: expected {expected_len}, got {downloaded_len}")

    if downloaded_hash != expected_hash:
        raise AssertionError(f"Checksum mismatch: expected {expected_hash}, got {downloaded_hash}")

    client2.close()
    print("[SUCCESS] Report persistence verified across stack restart!")


if __name__ == "__main__":
    main()
