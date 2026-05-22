import pytest
import os
import sqlite3
from discography_webapp.services.queue import QueueService

@pytest.fixture
def queue_service(tmp_path):
    db_file = tmp_path / "test_queue.db"
    service = QueueService(db_path=str(db_file))
    yield service
    if os.path.exists(db_file):
        os.remove(db_file)

def test_managed_artists(queue_service):
    queue_service.add_managed_artist("mbid1", "Artist 1")
    artists = queue_service.get_managed_artists()
    assert len(artists) == 1
    assert artists[0]['name'] == "Artist 1"

    queue_service.remove_managed_artist("mbid1")
    assert len(queue_service.get_managed_artists()) == 0

def test_secondary_artists(queue_service):
    queue_service.add_managed_artist("mbid2", "Artist 2", is_secondary=True)
    artists = queue_service.get_managed_artists()
    assert artists[0]['is_secondary'] == 1
