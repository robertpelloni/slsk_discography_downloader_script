#!/usr/bin/env python3
"""
Watchdog for the Discography Downloader web server.

Monitors the server process and port, restarts on crash or hang,
and logs all activity to a dedicated log file.

Usage:
    python watchdog.py              # Run in foreground
    python watchdog.py --daemon     # Detach (notify user to background manually)
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

# ─── Configuration ───────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8000
CHECK_INTERVAL = 15  # seconds between health checks
STARTUP_GRACE = 10  # seconds to wait before first health check
HTTP_TIMEOUT = 5  # seconds for HTTP health check

PID_FILE = "server.pid"
WATCHDOG_PID_FILE = "watchdog.pid"
LOG_FILE = "watchdog.log"

# Resolve paths relative to this script's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
UVICORN_ARGS = [
    "-m",
    "uvicorn",
    "main:app",
    "--host",
    HOST,
    "--port",
    str(PORT),
    "--log-level",
    "info",
]

# ─── Logging Setup ───────────────────────────────────────────────

# Ensure sys.stdout is safe for pythonw.exe (can be None)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

log_path = os.path.join(BASE_DIR, LOG_FILE)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_path, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")


# ─── Platform-aware helpers ──────────────────────────────────────


def find_pid_on_port(port: int) -> int | None:
    """Return the PID listening on *port*, or None."""
    try:
        import psutil

        for conn in psutil.net_connections(kind="inet"):
            try:
                laddr = conn.laddr
                # type ignore below: psutil laddr may be a tuple in older versions
                if (
                    conn.status == "LISTEN"
                    and hasattr(laddr, "port")
                    and laddr.port == port
                ):  # type: ignore[union-attr]
                    pid = conn.pid
                    # Verify the process still exists
                    if pid and psutil.pid_exists(pid):
                        return pid
            except (AttributeError, TypeError):
                continue
    except ImportError:
        pass

    # Fallback: netstat
    try:
        import subprocess

        cmd = ["netstat", "-ano"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid_str = parts[-1]
                    if pid_str.isdigit():
                        return int(pid_str)
    except Exception:
        pass

    return None


def kill_process(pid: int) -> bool:
    """Force-kill a process by PID. Returns True on success."""
    try:
        # Try graceful first
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)

        # Verify it's gone
        try:
            import psutil

            if psutil.pid_exists(pid):
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                else:
                    os.kill(pid, signal.SIGKILL)
                time.sleep(1)
        except ImportError:
            # Fallback: taskkill
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        return True
    except ProcessLookupError:
        return True  # Already dead
    except Exception as e:
        log.warning(f"Failed to kill PID {pid}: {e}")
        # Last resort on Windows: wmic to force-terminate
        try:
            subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "delete"],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except Exception:
            pass
        return False


def is_http_alive(host: str, port: int, timeout: int = HTTP_TIMEOUT) -> bool:
    """Check if the server responds to HTTP GET."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(f"http://{host}:{port}/", method="GET")
        req.add_header("User-Agent", "watchdog/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
        return False


CRASH_LOG = os.path.join(BASE_DIR, "server_crash.log")


def start_server() -> subprocess.Popen | None:
    """Start the uvicorn server process. Returns the Popen object or None.

    Uses the system Python (C:\Python314) to avoid the venv Python 3.14.6
    stub-process bug which creates a duplicate child process for every spawn.
    The venv's site-packages are added via PYTHONPATH so all project
    dependencies (fastapi, aioslsk, etc.) are available.
    """
    system_python = "C:\\Python314\\python.exe"
    venv_site = os.path.join(BASE_DIR, "venv", "Lib", "site-packages")
    python_exe = system_python

    if not os.path.isfile(python_exe):
        # Fallback to venv Python
        python_exe = VENV_PYTHON
        log.warning(f"system python not found at {system_python}, using venv python")

    log.info(f"Starting server: {python_exe} {' '.join(UVICORN_ARGS)}")

    # Build environment: inherit current + PYTHONPATH pointing to venv site-packages
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = venv_site + (";" + existing if existing else "")

    try:
        crash_fh = open(CRASH_LOG, "a", encoding="utf-8")
        crash_fh.write(
            f"\n--- Server start at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
        crash_fh.flush()

        proc = subprocess.Popen(
            [python_exe] + UVICORN_ARGS,
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=crash_fh,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32"
            else 0,
        )
        # Don't close the handle — keep it open for the process to write to
        log.info(f"Server started with PID {proc.pid}")

        # Write PID file for external management
        pid_file = os.path.join(BASE_DIR, PID_FILE)
        try:
            with open(pid_file, "w") as f:
                f.write(str(proc.pid))
        except Exception as e:
            log.warning(f"Could not write PID file: {e}")

        return proc
    except Exception as e:
        log.error(f"Failed to start server: {e}")
        return None


# ─── Watchdog Core ───────────────────────────────────────────────


async def run_watchdog(daemon: bool = False):
    """Main watchdog loop."""
    import os as _os

    log.info(
        f"[PID {_os.getpid()} PPID {_os.getppid() if hasattr(_os, 'getppid') else 'N/A'}] Entered run_watchdog"
    )
    server_proc: subprocess.Popen | None = None
    consecutive_failures = 0
    max_consecutive_failures = 5
    backoff = 15  # seconds, doubles on rapid cycling
    min_backoff = 15
    max_backoff = 600  # 10 minutes
    last_restart_time = 0.0

    if daemon:
        log.info("--- Watchdog started (daemon mode) ---")
    else:
        log.info("--- Watchdog started (foreground) ---")

    log.info(f"Target: http://{HOST}:{PORT}")
    log.info(f"Check interval: {CHECK_INTERVAL}s | Startup grace: {STARTUP_GRACE}s")

    while True:
        # ── Step 1: Is the process alive? ──
        pid = find_pid_on_port(PORT)

        if pid:
            # ── Step 2: Is it responding? ──
            alive = is_http_alive(HOST, PORT)

            if alive:
                consecutive_failures = 0
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # Port is bound but HTTP is dead — hang
            log.warning(
                f"Server PID {pid} is listening but not responding HTTP. Restarting..."
            )
            kill_process(pid)
            server_proc = None
        else:
            log.warning("No server process found on port 8000")

        # ── Step 3: Restart ──
        consecutive_failures += 1
        if consecutive_failures > max_consecutive_failures:
            log.error(
                f"Watchdog shutting down: {consecutive_failures} consecutive "
                f"restart failures (limit {max_consecutive_failures})"
            )
            break

        # Exponential backoff if restarts are too frequent
        now = time.time()
        if last_restart_time > 0 and (now - last_restart_time) < 120:
            backoff = min(backoff * 2, max_backoff)
        else:
            backoff = min_backoff  # Reset if it's been stable for a while
        last_restart_time = now

        if backoff > min_backoff:
            log.warning(
                f"Rapid cycling detected — backing off {backoff}s before restart"
            )

        # Clean up any orphaned PIDs
        if server_proc and server_proc.returncode is None:
            try:
                kill_process(server_proc.pid)
            except Exception:
                pass

        await asyncio.sleep(backoff)
        server_proc = start_server()

        if server_proc:
            log.info(f"Waiting {STARTUP_GRACE}s for startup...")
            await asyncio.sleep(STARTUP_GRACE)

            # Verify it actually started
            if not is_http_alive(HOST, PORT):
                log.warning(
                    "Server started but not responding yet — will retry on next cycle"
                )
            else:
                log.info("Server is healthy and responding")
                consecutive_failures = 0
        else:
            log.error("Server failed to start, retrying in 30s...")
            await asyncio.sleep(30)

        await asyncio.sleep(CHECK_INTERVAL)

    # Cleanup on shutdown
    if server_proc and server_proc.returncode is None:
        try:
            kill_process(server_proc.pid)
        except Exception:
            pass

    log.info("--- Watchdog stopped ---")


# ─── Entry Point ─────────────────────────────────────────────────


def _lock_with_pid() -> bool:
    """Atomically claim the watchdog lock via PID file + Windows mutex.
    Returns True if we own the lock, False if another instance owns it."""
    my_pid = os.getpid()
    wpid_file = os.path.join(BASE_DIR, WATCHDOG_PID_FILE)
    log.info(f"[_lock_with_pid PID={my_pid}] Acquiring lock...")

    # PID file check first
    try:
        if os.path.exists(wpid_file):
            with open(wpid_file) as f:
                existing_pid = int(f.read().strip())
            try:
                os.kill(existing_pid, 0)
                log.warning(
                    f"[_lock_with_pid PID={my_pid}] Another watchdog is running (PID {existing_pid}). Exiting."
                )
                return False
            except (OSError, ValueError):
                log.info(
                    f"[_lock_with_pid PID={my_pid}] Stale PID file ({existing_pid}), will overwrite."
                )

        with open(wpid_file, "w") as f:
            f.write(str(my_pid))
        log.info(f"[_lock_with_pid PID={my_pid}] Lock acquired.")
        return True
    except Exception as e:
        log.warning(f"[_lock_with_pid PID={my_pid}] Lock error: {e}, proceeding anyway")
        return True


def main():
    parser = argparse.ArgumentParser(description="Discography Downloader Watchdog")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start in daemon mode (background yourself)",
    )
    args = parser.parse_args()

    # Make sure we're in the correct directory
    os.chdir(BASE_DIR)

    # ── Single-instance lock ──
    if not _lock_with_pid():
        return

    try:
        asyncio.run(run_watchdog(daemon=args.daemon))
    except KeyboardInterrupt:
        log.info("Watchdog interrupted by user")
        # Cleanup
        pid = find_pid_on_port(PORT)
        if pid:
            log.info(f"Shutting down server PID {pid}")
            kill_process(pid)


if __name__ == "__main__":
    main()
