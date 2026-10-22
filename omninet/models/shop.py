"""
Shop related database models.
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omninet.database import Base

if TYPE_CHECKING:
    from omninet.models.user import User


class CosmeticType(enum.Enum):
    """Type of cosmetic item."""
    BACKGROUND = "background"


#: What a shop entry is paid with. Coins are the game's currency; contribution
#: points are earned on the Digimon Database and pay for some Specials.
CURRENCY_COINS = "coins"
CURRENCY_CONTRIBUTION_POINTS = "contribution_points"
CURRENCIES = (CURRENCY_COINS, CURRENCY_CONTRIBUTION_POINTS)

#: What a Special unlocks. Only backgrounds so far; the game lists a type it
#: does not know as unavailable.
SPECIAL_TYPE_BACKGROUND = "background"


class ShopCosmetic(Base):
    """Cosmetic items available in the shop (backgrounds, etc.)."""

    __tablename__ = "shop_cosmetics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cosmetic_type: Mapped[CosmeticType] = mapped_column(
        Enum(CosmeticType, values_callable=lambda obj: [e.value for e in obj], create_type=False),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sprite_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Background-only metadata mirroring the game's Background class:
    # day_night = True means the asset has separate _day / _night variants,
    # high_res = True means a *_high.png version is available.
    day_night: Mapped[bool] = mapped_column(Boolean, default=True)
    high_res: Mapped[bool] = mapped_column(Boolean, default=False)
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    json_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sprite_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    """Specials: unlocks bought once, optionally for a limited time and in
    either currency (storage/specials/specials.json, services/shop_sync.py)."""

    __tablename__ = "shop_specials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    # CURRENCY_COINS or CURRENCY_CONTRIBUTION_POINTS: which balance pays it.
    currency: Mapped[str] = mapped_column(
        String(32), default=CURRENCY_COINS, server_default=CURRENCY_COINS, nullable=False
    )
    # What it unlocks (SPECIAL_TYPE_BACKGROUND); details in json_data.
    special_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # A background's base file name in <storage>/backgrounds ("bg_<name>").
    sprite_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Listing order (then name).
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    json_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        Enum(PurchaseType, values_callable=lambda obj: [e.value for e in obj], create_type=False),
        nullable=False,
        index=True,
    )
    price_paid: Mapped[int] = mapped_column(Integer, default=0)
    # The balance price_paid came out of (CURRENCIES).
    currency: Mapped[str] = mapped_column(
        String(32), default=CURRENCY_COINS, server_default=CURRENCY_COINS, nullable=False
    )
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="purchases")

    def __repr__(self) -> str:
        return f"<UserPurchase(user_id={self.user_id}, item_id={self.item_id}, type={self.purchase_type})>"
