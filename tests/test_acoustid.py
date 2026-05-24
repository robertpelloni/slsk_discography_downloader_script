import pytest
import asyncio
from unittest.mock import MagicMock, patch
from discography_webapp.services.acoustid_service import AcoustidService

@pytest.mark.asyncio
async def test_acoustid_service_no_key():
    logger = MagicMock()
    service = AcoustidService(api_key="", logger=logger)

    result = await service.identify_file("dummy.mp3")
    assert result is None
    logger.warning.assert_called_with("AcoustID API key not configured. Skipping identification.")

@pytest.mark.asyncio
async def test_acoustid_service_fpcalc_missing():
    logger = MagicMock()
    service = AcoustidService(api_key="fake_key", logger=logger)

    # In identify_file, self._lookup is called in a thread.
    # We need to patch where AcoustidService._lookup is or where it calls acoustid.match
    with patch("discography_webapp.services.acoustid_service.acoustid.match", side_effect=Exception("fpcalc not found")):
        result = await service.identify_file("dummy.mp3")
        assert result is None
        # The specific error might vary, but it should be caught
        assert logger.error.called
