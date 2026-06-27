import asyncio
import logging

try:
    # Attempt to load the compiled Rust module
    import bob_soulseek_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

class RustSoulseekService:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.logger = logging.getLogger(__name__)
        self._connected = False

        if not RUST_AVAILABLE:
            self.logger.warning("Rust module 'bob_soulseek_rs' not found. Ensure it is compiled and in PYTHONPATH. Falling back to mock python implementation.")

    async def connect(self):
        if RUST_AVAILABLE:
            self.logger.info("Delegating connection to Rust FFI...")
            # Call the async Rust function directly from Python event loop
            try:
                res = await bob_soulseek_rs.connect_to_soulseek_async(self.username, self.password)
                self.logger.info(f"Rust FFI Response: {res}")
                self._connected = True
                return True
            except Exception as e:
                self.logger.error(f"Rust FFI Connection Error: {e}")
                self._connected = False
                return False
        else:
            self.logger.info(f"Connected (Rust Mock) as {self.username}")
            self._connected = True
            return True

    async def disconnect(self):
        self.logger.info("Disconnected (Rust Mock/FFI)")
        self._connected = False

    async def is_connected(self):
        return self._connected

    async def search(self, query):
        if RUST_AVAILABLE:
            if not self._connected:
                self.logger.info("Rust bridge not connected. Connecting now...")
                await self.connect()

            self.logger.info(f"Delegating search to Rust FFI: {query}")
            try:
                return await bob_soulseek_rs.rust_search_async(query)
            except Exception as e:
                self.logger.error(f"Rust Search Error: {e}")
                # Try to reconnect once if it fails
                self.logger.info("Attempting Rust reconnect...")
                if await self.connect():
                    return await bob_soulseek_rs.rust_search_async(query)
                raise e
        else:

            # Fallback
            await asyncio.sleep(0.05)
            return [f"Fallback Python Result 1 for {query}"]

    async def download_file(self, username, filename, size=0, download_directory="."):
        if RUST_AVAILABLE:
            if not self._connected:
                self.logger.info("Rust bridge not connected. Connecting now...")
                await self.connect()

            self.logger.info(f"Delegating download to Rust FFI: {filename} from {username}")
            try:
                transfer = await bob_soulseek_rs.rust_download_async(username, filename, size, download_directory)
                return transfer
            except Exception as e:
                self.logger.error(f"Rust Download Error: {e}")
                self.logger.info("Attempting Rust reconnect...")
                if await self.connect():
                    return await bob_soulseek_rs.rust_download_async(username, filename, size, download_directory)
                raise e
        else:
            self.logger.warning("Mock download not implemented")
            return False
