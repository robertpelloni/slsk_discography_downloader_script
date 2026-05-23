from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import asyncio
import os
import json
import sys
import time
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure UTF-8 on Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add local bin to PATH for fpcalc
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
bin_path = os.path.join(BASE_DIR, "bin")
os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]

from services.logger import manager
from services.event_bus import EventBus
from dependencies import orchestrators, get_orchestrator as deps_get_orchestrator
from routers.core import router as core_router
from routers.library import router as library_router
from routers.protocol import router as protocol_router

# Event bus
event_bus = EventBus()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    event_bus.set_loop(asyncio.get_running_loop())
    app.state.event_bus = event_bus

    async def handle_log_event(payload):
        user_id = payload.get('user_id')
        message = payload.get('message')
        if user_id:
            await manager.broadcast(json.dumps({"type": "log", "message": message}), user_id)

    event_bus.subscribe('log', handle_log_event)
    yield
    # Shutdown
    for uid, orch in orchestrators.items():
        try:
            if orch.is_running:
                orch.stop_job()
        except Exception:
            pass

app = FastAPI(title="Discography Downloader", lifespan=lifespan)

STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DOWNLOADS_DIR = os.path.join(os.path.dirname(BASE_DIR), "downloads")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.cache = None

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

# Register Routers
app.include_router(core_router)
app.include_router(library_router)
app.include_router(protocol_router)

def get_orchestrator(user_id: int = 1):
    return deps_get_orchestrator(event_bus, user_id)

# ─── UI Routes ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    version = "unknown"
    version_file = os.path.join(os.path.dirname(BASE_DIR), "VERSION.md")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            version = f.read().strip()
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request, "version": version})

# ─── API Routes (Remaining) ─────────────────────────────────────

@app.get("/api/status")
async def get_status():
    orch = get_orchestrator()
    progress_data = []
    for target_dir, data in orch.album_tracker.items():
        meta = data['metadata']
        total = data['total']
        done = data['done']
        pct = (done / total * 100) if total > 0 else 0
        elapsed = time.time() - data.get('start_time', time.time())
        speed = ""
        if done > 0 and elapsed > 0:
            rate = done / elapsed
            remaining = (total - done) / rate if rate > 0 else 0
            speed = f"{rate:.1f} f/s, {int(remaining)}s left"

        progress_data.append({
            "album": meta['album'],
            "artist": meta['artist'],
            "total": total,
            "done": done,
            "percent": round(pct, 1),
            "speed": speed
        })

    return {
        "is_running": orch.is_running,
        "is_paused": orch.is_paused,
        "current_artist": orch.current_artist,
        "progress": progress_data,
        "queue_size": len(orch.queue_service.queue),
        "completed_count": len(orch.queue_service.completed_albums)
    }

# ─── WebSockets ────────────────────────────────────────────────

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
