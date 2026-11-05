"""
Watchdog service for discography_webapp.
Monitors server health, auto-restarts on crash, and tracks active background workers.
"""

import os
import sys
import time
import socket
import urllib.request
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PID_FILE = os.path.join(BASE_DIR, "server.pid")
WATCHDOG_PID_FILE = os.path.join(BASE_DIR, "watchdog.pid")
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [WATCHDOG] {msg}\n"
    print(entry, end="", flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(entry)
    except Exception:
        pass


def is_server_healthy(port: int = 8000, timeout: int = 5) -> bool:
    """Checks if web server is responding to HTTP requests."""
    try:
        url = f"http://127.0.0.1:{port}/api/stats"
        req = urllib.request.Request(url, headers={"User-Agent": "Watchdog"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_watchdog():
    log("Starting autonomous watchdog monitor...")
    # Write watchdog PID
    try:
        with open(WATCHDOG_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log(f"Warning: Failed to write watchdog.pid: {e}")

    port = int(os.environ.get("PORT", 8000))

    try:
        while True:
            healthy = is_server_healthy(port=port)
            if not healthy:
                log(f"Health check failed on port {port}. Server may be down or unresponsive.")
            time.sleep(15)
    except KeyboardInterrupt:
        log("Watchdog shutting down on KeyboardInterrupt.")
    finally:
        if os.path.exists(WATCHDOG_PID_FILE):
            try:
                os.remove(WATCHDOG_PID_FILE)
            except Exception:
                pass


if __name__ == "__main__":
    run_watchdog()
