"""
System tray icon for the Discography Downloader.
- Windows: shows star icon in system tray with activity/event log
- Linux/headless: runs as a background monitor without UI
"""

import argparse
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque

HOST = "http://127.0.0.1:8000"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Activity & event log (thread-safe) ──────────────────────────

_events = deque(maxlen=50)  # Recent internal events
_activity_lock = threading.Lock()


def log_event(msg: str):
    ts = time.strftime("%H:%M:%S")
    with _activity_lock:
        _events.appendleft(f"[{ts}] {msg}")


# Network activity counters
_tx_count = 0  # Requests sent
_rx_count = 0  # Responses received
_activity_lock2 = threading.Lock()


def record_tx():
    global _tx_count
    with _activity_lock2:
        _tx_count += 1


def record_rx():
    global _rx_count
    with _activity_lock2:
        _rx_count += 1


# ── Health polling ───────────────────────────────────────────────

_server_status = "unknown"
_status_lock = threading.Lock()


def _check_health():
    global _server_status
    try:
        req = urllib.request.Request(f"{HOST}/", method="GET")
        record_tx()
        with urllib.request.urlopen(req, timeout=5) as resp:
            record_rx()
            if resp.status == 200:
                with _status_lock:
                    _server_status = "healthy"
            else:
                with _status_lock:
                    _server_status = "degraded"
                log_event(f"Server degraded: HTTP {resp.status}")
    except Exception as e:
        with _status_lock:
            _server_status = "down"
        log_event(f"Server down: {e}")


def _poll_loop(interval=10):
    while True:
        _check_health()
        time.sleep(interval)


# ── Activity poll from API ──────────────────────────────────────


def _poll_activity(interval=5):
    """Fetch the API status and log filler/queue changes."""
    last_completed = []
    while True:
        try:
            req = urllib.request.Request(f"{HOST}/api/status", method="GET")
            record_tx()
            with urllib.request.urlopen(req, timeout=5) as resp:
                record_rx()
                import json

                data = json.loads(resp.read().decode())
                fs = data.get("filler_status")
                if fs and fs.get("running"):
                    log_event(
                        f"Filler: {fs.get('status', 'running')} ({fs.get('artists', '?')} artists)"
                    )
                completed = data.get("completed_albums", [])
                if len(completed) > len(last_completed):
                    new_ones = completed[len(last_completed) :]
                    for a in new_ones:
                        log_event(
                            f"Completed: {a['artist']} - {a['album']} ({a['status']})"
                        )
                last_completed = completed
        except Exception:
            pass
        time.sleep(interval)


# ── Menu actions ─────────────────────────────────────────────────


def _open_ui(icon):
    webbrowser.open(HOST)
    log_event("Opened web UI in browser")


def _restart(icon):
    log_event("Restart request sent to server")
    try:
        req = urllib.request.Request(f"{HOST}/api/stop", method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        log_event(f"Restart failed: {e}")


def _exit_app(icon):
    log_event("Systray exiting")
    icon.stop()
    os._exit(0)


# ── Windows tray icon ────────────────────────────────────────────


def _make_icon(color, size=64):
    import math
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    outer = size // 2 - 2
    inner = outer // 2
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        angle = math.radians(-90 + i * 36)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=(*color, 255))
    return img


_COLORS = {
    "healthy": (34, 197, 94),
    "degraded": (234, 179, 8),
    "down": (239, 68, 68),
    "unknown": (156, 163, 175),
}


def run_tray():
    from pystray import Icon, MenuItem, Menu

    poller = threading.Thread(target=_poll_loop, daemon=True)
    poller.start()
    activity_poller = threading.Thread(target=_poll_activity, daemon=True)
    activity_poller.start()

    def _build_menu():
        with _status_lock:
            status = _server_status
        with _activity_lock2:
            tx = _tx_count
            rx = _rx_count
        with _activity_lock:
            recent = list(_events)[:8]

        items = [
            MenuItem(f"Server: {status}", None, enabled=False),
            MenuItem(f"TX: {tx}  RX: {rx}", None, enabled=False),
            Menu.SEPARATOR,
        ]
        # Show up to 8 recent events
        for evt in recent:
            items.append(MenuItem(evt[:45], None, enabled=False))
        if recent:
            items.append(Menu.SEPARATOR)
        items.append(MenuItem("🌐 Open Web UI", _open_ui, default=True))
        items.append(MenuItem("🔄 Restart Server", _restart))
        items.append(Menu.SEPARATOR)
        items.append(MenuItem("❌ Exit", _exit_app))
        return Menu(*items)

    icon = Icon(
        "discography-downloader",
        _make_icon(_COLORS.get(_server_status, _COLORS["unknown"])),
        title="Discography Downloader",
        menu=_build_menu(),
    )

    # Icon color updater thread
    def _update_icon_thread():
        while icon._running:
            with _status_lock:
                color = _COLORS.get(_server_status, _COLORS["unknown"])
            icon.icon = _make_icon(color)
            icon._update_icon()
            time.sleep(10)

    updater = threading.Thread(target=_update_icon_thread, daemon=True)
    updater.start()

    log_event("Systray started")
    icon.run()


# ── Headless mode (Linux / CI) ──────────────────────────────────


def run_headless():
    """Monitor without a tray icon — suitable for headless/Linux."""
    print("[systray] Headless mode — monitoring server health")
    poller = threading.Thread(target=_poll_loop, daemon=True)
    poller.start()
    activity_poller = threading.Thread(target=_poll_activity, daemon=True)
    activity_poller.start()

    try:
        while True:
            time.sleep(60)
            with _status_lock:
                s = _server_status
            with _activity_lock:
                ev = list(_events)[:3] if _events else ["(no events)"]
            print(f"[systray] Status: {s} | Recent: {'; '.join(ev)}")
    except KeyboardInterrupt:
        print("[systray] Shutting down")


# ── Entry point ─────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Discography Downloader Systray")
    parser.add_argument(
        "--headless", action="store_true", help="Run without GUI (Linux/CI)"
    )
    args = parser.parse_args()

    if args.headless or sys.platform != "win32":
        run_headless()
    else:
        try:
            run_tray()
        except ImportError:
            print("[systray] pystray/PIL not available — falling back to headless mode")
            run_headless()


if __name__ == "__main__":
    main()
