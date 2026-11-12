"""Test deployment and rollback workflow for Docker Compose (Issue #15).

Steps:
1. Build frontend image with VITE_APP_VERSION=v1.0.0-test (tag v1-test).
2. Build frontend image with VITE_APP_VERSION=v2.0.0-test (tag v2-test).
3. Build backend image (tag v1-test and v2-test).
4. Deploy v1-test using compose.prod.yaml with IMAGE_TAG=v1-test.
5. Verify application is healthy and UI serves version v1.0.0-test.
6. Deploy v2-test using compose.prod.yaml with IMAGE_TAG=v2-test.
7. Verify application is healthy and UI serves version v2.0.0-test.
8. Perform rollback: redeploy v1-test using compose.prod.yaml with IMAGE_TAG=v1-test.
9. Verify application is healthy and UI serves version v1.0.0-test.
10. Clean up test containers and network with docker compose -f compose.prod.yaml down.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

FRONTEND_PORT = os.getenv("FRONTEND_PORT", "3000")
BASE_URL = os.getenv("BASE_URL", f"http://127.0.0.1:{FRONTEND_PORT}")
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cmd(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print(f"Running: {' '.join(cmd)}")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=full_env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"STDOUT:\n{result.stdout}", file=sys.stderr)
        print(f"STDERR:\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed with code {result.returncode}: {' '.join(cmd)}")


def wait_for_health(timeout_sec: int = 60) -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=3.0)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            res = client.get("/api/health")
            if res.status_code == 200 and res.json().get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Application at {BASE_URL}/api/health did not become healthy in {timeout_sec}s")


def fetch_ui_version() -> str:
    client = httpx.Client(base_url=BASE_URL, timeout=5.0)
    res = client.get("/")
    if res.status_code != 200:
        raise RuntimeError(f"Failed to fetch index.html from {BASE_URL}: status {res.status_code}")

    html = res.text
    # Find script bundle in index.html
    import re
    scripts = re.findall(r'src="(/assets/[^"]+\.js)"', html)
    for script_path in scripts:
        js_res = client.get(script_path)
        if js_res.status_code == 200:
            match = re.search(r'v[0-9]+\.[0-9]+\.[0-9]+-test', js_res.text)
            if match:
                return match.group(0)
    raise RuntimeError(f"Could not locate version string in frontend bundles from {BASE_URL}")


def main() -> None:
    print(f"--- Rollback Verification Test on {BASE_URL} ---")

    try:
        # 1. Build backend image for test
        print("\n[Step 1/7] Building backend image tag v1-test...")
        run_cmd([
            "docker", "build",
            "-t", "ghcr.io/kushagrapan/metal-ops-backend:v1-test",
            "-t", "ghcr.io/kushagrapan/metal-ops-backend:v2-test",
            ".",
        ])

        # 2. Build frontend image v1-test
        print("\n[Step 2/7] Building frontend image with VITE_APP_VERSION=v1.0.0-test...")
        run_cmd([
            "docker", "build",
            "--build-arg", "VITE_APP_VERSION=v1.0.0-test",
            "-t", "ghcr.io/kushagrapan/metal-ops-frontend:v1-test",
            "frontend",
        ])

        # 3. Build frontend image v2-test
        print("\n[Step 3/7] Building frontend image with VITE_APP_VERSION=v2.0.0-test...")
        run_cmd([
            "docker", "build",
            "--build-arg", "VITE_APP_VERSION=v2.0.0-test",
            "-t", "ghcr.io/kushagrapan/metal-ops-frontend:v2-test",
            "frontend",
        ])

        # 4. Deploy v1-test
        print("\n[Step 4/7] Deploying initial release v1-test...")
        run_cmd(
            ["docker", "compose", "-f", "compose.prod.yaml", "up", "-d", "--wait"],
            env={"IMAGE_TAG": "v1-test", "FRONTEND_PORT": FRONTEND_PORT},
        )
        wait_for_health()
        version_v1 = fetch_ui_version()
        print(f"Verified initial deployed version in UI: {version_v1}")
        assert version_v1 == "v1.0.0-test", f"Expected v1.0.0-test, got {version_v1}"

        # 5. Deploy v2-test
        print("\n[Step 5/7] Deploying new release v2-test...")
        run_cmd(
            ["docker", "compose", "-f", "compose.prod.yaml", "up", "-d", "--wait"],
            env={"IMAGE_TAG": "v2-test", "FRONTEND_PORT": FRONTEND_PORT},
        )
        wait_for_health()
        version_v2 = fetch_ui_version()
        print(f"Verified upgraded deployed version in UI: {version_v2}")
        assert version_v2 == "v2.0.0-test", f"Expected v2.0.0-test, got {version_v2}"

        # 6. Execute Rollback to v1-test
        print("\n[Step 6/7] Executing rollback to previous tag v1-test...")
        run_cmd(
            ["docker", "compose", "-f", "compose.prod.yaml", "up", "-d", "--wait"],
            env={"IMAGE_TAG": "v1-test", "FRONTEND_PORT": FRONTEND_PORT},
        )
        wait_for_health()
        version_restored = fetch_ui_version()
        print(f"Verified restored version in UI after rollback: {version_restored}")
        assert version_restored == "v1.0.0-test", f"Expected rollback to v1.0.0-test, got {version_restored}"

        print("\n[Step 7/7] Rollback test PASSED successfully.")

    finally:
        print("\nTearing down test stack...")
        run_cmd(["docker", "compose", "-f", "compose.prod.yaml", "down"])


if __name__ == "__main__":
    main()

