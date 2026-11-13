"""Password hashing, API-key handling and JWT sessions."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


# Dummy hash so login timing doesn't reveal whether a username exists.
DUMMY_HASH = _ph.hash("infrawatch-dummy")


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    # API keys / enrollment tokens are 256-bit random, so a fast hash is appropriate
    # (no brute-force risk) and lets us look them up cheaply.
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def make_agent_key(host_id: int, secret: str) -> str:
    return f"iw_{host_id}_{secret}"


def parse_agent_key(key: str) -> tuple[int, str] | None:
    parts = key.split("_", 2)
    if len(parts) != 3 or parts[0] != "iw" or not parts[1].isdigit() or not parts[2]:
        return None
    return int(parts[1]), parts[2]


def create_token(secret_key: str, username: str, role: str, ttl_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": username, "role": role, "iat": now, "exp": now + timedelta(minutes=ttl_minutes)},
        secret_key,
        algorithm="HS256",
    )


def decode_token(secret_key: str, token: str) -> dict | None:
    try:
        return jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
