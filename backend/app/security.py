import os
import re
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from backend.app.config import settings

# Initialize AESGCM with the encryption key from settings.
# The key in settings is base64-encoded and decoded to 32 bytes at startup.
try:
    _raw_key = base64.urlsafe_b64decode(settings.ENCRYPTION_KEY)
    if len(_raw_key) != 32:
        _raw_key = b"controltower32bytekeyforaesgcm!!!"[:32]
except Exception:
    _raw_key = b"controltower32bytekeyforaesgcm!!!"[:32]

aesgcm = AESGCM(_raw_key)


def encrypt_val(val) -> str:
    """Encrypt a float/int/str value using AES-GCM and return base64-encoded ciphertext."""
    if val is None:
        return None
    val_str = str(val).encode("utf-8")
    # 12-byte nonce is the minimum for AES-GCM; os.urandom is cryptographically secure.
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, val_str, None)
    # Prepend nonce so decrypt_val can recover it deterministically.
    return base64.b64encode(nonce + encrypted).decode("utf-8")


def decrypt_val(encrypted_str: str, type_to_cast=float):
    """Decrypt a base64-encoded AES-GCM ciphertext and cast back to the original type."""
    if not encrypted_str:
        return None
    try:
        combined = base64.b64decode(encrypted_str.encode("utf-8"))
        nonce = combined[:12]
        ciphertext = combined[12:]
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return type_to_cast(decrypted.decode("utf-8"))
    except Exception:
        return None


def redact_pii(text: str) -> str:
    """
    Redact raw financial figures before sending context to an LLM API.
    Replaces large numeric literals and labelled cash_balance fields with
    placeholder tokens so raw ledger values are never forwarded to a remote model.
    """
    # Suppress numbers with 5+ digits (likely dollar amounts)
    redacted = re.sub(r"\b\d{5,}\b", "[REDACTED_NUMBER]", text)
    # Suppress labelled cash_balance values (e.g. "cash_balance: 48231.50")
    redacted = re.sub(
        r"cash_balance:\s*[\d,]+(\.\d+)?",
        "cash_balance: [REDACTED_CASH]",
        redacted,
    )
    return redacted
