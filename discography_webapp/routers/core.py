from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncio
from typing import List, Optional

router = APIRouter()

# Because routers are imported by main.py, we can safely import get_orchestrator from main.
from fastapi import Depends
from dependencies import get_orchestrator

def get_orch(request: Request):
    return get_orchestrator(request.app.state.event_bus)

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The artist name to search for.")

class ScanRequest(BaseModel):
    artist_names: List[str] = Field(..., min_items=1, description="List of artist names to scan.")
    depth: int = Field(1, ge=0, le=5, description="Depth of related artists to search.")

class StartJobRequest(BaseModel):
    artist_names: List[str] = Field(..., min_items=1, description="List of artist names to start downloading.")
    dry_run: bool = Field(False, description="Simulate downloads without writing files.")
    depth: int = Field(1, ge=0, le=5, description="Depth of related artists to search.")
    selection: Optional[List[dict]] = Field(None, description="Specific selected albums to download.")

class ConfigUpdateRequest(BaseModel):
    slsk_user: str = Field(..., description="Soulseek username.")
    slsk_pass: str = Field(..., description="Soulseek password.")
    preferred_format: str = Field(..., pattern="^(flac|mp3)$", description="Preferred audio format.")
    acoustid_enabled: bool = Field(True, description="Enable AcoustID fingerprinting.")
    acoustid_api_key: str = Field(..., description="API key for AcoustID.")
    acoustid_verify: bool = Field(False, description="Strict verification.")
    embed_lyrics: bool = Field(False, description="Fetch and embed lyrics.")
    genius_api_key: str = Field("", description="Genius API key for fallback lyrics.")
    convert_to_mp3: bool = Field(False, description="Convert FLAC to MP3 V0.")
    sentinel_enabled: bool = Field(False, description="Neural Audio-Quality Sentinel.")


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
    return {"tree": result}

@router.post("/api/test_search")
async def test_search(request: Request, orch=Depends(get_orch)):
    """Test Soulseek connection with a simple search."""
    data = await request.json()
    query = data.get('query', 'FLAC')
    if not orch.slsk_service.is_connected:
        return {"error": "Not connected to Soulseek. Start a download first."}
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
    if not orch.is_running:
        return {"message": "No job running."}
    orch.stop_job()
    return {"message": "Stopping..."}

@router.post("/api/pause")
async def pause_job(orch=Depends(get_orch)):
    if not orch.is_running:
        return {"message": "No job running.", "is_paused": False}
    is_paused = orch.toggle_pause()
    return {"message": "Paused" if is_paused else "Resumed", "is_paused": is_paused}

@router.post("/api/clear_queue")
async def clear_queue(orch=Depends(get_orch)):
    orch.completed_albums = []
    orch.queue_service.completed_albums = []
    orch.queue_service.save()
    return {"message": "History cleared."}
