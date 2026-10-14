"""Organisation-scoped API keys. Plaintext keys are returned only once."""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.db import get_conn
from auth.rbac import require_admin

router = APIRouter(prefix="/orgs/api-keys", tags=["API key management"])


def init_api_keys():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS organisation_api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                revoked_at TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_org "
            "ON organisation_api_keys(org_id)"
        )


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_api_key(org_id: int, label: str, created_by: str) -> dict:
    init_api_keys()
    raw_key = "afk_" + secrets.token_urlsafe(32)
    prefix = raw_key[:12]

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO organisation_api_keys
                (org_id, label, key_prefix, key_hash, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (org_id, label.strip(), prefix, _hash_key(raw_key), created_by),
        )
        key_id = cur.lastrowid

    return {
        "id": key_id,
        "key": raw_key,
        "label": label.strip(),
        "prefix": prefix,
        "warning": "Copy this key now. It cannot be shown again.",
    }


def list_api_keys(org_id: int) -> list[dict]:
    init_api_keys()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, label, key_prefix, created_by, created_at, revoked_at
            FROM organisation_api_keys
            WHERE org_id = ?
            ORDER BY id DESC
            """,
            (org_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_api_key(key_id: int, org_id: int) -> bool:
    init_api_keys()
    revoked_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE organisation_api_keys
            SET revoked_at = ?
            WHERE id = ? AND org_id = ? AND revoked_at IS NULL
            """,
            (revoked_at, key_id, org_id),
        )
        return cur.rowcount == 1


def authenticate_api_key(raw_key: str) -> dict | None:
    """Validate a key and return a least-privilege staff identity."""
    if not raw_key:
        return None

    init_api_keys()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, org_id
            FROM organisation_api_keys
            WHERE key_hash = ? AND revoked_at IS NULL
            """,
            (_hash_key(raw_key),),
        ).fetchone()

    if row is None:
        return None

    return {
        "username": f"api-key:{row['id']}",
        "org_id": int(row["org_id"]),
        "role": "staff",
        "api_key_id": int(row["id"]),
        "auth_method": "api_key",
    }


class CreateAPIKeyRequest(BaseModel):
    label: str = Field(default="API key", min_length=1, max_length=100)


@router.post("", status_code=201)
def create_key(
    body: CreateAPIKeyRequest,
    identity: dict = Depends(require_admin),
):
    return create_api_key(
        org_id=identity["org_id"],
        label=body.label,
        created_by=identity["username"],
    )


@router.get("")
def get_keys(identity: dict = Depends(require_admin)):
    return {"keys": list_api_keys(identity["org_id"])}


@router.delete("/{key_id}")
def delete_key(
    key_id: int,
    identity: dict = Depends(require_admin),
):
    if not revoke_api_key(key_id, identity["org_id"]):
        raise HTTPException(
            status_code=404,
            detail="Active API key not found in your organisation.",
        )
    return {"status": "revoked", "id": key_id}
