from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import asyncio
import os
import re
import json
import sys
import shutil
import time
from typing import List, Optional

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

from services.orchestrator import Orchestrator
from services.logger import get_logger, manager
from services.musicbrainz import MusicBrainzService
from services.soulseek import SoulseekService
from services.rust_soulseek import RustSoulseekService
from services.config import ConfigService
from services.queue import QueueService
from services.post_processor import PostProcessor
from services.event_bus import EventBus

app = FastAPI(title="Discography Downloader")

STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DOWNLOADS_DIR = os.path.join(os.path.dirname(BASE_DIR), "downloads")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.cache = None

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOADS_DIR), name="downloads")

from routers.core import router as core_router
from routers.library import router as library_router


from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    version = "Unknown"
    version_path = os.path.join(os.path.dirname(BASE_DIR), "VERSION.md")
    if os.path.exists(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
        except Exception:
            pass
    return templates.TemplateResponse("index.html", {"request": request, "version": version})

app.include_router(core_router)
app.include_router(library_router)


from dependencies import get_orchestrator as deps_get_orchestrator

# Event bus
event_bus = EventBus()
app.state.event_bus = event_bus

@app.on_event("startup")
async def startup_event():
    event_bus.set_loop(asyncio.get_running_loop())

async def handle_log_event(payload):
    user_id = payload.get('user_id')
    message = payload.get('message')
    if user_id:
        await manager.broadcast(json.dumps({"type": "log", "message": message}), user_id)

event_bus.subscribe('log', handle_log_event)

def get_orchestrator(user_id: int = 1):
    return deps_get_orchestrator(event_bus, user_id)


# ─── Request Models ─────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    orch = get_orchestrator()

    # Progress data
    progress_data = []
    for target_dir, data in orch.album_tracker.items():
        meta = data['metadata']
        total = data['total']
        done = data['done']
        pct = (done / total * 100) if total > 0 else 0
        elapsed = time.time() - data.get('start_time', time.time())
        speed = ""
        if done > 0 and elapsed > 0:
            rate = done / elapsed  # files per second
            remaining = (total - done) / rate if rate > 0 else 0
            if remaining > 60:
                speed = f"~{int(remaining/60)}m left"
            else:
                speed = f"~{int(remaining)}s left"
        progress_data.append({
            "artist": meta.get('artist', ''),
            "album": meta.get('album', ''),
            "percent": round(pct, 1),
            "text": f"{done}/{total} files",
            "eta": speed
        })

    # Recent logs from file
    recent_logs = []
    try:
        log_file = os.path.join(BASE_DIR, "data", f"app_{USER_ID}.log")
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                recent_logs = [l.strip() for l in lines[-80:]]
    except Exception:
        pass

    return {
        "is_running": orch.is_running,
        "is_paused": orch.is_paused,
        "logs": recent_logs,
        "active_downloads": len(orch.active_downloads),
        "completed_albums": orch.queue_service.completed_albums,
        "progress": progress_data
    }

@app.post("/api/organize_flat")
async def organize_flat_files():
    """Parse flat files in artist dirs and move into Year - Album subfolders.
    Handles pattern: Artist - Year - Album - TrackNum - Title.ext
    """
    root = "downloads"
    moved = 0
    skipped = 0
    errors = 0
    created = []

    if not os.path.isdir(root):
        return {"moved": 0}

    AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}

    for artist_name in sorted(os.listdir(root)):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path):
            continue

        # Scan both the artist root and any Unsorted subdirs
        scan_dirs = [artist_path]
        unsorted_path = os.path.join(artist_path, "Unsorted")
        if os.path.isdir(unsorted_path):
            scan_dirs.append(unsorted_path)

        # Group flat files by album using the filename pattern
        album_groups = {}  # key: "YYYY - Album" -> list of (source_dir, filename)

        for scan_dir in scan_dirs:
            for f in sorted(os.listdir(scan_dir)):
                fp = os.path.join(scan_dir, f)
                if not os.path.isfile(fp):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext not in AUDIO_EXT:
                    continue
                if os.path.getsize(fp) < 50 * 1024:
                    continue

                name = os.path.splitext(f)[0]
                # Remove (1), (2) duplicate suffixes
                name = re.sub(r'\s+\(\d+\)$', '', name)

                # Try pattern: Artist - Year - Album - TrackNum - Title
                m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+\s*-\s*(.+)$', name)
                if m:
                    year = m.group(2)
                    album = m.group(3).strip()
                    album = re.sub(r'\s+\d+$', '', album)
                    key = f"{year} - {album}"
                    album_groups.setdefault(key, []).append((scan_dir, f))
                    continue

                # Try pattern: Artist - Year - Album - TrackNum (no title)
                m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
                if m:
                    year = m.group(2)
                    album = m.group(3).strip()
                    key = f"{year} - {album}"
                    album_groups.setdefault(key, []).append((scan_dir, f))
                    continue

                # Try pattern: Year - Album from folder-style names
                m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+)$', name)
                if m:
                    year = m.group(2)
                    album = m.group(3).strip()
                    if len(album) > 5:
                        key = f"{year} - {album}"
                        album_groups.setdefault(key, []).append((scan_dir, f))
                        continue

                skipped += 1

        # Move grouped files into album subfolders
        for album_key, file_tuples in album_groups.items():
            # Skip if only 1 file — likely not a real album
            if len(file_tuples) < 2:
                skipped += len(file_tuples)
                continue

            # Sanitize folder name for Windows
            safe_key = re.sub(r'[<>:"|?*]', '', album_key)
            safe_key = safe_key.rstrip('. ')
            album_dir = os.path.join(artist_path, safe_key)

            if os.path.exists(album_dir):
                existing = set(os.listdir(album_dir))
                for src_dir, f in file_tuples:
                    fp_src = os.path.join(src_dir, f)
                    clean_f = re.sub(r'\s+\(\d+\)\.', '.', f)
                    dest = os.path.join(album_dir, clean_f)
                    if os.path.exists(dest):
                        try:
                            os.remove(fp_src)
                            moved += 1
                        except:
                            errors += 1
                    else:
                        try:
                            shutil.move(fp_src, dest)
                            moved += 1
                        except:
                            errors += 1
            else:
                os.makedirs(album_dir, exist_ok=True)
                for src_dir, f in file_tuples:
                    fp_src = os.path.join(src_dir, f)
                    clean_f = re.sub(r'\s+\(\d+\)\.', '.', f)
                    dest = os.path.join(album_dir, clean_f)
                    if not os.path.exists(dest):
                        try:
                            shutil.move(fp_src, dest)
                            moved += 1
                        except:
                            errors += 1
                    else:
                        try:
                            os.remove(fp_src)
                            moved += 1
                        except:
                            errors += 1
                created.append(f"{artist_name}/{safe_key} ({len(file_tuples)} files)")

    orch = get_orchestrator()
    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}


@app.post("/api/organize_root")
async def organize_root_files():
    """Organize flat files in the downloads/ root into Artist/Year - Album/ folders."""
    try:
        return await _organize_root_impl()
    except Exception as e:
        return {"moved": 0, "skipped": 0, "errors": 0, "created": [], "error": str(e)}

async def _organize_root_impl():
    root = "downloads"
    moved = 0
    skipped = 0
    errors = 0
    created = []

    if not os.path.isdir(root):
        return {"moved": 0}

    AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}

    # Build artist alias map (e.g. GMS -> Growling Mad Scientists)
    artist_aliases = {}
    for d in os.listdir(root):
        dp = os.path.join(root, d)
        if os.path.isdir(dp):
            artist_aliases[d.lower()] = d

    # Group root-level flat files by (artist, album)
    # Pattern: "Artist - YYYY - Album Name - N - Track Title.ext"
    album_groups = {}  # key: (artist, "YYYY - Album") -> list of files

    for f in sorted(os.listdir(root)):
        fp = os.path.join(root, f)
        if not os.path.isfile(fp):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in AUDIO_EXT:
            continue
        if os.path.getsize(fp) < 50 * 1024:
            continue

        name = os.path.splitext(f)[0]
        # Remove (1), (2) duplicate suffixes
        name = re.sub(r'\s+\(\d+\)$', '', name)

        # Pattern: Artist - Year - Album - TrackNum - Title
        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+\s*-\s*(.+)$', name)
        if m:
            artist_raw = m.group(1).strip()
            year = m.group(2)
            album = m.group(3).strip()
            album = re.sub(r'\s+\d+$', '', album)
            key = (artist_raw, f"{year} - {album}")
            album_groups.setdefault(key, []).append(f)
            continue

        # Pattern: Artist - Year - Album - TrackNum
        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
        if m:
            artist_raw = m.group(1).strip()
            year = m.group(2)
            album = m.group(3).strip()
            key = (artist_raw, f"{year} - {album}")
            album_groups.setdefault(key, []).append(f)
            continue

        skipped += 1

    # Resolve artist names to existing folders
    def resolve_artist(raw_name):
        raw_lower = raw_name.lower()
        # Direct match
        if raw_lower in artist_aliases:
            return artist_aliases[raw_lower]
        # Normalize for fuzzy match
        raw_norm = re.sub(r'[^a-z0-9]', '', raw_lower)
        for alias_lower, alias_orig in artist_aliases.items():
            alias_norm = re.sub(r'[^a-z0-9]', '', alias_lower)
            if raw_norm == alias_norm or raw_norm in alias_norm or alias_norm in raw_norm:
                return alias_orig
        # Known aliases
        alias_map = {
            'gms': 'Growling Mad Scientists',
            'g.m.s.': 'Growling Mad Scientists',
            'gms & dickster': 'Growling Mad Scientists',
            'gms & stryker': 'Growling Mad Scientists',
            'gms vs. systembusters': 'Growling Mad Scientists',
            'gms feat. chicago': 'Growling Mad Scientists',
        }
        if raw_lower in alias_map:
            resolved = alias_map[raw_lower]
            if resolved.lower() in artist_aliases:
                return artist_aliases[resolved.lower()]
        # Create new folder with the raw name
        safe = re.sub(r'[<>:"|?*]', '', raw_name)
        return safe

    # Move grouped files
    for (artist_raw, album_key), files in sorted(album_groups.items()):
        if len(files) < 2:
            skipped += len(files)
            continue

        artist_folder = resolve_artist(artist_raw)
        safe_key = re.sub(r'[<>:"|?*]', '', album_key)
        # Remove trailing dots and spaces (invalid in Windows paths)
        safe_key = safe_key.rstrip('. ')
        album_dir = os.path.join(root, artist_folder, safe_key)

        if os.path.exists(album_dir):
            existing = set(os.listdir(album_dir))
            for f in files:
                fp_src = os.path.join(root, f)
                clean_f = re.sub(r'\s+\(\d+\)\.', '.', f)
                dest = os.path.join(album_dir, clean_f)
                if os.path.exists(dest):
                    try:
                        os.remove(fp_src)
                        moved += 1
                    except:
                        errors += 1
                else:
                    try:
                        shutil.move(fp_src, dest)
                        moved += 1
                    except:
                        errors += 1
        else:
            os.makedirs(album_dir, exist_ok=True)
            for f in files:
                fp_src = os.path.join(root, f)
                clean_f = re.sub(r'\s+\(\d+\)\.', '.', f)
                dest = os.path.join(album_dir, clean_f)
                if not os.path.exists(dest):
                    try:
                        shutil.move(fp_src, dest)
                        moved += 1
                    except:
                        errors += 1
                else:
                    try:
                        os.remove(fp_src)
                        moved += 1
                    except:
                        errors += 1
            created.append(f"{artist_folder}/{safe_key} ({len(files)} files)")

    orch = get_orchestrator()
    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}


@app.post("/api/organize_by_tags")
async def organize_by_tags():
    """Organize remaining files by reading their audio metadata tags.
    Scans root files AND Unsorted subfolders.
    """
    root = "downloads"
    moved = 0
    skipped = 0
    errors = 0
    created = []

    if not os.path.isdir(root):
        return {"moved": 0}

    try:
        import mutagen
    except ImportError:
        return {"moved": 0, "error": "mutagen not installed"}

    AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}

    # Collect files to organize: root-level AND files in Unsorted subdirs
    files_to_check = []
    for f in sorted(os.listdir(root)):
        fp = os.path.join(root, f)
        if os.path.isfile(fp) and f.lower().endswith(('.mp3', '.flac', '.m4a')):
            if os.path.getsize(fp) >= 50 * 1024:
                files_to_check.append(fp)

    for artist_name in os.listdir(root):
        unsorted = os.path.join(root, artist_name, "Unsorted")
        if os.path.isdir(unsorted):
            for f in os.listdir(unsorted):
                fp = os.path.join(unsorted, f)
                if os.path.isfile(fp) and f.lower().endswith(('.mp3', '.flac', '.m4a')):
                    if os.path.getsize(fp) >= 50 * 1024:
                        files_to_check.append(fp)

    for fp in files_to_check:
        try:
            mf = mutagen.File(fp, easy=True)
            if not mf:
                skipped += 1
                continue

            tags = dict(mf)
            artist = tags.get('artist', [None])[0] or tags.get('albumartist', [None])[0]
            album = tags.get('album', [None])[0]

            if not artist or not album:
                skipped += 1
                continue

            safe_artist = re.sub(r'[<>:"|?*]', '', artist.strip()).rstrip('. ')
            safe_album = re.sub(r'[<>:"|?*]', '', album.strip()).rstrip('. ')

            if not safe_artist or not safe_album:
                skipped += 1
                continue

            dest_dir = os.path.join(root, safe_artist, safe_album)
            os.makedirs(dest_dir, exist_ok=True)

            f = os.path.basename(fp)
            clean_f = re.sub(r'\s+\(\d+\)\.', '.', f)
            dest = os.path.join(dest_dir, clean_f)

            if os.path.exists(dest):
                os.remove(fp)
                moved += 1
            else:
                shutil.move(fp, dest)
                moved += 1

            if not os.path.exists(os.path.join(dest_dir, '.organized')):
                open(os.path.join(dest_dir, '.organized'), 'w').close()
                created.append(f"{safe_artist}/{safe_album}")

        except Exception as e:
            errors += 1

    orch = get_orchestrator()
    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}


@app.post("/api/cleanup_empty")
async def cleanup_empty_folders():
    """Remove empty artist folders and Unsorted folders with no audio files."""
    root = "downloads"
    removed = []

    if not os.path.isdir(root):
        return {"removed": 0}

    # Remove empty Unsorted folders
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dirname = os.path.basename(dirpath)
        if dirname == "Unsorted":
            audio = [f for f in filenames if f.lower().endswith(('.mp3', '.flac', '.m4a'))]
            if not audio:
                try:
                    shutil.rmtree(dirpath)
                    removed.append(dirpath)
                except:
                    pass

    # Remove empty artist folders
    for d in sorted(os.listdir(root)):
        dp = os.path.join(root, d)
        if not os.path.isdir(dp):
            continue
        has_files = False
        for dirpath, dirnames, filenames in os.walk(dp):
            if any(f.lower().endswith(('.mp3', '.flac', '.m4a')) for f in filenames):
                has_files = True
                break
        if not has_files:
            try:
                shutil.rmtree(dp)
                removed.append(d)
            except:
                pass

    return {"removed": len(removed), "folders": removed}


@app.post("/api/tidy")
async def tidy_library():
    """Move flat audio files from downloads/ root into organized subfolders."""
    orch = get_orchestrator()
    root = "downloads"
    moved = 0
    skipped = 0
    errors = 0

    if not os.path.isdir(root):
        return {"moved": 0, "skipped": 0, "errors": 0, "message": "No downloads directory."}

    # Build list of existing artist dirs (normalized)
    artist_dirs = {}
    for d in os.listdir(root):
        dp = os.path.join(root, d)
        if os.path.isdir(dp):
            norm = re.sub(r'[^a-z0-9]', '', d.lower())
            artist_dirs[norm] = d

    for f in os.listdir(root):
        fp = os.path.join(root, f)
        if not os.path.isfile(fp):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in ('.mp3', '.flac', '.m4a', '.ogg', '.wav'):
            continue
        if os.path.getsize(fp) < 100 * 1024:
            continue

        name = os.path.splitext(f)[0]
        artist = None

        # Pattern 1: "NN - Artist - Title"
        m = re.match(r'^\d+\s*[-.]\s*(.+?)\s*[-.]\s*(.+)$', name)
        if m:
            artist = m.group(1).strip()
        else:
            # Pattern 2: "(NN) [Artist] Title"
            m = re.match(r'^\(\d+\)\s*\[(.+?)\]\s*(.+)$', name)
            if m:
                artist = m.group(1).strip()
            else:
                # Pattern 3: "Artist - Title"
                parts = name.split(' - ', 1)
                if len(parts) == 2:
                    artist = parts[0].strip()

        if not artist:
            skipped += 1
            continue

        # Find matching artist folder
        artist_norm = re.sub(r'[^a-z0-9]', '', artist.lower())
        matched_dir = None

        # Exact match
        if artist_norm in artist_dirs:
            matched_dir = artist_dirs[artist_norm]
        else:
            # Partial match (artist name contained in folder or vice versa)
            for norm, orig in artist_dirs.items():
                if artist_norm in norm or norm in artist_norm:
                    matched_dir = orig
                    break

        if matched_dir:
            dest = os.path.join(root, matched_dir, f)
            # If dest exists, skip
            if os.path.exists(dest):
                skipped += 1
                continue
            # Move into artist's "Unsorted" subfolder
            unsorted = os.path.join(root, matched_dir, "Unsorted")
            os.makedirs(unsorted, exist_ok=True)
            dest = os.path.join(unsorted, f)
            if not os.path.exists(dest):
                try:
                    shutil.move(fp, dest)
                    moved += 1
                except Exception:
                    errors += 1
            else:
                skipped += 1
        else:
            skipped += 1

    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors}

@app.post("/api/cleanup_incomplete")
async def cleanup_incomplete():
    """Remove album folders with fewer than 3 audio files (likely failed downloads)."""
    root = "downloads"
    cleaned = 0
    freed_mb = 0

    if not os.path.isdir(root):
        return {"cleaned": 0}

    for artist_name in os.listdir(root):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path):
            continue
        for album_name in os.listdir(artist_path):
            album_path = os.path.join(artist_path, album_name)
            if not os.path.isdir(album_path):
                continue
            # Count audio files
            audio = [f for f in os.listdir(album_path)
                     if f.lower().endswith(('.mp3', '.flac', '.m4a'))
                     and os.path.getsize(os.path.join(album_path, f)) > 100 * 1024]
            if 0 < len(audio) < 3:
                # Calculate size before removing
                total_size = sum(os.path.getsize(os.path.join(album_path, f)) for f in os.listdir(album_path)
                                 if os.path.isfile(os.path.join(album_path, f)))
                freed_mb += total_size / (1024 * 1024)
                shutil.rmtree(album_path)
                cleaned += 1

    return {"cleaned": cleaned, "freed_mb": round(freed_mb, 1)}

@app.post("/api/deduplicate")
async def deduplicate_library():
    """Remove duplicate audio files. Works in two passes:
    1. Exact filename match in artist root vs album subfolders
    2. Root-level files that already exist in any album subfolder (by title match)
    """
    root = "downloads"
    removed = 0
    freed_mb = 0

    if not os.path.isdir(root):
        return {"removed": 0}

    AUDIO_EXT = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}

    # Pass 1: artist-root files that duplicate album subfolder files
    for artist_name in os.listdir(root):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path):
            continue

        album_files = set()
        for album_name in os.listdir(artist_path):
            album_path = os.path.join(artist_path, album_name)
            if not os.path.isdir(album_path):
                continue
            for f in os.listdir(album_path):
                album_files.add(f.lower())

        for f in list(os.listdir(artist_path)):
            fp = os.path.join(artist_path, f)
            if os.path.isfile(fp) and f.lower().endswith(('.mp3', '.flac', '.m4a')):
                if f.lower() in album_files:
                    size = os.path.getsize(fp) / (1024 * 1024)
                    freed_mb += size
                    os.remove(fp)
                    removed += 1

    # Pass 2: root-level files that duplicate organized album files (by title)
    # Build index of all track titles in album folders
    organized_titles = {}  # normalized_title -> first path found
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.replace(root, '').count(os.sep)
        if depth < 1:  # skip root level
            continue
        for f in filenames:
            if not f.lower().endswith(('.mp3', '.flac', '.m4a')):
                continue
            # Extract title: remove track number prefix and extension
            name = os.path.splitext(f)[0]
            name = re.sub(r'^\d+\s*[-.]?\s*', '', name)  # Remove track number
            name = re.sub(r'\s+\(\d+\)$', '', name)  # Remove (1) suffix
            name_norm = re.sub(r'[^a-z0-9]', '', name.lower())
            if len(name_norm) > 5:  # Only match meaningful titles
                organized_titles[name_norm] = os.path.join(dirpath, f)

    # Check root-level files against organized titles
    for f in list(os.listdir(root)):
        fp = os.path.join(root, f)
        if not os.path.isfile(fp):
            continue
        if not f.lower().endswith(('.mp3', '.flac', '.m4a')):
            continue
        if os.path.getsize(fp) < 50 * 1024:
            continue

        name = os.path.splitext(f)[0]
        name = re.sub(r'^\d+\s*[-.]?\s*', '', name)
        name = re.sub(r'\s+\(\d+\)$', '', name)
        name_norm = re.sub(r'[^a-z0-9]', '', name.lower())

        if len(name_norm) > 5 and name_norm in organized_titles:
            size = os.path.getsize(fp) / (1024 * 1024)
            freed_mb += size
            os.remove(fp)
            removed += 1

    return {"removed": removed, "freed_mb": round(freed_mb, 1)}


@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket, USER_ID)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, USER_ID)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
