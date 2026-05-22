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

# Known artist aliases for matching (abbreviated <-> full name)
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

# Psytrance / electronic tags for genre filtering of related artists
PSYTRANCE_TAGS = {
    'psytrance', 'psychedelic trance', 'psychedelic', 'goa trance',
    'goa', 'trance', 'electronic', 'techno', 'psy', 'full-on',
    'progressive trance', 'darkpsy', 'suomisaundi', 'hi-tech',
    'psychill', 'downtempo', 'ambient', 'chillout', 'tribal',
    'industrial', 'hardcore', 'gabber', 'frenchcore',
    'electronica', 'edm', 'dance', 'hard trance',
}

# Tags that represent a radical departure from the target scene
DISALLOWED_TAGS = {
    'pop', 'jazz', 'classical', 'country', 'folk', 'punk', 'blues', 
    'soul', 'r&b', 'hip hop', 'rap', 'christian', 'gospel', 'latin', 
    'reggae', 'indie', 'alternative rock', 'metal', 'heavy metal',
    'rock', 'hard rock', 'soft rock', 'aor', 'prog rock', 'progressive rock',
    'singer-songwriter', 'musical', 'soundtrack', 'score',
    'contemporary christian', 'worship', 'praise', 'spiritual',
}

# Names that exist in both psy/electronic and unrelated genres
AMBIGUOUS_NAMES = {'chicago', 'avalon', 'quintessence', 'truth', 'esp', 'hydra'}

# Artists known to be in the psytrance/electronic scene, even if MB tags are sparse
# Built lazily via function to avoid forward-reference issues with normalize()
_KNOWN_PSYTRANCE_NAMES = [
    '1200 Micrograms', 'Growling Mad Scientists', 'GMS', 'Infected Mushroom',
    'Hallucinogen', 'Shpongle', 'Cosmosis', 'Total Eclipse', 'Astral Projection',
    'Electric Universe', 'Space Tribe', 'Transwave', 'Koxbox', 'Logic Bomb',
    'X-Dream', 'Sandman', 'Jaia', 'Chi-A.D.', 'Oforia', 'Prana',
    'The Infinity Project', 'Younger Brother', 'Prometheus', 'Slinky',
    'Absolum', 'Talamasca', 'Astrix', 'Ace Ventura', 'Ajja',
    'Dickster', 'Mad Maxx', 'Mad Tribe', 'Biodegradable',
    'Alien Project', 'Psysex', 'Hujaboy', 'Riktam', 'Bansi',
    'Raja Ram', 'Sajahan Matkin',
    'Soundaholix', '3 Of Life', 'Faders', 'Hypnocoustics',
    'Save The Robot', 'Alienatic', 'Space Buddha', 'Laughing Buddha',
    'Outsiders', 'Growling Machines', 'DJ Stryker', 'Avalon',
    'Mumbo Jumbo', 'Hopefiend', 'Abraxas',
    'Alien vs. The Cat', 'Crunchy Punch', 'Liquid Ace', 'Zentura',
    'Vogon 42', 'Specimen', 'Sirius Isness', 'Olli Wisdom',
    'Max Peterson', 'The Plague', 'Hydra', 'ESP',
    'DJ Technorch', 'Betwixt & Between', 'RaverRose',
    'The Peaking Goddess Collective', 'Tranceformation',
    'Undefined Behavior', 'Omputer', 'The Noodniks',
    'Twisted Allstars', 'Meathead Productions', 'Spacedrifters',
    'Sas, Ban & Tony', 'Riktam & Bansi', 'Children of the Doc',
    'Psysex in Panick', 'Growling Mad Sex', 'Koopa Troopa',
    'Sex on Mushroom', 'Alpha Portal', 'Easy Riders',
    'The Unstables', 'Yoni Oshrat', 'Udi Sternberg',
    'Volcano', 'Volcano On Mars', 'Paradise Connection',
    'Jupiter 8000', 'Electric Shiva Universe',
    'Outside The Universe', 'Lo-Fi', 'Gabon', 'Endora',
    'Boris Blenn', 'Roland Wedig', 'Michael Dressler',
    'Everblast', 'Third Ear Audio', 'Water Spirits', 'Dual Head',
    'The Rave Commission', 'TCD', 'Yakov Biton', 'Psykov',
    'Mandelbrot', 'Electric S.U.N.', 'Eli Biton Tal', 'Celli Firmi',
    'Sebastian Claro', 'Tony 2 Toes', 'Sound Farmers', 'Jakan',
    'Jakaan', 'Dennis Stellovic', 'Ido Liran', 'Ari Linker',
]


def sanitize_name(name):
    """Make a filesystem-safe name."""
    return "".join(c for c in name if c.isalpha() or c.isdigit() or c in " .-_").strip()


def normalize(text):
    """Lowercase, strip punctuation/spaces for fuzzy comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())

# Build the normalized set after normalize() is defined
KNOWN_PSYTRANCE_ARTISTS = {normalize(n) for n in _KNOWN_PSYTRANCE_NAMES}


def normalize_artist_aliases(artist_name):
    """Return a set of normalized artist name variants for matching."""
    variants = set()
    norm = normalize(artist_name)
    variants.add(norm)

    # Handle "The " prefix
    if artist_name.lower().startswith('the '):
        variants.add(normalize(artist_name[4:]))

    for short, full in ARTIST_ALIASES.items():
        short_norm = normalize(short)
        full_norm = normalize(full)
        if norm == short_norm or norm == full_norm:
            variants.add(short_norm)
            variants.add(full_norm)
    return variants


def is_psytrance_artist(artist_data):
    """Check if an artist (from MusicBrainz) is likely psytrance/electronic.

    Uses tag matching and a known-artists whitelist.
    """
    name = artist_data.get('name', '')
    norm_name = normalize(name)
    tags = artist_data.get('tag-list', [])
    
    has_positive = False
    neg_tags = []

    for tag in tags:
        tag_name = (tag.get('name', '').lower() if isinstance(tag, dict) 
                    else str(tag).lower())
        if tag_name in PSYTRANCE_TAGS:
            has_positive = True
        if tag_name in DISALLOWED_TAGS:
            neg_tags.append(tag_name)

    # 1. Ambiguous names MUST have positive tags and NO negative tags
    if norm_name in AMBIGUOUS_NAMES:
        return has_positive and not neg_tags

    # 2. Known psytrance whitelist (high confidence for non-ambiguous names)
    if norm_name in KNOWN_PSYTRANCE_ARTISTS:
        # Accept if they have no tags OR positive tags, as long as no negative tags
        return not neg_tags

    # 3. Radical departure check: if it has ANY negative tags, it's out.
    if neg_tags:
        return False

    # 4. Side-project/collaborator safety net: 
    # If they are connected to a known artist (detected via relation description in _filter_related_artists),
    # we allow them to stay even with NO tags, provided they don't have negative tags (checked above).
    # Since this function only sees the artist data, we assume that if we are here
    # and there are NO positive tags, it's only okay if it's a side project.
    # Standard tag check:
    return has_positive or (not tags)  # Permissive for sparsely-tagged artists


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
        self._existing_cache = None
        self._attempted_albums = set()  # Track (artist_norm, album_norm) to skip dupes
        self.slsk_user = self.config_service.get('slsk_user', '')
        self.slsk_pass = self.config_service.get('slsk_pass', '')

    # ─── Library Indexing ─────────────────────────────────────────

    def _build_existing_index(self):
        """Scan the entire downloads tree and build a lookup of what we
        already have.  Keys are normalized 'artistalbum' or
        'artistyearalbum'.
        """
        if self._existing_cache is not None:
            return self._existing_cache

        index = {}
        root = "downloads"
        if not os.path.exists(root):
            self._existing_cache = index
            return index

        # 1. Organized folders
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
                    self._add_album_to_index(index, artist_name, album_name,
                                              album_path, audio_count)

        # 2. Flat files in root
        self._index_flat_root_files(root, index)

        # 3. Unsorted subdirs
        for artist_name in os.listdir(root):
            unsorted_path = os.path.join(root, artist_name, "Unsorted")
            if os.path.isdir(unsorted_path):
                self._index_flat_subdir_files(unsorted_path, index, artist_name)

        # 4. Flat files in artist root folders
        for artist_name in os.listdir(root):
            artist_path = os.path.join(root, artist_name)
            if os.path.isdir(artist_path):
                self._index_flat_subdir_files(artist_path, index, artist_name,
                                              skip_subdirs=True)

        self._existing_cache = index
        self.logger.info(f"Library index built: {len(index)} albums/entries cached.")
        return index

    def _add_album_to_index(self, index, artist_name, album_dir_name, path,
                             audio_count):
        m = re.match(r'^(\d{4})\s*-\s*(.+)$', album_dir_name)
        year = m.group(1) if m else ''
        album_title = m.group(2).strip() if m else album_dir_name

        entry = {'dir': path, 'count': audio_count, 'artist': artist_name,
                 'album': album_title, 'year': year}

        keys = self._album_key_variants(artist_name, album_title, album_dir_name, year)
        for key in keys:
            if key not in index or index[key]['count'] < audio_count:
                index[key] = entry

    def _album_key_variants(self, artist_name, album_title, album_dir_name, year):
        """Generate all reasonable lookup key variants for an album."""
        keys = set()
        clean_title = re.sub(
            r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|'
            r'remix|remastered|live|acoustic).*?\)',
            '', album_title, flags=re.IGNORECASE)
        clean_dir = re.sub(
            r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|'
            r'remix|remastered|live|acoustic).*?\)',
            '', album_dir_name, flags=re.IGNORECASE)
        title_no_the = re.sub(r'^[Tt]he\s+', '', album_title)

        for av in normalize_artist_aliases(artist_name):
            for title in [album_title, clean_title, title_no_the]:
                keys.add(av + normalize(title))
            for dirname in [album_dir_name, clean_dir]:
                keys.add(av + normalize(dirname))
            if year:
                for title in [album_title, clean_title, title_no_the]:
                    keys.add(av + year + normalize(title))
                    keys.add(av + normalize(year + title))
        return keys

    def _index_flat_root_files(self, root, index):
        """Parse flat files in downloads/ root and group by album."""
        album_groups = {}

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
            artist, year, album = self._parse_flat_filename(name)
            if not album:
                continue
            key = f"{artist}|{year}|{album}"
            grp = album_groups.setdefault(key, {
                'files': [], 'artist': artist, 'album': album, 'year': year})
            grp['files'].append(fp)

        for key, group in album_groups.items():
            if len(group['files']) < 2:
                continue
            artist, album, year = group['artist'], group['album'], group['year']
            count = len(group['files'])
            entry = {'dir': root, 'count': count, 'artist': artist,
                     'album': album, 'year': year, 'flat_files': True}
            for av in normalize_artist_aliases(artist):
                for idx_key in [av + normalize(album),
                                av + year + normalize(album)] if year else [av + normalize(album)]:
                    if idx_key not in index or index[idx_key]['count'] < count:
                        index[idx_key] = entry

    def _index_flat_subdir_files(self, subdir, index, artist_name=None,
                                  skip_subdirs=False):
        """Index flat audio files in a subdirectory and group by album."""
        album_groups = {}  # key -> {'artist', 'album', 'year', 'count'}

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
            extracted_artist, year, album = self._parse_flat_filename(name)
            effective_artist = artist_name or extracted_artist
            if not album:
                continue

            # Grouping key for this specific subdirectory
            g_key = f"{normalize(effective_artist)}|{year}|{normalize(album)}"
            if g_key not in album_groups:
                album_groups[g_key] = {
                    'artist': effective_artist,
                    'album': album,
                    'year': year,
                    'count': 0,
                    'dir': subdir
                }
            album_groups[g_key]['count'] += 1

        for g_key, group in album_groups.items():
            count = group['count']
            artist = group['artist']
            album = group['album']
            year = group['year']
            entry = {'dir': subdir, 'count': count, 'artist': artist,
                     'album': album, 'year': year}

            for av in normalize_artist_aliases(artist):
                keys = ([av + normalize(album),
                         av + year + normalize(album)] if year
                        else [av + normalize(album)])
                for idx_key in keys:
                    if idx_key not in index or index[idx_key]['count'] < count:
                        index[idx_key] = entry

    @staticmethod
    def _parse_flat_filename(name):
        """Extract (artist, year, album) from a flat filename.

        Handles patterns like:
          Artist - Year - Album - TrackNum - Title
          Artist - Album - TrackNum - Title
        """
        # Pattern: Artist - Year - Album - TrackNum …
        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+?)\s*-\s*\d+', name)
        if m:
            artist = m.group(1).strip()
            year = m.group(2)
            album = re.sub(r'\s+\d+$', '', m.group(3).strip())
            return artist, year, album

        # Pattern: Artist - Album - TrackNum …
        m = re.match(r'^(.+?)\s*-\s*(.+?)\s*-\s*\d+\s*[-.]', name)
        if m:
            artist = m.group(1).strip()
            album = m.group(2).strip()
            return artist, '', album

        return '', '', ''

    def _count_audio_files(self, directory):
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
        """Check if a complete album already exists locally."""
        index = self._build_existing_index()

        candidates = set()
        title_no_the = re.sub(r'^[Tt]he\s+', '', album_title)
        clean_title = re.sub(
            r'\s*\(.*?(deluxe|remaster|edition|expanded|bonus|special|'
            r'remix|remastered|live|acoustic).*?\)',
            '', album_title, flags=re.IGNORECASE)

        for av in normalize_artist_aliases(artist_name):
            for title in [album_title, clean_title, title_no_the]:
                candidates.add(av + normalize(title))
                if year:
                    candidates.add(av + year + normalize(title))
                    candidates.add(av + normalize(year + title))

        for key in candidates:
            if key in index:
                entry = index[key]
                if entry['count'] >= 3:
                    return entry
                # If it's in a library folder (not root downloads), still require
                # a reasonable track count to avoid skipping due to single tracks.
                # (EPs usually have 3+ tracks anyway)
                if entry['count'] >= 3 and entry.get('dir', '') != 'downloads':
                    return entry

        # Substring fallback
        title_norm = normalize(album_title)
        for av in normalize_artist_aliases(artist_name):
            for key, entry in index.items():
                if av in key and title_norm in key and entry['count'] >= 3:
                    return entry

        # Exact directory check
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
        self._existing_cache = None

    # ─── Managed Artists ──────────────────────────────────────────

    async def get_managed_artists(self):
        """Returns the list of managed artists, prepopulating from disk if empty."""
        db_artists = self.queue_service.get_managed_artists()

        if not db_artists:
            # Prepopulate from downloads folder
            root = "downloads"
            if os.path.exists(root):
                self.logger.info("Prepopulating managed artists from downloads folder...")
                for artist_name in os.listdir(root):
                    artist_path = os.path.join(root, artist_name)
                    if os.path.isdir(artist_path):
                        # Simple check: does it have any subdirectories (albums)?
                        if any(os.path.isdir(os.path.join(artist_path, d)) for d in os.listdir(artist_path)):
                            try:
                                artists = await asyncio.to_thread(self.mb_service.search_artist, artist_name)
                                if artists:
                                    best = self._pick_best_artist(artists, artist_name)
                                    self.queue_service.add_managed_artist(best['id'], best['name'])
                            except Exception as e:
                                self.logger.warning(f"Failed to resolve artist {artist_name} during prepopulation: {e}")
                db_artists = self.queue_service.get_managed_artists()

        active = [a for a in db_artists if not a['is_secondary']]
        secondary = [a for a in db_artists if a['is_secondary']]
        return {"active": active, "secondary": secondary}

    async def add_managed_artist(self, artist_id: str, name: str, is_secondary: bool = False):
        self.queue_service.add_managed_artist(artist_id, name, is_secondary)
        # If we added a primary artist, also find and add related artists as secondary
        if not is_secondary:
            try:
                related = await asyncio.to_thread(self.mb_service.get_related_artists, artist_id, 1)
                related = self._filter_related_artists(related, name)
                for r in related:
                    # Only add as secondary if not already in the list
                    self.queue_service.add_managed_artist(r['id'], r['name'], is_secondary=True)
            except Exception as e:
                self.logger.warning(f"Failed to fetch related artists for {name}: {e}")

    async def remove_managed_artist(self, artist_id: str):
        self.queue_service.remove_managed_artist(artist_id)

    async def cleanup_managed_artists(self):
        """Re-filter the entire managed list and remove non-genre artists."""
        self.logger.info("🧹 Starting database cleanup...")
        db_artists = self.queue_service.get_managed_artists()
        removed = 0
        
        for artist in db_artists:
            aid = artist['artist_id']
            name = artist['name']
            
            # Fetch fresh tags for the artist
            full_info = await asyncio.to_thread(self.mb_service.get_artist_by_id, aid)
            if not full_info or not is_psytrance_artist(full_info):
                self.logger.info(f"  🗑 Removing {name} (failed genre check)")
                self.queue_service.remove_managed_artist(aid)
                removed += 1
                
        self.logger.info(f"✨ Cleanup complete. Removed {removed} artists.")
        return removed

    async def get_artist_discography_details(self, artist_id: str):
        """Returns detailed discography for an artist with track-level comparison."""
        artist_info = await asyncio.to_thread(self.mb_service.get_artist_by_id, artist_id)
        if not artist_info:
            return {"error": "Artist not found"}

        artist_name = artist_info['name']
        rgs = await asyncio.to_thread(self.mb_service.get_discography, artist_id)
        
        discography = []
        for rg in rgs:
            year = rg.get('first-release-date', '')[:4] or "Unknown"
            title = rg['title']
            rg_id = rg['id']
            
            existing = self.album_exists_on_disk(artist_name, title, year)
            
            status = "Missing"
            local_files = []
            missing_tracks = []
            
            if existing:
                status = "Complete" # Default if existing
                target_dir = existing['dir']
                if os.path.exists(target_dir):
                    local_files = [f for f in os.listdir(target_dir) if f.lower().endswith(tuple(AUDIO_EXTENSIONS))]
                
                # For track-level comparison, we need the official tracklist
                release = await asyncio.to_thread(self.mb_service.get_best_release_with_tracks, rg_id)
                if release:
                    official_tracks = []
                    for medium in release.get('medium-list', []):
                        for track in medium.get('track-list', []):
                            track_title = track.get('recording', {}).get('title', 'Unknown Track')
                            official_tracks.append(track_title)
                    
                    # Fuzzy match local files against official tracks
                    found_tracks = []
                    for track in official_tracks:
                        norm_track = normalize(track)
                        found = False
                        for f in local_files:
                            if norm_track in normalize(f):
                                found = True
                                break
                        if found:
                            found_tracks.append(track)
                        else:
                            missing_tracks.append(track)
                    
                    if missing_tracks:
                        status = "Partial"
                    elif len(found_tracks) >= len(official_tracks):
                        status = "Complete"
            
            discography.append({
                "id": rg_id,
                "title": title,
                "year": year,
                "status": status,
                "local_files": local_files,
                "missing_tracks": missing_tracks
            })

        return {
            "artist": artist_name,
            "discography": discography
        }

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

            # If no results, or none match the psytrance scene, try
            # alternative query forms (remove spaces, use aliases)
            if not artists or not any(
                    is_psytrance_artist(a) or
                    normalize(a.get('name', '')) in KNOWN_PSYTRANCE_ARTISTS
                    for a in artists):
                alt_queries = self._artist_query_alternatives(artist_name)
                for alt in alt_queries:
                    self.logger.info(
                        f"  Retrying search as: {alt}")
                    alt_results = await asyncio.to_thread(
                        self.mb_service.search_artist, alt)
                    if alt_results and any(
                            is_psytrance_artist(a) or
                            normalize(a.get('name', '')) in KNOWN_PSYTRANCE_ARTISTS
                            for a in alt_results):
                        artists = alt_results
                        break

            if not artists:
                self.logger.warning(f"Artist not found: {artist_name}")
                continue

            # Pick the best match — prefer known psytrance artists
            main = self._pick_best_artist(artists, artist_name)
            
            # Final genre guard before fetching releases
            if not is_psytrance_artist(main):
                self.logger.info(f"  ⊘ Skip {main['name']} (does not match genre profile)")
                continue

            if main['id'] in seen_ids:
                self.logger.info(f"  {main['name']} already scanned, skipping.")
                continue
            seen_ids.add(main['id'])

            related = []
            if depth > 0:
                self.logger.info("Finding related artists...")
                related = await asyncio.to_thread(
                    self.mb_service.get_related_artists, main['id'], depth)
                # Filter out artists that are clearly not psytrance
                before = len(related)
                related = self._filter_related_artists(related, main['name'])
                after = len(related)
                if before != after:
                    self.logger.info(
                        f"  Filtered related: {before} → {after} "
                        f"(removed {before - after} non-genre artists)")

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

    def _pick_best_artist(self, artists, query):
        """From a list of MB search results, pick the one most likely
        to be the artist the user intended.  Prefers known psytrance
        artists, then those with psytrance tags, then exact-name matches.
        """
        query_norm = normalize(query)
        # 1. High-confidence whitelist
        for a in artists:
            if normalize(a.get('name', '')) in KNOWN_PSYTRANCE_ARTISTS:
                return a
        # 2. Genre tag match (is_psytrance_artist returns has_positive and not has_negative)
        for a in artists:
            if is_psytrance_artist(a):
                return a
        # 3. Exact name match
        for a in artists:
            if normalize(a.get('name', '')) == query_norm:
                return a
        # 4. Fallback to first result
        return artists[0]

    @staticmethod
    def _artist_query_alternatives(artist_name):
        """Generate alternative MB search queries for an artist name.

        For example 'Kox Box' → ['Koxbox', 'Kox-Box'],
        'DJ Stryker' → ['Stryker'], etc.
        """
        alts = []
        # Remove spaces: "Kox Box" → "Koxbox"
        collapsed = re.sub(r'\s+', '', artist_name)
        if collapsed != artist_name:
            alts.append(collapsed)
        # Replace spaces with hyphens
        hyphenated = re.sub(r'\s+', '-', artist_name)
        if hyphenated not in alts and hyphenated != artist_name:
            alts.append(hyphenated)
        # Try without "DJ " prefix
        no_dj = re.sub(r'^DJ\s+', '', artist_name, flags=re.IGNORECASE)
        if no_dj != artist_name:
            alts.append(no_dj)
        # Check aliases — search by the other name
        norm = normalize(artist_name)
        for short, full in ARTIST_ALIASES.items():
            if norm == normalize(short):
                if full not in alts and full != artist_name:
                    alts.append(full)
            elif norm == normalize(full):
                if short not in alts and short != artist_name:
                    alts.append(short)
        return alts

    def _filter_related_artists(self, related, main_artist_name):
        """Remove related artists that are clearly not in the same genre."""
        filtered = []
        for artist in related:
            name = artist.get('name', 'Unknown')
            # 1. Check tags/whitelist first
            if is_psytrance_artist(artist):
                filtered.append(artist)
                continue

            # 2. If it failed is_psytrance_artist, check if it was specifically REJECTED
            # due to radical genre tags.
            tags = artist.get('tag-list', [])
            neg_tags = [
                (t.get('name', '').lower() if isinstance(t, dict) else str(t).lower())
                for t in tags
                if (t.get('name', '').lower() if isinstance(t, dict) else str(t).lower()) in DISALLOWED_TAGS
            ]
            if neg_tags:
                self.logger.info(f"  ⊘ Skip {name} (wrong genre: {', '.join(neg_tags)})")
                continue

            # 3. Fallback to "member of" side project rule for sparsely tagged projects
            # If it has no tags (sparsely tagged) but is a side project of a psy artist, keep it.
            rel = artist.get('relation', '')
            if 'member' in rel.lower() or 'involving' in rel.lower():
                # Conservative: only keep if the main artist IS in the whitelist
                if normalize(main_artist_name) in KNOWN_PSYTRANCE_ARTISTS:
                    filtered.append(artist)
                    continue
            
            # Default skip if it didn't meet any criteria
            # self.logger.info(f"  ⊘ Skip {name} (unverified genre/connection)")
        return filtered

    # ─── Autonomous Filler ────────────────────────────────────────

    async def run_autonomous_filler(self, slsk_user, slsk_pass, artist_names,
                                     depth=1, dry_run=False):
        """Autonomous filler that processes one or more artists in a persistent loop."""
        if isinstance(artist_names, str):
            artist_names = [artist_names]

        self.logger.info("=== Autonomous Collection Filler (Persistent Mode) ===")
        self.logger.info(f"Artists: {', '.join(artist_names)}")

        self.is_running = True
        self.should_stop = False
        self.is_paused = False

        try:
            while not self.should_stop:
                self.invalidate_cache()
                self.logger.info("Scanning library for gaps...")
                result_tree = await self.scan_artists(artist_names, depth)

                if not result_tree:
                    self.logger.warning("No artists found.")
                    break

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
                    self.logger.info("✨ Library is complete — no gaps found!")
                    break

                self.logger.info(
                    f"Found {total_missing} missing albums across {len(missing)} artists.")

                # Run a single download pass
                await self._run_job_impl(
                    artist_names=artist_names,
                    slsk_user=slsk_user,
                    slsk_pass=slsk_pass,
                    dry_run=dry_run,
                    related_artist_depth=depth,
                    selection=missing
                )

                if self.should_stop:
                    break

                self.logger.info("Pass complete. Cooldown for 10 minutes before retrying remaining gaps...")
                # Wait in small increments to remain responsive to stop signals
                for _ in range(600):
                    if self.should_stop:
                        break
                    await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Autonomous filler fatal error: {e}")
        finally:
            self.is_running = False
            self.should_stop = False
            self.logger.info("=== Autonomous Filler Stopped ===")

    # ─── Main Download Engine ─────────────────────────────────────

    async def start_download(self, artist_names, slsk_user, slsk_pass,
                              dry_run=False, related_artist_depth=1,
                              selection=None):
        """Standard single-pass download job."""
        if self.is_running:
            self.logger.warning("Job already running.")
            return

        self.is_running = True
        try:
            await self._run_job_impl(
                artist_names, slsk_user, slsk_pass, dry_run,
                related_artist_depth, selection
            )
        finally:
            self.is_running = False

    async def _run_job_impl(self, artist_names, slsk_user, slsk_pass,
                             dry_run=False, related_artist_depth=1,
                             selection=None):
        """The actual core of the download engine."""
        if isinstance(artist_names, str):
            artist_names = [artist_names]

        self.invalidate_cache()
        self._attempted_albums = set()  # Reset per-job dedup
        self.should_stop = False
        self.is_paused = False

        if slsk_user != self.slsk_user or slsk_pass != self.slsk_pass:
            self.config_service.set('slsk_user', slsk_user)
            self.config_service.set('slsk_pass', slsk_pass)
            self.slsk_user = slsk_user
            self.slsk_pass = slsk_pass

        if dry_run:
            self.logger.info("*** DRY RUN MODE ***")

        try:
            self.logger.info("Connecting to Soulseek...")
            await self.slsk_service.connect(slsk_user, slsk_pass)
            self.logger.info("Connected.")

            if selection:
                artists_to_process = selection
            else:
                seen = set()
                artists_to_process = []
                for name in artist_names:
                    found = await asyncio.to_thread(
                        self.mb_service.search_artist, name)
                    if not found:
                        self.logger.warning(
                            f"Artist not found on MusicBrainz: {name}")
                        continue
                    main = self._pick_best_artist(found, name)
                    if main['id'] in seen:
                        continue
                    seen.add(main['id'])
                    self.logger.info(f"Found: {main['name']} ({main['id']})")
                    artists_to_process.append({
                        'id': main['id'], 'name': main['name']})

                    if related_artist_depth > 0:
                        self.logger.info(
                            f"Finding related artists (depth={related_artist_depth})...")
                        related = await asyncio.to_thread(
                            self.mb_service.get_related_artists,
                            main['id'], related_artist_depth)
                        related = self._filter_related_artists(
                            related, main['name'])
                        for a in related:
                            if a['id'] not in seen:
                                seen.add(a['id'])
                                artists_to_process.append({
                                    'id': a['id'], 'name': a['name']})

            self.logger.info(f"Processing {len(artists_to_process)} artist(s).")

            for artist in artists_to_process:
                if self.should_stop:
                    break
                await self._process_artist(artist, dry_run,
                                            artist.get('albums'))

            if self.should_stop:
                self.logger.info("Job stopped by user.")
            else:
                self.logger.info(
                    "Pass complete. Waiting for final downloads...")
                while self.active_downloads and not self.should_stop:
                    await asyncio.sleep(2)

        except Exception as e:
            self.logger.error(f"Download pass error: {e}")
        finally:
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

            # ── Cross-artist dedup: skip if we already tried this album ──
            album_norm = normalize(title)
            artist_norm = normalize(name)
            dedup_key = f"{artist_norm}:{album_norm}"
            if dedup_key in self._attempted_albums:
                self.logger.info(f"  ⊘ Skip {title} (already attempted)")
                continue
            self._attempted_albums.add(dedup_key)

            # ── Check 1: Already completed this session
            if self._is_session_completed(name, title):
                self.logger.info(f"  ⊘ Skip {title} (completed this session)")
                continue

            # ── Check 2: Already on disk
            existing = self.album_exists_on_disk(name, title, year)
            if existing:
                self.logger.info(
                    f"  ⊘ Skip {title} ({existing['count']} tracks on disk)")
                self.queue_service.add_completed({
                    'artist': name, 'album': title,
                    'year': year, 'path': existing['dir'],
                    'status': 'Existing'
                })
                continue

            self.logger.info(f"  ↓ [{idx+1}/{len(rgs)}] {title} ({year})")

            # ── Search with adaptive timeout ──
            success = False
            queries = self._build_queries(name, title, year)

            for attempt, query in enumerate(queries):
                if success or self.should_stop:
                    break

                # Adaptive timeout: first 3 queries get full 20s,
                # later queries get 10s (they're longshots anyway)
                timeout = 20 if attempt < 3 else 10

                self.logger.info(
                    f"  Searching ({attempt+1}/{len(queries)}): {query}")
                results = await self.slsk_service.search(query, timeout=timeout)
                self.logger.info(f"  Got {len(results)} results")

                if not results:
                    if attempt < len(queries) - 1:
                        await asyncio.sleep(0.5)
                    continue

                candidates = self._rank_candidates(results, artist_name=name)
                if not candidates:
                    if attempt < len(queries) - 1:
                        await asyncio.sleep(0.5)
                    continue

                # Try top 5 candidates
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
                        self.logger.info(
                            f"  [Dry Run] Would download → {target_dir}")
                        success = True
                        break

                    try:
                        meta = {
                            'artist': name, 'album': title,
                            'year': year, 'mb_release_group_id': rg['id']
                        }
                        await self._download_sequential(
                            user, files, target_dir, meta)
                        
                        # Verify we actually got files before marking as success
                        if self._count_audio_files(target_dir) > 0:
                            success = True
                            self.queue_service.add_completed({
                                'artist': name, 'album': title,
                                'year': year, 'path': target_dir,
                                'status': 'Downloaded'
                            })
                            self.invalidate_cache()
                        else:
                            self.logger.warning(f"  Candidate {user} finished but no files were saved.")
                            self._cleanup_dir(target_dir)
                    except Exception as e:
                        self.logger.warning(f"  Candidate failed: {e}")
                        self._cleanup_partial(target_dir)
                        await asyncio.sleep(2)

                if not success and attempt < len(queries) - 1:
                    await asyncio.sleep(0.5)

            if not success:
                if not self.should_stop:
                    self.logger.warning(f"  ✗ Failed: {title}")
                self._cleanup_dir(target_dir)
            else:
                self.logger.info(f"  ✓ Album complete: {year} - {title}")

    def _build_queries(self, artist, title, year=""):
        """Build a prioritized list of search queries.

        Starts specific, gets broader.  Handles slash-separated
        double-album titles by searching each half separately.
        """
        # Handle slash titles: "Title A / Title B" → try each half
        title_parts = [title]
        if '/' in title:
            parts = [p.strip() for p in title.split('/') if p.strip()]
            title_parts = parts + [title]  # Try each half first, then full

        clean = lambda t: re.sub(r'[^a-zA-Z0-9 ]', '', t)
        queries = []

        for t in title_parts:
            ct = clean(t)
            queries.extend([
                f"{artist} {t}",              # Full specific
                f"{artist} {t} FLAC",         # Format hint
            ])
            if year:
                queries.append(f"{artist} {year} {t}")
            queries.extend([
                f"{artist} {ct}",             # Cleaned title
                t,                            # Album title alone
                f"{ct} FLAC",                 # Cleaned + format
            ])

        # Add alias-based queries
        norm = normalize(artist)
        for short, full in ARTIST_ALIASES.items():
            if norm == normalize(short):
                for t in title_parts[:2]:  # Only first 2 title variants
                    queries.insert(3, f"{full} {t}")
                    if year:
                        queries.insert(4, f"{full} {year} {t}")
            elif norm == normalize(full):
                for t in title_parts[:2]:
                    queries.insert(3, f"{short} {t}")
                    if year:
                        queries.insert(4, f"{short} {year} {t}")

        # Deduplicate preserving order
        seen = set()
        unique = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)

        return unique

    def _build_query(self, artist, title, attempt):
        """Legacy single-query builder."""
        queries = self._build_queries(artist, title)
        return queries[attempt] if attempt < len(queries) else title

    def _is_session_completed(self, artist, album):
        return any(
            c['artist'] == artist and c['album'] == album
            and c['status'] in ('Downloaded', 'Queued')
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
        artist_norms = normalize_artist_aliases(
            artist_name) if artist_name else set()

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
                    score += 80 if avg >= 320 else (60 if avg >= 190 else -50)
            else:
                if '.mp3' in formats:
                    bitrates = [f['bitrate'] for f in audio if f['bitrate']]
                    avg = sum(bitrates) / len(bitrates) if bitrates else 0
                    score += 200 if avg >= 320 else (80 if avg >= 190 else 40)
                elif '.flac' in formats:
                    score += 100

            # File count
            if 4 <= num_files <= 20:
                score += num_files * 10
            elif 2 <= num_files <= 3:
                score += 20
            elif num_files > 20:
                score -= (num_files - 20) * 15

            # Artist folder match with aliases
            if artist_norms:
                folder_norm = re.sub(r'[^a-z0-9]', '', data['folder'].lower())
                if any(a_norm in folder_norm for a_norm in artist_norms):
                    score += 50
                else:
                    score -= 80

            # Free slots bonus
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
        os.makedirs(target_dir, exist_ok=True)

        to_download = [
            f for f in candidate_files
            if f['extension'].lower() in AUDIO_EXTENSIONS
            or f['extension'].lower() in ('.jpg', '.png')
        ]
        if not to_download:
            raise Exception("No audio files in candidate")

        existing_files = (set(os.listdir(target_dir))
                          if os.path.exists(target_dir) else set())
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
            safe_filename = re.sub(r'[<>:"|?*]', '', filename)
            if safe_filename != filename:
                self.logger.info(f"  Sanitized: {safe_filename}")
            filename = safe_filename

            local_target = os.path.join(target_dir, filename)
            if (os.path.exists(local_target) and
                    os.path.getsize(local_target) > MIN_FILE_SIZE):
                self.logger.info(
                    f"  [{i+1}/{total}] Skip (exists): {filename}")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures = 0
                continue

            self.logger.info(f"  [{i+1}/{total}] ↓ {filename}")

            try:
                transfer = await self.slsk_service.download_file(
                    user, remote_path)
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
                    raise Exception(
                        f"User {user} unreliable after "
                        f"{MAX_CONSECUTIVE_FAILURES} failures")
            else:
                self.logger.warning(f"  [{i+1}/{total}] ⏱ Timeout")
                self.album_tracker[target_dir]['done'] += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise Exception(
                        f"User {user} too slow after "
                        f"{MAX_CONSECUTIVE_FAILURES} timeouts")

        self._finalize_album(target_dir)

    async def _wait_for_transfer(self, transfer, timeout=180):
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
            # Count actual audio files in directory to ensure we actually got something
            audio_count = self._count_audio_files(target_dir)
            
            if audio_count > 0:
                self.logger.info(
                    f"  ✓ Album complete: {os.path.basename(target_dir)}")
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self.post_processor.process_album(
                            target_dir, info['metadata']))
                except RuntimeError:
                    try:
                        asyncio.create_task(
                            self.post_processor.process_album(
                                target_dir, info['metadata']))
                    except RuntimeError:
                        self.logger.warning(
                            f"Could not schedule post-processing for "
                            f"{target_dir} (no event loop)")
            else:
                self.logger.warning(
                    f"  ✗ Failed: {os.path.basename(target_dir)} (no files downloaded)")
            
            del self.album_tracker[target_dir]

    # ─── Legacy Monitor ───────────────────────────────────────────

    async def monitor_downloads(self):
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
        return self._rank_candidates(results)
