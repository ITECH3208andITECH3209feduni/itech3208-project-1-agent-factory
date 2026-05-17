# api/auth.py
# ──────────────────────────────────────────────────────────────
# API key authentication dependency for /api/* endpoints.
# PROJ-113.
#
# Accepts the key in either:
#   - X-API-Key header (standard)
#   - ?api_key=... query parameter (convenient for browser/curl)
#
# Fail-closed: if API_KEY is unset/empty in env, ALL requests fail.
# ──────────────────────────────────────────────────────────────

import os

from dotenv import load_dotenv
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

# Load .env at module import (idempotent — safe if already loaded elsewhere).
load_dotenv()

_API_KEY_HEADER_NAME = "X-API-Key"
_API_KEY_QUERY_NAME  = "api_key"

# auto_error=False so we can check both sources before raising.
_header_scheme = APIKeyHeader(name=_API_KEY_HEADER_NAME, auto_error=False)
_query_scheme  = APIKeyQuery(name=_API_KEY_QUERY_NAME,  auto_error=False)


def _get_expected_key() -> str:
    """Read the expected API key from env at request time (not import time).

    Reading per-request lets tests monkeypatch env vars without re-importing.
    """
    return os.getenv("API_KEY", "").strip()


def require_api_key(
    header_key: str = Security(_header_scheme),
    query_key:  str = Security(_query_scheme),
) -> str:
    """FastAPI dependency. Raises 401 unless a valid key is provided.

    Returns the validated key string (useful for logging if needed).
    """
    expected = _get_expected_key()

    if not expected:
        # Fail-closed: server misconfigured, reject everything.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API authentication is not configured on this server.",
        )

    provided = header_key or query_key
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide via X-API-Key header or ?api_key= query parameter.",
        )

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return provided