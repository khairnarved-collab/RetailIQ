"""
Password hashing (bcrypt) and JWT access tokens.

* Passwords are hashed with bcrypt + a random salt; only the hash is stored.
* Access tokens are short-lived signed JWTs (HS256) carrying the user id and role.
* Password-reset tokens are random URL-safe strings; only their SHA-256 hash
  is stored, so a database leak does not reveal usable reset links.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

UTC = timezone.utc  # datetime.UTC needs Python 3.11+; this works on 3.10 too


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; we validate length at the schema level.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, expires_minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid or expired."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_reset_token() -> tuple[str, str]:
    """Return (token_for_user, sha256_hash_to_store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
