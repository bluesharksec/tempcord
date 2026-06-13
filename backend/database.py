import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List
from contextlib import contextmanager

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    webhook_id TEXT NOT NULL,
                    webhook_token TEXT NOT NULL,
                    username TEXT NOT NULL,
                    avatar_url TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS message_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_expires_at ON sessions(expires_at)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_session_timestamp ON message_logs(session_id, timestamp)
            ''')
    
    def create_session(self, session_id: str, guild_id: str, channel_id: str,
                      webhook_id: str, webhook_token: str, username: str,
                      avatar_url: str, expires_at: datetime) -> bool:
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO sessions 
                    (session_id, guild_id, channel_id, webhook_id, webhook_token,
                     username, avatar_url, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (session_id, guild_id, channel_id, webhook_id, webhook_token,
                      username, avatar_url, datetime.now(timezone.utc), expires_at))
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            row = conn.execute('''
                SELECT * FROM sessions WHERE session_id = ?
            ''', (session_id,)).fetchone()
            return dict(row) if row else None
    
    def delete_session(self, session_id: str):
        with self.get_connection() as conn:
            conn.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
            conn.execute('DELETE FROM message_logs WHERE session_id = ?', (session_id,))
    
    def get_expired_sessions(self) -> List[Dict]:
        with self.get_connection() as conn:
            rows = conn.execute('''
                SELECT * FROM sessions WHERE expires_at <= ?
            ''', (datetime.now(timezone.utc),)).fetchall()
            return [dict(row) for row in rows]
    
    def log_message(self, session_id: str):
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO message_logs (session_id, timestamp)
                VALUES (?, ?)
            ''', (session_id, datetime.now(timezone.utc)))
    
    def get_message_count(self, session_id: str, since: datetime) -> int:
        with self.get_connection() as conn:
            row = conn.execute('''
                SELECT COUNT(*) as count FROM message_logs
                WHERE session_id = ? AND timestamp >= ?
            ''', (session_id, since)).fetchone()
            return row['count'] if row else 0
