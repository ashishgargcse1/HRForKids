from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> str:
    return os.getenv("APP_DB_PATH", "/data/app.db")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | None = None) -> None:
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = connect(path)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('ADMIN','PARENT','CHILD')),
            password_hash TEXT NOT NULL,
            avatar TEXT NOT NULL DEFAULT '🙂',
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            points INTEGER NOT NULL CHECK(points >= 0),
            recurrence TEXT NOT NULL CHECK(recurrence IN ('NONE','DAILY','WEEKLY')) DEFAULT 'NONE',
            due_date TEXT,
            status TEXT NOT NULL CHECK(status IN ('ASSIGNED','DONE_PENDING','APPROVED','REJECTED')) DEFAULT 'ASSIGNED',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chore_assignments (
            chore_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (chore_id, user_id),
            FOREIGN KEY(chore_id) REFERENCES chores(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS chore_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chore_id INTEGER NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            actor_user_id INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(chore_id) REFERENCES chores(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL CHECK(cost >= 0),
            is_active INTEGER NOT NULL DEFAULT 1,
            limit_per_week INTEGER,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('REQUESTED','APPROVED','DENIED')) DEFAULT 'REQUESTED',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            handled_by INTEGER,
            FOREIGN KEY(reward_id) REFERENCES rewards(id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(handled_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL,
            ref_type TEXT NOT NULL CHECK(ref_type IN ('CHORE','REWARD','ADMIN_ADJUST')),
            ref_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_chores_status ON chores(status);
        CREATE INDEX IF NOT EXISTS idx_assignments_user ON chore_assignments(user_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_user_time ON ledger(user_id, created_at);
        """
    )

    user_count = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if user_count == 0:
        admin_hash = pwd_context.hash("admin123")
        cur.execute(
            """
            INSERT INTO users (username, display_name, role, password_hash, avatar, is_active, must_change_password, created_at)
            VALUES (?, ?, 'ADMIN', ?, ?, 1, 1, ?)
            """,
            ("admin", "Admin", admin_hash, "🛡️", now_iso()),
        )
        print("WARNING: Created default admin user admin/admin123. Change password immediately.")

    conn.commit()
    conn.close()
