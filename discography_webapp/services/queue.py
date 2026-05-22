import json
import os
import sqlite3
from typing import List, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")


class QueueService:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.completed_albums = []
        self.queue = []
        self.pending_downloads = []
        self.load()

    def get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Ensure tables exist
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_queues (
                user_id INTEGER PRIMARY KEY,
                queue_json TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS managed_artists (
                user_id INTEGER,
                artist_id TEXT,
                name TEXT,
                is_secondary INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, artist_id)
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
                cursor.execute("SELECT queue_json FROM user_queues WHERE user_id = ?", (self.user_id,))
                row = cursor.fetchone()
                if row and row['queue_json']:
                    data = json.loads(row['queue_json'])
                    self.completed_albums = data.get('completed', [])
        except Exception as e:
            print(f"Error loading queue from DB: {e}")

    def save(self):
        if not self.user_id:
            return
        try:
            queue_json = json.dumps({"completed": self.completed_albums})
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_queues (user_id, queue_json)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET queue_json=excluded.queue_json
                """, (self.user_id, queue_json))
                conn.commit()
        except Exception as e:
            print(f"Error saving queue to DB: {e}")

    def get_managed_artists(self) -> List[Dict[str, Any]]:
        if not self.user_id:
            return []
        try:
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT artist_id, name, is_secondary FROM managed_artists WHERE user_id = ?",
                    (self.user_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error getting managed artists: {e}")
            return []

    def add_managed_artist(self, artist_id: str, name: str, is_secondary: bool = False):
        if not self.user_id:
            return
        try:
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO managed_artists (user_id, artist_id, name, is_secondary)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, artist_id) DO UPDATE SET 
                        name=excluded.name, 
                        is_secondary=excluded.is_secondary
                """, (self.user_id, artist_id, name, 1 if is_secondary else 0))
                conn.commit()
        except Exception as e:
            print(f"Error adding managed artist: {e}")

    def remove_managed_artist(self, artist_id: str):
        if not self.user_id:
            return
        try:
            with self.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM managed_artists WHERE user_id = ? AND artist_id = ?",
                    (self.user_id, artist_id)
                )
                conn.commit()
        except Exception as e:
            print(f"Error removing managed artist: {e}")

    def add_completed(self, album_info):
        # Remove any existing entry for this artist+album (to update status)
        self.completed_albums = [
            a for a in self.completed_albums
            if not (a['artist'] == album_info['artist'] and a['album'] == album_info['album'])
        ]
        self.completed_albums.append(album_info)
        self.save()

    def get_completed(self):
        return self.completed_albums
