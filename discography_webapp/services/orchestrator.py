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

# Known artist aliases for matching (abbreviated -> full name, and vice versa)
ARTIST_ALIASES = {
    'gms': 'Growling Mad Scientists',
    'g.m.s.': 'Growling Mad Scientists',
    'g.m.s': 'Growling Mad Scientists',
    'infected': 'Infected Mushroom',
    '1200mics': '1200 Micrograms',
    '1200mics.': '1200 Micrograms',
    'youngerbrother': 'Younger Brother',
    'youngerbro': 'Younger Brother',
    'prometheus': 'Prometheus (Sean Truby)',
    'slinky': 'Slinky',
    'absolum': 'Absolum',
    'prana': 'Prana',
    'transwave': 'Transwave',
    'hallucinogen': 'Hallucinogen',
    'shpongle': 'Shpongle',
    'cosmosis': 'Cosmosis',
    'totaleclipse': 'Total Eclipse',
    'theantidote': 'The Antidote',
    'oforia': 'Oforia',
    'astralprojection': 'Astral Projection',
    'mitti': 'Mitti',
    'koxbox': 'Koxbox',
    'logicbomb': 'Logic Bomb',
    'x-dream': 'X-Dream',
    'sandman': 'Sandman',
    'jaia': 'Jaia',
    'chi-ad': 'Chi-A.D.',
    'electricuniverse': 'Electric Universe',
    'spacetribe': 'Space Tribe',
    'mantru': 'Manitu',
}


def sanitize_name(name):
    """Make a filesystem-safe name."""
    return "".join(c for c in name if c.isalpha() or c.isdigit() or c in " .-_").strip()


def normalize(text):
    """Lowercase, strip punctuation/spaces for fuzzy comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def normalize_artist_aliases(artist_name):
    """Return a list of normalized artist name variants for matching."""
    variants = set()
    norm = normalize(artist_name)
    variants.add(norm)

    # Check if this artist has known aliases
    for short, full in ARTIST_ALIASES.items():
        short_norm = normalize(short)
        full_norm = normalize(full)
        if norm == short_norm or norm == full_norm:
            variants.add(short_norm)
            variants.add(full_norm)

    return variants


class Orchestrator:
    def __init__(self, logger, mb_service, slsk_service, config_service,
                 post_processor, queue_service, user_id=None):
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

        Returns a dict keyed by normalized 'artistalbum' or 'artistyearalbum'
        with {dir, count, artist, album, year}.
        """
        if self._existing_cache is not None:
            return self._existing_cache

        index = {}
        root = "downloads"
        if not os.path.exists(root):
            self._existing_cache = index
            return index

        # ── 1. Scan organized folders: downloads/Artist/Year - Album/ ──
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
                    # Index with multiple key variations
                    self._add_album_to_index(index, artist_name, album_name, album_path, audio_count)

        # ── 2. Parse flat files in downloads/ root into album groups ──
        self._index_flat_root_files(root, index)

        # ── 3. Index files in "Unsorted" subdirectories ──
        for artist_name in os.listdir(root):
            unsorted_path = os.path.join(root, artist_name, "Unsorted")
            if not os.path.isdir(unsorted_path):
                continue
            self._index_flat_subdir_files(unsorted_path, index, artist_name)

        # ── 4. Index files sitting directly in artist root folders ──
        for artist_name in os.listdir(root):
            artist_path = os.path.join(root, artist_name)
            if not os.path.isdir(artist_path):
                continue
            self._index_flat_subdir_files(artist_path, index, artist_name,
                                          skip_subdirs=True)

        self._existing_cache = index
        self.logger.info(f"Library index built: {len(index)} albums/entries cached.")
        return index

    def _add_album_to_index(self, index, artist_name, album_dir_name, path, audio_count):
        """Add an album to the index with multiple key variations for robust matching."""
        # Try to extract year from "YYYY - Album Title" pattern
        m = re.match(r'^(\d{4})\s*-\s*(.+)$', album_dir_name)
        if m:
            year = m.group(1)
            album_title = m.group(2).strip()
        else:
            year = ''
            album_title = album_dir_name

        entry = {'dir': path, 'count': audio_count, 'artist': artist_name,
                 'album': album_title, 'year': year}

        # Multiple key variations for robust matching
        keys = set()
        for artist_variant in normalize_artist_aliases(artist_name):
            keys.add(artist_variant + normalize(album_dir_name))  # full dir name
            keys.add(artist_variant + normalize(album_title))      # album title only
            if year:
                keys.add(artist_variant + year + normalize(album_title))
                keys.add(artist_variant + normalize(year + album_title))

        # Also try without common suffixes
        clean_title = re.sub(
            r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|remix|remastered|live|acoustic).*?\)',
            '', album_title, flags=re.IGNORECASE)
        clean_dir = re.sub(
            r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|remix|remastered|live|acoustic).*?\)',
            '', album_dir_name, flags=re.IGNORECASE)
        for artist_variant in normalize_artist_aliases(artist_name):
            keys.add(artist_variant + normalize(clean_title))
            keys.add(artist_variant + normalize(clean_dir))
            if year:
                keys.add(artist_variant + year + normalize(clean_title))

        for key in keys:
            if key not in index or index[key]['count'] < audio_count:
                index[key] = entry

    def _index_flat_root_files(self, root, index):
        """Parse flat files in the downloads/ root and group them by album."""
        album_groups = {}  # key -> {files: [], artist, album, year}

        for f in sorted(os.listdir(root)):
            fp = os.path.join(root, f)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            if os.path.getsize(fp) < MIN_FILE_SIZE:
                continue
            name = os.path.splitext(f)[0]

            # Pattern: Artist - Year - Album - TrackNum - Title
            m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
            if m:
                artist = m.group(1).strip()
                year = m.group(2)
                album = re.sub(r'\s+\d+$', '', m.group(3).strip())
                key = f"{artist}|{year}|{album}"
                album_groups.setdefault(key, {
                    'files': [], 'artist': artist, 'album': album, 'year': year
                }).get('files').append(fp)
                continue

            # Pattern: Artist - Album - TrackNum - Title
            m = re.match(r'^(.+?)\s*-\s*(.+?)\s*-\s*\d+\s*[-.]', name)
            if m:
                artist = m.group(1).strip()
                album = m.group(2).strip()
                key = f"{artist}|{album}"
                album_groups.setdefault(key, {
                    'files': [], 'artist': artist, 'album': album, 'year': ''
                }).get('files').append(fp)
                continue

        # Add groups with 2+ files to the index as real albums
        for key, group in album_groups.items():
            if len(group['files']) < 2:
                continue
            artist = group['artist']
            album = group['album']
            year = group['year']
            count = len(group['files'])

            entry = {'dir': root, 'count': count, 'artist': artist,
                     'album': album, 'year': year, 'flat_files': True}

            for artist_variant in normalize_artist_aliases(artist):
                idx_key = artist_variant + normalize(album)
                if idx_key not in index or index[idx_key]['count'] < count:
                    index[idx_key] = entry
                if year:
                    idx_key2 = artist_variant + year + normalize(album)
                    if idx_key2 not in index or index[idx_key2]['count'] < count:
                        index[idx_key2] = entry
                    idx_key3 = artist_variant + normalize(year + album)
                    if idx_key3 not in index or index[idx_key3]['count'] < count:
                        index[idx_key3] = entry

    def _index_flat_subdir_files(self, subdir, index, artist_name=None,
                                  skip_subdirs=False):
        """Index flat audio files in a subdirectory (e.g. Unsorted/)."""
        for f in os.listdir(subdir):
            fp = os.path.join(subdir, f)
            if skip_subdirs and os.path.isdir(fp):
                continue
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            if os.path.getsize(fp) < MIN_FILE_SIZE:
                continue

            name = os.path.splitext(f)[0]
            # Try to extract artist/album from filename
            extracted_artist = artist_name
            album = ''
            year = ''

            m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
            if m:
                extracted_artist = m.group(1).strip()
                year = m.group(2)
                album = re.sub(r'\s+\d+$', '', m.group(3).strip())
            else:
                m = re.match(r'^(.+?)\s*-\s*(.+?)\s*-\s*\d+\s*[-.]', name)
                if m:
                    extracted_artist = m.group(1).strip()
                    album = m.group(2).strip()

            # Add to index with artist override if provided
            effective_artist = artist_name or extracted_artist
            for artist_variant in normalize_artist_aliases(effective_artist):
                if album:
                    key = artist_variant + normalize(album)
                    if key not in index:
                        index[key] = {'dir': subdir, 'count': 1,
                                      'artist': effective_artist,
                                      'album': album, 'year': year}
                    if year and album:
                        key2 = artist_variant + year + normalize(album)
                        if key2 not in index:
                            index[key2] = {'dir': subdir, 'count': 1,
                                           'artist': effective_artist,
                                           'album': album, 'year': year}

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

        Returns None if not found or if only incomplete (< 3 files).
        Uses multiple key variations and artist alias matching.
        """
        index = self._build_existing_index()

        # Build candidate keys with artist aliases
        candidates = set()
        for artist_variant in normalize_artist_aliases(artist_name):
            candidates.add(artist_variant + normalize(album_title))
            if year:
                candidates.add(artist_variant + year + normalize(album_title))
                candidates.add(artist_variant + normalize(year + album_title))

            # Also try without common suffixes
            clean_title = re.sub(
                r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|remix|remastered|live|acoustic).*?\)',
                '', album_title, flags=re.IGNORECASE)
            candidates.add(artist_variant + normalize(clean_title))
            if year:
                candidates.add(artist_variant + year + normalize(clean_title))

            # Try without "The" prefix
            title_no_the = re.sub(r'^[Tt]he\s+', '', album_title)
            candidates.add(artist_variant + normalize(title_no_the))
            if year:
                candidates.add(artist_variant + year + normalize(title_no_the))

        # Check all candidates
        for key in candidates:
            if key in index:
                entry = index[key]
                if entry['count'] >= 3:
                    return entry
                # Single/EP (1-2 tracks) in a proper subfolder is OK
                if entry['count'] >= 1 and entry.get('dir', '') != 'downloads':
                    return entry

        # Fallback: substring match — title appears in any index key for this artist
        title_norm = normalize(album_title)
        for artist_variant in normalize_artist_aliases(artist_name):
            for key, entry in index.items():
                if artist_variant in key and title_norm in key and entry['count'] >= 2:
                    return entry

        # Final fallback: exact directory check
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
            artists = await asyncio.to_thread(
                self.mb_service.search_artist, artist_name)
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
                related = await asyncio.to_thread(
                    self.mb_service.get_related_artists, main['id'], depth)

            all_artists = [main] + related
            for artist in all_artists:
                if artist['id'] in seen_ids:
                    continue
                seen_ids.add(artist['id'])
                self.logger.info(f"Fetching releases for {artist['name']}...")
                rgs = await asyncio.to_thread(
                    self.mb_service.get_discography, artist['id'])
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

    async def run_autonomous_filler(self, slsk_user, slsk_pass, artist_names,
                                     depth=1, dry_run=False):
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
            missing_albums = [a for a in artist_node['albums']
                              if not a['exists_locally']]
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

    async def start_download(self, artist_names, slsk_user, slsk_pass,
                              dry_run=False, related_artist_depth=1,
                              selection=None):
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
                    found = await asyncio.to_thread(
                        self.mb_service.search_artist, name)
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
                        related = await asyncio.to_thread(
                            self.mb_service.get_related_artists,
                            main['id'], related_artist_depth)
                        for a in related:
                            if a['id'] not in seen:
                                seen.add(a['id'])
                                artists_to_process.append({
                                    'id': a['id'], 'name': a['name']})

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
            rgs = await asyncio.to_thread(
                self.mb_service.get_discography, artist['id'])

        self.logger.info(f"  {len(rgs)} releases to check.")

        for idx, rg in enumerate(rgs):
            if self.should_stop:
                break
            while self.is_paused and not self.should_stop:
                await asyncio.sleep(1)

            title = rg['title']
            year = (rg.get('year') or
                    rg.get('first-release-date', '')[:4] or
                    "Unknown")
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
                    'artist': name, 'album': title,
                    'year': year, 'path': existing['dir'],
                    'status': 'Existing'
                })
                continue

            self.logger.info(f"  ↓ [{idx+1}/{len(rgs)}] {title} ({year})")

            # ── Smart Retry Search with broad strategy ──
            success = False
            queries = self._build_queries(name, title, year)

            for attempt, query in enumerate(queries):
                if success or self.should_stop:
                    break

                self.logger.info(f"  Searching (attempt {attempt+1}/{len(queries)}): {query}")
                results = await self.slsk_service.search(query, timeout=20)
                self.logger.info(f"  Got {len(results)} results")

                if not results:
                    if attempt < len(queries) - 1:
                        await asyncio.sleep(1)
                    continue

                candidates = self._rank_candidates(results, artist_name=name)
                if not candidates:
                    if attempt < len(queries) - 1:
                        await asyncio.sleep(1)
                    continue

                # Try top candidates
                for cidx, cand in enumerate(candidates[:5]):
                    if success or self.should_stop:
                        break
                    user = cand['user']
                    folder = cand['folder']
                    score = cand['score']
                    files = cand['files']
                    self.logger.info(
                        f"  Match #{cidx+1}: {folder} "
                        f"({user}, score={score}, {len(files)} files)")

                    if dry_run:
                        self.logger.info(f"  [Dry Run] Would download → {target_dir}")
                        success = True
                        break

                    try:
                        meta = {
                            'artist': name, 'album': title,
                            'year': year, 'mb_release_group_id': rg['id']
                        }
                        await self._download_sequential(user, files, target_dir, meta)
                        success = True
                        self.queue_service.add_completed({
                            'artist': name, 'album': title,
                            'year': year, 'path': target_dir,
                            'status': 'Downloaded'
                        })
                        self.invalidate_cache()
                    except Exception as e:
                        self.logger.warning(f"  Candidate failed: {e}")
                        self._cleanup_partial(target_dir)
                        await asyncio.sleep(2)

                if not success and attempt < len(queries) - 1:
                    await asyncio.sleep(1)

            if not success:
                self.logger.warning(f"  ✗ Failed: {title}")
                self._cleanup_dir(target_dir)
                await asyncio.sleep(1)

    def _build_queries(self, artist, title, year=""):
        """Build a prioritized list of search queries with increasing breadth.

        Strategy: start specific, get progressively broader.
        """
        clean_title = re.sub(r'[^a-zA-Z0-9 ]', '', title)
        queries = [
            f"{artist} {title}",                          # Full specific
            f"{artist} {title} FLAC",                     # Format hint
            f"{artist} {year} {title}",                   # With year
            f"{artist} {clean_title}",                    # Cleaned title
            f"{artist} {clean_title} FLAC",               # Cleaned + format
            title,                                        # Album title alone
            f"{clean_title} FLAC",                        # Cleaned title + format
        ]

        # Add alias-based queries if the artist has known aliases
        norm = normalize(artist)
        for short, full in ARTIST_ALIASES.items():
            if norm == normalize(short):
                queries.insert(3, f"{full} {title}")
                queries.insert(4, f"{full} {year} {title}")
            elif norm == normalize(full):
                queries.insert(3, f"{short} {title}")
                queries.insert(4, f"{short} {year} {title}")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)

        return unique

    def _build_query(self, artist, title, attempt):
        """Legacy single-query builder (kept for compatibility)."""
        queries = self._build_queries(artist, title)
        if attempt < len(queries):
            return queries[attempt]
        return title

    def _is_session_completed(self, artist, album):
        return any(
            c['artist'] == artist and c['album'] == album
            and c['status'] in ('Existing', 'Downloaded', 'Queued')
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
        """Remove partially downloaded files (but keep cover art)."""
        if not os.path.exists(target_dir):
            return
        try:
            for f in os.listdir(target_dir):
                fp = os.path.join(target_dir, f)
                if os.path.isfile(fp) and f != 'folder.jpg':
                    os.remove(fp)
            self.logger.info(f"  Cleaned partial files from {target_dir}")
        except Exception as e:
            self.logger.warning(f"  Cleanup error: {e}")

    # ─── Candidate Ranking ────────────────────────────────────────

    def _rank_candidates(self, results, artist_name=None):
        preferred = self.config_service.get('preferred_format', 'flac')

        # Normalize artist name for folder matching
        artist_norms = set()
        if artist_name:
            artist_norms = normalize_artist_aliases(artist_name)

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
            audio = [f for f in data['files']
                     if f['extension'] in AUDIO_EXTENSIONS]
            if not audio:
                continue

            score = 0
            formats = [f['extension'] for f in audio]
            num_files = len(audio)

            # Format preference
            if preferred == 'flac':
                if '.flac' in formats:
                    score += 200
                elif '.mp3' in formats:
                    bitrates = [f['bitrate'] for f in audio if f['bitrate']]
                    avg = sum(bitrates) / len(bitrates) if bitrates else 0
                    score += 80 if avg >= 320 else 60 if avg >= 190 else -50
            else:
                if '.mp3' in formats:
                    bitrates = [f['bitrate'] for f in audio if f['bitrate']]
                    avg = sum(bitrates) / len(bitrates) if bitrates else 0
                    score += 200 if avg >= 320 else 80 if avg >= 190 else 40
                elif '.flac' in formats:
                    score += 100

            # File count sweet spot
            if 4 <= num_files <= 20:
                score += num_files * 10
            elif 2 <= num_files <= 3:
                score += 20  # EPs are OK
            elif num_files > 20:
                score -= (num_files - 20) * 15  # Compilation penalty

            # Artist name verification with aliases
            if artist_norms:
                folder_norm = re.sub(r'[^a-z0-9]', '', data['folder'].lower())
                artist_match = any(a_norm in folder_norm for a_norm in artist_norms)
                if artist_match:
                    score += 50  # Bonus — correct artist
                else:
                    score -= 80  # Moderate penalty (not as harsh as before —
                                  # folder might still be the right album)

            # Prefer users with free slots
            if any(f.get('slots') for f in audio):
                score += 20

            data['score'] = score
            data['audio_files'] = audio
            scored.append(data)

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored

    # ─── Sequential Downloader ────────────────────────────────────

    async def _download_sequential(self, user, candidate_files, target_dir,
                                    metadata):
        """Download files sequentially with circuit breaker."""
        os.makedirs(target_dir, exist_ok=True)

        # Filter to audio + cover art only
        to_download = [
            f for f in candidate_files
            if f['extension'].lower() in AUDIO_EXTENSIONS
            or f['extension'].lower() in ('.jpg', '.png')
        ]
        if not to_download:
            raise Exception("No audio files in candidate")

        # Skip files that already exist
        existing_files = set(os.listdir(target_dir)) if os.path.exists(target_dir) else set()
        to_download = [f for f in to_download
                       if os.path.basename(f['filename']) not in existing_files]
        if not to_download:
            self.logger.info(f"  All files already exist in {target_dir}")
            return

        self.post_processor.download_cover_art(
            metadata.get('mb_release_group_id'), target_dir)

        total = len(to_download)
        self.logger.info(f"  Downloading {total} files from {user}...")

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
            safe_filename = re.sub(r'[<>:"|?*]', '', filename)
            if safe_filename != filename:
                self.logger.info(f"  Sanitized: {safe_filename}")
            filename = safe_filename

            # Skip if already downloaded
            local_target = os.path.join(target_dir, filename)
            if os.path.exists(local_target) and os.path.getsize(local_target) > MIN_FILE_SIZE:
                self.logger.info(f"  [{i+1}/{total}] Skip (exists): {filename}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures = 0
                continue

            self.logger.info(f"  [{i+1}/{total}] ↓ {filename}")

            try:
                transfer = await self.slsk_service.download_file(user, remote_path)
            except Exception as e:
                self.logger.warning(f"  [{i+1}/{total}] Queue failed: {e}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(
                        f"  Circuit breaker: {MAX_CONSECUTIVE_FAILURES} "
                        f"consecutive failures. Aborting this user.")
                    raise Exception(
                        f"User {user} unreliable after "
                        f"{MAX_CONSECUTIVE_FAILURES} failures")
                continue

            done = await self._wait_for_transfer(transfer, timeout=120)

            if done == 'complete':
                local_path = getattr(transfer, 'local_path', None)
                if local_path and os.path.exists(local_path):
                    try:
                        shutil.move(local_path, local_target)
                    except Exception as e:
                        self.logger.error(f"  Move error: {e}")
                self.album_tracker[target_dir]['done'] += 1
                self.logger.info(f"  [{i+1}/{total}] ✓ Done")
                consecutive_failures = 0
            elif done == 'failed':
                reason = (getattr(transfer, 'fail_reason', '') or
                          getattr(transfer, 'abort_reason', '') or 'unknown')
                self.logger.warning(f"  [{i+1}/{total}] ✗ Failed: {reason}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(f"  Circuit breaker: aborting.")
                    raise Exception(
                        f"User {user} unreliable after "
                        f"{MAX_CONSECUTIVE_FAILURES} failures")
            else:
                self.logger.warning(f"  [{i+1}/{total}] ⏱ Timeout")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(f"  Circuit breaker: aborting.")
                    raise Exception(
                        f"User {user} too slow after "
                        f"{MAX_CONSECUTIVE_FAILURES} timeouts")

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
            elif state in (TransferState.FAILED, TransferState.ABORTED,
                           TransferState.INCOMPLETE):
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
            # Safely schedule post-processing on the running event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.post_processor.process_album(target_dir, info['metadata']))
            except RuntimeError:
                try:
                    asyncio.create_task(
                        self.post_processor.process_album(target_dir, info['metadata']))
                except RuntimeError:
                    self.logger.warning(
                        f"Could not schedule post-processing for {target_dir} "
                        f"(no event loop)")
            del self.album_tracker[target_dir]

    # ─── Legacy Monitor ───────────────────────────────────────────

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
                        target_path = os.path.join(
                            info['target_dir'], info['filename'])
                        try:
                            shutil.move(local_path, target_path)
                        except Exception as e:
                            self.logger.error(f"Move error: {e}")
                    finished.append(remote_path)
                elif state in (TransferState.FAILED, TransferState.ABORTED,
                               TransferState.INCOMPLETE):
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
