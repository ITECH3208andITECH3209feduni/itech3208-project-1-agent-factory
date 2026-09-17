# auth/org_routes.py
# ──────────────────────────────────────────────────────────────
# Organisation registration (PROJ-406)
#
# Registration creates an organisation and its first user in a
# single transaction. If either half fails, neither is written —
# an orphaned org with no owner would be unreachable, and a user
# with no org_id would break the scoping rule in PROJ-410.
#
# PROJ-409 (organisation profile — GET/PATCH /orgs/me) is NOT
# included here. Both endpoints need a `current_user` dependency
# that resolves the caller's own org_id from an auth token, but the
# JWT login flow that would issue that token (PROJ-339, auth/routes.py)
# was never wired into app/web_ui/main.py — it would collide with
# Sprint 3's existing session-cookie /auth/login. Standardising the
# whole app on one auth model is a real decision for the team, not
# something to resolve unilaterally inside a merge conflict fix.
# Building /orgs/me against a token flow that has no way to issue a
# valid token would just 401 forever, so it's left for that decision
# rather than merged half-working.
# ──────────────────────────────────────────────────────────────

import sqlite3

from fastapi import APIRouter, HTTPException, status

from auth.db import DB_PATH, get_user_by_email
from auth.security import hash_password
from contracts.schemas import (
    OrgOut,
    OrgRegistration,
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