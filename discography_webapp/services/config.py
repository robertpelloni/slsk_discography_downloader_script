import json
import os
import sqlite3
from typing import Any, Dict


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")


class ConfigService:
    def __init__(self, user_id=None):
        self.user_id = user_id

        self.config: Dict[str, Any] = {
            "slsk_user": "",
            "slsk_pass": "",
            "download_path": "downloads",
            "preferred_format": "flac",  # can be 'flac' or 'mp3'
            "acoustid_enabled": True,
            "acoustid_api_key": "8XaBELgH",  # default test key
            "acoustid_verify": False,  # Strict verification
            "embed_lyrics": False,  # fetch and embed lyrics
            "genius_api_key": "",  # Genius API key for fallback lyrics
            "convert_to_mp3": False,  # Convert FLAC to MP3 V0
            "sentinel_enabled": False,  # Neural Audio-Quality Sentinel (fake FLAC detection)
        }
        self.load()

    def get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def load(self):
        if not self.user_id:
            return

        try:
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT config_json FROM user_configs WHERE user_id = ?", (self.user_id,))
            row = cursor.fetchone()
            conn.close()

            if row and row['config_json']:
                data = json.loads(row['config_json'])
                self.config.update(data)
        except Exception as e:
            print(f"Error loading config from DB: {e}")

    def save(self):
        if not self.user_id:
            return

        try:
            config_json = json.dumps(self.config)
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO user_configs (user_id, config_json)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET config_json=excluded.config_json
            ''',
                (self.user_id, config_json),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving config to DB: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def update_all(self, new_config: Dict[str, Any]):
        for k, v in new_config.items():
            if k in self.config:
                self.config[k] = v
        self.save()
