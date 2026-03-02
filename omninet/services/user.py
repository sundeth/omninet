"""
User service for managing user accounts.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.models.user import User, UserType
from omninet.services.security import hash_password


class UserService:
    """Service for user-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        query = (
            select(User)
            .options(selectinload(User.user_type))
            .where(User.id == user_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        query = (
            select(User)
            .options(selectinload(User.user_type))
            .where(func.lower(User.email) == email.lower())
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_nickname(self, nickname: str) -> Optional[User]:
        """Get user by nickname."""
        query = (
            select(User)
            .options(selectinload(User.user_type))
            .where(func.lower(User.nickname) == nickname.lower())
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_user_type(self, name: str, description: str = "") -> UserType:
        """Get or create a user type."""
        query = select(UserType).where(func.lower(UserType.name) == name.lower())
        result = await self.db.execute(query)
        user_type = result.scalar_one_or_none()

        if not user_type:
            user_type = UserType(name=name, description=description)
            self.db.add(user_type)
            await self.db.flush()

        return user_type

    async def create_user(
        self,
        nickname: str,
        email: str,
        password: str,
        type_name: str = "Standard",
        is_verified: bool = False,
        is_active: bool = True,
    ) -> User:
        """Create a new user."""
        # Get or create user type
        user_type = await self.get_or_create_user_type(
            type_name, f"{type_name} user account"
        )

        user = User(
            nickname=nickname,
            email=email.lower(),
            password_hash=hash_password(password),
            type_id=user_type.id,
            is_verified=is_verified,
            is_active=is_active,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        # Load the user type relationship
        query = (
            select(User)
            .options(selectinload(User.user_type))
            .where(User.id == user.id)
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def update_user(
        self,
        user: User,
        **kwargs,
    ) -> User:
        """Update user attributes."""
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def verify_user(self, user: User) -> User:
        """Mark a user as verified."""
        user.is_verified = True
        user.is_active = True
        await self.db.flush()
        return user

    async def update_coins(self, user: User, amount: int) -> User:
        """Update user's coin balance."""
        user.coins += amount
        if user.coins < 0:
            user.coins = 0
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def set_password(self, user: User, new_password: str) -> User:
        """Set a new password for the user."""
        user.password_hash = hash_password(new_password)
        await self.db.flush()
        return user

    async def email_exists(self, email: str) -> bool:
        """Check if an email is already registered."""
        query = select(func.count(User.id)).where(
            func.lower(User.email) == email.lower()
        )
        result = await self.db.execute(query)
        return result.scalar_one() > 0

    async def nickname_exists(self, nickname: str) -> bool:
        """Check if a nickname is already taken."""
        query = select(func.count(User.id)).where(
            func.lower(User.nickname) == nickname.lower()
        )
        result = await self.db.execute(query)
        return result.scalar_one() > 0

    async def get_users_by_nicknames(self, nicknames: list[str]) -> list[User]:
        """Get multiple users by their nicknames."""
        lower_nicknames = [n.lower() for n in nicknames]
        query = (
            select(User)
            .options(selectinload(User.user_type))
            .where(func.lower(User.nickname).in_(lower_nicknames))
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
