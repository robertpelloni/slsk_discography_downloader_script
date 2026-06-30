import asyncio
import os
from typing import List, Dict, Any

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".aac", ".wma"}


class SoulseekService:
    def __init__(self):
        self.client: Any = None
        self.username = None
        self.password = None
        self.download_path = os.path.abspath("downloads")
        self.is_connected = False

        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

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
                ListeningSettings,
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
                peer=PeerSettings(connect_mode=PeerConnectMode.RACE),
                listening=ListeningSettings(port=60000, obfuscated_port=60001),
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
                try:
                    ports = network.get_listening_ports()
                    if ports:
                        print(f"Soulseek: Listening on ports: {ports}")
                    else:
                        print("Soulseek: No listening ports bound")
                except Exception:
                    print("Soulseek: Could not check ports")
            except Exception as e:
                print(f"Soulseek: Could not check ports: {e}")

        except Exception as e:
            print(f"Soulseek Login Failed: {e}")
            self.is_connected = False
            raise

    async def _ensure_connected(self):
        """Check if the client is actually alive and reconnect if needed."""
        if not self.client:
            self.is_connected = False
            return False

        try:
            # Check connection state via aioslsk's internal flags
            network = self.client.network
            if network and hasattr(network, "_server_connection"):
                conn = network._server_connection
                if conn:
                    # Check for CLOSING state — this is the actual flag aioslsk uses
                    is_closing = getattr(conn, "_is_closing", True)
                    if is_closing:
                        print("Soulseek: Connection closing, reconnecting...")
                        self.is_connected = False
                        if self.username and self.password:
                            await self.connect(self.username, self.password)
                        return self.is_connected
            return True
        except Exception as e:
            print(f"Soulseek: Health check failed: {e}")
            self.is_connected = False
            return False

    async def search(self, query: str, timeout: int = 20) -> List[Dict[str, Any]]:
        import sys

        print(
            f"SLK_SEARCH: query={query!r} timeout={timeout} connected={self.is_connected}",
            file=sys.stderr,
            flush=True,
        )
        if not self.is_connected or not self.client:
            print("Soulseek: NOT CONNECTED, raising exception")
            raise Exception("Soulseek not connected")

        # Check if connection is still alive
        await self._ensure_connected()
        if not self.is_connected:
            print("Soulseek: CONNECTION LOST after health check")
            raise Exception("Soulseek connection lost")

        safe_query = query.encode("ascii", errors="replace").decode("ascii")

        try:
            search_request = await self.client.searches.search(query)

            # Collect results with early termination once we have enough
            # (avoid accumulating 20k+ results that exhaust memory/connections)
            max_results = 200
            for _ in range(timeout):
                if len(search_request.results) >= max_results:
                    break
                # Check connection health mid-wait — abort early if dropped
                if self.client and hasattr(self.client, "network"):
                    sc = getattr(self.client.network, "_server_connection", None)
                    if sc and getattr(sc, "_is_closing", False):
                        print("Soulseek: Connection dropped mid-search, aborting wait")
                        break
                await asyncio.sleep(1)

            results = list(search_request.results)[:max_results]
            print(f"Soulseek: Search '{safe_query}' got {len(results)} raw results")

            # Remove the search request to stop aioslsk from accumulating
            # more results and spawning more peer connection attempts
            try:
                self.client.searches.remove_request(search_request)
            except Exception:
                pass

        except OSError as e:
            # Socket errors (e.g., [Errno 22] Invalid argument) mean the
            # connection is dead. Reconnect and retry ONCE.
            print(f"Soulseek: Socket error during search: {e}")
            self.is_connected = False
            try:
                if self.username and self.password:
                    await self.connect(self.username, self.password)
                    print("Soulseek: Reconnected, retrying search...")
                    # Retry the search after reconnect
                    search_request = await self.client.searches.search(query)
                    max_results = 200
                    for _ in range(timeout):
                        if len(search_request.results) >= max_results:
                            break
                        await asyncio.sleep(1)
                    results = list(search_request.results)[:max_results]
                    try:
                        self.client.searches.remove_request(search_request)
                    except Exception:
                        pass
            except Exception as retry_err:
                print(f"Soulseek: Reconnect+retry failed: {retry_err}")
                return []
        except Exception as e:
            # Try to reconnect if search fails
            print(f"Soulseek: Search error: {e}")
            self.is_connected = False
            try:
                if self.username and self.password:
                    await self.connect(self.username, self.password)
            except Exception as reconnect_err:
                print(f"Soulseek: Reconnection failed: {reconnect_err}")
            return []

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

                        # Extension - always store with leading dot

                        ext = ""

                        try:
                            ext = item.extension.lower() if item.extension else ""

                        except Exception:
                            pass

                        if not ext and item.filename:
                            ext = os.path.splitext(item.filename)[1].lower()

                        # Ensure leading dot

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
            # Try to reconnect before failing
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

                RUST_AVAILABLE = True
            except ImportError:
                RUST_AVAILABLE = False

            if RUST_AVAILABLE:
                try:
                    transfer = await bob_soulseek_rs.rust_download_async(
                        user, filename, size, download_directory
                    )
                    return transfer
                except AttributeError:
                    # Rust module exists but doesn't support rust_download_async
                    RUST_AVAILABLE = False
            # Fallback to Python Soulseek client
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
