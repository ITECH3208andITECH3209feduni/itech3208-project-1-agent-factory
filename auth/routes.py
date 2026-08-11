# auth/routes.py
# ──────────────────────────────────────────────────────────────
# Registration / login / refresh / me endpoints (PROJ-339..343)
# ──────────────────────────────────────────────────────────────

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from auth import db
from auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


# ── Schemas ────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool


# ── Dependency ─────────────────────────────────────────────────
def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> sqlite3.Row:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_token(creds.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get_user_by_id(int(payload["sub"]))
    if user is None or not user["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


# ── Endpoints ──────────────────────────────────────────────────
@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest):
    if db.get_user_by_email(body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user_id = db.create_user(body.email, hash_password(body.password))
    return UserOut(id=user_id, email=body.email.lower(), is_active=True)


@router.post("/login", response_model=TokenPair)
def login(body: LoginRequest):
    user = db.get_user_by_email(body.email)
    # Same message either way — don't reveal whether the email exists.
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")

    access = create_access_token(user["id"])
    refresh, jti, expires_at = create_refresh_token(user["id"])
    db.store_refresh_token(jti, user["id"], expires_at.isoformat())
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    jti = payload["jti"]
    if not db.is_refresh_token_valid(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked")

    user = db.get_user_by_id(int(payload["sub"]))
    if user is None or not user["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    # Rotate: revoke the old refresh token, issue a new pair.
    db.revoke_refresh_token(jti)
    access = create_access_token(user["id"])
    new_refresh, new_jti, expires_at = create_refresh_token(user["id"])
    db.store_refresh_token(new_jti, user["id"], expires_at.isoformat())
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest):
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if payload is not None:
        db.revoke_refresh_token(payload["jti"])
    return None


@router.get("/me", response_model=UserOut)
def me(user: sqlite3.Row = Depends(current_user)):
    return UserOut(id=user["id"], email=user["email"], is_active=bool(user["is_active"]))