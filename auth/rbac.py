"""Shared organisation-role checks for authenticated requests."""

from fastapi import HTTPException, Request

from agent import auth as session_auth
from app.web_ui.auth_routes import get_current_username
from auth import db as email_db


def _session_role_conn():
    conn = session_auth._get_conn()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'staff'"
        )
        conn.commit()
    return conn


def set_session_role(username: str, role: str) -> None:
    if role not in {"admin", "staff"}:
        raise ValueError("Role must be 'admin' or 'staff'.")

    conn = _session_role_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET role = ? WHERE username = ?",
            (role, username),
        )
        conn.commit()
        if cur.rowcount != 1:
            raise ValueError("Session user was not found.")
    finally:
        conn.close()


def _get_session_role(username: str) -> str:
    conn = _session_role_conn()
    try:
        row = conn.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        ).fetchone()
        return row["role"] if row else "staff"
    finally:
        conn.close()


def get_current_identity(request: Request) -> dict:
    """Resolve a session-cookie identity or a valid organisation API key."""

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        raw_key = authorization[7:].strip()

        # Import locally to avoid a circular import with auth.api_keys.
        from auth.api_keys import authenticate_api_key

        identity = authenticate_api_key(raw_key)
        if identity is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        return identity

    username = get_current_username(request)

    email_user = (
        email_db.get_user_by_email(username)
        if "@" in username
        else None
    )

    if email_user is not None:
        keys = email_user.keys()
        org_id = email_user["org_id"] if "org_id" in keys else None
        stored_role = email_user["role"] if "role" in keys else "member"
        role = "admin" if stored_role in {"owner", "admin"} else "staff"
    else:
        org_id = session_auth.get_user_org_id(username)
        role = _get_session_role(username)

    if org_id is None:
        raise HTTPException(
            status_code=403,
            detail="Your account is not assigned to an organisation.",
        )

    if role not in {"admin", "staff"}:
        raise HTTPException(status_code=403, detail="Invalid account role.")

    return {
        "username": username,
        "org_id": int(org_id),
        "role": role,
    }


def require_org_member(request: Request) -> dict:
    return get_current_identity(request)


def require_admin(request: Request) -> dict:
    identity = get_current_identity(request)
    if identity["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Organisation admin permission required.",
        )
    return identity