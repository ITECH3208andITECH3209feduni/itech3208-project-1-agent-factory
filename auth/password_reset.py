# auth/password_reset.py
# ──────────────────────────────────────────────────────────────
# Password recovery (PROJ-408)
#
# Flow:
#   1. POST /auth/forgot-password  — always returns 202, whether or
#      not the email exists. Revealing which addresses are
#      registered is an account-enumeration leak.
#   2. A random token is generated. Only its SHA-256 hash is
#      stored, so a database read doesn't yield usable tokens.
#   3. POST /auth/reset-password   — validates the token, sets the
#      new password, marks the token used, and revokes every
#      refresh token for that user so existing sessions die.
#
# Tokens are single-use and expire after RESET_TOKEN_MINUTES.
# ──────────────────────────────────────────────────────────────

import hashlib
import logging
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from auth.db import get_conn

load_dotenv()

log = logging.getLogger("password_reset")

RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "30"))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

RESET_SCHEMA = """
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    expires_at TEXT    NOT NULL,
    used_at    TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_resets_user ON password_resets(user_id);
"""


def init_reset_table() -> None:
    with get_conn() as conn:
        conn.executescript(RESET_SCHEMA)


def _hash(token: str) -> str:
    """Store only the hash — a leaked table shouldn't yield live tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(user_id: int) -> str:
    """
    Issue a single-use reset token. Any outstanding tokens for this
    user are invalidated first, so requesting a second reset email
    retires the first link.
    """
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_MINUTES)

    with get_conn() as conn:
        conn.execute(
            "UPDATE password_resets SET used_at = datetime('now')"
            " WHERE user_id = ? AND used_at IS NULL",
            (user_id,),
        )
        conn.execute(
            "INSERT INTO password_resets (token_hash, user_id, expires_at)"
            " VALUES (?, ?, ?)",
            (_hash(token), user_id, expires.isoformat()),
        )
    return token


def consume_reset_token(token: str) -> int | None:
    """
    Validate and burn a token. Returns the user_id, or None if the
    token is unknown, already used, or expired.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at, used_at FROM password_resets"
            " WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()

        if row is None or row["used_at"] is not None:
            return None

        try:
            expires = datetime.fromisoformat(row["expires_at"])
        except ValueError:
            return None
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return None

        conn.execute(
            "UPDATE password_resets SET used_at = datetime('now')"
            " WHERE token_hash = ?",
            (_hash(token),),
        )
        return row["user_id"]


def set_password(user_id: int, password_hash: str) -> None:
    """Change the password and kill every existing session."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        # A password change should log out everywhere — otherwise a
        # stolen refresh token survives the reset.
        conn.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?",
            (user_id,),
        )


# ── Delivery ───────────────────────────────────────────────────
def _send_via_smtp(to_email: str, reset_url: str) -> bool:
    """Send through SMTP if credentials are configured."""
    host = os.getenv("SMTP_HOST")
    if not host:
        return False

    import smtplib
    from email.message import EmailMessage

    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", user or "noreply@agentfactory.local")

    msg = EmailMessage()
    msg["Subject"] = "Reset your Agent Factory password"
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(
        "Someone requested a password reset for this address.\n\n"
        f"To choose a new password, open:\n{reset_url}\n\n"
        f"The link expires in {RESET_TOKEN_MINUTES} minutes and can be used once.\n"
        "If you didn't request this, you can ignore this email."
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as exc:
        log.error("SMTP send failed: %s", exc)
        return False


def deliver_reset_link(to_email: str, token: str) -> str:
    """
    Deliver the reset link and return the channel used.

    SMTP when SMTP_HOST is set, otherwise the link is written to the
    server log. Console delivery keeps the whole flow testable
    without mail credentials; set SMTP_HOST to switch it on.
    """
    reset_url = f"{APP_BASE_URL}/reset-password?token={token}"

    if _send_via_smtp(to_email, reset_url):
        log.info("reset link emailed to %s", to_email)
        return "smtp"

    log.warning(
        "No SMTP configured — reset link for %s (expires in %s min):\n    %s",
        to_email, RESET_TOKEN_MINUTES, reset_url,
    )
    return "console"