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
        self.pending_downloads = []
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
            cursor.execute("SELECT queue_json FROM user_queues WHERE user_id = ?", (self.user_id,))
            row = cursor.fetchone()
            conn.close()

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
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_queues (user_id, queue_json)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET queue_json=excluded.queue_json
            ''', (self.user_id, queue_json))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving queue to DB: {e}")

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
