# auth/db.py
# ──────────────────────────────────────────────────────────────
# SQLite users table for JWT authentication (PROJ-339..343)
# ──────────────────────────────────────────────────────────────

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("AUTH_DB_PATH", "auth_users.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti        TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    expires_at TEXT    NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def create_user(email: str, password_hash: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.lower().strip(), password_hash),
        )
        return cur.lastrowid


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def store_refresh_token(jti: str, user_id: int, expires_at: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (jti, user_id, expires_at) VALUES (?, ?, ?)",
            (jti, user_id, expires_at),
        )


def is_refresh_token_valid(jti: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT revoked FROM refresh_tokens WHERE jti = ?", (jti,)
        ).fetchone()
    return row is not None and row["revoked"] == 0


def revoke_refresh_token(jti: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE refresh_tokens SET revoked = 1 WHERE jti = ?", (jti,))