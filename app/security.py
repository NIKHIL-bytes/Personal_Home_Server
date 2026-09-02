"""
Authentication primitives: password hashing (Argon2id) and session tokens.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.config import SESSION_TIMEOUT_HOURS

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def generate_session_token() -> str:
    """A high-entropy token given to the browser as a cookie. Never stored raw."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """SHA-256 of the token, stored server-side instead of the raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TIMEOUT_HOURS)
    return expires.strftime("%Y-%m-%d %H:%M:%S")


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
