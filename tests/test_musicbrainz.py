import pytest
from discography_webapp.services.musicbrainz import MusicBrainzService
import musicbrainzngs

class MockMusicBrainzResponse:
    def __init__(self, data):
        self.data = data

@pytest.fixture
def mb_service():
    return MusicBrainzService()

def test_search_artist(monkeypatch, mb_service):
    def mock_search_artists(artist, limit):
        return {'artist-list': [{'id': '123', 'name': 'Aphex Twin'}]}

    monkeypatch.setattr(musicbrainzngs, "search_artists", mock_search_artists)

    results = mb_service.search_artist("Aphex Twin")
    assert len(results) == 1
    assert results[0]['name'] == 'Aphex Twin'
    assert results[0]['id'] == '123'

def test_search_artist_error_handling(monkeypatch, mb_service):
    def mock_search_artists_fail(artist, limit):
        raise Exception("Network error")

    monkeypatch.setattr(musicbrainzngs, "search_artists", mock_search_artists_fail)

    results = mb_service.search_artist("Unknown")
    assert results == []
