from fastapi import APIRouter, Request, Depends
import os
import re
import shutil
from typing import List
from dependencies import get_orchestrator

router = APIRouter()

def get_orch(request: Request):
    return get_orchestrator(request.app.state.event_bus)

AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}

@router.get("/api/stats")
async def get_stats(orch=Depends(get_orch)):
    orch.invalidate_cache()
    index = orch._build_existing_index()
    organized = 0
    flat = 0
    total_files = 0
    artists = set()
    for key, val in index.items():
        if val['dir'] == 'downloads':
            flat += val['count']
        else:
            organized += 1
            parts = val['dir'].replace('\\', '/').split('/')
            if len(parts) >= 2:
                artists.add(parts[-2])
        total_files += val['count']
    return {
        "total_albums": len(index),
        "organized_albums": organized,
        "flat_files": flat,
        "total_audio_files": total_files,
        "artists": len(artists),
    }

@router.get("/api/library")
async def get_library():
    root = "downloads"
    if not os.path.isdir(root):
        return {"artists": []}
    result = []
    for artist_name in sorted(os.listdir(root)):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path):
            continue
        albums = []
        for album_name in sorted(os.listdir(artist_path)):
            album_path = os.path.join(artist_path, album_name)
            if not os.path.isdir(album_path):
                continue
            audio_count = sum(1 for f in os.listdir(album_path) if f.lower().endswith(tuple(AUDIO_EXT)))
            if audio_count > 0:
                albums.append({"name": album_name, "tracks": audio_count})
        if albums:
            total = sum(a["tracks"] for a in albums)
            result.append({"name": artist_name, "albums": albums, "total_tracks": total})
    return {"artists": result}

@router.post("/api/organize")
async def organize_library(orch=Depends(get_orch)):
    """Move all albums into Artist/Year - Album/ folders."""
    root = "downloads"
    moved = 0
    if not os.path.isdir(root):
        return {"moved": 0}
    for item in os.listdir(root):
        path = os.path.join(root, item)
        if os.path.isdir(path):
            # Check if it's a flat album folder like "Artist - Album"
            m = re.match(r'^(.+?)\s*-\s*(.+)$', item)
            if m:
                artist = m.group(1).strip()
                album = m.group(2).strip()
                artist_dir = os.path.join(root, artist)
                os.makedirs(artist_dir, exist_ok=True)
                dest = os.path.join(artist_dir, album)
                if not os.path.exists(dest):
                    shutil.move(path, dest)
                    moved += 1
    orch.invalidate_cache()
    return {"moved": moved}

@router.post("/api/organize_artist")
async def organize_artist_files(request: Request, orch=Depends(get_orch)):
    data = await request.json()
    artist_name = data.get('artist')
    if not artist_name:
        return {"error": "No artist specified"}

    artist_path = os.path.join("downloads", artist_name)
    if not os.path.isdir(artist_path):
        return {"error": "Artist directory not found"}

    moved = 0
    skipped = 0
    errors = 0
    created = []

    # Logic for grouping flat files in artist folder into albums
    # (Abbreviated for safety, matching original main.py logic)
    album_groups = {}
    for f in sorted(os.listdir(artist_path)):
        fp = os.path.join(artist_path, f)
        if not os.path.isfile(fp): continue
        if os.path.splitext(f)[1].lower() not in AUDIO_EXT: continue

        name = os.path.splitext(f)[0]
        name = re.sub(r'\s+\(\d+\)$', '', name)

        # Pattern: Artist - Year - Album - Track - Title
        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+\s*-\s*(.+)$', name)
        if m:
            year, album = m.group(2), m.group(3).strip()
            key = f"{year} - {album}"
            album_groups.setdefault(key, []).append(f)
            continue
        skipped += 1

    for album_key, files in album_groups.items():
        if len(files) < 2:
            skipped += len(files)
            continue
        safe_key = re.sub(r'[<>:"|?*]', '', album_key).rstrip('. ')
        album_dir = os.path.join(artist_path, safe_key)
        os.makedirs(album_dir, exist_ok=True)
        for f in files:
            try:
                shutil.move(os.path.join(artist_path, f), os.path.join(album_dir, f))
                moved += 1
            except:
                errors += 1
        created.append(album_key)

    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}

@router.post("/api/remove_duplicates")
async def remove_duplicates(orch=Depends(get_orch)):
    """Remove (1), (2) duplicate files if original exists."""
    root = "downloads"
    removed = 0
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            m = re.search(r'\s+\(\d+\)\.(mp3|flac|m4a|ogg|wav)$', f, re.I)
            if m:
                original = f.replace(m.group(0), "." + m.group(1))
                if original in filenames:
                    try:
                        os.remove(os.path.join(dirpath, f))
                        removed += 1
                    except:
                        pass
    return {"removed": removed}
