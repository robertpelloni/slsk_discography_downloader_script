import asyncio
import os
import re
import shutil
import time
from typing import List, Dict, Any, Optional
from .musicbrainz import MusicBrainzService
from .soulseek import SoulseekService
from .config import ConfigService
from .queue import QueueService
from .post_processor import PostProcessor
from aioslsk.transfer.state import TransferState
import logging

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.ogg', '.wav', '.aac'}
MIN_FILE_SIZE = 100 * 1024  # 100KB — ignore junk files


def sanitize_name(name):
    """Make a filesystem-safe name."""
    return "".join(c for c in name if c.isalpha() or c.isdigit() or c in " .-_").strip()


def normalize(text):
    """Lowercase, strip punctuation/spaces for fuzzy comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


class Orchestrator:
    def __init__(self, logger, mb_service, slsk_service, config_service, post_processor, queue_service, user_id=None):
        self.logger = logger
        self.user_id = user_id
        self.mb_service = mb_service
        self.slsk_service = slsk_service
        self.config_service = config_service
        self.post_processor = post_processor
        self.queue_service = queue_service

        self.is_running = False
        self.should_stop = False
        self.is_paused = False
        self.active_downloads = {}
        self.album_tracker = {}
        self.completed_albums = self.queue_service.get_completed()
        self._existing_cache = None  # Lazy-built index of what's already on disk

        self.slsk_user = self.config_service.get('slsk_user', '')
        self.slsk_pass = self.config_service.get('slsk_pass', '')

    # ─── Library Indexing ─────────────────────────────────────────

    def _build_existing_index(self):
        """Scan the entire downloads tree and build a lookup of what we already have.
        Returns a dict keyed by normalized 'artistalbum' with {dir, count}."""
        if self._existing_cache is not None:
            return self._existing_cache

        index = {}
        root = "downloads"
        if not os.path.exists(root):
            self._existing_cache = index
            return index

        # Scan organized folders: downloads/Artist/Year - Album/
        for artist_name in os.listdir(root):
            artist_path = os.path.join(root, artist_name)
            if not os.path.isdir(artist_path):
                continue
            for album_name in os.listdir(artist_path):
                album_path = os.path.join(artist_path, album_name)
                if not os.path.isdir(album_path):
                    continue
                audio_count = self._count_audio_files(album_path)
                if audio_count > 0:
                    key = normalize(artist_name + album_name)
                    index[key] = {'dir': album_path, 'count': audio_count}

        # Also scan flat files sitting directly in downloads/ root
        for f in os.listdir(root):
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                ext = os.path.splitext(f)[1].lower()
                if ext in AUDIO_EXTENSIONS and os.path.getsize(fp) > MIN_FILE_SIZE:
                    # Try to extract artist-album from filename patterns
                    # These are orphaned files — just note them so we don't re-grab
                    key = normalize(os.path.splitext(f)[0])
                    if key not in index:
                        index[key] = {'dir': root, 'count': 1}

        self._existing_cache = index
        self.logger.info(f"Library index built: {len(index)} albums/entries cached.")
        return index

    def _count_audio_files(self, directory):
        """Count valid audio files (>100KB) in a directory."""
        count = 0
        if not os.path.isdir(directory):
            return 0
        for f in os.listdir(directory):
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                try:
                    if os.path.getsize(os.path.join(directory, f)) > MIN_FILE_SIZE:
                        count += 1
                except OSError:
                    pass
        return count

    def album_exists_on_disk(self, artist_name, album_title, year=""):
        """Check if a complete album already exists locally.
        Returns None if not found or if only incomplete (< 3 files)."""
        index = self._build_existing_index()

        # Try several key variations
        candidates = [
            normalize(artist_name + year + album_title),
            normalize(artist_name + album_title),
        ]
        # Also try without common suffixes like "(Deluxe Edition)", "(Remastered)"
        clean_title = re.sub(r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|remix).*?\)', '', album_title, flags=re.IGNORECASE)
        candidates.append(normalize(artist_name + year + clean_title))
        candidates.append(normalize(artist_name + clean_title))

        for key in candidates:
            if key in index:
                entry = index[key]
                # Require at least 3 files to consider an album "complete"
                # Single-track releases (singles, some EPs) pass with 1+
                if entry['count'] >= 3:
                    return entry
                # Check if it looks like a single/EP (1-2 tracks in a proper subfolder)
                if entry['count'] >= 1 and entry['dir'] != 'downloads':
                    return entry
                # Otherwise it's incomplete — skip it
                return None

        # Fallback: exact directory check
        safe_artist = sanitize_name(artist_name)
        for year_str in [year, "Unknown"] if year else ["Unknown"]:
            safe_album = f"{year_str} - {sanitize_name(album_title)}"
            target_dir = os.path.join("downloads", safe_artist, safe_album)
            if os.path.isdir(target_dir):
                count = self._count_audio_files(target_dir)
                if count >= 3:
                    return {'dir': target_dir, 'count': count}

        return None

    def invalidate_cache(self):
        """Call after downloads complete to refresh the index."""
        self._existing_cache = None

    # ─── Job Control ──────────────────────────────────────────────

    def stop_job(self):
        if self.is_running:
            self.should_stop = True
            self.is_paused = False
            self.logger.info("Stop requested...")

    def toggle_pause(self):
        if self.is_running:
            self.is_paused = not self.is_paused
            self.logger.info(f"Job {'Paused' if self.is_paused else 'Resumed'}.")
        return self.is_paused

    # ─── Scanning ─────────────────────────────────────────────────

    async def scan_artists(self, artist_names, depth=1):
        """Scan one or more artists and return merged result tree."""
        if isinstance(artist_names, str):
            artist_names = [artist_names]
        result_tree = []
        seen_ids = set()
        for artist_name in artist_names:
            self.logger.info(f"Scanning: {artist_name} (depth={depth})")
            artists = await asyncio.to_thread(self.mb_service.search_artist, artist_name)
            if not artists:
                self.logger.warning(f"Artist not found: {artist_name}")
                continue
            main = artists[0]
            if main['id'] in seen_ids:
                self.logger.info(f"  {main['name']} already scanned, skipping.")
                continue
            seen_ids.add(main['id'])
            related = []
            if depth > 0:
                self.logger.info("Finding related artists...")
                related = await asyncio.to_thread(self.mb_service.get_related_artists, main['id'], depth)
            all_artists = [main] + related
            for artist in all_artists:
                if artist['id'] in seen_ids:
                    continue
                seen_ids.add(artist['id'])
                self.logger.info(f"Fetching releases for {artist['name']}...")
                rgs = await asyncio.to_thread(self.mb_service.get_discography, artist['id'])
                albums = []
                for rg in rgs:
                    year = rg.get('first-release-date', '')[:4] or "Unknown"
                    title = rg['title']
                    existing = self.album_exists_on_disk(artist['name'], title, year)
                    albums.append({
                        'id': rg['id'],
                        'title': title,
                        'year': year,
                        'exists_locally': existing is not None,
                        'track_count': existing['count'] if existing else 0
                    })
                result_tree.append({
                    'id': artist['id'],
                    'name': artist['name'],
                    'albums': albums
                })
        return result_tree

    # ─── Autonomous Filler ────────────────────────────────────────
    async def run_autonomous_filler(self, slsk_user, slsk_pass, artist_names, depth=1, dry_run=False):
        """Autonomous filler that processes one or more artists."""
        if isinstance(artist_names, str):
            artist_names = [artist_names]
        self.logger.info("=== Autonomous Collection Filler ===")
        self.logger.info(f"Artists: {', '.join(artist_names)}")
        self.invalidate_cache()
        result_tree = await self.scan_artists(artist_names, depth)
        if not result_tree:
            self.logger.warning("No artists found.")
            return
        missing = []
        total_missing = 0
        for artist_node in result_tree:
            missing_albums = [a for a in artist_node['albums'] if not a['exists_locally']]
            if missing_albums:
                missing.append({
                    'id': artist_node['id'],
                    'name': artist_node['name'],
                    'albums': missing_albums
                })
                total_missing += len(missing_albums)
        if not missing:
            self.logger.info("Library is complete — no gaps found!")
            return
        self.logger.info(f"Found {total_missing} missing albums across {len(missing)} artists.")
        await self.start_download(
            artist_names=artist_names,
            slsk_user=slsk_user,
            slsk_pass=slsk_pass,
            dry_run=dry_run,
            related_artist_depth=depth,
            selection=missing
        )

    # ─── Main Download Engine ─────────────────────────────────────
    async def start_download(self, artist_names, slsk_user, slsk_pass, dry_run=False, related_artist_depth=1, selection=None):
        if self.is_running:
            self.logger.warning("Job already running.")
            return
        if isinstance(artist_names, str):
            artist_names = [artist_names]

        self.invalidate_cache()

        if slsk_user != self.slsk_user or slsk_pass != self.slsk_pass:
            self.config_service.set('slsk_user', slsk_user)
            self.config_service.set('slsk_pass', slsk_pass)
            self.slsk_user = slsk_user
            self.slsk_pass = slsk_pass

        self.is_running = True
        self.should_stop = False
        self.is_paused = False

        if dry_run:
            self.logger.info("*** DRY RUN MODE ***")
        self.logger.info(f"Starting job for artists: {', '.join(artist_names)}")

        try:
            self.logger.info("Connecting to Soulseek...")
            await self.slsk_service.connect(slsk_user, slsk_pass)
            self.logger.info("Connected.")

            # Build artist list
            if selection:
                artists_to_process = selection
            else:
                seen = set()
                artists_to_process = []
                for name in artist_names:
                    found = await asyncio.to_thread(self.mb_service.search_artist, name)
                    if not found:
                        self.logger.warning(f"Artist not found on MusicBrainz: {name}")
                        continue
                    main = found[0]
                    if main['id'] in seen:
                        continue
                    seen.add(main['id'])
                    self.logger.info(f"Found: {main['name']} ({main['id']})")
                    artists_to_process.append({'id': main['id'], 'name': main['name']})
                    if related_artist_depth > 0:
                        self.logger.info(f"Finding related artists (depth={related_artist_depth})...")
                        related = await asyncio.to_thread(self.mb_service.get_related_artists, main['id'], related_artist_depth)
                        for a in related:
                            if a['id'] not in seen:
                                seen.add(a['id'])
                                artists_to_process.append({'id': a['id'], 'name': a['name']})

            self.logger.info(f"Processing {len(artists_to_process)} artist(s).")

            for artist in artists_to_process:
                if self.should_stop:
                    break
                await self._process_artist(artist, dry_run, artist.get('albums'))

            if self.should_stop:
                self.logger.info("Job stopped by user.")
            else:
                self.logger.info("All searches complete. Waiting for final downloads...")
                while self.active_downloads and not self.should_stop:
                    await asyncio.sleep(2)

            self.logger.info("=== Job Finished ===")

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
        finally:
            self.is_running = False
            self.should_stop = False
            # Disconnect from Soulseek to free ports
            try:
                await self.slsk_service.disconnect()
            except Exception:
                pass

    async def _process_artist(self, artist, dry_run, specific_albums=None):
        if self.should_stop:
            return

        name = artist['name']
        self.logger.info(f"═══ {name} ═══")

        if specific_albums:
            rgs = specific_albums
        else:
            rgs = await asyncio.to_thread(self.mb_service.get_discography, artist['id'])

        self.logger.info(f"  {len(rgs)} releases to check.")

        for idx, rg in enumerate(rgs):
            if self.should_stop:
                break
            while self.is_paused and not self.should_stop:
                await asyncio.sleep(1)

            title = rg['title']
            year = rg.get('year') or rg.get('first-release-date', '')[:4] or "Unknown"

            safe_artist = sanitize_name(name)
            safe_album = f"{year} - {sanitize_name(title)}"
            target_dir = os.path.join("downloads", safe_artist, safe_album)

            # ── Check 1: Already completed this session
            if self._is_session_completed(name, title):
                self.logger.info(f"  ⊘ Skip {title} (completed this session)")
                continue

            # ── Check 2: Already on disk
            existing = self.album_exists_on_disk(name, title, year)
            if existing:
                self.logger.info(f"  ⊘ Skip {title} ({existing['count']} tracks on disk)")
                self.queue_service.add_completed({
                    'artist': name, 'album': title, 'year': year,
                    'path': existing['dir'], 'status': 'Existing'
                })
                continue

            self.logger.info(f"  ↓ [{idx+1}/{len(rgs)}] {title} ({year})")

            # ── Smart Retry Search
            success = False
            for attempt in range(4):
                if self.should_stop:
                    break

                query = self._build_query(name, title, attempt)
                self.logger.info(f"    Searching: {query}")

                results = await self.slsk_service.search(query, timeout=15)
                self.logger.info(f"    Got {len(results)} results")

                if not results:
                    if attempt < 3:
                        backoff = 2 ** attempt
                        self.logger.info(f"    No results. Retry in {backoff}s...")
                        await asyncio.sleep(backoff)
                        continue
                    break

                candidates = self._rank_candidates(results, artist_name=name)
                if not candidates:
                    continue

                for idx, cand in enumerate(candidates[:3]):
                    if success or self.should_stop:
                        break

                    user = cand['user']
                    folder = cand['folder']
                    score = cand['score']
                    files = cand['files']
                    self.logger.info(f"    Match #{idx+1}: {folder} ({user}, score={score}, {len(files)} files)")

                    if dry_run:
                        self.logger.info(f"    [Dry Run] Would download → {target_dir}")
                        success = True
                        break

                    try:
                        meta = {
                            'artist': name, 'album': title, 'year': year,
                            'mb_release_group_id': rg['id']
                        }
                        await self._download_sequential(user, files, target_dir, meta)
                        success = True
                        self.queue_service.add_completed({
                            'artist': name, 'album': title, 'year': year,
                            'path': target_dir, 'status': 'Downloaded'
                        })
                        self.invalidate_cache()
                    except Exception as e:
                        self.logger.warning(f"    Candidate failed: {e}")
                        # Clean partial files from this failed attempt
                        self._cleanup_partial(target_dir)
                        await asyncio.sleep(2)

                if not success and attempt < 3:
                    backoff = 2 ** attempt
                    self.logger.info(f"    All candidates failed. Retry in {backoff}s...")
                    await asyncio.sleep(backoff)

            if not success:
                self.logger.warning(f"  ✗ Failed: {title}")
                self._cleanup_dir(target_dir)

            await asyncio.sleep(1)

    def _build_query(self, artist, title, attempt):
        if attempt == 0:
            return f"{artist} {title}"
        elif attempt == 1:
            return f"{artist} {title} FLAC"
        elif attempt == 2:
            clean = re.sub(r'[^a-zA-Z0-9 ]', '', title)
            return f"{artist} {clean}"
        else:
            return title

    def _is_session_completed(self, artist, album):
        return any(
            c['artist'] == artist and c['album'] == album and c['status'] in ('Existing', 'Downloaded', 'Queued')
            for c in self.completed_albums
        )

    def _cleanup_dir(self, target_dir):
        if os.path.exists(target_dir):
            try:
                remaining = os.listdir(target_dir)
                if not remaining or all(f == 'folder.jpg' for f in remaining):
                    shutil.rmtree(target_dir)
            except Exception:
                pass

    def _cleanup_partial(self, target_dir):
        """Remove partially downloaded files (but keep cover art) after a failed candidate."""
        if not os.path.exists(target_dir):
            return
        try:
            for f in os.listdir(target_dir):
                fp = os.path.join(target_dir, f)
                if os.path.isfile(fp) and f != 'folder.jpg':
                    os.remove(fp)
            self.logger.info(f"    Cleaned partial files from {target_dir}")
        except Exception as e:
            self.logger.warning(f"    Cleanup error: {e}")

    # ─── Candidate Ranking ────────────────────────────────────────

    def _rank_candidates(self, results, artist_name=None):
        preferred = self.config_service.get('preferred_format', 'flac')

        # Normalize artist name for folder matching
        artist_norm = None
        if artist_name:
            artist_norm = re.sub(r'[^a-z0-9]', '', artist_name.lower())

        # Group results by (user, folder)
        groups = {}
        for res in results:
            user = res['user']
            folder = os.path.dirname(res['filename'])
            key = (user, folder)
            if key not in groups:
                groups[key] = {'files': [], 'user': user, 'folder': folder}
            groups[key]['files'].append(res)

        scored = []
        for key, data in groups.items():
            audio = [f for f in data['files'] if f['extension'] in AUDIO_EXTENSIONS]
            if not audio:
                continue

            score = 0
            formats = [f['extension'] for f in audio]
            num_files = len(audio)

            # Format preference
            if preferred == 'flac':
                if 'flac' in formats:
                    score += 200
                elif 'mp3' in formats:
                    bitrates = [f['bitrate'] for f in audio if f['bitrate']]
                    avg = sum(bitrates) / len(bitrates) if bitrates else 0
                    score += 80 if avg >= 320 else 60 if avg >= 190 else -50
            else:
                if 'mp3' in formats:
                    bitrates = [f['bitrate'] for f in audio if f['bitrate']]
                    avg = sum(bitrates) / len(bitrates) if bitrates else 0
                    score += 200 if avg >= 320 else 80 if avg >= 190 else 40
                elif 'flac' in formats:
                    score += 100

            # Sweet spot: 4-20 files = likely a real album
            # Too few (<4) = incomplete/random, too many (>20) = compilation
            if 4 <= num_files <= 20:
                score += num_files * 10
            elif 2 <= num_files <= 3:
                score += 20  # EPs are OK
            elif num_files > 20:
                # Heavy penalty for compilations — subtract more for each extra file
                score -= (num_files - 20) * 15

            # Artist name verification: check if folder path contains the artist name
            if artist_norm:
                folder_norm = re.sub(r'[^a-z0-9]', '', data['folder'].lower())
                if artist_norm and artist_norm not in folder_norm:
                    score -= 150  # Heavy penalty — wrong artist
                else:
                    score += 50   # Bonus — correct artist in path

            # Prefer users with free slots
            if any(f.get('slots') for f in audio):
                score += 20

            data['score'] = score
            data['audio_files'] = audio
            scored.append(data)

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    # ─── Sequential Downloader ────────────────────────────────────

    async def _download_sequential(self, user, candidate_files, target_dir, metadata):
        """Download files sequentially with circuit breaker.
        If 3 consecutive files fail, abort and raise to try next candidate."""
        os.makedirs(target_dir, exist_ok=True)

        # Filter to audio + cover art only
        to_download = [
            f for f in candidate_files
            if f['extension'].lower() in AUDIO_EXTENSIONS or f['extension'].lower() in ('.jpg', '.png')
        ]

        if not to_download:
            raise Exception("No audio files in candidate")

        # Skip files that already exist in target_dir
        existing_files = set(os.listdir(target_dir)) if os.path.exists(target_dir) else set()
        to_download = [f for f in to_download if os.path.basename(f['filename']) not in existing_files]

        if not to_download:
            self.logger.info(f"    All files already exist in {target_dir}")
            return

        self.post_processor.download_cover_art(metadata.get('mb_release_group_id'), target_dir)

        total = len(to_download)
        self.logger.info(f"    Downloading {total} files from {user}...")

        self.album_tracker[target_dir] = {
            'total': total, 'done': 0, 'metadata': metadata,
            'start_time': time.time(), 'bytes_done': 0
        }

        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3

        for i, file_info in enumerate(to_download):
            if self.should_stop:
                break

            remote_path = file_info['filename']
            filename = os.path.basename(remote_path)

            # Sanitize filename for Windows
            # Replace chars that are invalid on Windows
            safe_filename = re.sub(r'[<>:"|?*]', '', filename)
            if safe_filename != filename:
                self.logger.info(f"    Sanitized: {safe_filename}")
                filename = safe_filename

            # Skip if already downloaded
            local_target = os.path.join(target_dir, filename)
            if os.path.exists(local_target) and os.path.getsize(local_target) > MIN_FILE_SIZE:
                self.logger.info(f"    [{i+1}/{total}] Skip (exists): {filename}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures = 0
                continue

            self.logger.info(f"    [{i+1}/{total}] ↓ {filename}")

            try:
                transfer = await self.slsk_service.download_file(user, remote_path)
            except Exception as e:
                self.logger.warning(f"    [{i+1}/{total}] Queue failed: {e}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(f"    Circuit breaker: {MAX_CONSECUTIVE_FAILURES} consecutive failures. Aborting this user.")
                    raise Exception(f"User {user} unreliable after {MAX_CONSECUTIVE_FAILURES} failures")
                continue

            done = await self._wait_for_transfer(transfer, timeout=120)

            if done == 'complete':
                local_path = getattr(transfer, 'local_path', None)
                if local_path and os.path.exists(local_path):
                    try:
                        shutil.move(local_path, local_target)
                    except Exception as e:
                        self.logger.error(f"    Move error: {e}")
                self.album_tracker[target_dir]['done'] += 1
                self.logger.info(f"    [{i+1}/{total}] ✓ Done")
                consecutive_failures = 0
            elif done == 'failed':
                reason = getattr(transfer, 'fail_reason', '') or getattr(transfer, 'abort_reason', '') or 'unknown'
                self.logger.warning(f"    [{i+1}/{total}] ✗ Failed: {reason}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(f"    Circuit breaker: aborting.")
                    raise Exception(f"User {user} unreliable after {MAX_CONSECUTIVE_FAILURES} failures")
            else:
                self.logger.warning(f"    [{i+1}/{total}] ⏱ Timeout")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(f"    Circuit breaker: aborting.")
                    raise Exception(f"User {user} too slow after {MAX_CONSECUTIVE_FAILURES} timeouts")

        self._finalize_album(target_dir)

    async def _wait_for_transfer(self, transfer, timeout=180):
        """Wait for a single transfer to reach a final state."""
        waited = 0
        while waited < timeout:
            if self.should_stop:
                return 'stopped'

            state = transfer.state.VALUE
            if state == TransferState.COMPLETE:
                return 'complete'
            elif state in (TransferState.FAILED, TransferState.ABORTED, TransferState.INCOMPLETE):
                return 'failed'

            await asyncio.sleep(1)
            waited += 1
        return 'timeout'

    def _finalize_album(self, target_dir):
        if target_dir not in self.album_tracker:
            return
        info = self.album_tracker[target_dir]
        if info['done'] >= info['total']:
            self.logger.info(f"  ✓ Album complete: {os.path.basename(target_dir)}")
            asyncio.create_task(self.post_processor.process_album(target_dir, info['metadata']))
            del self.album_tracker[target_dir]

    # ─── Legacy Monitor (for any parallel downloads that slip through) ──

    async def monitor_downloads(self):
        """Fallback monitor — only needed if _download_sequential isn't used."""
        while self.is_running or self.active_downloads:
            if self.should_stop and not self.active_downloads:
                break

            finished = []
            failed = []

            for remote_path, info in list(self.active_downloads.items()):
                transfer = info['transfer']
                state = transfer.state.VALUE

                if state == TransferState.COMPLETE:
                    local_path = getattr(transfer, 'local_path', None)
                    if local_path and os.path.exists(local_path):
                        target_path = os.path.join(info['target_dir'], info['filename'])
                        try:
                            shutil.move(local_path, target_path)
                        except Exception as e:
                            self.logger.error(f"Move error: {e}")
                    finished.append(remote_path)
                elif state in (TransferState.FAILED, TransferState.ABORTED, TransferState.INCOMPLETE):
                    failed.append(remote_path)

            for key in finished + failed:
                if key in self.active_downloads:
                    info = self.active_downloads.pop(key)
                    td = info['target_dir']
                    if td in self.album_tracker:
                        self.album_tracker[td]['done'] += 1
                        self._finalize_album(td)

            await asyncio.sleep(1)

    def check_album_completion(self, target_dir):
        self._finalize_album(target_dir)

    def select_best_candidates(self, results):
        """Public wrapper used by tests or external callers."""
        return self._rank_candidates(results)
