import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from discography_webapp.services.post_processor import PostProcessor

@pytest.mark.asyncio
async def test_sentinel_detects_fake_flac():
    mb = MagicMock()
    config = MagicMock()
    config.get.return_value = True # Enable sentinel
    logger = MagicMock()

    pp = PostProcessor(mb, config, logger)

    # Mock subprocess.run for ffmpeg to return a low max_volume (fake FLAC)
    mock_proc = MagicMock()
    mock_proc.stderr.decode.return_value = "max_volume: -60.5 dB"

    with patch("discography_webapp.services.post_processor.subprocess.run", return_value=mock_proc):
        # We test the private verify function directly since it's an async thread call
        is_lossless = await pp._verify_lossless("fake.flac")
        assert is_lossless is False
        logger.warning.assert_called()

@pytest.mark.asyncio
async def test_sentinel_passes_real_flac():
    mb = MagicMock()
    config = MagicMock()
    config.get.return_value = True
    logger = MagicMock()

    pp = PostProcessor(mb, config, logger)

    # Mock subprocess.run for ffmpeg to return a high max_volume (real FLAC)
    mock_proc = MagicMock()
    mock_proc.stderr.decode.return_value = "max_volume: -15.5 dB"

    with patch("discography_webapp.services.post_processor.subprocess.run", return_value=mock_proc):
        is_lossless = await pp._verify_lossless("real.flac")
        assert is_lossless is True
