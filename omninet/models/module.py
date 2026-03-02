"""
Game module related database models.
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omninet.database import Base

if TYPE_CHECKING:
    from omninet.models.user import User


class ModuleStatus(enum.Enum):
    """Status of a game module."""

    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    BANNED = "banned"


class ModuleCategory(Base):
    """Category for game modules (Classics, Modern, Conversions, Custom)."""

    __tablename__ = "module_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    modules: Mapped[list["GameModule"]] = relationship(
        "GameModule", back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<ModuleCategory(name={self.name})>"


class GameModule(Base):
    """User-generated game module containing sprites, JSON files, and assets."""

    __tablename__ = "game_modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("module_categories.id"), nullable=True
    )
    status: Mapped[ModuleStatus] = mapped_column(
        Enum(ModuleStatus), default=ModuleStatus.DRAFT
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[int] = mapped_column(Integer, default=0)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship(
        "User", back_populates="modules", foreign_keys=[owner_id]
    )
    category: Mapped[Optional["ModuleCategory"]] = relationship(
        "ModuleCategory", back_populates="modules"
    )
    contributors: Mapped[list["ModuleContributor"]] = relationship(
        "ModuleContributor", back_populates="module", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GameModule(name={self.name}, version={self.version})>"


class ModuleContributor(Base):
    """Users who can upload changes to a module (allowed by owner)."""

    __tablename__ = "module_contributors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_modules.id", ondelete="CASCADE"), nullable=False
    )
    can_publish: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Unique constraint on user_id and module_id
    __table_args__ = (
        UniqueConstraint("user_id", "module_id", name="uq_contributor_module"),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="contributions", foreign_keys=[user_id]
    )
    module: Mapped["GameModule"] = relationship(
        "GameModule", back_populates="contributors"
    )

    def __repr__(self) -> str:
        return f"<ModuleContributor(user_id={self.user_id}, module_id={self.module_id})>"
