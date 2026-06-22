import musicbrainzngs
import time
from typing import List, Dict, Any, Optional

# Configure MusicBrainz
musicbrainzngs.set_useragent(
    "DiscographyDownloader", "0.1", "https://github.com/jules/discography-downloader"
)


class MusicBrainzService:
    def __init__(self):
        pass

    def search_artist(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for an artist by name.
        """
        try:
            # musicbrainzngs.search_artists returns {'artist-list': [], 'artist-count': ...}
            result = musicbrainzngs.search_artists(artist=query, limit=5)
            return result.get("artist-list", [])
        except Exception as e:
            print(f"Error searching artist: {e}")
            return []

    def get_artist_by_id(
        self, artist_id: str, includes: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            if includes is None:
                includes = ["artist-rels", "url-rels", "tags"]

            # Rate limit before call
            time.sleep(1.1)
            response = musicbrainzngs.get_artist_by_id(artist_id, includes=includes)
            return response.get("artist")
        except Exception as e:
            print(f"Error getting artist details for {artist_id}: {e}")
            return None

    def get_discography(
        self, artist_id: str, cancel_event: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all official Release Groups (Albums/EPs) for an artist.

        If *cancel_event* is provided (a no-arg callable that returns True
        when cancellation is requested), this method will bail early between
        pages so orphan threads from timed-out to_thread() calls don't keep
        running.
        """
        release_groups = []
        offset = 0
        limit = 100

        while True:
            # Check cancellation between pages
            if cancel_event is not None and cancel_event():
                print(f"[get_discography] Cancelled for {artist_id}")
                break

            try:
                time.sleep(1.1)
                result = musicbrainzngs.browse_release_groups(
                    artist=artist_id,
                    release_type=["album", "ep"],
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

        return release_groups

    def get_releases_in_group(self, rg_id: str) -> List[Dict[str, Any]]:
        """
        Get specific releases (e.g. CD, Digital) for a Release Group.
        Useful to find track counts and specific formats.
        """
        try:
            time.sleep(1.1)
            result = musicbrainzngs.browse_releases(
                release_group=rg_id, includes=["media"], limit=100
            )
            return result.get("release-list", [])
        except Exception as e:
            print(f"Error fetching releases for group {rg_id}: {e}")
            return []

    def get_best_release_with_tracks(self, rg_id: str) -> Optional[Dict[str, Any]]:
        """
        Find the 'best' release in a group (prioritizing Official, CD/Digital, Track Count)
        and return it with full tracklist.
        """
        releases = self.get_releases_in_group(rg_id)
        if not releases:
            return None

        # Sort/Filter logic
        # 1. Prefer Official
        official = [r for r in releases if r.get("status") == "Official"]
        candidates = official if official else releases

        # 2. Prefer specific formats (CD, Digital Media) over Vinyl/Cassette usually (for metadata quality/track count consistency)
        # But maybe we just want the one with the most tracks?
        # Let's sort by track count desc
        def get_track_count(rel):
            count = 0
            for medium in rel.get("medium-list", []):
                count += int(medium.get("track-count", 0))
            return count

        candidates.sort(key=get_track_count, reverse=True)

        best_release = candidates[0]
        release_id = best_release["id"]

        # Fetch full details with recordings
        try:
            time.sleep(1.1)
            result = musicbrainzngs.get_release_by_id(
                release_id, includes=["recordings", "media"]
            )
            return result.get("release")
        except Exception as e:
            print(f"Error fetching release details {release_id}: {e}")
            return None

    def get_related_artists(
        self, artist_id: str, depth: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Find related bands/projects via members recursively up to the given depth.
        Returns a list of dicts: {'id', 'name', 'relation_type', 'related_to', 'tag-list'}
        """
        if depth <= 0:
            return []

        found_artists = {}  # id -> dict
        visited = set([artist_id])

        def add_artist(artist_data, relation_desc):
            aid = artist_data.get("id")
            if aid and aid not in found_artists and aid not in visited:
                # Fetch full artist info to get tags for filtering
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

        return list(found_artists.values())
