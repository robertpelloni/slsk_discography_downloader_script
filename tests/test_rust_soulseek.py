import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Attempt to load the rust module for type patching, but don't fail if it's missing (should use sys.modules mock if missing)
import sys

# We need to mock bob_soulseek_rs if we want to run tests without compiling the Rust bridge in this environment
mock_rust = MagicMock()
mock_rust.connect_to_soulseek_async = MagicMock(return_value=asyncio.Future())
mock_rust.connect_to_soulseek_async.return_value.set_result(True)

sys.modules['bob_soulseek_rs'] = mock_rust

from discography_webapp.services.rust_soulseek import RustSoulseekService

class MockTransfer:
    def __init__(self, filename, is_finished=True, error=None):
        self.filename = filename
        self.is_finished = is_finished
        self.error = error

@pytest.mark.asyncio
async def test_rust_soulseek_connect():
    service = RustSoulseekService('testuser', 'testpass')
    with patch('discography_webapp.services.rust_soulseek.RUST_AVAILABLE', True):
        with patch('bob_soulseek_rs.connect_to_soulseek_async') as mock_connect:
            future = asyncio.Future()
            future.set_result(True)
            mock_connect.return_value = future

            res = await service.connect()
            assert res is True
            assert service._connected is True
            mock_connect.assert_called_once_with('testuser', 'testpass')

@pytest.mark.asyncio
async def test_rust_soulseek_search():
    service = RustSoulseekService('testuser', 'testpass')
    service._connected = True
    with patch('discography_webapp.services.rust_soulseek.RUST_AVAILABLE', True):
        with patch('bob_soulseek_rs.rust_search_async') as mock_search:
            future = asyncio.Future()
            future.set_result([{"filename": "test.mp3", "user": "user1", "size": 100, "bitrate": 320, "extension": ".mp3"}])
            mock_search.return_value = future

            res = await service.search("test query")
            assert len(res) == 1
            assert res[0]["filename"] == "test.mp3"
            mock_search.assert_called_once_with("test query")

@pytest.mark.asyncio
async def test_rust_soulseek_download():
    service = RustSoulseekService('testuser', 'testpass')
    service._connected = True
    with patch('discography_webapp.services.rust_soulseek.RUST_AVAILABLE', True):
        with patch('bob_soulseek_rs.rust_download_async') as mock_download:
            mock_transfer = MockTransfer("test.mp3")
            future = asyncio.Future()
            future.set_result(mock_transfer)
            mock_download.return_value = future

            transfer = await service.download_file("user1", "test.mp3", 100, ".")
            assert transfer.filename == "test.mp3"
            assert transfer.is_finished is True
            assert transfer.error is None
            mock_download.assert_called_once_with("user1", "test.mp3", 100, ".")
