from fastapi import APIRouter, BackgroundTasks, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncio
import os
import time
from typing import List, Optional
from dependencies import get_orchestrator

router = APIRouter()

def get_orch(request: Request):
    return get_orchestrator(request.app.state.event_bus)

@router.get("/api/status")
async def get_status(orch=Depends(get_orch)):
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
        "completed_count": len(orch.queue_service.completed_albums),
        "completed_albums": orch.queue_service.get_completed()
    }

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

@router.get("/api/config")
async def get_config(orch=Depends(get_orch)):
    return orch.config_service.config

@router.post("/api/config")
async def save_config(request: ConfigUpdateRequest, orch=Depends(get_orch)):
    orch.config_service.update_all(request.dict())
    return {"message": "Config saved"}

@router.post("/api/search")
async def search_artist(request: SearchRequest, orch=Depends(get_orch)):
    artists = await asyncio.to_thread(orch.mb_service.search_artist, request.query)
    return {"artists": artists}

@router.post("/api/scan")
async def scan_artist(request: ScanRequest, orch=Depends(get_orch)):
    result = await orch.scan_artists(request.artist_names, request.depth)
    # Auto-add main artists to managed list
    # Use alias-aware normalization to ensure matches (e.g. GMS -> Growling Mad Scientists)
    from services.orchestrator import normalize, normalize_artist_aliases

    for artist_node in result:
        node_norm = normalize(artist_node['name'])
        for req_name in request.artist_names:
            # Check if the returned artist name is an alias of the requested name
            if node_norm in normalize_artist_aliases(req_name):
                await orch.add_managed_artist(artist_node['id'], artist_node['name'])
                break
    return {"tree": result}

@router.post("/api/test_search")
async def test_search(request: Request, orch=Depends(get_orch)):
    data = await request.json()
    query = data.get('query', 'FLAC')
    if not orch.slsk_service.is_connected:
        return {"error": "Not connected to Soulseek."}
    try:
        results = await orch.slsk_service.search(query, timeout=10)
        return {
            "query": query,
            "result_count": len(results),
            "sample": [r['filename'] for r in results[:5]] if results else []
        }
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/start")
async def start_job(request: StartJobRequest, background_tasks: BackgroundTasks, orch=Depends(get_orch)):
    if orch.is_running:
        return JSONResponse(status_code=400, content={"message": "A job is already running."})
    user = orch.config_service.get('slsk_user')
    password = orch.config_service.get('slsk_pass')
    if not user or not password:
        return JSONResponse(status_code=400, content={"message": "Soulseek credentials not configured."})
    background_tasks.add_task(orch.start_download, request.artist_names, user, password, request.dry_run, request.depth, request.selection)
    return {"message": "Job started", "artists": request.artist_names}

@router.post("/api/autonomous_fill")
async def autonomous_fill(request: StartJobRequest, background_tasks: BackgroundTasks, orch=Depends(get_orch)):
    if orch.is_running:
        return JSONResponse(status_code=400, content={"message": "A job is already running."})
    user = orch.config_service.get('slsk_user')
    password = orch.config_service.get('slsk_pass')
    if not user or not password:
        return JSONResponse(status_code=400, content={"message": "Soulseek credentials not configured."})
    background_tasks.add_task(orch.run_autonomous_filler, user, password, request.artist_names, request.depth, request.dry_run)
    return {"message": "Autonomous fill started", "artists": request.artist_names}

@router.post("/api/stop")
async def stop_job(orch=Depends(get_orch)):
    if orch.is_running: orch.stop_job()
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

@router.get("/api/managed_artists")
async def get_managed_artists(orch=Depends(get_orch)):
    return await orch.get_managed_artists()

@router.post("/api/managed_artists")
async def add_managed_artist(request: ManagedArtistRequest, orch=Depends(get_orch)):
    await orch.add_managed_artist(request.artist_id, request.name, request.is_secondary)
    return {"message": f"Added {request.name}"}

@router.delete("/api/managed_artists/{artist_id}")
async def remove_managed_artist(artist_id: str, orch=Depends(get_orch)):
    await orch.remove_managed_artist(artist_id)
    return {"message": "Removed artist"}

@router.post("/api/cleanup_artists")
async def cleanup_artists(orch=Depends(get_orch)):
    removed = await orch.cleanup_managed_artists()
    return {"message": f"Cleaned up {removed} artists"}

@router.get("/api/artist_discography/{artist_id}")
async def get_artist_discography(artist_id: str, orch=Depends(get_orch)):
    return await orch.get_artist_discography_details(artist_id)
