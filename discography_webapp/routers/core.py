from fastapi import APIRouter, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncio
from typing import List, Optional
from dependencies import get_orchestrator

router = APIRouter()

def get_orch(request: Request):
    # Use the event_bus from app state
    return get_orchestrator(request.app.state.event_bus)

# ─── Models ──────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)

class ScanRequest(BaseModel):
    artist_names: List[str]
    depth: int = 1

class StartJobRequest(BaseModel):
    artist_names: List[str]
    dry_run: bool = False
    depth: int = 1
    selection: Optional[List[dict]] = None

class ManagedArtistRequest(BaseModel):
    artist_id: str
    name: str
    is_secondary: bool = False

class ConfigUpdateRequest(BaseModel):
    slsk_user: str
    slsk_pass: str
    preferred_format: str
    acoustid_enabled: bool
    acoustid_api_key: str
    acoustid_verify: bool
    embed_lyrics: bool
    genius_api_key: str
    convert_to_mp3: bool
    sentinel_enabled: bool

# ─── Config ──────────────────────────────────────────────────────

@router.get("/api/config")
async def get_config(orch=Depends(get_orch)):
    return orch.config_service.config

@router.post("/api/config")
async def save_config(request: ConfigUpdateRequest, orch=Depends(get_orch)):
    orch.config_service.update_all(request.dict())
    return {"message": "Config saved"}

# ─── Search & Scan ──────────────────────────────────────────────

@router.post("/api/search")
async def search_artist(request: SearchRequest, orch=Depends(get_orch)):
    artists = await asyncio.to_thread(orch.mb_service.search_artist, request.query)
    return {"artists": artists}

@router.post("/api/scan")
async def scan_artist(request: ScanRequest, orch=Depends(get_orch)):
    result = await orch.scan_artists(request.artist_names, request.depth)
    return {"tree": result}

# ─── Job Control ────────────────────────────────────────────────

@router.post("/api/start")
async def start_job(request: StartJobRequest, background_tasks: BackgroundTasks, orch=Depends(get_orch)):
    if orch.is_running:
        return JSONResponse(status_code=400, content={"message": "A job is already running."})
    user = orch.config_service.get('slsk_user')
    password = orch.config_service.get('slsk_pass')
    if not user or not password:
        return JSONResponse(status_code=400, content={"message": "Soulseek credentials not configured."})
    background_tasks.add_task(
        orch.start_download, request.artist_names, user, password,
        request.dry_run, request.depth, request.selection
    )
    return {"message": "Job started", "artists": request.artist_names}

@router.post("/api/autonomous_fill")
async def autonomous_fill(request: StartJobRequest, background_tasks: BackgroundTasks, orch=Depends(get_orch)):
    if orch.is_running:
        return JSONResponse(status_code=400, content={"message": "A job is already running."})
    user = orch.config_service.get('slsk_user')
    password = orch.config_service.get('slsk_pass')
    if not user or not password:
        return JSONResponse(status_code=400, content={"message": "Soulseek credentials not configured."})
    background_tasks.add_task(
        orch.run_autonomous_filler, user, password, request.artist_names,
        request.depth, request.dry_run
    )
    return {"message": "Autonomous fill started", "artists": request.artist_names}

@router.post("/api/stop")
async def stop_job(orch=Depends(get_orch)):
    if orch.is_running:
        orch.stop_job()
    return {"message": "Stopped"}

@router.post("/api/pause")
async def pause_job(orch=Depends(get_orch)):
    is_paused = orch.toggle_pause()
    return {"message": "Paused" if is_paused else "Resumed", "is_paused": is_paused}

@router.post("/api/clear_queue")
async def clear_queue(orch=Depends(get_orch)):
    orch.completed_albums = []
    orch.queue_service.completed_albums = []
    orch.queue_service.save()
    return {"message": "History cleared."}

# ─── Managed Artists ───────────────────────────────────────────

@router.get("/api/managed_artists")
async def get_managed_artists(orch=Depends(get_orch)):
    return orch.queue_service.get_managed_artists()

@router.post("/api/managed_artists")
async def add_managed_artist(request: ManagedArtistRequest, orch=Depends(get_orch)):
    orch.queue_service.add_managed_artist(request.artist_id, request.name, request.is_secondary)
    return {"message": f"Added {request.name}"}

@router.delete("/api/managed_artists/{artist_id}")
async def remove_managed_artist(artist_id: str, orch=Depends(get_orch)):
    orch.queue_service.remove_managed_artist(artist_id)
    return {"message": "Removed artist"}

@router.post("/api/managed_artists/sync")
async def sync_managed_artists(orch=Depends(get_orch)):
    """Sync managed artists list with actual directories on disk."""
    root = "downloads"
    if not os.path.isdir(root):
        return {"message": "No downloads directory."}

    # Simple logic: if a directory exists and isn't managed, add it.
    # Note: We don't have MBIDs for existing folders easily, so this is a 'best effort'.
    # For now, let's just return what's in the DB.
    return orch.queue_service.get_managed_artists()
import os
