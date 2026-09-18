# auth/org_routes.py
# ──────────────────────────────────────────────────────────────
# Organisation registration (PROJ-406) + profile (PROJ-409)
#
# Registration creates an organisation and its first user in a
# single transaction. If either half fails, neither is written —
# an orphaned org with no owner would be unreachable, and a user
# with no org_id would break the scoping rule in PROJ-410.
#
# Auth model resolution: PROJ-409's GET/PATCH /orgs/me originally
# needed a `current_user` dependency resolving org_id from a JWT
# (auth/routes.py, PROJ-339) that was never wired into
# app/web_ui/main.py — it would have collided with Sprint 3's
# existing, working session-cookie /auth/login. Rather than build
# against a token flow with no way to issue a token, /orgs/me below
# is built on get_current_username (app/web_ui/auth_routes.py) — the
# auth that's actually live — plus a lightweight org_id column added
# to agent/auth.py's own users table (agent.auth.get_user_org_id /
# set_user_org_id). A Sprint-3-authenticated user claims an org via
# /orgs/claim, the same way /orgs/register creates one for a fresh
# JWT-style signup.
# ──────────────────────────────────────────────────────────────

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from agent.auth import get_user_org_id, set_user_org_id
from app.web_ui.auth_routes import get_current_username
from auth import tenancy
from auth.db import DB_PATH, get_user_by_email
from auth.security import hash_password
from contracts.schemas import (
    OrgOut,
    OrgRegistration,
    OrgUpdate,
    RegistrationOut,
)

router = APIRouter(prefix="/orgs", tags=["organisations"])


def _row_to_org(row: sqlite3.Row) -> OrgOut:
    return OrgOut(
        id=row["id"],
        name=row["name"],
        contact_email=row["contact_email"],
        timezone=row["timezone"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


@router.post("/register", response_model=RegistrationOut, status_code=201)
def register_org(body: OrgRegistration):
    """
    Create an organisation and its owner user atomically.

    Done with an explicit transaction rather than the usual
    get_conn() helper, because two inserts must succeed or fail
    together.
    """
    if get_user_by_email(body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "INSERT INTO organisations (name, contact_email, timezone) VALUES (?, ?, ?)",
            (body.org_name.strip(), str(body.email), body.timezone),
        )
        org_id = cur.lastrowid

        cur = conn.execute(
            "INSERT INTO users (email, password_hash, org_id, role) VALUES (?, ?, ?, ?)",
            (str(body.email).lower().strip(), hash_password(body.password), org_id, "owner"),
        )
        user_id = cur.lastrowid

        org_row = conn.execute(
            "SELECT * FROM organisations WHERE id = ?", (org_id,)
        ).fetchone()

        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Registration failed: {exc}") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return RegistrationOut(org=_row_to_org(org_row), user_id=user_id, role="owner")


def _require_org(username: str) -> int:
    org_id = get_user_org_id(username)
    if org_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You're not part of an organisation yet — create one with POST /orgs/claim.",
        )
    return org_id


@router.post("/claim", response_model=OrgOut, status_code=201)
def claim_org(body: OrgRegistration, username: str = Depends(get_current_username)):
    """
    Create an organisation owned by the logged-in Sprint 3 user.

    Same shape as /orgs/register, but for a caller who already has a
    session-cookie login (agent/auth.py) rather than signing up fresh —
    password/email on the body are accepted for org contact details
    but a new login identity is not created, this one is just linked
    to the new org.
    """
    if get_user_org_id(username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already belong to an organisation.")

    org_id = tenancy.create_org(body.org_name, str(body.email), body.timezone)
    set_user_org_id(username, org_id)
    return _row_to_org(tenancy.get_org(org_id))


@router.get("/me", response_model=OrgOut)
def get_my_org(username: str = Depends(get_current_username)):
    """Return the caller's own organisation. org_id comes from the
    logged-in session, not a client-supplied parameter, so a user
    can't read another org by changing one (PROJ-409)."""
    org_id = _require_org(username)
    row = tenancy.get_org(org_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return _row_to_org(row)


@router.patch("/me", response_model=OrgOut)
def update_my_org(body: OrgUpdate, username: str = Depends(get_current_username)):
    """Update the caller's organisation."""
    org_id = _require_org(username)
    tenancy.update_org(
        org_id,
        name=body.name,
        contact_email=str(body.contact_email) if body.contact_email else None,
        timezone=body.timezone,
    )
    return _row_to_org(tenancy.get_org(org_id))