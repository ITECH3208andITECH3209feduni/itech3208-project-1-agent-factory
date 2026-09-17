# auth/security.py
# ──────────────────────────────────────────────────────────────
# Password hashing (PROJ-406 org registration)
#
# The original PROJ-339 version of this file also included JWT
# access/refresh token creation for a login flow that isn't wired
# into the app yet (see auth/org_routes.py's header comment and the
# PROJ-409 PR description for why) — trimmed to just password
# hashing, which org registration genuinely needs, rather than carry
# an unused python-jose dependency and a SECRET_KEY the app doesn't
# configure for functionality nothing calls.
# ──────────────────────────────────────────────────────────────

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
