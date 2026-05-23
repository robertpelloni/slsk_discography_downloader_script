import asyncio
import difflib
import os
import re
import shutil
import subprocess
from typing import Optional

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover

from bs4 import BeautifulSoup
import requests


class PostProcessor:
    def __init__(self, mb_service, config_service, logger):
        self.mb_service = mb_service
        self.config_service = config_service
        self.logger = logger

    async def process_album(self, target_dir, metadata):
        """Post-process a downloaded album: rename files, tag, fetch cover art & lyrics."""
        if not os.path.isdir(target_dir):
            return

        self.logger.info(f"Post-processing: {os.path.basename(target_dir)}")

        # 1. Fetch release metadata from MusicBrainz
        rg_id = metadata.get('mb_release_group_id')
        if not rg_id:
            self.logger.warning("No release group ID, skipping tagging.")
            return

        release = await asyncio.to_thread(self.mb_service.get_best_release_with_tracks, rg_id)
        if not release:
            self.logger.warning("Could not fetch release metadata. Skipping tagging.")
            return

        # Build track list
        tracks = []
        for medium in release.get('medium-list', []):
            for track in medium.get('track-list', []):
                rec = track.get('recording', {})
                tracks.append({
                    'number': track.get('number', '0'),
                    'title': rec.get('title', 'Unknown'),
                    'length': int(rec.get('length', 0) or 0),
                    'recording_id': rec.get('id'),
                })

        if not tracks:
            self.logger.warning("No tracks found in release metadata.")
            return

        # 2. List local audio files
        local_files = [
            f for f in os.listdir(target_dir)
            if f.lower().endswith(('.mp3', '.flac', '.m4a'))
            and os.path.getsize(os.path.join(target_dir, f)) > 100 * 1024
        ]

        if not local_files:
            self.logger.warning("No audio files found to tag.")
            return

        # 3. Match files to tracks
        matched = self._match_files_to_tracks(local_files, tracks, target_dir)

        if not matched:
            self.logger.warning("No files could be matched to tracks. Leaving as-is.")
            return

        # 4. Rename and tag
        cover_path = os.path.join(target_dir, "folder.jpg")
        has_cover = os.path.exists(cover_path)

        for filename, track in matched:
            try:
                await self._process_file(target_dir, filename, track, metadata, cover_path if has_cover else None)
            except Exception as e:
                if "Fake FLAC" in str(e):
                    raise e
                self.logger.error(f"Error processing {filename}: {e}")

        self.logger.info(f"Tagged {len(matched)} files in {os.path.basename(target_dir)}")

    def _match_files_to_tracks(self, local_files, tracks, target_dir):
        """Match downloaded files to MusicBrainz tracks using fuzzy matching."""
        matched = []

        for f in local_files:
            best_match = None
            best_ratio = 0

            name_clean = f.lower().replace('-', ' ').replace('_', ' ')

            for t in tracks:
                title_clean = t['title'].lower()
                ratio = difflib.SequenceMatcher(None, name_clean, title_clean).ratio()

                # Boost if track number appears in filename
                try:
                    num = re.escape(str(t['number']))
                    if re.search(r'\b0?' + num + r'\b', f):
                        ratio += 0.3
                except Exception:
                    pass

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = t

            if best_ratio > 0.5 and best_match:
                matched.append((f, best_match))
            else:
                # Keep unmatched files — they'll just stay with their original names
                self.logger.info(f"Unmatched file (will keep original name): {f}")

        return matched

    async def _process_file(self, target_dir, filename, track, metadata, cover_path):
        """Rename, tag, and optionally convert a single file."""
        old_path = os.path.join(target_dir, filename)
        ext = os.path.splitext(filename)[1]

        # Build new filename: "01 - Track Title.flac"
        track_num_raw = str(track.get('number', '0'))
        num_match = re.search(r'\d+', track_num_raw)
        num = num_match.group(0).zfill(2) if num_match else "00"
        safe_title = self._sanitize(track.get('title', 'Unknown'))
        new_name = f"{num} - {safe_title}{ext}"
        new_path = os.path.join(target_dir, new_name)

        # Rename (only if doesn't conflict)
        if old_path != new_path and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
            except OSError:
                new_path = old_path

        # Optional: verify lossless integrity
        if self.config_service.get('sentinel_enabled', False) and ext in ('.flac', '.wav'):
            if not await self._verify_lossless(new_path):
                self.logger.warning(f"Fake FLAC detected, removing: {filename}")
                try:
                    os.remove(new_path)
                except Exception:
                    pass
                raise ValueError(f"Fake FLAC detected in {filename}")

        # Fetch lyrics if enabled
        lyrics = None
        if self.config_service.get('embed_lyrics', False):
            lyrics = await asyncio.to_thread(
                self._fetch_lyrics, metadata.get('artist'), track.get('title')
            )

        # Tag the file
        tags = {
            'artist': metadata.get('artist', 'Unknown Artist'),
            'album': metadata.get('album', 'Unknown Album'),
            'title': track.get('title', 'Unknown Title'),
            'tracknumber': track_num_raw,
            'year': metadata.get('year', 'Unknown'),
        }
        self.tag_file(new_path, tags, cover_path, lyrics)

        # Optional: convert FLAC → MP3
        if self.config_service.get('convert_to_mp3', False) and ext in ('.flac', '.wav'):
            mp3_path = await self._convert_to_mp3(new_path, target_dir, metadata)
            if mp3_path:
                self.tag_file(mp3_path, tags, cover_path, lyrics)

    # ─── Audio Quality Verification ───────────────────────────────

    async def _verify_lossless(self, file_path):
        """Check if a FLAC truly contains high-frequency content (>18kHz).
        Returns False if it's likely a lossy upscale (fake FLAC)."""
        try:
            self.logger.info(f"Sentinel: checking {os.path.basename(file_path)}")

            cmd = [
                'ffmpeg', '-i', file_path,
                '-af', 'highpass=f=18000,volumedetect',
                '-f', 'null', os.devnull
            ]
            proc = await asyncio.to_thread(
                subprocess.run, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            output = proc.stderr.decode('utf-8', errors='ignore')

            # Parse max_volume from ffmpeg output
            match = re.search(r'max_volume:\s*([-\d.]+)\s*dB', output)
            if match:
                max_vol = float(match.group(1))
                if max_vol < -55.0:
                    self.logger.warning(
                        f"SENTINEL: {os.path.basename(file_path)} is likely lossy upscale "
                        f"(high-freq volume: {max_vol}dB)"
                    )
                    return False
                return True
            else:
                self.logger.info("Sentinel: could not parse volume, passing.")
                return True
        except Exception as e:
            self.logger.error(f"Sentinel error: {e}")
            return True

    # ─── File Tagging ─────────────────────────────────────────────

    def tag_file(self, filepath, tags, cover_path=None, lyrics=None):
        try:
            ext = os.path.splitext(filepath)[1].lower()

            if ext == '.mp3':
                self._tag_mp3(filepath, tags, cover_path, lyrics)
            elif ext == '.flac':
                self._tag_flac(filepath, tags, cover_path, lyrics)
            elif ext == '.m4a':
                self._tag_m4a(filepath, tags, cover_path, lyrics)
        except Exception as e:
            self.logger.error(f"Tag error on {os.path.basename(filepath)}: {e}")

    def _tag_mp3(self, filepath, tags, cover_path, lyrics):
        try:
            audio = EasyID3(filepath)
        except mutagen.id3.ID3NoHeaderError:
            audio = mutagen.File(filepath, easy=True)
            audio.add_tags()

        audio['artist'] = tags['artist']
        audio['album'] = tags['album']
        audio['title'] = tags.get('title', '')
        audio['tracknumber'] = tags.get('tracknumber', '')
        if tags.get('year') not in (None, 'Unknown', ''):
            audio['date'] = tags['year']
        audio.save()

        audio_full = MP3(filepath, ID3=mutagen.id3.ID3)
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as f:
                audio_full.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=f.read()))
        if lyrics:
            audio_full.tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics))
        audio_full.save()

    def _tag_flac(self, filepath, tags, cover_path, lyrics):
        audio = FLAC(filepath)
        audio['artist'] = tags['artist']
        audio['album'] = tags['album']
        audio['title'] = tags.get('title', '')
        audio['tracknumber'] = tags.get('tracknumber', '')
        if tags.get('year') not in (None, 'Unknown', ''):
            audio['date'] = tags['year']
        if lyrics:
            audio['LYRICS'] = lyrics
        if cover_path and os.path.exists(cover_path):
            # Remove existing cover art first
            audio.clear_pictures()
            img = Picture()
            img.type = 3
            img.mime = 'image/jpeg'
            with open(cover_path, 'rb') as f:
                img.data = f.read()
            audio.add_picture(img)
        audio.save()

    def _tag_m4a(self, filepath, tags, cover_path, lyrics):
        audio = MP4(filepath)
        audio['\xa9ART'] = tags['artist']
        audio['\xa9alb'] = tags['album']
        audio['\xa9nam'] = tags.get('title', '')
        try:
            num = int(re.search(r'\d+', str(tags.get('tracknumber', '0'))).group())
            audio['trkn'] = [(num, 0)]
        except (ValueError, AttributeError):
            pass
        if tags.get('year') not in (None, 'Unknown', ''):
            audio['\xa9day'] = tags['year']
        if lyrics:
            audio['\xa9lyr'] = lyrics
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as f:
                audio['covr'] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()

    # ─── MP3 Conversion ───────────────────────────────────────────

    async def _convert_to_mp3(self, source_path, target_dir, metadata):
        try:
            parts = target_dir.replace('\\', '/').split('/')
            artist_album = os.path.join(*parts[-2:]) if len(parts) >= 2 else os.path.basename(target_dir)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mp3_dir = os.path.join(base_dir, "converted_mp3s", artist_album)
            os.makedirs(mp3_dir, exist_ok=True)

            name = os.path.splitext(os.path.basename(source_path))[0]
            target_path = os.path.join(mp3_dir, f"{name}.mp3")

            if os.path.exists(target_path):
                return target_path

            cmd = [
                'ffmpeg', '-y', '-i', source_path,
                '-codec:a', 'libmp3lame', '-q:a', '0',
                '-map_metadata', '0', target_path
            ]
            proc = await asyncio.to_thread(
                subprocess.run, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if proc.returncode != 0:
                self.logger.error(f"ffmpeg error converting {os.path.basename(source_path)}")
                return None
            return target_path
        except Exception as e:
            self.logger.error(f"Conversion error: {e}")
            return None

    # ─── Lyrics Fetching ──────────────────────────────────────────

    def _fetch_lyrics(self, artist, title):
        if not artist or not title:
            return None

        # 1. lrclib.net
        try:
            import urllib.parse
            url = f"https://lrclib.net/api/search?artist_name={urllib.parse.quote(artist)}&track_name={urllib.parse.quote(title)}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    return data[0].get('syncedLyrics') or data[0].get('plainLyrics')
        except Exception:
            pass

        # 2. Genius fallback
        genius_key = self.config_service.get('genius_api_key', '')
        if genius_key:
            try:
                res = requests.get(
                    "https://api.genius.com/search",
                    headers={"Authorization": f"Bearer {genius_key}"},
                    params={"q": f"{artist} {title}"},
                    timeout=5
                )
                if res.status_code == 200:
                    hits = res.json().get("response", {}).get("hits", [])
                    if hits:
                        page = requests.get(hits[0]["result"]["url"], timeout=5)
                        html = BeautifulSoup(page.text, "html.parser")
                        divs = html.find_all("div", {"data-lyrics-container": "true"})
                        if divs:
                            lines = []
                            for div in divs:
                                for br in div.find_all("br"):
                                    br.replace_with("\n")
                                lines.append(div.get_text())
                            return "\n".join(lines)
            except Exception:
                pass

        return None

    # ─── Cover Art ────────────────────────────────────────────────

    def download_cover_art(self, rg_id, target_dir):
        """Fire-and-forget cover art download."""
        if rg_id:
            # Safely schedule on the running event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._fetch_cover_art(rg_id, target_dir))
            except RuntimeError:
                try:
                    asyncio.create_task(self._fetch_cover_art(rg_id, target_dir))
                except RuntimeError:
                    self.logger.warning(f"Could not schedule cover art download (no event loop)")

    async def _fetch_cover_art(self, rg_id, target_dir):
        try:
            releases = await asyncio.to_thread(self.mb_service.get_releases_in_group, rg_id)
            if not releases:
                return
            release_id = releases[0]['id']
            url = f"https://coverartarchive.org/release/{release_id}/front"
            r = await asyncio.to_thread(requests.get, url, allow_redirects=True, timeout=10)
            if r.status_code == 200 and len(r.content) > 1000:
                os.makedirs(target_dir, exist_ok=True)
                path = os.path.join(target_dir, "folder.jpg")
                with open(path, 'wb') as f:
                    f.write(r.content)
        except Exception:
            pass

    # ─── Utility ──────────────────────────────────────────────────

    def _sanitize(self, name):
        return "".join(c for c in name if c.isalpha() or c.isdigit() or c in " .-_").strip()
