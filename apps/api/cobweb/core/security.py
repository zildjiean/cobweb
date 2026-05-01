"""Password hashing, JWT, API key, MFA primitives."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from cobweb.core.settings import get_settings

_hasher = PasswordHasher()
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except VerifyMismatchError:
        return False


def issue_access_token(*, subject: str, claims: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.access_token_ttl_min)).timestamp()),
        "type": "access",
        **(claims or {}),
    }
    return jwt.encode(payload, s.secret_key, algorithm=_ALGO)


def issue_refresh_token(*, subject: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=s.refresh_token_ttl_days)).timestamp()),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, s.secret_key, algorithm=_ALGO)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=[_ALGO])
    except JWTError as e:
        raise ValueError("invalid token") from e


# ── API keys ────────────────────────────────────────────────────────
def generate_api_key() -> tuple[str, str]:
    """Return (plaintext, sha256_hash). Store only the hash."""
    import hashlib

    raw = "cwbk_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, digest


def hash_api_key(plaintext: str) -> str:
    import hashlib

    return hashlib.sha256(plaintext.encode()).hexdigest()


# ── MFA / TOTP ──────────────────────────────────────────────────────
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, *, account: str, issuer: str = "Cobweb") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
