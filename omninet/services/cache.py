"""
In-memory cache for verification codes.
For production, consider using Redis.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import asyncio


class VerificationCache:
    """Simple in-memory cache for verification and pairing codes."""

    def __init__(self):
        self._verification_codes: dict[str, tuple[str, datetime, dict]] = {}
        self._pairing_codes: dict[str, tuple[str, datetime, dict]] = {}
        self._lock = asyncio.Lock()

    async def set_verification_code(
        self,
        email: str,
        code: str,
        expiry_minutes: int = 5,
        metadata: Optional[dict] = None,
    ) -> None:
        """Store a verification code for an email."""
        async with self._lock:
            expiry = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
            self._verification_codes[email.lower()] = (code, expiry, metadata or {})

    async def get_verification_code(
        self, email: str
    ) -> Optional[tuple[str, dict]]:
        """Get a verification code if it exists and is not expired."""
        async with self._lock:
            data = self._verification_codes.get(email.lower())
            if data is None:
                return None

            code, expiry, metadata = data
            if datetime.now(timezone.utc) > expiry:
                del self._verification_codes[email.lower()]
                return None

            return code, metadata

    async def verify_and_consume(
        self, email: str, code: str
    ) -> tuple[bool, Optional[dict]]:
        """Verify a code and consume it if valid."""
        async with self._lock:
            data = self._verification_codes.get(email.lower())
            if data is None:
                return False, None

            stored_code, expiry, metadata = data
            if datetime.now(timezone.utc) > expiry:
                del self._verification_codes[email.lower()]
                return False, None

            if stored_code != code:
                return False, None

            # Consume the code
            del self._verification_codes[email.lower()]
            return True, metadata

    async def set_pairing_code(
        self,
        code: str,
        user_id: str,
        expiry_minutes: int = 5,
    ) -> None:
        """Store a pairing code for device linking."""
        async with self._lock:
            expiry = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)
            self._pairing_codes[code.upper()] = (user_id, expiry, {})

    async def get_pairing_user(self, code: str) -> Optional[str]:
        """Get the user ID associated with a pairing code."""
        async with self._lock:
            data = self._pairing_codes.get(code.upper())
            if data is None:
                return None

            user_id, expiry, _ = data
            if datetime.now(timezone.utc) > expiry:
                del self._pairing_codes[code.upper()]
                return None

            return user_id

    async def consume_pairing_code(self, code: str) -> Optional[str]:
        """Consume a pairing code and return the user ID."""
        async with self._lock:
            data = self._pairing_codes.get(code.upper())
            if data is None:
                return None

            user_id, expiry, _ = data
            if datetime.now(timezone.utc) > expiry:
                del self._pairing_codes[code.upper()]
                return None

            # Consume the code
            del self._pairing_codes[code.upper()]
            return user_id

    async def cleanup_expired(self) -> None:
        """Remove expired codes from cache."""
        now = datetime.now(timezone.utc)
        async with self._lock:
            # Clean verification codes
            expired_emails = [
                email
                for email, (_, expiry, _) in self._verification_codes.items()
                if now > expiry
            ]
            for email in expired_emails:
                del self._verification_codes[email]

            # Clean pairing codes
            expired_codes = [
                code
                for code, (_, expiry, _) in self._pairing_codes.items()
                if now > expiry
            ]
            for code in expired_codes:
                del self._pairing_codes[code]


# Singleton instance
verification_cache = VerificationCache()
