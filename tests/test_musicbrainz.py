import pytest
import musicbrainzngs
from discography_webapp.services.musicbrainz import MusicBrainzService


@pytest.fixture
def mb_service(tmp_path):
    return MusicBrainzService(cache_db_path=str(tmp_path / "test_mb_cache.db"))


def test_search_artist(monkeypatch, mb_service):
    monkeypatch.setattr("time.sleep", lambda _s: None)

    def mock_search_artists(artist, limit):
        return {"artist-list": [{"id": "123", "name": "Aphex Twin"}]}

    monkeypatch.setattr(musicbrainzngs, "search_artists", mock_search_artists)

    results = mb_service.search_artist("Aphex Twin")
    assert len(results) == 1
    assert results[0]["name"] == "Aphex Twin"
    assert results[0]["id"] == "123"


def test_search_artist_error_handling(monkeypatch, mb_service):
    monkeypatch.setattr("time.sleep", lambda _s: None)

    def mock_search_artists_fail(artist, limit):
        raise Exception("Network error")

    monkeypatch.setattr(musicbrainzngs, "search_artists", mock_search_artists_fail)

    results = mb_service.search_artist("Unknown")
    assert results == []


def test_get_related_artists_respects_max_api_calls(monkeypatch, mb_service):
    calls = {"count": 0}

    def fake_get_artist_by_id(aid, includes=None):
        calls["count"] += 1
        if aid == "root":
            return {
                "id": "root",
                "name": "Root Group",
                "type": "Group",
                "artist-relation-list": [
                    {
                        "type": "member of band",
                        "direction": "backward",
                        "artist": {"id": f"m{i}", "name": f"Member {i}", "type": "Person"},
                    }
                    for i in range(10)
                ],
            }
        return {"id": aid, "name": f"Artist {aid}", "tag-list": []}

    monkeypatch.setattr(mb_service, "get_artist_by_id", fake_get_artist_by_id)
    related = mb_service.get_related_artists("root", depth=1, max_api_calls=4)
    assert calls["count"] <= 4
    assert len(related) <= 3
