"""Symmetric encryption helper — used for at-rest sensitive values like LLM API keys.

Derives a Fernet key from `COBWEB_SECRET_KEY` so we don't introduce a second secret
to manage in dev. For prod, swap to a KMS-backed key.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from cobweb.core.settings import get_settings


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode()
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("invalid ciphertext") from exc
