"""
Shop related database models.
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
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omninet.database import Base

if TYPE_CHECKING:
    from omninet.models.user import User
    from omninet.models.module import GameModule


class CosmeticType(enum.Enum):
    """Type of cosmetic item."""
    BACKGROUND = "background"


class ShopCosmetic(Base):
    """Cosmetic items available in the shop (backgrounds, etc.)."""

    __tablename__ = "shop_cosmetics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cosmetic_type: Mapped[CosmeticType] = mapped_column(
        Enum(CosmeticType), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sprite_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ShopCosmetic(name={self.name}, type={self.cosmetic_type})>"


class ShopGameplay(Base):
    """Gameplay items available in the shop (minigames, battle modes, etc.)."""

    __tablename__ = "shop_gameplay"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ShopGameplay(name={self.name})>"


class ShopItem(Base):
    """Consumable items available in the shop (clocks, boosts, etc.)."""

    __tablename__ = "shop_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sprite_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ShopItem(name={self.name})>"


class ShopSpecial(Base):
    """Special limited-time items in the shop (future use)."""

    __tablename__ = "shop_specials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    json_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ShopSpecial(name={self.name})>"


class PurchaseType(enum.Enum):
    """Type of purchase."""
    MODULE = "module"
    COSMETIC = "cosmetic"
    GAMEPLAY = "gameplay"
    ITEM = "item"
    SPECIAL = "special"


class UserPurchase(Base):
    """Track user purchases."""

    __tablename__ = "user_purchases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    purchase_type: Mapped[PurchaseType] = mapped_column(
        Enum(PurchaseType), nullable=False, index=True
    )
    price_paid: Mapped[int] = mapped_column(Integer, default=0)
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="purchases")

    def __repr__(self) -> str:
        return f"<UserPurchase(user_id={self.user_id}, item_id={self.item_id}, type={self.purchase_type})>"
