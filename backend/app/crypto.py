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
    """Encrypt a plaintext string. Returns None if input is None/empty."""
    if not plaintext:
        return plaintext
    try:
        return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.warning("Encryption failed: %s", e)
        return plaintext


def decrypt_value(ciphertext: str | None) -> str | None:
    """Decrypt a ciphertext string. Falls back to plaintext for legacy unencrypted values."""
    if not ciphertext:
        return ciphertext
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Legacy plaintext value or corrupted data — return as-is
        return ciphertext
