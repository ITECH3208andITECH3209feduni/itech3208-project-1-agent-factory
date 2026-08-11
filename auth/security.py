# auth/security.py
# ──────────────────────────────────────────────────────────────
# Password hashing + JWT creation/validation (PROJ-339..343)
# Access token: 15 minutes. Refresh token: 7 days.
# ──────────────────────────────────────────────────────────────

import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set. Add it to your .env file.")


# ── Passwords ──────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ── Tokens ─────────────────────────────────────────────────────
def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(subject),
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, jti, expire


def create_access_token(user_id: int) -> str:
    token, _, _ = _create_token(user_id, "access", timedelta(minutes=ACCESS_TOKEN_MINUTES))
    return token


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at) so the caller can persist the jti."""
    return _create_token(user_id, "refresh", timedelta(days=REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str) -> dict | None:
    """Return the payload if valid and of the expected type, else None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload