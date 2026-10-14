# auth/org_routes.py
# Organisation registration and profile routes.
#
# Authentication compatibility bridge:
# - Session-cookie users are stored in agent.auth.
# - Email-registered organisation owners are stored in auth.db.
# - Both account types can access their own organisation profile.
#
# The authentication stores are not yet consolidated. This module
# resolves each authenticated identity to its organisation without
# allowing a client to choose another organisation's ID.

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from agent.auth import get_user_org_id, set_user_org_id
from app.web_ui.auth_routes import get_current_username
from auth import tenancy
from auth import db as auth_db

# Backward-compatible alias for existing tests
DB_PATH = auth_db.DB_PATH
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


def _get_authenticated_org_id(username: str) -> int | None:
    """
    Resolve an organisation for either supported login type.

    Session-cookie accounts use agent.auth's organisation mapping.
    Email-registered organisation owners use the org_id stored with
    their account in auth.db.
    """
    # First check the existing session-cookie user store.
    org_id = get_user_org_id(username)
    if org_id is not None:
        return org_id

    # Email-based login uses the email address as the session username.
    email_user = auth_db.get_user_by_email(username)
    if email_user is not None:
        org_id = email_user["org_id"]
        return int(org_id) if org_id is not None else None

    return None


def _require_org(username: str) -> int:
    org_id = _get_authenticated_org_id(username)
    if org_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You're not part of an organisation yet â€” create one with POST /orgs/claim.",
        )
    return org_id


@router.post(
    "/register",
    response_model=RegistrationOut,
    status_code=status.HTTP_201_CREATED,
)
def register_org(body: OrgRegistration):
    """
    Create an organisation and its owner user atomically.

    If either database insert fails, neither insert is committed.
    """
    if auth_db.get_user_by_email(str(body.email)) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Email already registered",
        )

    conn = sqlite3.connect(auth_db.DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.execute(
            """
            INSERT INTO organisations (name, contact_email, timezone)
            VALUES (?, ?, ?)
            """,
            (body.org_name.strip(), str(body.email), body.timezone),
        )
        org_id = cur.lastrowid

        cur = conn.execute(
            """
            INSERT INTO users (email, password_hash, org_id, role)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(body.email).lower().strip(),
                hash_password(body.password),
                org_id,
                "owner",
            ),
        )
        user_id = cur.lastrowid

        org_row = conn.execute(
            "SELECT * FROM organisations WHERE id = ?",
            (org_id,),
        ).fetchone()

        conn.commit()

    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Registration failed: {exc}",
        ) from exc

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return RegistrationOut(
        org=_row_to_org(org_row),
        user_id=user_id,
        role="owner",
    )


@router.post(
    "/claim",
    response_model=OrgOut,
    status_code=status.HTTP_201_CREATED,
)
def claim_org(
    body: OrgRegistration,
    username: str = Depends(get_current_username),
):
    """
    Create an organisation for a logged-in session-cookie user.

    Email-registered owners already receive an organisation during
    registration. Do not create a second organisation for those users.
    """
    email_user = auth_db.get_user_by_email(username)
    if email_user is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Email-registered accounts use the organisation created during registration.",
        )

    if get_user_org_id(username) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You already belong to an organisation.",
        )

    org_id = tenancy.create_org(
        body.org_name,
        str(body.email),
        body.timezone,
    )
    set_user_org_id(username, org_id)

    row = tenancy.get_org(org_id)
    return _row_to_org(row)


@router.get("/me", response_model=OrgOut)
def get_my_org(username: str = Depends(get_current_username)):
    """Return the authenticated user's own organisation."""
    org_id = _require_org(username)
    row = tenancy.get_org(org_id)

    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Organisation not found",
        )

    return _row_to_org(row)


@router.patch("/me", response_model=OrgOut)
def update_my_org(
    body: OrgUpdate,
    username: str = Depends(get_current_username),
):
    """Update only the organisation belonging to the authenticated user."""
    org_id = _require_org(username)

    tenancy.update_org(
        org_id,
        name=body.name,
        contact_email=(
            str(body.contact_email) if body.contact_email else None
        ),
        timezone=body.timezone,
    )

    row = tenancy.get_org(org_id)
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Organisation not found",
        )

    return _row_to_org(row)
