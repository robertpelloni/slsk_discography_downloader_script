import asyncio
import logging
import random
import time
from typing import Optional, List, Dict, Any

try:
    # Attempt to load the compiled Rust module
    import bob_soulseek_rs
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False


class RateLimiter:
    """Token bucket / sliding window rate limiter to prevent peer throttling and 429/400 errors."""
    def __init__(self, min_interval: float = 1.0, max_concurrent: int = 2):
        self.min_interval = min_interval
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request_time = time.monotonic()

    def release(self):
        self._semaphore.release()


class RustSoulseekService:
    """High-performance bridge to Soulseek P2P via Rust FFI (bob_soulseek_rs).
    Includes intelligent rate-limiting, exponential backoff with jitter, and auto-reconnection.
    """
    def __init__(
        self,
        username: str,
        password: str,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        rate_limit_interval: float = 0.5,
        max_concurrent_downloads: int = 2,
    ):
        self.username = username
        self.password = password
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.rate_limiter = RateLimiter(
            min_interval=rate_limit_interval,
            max_concurrent=max_concurrent_downloads
        )
        self.logger = logging.getLogger(__name__)
        self._connected = False

        if not RUST_AVAILABLE:
            self.logger.warning(
                "Rust module 'bob_soulseek_rs' not found. Ensure it is compiled and in PYTHONPATH. Falling back to mock python implementation."
            )

    async def connect(self) -> bool:
        """Connects or authenticates to Soulseek via the Rust bridge."""
        if RUST_AVAILABLE:
            self.logger.info("Delegating connection to Rust FFI...")
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
        """Disconnects the bridge session."""
        self.logger.info("Disconnected (Rust Mock/FFI)")
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def search(self, query: str) -> List[Any]:
        """Performs a query search with rate limiting and exponential retry."""
        await self.rate_limiter.acquire()
        try:
            if RUST_AVAILABLE:
                if not self._connected:
                    self.logger.info("Rust bridge not connected. Connecting now...")
                    await self.connect()

                attempt = 0
                while attempt <= self.max_retries:
                    try:
                        self.logger.info(f"Delegating search to Rust FFI: {query} (attempt {attempt + 1})")
                        return await bob_soulseek_rs.rust_search_async(query)
                    except Exception as e:
                        attempt += 1
                        if attempt > self.max_retries:
                            self.logger.error(f"Rust Search Error after {attempt} attempts: {e}")
                            raise e

                        backoff = self.base_backoff * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                        self.logger.warning(f"Search attempt failed: {e}. Retrying in {backoff:.2f}s...")
                        await asyncio.sleep(backoff)
                        await self.connect()
            else:
                await asyncio.sleep(0.05)
                return [f"Fallback Python Result 1 for {query}"]
        finally:
            self.rate_limiter.release()

    async def download_file(
        self, username: str, filename: str, size: int = 0, download_directory: str = "."
    ) -> Any:
        """Downloads a target file from a peer via Rust FFI.
        Applies exponential backoff with jitter and rate limiting to prevent 429/400 peer throttling.
        """
        await self.rate_limiter.acquire()
        try:
            if RUST_AVAILABLE:
                if not self._connected:
                    self.logger.info("Rust bridge not connected. Connecting now...")
                    await self.connect()

                attempt = 0
                while attempt <= self.max_retries:
                    try:
                        self.logger.info(
                            f"Delegating download to Rust FFI: {filename} from {username} (attempt {attempt + 1})"
                        )
                        transfer = await bob_soulseek_rs.rust_download_async(
                            username, filename, size, download_directory
                        )
                        return transfer
                    except Exception as e:
                        attempt += 1
                        if attempt > self.max_retries:
                            self.logger.error(f"Rust Download Error after {attempt} attempts: {e}")
                            raise e

                        # Calculate exponential backoff with jitter
                        backoff = self.base_backoff * (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
                        self.logger.warning(
                            f"Download failed for {filename}: {e}. Retrying with backoff {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)

                        # Re-establish connection if peer/network dropped
                        self.logger.info("Attempting Rust reconnect prior to retry...")
                        await self.connect()
            else:
                self.logger.warning("Mock download not implemented")
                return False
        finally:
            self.rate_limiter.release()
