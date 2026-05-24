import asyncio
import os
import acoustid
from typing import Optional, Dict, Any

class AcoustidService:
    def __init__(self, api_key: str, logger):
        self.api_key = api_key
        self.logger = logger

    async def identify_file(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Identify an audio file using AcoustID fingerprinting."""
        if not self.api_key:
            self.logger.warning("AcoustID API key not configured. Skipping identification.")
            return None

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
