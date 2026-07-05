import pytest
import os
import sqlite3

from discography_webapp.services.config import ConfigService, DB_PATH

@pytest.fixture(autouse=True)
def setup_db():
    # Make sure the data directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    # Initialize the sqlite table
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_configs (
            user_id INTEGER PRIMARY KEY,
            config_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

    yield

    # Teardown
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

def test_config_initialization():
    config = ConfigService(user_id=1)
    assert config.get("slsk_user") == ""
    assert config.get("preferred_format") == "flac"

def test_config_save_and_load():
    config = ConfigService(user_id=2)
    config.set("slsk_user", "test_user")
    config.set("preferred_format", "mp3")

    # Reload should read from DB
    new_config = ConfigService(user_id=2)
    assert new_config.get("slsk_user") == "test_user"
    assert new_config.get("preferred_format") == "mp3"

def test_config_update_all():
    config = ConfigService(user_id=3)
    updates = {
        "slsk_user": "bulk_user",
        "embed_lyrics": True,
        "invalid_key": "should not save"
    }
    config.update_all(updates)

    new_config = ConfigService(user_id=3)
    assert new_config.get("slsk_user") == "bulk_user"
    assert new_config.get("embed_lyrics") == True
    assert new_config.get("invalid_key") is None
