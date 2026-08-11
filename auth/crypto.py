# auth/crypto.py
# ──────────────────────────────────────────────────────────────
# Symmetric encryption for per-user API keys (PROJ-344..348)
# Keys are encrypted at rest with Fernet (AES-128-CBC + HMAC).
# ──────────────────────────────────────────────────────────────

import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

_KEK = os.getenv("KEY_ENCRYPTION_KEY")

if not _KEK:
    raise RuntimeError(
        "KEY_ENCRYPTION_KEY is not set. Generate one with:\n"
        "  py -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

_fernet = Fernet(_KEK.encode())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str | None:
    """Return the plaintext, or None if the value can't be decrypted."""
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask(api_key: str) -> str:
    """Show only the last 4 characters — never return a full key to a client."""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:7]}...{api_key[-4:]}"