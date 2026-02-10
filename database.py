"""
Database module — SQLite-based memory for DietBuddy
Handles: users, messages, conversation history, stats
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("dietbuddy.db")


class Database:
    def __init__(self, db_path: str = "/tmp/dietbuddy.db"):
        self.db_path = db_path
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent reads
        return conn
    
    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    phone TEXT PRIMARY KEY,
                    name TEXT,
                    diet_preference TEXT,
                    goal TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_active TEXT DEFAULT (datetime('now'))
                );
                
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (phone) REFERENCES users(phone)
                );
                
                CREATE INDEX IF NOT EXISTS idx_messages_phone 
                    ON messages(phone, created_at DESC);
            """)
            conn.commit()
            logger.info("✅ Database initialized")
        finally:
            conn.close()
    
    # ─── User Operations ─────────────────────────────────────────
    
    def create_user(self, phone: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO users (phone) VALUES (?)",
                (phone,)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_user(self, phone: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE phone = ?", (phone,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def update_user_profile(self, phone: str, **kwargs):
        """Update user profile fields (name, diet_preference, goal, notes)."""
        allowed = {"name", "diet_preference", "goal", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v}
        
        if not updates:
            return
        
        conn = self._get_conn()
        try:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [phone]
            conn.execute(
                f"UPDATE users SET {set_clause} WHERE phone = ?",
                values
            )
            conn.commit()
        finally:
            conn.close()
    
    def update_last_active(self, phone: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE users SET last_active = datetime('now') WHERE phone = ?",
                (phone,)
            )
            conn.commit()
        finally:
            conn.close()
    
    # ─── Message Operations ──────────────────────────────────────
    
    def save_message(self, phone: str, role: str, content: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (phone, role, content) VALUES (?, ?, ?)",
                (phone, role, content)
            )
            conn.commit()
        finally:
            conn.close()
    
    def get_recent_messages(self, phone: str, limit: int = 15) -> list[dict]:
        """Get last N messages for a user, ordered oldest first (for LLM context)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT role, content, created_at FROM messages 
                   WHERE phone = ? 
                   ORDER BY id DESC LIMIT ?""",
                (phone, limit)
            ).fetchall()
            # Reverse to get chronological order
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()
    
    def get_message_count(self, phone: str) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE phone = ?",
                (phone,)
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()
    
    # ─── Admin / Stats ───────────────────────────────────────────
    
    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            total_messages = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
            active_today = conn.execute(
                "SELECT COUNT(*) as c FROM users WHERE date(last_active) = date('now')"
            ).fetchone()["c"]
            
            return {
                "total_users": total_users,
                "total_messages": total_messages,
                "active_today": active_today,
            }
        finally:
            conn.close()
    
    def get_all_users(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT u.phone, u.name, u.diet_preference, u.last_active,
                          COUNT(m.id) as message_count
                   FROM users u
                   LEFT JOIN messages m ON u.phone = m.phone
                   GROUP BY u.phone
                   ORDER BY u.last_active DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
