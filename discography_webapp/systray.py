"""
System tray icon for the Discography Downloader.
Shows server status, allows opening the web UI and restarting/stopping.

Run alongside the watchdog:  pythonw.exe systray.py
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser

HOST = "http://127.0.0.1:8000"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import pystray
    from pystray import Icon, MenuItem, Menu
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing pystray or PIL.  Install with:  pip install pystray pillow")
    sys.exit(1)

# ── Icon generation ──────────────────────────────────────────────

_COLORS = {
    "healthy": (34, 197, 94),  # green
    "degraded": (234, 179, 8),  # amber
    "down": (239, 68, 68),  # red
    "unknown": (156, 163, 175),  # gray
}


def _make_icon(color, size=64):
    """Create a 64×64 RGBA icon with a centered 5-pointed star."""
    import math

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


# ── Health polling ───────────────────────────────────────────────

_server_status = "unknown"  # healthy / degraded / down / unknown
_status_lock = threading.Lock()


def _check_health():
    global _server_status
    try:
        req = urllib.request.Request(f"{HOST}/", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                with _status_lock:
                    _server_status = "healthy"
            else:
                with _status_lock:
                    _server_status = "degraded"
    except Exception:
        with _status_lock:
            _server_status = "down"


def _poll_loop(interval=10):
    while True:
        _check_health()
        time.sleep(interval)


# ── Menu actions ─────────────────────────────────────────────────


def _open_ui(icon):
    webbrowser.open(HOST)


def _restart(icon):
    """Kill server process — watchdog will restart it."""
    try:
        req = urllib.request.Request(f"{HOST}/api/stop", method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _exit_app(icon):
    icon.stop()
    os._exit(0)


# ── Main ─────────────────────────────────────────────────────────


def _menu() -> Menu:
    with _status_lock:
        status = _server_status
    return Menu(
        MenuItem(f"Server: {status}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("🌐 Open Web UI", _open_ui, default=True),
        MenuItem("🔄 Restart Server", _restart),
        Menu.SEPARATOR,
        MenuItem("❌ Exit", _exit_app),
    )


def _update_icon(icon: Icon):
    """Polling thread updates the icon image based on health."""
    while icon._running:
        with _status_lock:
            color = _COLORS.get(_server_status, _COLORS["unknown"])
        icon.icon = _make_icon(color)
        icon._update_icon()
        time.sleep(10)


def main():
    poller = threading.Thread(target=_poll_loop, daemon=True)
    poller.start()

    icon = Icon(
        "discography-downloader",
        _make_icon(_COLORS["unknown"]),
        title="Discography Downloader",
        menu=_menu(),
    )

    updater = threading.Thread(target=_update_icon, args=(icon,), daemon=True)
    updater.start()

    icon.run()


if __name__ == "__main__":
    main()
