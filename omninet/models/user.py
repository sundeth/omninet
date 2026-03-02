"""
User-related database models.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omninet.database import Base

if TYPE_CHECKING:
    from omninet.models.battle import GameTeam
    from omninet.models.module import GameModule, ModuleContributor
    from omninet.models.shop import UserPurchase


class UserType(Base):
    """User type for permission handling (Admin, Standard)."""

    __tablename__ = "user_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="user_type")

    def __repr__(self) -> str:
        return f"<UserType(name={self.name})>"


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nickname: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_types.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user_type: Mapped["UserType"] = relationship("UserType", back_populates="users")
    devices: Mapped[list["UserDevice"]] = relationship(
        "UserDevice", back_populates="owner", cascade="all, delete-orphan"
    )
    modules: Mapped[list["GameModule"]] = relationship(
        "GameModule", back_populates="owner", foreign_keys="GameModule.owner_id"
    )
    contributions: Mapped[list["ModuleContributor"]] = relationship(
        "ModuleContributor", back_populates="user", foreign_keys="ModuleContributor.user_id"
    )
    teams: Mapped[list["GameTeam"]] = relationship("GameTeam", back_populates="owner")
    purchases: Mapped[list["UserPurchase"]] = relationship(
        "UserPurchase", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(nickname={self.nickname}, email={self.email})"

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.user_type.name.lower() == "admin" if self.user_type else False


class UserDevice(Base):
    """Device linked to user for auto-login functionality."""

    __tablename__ = "user_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    secret_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_type: Mapped[str] = mapped_column(
        String(50), default="application"
    )  # application, game
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="devices")

    def __repr__(self) -> str:
        return f"<UserDevice(owner_id={self.owner_id}, device_type={self.device_type})>"
