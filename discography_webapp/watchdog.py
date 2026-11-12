#!/usr/bin/env python3
"""
Unified Watchdog service for discography_webapp (reconciled v2.3.0).

Combines:
- Multi-attempt HTTP health check retry tolerance (`is_server_healthy`) for transient network disruptions.
- `psutil`-based process inspection & termination (zero console window flashes on Windows).
- 500 MB RSS memory-leak restart protection (`aioslsk` long-uptime mitigation).
- Exponential restart backoff, crash stderr capture (`server_crash.log`), and PID lockfile.
- Optional `--with-filler` autonomous filler monitoring (loads all managed artists from SQLite
  `data/app.db`, detects 15-minute stale logs, and handles HTTP 429 cooldowns gracefully).

Usage:
    python watchdog.py                  # Monitor & auto-recover web server only
    python watchdog.py --with-filler    # Also monitor & auto-restart autonomous filler worker
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    import psutil
except ImportError:
    psutil = None

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", 8000))
CHECK_INTERVAL = 15
STARTUP_GRACE = 10
HTTP_TIMEOUT = 5
MEMORY_LIMIT_MB = 500

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PID_FILE = os.path.join(BASE_DIR, "server.pid")
WATCHDOG_PID_FILE = os.path.join(BASE_DIR, "watchdog.pid")
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")
CRASH_LOG = os.path.join(BASE_DIR, "server_crash.log")
FILLER_LOG = os.path.join(BASE_DIR, "filler_output.log")
FILLER_STALE_SECONDS = 900
FILLER_CHECK_INTERVAL = 60

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

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("watchdog")


def log(msg: str):
    """Backwards-compatible logging helper."""
    logger.info(msg)


def is_server_healthy(port: int = 8000, timeout: int = 5, retries: int = 2) -> bool:
    """Check if web server responds to HTTP requests with retry tolerance for transient disruptions."""
    urls = [f"http://{HOST}:{port}/api/health", f"http://{HOST}:{port}/"]
    for attempt in range(retries + 1):
        for url in urls:
            req = urllib.request.Request(url, headers={"User-Agent": "Watchdog/2.3"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
                continue
            except Exception:
                break
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    return False


def is_http_alive(host: str = HOST, port: int = PORT, timeout: int = HTTP_TIMEOUT) -> bool:
    """Alias for HTTP health check with retry tolerance."""
    return is_server_healthy(port=port, timeout=timeout, retries=1)


def find_pid_on_port(port: int) -> int | None:
    """Return the PID listening on *port*, or None. Uses psutil to avoid console flashes."""
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
    return None


def kill_process(pid: int) -> bool:
    """Gracefully terminate then force-kill a process tree via psutil."""
    if not psutil:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=3)
            return True
        except psutil.TimeoutExpired:
            pass

        for child in proc.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        proc.kill()
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception as e:
        logger.warning(f"Failed to kill PID {pid}: {e}")
        return False


def get_process_memory_mb(pid: int) -> float | None:
    if not psutil:
        return None
    try:
        return psutil.Process(pid).memory_info().rss / (1024 * 1024)
    except Exception:
        return None


def start_server(port: int = PORT) -> subprocess.Popen | None:
    """Start the uvicorn server process, preferring system Python 3.14 on Windows to avoid venv stub duplicates."""
    system_python = r"C:\Python314\python.exe"
    venv_site = os.path.join(BASE_DIR, "venv", "Lib", "site-packages")
    if sys.platform == "win32" and os.path.isfile(system_python):
        python_exe = system_python
    elif os.path.isfile(VENV_PYTHON):
        python_exe = VENV_PYTHON
    else:
        python_exe = sys.executable

    args = [
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        HOST,
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    logger.info(f"Starting server: {python_exe} {' '.join(args)}")

    env = os.environ.copy()
    sep = ";" if sys.platform == "win32" else ":"
    extra_paths = [BASE_DIR, os.path.dirname(BASE_DIR)]
    if os.path.isdir(venv_site):
        extra_paths.insert(0, venv_site)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = sep.join(extra_paths + ([existing] if existing else []))

    try:
        crash_fh = open(CRASH_LOG, "a", encoding="utf-8")
        crash_fh.write(f"\n--- Server start at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        crash_fh.flush()

        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [python_exe] + args,
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=crash_fh,
            env=env,
            creationflags=flags,
        )
        with open(SERVER_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
        logger.info(f"Server started with PID {proc.pid}")
        return proc
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return None


def find_filler_process() -> int | None:
    if not psutil:
        return None
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "filler_worker" in cmdline:
                    return proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return None


def is_filler_log_stale() -> bool:
    try:
        return time.time() - os.path.getmtime(FILLER_LOG) > FILLER_STALE_SECONDS
    except FileNotFoundError:
        return True


def load_artist_list() -> list[str]:
    """Load managed artist names from SQLite database."""
    try:
        db_path = os.path.join(BASE_DIR, "data", "app.db")
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM managed_artists WHERE user_id=1 ORDER BY name")
        artists = [row[0] for row in cursor.fetchall()]
        conn.close()
        return artists
    except Exception as e:
        logger.warning(f"Failed to load artist list from DB: {e}")
        return []


def start_filler(port: int = PORT) -> bool:
    artists = load_artist_list()
    if not artists:
        logger.warning("No artists found in database. Cannot start filler.")
        return False
    try:
        req = urllib.request.Request(
            f"http://{HOST}:{port}/api/autonomous_fill",
            data=json.dumps({"artist_names": artists, "depth": 1, "dry_run": False}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            logger.info(f"Filler started: {result.get('message', 'ok')} ({len(artists)} artists)")
            return True
    except urllib.error.HTTPError as e:
        if e.code in (400, 429):
            logger.info(f"Filler API returned HTTP {e.code} (already running or cooldown).")
            return True
        logger.warning(f"Failed to start filler: {e}")
        return False
    except Exception as e:
        logger.warning(f"Failed to start filler: {e}")
        return False


async def run_watchdog_async(with_filler: bool = False, port: int = PORT):
    logger.info(
        f"Starting watchdog monitor on http://{HOST}:{port} "
        f"(memory limit={MEMORY_LIMIT_MB}MB, with_filler={with_filler})"
    )
    server_proc: subprocess.Popen | None = None
    consecutive_failures = 0
    max_consecutive_failures = 5
    backoff = 15
    min_backoff = 15
    max_backoff = 600
    last_restart_time = 0.0
    last_filler_check = 0.0

    while True:
        now = time.time()
        pid = find_pid_on_port(port)
        healthy = is_server_healthy(port=port)

        if healthy:
            consecutive_failures = 0
            if pid:
                mem_mb = get_process_memory_mb(pid)
                if mem_mb and mem_mb > MEMORY_LIMIT_MB:
                    logger.warning(
                        f"Server PID {pid} using {mem_mb:.0f}MB (limit {MEMORY_LIMIT_MB}MB). "
                        "Restarting preemptively..."
                    )
                    kill_process(pid)
                    server_proc = None
                else:
                    if with_filler and (now - last_filler_check >= FILLER_CHECK_INTERVAL):
                        last_filler_check = now
                        filler_pid = find_filler_process()
                        if filler_pid and is_filler_log_stale():
                            logger.warning(f"Filler PID {filler_pid} stale; restarting...")
                            kill_process(filler_pid)
                            await asyncio.sleep(5)
                            start_filler(port=port)
                        elif not filler_pid:
                            start_filler(port=port)
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue
            else:
                await asyncio.sleep(CHECK_INTERVAL)
                continue
        elif pid:
            logger.warning(f"Server PID {pid} listening on {port} but unresponsive; killing...")
            kill_process(pid)
            server_proc = None

        consecutive_failures += 1
        if consecutive_failures > max_consecutive_failures:
            logger.error(
                f"Watchdog stopping after {consecutive_failures} consecutive recovery failures."
            )
            break

        if last_restart_time > 0 and (now - last_restart_time) < 120:
            backoff = min(backoff * 2, max_backoff)
        else:
            backoff = min_backoff
        last_restart_time = now

        if server_proc and server_proc.returncode is None:
            kill_process(server_proc.pid)

        await asyncio.sleep(backoff)
        server_proc = start_server(port=port)
        if server_proc:
            await asyncio.sleep(STARTUP_GRACE)
            if is_server_healthy(port=port):
                logger.info("Server recovered and responding HTTP 200.")
                consecutive_failures = 0

        await asyncio.sleep(CHECK_INTERVAL)


def _lock_with_pid() -> bool:
    my_pid = os.getpid()
    try:
        if os.path.exists(WATCHDOG_PID_FILE):
            with open(WATCHDOG_PID_FILE, encoding="utf-8") as f:
                existing_pid = int(f.read().strip())
            if psutil and psutil.pid_exists(existing_pid):
                logger.warning(f"Another watchdog is already running (PID {existing_pid}).")
                return False
        with open(WATCHDOG_PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(my_pid))
        return True
    except Exception:
        return True


def run_watchdog(with_filler: bool = False):
    """Synchronous entry point for launching the watchdog monitor."""
    if not _lock_with_pid():
        return
    try:
        asyncio.run(run_watchdog_async(with_filler=with_filler, port=PORT))
    except KeyboardInterrupt:
        logger.info("Watchdog shutting down on KeyboardInterrupt.")
    finally:
        if os.path.exists(WATCHDOG_PID_FILE):
            try:
                os.remove(WATCHDOG_PID_FILE)
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Discography Downloader Watchdog")
    parser.add_argument("--daemon", action="store_true", help="Compatibility flag for daemon launch")
    parser.add_argument(
        "--with-filler",
        action="store_true",
        help="Monitor and auto-restart autonomous filler worker in addition to web server",
    )
    args = parser.parse_args()
    os.chdir(BASE_DIR)
    run_watchdog(with_filler=args.with_filler)


if __name__ == "__main__":
    main()
