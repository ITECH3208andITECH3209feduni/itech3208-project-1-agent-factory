# agent/auth.py
# ──────────────────────────────────────────────────────────────
# Lightweight username/password auth for the Web UI (PROJ-349-353)
#
# Deliberately stdlib-only — no bcrypt/passlib/itsdangerous — so login
# doesn't add a single new pip dependency beyond requirements_web.txt.
#
#   Passwords — PBKDF2-HMAC-SHA256, 200k iterations, random 16-byte
#               salt per user. Stored in outputs/auth.db (gitignored).
#   Sessions  — signed, stateless tokens (HMAC-SHA256 over
#               "username:expiry"), held client-side in an httponly
#               cookie. There's no server-side session table to
#               garbage-collect: verifying is just "recompute the
#               signature and check the expiry," and logging out is
#               just "the browser stops sending the cookie."
# ──────────────────────────────────────────────────────────────

import base64
import binascii
import hashlib
import hmac
import os
import re
import sqlite3
import time
from datetime import datetime

from config.settings import AUTH_DB, AUTH_SECRET_KEY

SESSION_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days
PBKDF2_ITERATIONS = 200_000
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


class AuthError(Exception):
    """Raised for registration/login failures with a user-facing message."""


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUTH_DB), exist_ok=True)
    conn = sqlite3.connect(AUTH_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return base64.b64encode(digest).decode("ascii")


# ── Registration / login ─────────────────────────────────────────


def register_user(username: str, password: str) -> None:
    """Create a new user. Raises AuthError on invalid input or a
    username that's already taken."""
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError(
            "Username must be 3-32 characters: letters, numbers, '.', '_', '-'."
        )
    if not password or len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")

    salt = os.urandom(16)
    password_hash = _hash_password(password, salt)

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, salt, password_hash, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                username,
                base64.b64encode(salt).decode("ascii"),
                password_hash,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise AuthError("That username is already taken.")
    finally:
        conn.close()


def verify_login(username: str, password: str) -> None:
    """Raises AuthError if the username/password combination is invalid.
    Returns None (no exception) on success."""
    username = (username or "").strip()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT salt, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    # Same error either way — don't leak whether the username exists.
    invalid = AuthError("Invalid username or password.")
    if row is None:
        raise invalid

    salt = base64.b64decode(row["salt"])
    expected = _hash_password(password, salt)
    if not hmac.compare_digest(expected, row["password_hash"]):
        raise invalid


# ── Session tokens (signed, stateless) ────────────────────────────


def create_session_token(username: str) -> str:
    """Return an opaque, signed token embedding username + expiry."""
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{username}:{expires_at}"
    signature = _sign(payload)
    raw = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def verify_session_token(token: str) -> str | None:
    """Return the username if the token is valid and unexpired, else None."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires_at, signature = raw.rsplit(":", 2)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None

    payload = f"{username}:{expires_at}"
    if not hmac.compare_digest(_sign(payload), signature):
        return None

    try:
        if int(expires_at) < int(time.time()):
            return None
    except ValueError:
        return None

    return username


def _sign(payload: str) -> str:
    return hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
