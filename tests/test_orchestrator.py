import pytest
import os
from unittest.mock import MagicMock
from discography_webapp.services.orchestrator import Orchestrator, normalize, sanitize_name

@pytest.fixture
def mock_services():
    return {
        'logger': MagicMock(),
        'mb_service': MagicMock(),
        'slsk_service': MagicMock(),
        'config_service': MagicMock(),
        'post_processor': MagicMock(),
        'queue_service': MagicMock()
    }

@pytest.fixture
def orchestrator(mock_services):
    mock_services['queue_service'].get_completed.return_value = []
    return Orchestrator(**mock_services, user_id=1)

def test_normalize():
    assert normalize("Growling Mad Scientists") == "growlingmadscientists"
    assert normalize("G.M.S.") == "gms"
    assert normalize("Infected Mushroom - Converting Veggies") == "infectedmushroomconvertingveggies"

def test_sanitize_name():
    assert sanitize_name("Artist / Album?") == "Artist  Album"
    assert sanitize_name("Valid-Name_123") == "Valid-Name_123"

def test_library_indexing(orchestrator, tmp_path):
    # Setup a mock downloads directory
    downloads = tmp_path / "downloads"
    downloads.mkdir()

    artist_dir = downloads / "GMS"
    artist_dir.mkdir()

    album_dir = artist_dir / "2002 - No Rules"
    album_dir.mkdir()

    # Create mock audio files
    (album_dir / "01 - No Rules.flac").write_bytes(b"dummy data" * 100000)
    (album_dir / "02 - Diesel Drift.flac").write_bytes(b"dummy data" * 100000)
    (album_dir / "03 - Do Limit.flac").write_bytes(b"dummy data" * 100000)

    # Mock os.listdir to use our tmp_path
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        index = orchestrator._build_existing_index()
        # The key should be normalized artist + album
        # keys generated: gmsnorules, growlingmadscientistsnorules, etc.
        assert "gmsnorules" in index
        assert index["gmsnorules"]["count"] == 3
        assert index["gmsnorules"]["year"] == "2002"
    finally:
        os.chdir(original_cwd)

def test_candidate_ranking(orchestrator):
    orchestrator.config_service.get.side_effect = lambda k, v: v if k != 'preferred_format' else 'flac'

    results = [
        {
            'user': 'user1',
            'filename': 'Artist/Album/01.mp3',
            'extension': '.mp3',
            'size': 1000000,
            'bitrate': 320,
            'speed': 100,
            'slots': True
        },
        {
            'user': 'user2',
            'filename': 'Artist/Album/01.flac',
            'extension': '.flac',
            'size': 10000000,
            'bitrate': 0,
            'speed': 100,
            'slots': True
        }
    ]

    ranked = orchestrator._rank_candidates(results, artist_name="Artist")
    # user2 has flac, should be ranked higher
    assert ranked[0]['user'] == 'user2'
    assert ranked[0]['score'] > ranked[1]['score']

def test_psytrance_filtering():
    from discography_webapp.services.orchestrator import is_psytrance_artist

    # White-listed artist
    assert is_psytrance_artist({'name': 'GMS', 'tag-list': []}) is True

    # Tag-matched artist
    assert is_psytrance_artist({'name': 'Unknown', 'tag-list': [{'name': 'goa trance'}]}) is True

    # Disallowed tag
    assert is_psytrance_artist({'name': 'Britney Spears', 'tag-list': [{'name': 'pop'}]}) is False

def test_build_queries(orchestrator):
    queries = orchestrator._build_queries("GMS", "No Rules", "2002")
    assert "GMS No Rules" in queries
    assert "GMS 2002 No Rules" in queries
    assert "Growling Mad Scientists No Rules" in queries # Alias check

def test_filter_related_artists(orchestrator):
    related = [
        {'id': '1', 'name': 'Artist A', 'tag-list': [{'name': 'psytrance'}]},
        {'id': '2', 'name': 'Artist B', 'tag-list': [{'name': 'pop'}]},
        {'id': '3', 'name': 'Artist C', 'tag-list': []}
    ]
    filtered = orchestrator._filter_related_artists(related, "GMS")
    
    # Artist A should be kept (psytrance tag)
    # Artist B should be removed (pop tag)
    # Artist C should be removed (no tags and not a known side project of GMS)
    
    names = [a['name'] for a in filtered]
    assert 'Artist A' in names
    assert 'Artist B' not in names
    assert 'Artist C' not in names

    # Test side-project rule: Artist D has no tags but is a member of GMS
    related_with_member = [
        {'id': '4', 'name': 'Artist D', 'tag-list': [], 'relation': 'member of GMS'}
    ]
    filtered_member = orchestrator._filter_related_artists(related_with_member, "GMS")
    assert 'Artist D' in [a['name'] for a in filtered_member]
