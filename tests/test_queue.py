import pytest
import os
from discography_webapp.services.queue import QueueService

@pytest.fixture
def queue_service(tmp_path):
    # Mocking DB_PATH in the module
    import discography_webapp.services.queue as queue_mod
    original_db_path = queue_mod.DB_PATH
    db_file = tmp_path / "test_queue.db"
    queue_mod.DB_PATH = str(db_file)

    service = QueueService(user_id=1)
    yield service

    # Ensure all connections are closed and collected before deleting
    import gc
    import time
    gc.collect()
    time.sleep(0.1)

    queue_mod.DB_PATH = original_db_path
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except PermissionError:
            pass # Ignore if still locked on Windows, it's a temp file anyway

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
