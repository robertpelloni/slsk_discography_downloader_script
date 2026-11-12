import json
import os
import sqlite3
from typing import Any, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "app.db")
DB_PATH = _DEFAULT_DB_PATH
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

try:
    from dotenv import load_dotenv

    if os.path.exists(ENV_FILE_PATH):
        load_dotenv(ENV_FILE_PATH, override=False)
except ImportError:
    pass

# Keys containing credentials/tokens that must live in .env rather than tracked SQLite DBs
SECRET_ENV_MAP = {
    "slsk_pass": "SLSK_PASS",
    "slsk_boost_pass": "SLSK_BOOST_PASS",
    "genius_api_key": "GENIUS_API_KEY",
}


class ConfigService:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.config: Dict[str, Any] = {
            "slsk_user": os.environ.get("SLSK_USER", ""),
            "slsk_pass": os.environ.get("SLSK_PASS", ""),
            "slsk_boost_user": os.environ.get("SLSK_BOOST_USER", ""),
            "slsk_boost_pass": os.environ.get("SLSK_BOOST_PASS", ""),
            "download_path": os.environ.get("DOWNLOAD_PATH", "downloads"),
            "preferred_format": "flac",  # can be 'flac' or 'mp3'
            "acoustid_enabled": True,
            "acoustid_api_key": "8XaBELgH",  # default public test key
            "acoustid_verify": False,  # Strict verification
            "embed_lyrics": False,  # fetch and embed lyrics
            "genius_api_key": os.environ.get("GENIUS_API_KEY", ""),
            "convert_to_mp3": False,  # Convert FLAC to MP3 V0
            "flat_file_structure": True,  # Use flat Artist - Year - Album - XX - Title.ext naming
            "sentinel_enabled": False,  # Neural Audio-Quality Sentinel (fake FLAC detection)
        }
        # Treat template 'placeholder' values as empty
        if self.config["slsk_user"] == "placeholder":
            self.config["slsk_user"] = ""
        if self.config["slsk_pass"] == "placeholder":
            self.config["slsk_pass"] = ""
        self.load()

    def get_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")

        # Ensure tables exist
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id INTEGER PRIMARY KEY,
                config_json TEXT
            )
        """)
        conn.commit()
        return conn

    def load(self):
        if not self.user_id:
            return
        try:
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT config_json FROM user_configs WHERE user_id = ?",
                    (self.user_id,),
                )
                row = cursor.fetchone()
                if row and row["config_json"]:
                    data = json.loads(row["config_json"])
                    for k, v in data.items():
                        # Preserve secrets loaded from .env when DB stores scrubbed empty string
                        if k in SECRET_ENV_MAP and not v and self.config.get(k):
                            continue
                        if k == "slsk_user" and not v and self.config.get("slsk_user"):
                            continue
                        self.config[k] = v
        except Exception as e:
            print(f"Error loading config from DB: {e}")

    def _sync_secrets_to_env(self):
        """Persist updated credentials to gitignored discography_webapp/.env when using live DB."""
        if DB_PATH != _DEFAULT_DB_PATH or self.user_id != 1:
            return
        try:
            existing: Dict[str, str] = {}
            comments = []
            if os.path.exists(ENV_FILE_PATH):
                with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.rstrip("\n")
                        if stripped.startswith("#") or "=" not in stripped:
                            if stripped:
                                comments.append(stripped)
                        else:
                            ek, ev = stripped.split("=", 1)
                            existing[ek.strip()] = ev

            existing.setdefault("PORT", os.environ.get("PORT", "8000"))
            if self.config.get("slsk_user"):
                existing["SLSK_USER"] = str(self.config["slsk_user"])
            if self.config.get("slsk_boost_user") is not None:
                existing["SLSK_BOOST_USER"] = str(self.config.get("slsk_boost_user", ""))
            for cfg_key, env_key in SECRET_ENV_MAP.items():
                val = self.config.get(cfg_key, "")
                if val:
                    existing[env_key] = str(val)

            header = comments or [
                "# Local runtime configuration (gitignored - secrets stored here per AGENTS.md)"
            ]
            out_lines = header + [f"{k}={v}" for k, v in existing.items()] + [""]
            with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines))
        except Exception as e:
            print(f"Warning: could not sync credentials to .env: {e}")

    def save(self):
        if not self.user_id:
            return
        try:
            # Never store plaintext secrets in tracked SQLite DB
            sanitized = {
                k: ("" if k in SECRET_ENV_MAP else v) for k, v in self.config.items()
            }
            config_json = json.dumps(sanitized)
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO user_configs (user_id, config_json)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET config_json=excluded.config_json
                    """,
                    (self.user_id, config_json),
                )
                conn.commit()
            self._sync_secrets_to_env()
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
