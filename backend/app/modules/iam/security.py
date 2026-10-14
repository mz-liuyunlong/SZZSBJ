from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

import bcrypt

ACCESS_TOKEN_TTL: Final = timedelta(days=7)


def now_utc() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    New-system passwords use bcrypt too, so existing `$2a$` legacy hashes remain
    verifiable without introducing a second password algorithm.
    """

    if not password or password != password.strip() or len(password) < 8:
        raise ValueError("password must be at least 8 characters and trimmed")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify bcrypt hashes only; legacy one-character placeholders fail closed."""

    if not password or not password_hash:
        return False
    if not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def issue_access_token() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(48)
    return token, token_hash(token), now_utc() + ACCESS_TOKEN_TTL


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
