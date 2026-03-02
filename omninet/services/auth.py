"""
Authentication service.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omninet.models.user import User
from omninet.models.logs import ActivityType
from omninet.services.user import UserService
from omninet.services.device import DeviceService
from omninet.services.logging import LoggingService
from omninet.services.email import email_service
from omninet.services.cache import verification_cache
from omninet.services.security import (
    verify_password,
    generate_verification_code,
)
from omninet.config import settings


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)
        self.device_service = DeviceService(db)
        self.logging_service = LoggingService(db)

    async def register_user(
        self,
        nickname: str,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[User]]:
        """
        Register a new user and send verification email.
        Returns (success, message, user).
        """
        # Check if email already exists
        if await self.user_service.email_exists(email):
            return False, "Email is already registered", None

        # Check if nickname is taken
        if await self.user_service.nickname_exists(nickname):
            return False, "Nickname is already taken", None

        # Create user (unverified)
        user = await self.user_service.create_user(
            nickname=nickname,
            email=email,
            password=password,
            is_verified=False,
            is_active=False,
        )

        # Generate and store verification code
        code = generate_verification_code()
        await verification_cache.set_verification_code(
            email=email,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
            metadata={"user_id": str(user.id), "action": "register"},
        )

        # Send verification email
        await email_service.send_verification_email(
            to_email=email,
            nickname=nickname,
            code=code,
        )

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_REGISTERED,
            user_id=user.id,
            description=f"User {nickname} registered",
            ip_address=ip_address,
        )

        return True, "Verification code sent to your email", user

    async def verify_registration(
        self,
        email: str,
        code: str,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[str], Optional[uuid.UUID]]:
        """
        Verify user registration with code.
        Returns (success, message, secret_key, device_id).
        """
        # Verify code
        valid, metadata = await verification_cache.verify_and_consume(email, code)
        if not valid:
            return False, "Invalid or expired verification code", None

        # Get user
        user = await self.user_service.get_by_email(email)
        if not user:
            return False, "User not found", None

        # Mark as verified
        user = await self.user_service.verify_user(user)

        # Create device for auto-login
        device = await self.device_service.create_device(
            user_id=user.id,
            device_type="application",
            device_name="Initial registration device",
        )

        # Send welcome email
        await email_service.send_welcome_email(
            to_email=email,
            nickname=user.nickname,
        )

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_VERIFIED,
            user_id=user.id,
            description=f"User {user.nickname} verified their account",
            ip_address=ip_address,
        )

        return True, "Account verified successfully", device.secret_key, device.id

    async def login(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[User]]:
        """
        Authenticate user and send verification code.
        Returns (success, message, user).
        """
        # Get user
        user = await self.user_service.get_by_email(email)
        if not user:
            return False, "Invalid email or password", None

        # Verify password
        if not verify_password(password, user.password_hash):
            return False, "Invalid email or password", None

        # Check if user is active
        if not user.is_active:
            return False, "Account is not active", None

        # Generate and store verification code
        code = generate_verification_code()
        await verification_cache.set_verification_code(
            email=email,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
            metadata={"user_id": str(user.id), "action": "login"},
        )

        # Send verification email
        await email_service.send_verification_email(
            to_email=email,
            nickname=user.nickname,
            code=code,
        )

        return True, "Verification code sent to your email", user

    async def verify_login(
        self,
        email: str,
        code: str,
        clear_devices: bool = False,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[str], Optional[uuid.UUID]]:
        """
        Verify login with code.
        Returns (success, message, secret_key, device_id).
        """
        # Verify code
        valid, metadata = await verification_cache.verify_and_consume(email, code)
        if not valid:
            return False, "Invalid or expired verification code", None

        # Get user
        user = await self.user_service.get_by_email(email)
        if not user:
            return False, "User not found", None

        # Clear devices if requested
        if clear_devices:
            count = await self.device_service.delete_all_user_devices(user.id)
            await self.logging_service.log_activity(
                activity_type=ActivityType.USER_DEVICE_REMOVED,
                user_id=user.id,
                description=f"Cleared {count} devices on login",
                ip_address=ip_address,
            )

        # Create new device
        device = await self.device_service.create_device(
            user_id=user.id,
            device_type="application",
        )

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_LOGIN,
            user_id=user.id,
            description=f"User {user.nickname} logged in",
            ip_address=ip_address,
        )

        return True, "Login successful", device.secret_key, device.id

    async def validate_device(
        self,
        secret_key: str,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Validate a device secret key and return the user."""
        return await self.device_service.validate_secret_key(secret_key)

    async def generate_game_pairing_code(
        self,
        user: User,
    ) -> str:
        """Generate a pairing code for linking a game device."""
        code = await self.device_service.generate_pairing_code(user.id)
        return code

    async def validate_game_pairing(
        self,
        code: str,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str, Optional[str], Optional[uuid.UUID]]:
        """
        Validate a game pairing code and create a device.
        Returns (success, message, secret_key, device_id).
        """
        # Validate pairing code
        user_id = await self.device_service.validate_pairing_code(code)
        if not user_id:
            return False, "Invalid or expired pairing code", None

        # Create game device
        device = await self.device_service.create_device(
            user_id=user_id,
            device_type="game",
            device_name="Game device",
        )

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_DEVICE_ADDED,
            user_id=user_id,
            description="Game device linked via pairing code",
            ip_address=ip_address,
        )

        return True, "Device linked successfully", device.secret_key, device.id

    async def resend_verification_code(
        self,
        email: str,
    ) -> tuple[bool, str]:
        """Resend verification code to email."""
        user = await self.user_service.get_by_email(email)
        if not user:
            return False, "Email not found"

        # Generate new code
        code = generate_verification_code()
        await verification_cache.set_verification_code(
            email=email,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
            metadata={"user_id": str(user.id), "action": "resend"},
        )

        # Send email
        await email_service.send_verification_email(
            to_email=email,
            nickname=user.nickname,
            code=code,
        )

        return True, "Verification code resent"

    async def request_password_reset(
        self,
        email: str,
    ) -> tuple[bool, str]:
        """Request a password reset."""
        user = await self.user_service.get_by_email(email)
        if not user:
            # Don't reveal if email exists
            return True, "If the email exists, a reset code will be sent"

        # Generate code
        code = generate_verification_code()
        await verification_cache.set_verification_code(
            email=email,
            code=code,
            expiry_minutes=settings.verification_code_expiry_minutes,
            metadata={"user_id": str(user.id), "action": "password_reset"},
        )

        # Send email
        await email_service.send_password_reset_email(
            to_email=email,
            nickname=user.nickname,
            code=code,
        )

        return True, "If the email exists, a reset code will be sent"

    async def reset_password(
        self,
        email: str,
        code: str,
        new_password: str,
        ip_address: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Reset password with verification code."""
        # Verify code
        valid, metadata = await verification_cache.verify_and_consume(email, code)
        if not valid:
            return False, "Invalid or expired verification code"

        # Get user
        user = await self.user_service.get_by_email(email)
        if not user:
            return False, "User not found"

        # Update password
        await self.user_service.set_password(user, new_password)

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_PASSWORD_RESET,
            user_id=user.id,
            description=f"Password reset for {user.nickname}",
            ip_address=ip_address,
        )

        return True, "Password reset successfully"
