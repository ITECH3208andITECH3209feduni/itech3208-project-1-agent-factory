# auth/db.py
# ──────────────────────────────────────────────────────────────
# SQLite users table for JWT authentication (PROJ-339..343)
# Per-user encrypted API key storage (PROJ-344..348)
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
    """Create tables if they don't exist, then apply migrations."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the initial schema. Safe to re-run."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "anthropic_key_enc" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN anthropic_key_enc TEXT")
    if "anthropic_key_updated_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN anthropic_key_updated_at TEXT")


# ── Users ──────────────────────────────────────────────────────
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


# ── Refresh tokens ─────────────────────────────────────────────
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


# ── Per-user API keys ──────────────────────────────────────────
def set_user_api_key(user_id: int, encrypted_key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET anthropic_key_enc = ?, "
            "anthropic_key_updated_at = datetime('now') WHERE id = ?",
            (encrypted_key, user_id),
        )


def clear_user_api_key(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET anthropic_key_enc = NULL, "
            "anthropic_key_updated_at = NULL WHERE id = ?",
            (user_id,),
        )


def get_user_api_key_enc(user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT anthropic_key_enc FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["anthropic_key_enc"] if row else None