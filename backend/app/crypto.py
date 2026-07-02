"""
Symmetric encryption utility for sensitive fields (API keys, SMTP passwords).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from SECRET_KEY.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger("falltracker.crypto")

# Derive a Fernet-compatible key from SECRET_KEY (32 bytes → base64url-encoded)
_derived_key = base64.urlsafe_b64encode(
    hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
)
_fernet = Fernet(_derived_key)


def encrypt_value(plaintext: str | None) -> str | None:
    """Encrypt a plaintext string. Returns None if input is None/empty.
    Raises on encryption failure to prevent storing sensitive data in plaintext."""
    if not plaintext:
        return plaintext
    # Already encrypted values (Fernet tokens start with 'gAAAAA') should not be re-encrypted
    if plaintext.startswith("gAAAAA"):
        return plaintext
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str | None) -> str | None:
    """Decrypt a ciphertext string. Falls back to plaintext only for values that
    are clearly not Fernet tokens (legacy unencrypted data). Returns empty string
    for corrupted or wrong-key Fernet tokens to avoid leaking ciphertext."""
    if not ciphertext:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Fernet tokens always start with 'gAAAAA' (base64 of version byte 0x80).
        # If the value looks like a Fernet token but can't be decrypted, it's
        # corrupted or was encrypted with a different key — return empty, not the ciphertext.
        if ciphertext.startswith("gAAAAA"):
            logger.warning("Fernet token decryption failed (wrong key or corrupted), len=%d", len(ciphertext))
            return ""
        # Legacy plaintext value — not a Fernet token, return as-is
        return ciphertext
    except Exception as e:
        # Unexpected error — log and return empty to avoid leaking ciphertext
        logger.warning("Decryption failed for value (len=%d): %s", len(ciphertext), e)
        return ""
