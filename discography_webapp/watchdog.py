#!/usr/bin/env python3
"""
Watchdog for the Discography Downloader web server.

Monitors the server process and port, restarts on crash or hang,
and logs all activity to a dedicated log file.

Uses psutil everywhere to avoid console window flashes from
taskkill/netstat/wmic subprocess calls.

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

try:
    import psutil
except ImportError:
    psutil = None

# ─── Configuration ───────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8000
CHECK_INTERVAL = 15  # seconds between health checks
STARTUP_GRACE = 10  # seconds to wait before first health check
HTTP_TIMEOUT = 5  # seconds for HTTP health check
MEMORY_LIMIT_MB = 500  # restart if server exceeds this RSS (aioslsk leak)

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


# ─── psutil-based helpers (no console window flashes) ────────────


def find_pid_on_port(port: int) -> int | None:
    """Return the PID listening on *port*, or None. Uses psutil only."""
    if psutil:
        try:
            for conn in psutil.net_connections(kind="inet"):
                try:
                    laddr = conn.laddr
                    if (
                        conn.status == "LISTEN"
                        and hasattr(laddr, "port")
                        and laddr.port == port
                    ):
                        pid = conn.pid
                        if pid and psutil.pid_exists(pid):
                            return pid
                except (AttributeError, TypeError):
                    continue
        except Exception:
            pass

    # Fallback: socket check only (no subprocess calls)
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex((HOST, port)) != 0:
                return None
    except Exception:
        return None
    return None


def kill_process(pid: int) -> bool:
    """Force-kill a process by PID using psutil (no console window)."""
    if not psutil:
        # Last resort: os.kill
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return True
        except Exception:
            return False

    try:
        proc = psutil.Process(pid)
        # Try graceful first
        proc.terminate()
        try:
            proc.wait(timeout=3)
            return True
        except psutil.TimeoutExpired:
            pass

        # Force kill
        proc.kill()
        try:
            proc.wait(timeout=3)
            return True
        except psutil.TimeoutExpired:
            pass

        # Still alive? Kill the whole tree
        for child in proc.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        proc.kill()
        return True

    except psutil.NoSuchProcess:
        return True  # Already dead
    except psutil.AccessDenied:
        log.warning(f"Access denied killing PID {pid}, trying os.kill")
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except Exception:
            return False
    except Exception as e:
        log.warning(f"Failed to kill PID {pid}: {e}")
        # Last resort: os.kill with SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
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


def get_process_memory_mb(pid: int) -> float | None:
    """Return RSS memory in MB for a process, or None if unavailable."""
    if not psutil:
        return None
    try:
        proc = psutil.Process(pid)
        return proc.memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


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
        python_exe = VENV_PYTHON
        log.warning(f"system python not found at {system_python}, using venv python")

    log.info(f"Starting server: {python_exe} {' '.join(UVICORN_ARGS)}")

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = venv_site + (";" + existing if existing else "")

    try:
        crash_fh = open(CRASH_LOG, "a", encoding="utf-8")
        crash_fh.write(
            f"\n--- Server start at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
        crash_fh.flush()

        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [python_exe] + UVICORN_ARGS,
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=crash_fh,
            env=env,
            creationflags=flags,
        )
        log.info(f"Server started with PID {proc.pid}")

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


FILLER_LOG = os.path.join(BASE_DIR, "filler_output.log")
FILLER_STALE_SECONDS = 900  # 15 min with no log write = stuck
FILLER_CHECK_INTERVAL = 60  # check filler every 60s


def find_filler_process() -> int | None:
    """Return PID of a running filler_worker.py, or None."""
    if psutil:
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if (
                        "filler_worker" in cmdline
                        and proc.info["name"] == "pythonw.exe"
                    ):
                        return proc.info["pid"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
    return None


def is_filler_log_stale() -> bool:
    """Check if the filler log hasn't been updated in too long."""
    try:
        return time.time() - os.path.getmtime(FILLER_LOG) > FILLER_STALE_SECONDS
    except FileNotFoundError:
        return True


def load_artist_list() -> list[str]:
    """Load artist names from the managed_artists database table."""
    try:
        import sqlite3

        db_path = os.path.join(BASE_DIR, "data", "app.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM managed_artists WHERE user_id=1 ORDER BY name")
        artists = [row[0] for row in cursor.fetchall()]
        conn.close()
        return artists
    except Exception as e:
        log.warning(f"Failed to load artist list from DB: {e}")
        return []


def start_filler() -> bool:
    """Start a filler worker via the server API. Returns True on success or already running."""
    import urllib.request
    import json

    artists = load_artist_list()
    if not artists:
        log.warning("No artists found in database. Cannot start filler.")
        return False

    try:
        req = urllib.request.Request(
            f"http://{HOST}:{PORT}/api/autonomous_fill",
            data=json.dumps(
                {"artist_names": artists, "depth": 1, "dry_run": False}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            log.info(
                f"Filler started: {result.get('message', 'ok')} ({len(artists)} artists)"
            )
            return True
    except urllib.error.HTTPError as e:
        if e.code == 429:
            log.info("Filler API on cooldown. Will retry next check.")
            return True  # Treat as success — filler will start when cooldown expires
        elif e.code == 400:
            log.info("Filler already running (API returned 400).")
            return True
        else:
            log.warning(f"Failed to start filler: {e}")
            return False
    except Exception as e:
        log.warning(f"Failed to start filler: {e}")
        return False


async def run_watchdog(daemon: bool = False):
    """Main watchdog loop."""
    my_pid = os.getpid()
    log.info(f"[PID {my_pid}] Entered run_watchdog")

    server_proc: subprocess.Popen | None = None
    consecutive_failures = 0
    max_consecutive_failures = 5
    backoff = 15
    min_backoff = 15
    max_backoff = 600
    last_restart_time = 0.0
    last_filler_check = 0.0
    filler_consecutive_failures = 0
    max_filler_consecutive_failures = 3

    log.info("--- Watchdog started ---")
    log.info(f"Target: http://{HOST}:{PORT}")
    log.info(f"Check interval: {CHECK_INTERVAL}s | Memory limit: {MEMORY_LIMIT_MB}MB")
    log.info(
        f"Filler check interval: {FILLER_CHECK_INTERVAL}s | Stale threshold: {FILLER_STALE_SECONDS}s"
    )

    while True:
        now = time.time()
        pid = find_pid_on_port(PORT)

        if pid:
            # Check HTTP responsiveness
            alive = is_http_alive(HOST, PORT)

            if alive:
                # Also check memory (aioslsk leak detection)
                mem_mb = get_process_memory_mb(pid)
                if mem_mb and mem_mb > MEMORY_LIMIT_MB:
                    log.warning(
                        f"Server PID {pid} using {mem_mb:.0f}MB (limit {MEMORY_LIMIT_MB}MB). "
                        f"Likely aioslsk leak — restarting preemptively."
                    )
                    kill_process(pid)
                    server_proc = None
                else:
                    consecutive_failures = 0

                    # ── Filler health check (only when server is healthy) ──
                    if now - last_filler_check >= FILLER_CHECK_INTERVAL:
                        last_filler_check = now
                        filler_pid = find_filler_process()
                        if filler_pid:
                            # Filler is running — check if stuck
                            if is_filler_log_stale():
                                log.warning(
                                    f"Filler PID {filler_pid} stuck (no log update in {FILLER_STALE_SECONDS}s). "
                                    f"Killing and restarting."
                                )
                                kill_process(filler_pid)
                                await asyncio.sleep(5)
                                start_filler()
                                filler_consecutive_failures = 0
                            else:
                                filler_consecutive_failures = 0
                        else:
                            # No filler running — start one (if server is up)
                            if filler_consecutive_failures == 0:
                                log.info("No filler process found. Starting filler...")
                            elif filler_consecutive_failures < 3:
                                log.info(
                                    f"Filler not found (attempt {filler_consecutive_failures + 1}). Restarting..."
                                )
                            start_filler()
                            filler_consecutive_failures += 1
                            if (
                                filler_consecutive_failures
                                >= max_filler_consecutive_failures
                            ):
                                filler_consecutive_failures = (
                                    0  # Reset to keep retrying quietly
                                )

                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

            else:
                log.warning(
                    f"Server PID {pid} is listening but not responding HTTP. Restarting..."
                )
                kill_process(pid)
                server_proc = None
        else:
            log.warning("No server process found on port 8000")

        # Restart
        consecutive_failures += 1
        if consecutive_failures > max_consecutive_failures:
            log.error(
                f"Watchdog shutting down: {consecutive_failures} consecutive "
                f"restart failures (limit {max_consecutive_failures})"
            )
            break

        now = time.time()
        if last_restart_time > 0 and (now - last_restart_time) < 120:
            backoff = min(backoff * 2, max_backoff)
        else:
            backoff = min_backoff
        last_restart_time = now

        if backoff > min_backoff:
            log.warning(f"Rapid cycling — backing off {backoff}s before restart")

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

            if not is_http_alive(HOST, PORT):
                log.warning(
                    "Server started but not responding yet — will retry next cycle"
                )
            else:
                log.info("Server is healthy and responding")
                consecutive_failures = 0
        else:
            log.error("Server failed to start, retrying in 30s...")
            await asyncio.sleep(30)

        await asyncio.sleep(CHECK_INTERVAL)

    if server_proc and server_proc.returncode is None:
        try:
            kill_process(server_proc.pid)
        except Exception:
            pass

    log.info("--- Watchdog stopped ---")


# ─── Entry Point ─────────────────────────────────────────────────


def _lock_with_pid() -> bool:
    """Atomically claim the watchdog lock via PID file."""
    my_pid = os.getpid()
    wpid_file = os.path.join(BASE_DIR, WATCHDOG_PID_FILE)

    try:
        if os.path.exists(wpid_file):
            with open(wpid_file) as f:
                existing_pid = int(f.read().strip())
            try:
                if psutil:
                    if psutil.pid_exists(existing_pid):
                        log.warning(
                            f"Another watchdog running (PID {existing_pid}). Exiting."
                        )
                        return False
                else:
                    os.kill(existing_pid, 0)
                    log.warning(
                        f"Another watchdog running (PID {existing_pid}). Exiting."
                    )
                    return False
            except (OSError, ValueError):
                log.info(f"Stale PID file ({existing_pid}), overwriting.")

        with open(wpid_file, "w") as f:
            f.write(str(my_pid))
        return True
    except Exception as e:
        log.warning(f"Lock error: {e}, proceeding anyway")
        return True


def main():
    parser = argparse.ArgumentParser(description="Discography Downloader Watchdog")
    parser.add_argument("--daemon", action="store_true", help="Start in daemon mode")
    args = parser.parse_args()

    os.chdir(BASE_DIR)

    if not _lock_with_pid():
        return

    try:
        asyncio.run(run_watchdog(daemon=args.daemon))
    except KeyboardInterrupt:
        log.info("Watchdog interrupted by user")
        pid = find_pid_on_port(PORT)
        if pid:
            log.info(f"Shutting down server PID {pid}")
            kill_process(pid)


if __name__ == "__main__":
    main()
