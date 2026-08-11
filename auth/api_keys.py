# auth/api_keys.py
# ──────────────────────────────────────────────────────────────
# API key scoping (PROJ-344..348)
# Resolves which Anthropic API key to use for a given user:
# the user's own key if they've set one, otherwise the system key.
# ──────────────────────────────────────────────────────────────

import os

from dotenv import load_dotenv

from auth import crypto, db

load_dotenv()

SYSTEM_KEY = os.getenv("ANTHROPIC_API_KEY")


def resolve_api_key(user_id: int | None = None) -> tuple[str | None, str]:
    """
    Return (api_key, source).

    source is "user" when the caller's own key is used, "system" when
    falling back to the shared key, and "none" when neither is available.
    """
    if user_id is not None:
        enc = db.get_user_api_key_enc(user_id)
        if enc:
            plain = crypto.decrypt(enc)
            if plain:
                return plain, "user"
            # Stored value is corrupt or was encrypted with a different
            # KEY_ENCRYPTION_KEY — fall through to the system key.

    if SYSTEM_KEY:
        return SYSTEM_KEY, "system"

    return None, "none"


def has_user_key(user_id: int) -> bool:
    return db.get_user_api_key_enc(user_id) is not None