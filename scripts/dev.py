"""Run the API and the frontend together for local development.

Used by `make dev`. Works on Windows and POSIX. Ctrl+C stops both processes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"


def venv_python() -> Path:
    binary = "Scripts/python.exe" if IS_WINDOWS else "bin/python"
    return ROOT / ".venv" / binary


def start_api() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            str(venv_python()),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
    )


def start_frontend() -> subprocess.Popen[bytes]:
    if IS_WINDOWS:
        # npm is a .cmd shim, so it needs a command interpreter.
        command = ["cmd.exe", "/c", "npm.cmd", "run", "dev"]
    else:
        command = ["npm", "run", "dev"]
    return subprocess.Popen(command, cwd=ROOT / "frontend")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if IS_WINDOWS:
        # Kill the tree: uvicorn's reloader and Vite both spawn children.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    print("API      http://127.0.0.1:8000/api/health")
    print("Frontend http://127.0.0.1:5173")
    print("Ctrl+C to stop both.")

    processes = [start_api(), start_frontend()]
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            stop(process)

    return 0


if __name__ == "__main__":
    sys.exit(main())
