"""
Database module — Enhanced SQLite memory for DietBuddy Pro
Handles: users, messages, food logs, preferences, hydration, weekly summaries
"""

import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("dietbuddy.db")

# IST offset
IST = timedelta(hours=5, minutes=30)


def now_ist() -> datetime:
    return datetime.now(timezone.utc) + IST


def today_ist() -> str:
    return now_ist().strftime("%Y-%m-%d")


def current_hour_ist() -> int:
    return now_ist().hour


class Database:
    def __init__(self, db_path: str = "/tmp/dietbuddy.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    phone TEXT PRIMARY KEY,
                    name TEXT,
                    age TEXT,
                    gender TEXT,
                    diet_preference TEXT,
                    regional_cuisine TEXT,
                    allergies TEXT,
                    health_goal TEXT,
                    activity_level TEXT,
                    wake_time TEXT DEFAULT '07:00',
                    sleep_time TEXT DEFAULT '23:00',
                    water_goal_liters REAL DEFAULT 3.0,
                    onboarding_complete INTEGER DEFAULT 0,
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

                CREATE TABLE IF NOT EXISTS food_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    meal_type TEXT,
                    food_description TEXT NOT NULL,
                    meal_date TEXT,
                    meal_time TEXT,
                    ai_analysis TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (phone) REFERENCES users(phone)
                );

                CREATE TABLE IF NOT EXISTS water_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    glasses INTEGER DEFAULT 1,
                    logged_at TEXT DEFAULT (datetime('now')),
                    log_date TEXT,
                    FOREIGN KEY (phone) REFERENCES users(phone)
                );

                CREATE TABLE IF NOT EXISTS daily_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    checkin_date TEXT,
                    mood TEXT,
                    energy_level TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (phone) REFERENCES users(phone)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_phone
                    ON messages(phone, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_food_logs_phone
                    ON food_logs(phone, meal_date DESC);
                CREATE INDEX IF NOT EXISTS idx_water_logs_phone
                    ON water_logs(phone, log_date DESC);
            """)
            conn.commit()
            logger.info("✅ Database initialized (Pro schema)")
        finally:
            conn.close()

    # ─── User Operations ─────────────────────────────────────────

    def create_user(self, phone: str):
        conn = self._get_conn()
        try:
            conn.execute("INSERT OR IGNORE INTO users (phone) VALUES (?)", (phone,))
            conn.commit()
        finally:
            conn.close()

    def get_user(self, phone: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update_user_profile(self, phone: str, **kwargs):
        allowed = {
            "name", "age", "gender", "diet_preference", "regional_cuisine",
            "allergies", "health_goal", "activity_level", "wake_time",
            "sleep_time", "water_goal_liters", "onboarding_complete"
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return
        conn = self._get_conn()
        try:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [phone]
            conn.execute(f"UPDATE users SET {set_clause} WHERE phone = ?", values)
            conn.commit()
        finally:
            conn.close()

    def update_last_active(self, phone: str):
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE users SET last_active = datetime('now') WHERE phone = ?", (phone,)
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
                (phone, role, content),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_messages(self, phone: str, limit: int = 15) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE phone = ? ORDER BY id DESC LIMIT ?""",
                (phone, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def get_message_count(self, phone: str) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM messages WHERE phone = ?", (phone,)
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_older_messages(self, phone: str, skip_recent: int = 50,
                           limit: int = 200) -> list[dict]:
        """Get older messages beyond the recent window, for building long-term summary."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE phone = ? ORDER BY id DESC LIMIT ? OFFSET ?""",
                (phone, limit, skip_recent),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()

    def get_food_summary_by_date(self, phone: str, days: int = 30) -> list[dict]:
        """Get daily food summaries for long-term pattern awareness."""
        conn = self._get_conn()
        start_date = (now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            rows = conn.execute(
                """SELECT meal_date, 
                          GROUP_CONCAT(meal_type || ': ' || food_description, ' | ') as meals,
                          COUNT(*) as meal_count
                   FROM food_logs WHERE phone = ? AND meal_date >= ?
                   GROUP BY meal_date ORDER BY meal_date DESC""",
                (phone, start_date),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ─── Food Logging ────────────────────────────────────────────

    def log_food(self, phone: str, food_description: str, meal_type: str = None,
                 ai_analysis: str = None):
        conn = self._get_conn()
        now = now_ist()
        try:
            # Auto-detect meal type from time if not provided
            if not meal_type:
                hour = now.hour
                if 5 <= hour < 11:
                    meal_type = "breakfast"
                elif 11 <= hour < 15:
                    meal_type = "lunch"
                elif 15 <= hour < 18:
                    meal_type = "snack"
                elif 18 <= hour < 22:
                    meal_type = "dinner"
                else:
                    meal_type = "late_night"

            conn.execute(
                """INSERT INTO food_logs 
                   (phone, meal_type, food_description, meal_date, meal_time, ai_analysis)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (phone, meal_type, food_description, now.strftime("%Y-%m-%d"),
                 now.strftime("%H:%M"), ai_analysis),
            )
            conn.commit()
        finally:
            conn.close()

    def get_today_food_logs(self, phone: str) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT meal_type, food_description, meal_time, ai_analysis
                   FROM food_logs WHERE phone = ? AND meal_date = ?
                   ORDER BY id ASC""",
                (phone, today_ist()),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_food_logs_for_period(self, phone: str, days: int = 7) -> list[dict]:
        conn = self._get_conn()
        start_date = (now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            rows = conn.execute(
                """SELECT meal_type, food_description, meal_date, meal_time
                   FROM food_logs WHERE phone = ? AND meal_date >= ?
                   ORDER BY meal_date ASC, id ASC""",
                (phone, start_date),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ─── Water Logging ───────────────────────────────────────────

    def log_water(self, phone: str, glasses: int = 1):
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO water_logs (phone, glasses, log_date) VALUES (?, ?, ?)",
                (phone, glasses, today_ist()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_today_water(self, phone: str) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COALESCE(SUM(glasses), 0) as total
                   FROM water_logs WHERE phone = ? AND log_date = ?""",
                (phone, today_ist()),
            ).fetchone()
            return row["total"] if row else 0
        finally:
            conn.close()

    # ─── Daily Check-in ──────────────────────────────────────────

    def save_checkin(self, phone: str, mood: str = None, energy: str = None,
                     notes: str = None):
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO daily_checkins (phone, checkin_date, mood, energy_level, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (phone, today_ist(), mood, energy, notes),
            )
            conn.commit()
        finally:
            conn.close()

    def has_checked_in_today(self, phone: str) -> bool:
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM daily_checkins
                   WHERE phone = ? AND checkin_date = ?""",
                (phone, today_ist()),
            ).fetchone()
            return row["cnt"] > 0 if row else False
        finally:
            conn.close()

    # ─── Weekly Summary Data ─────────────────────────────────────

    def get_weekly_summary_data(self, phone: str) -> dict:
        conn = self._get_conn()
        start_date = (now_ist() - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            # Meal counts by type
            meal_counts = conn.execute(
                """SELECT meal_type, COUNT(*) as cnt
                   FROM food_logs WHERE phone = ? AND meal_date >= ?
                   GROUP BY meal_type""",
                (phone, start_date),
            ).fetchall()

            # Total meals logged
            total_meals = conn.execute(
                """SELECT COUNT(*) as cnt FROM food_logs
                   WHERE phone = ? AND meal_date >= ?""",
                (phone, start_date),
            ).fetchone()

            # Days active
            active_days = conn.execute(
                """SELECT COUNT(DISTINCT meal_date) as cnt
                   FROM food_logs WHERE phone = ? AND meal_date >= ?""",
                (phone, start_date),
            ).fetchone()

            # Average water per day
            water_data = conn.execute(
                """SELECT log_date, SUM(glasses) as daily_total
                   FROM water_logs WHERE phone = ? AND log_date >= ?
                   GROUP BY log_date""",
                (phone, start_date),
            ).fetchall()

            # All food descriptions for the week
            foods = conn.execute(
                """SELECT meal_date, meal_type, food_description
                   FROM food_logs WHERE phone = ? AND meal_date >= ?
                   ORDER BY meal_date ASC, id ASC""",
                (phone, start_date),
            ).fetchall()

            avg_water = 0
            if water_data:
                avg_water = sum(r["daily_total"] for r in water_data) / len(water_data)

            return {
                "meal_counts": {r["meal_type"]: r["cnt"] for r in meal_counts},
                "total_meals_logged": total_meals["cnt"] if total_meals else 0,
                "active_days": active_days["cnt"] if active_days else 0,
                "avg_water_glasses": round(avg_water, 1),
                "foods": [dict(r) for r in foods],
            }
        finally:
            conn.close()

    # ─── Admin / Stats ───────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._get_conn()
        try:
            total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            total_messages = conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
            total_food_logs = conn.execute("SELECT COUNT(*) as c FROM food_logs").fetchone()["c"]
            active_today = conn.execute(
                "SELECT COUNT(*) as c FROM users WHERE date(last_active) = date('now')"
            ).fetchone()["c"]
            return {
                "total_users": total_users,
                "total_messages": total_messages,
                "total_food_logs": total_food_logs,
                "active_today": active_today,
            }
        finally:
            conn.close()

    def get_all_users(self) -> list[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT u.phone, u.name, u.diet_preference, u.regional_cuisine,
                          u.health_goal, u.onboarding_complete, u.last_active,
                          COUNT(m.id) as message_count
                   FROM users u LEFT JOIN messages m ON u.phone = m.phone
                   GROUP BY u.phone ORDER BY u.last_active DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
