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
    index = orch._build_existing_index()  # Uses cached index
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

@router.post("/api/organize_flat")
async def organize_library_flat(orch=Depends(get_orch)):
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

@router.post("/api/organize_root")
async def organize_root_files(orch=Depends(get_orch)):
    """Organize flat files in the downloads/ root into Artist/Year - Album/ folders."""
    root = "downloads"
    moved = 0
    skipped = 0
    errors = 0
    created = []

    if not os.path.isdir(root):
        return {"moved": 0}

    # Build artist alias map (e.g. GMS -> Growling Mad Scientists)
    artist_aliases = {}
    for d in os.listdir(root):
        dp = os.path.join(root, d)
        if os.path.isdir(dp):
            artist_aliases[d.lower()] = d

    # Group root-level flat files by (artist, album)
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
        name = re.sub(r'\s+\(\d+\)$', '', name)

        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+\s*-\s*(.+)$', name)
        if m:
            artist_raw = m.group(1).strip()
            year = m.group(2)
            album = m.group(3).strip()
            album = re.sub(r'\s+\d+$', '', album)
            key = (artist_raw, f"{year} - {album}")
            album_groups.setdefault(key, []).append(f)
            continue

        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
        if m:
            artist_raw = m.group(1).strip()
            year = m.group(2)
            album = m.group(3).strip()
            key = (artist_raw, f"{year} - {album}")
            album_groups.setdefault(key, []).append(f)
            continue
        skipped += 1

    from services.orchestrator import ARTIST_ALIASES
    def resolve_artist(raw_name):
        raw_lower = raw_name.lower()
        if raw_lower in artist_aliases:
            return artist_aliases[raw_lower]
        raw_norm = re.sub(r'[^a-z0-9]', '', raw_lower)
        for alias_lower, alias_orig in artist_aliases.items():
            alias_norm = re.sub(r'[^a-z0-9]', '', alias_lower)
            if raw_norm == alias_norm or raw_norm in alias_norm or alias_norm in raw_norm:
                return alias_orig
        for short, full in ARTIST_ALIASES.items():
            if raw_lower == short.lower() or raw_lower == full.lower():
                if full.lower() in artist_aliases: return artist_aliases[full.lower()]
                if short.lower() in artist_aliases: return artist_aliases[short.lower()]
        return re.sub(r'[<>:"|?*]', '', raw_name)

    for (artist_raw, album_key), files in sorted(album_groups.items()):
        if len(files) < 2:
            skipped += len(files)
            continue
        artist_folder = resolve_artist(artist_raw)
        safe_key = re.sub(r'[<>:"|?*]', '', album_key).rstrip('. ')
        album_dir = os.path.join(root, artist_folder, safe_key)
        os.makedirs(album_dir, exist_ok=True)
        for f in files:
            fp_src = os.path.join(root, f)
            dest = os.path.join(album_dir, re.sub(r'\s+\(\d+\)\.', '.', f))
            try:
                if os.path.exists(dest): os.remove(fp_src)
                else: shutil.move(fp_src, dest)
                moved += 1
            except: errors += 1
        created.append(f"{artist_folder}/{safe_key}")

    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}

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

    album_groups = {}
    for f in sorted(os.listdir(artist_path)):
        fp = os.path.join(artist_path, f)
        if not os.path.isfile(fp): continue
        if os.path.splitext(f)[1].lower() not in AUDIO_EXT: continue

        name = os.path.splitext(f)[0]
        name = re.sub(r'\s+\(\d+\)$', '', name)

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

@router.post("/api/organize_by_tags")
async def organize_by_tags(orch=Depends(get_orch)):
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
        import mutagen, mutagen.easyid3, mutagen.flac
    except ImportError:
        return {"moved": 0, "error": "mutagen not installed"}

    # Collect files to organize: root-level AND files in Unsorted subdirs
    files_to_check = []
    for f in sorted(os.listdir(root)):
        fp = os.path.join(root, f)
        if os.path.isfile(fp) and f.lower().endswith(tuple(AUDIO_EXT)):
            if os.path.getsize(fp) >= 50 * 1024:
                files_to_check.append(fp)

    for artist_name in os.listdir(root):
        unsorted = os.path.join(root, artist_name, "Unsorted")
        if os.path.isdir(unsorted):
            for f in os.listdir(unsorted):
                fp = os.path.join(unsorted, f)
                if os.path.isfile(fp) and f.lower().endswith(tuple(AUDIO_EXT)):
                    if os.path.getsize(fp) >= 50 * 1024:
                        files_to_check.append(fp)

    for fp in files_to_check:
        try:
            from mutagen.easyid3 import EasyID3
            from mutagen.flac import FLAC
            artist = None
            album = None

            if fp.endswith('.mp3'):
                audio = EasyID3(fp)
                artist = audio.get('artist', [None])[0]
                album = audio.get('album', [None])[0]
            elif fp.endswith('.flac'):
                audio = FLAC(fp)
                artist = audio.get('artist', [None])[0]
                album = audio.get('album', [None])[0]

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
        except:
            errors += 1

    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors, "created": created}

@router.post("/api/cleanup_empty")
async def cleanup_empty_folders():
    """Remove empty artist folders and Unsorted folders with no audio files."""
    root = "downloads"
    removed = []
    if not os.path.isdir(root): return {"removed": 0}

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        dirname = os.path.basename(dirpath)
        if dirname == "Unsorted":
            audio = [f for f in filenames if f.lower().endswith(tuple(AUDIO_EXT))]
            if not audio:
                try:
                    shutil.rmtree(dirpath)
                    removed.append(dirpath)
                except: pass

    for d in sorted(os.listdir(root)):
        dp = os.path.join(root, d)
        if not os.path.isdir(dp): continue
        has_files = False
        for dirpath, dirnames, filenames in os.walk(dp):
            if any(f.lower().endswith(tuple(AUDIO_EXT)) for f in filenames):
                has_files = True
                break
        if not has_files:
            try:
                shutil.rmtree(dp)
                removed.append(d)
            except: pass
    return {"removed": len(removed), "folders": removed}

@router.post("/api/tidy")
async def tidy_library(orch=Depends(get_orch)):
    """Move flat audio files from downloads/ root into organized subfolders."""
    root = "downloads"
    moved = skipped = errors = 0
    if not os.path.isdir(root): return {"moved": 0}

    artist_dirs = {}
    for d in os.listdir(root):
        dp = os.path.join(root, d)
        if os.path.isdir(dp):
            norm = re.sub(r'[^a-z0-9]', '', d.lower())
            artist_dirs[norm] = d

    for f in os.listdir(root):
        fp = os.path.join(root, f)
        if not os.path.isfile(fp): continue
        if os.path.splitext(f)[1].lower() not in AUDIO_EXT: continue

        name = os.path.splitext(f)[0]
        artist = None
        m = re.match(r'^\d+\s*[-.]\s*(.+?)\s*[-.]\s*(.+)$', name)
        if m: artist = m.group(1).strip()
        else:
            m = re.match(r'^\(\d+\)\s*\[(.+?)\]\s*(.+)$', name)
            if m: artist = m.group(1).strip()
            else:
                parts = name.split(' - ', 1)
                if len(parts) == 2: artist = parts[0].strip()

        if not artist:
            skipped += 1
            continue

        artist_norm = re.sub(r'[^a-z0-9]', '', artist.lower())
        matched_dir = artist_dirs.get(artist_norm)

        # Use refined Orchestrator aliases if no direct folder match
        if not matched_dir:
            from services.orchestrator import ARTIST_ALIASES
            for short, full in ARTIST_ALIASES.items():
                s_norm = re.sub(r'[^a-z0-9]', '', short.lower())
                f_norm = re.sub(r'[^a-z0-9]', '', full.lower())
                if artist_norm == s_norm or artist_norm == f_norm:
                    # Check if either variant exists as a folder
                    if s_norm in artist_dirs: matched_dir = artist_dirs[s_norm]
                    elif f_norm in artist_dirs: matched_dir = artist_dirs[f_norm]
                    break

        if not matched_dir:
            for norm, orig in artist_dirs.items():
                if artist_norm in norm or norm in artist_norm:
                    matched_dir = orig
                    break

        if matched_dir:
            unsorted = os.path.join(root, matched_dir, "Unsorted")
            os.makedirs(unsorted, exist_ok=True)
            dest = os.path.join(unsorted, f)
            if not os.path.exists(dest):
                try:
                    shutil.move(fp, dest)
                    moved += 1
                except: errors += 1
            else: skipped += 1
        else: skipped += 1

    orch.invalidate_cache()
    return {"moved": moved, "skipped": skipped, "errors": errors}

@router.post("/api/cleanup_incomplete")
async def cleanup_incomplete():
    """Remove album folders with fewer than 3 audio files."""
    root = "downloads"
    cleaned = 0
    freed_mb = 0
    if not os.path.isdir(root): return {"cleaned": 0}

    for artist_name in os.listdir(root):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path): continue
        for album_name in os.listdir(artist_path):
            album_path = os.path.join(artist_path, album_name)
            if not os.path.isdir(album_path): continue
            audio = [f for f in os.listdir(album_path) if f.lower().endswith(tuple(AUDIO_EXT))]
            if 0 < len(audio) < 3:
                total_size = sum(os.path.getsize(os.path.join(album_path, f)) for f in os.listdir(album_path) if os.path.isfile(os.path.join(album_path, f)))
                freed_mb += total_size / (1024 * 1024)
                shutil.rmtree(album_path)
                cleaned += 1
    return {"cleaned": cleaned, "freed_mb": round(freed_mb, 1)}

@router.post("/api/deduplicate")
async def deduplicate_library():
    """Remove duplicate audio files by title match."""
    root = "downloads"
    removed = 0
    freed_mb = 0
    if not os.path.isdir(root): return {"removed": 0}

    # Simplified implementation based on original pass 1 & 2
    for artist_name in os.listdir(root):
        artist_path = os.path.join(root, artist_name)
        if not os.path.isdir(artist_path): continue
        album_files = set()
        for album_name in os.listdir(artist_path):
            album_path = os.path.join(artist_path, album_name)
            if os.path.isdir(album_path):
                for f in os.listdir(album_path): album_files.add(f.lower())

        for f in list(os.listdir(artist_path)):
            fp = os.path.join(artist_path, f)
            if os.path.isfile(fp) and f.lower().endswith(tuple(AUDIO_EXT)):
                if f.lower() in album_files:
                    freed_mb += os.path.getsize(fp) / (1024 * 1024)
                    os.remove(fp)
                    removed += 1
    return {"removed": removed, "freed_mb": round(freed_mb, 1)}

def is_safe_path(path: str, base_dir: str = "downloads") -> bool:
    """Ensure the path is within the base directory and prevent traversal."""
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(path)
    return abs_path.startswith(abs_base)

@router.post("/api/delete_album")
async def delete_album(request: Request, orch=Depends(get_orch)):
    data = await request.json()
    artist = data.get('artist')
    album = data.get('album')
    if not artist or not album:
        return {"error": "Missing artist or album"}

    path = os.path.join("downloads", artist, album)
    if not is_safe_path(path):
        return {"error": "Access denied"}

    if os.path.isdir(path):
        shutil.rmtree(path)
        orch.invalidate_cache()
        return {"message": f"Deleted {album}"}
    return {"error": "Album folder not found"}

@router.post("/api/rename_album")
async def rename_album(request: Request, orch=Depends(get_orch)):
    data = await request.json()
    artist = data.get('artist')
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    if not all([artist, old_name, new_name]):
        return {"error": "Missing parameters"}

    old_path = os.path.join("downloads", artist, old_name)
    new_path = os.path.join("downloads", artist, new_name)

    if not is_safe_path(old_path) or not is_safe_path(new_path):
        return {"error": "Access denied"}

    if os.path.isdir(old_path) and not os.path.exists(new_path):
        os.rename(old_path, new_path)
        orch.invalidate_cache()
        return {"message": f"Renamed to {new_name}"}
    return {"error": "Rename failed"}
