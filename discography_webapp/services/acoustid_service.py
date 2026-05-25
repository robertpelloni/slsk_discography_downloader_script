import asyncio
import os
import sqlite3
import json
import acoustid
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")

class AcoustidService:
    def __init__(self, api_key: str, logger):
        self.api_key = api_key
        self.logger = logger
        self._init_db()

    def _init_db(self):
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS acoustid_cache (
                        file_hash TEXT PRIMARY KEY,
                        match_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            self.logger.error(f"AcoustID Cache: DB init error: {e}")

    def _get_file_id(self, filepath: str) -> str:
        """Generate a stable ID for the file based on path and size."""
        try:
            stat = os.stat(filepath)
            return f"{os.path.basename(filepath)}|{stat.st_size}"
        except Exception:
            return filepath

    async def identify_file(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Identify an audio file using AcoustID fingerprinting."""
        if not self.api_key:
            self.logger.warning("AcoustID API key not configured. Skipping identification.")
            return None

        file_id = self._get_file_id(filepath)

        # 1. Check Cache
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT match_data FROM acoustid_cache WHERE file_hash = ?", (file_id,)).fetchone()
                if row:
                    self.logger.info(f"AcoustID: Cache hit for {os.path.basename(filepath)}")
                    return json.loads(row['match_data'])
        except Exception as e:
            self.logger.warning(f"AcoustID Cache: Read error: {e}")

        # 2. Perform Identification
        try:
            self.logger.info(f"Fingerprinting: {os.path.basename(filepath)}")
            # acoustid.match uses fpcalc under the hood.
            # We run it in a thread to avoid blocking the event loop.
            results = await asyncio.to_thread(
                self._lookup, filepath
            )

            if not results:
                self.logger.warning(f"No AcoustID match for {os.path.basename(filepath)}")
                return None

            # Get the best match
            # results is a generator of (score, recording_id, title, artist)
            best_match = None
            max_score = 0

            for score, rid, title, artist in results:
                if score > max_score:
                    max_score = score
                    best_match = {
                        'recording_id': rid,
                        'title': title,
                        'artist': artist,
                        'score': score
                    }

            if best_match and max_score > 0.5:
                self.logger.info(f"AcoustID Match: {best_match['artist']} - {best_match['title']} (Score: {max_score:.2f})")

                # Update Cache
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO acoustid_cache (file_hash, match_data) VALUES (?, ?)",
                            (file_id, json.dumps(best_match))
                        )
                        conn.commit()
                except Exception as e:
                    self.logger.warning(f"AcoustID Cache: Write error: {e}")

                return best_match

            return None

        except acoustid.FingerprintGenerationError:
            self.logger.error("AcoustID: fpcalc not found or failed to execute.")
            return None
        except Exception as e:
            self.logger.error(f"AcoustID error: {e}")
            return None

    def _lookup(self, filepath):
        """Synchronous lookup for use in a thread."""
        # parse_lookup_result returns a generator
        return acoustid.match(self.api_key, filepath)
