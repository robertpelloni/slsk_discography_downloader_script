import asyncio
import os
import time
from typing import List, Dict, Any

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".aac", ".wma"}


class SoulseekService:
    def __init__(self):
        self.client: Any = None
        self.username = None
        self.password = None
        self.download_path = os.path.abspath("downloads")
        self.is_connected = False

        # Rate limiting: max searches per window
        self._search_times: List[float] = []
        self._max_searches_per_window = 5
        self._rate_window = 10.0  # seconds

        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    def _get_server_connection_state(self):
        """Check the REAL server connection state from aioslsk internals."""
        if not self.client:
            return None
        try:
            server = self.client.server_manager
            if server:
                return server.connection_state
        except Exception:
            pass
        return None

    def _is_server_really_connected(self) -> bool:
        """True only if aioslsk's server connection state says CONNECTED."""
        state = self._get_server_connection_state()
        if state is None:
            return self.is_connected  # fall back to cached flag
        from aioslsk.network.connection import ConnectionState as CS

        return state == CS.CONNECTED

    def _wait_for_rate_limit(self):
        """Rate-limit searches to avoid tripping Soulseek server limits."""
        now = time.time()
        cutoff = now - self._rate_window
        # Keep only recent entries
        self._search_times = [t for t in self._search_times if t > cutoff]

        if len(self._search_times) >= self._max_searches_per_window:
            # Need to wait: oldest entry + window - now
            oldest = self._search_times[0]
            wait = oldest + self._rate_window - now
            if wait > 0:
                return wait
        return 0.0

    def _record_search(self):
        self._search_times.append(time.time())

    async def connect(self, username, password):
        try:
            import aioslsk
            from aioslsk.client import SoulSeekClient
            from aioslsk.settings import (
                Settings as SlskSettings,
                CredentialsSettings,
                SharesSettings,
                NetworkSettings,
                PeerSettings,
                PeerConnectMode,
                SearchSettings,
            )

            HAS_AIOSLSK = True
        except ImportError:
            HAS_AIOSLSK = False

        if not HAS_AIOSLSK:
            raise Exception("aioslsk library missing")

        if self.is_connected and self.username == username:
            return

        # Disconnect previous client if any
        if self.client:
            try:
                await self.client.stop()
            except Exception:
                pass
            self.client = None
            self.is_connected = False
            await asyncio.sleep(1)

        self.username = username
        self.password = password

        settings = SlskSettings(
            credentials=CredentialsSettings(
                username=self.username, password=self.password
            ),
            shares=SharesSettings(download=self.download_path),
            network=NetworkSettings(
                peer=PeerSettings(connect_mode=PeerConnectMode.FALLBACK)
            ),
            searches=SearchSettings(max_results=200),
        )

        self.client = SoulSeekClient(settings)
        await self.client.start()
        try:
            await self.client.login()
            self.is_connected = True
            print(f"Soulseek: Logged in as {username}")

            # Log listening port status
            try:
                network = self.client.network
                if network._listening_ports:
                    ports = [
                        p.port for p in network._listening_ports if hasattr(p, "port")
                    ]
                    print(f"Soulseek: Listening on ports: {ports}")
                else:
                    print("Soulseek: Warning - No listening ports bound")
            except Exception as e:
                print(f"Soulseek: Could not check ports: {e}")

        except Exception as e:
            print(f"Soulseek Login Failed: {e}")
            self.is_connected = False
            raise

    async def _ensure_connected(self):
        """Check if the REAL server connection is alive and reconnect if needed."""
        if not self.client:
            self.is_connected = False
            return False

        # Use aioslsk's own connection state for accurate detection
        if self._is_server_really_connected():
            return True

        # Connection is stale — force reconnect
        print("Soulseek: Server connection is stale, reconnecting...")
        self.is_connected = False
        if self.username and self.password:
            try:
                await self.connect(self.username, self.password)
                return self.is_connected
            except Exception as e:
                print(f"Soulseek: Forced reconnect failed: {e}")
                return False
        return False

    async def _perform_search(self, query: str, timeout: int) -> List[Dict[str, Any]]:
        """Low-level search — assumes connection is healthy. Returns parsed results or None on failure."""
        safe_query = query.encode("ascii", errors="replace").decode("ascii")

        try:
            search_request = await self.client.searches.search(query)

            # Collect results with early termination
            max_results = 200
            for _ in range(timeout):
                if len(search_request.results) >= max_results:
                    break
                await asyncio.sleep(1)

            results = list(search_request.results)[:max_results]
            print(f"Soulseek: Search '{safe_query}' got {len(results)} raw results")

            # Remove the search request to avoid accumulating peer connections
            try:
                self.client.searches.remove_request(search_request)
            except Exception:
                pass

        except OSError as e:
            print(f"Soulseek: Socket error during search: {e}")
            self.is_connected = False
            return None
        except Exception as e:
            print(f"Soulseek: Search error: {e}")
            self.is_connected = False
            return None

        # Parse results
        parsed = []
        for res in results:
            try:
                username = res.username
                avg_speed = res.avg_speed
                has_slots = res.has_free_slots

                for item in res.shared_items:
                    try:
                        # Bitrate
                        bitrate = 0
                        try:
                            attrs = item.get_attribute_map()
                            from aioslsk.protocol.attributes import AttributeKey

                            if AttributeKey.BITRATE in attrs:
                                bitrate = attrs[AttributeKey.BITRATE]
                        except Exception:
                            pass

                        # Extension
                        ext = ""
                        try:
                            ext = item.extension.lower() if item.extension else ""
                        except Exception:
                            pass
                        if not ext and item.filename:
                            ext = os.path.splitext(item.filename)[1].lower()
                        if ext and not ext.startswith("."):
                            ext = "." + ext

                        parsed.append(
                            {
                                "filename": item.filename,
                                "user": username,
                                "size": item.filesize,
                                "speed": avg_speed,
                                "slots": has_slots,
                                "bitrate": bitrate,
                                "extension": ext,
                            }
                        )
                        if len(parsed) >= 200:
                            break
                    except Exception:
                        continue
                if len(parsed) >= 200:
                    break
            except Exception:
                continue

        print(f"Parsed {len(parsed)} results")
        return parsed

    async def search(self, query: str, timeout: int = 20) -> List[Dict[str, Any]]:
        """
        Search Soulseek with connection health checks, rate limiting, and retry.

        Returns parsed results (may be empty) on success, or empty list on failure.
        """
        import sys

        print(
            f"SLK_SEARCH: query={query!r} timeout={timeout}",
            file=sys.stderr,
            flush=True,
        )

        if not self.client:
            print("Soulseek: No client — raising exception")
            raise Exception("Soulseek not connected")

        # Step 1: Verify the real connection state and reconnect if stale
        if not await self._ensure_connected():
            print("Soulseek: Cannot ensure connection")
            return []

        # Step 2: Rate limiting — wait if we're searching too fast
        wait = self._wait_for_rate_limit()
        if wait > 0:
            print(f"Soulseek: Rate limiting — waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        # Step 3: Perform search (up to 2 attempts)
        for attempt in range(2):
            self._record_search()
            results = await self._perform_search(query, timeout)

            if results is not None:
                # Search succeeded (results may be empty but that's legitimate)
                return results

            # Search failed due to connection issue — reconnect and retry once
            if attempt == 0:
                print("Soulseek: Search failed, reconnecting and retrying...")
                self.is_connected = False
                if self.username and self.password:
                    try:
                        await self.connect(self.username, self.password)
                        print("Soulseek: Reconnected, retrying search...")
                        continue
                    except Exception as retry_err:
                        print(f"Soulseek: Reconnect failed: {retry_err}")
                return []

        return []

    async def disconnect(self):
        """Properly disconnect from Soulseek and free ports."""
        if self.client:
            try:
                await self.client.stop()
                print("Soulseek: Disconnected")
            except Exception as e:
                print(f"Soulseek: Error disconnecting: {e}")
            finally:
                self.client = None
                self.is_connected = False

    async def download_file(self, user, filename, size=0, download_directory="."):
        if not self.is_connected:
            reconnected = await self._ensure_connected()
            if not reconnected:
                raise Exception("Not connected and reconnection failed")

        # Sanitize filename for logging
        safe_name = (
            os.path.basename(filename).encode("ascii", errors="replace").decode("ascii")
        )

        if not download_directory:
            download_directory = self.download_path

        try:
            try:
                import bob_soulseek_rs

                RUST_AVAILABLE = hasattr(bob_soulseek_rs, 'rust_download_async')
            except ImportError:
                RUST_AVAILABLE = False

            if RUST_AVAILABLE:
                transfer = await bob_soulseek_rs.rust_download_async(
                    user, filename, size, download_directory
                )
                return transfer
            else:
                transfer = await self.client.transfers.download(user, filename)
                return transfer
        except Exception as e:
            raise Exception(f"Failed to download {safe_name}: {e}")

    async def get_folder_contents(self, user, folder_path):
        """Fetch the file list of a remote folder."""
        if not self.is_connected:
            reconnected = await self._ensure_connected()
            if not reconnected:
                return []

        try:
            from aioslsk.commands import PeerGetDirectoryContentCommand

            cmd = PeerGetDirectoryContentCommand(user, folder_path)
            response = await self.client.execute(cmd)
            return response or []
        except Exception as e:
            print(f"Error getting folder contents: {e}")
            return []
