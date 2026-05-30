"""
Security utilities for password hashing and token generation.
"""
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from omninet.config import settings

# Password hashing context with bcrypt configured to auto-truncate
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__default_rounds=12,
    bcrypt__ident="2b"
)


def _truncate_password(password: str) -> str:
    """Truncate password to 72 bytes for bcrypt compatibility."""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) <= 72:
        return password
    # Truncate to 72 bytes and decode, removing any incomplete characters
    truncated = password_bytes[:72]
    # Decode and re-encode to ensure valid UTF-8
    try:
        return truncated.decode('utf-8')
    except UnicodeDecodeError:
        # If we cut in the middle of a character, try shorter lengths
        for length in range(71, 68, -1):
            try:
                return password_bytes[:length].decode('utf-8')
            except UnicodeDecodeError:
                continue
        # Fallback: just use first 50 chars
        return password[:50]


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password = _truncate_password(password)
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    plain_password = _truncate_password(plain_password)
    return pwd_context.verify(plain_password, hashed_password)


def generate_secret_key(length: int = 64) -> str:
    """Generate a cryptographically secure secret key."""
    return secrets.token_urlsafe(length)


def generate_verification_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_pairing_code(length: int = 4) -> str:
    """Generate an alphanumeric pairing code (uppercase letters and numbers)."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None
