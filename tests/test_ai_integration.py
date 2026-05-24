import pytest
import asyncio
import os
import shutil
from unittest.mock import MagicMock, patch
from discography_webapp.services.orchestrator import Orchestrator
from discography_webapp.services.post_processor import PostProcessor
from discography_webapp.services.protocol import ProtocolService
from discography_webapp.services.config import ConfigService
from discography_webapp.services.logger import get_logger
from discography_webapp.services.event_bus import EventBus

@pytest.mark.asyncio
async def test_full_ai_cycle_integration(tmp_path):
    # Setup
    event_bus = EventBus()
    logger = get_logger(event_bus, 1)
    config = ConfigService(user_id=1)
    config.set('sentinel_enabled', True)
    config.set('acoustid_enabled', True)
    config.set('acoustid_api_key', 'test_key')

    mb_service = MagicMock()
    slsk_service = MagicMock()
    queue_service = MagicMock()

    post_processor = PostProcessor(mb_service, config, logger)

    orchestrator = Orchestrator(
        logger=logger, mb_service=mb_service, slsk_service=slsk_service,
        config_service=config, post_processor=post_processor,
        queue_service=queue_service, user_id=1
    )

    # Simulate a download directory
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    album_dir = download_dir / "Test Artist - Test Album"
    album_dir.mkdir()

    # Create a dummy file (would be a "Fake FLAC")
    fake_flac = album_dir / "01 - Intro.flac"
    fake_flac.write_text("dummy audio data")

    # 1. Integration: Sentinel Check
    # Mock ffmpeg to simulate a fake flac detection
    with patch.object(PostProcessor, "_verify_lossless", return_value=False):
        with pytest.raises(ValueError, match="Fake FLAC detected"):
            await post_processor._process_file(str(album_dir), "01 - Intro.flac", {"title": "Intro"}, {"artist": "Test"}, None)

    # 2. Integration: AcoustID Identification
    # Create another file for identification
    unidentified_file = album_dir / "unknown.mp3"
    # Ensure it's large enough (>100KB) to be picked up by process_album
    unidentified_file.write_bytes(b"audio" * 30000)

    with patch("discography_webapp.services.acoustid_service.AcoustidService.identify_file") as mock_id:
        mock_id.return_value = {
            'recording_id': 'mb-rec-123',
            'title': 'Identified Track',
            'artist': 'Identified Artist',
            'score': 0.95
        }

        # Simulate MB release metadata containing this recording
        mb_service.get_best_release_with_tracks.return_value = {
            'medium-list': [{
                'track-list': [{
                    'number': '1',
                    'recording': {'id': 'mb-rec-123', 'title': 'Identified Track'}
                }]
            }]
        }

        # This triggers the AcoustID flow in process_album
        await post_processor.process_album(str(album_dir), {'artist': 'Identified Artist', 'album': 'Test', 'mb_release_group_id': 'rg1'})

        # Check if the file was matched (it would be in the internal matched list,
        # but here we check if tag_file was called with the identified title)
        # However, _process_file would rename it. Let's check if a tagged file exists.
        tagged_file = album_dir / "01 - Identified Track.mp3"
        # Since _process_file is async and handles tagging, we expect the file to be renamed
        # if the match was successful.
        assert tagged_file.exists() or any("Identified Track" in f for f in os.listdir(album_dir))

    # 3. Integration: Protocol Extraction
    # Use a dummy root for protocol testing
    protocol_root = tmp_path / "repo"
    protocol_root.mkdir()
    app_dir = protocol_root / "discography_webapp"
    app_dir.mkdir()

    # Create a file with a TODO
    todo_file = app_dir / "feature.py"
    todo_file.write_text("# TODO: Implement neural uplink")

    # Initialize protocol service pointing to our tmp repo
    protocol = ProtocolService(logger)
    protocol.root_dir = str(protocol_root)

    # Run extraction
    await protocol.extract_roadmap()

    # Verify documentation updates
    todo_md = protocol_root / "TODO.md"
    assert todo_md.exists()
    content = todo_md.read_text()
    assert "Implement neural uplink" in content
    assert "TODOs" in content
