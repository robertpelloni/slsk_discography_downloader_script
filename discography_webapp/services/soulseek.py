import asyncio
import os
import re
import time
from typing import List, Dict, Any, Optional

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.ogg', '.wav', '.aac', '.wma'}

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
                username=self.username,
                password=self.password
            ),
            shares=SharesSettings(
                download=self.download_path
            ),
            network=NetworkSettings(
                peer=PeerSettings(
                    connect_mode=PeerConnectMode.FALLBACK
                )
            ),
            searches=SearchSettings(
                max_results=200
            ),
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
                    ports = [p.port for p in network._listening_ports if hasattr(p, 'port')]
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
        """Check if the client is actually alive and reconnect if needed."""
        if not self.client:
            self.is_connected = False
            return False

        try:
            # Try to check if the network is still alive
            network = self.client.network
            if network and hasattr(network, '_server_connection'):
                conn = network._server_connection
                if conn and hasattr(conn, 'is_connected') and not conn.is_connected():
                    print("Soulseek: Connection lost, reconnecting...")
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
        if not self.is_connected or not self.client:
            raise Exception("Soulseek not connected")

        # Check if connection is still alive
        await self._ensure_connected()
        if not self.is_connected:
            raise Exception("Soulseek connection lost")

        safe_query = query.encode('ascii', errors='replace').decode('ascii')

        try:
            search_request = await self.client.searches.search(query)

            # Collect results with early termination once we have enough
            # (avoid accumulating 20k+ results that exhaust memory/connections)
            max_results = 500
            for _ in range(timeout):
                if len(search_request.results) >= max_results:
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

        except Exception as e:
            # Try to reconnect if search fails
            print(f"Search error: {e}")
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


                        if ext and not ext.startswith('.'):


                            ext = '.' + ext


                        parsed.append({


                            'filename': item.filename,


                            'user': username,


                            'size': item.filesize,


                            'speed': avg_speed,


                            'slots': has_slots,


                            'bitrate': bitrate,


                            'extension': ext,


                        })


                        if len(parsed) >= 1000:


                            break


                    except Exception:


                        continue


                if len(parsed) >= 1000:


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

    async def download_file(self, user, filename):
        if not self.is_connected:
            raise Exception("Not connected")

        # Sanitize filename for logging
        safe_name = os.path.basename(filename).encode('ascii', errors='replace').decode('ascii')

        try:
            transfer = await self.client.transfers.download(user, filename)
            return transfer
        except Exception as e:
            raise Exception(f"Failed to download {safe_name}: {e}")

    async def get_folder_contents(self, user, folder_path):
        """Fetch the file list of a remote folder."""
        if not self.is_connected:
            return []

        try:
            from aioslsk.commands import PeerGetDirectoryContentCommand
            cmd = PeerGetDirectoryContentCommand(user, folder_path)
            response = await self.client.execute(cmd)
            return response or []
        except Exception as e:
            print(f"Error getting folder contents: {e}")
            return []
