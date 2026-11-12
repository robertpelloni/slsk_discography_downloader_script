import os
import json
import sqlite3
from unittest.mock import patch

import pytest

from discography_webapp.services.config import ConfigService


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    test_db_path = str(tmp_path / "test_app.db")
    with patch("discography_webapp.services.config.DB_PATH", test_db_path):
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id INTEGER PRIMARY KEY,
                config_json TEXT
            )
        """)
        conn.commit()
        conn.close()
        yield


def test_config_initialization(tmp_path):
    test_db_path = str(tmp_path / "test_app.db")
    with (
        patch("discography_webapp.services.config.DB_PATH", test_db_path),
        patch.dict(os.environ, {"SLSK_USER": "", "SLSK_PASS": ""}),
    ):
        config = ConfigService(user_id=1)
        assert config.get("slsk_user") == ""
        assert config.get("preferred_format") == "flac"


def test_config_save_and_load(tmp_path):
    test_db_path = str(tmp_path / "test_app.db")
    with (
        patch("discography_webapp.services.config.DB_PATH", test_db_path),
        patch.dict(os.environ, {"SLSK_USER": "", "SLSK_PASS": ""}),
    ):
        config = ConfigService(user_id=2)
        config.set("slsk_user", "test_user")
        config.set("preferred_format", "mp3")

        new_config = ConfigService(user_id=2)
        assert new_config.get("slsk_user") == "test_user"
        assert new_config.get("preferred_format") == "mp3"


def test_config_update_all(tmp_path):
    test_db_path = str(tmp_path / "test_app.db")
    with (
        patch("discography_webapp.services.config.DB_PATH", test_db_path),
        patch.dict(os.environ, {"SLSK_USER": "", "SLSK_PASS": ""}),
    ):
        config = ConfigService(user_id=3)
        updates = {
            "slsk_user": "bulk_user",
            "embed_lyrics": True,
            "invalid_key": "should not save",
        }
        config.update_all(updates)

        new_config = ConfigService(user_id=3)
        assert new_config.get("slsk_user") == "bulk_user"
        assert new_config.get("embed_lyrics") is True
        assert new_config.get("invalid_key") is None


def test_config_secrets_not_stored_in_sqlite(tmp_path):
    test_db_path = str(tmp_path / "test_app.db")
    with (
        patch("discography_webapp.services.config.DB_PATH", test_db_path),
        patch.dict(os.environ, {"SLSK_USER": "env_user", "SLSK_PASS": "super_secret"}),
    ):
        config = ConfigService(user_id=4)
        config.set("preferred_format", "mp3")
        assert config.get("slsk_pass") == "super_secret"

        conn = sqlite3.connect(test_db_path)
        raw_json = conn.execute(
            "SELECT config_json FROM user_configs WHERE user_id = 4"
        ).fetchone()[0]
        conn.close()
        stored = json.loads(raw_json)
        assert stored["slsk_pass"] == ""
        assert "super_secret" not in raw_json
