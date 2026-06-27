import pytest
from unittest.mock import MagicMock
from discography_webapp.services.protocol import ProtocolService

@pytest.fixture
def protocol_service():
    logger = MagicMock()
    service = ProtocolService(logger)
    return service

def test_roadmap_extraction(protocol_service, tmp_path):
    # Setup mock root dir
    mock_root = tmp_path / "repo"
    mock_root.mkdir()
    app_dir = mock_root / "discography_webapp"
    app_dir.mkdir()

    # Create a file with a TODO
    test_file = app_dir / "test.py"
    test_file.write_text("# TODO: Implement this feature\nprint('hello')")

    protocol_service.root_dir = str(mock_root)

    import asyncio
    asyncio.run(protocol_service.extract_roadmap())

    todo_file = mock_root / "TODO.md"
    assert todo_file.exists()
    content = todo_file.read_text()
    assert "TODO: Implement this feature" in content

def test_git_commands_fail_gracefully(protocol_service):
    # This should fail as we are likely not in a git repo in some environments,
    # or at least we can mock the failure.
    protocol_service._run_git = MagicMock(side_effect=Exception("Git error"))

    import asyncio
    with pytest.raises(Exception):
        asyncio.run(protocol_service.sync_repository())
