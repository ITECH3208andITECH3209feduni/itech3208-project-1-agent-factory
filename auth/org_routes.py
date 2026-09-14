# auth/org_routes.py
# ──────────────────────────────────────────────────────────────
# Organisation registration + profile (PROJ-406, PROJ-409)
#
# Registration creates an organisation and its first user in a
# single transaction. If either half fails, neither is written —
# an orphaned org with no owner would be unreachable, and a user
# with no org_id would break the scoping rule in PROJ-410.
# ──────────────────────────────────────────────────────────────

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from auth import tenancy
from auth.db import DB_PATH, get_user_by_email
from auth.routes import current_user
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


# ── Organisation profile (PROJ-409) ────────────────────────────
@router.get("/me", response_model=OrgOut)
def get_my_org(user: sqlite3.Row = Depends(current_user)):
    """Return the caller's own organisation. No org_id is accepted
    from the client — it comes from the token, so a user can't read
    another org by changing a parameter."""
    org_id = user["org_id"]
    if org_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is not assigned to an organisation")
    row = tenancy.get_org(org_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found")
    return _row_to_org(row)


@router.patch("/me", response_model=OrgOut)
def update_my_org(body: OrgUpdate, user: sqlite3.Row = Depends(current_user)):
    """Update the caller's organisation. Owners only."""
    org_id = user["org_id"]
    if org_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is not assigned to an organisation")
    if user["role"] != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the organisation owner can change the profile")

    tenancy.update_org(
        org_id,
        name=body.name,
        contact_email=str(body.contact_email) if body.contact_email else None,
        timezone=body.timezone,
    )
    return _row_to_org(tenancy.get_org(org_id))