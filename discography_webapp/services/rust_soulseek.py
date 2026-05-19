import asyncio
import logging

try:
    # Attempt to load the compiled Rust module
    from discography_webapp.rust_bridge.bob_soulseek_rs import bob_soulseek_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

class RustSoulseekService:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.logger = logging.getLogger(__name__)

        if not RUST_AVAILABLE:
            self.logger.warning("Rust module 'bob_soulseek_rs' not found. Ensure it is compiled and in PYTHONPATH. Falling back to mock python implementation.")

    async def connect(self):
        if RUST_AVAILABLE:
            self.logger.info(f"Delegating connection to Rust FFI...")
            # Call the async Rust function directly from Python event loop
            try:
                res = await bob_soulseek_rs.connect_to_soulseek_async(self.username, self.password)
                self.logger.info(f"Rust FFI Response: {res}")
                return True
            except Exception as e:
                self.logger.error(f"Rust FFI Connection Error: {e}")
                return False
        else:
            self.logger.info(f"Connected (Rust Mock) as {self.username}")
            return True

    async def disconnect(self):
        self.logger.info("Disconnected (Rust Mock/FFI)")

    async def search(self, query):
        if RUST_AVAILABLE:
            self.logger.info(f"Delegating search to Rust FFI: {query}")
            # Call the async Rust function directly from Python event loop
            return await bob_soulseek_rs.rust_search_async(query)
        else:
            # Fallback
            await asyncio.sleep(0.05)
            return [f"Fallback Python Result 1 for {query}"]
