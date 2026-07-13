import json
import musicbrainzngs
import os
import sqlite3
import time
import socket
from typing import List, Dict, Any, Optional

# Enforce a global socket timeout so musicbrainzngs requests don't hang indefinitely
socket.setdefaulttimeout(15)

# Configure MusicBrainz
musicbrainzngs.set_useragent(
    "DiscographyDownloader", "0.1", "https://github.com/jules/discography-downloader"
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MB_CACHE_DB = os.path.join(BASE_DIR, "data", "mb_cache.db")


class MusicBrainzService:
    def __init__(self):
        self._init_cache()
        self._cache_hits = 0
        self._cache_misses = 0

    def _init_cache(self):
        """Create the cache table if it doesn't exist."""
        os.makedirs(os.path.dirname(MB_CACHE_DB), exist_ok=True)
        conn = sqlite3.connect(MB_CACHE_DB, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_expires
            ON cache(expires_at)
        """)
        conn.commit()
        conn.close()

    def _cache_get(self, key: str) -> Optional[Any]:
        """Get a cached value if it exists and hasn't expired."""
        try:
            conn = sqlite3.connect(MB_CACHE_DB, timeout=10)
            conn.execute("PRAGMA busy_timeout=5000")
            row = conn.execute(
                "SELECT value FROM cache WHERE key = ? AND expires_at > ?",
                (key, time.time()),
            ).fetchone()
            conn.close()
            if row:
                self._cache_hits += 1
                return json.loads(row[0])
        except Exception:
            pass
        self._cache_misses += 1
        return None

    def _cache_set(self, key: str, value: Any, ttl_seconds: float):
        """Store a value in the cache with expiration."""
        try:
            conn = sqlite3.connect(MB_CACHE_DB, timeout=10)
            conn.execute("PRAGMA busy_timeout=5000")
            now = time.time()
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (key, json.dumps(value, default=str), now + ttl_seconds, now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"MB cache write error: {e}")

    def cache_stats(self) -> Dict[str, Any]:
        """Return cache hit/miss stats."""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
        try:
            conn = sqlite3.connect(MB_CACHE_DB, timeout=10)
            count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at < ?", (time.time(),)
            ).fetchone()[0]
            conn.close()
        except Exception:
            count = 0
            expired = 0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "entries": count,
            "expired": expired,
        }

    def clear_expired(self):
        """Remove expired entries from the cache."""
        try:
            conn = sqlite3.connect(MB_CACHE_DB, timeout=10)
            cur = conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
            conn.commit()
            deleted = cur.rowcount
            conn.close()
            print(f"MB cache: cleared {deleted} expired entries")
            return deleted
        except Exception as e:
            print(f"MB cache cleanup error: {e}")
            return 0

    def search_artist(self, query: str) -> List[Dict[str, Any]]:
        """Search for an artist by name (cached 30 days)."""
        cache_key = f"search_artist:{query}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            result = musicbrainzngs.search_artists(artist=query, limit=5)
            data = result.get("artist-list", [])
            self._cache_set(cache_key, data, ttl_seconds=30 * 86400)
            return data
        except Exception as e:
            print(f"Error searching artist: {e}")
            return []

    def get_artist_by_id(
        self, artist_id: str, includes: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get artist details by ID (cached 30 days)."""
        if includes is None:
            includes = ["artist-rels", "url-rels", "tags"]

        includes_key = ",".join(sorted(includes))
        cache_key = f"get_artist_by_id:{artist_id}:{includes_key}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            time.sleep(1.1)
            response = musicbrainzngs.get_artist_by_id(artist_id, includes=includes)
            data = response.get("artist")
            if data:
                self._cache_set(cache_key, data, ttl_seconds=30 * 86400)
            return data
        except Exception as e:
            print(f"Error getting artist details for {artist_id}: {e}")
            return None

    def get_discography(
        self, artist_id: str, cancel_event: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """Get all official Release Groups for an artist (cached 7 days)."""
        cache_key = f"get_discography:{artist_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        release_groups = []
        offset = 0
        limit = 100

        while True:
            if cancel_event is not None and cancel_event():
                print(f"[get_discography] Cancelled for {artist_id}")
                break

            try:
                time.sleep(1.1)
                result = musicbrainzngs.browse_release_groups(
                    artist=artist_id,
                    release_type=["album", "ep", "single"],
                    limit=limit,
                    offset=offset,
                )
                batch = result.get("release-group-list", [])
                release_groups.extend(rg for rg in batch)

                if len(batch) < limit:
                    break
                offset += len(batch)
            except Exception as e:
                print(f"Error fetching discography: {e}")
                break

        if release_groups:
            self._cache_set(cache_key, release_groups, ttl_seconds=7 * 86400)
        return release_groups

    def get_releases_in_group(self, rg_id: str) -> List[Dict[str, Any]]:
        """Get specific releases for a Release Group (cached 14 days)."""
        cache_key = f"get_releases_in_group:{rg_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            time.sleep(1.1)
            result = musicbrainzngs.browse_releases(
                release_group=rg_id, includes=["media"], limit=100
            )
            data = result.get("release-list", [])
            self._cache_set(cache_key, data, ttl_seconds=14 * 86400)
            return data
        except Exception as e:
            print(f"Error fetching releases for group {rg_id}: {e}")
            return []

    def get_best_release_with_tracks(self, rg_id: str) -> Optional[Dict[str, Any]]:
        """Find the best release in a group with full tracklist (cached 14 days)."""
        cache_key = f"get_best_release:{rg_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        releases = self.get_releases_in_group(rg_id)
        if not releases:
            return None

        official = [r for r in releases if r.get("status") == "Official"]
        candidates = official if official else releases

        def get_track_count(rel):
            count = 0
            for medium in rel.get("medium-list", []):
                count += int(medium.get("track-count", 0))
            return count

        candidates.sort(key=get_track_count, reverse=True)

        best_release = candidates[0]
        release_id = best_release["id"]

        try:
            time.sleep(1.1)
            result = musicbrainzngs.get_release_by_id(
                release_id, includes=["recordings", "media"]
            )
            data = result.get("release")
            if data:
                self._cache_set(cache_key, data, ttl_seconds=14 * 86400)
            return data
        except Exception as e:
            print(f"Error fetching release details {release_id}: {e}")
            return None

    def get_related_artists(
        self, artist_id: str, depth: int = 1
    ) -> List[Dict[str, Any]]:
        """Find related artists recursively (cached 14 days)."""
        cache_key = f"get_related_artists:{artist_id}:d{depth}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if depth <= 0:
            return []

        found_artists = {}
        visited = set([artist_id])

        def add_artist(artist_data, relation_desc):
            aid = artist_data.get("id")
            if aid and aid not in found_artists and aid not in visited:
                full_info = self.get_artist_by_id(aid, includes=["tags"])
                tags = []
                if full_info:
                    tags = full_info.get("tag-list", [])

                found_artists[aid] = {
                    "id": aid,
                    "name": artist_data.get("name"),
                    "relation": relation_desc,
                    "type": artist_data.get("type"),
                    "tag-list": tags,
                }

        def traverse(current_id, current_depth, is_member_of_original_band=False):
            if current_depth > depth:
                return

            visited.add(current_id)
            artist_info = self.get_artist_by_id(current_id, includes=["artist-rels"])
            if not artist_info:
                return

            a_type = artist_info.get("type")
            relations = artist_info.get("artist-relation-list", [])

            members_to_check = []

            if a_type == "Group":
                for rel in relations:
                    if (
                        rel.get("type") == "member of band"
                        and rel.get("direction") == "backward"
                    ):
                        member = rel.get("artist", {})
                        members_to_check.append((member, True))
                        if current_depth == 1:
                            add_artist(member, f"Member of {artist_info.get('name')}")
            elif a_type == "Person":
                members_to_check.append((artist_info, False))

            for person, is_member in members_to_check:
                pid = person.get("id")
                pname = person.get("name")

                person_rels = []
                if pid == current_id:
                    person_rels = relations
                else:
                    p_details = self.get_artist_by_id(pid, includes=["artist-rels"])
                    if p_details:
                        person_rels = p_details.get("artist-relation-list", [])

                for rel in person_rels:
                    if (
                        rel.get("type") == "member of band"
                        and rel.get("direction") != "backward"
                    ):
                        target = rel.get("artist", {})
                        tid = target.get("id")
                        if tid and tid not in visited:
                            add_artist(target, f"Band involving {pname}")
                            traverse(tid, current_depth + 1)

        traverse(artist_id, 1)

        result = list(found_artists.values())
        if result:
            self._cache_set(cache_key, result, ttl_seconds=14 * 86400)
        return result
