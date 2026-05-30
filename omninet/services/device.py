"""
Device service for managing user devices.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.config import settings
from omninet.models.user import User, UserDevice
from omninet.services.cache import verification_cache
from omninet.services.security import generate_pairing_code, generate_secret_key


class DeviceService:
    """Service for device-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, device_id: UUID) -> UserDevice | None:
        """Get device by ID."""
        query = (
            select(UserDevice)
            .options(selectinload(UserDevice.owner))
            .where(UserDevice.id == device_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_secret_key(self, secret_key: str) -> UserDevice | None:
        """Get device by secret key."""
        query = (
            select(UserDevice)
            .options(selectinload(UserDevice.owner).selectinload(User.user_type))
            .where(UserDevice.secret_key == secret_key)
            .where(UserDevice.is_active.is_(True))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_devices(self, user_id: UUID) -> list[UserDevice]:
        """Get all devices for a user."""
        query = (
            select(UserDevice)
            .where(UserDevice.owner_id == user_id)
            .order_by(UserDevice.created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_device(
        self,
        user_id: UUID,
        device_type: str = "application",
        device_name: str | None = None,
    ) -> UserDevice:
        """Create a new device for a user."""
        device = UserDevice(
            owner_id=user_id,
            secret_key=generate_secret_key(),
            device_type=device_type,
            device_name=device_name,
            is_active=True,
        )
        self.db.add(device)
        await self.db.flush()
        await self.db.refresh(device)
        return device

    async def update_last_used(self, device: UserDevice) -> UserDevice:
        """Update the last used timestamp of a device."""
        device.last_used_at = datetime.now(UTC)
        await self.db.flush()
        return device

    async def deactivate_device(self, device: UserDevice) -> UserDevice:
        """Deactivate a device."""
        device.is_active = False
        await self.db.flush()
        return device

    async def delete_device(self, device_id: UUID) -> bool:
        """Delete a device."""
        query = delete(UserDevice).where(UserDevice.id == device_id)
        result = await self.db.execute(query)
        return result.rowcount > 0

    async def delete_all_user_devices(self, user_id: UUID) -> int:
        """Delete all devices for a user."""
        query = delete(UserDevice).where(UserDevice.owner_id == user_id)
        result = await self.db.execute(query)
        return result.rowcount

    async def generate_pairing_code(self, user_id: UUID) -> str:
        """Generate a pairing code for device linking."""
        # Generate unique code
        for _ in range(10):  # Try up to 10 times to get unique code
            code = generate_pairing_code()
            existing = await verification_cache.get_pairing_user(code)
            if existing is None:
                break
        else:
            raise ValueError("Could not generate unique pairing code")

        # Store in cache
        await verification_cache.set_pairing_code(
            code=code,
            user_id=str(user_id),
            expiry_minutes=settings.pairing_code_expiry_minutes,
        )
        return code

    async def validate_pairing_code(self, code: str) -> UUID | None:
        """Validate a pairing code and return the user ID if valid."""
        user_id_str = await verification_cache.consume_pairing_code(code)
        if user_id_str:
            return UUID(user_id_str)
        return None

    async def validate_secret_key(self, secret_key: str) -> User | None:
        """Validate a secret key and return the user if valid."""
        device = await self.get_by_secret_key(secret_key)
        if device and device.is_active:
            # Update last used time
            await self.update_last_used(device)
            return device.owner
        return None
