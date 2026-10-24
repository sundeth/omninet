"""
Shop-related Pydantic schemas.
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Base schemas
# ============================================================================

class ShopItemBase(BaseModel):
    """Base schema for shop items."""
    id: uuid.UUID
    name: str
    price: int
    enabled: bool = True


# ============================================================================
# Cosmetic schemas
# ============================================================================

class CosmeticListItem(BaseModel):
    """Cosmetic item for shop listing."""
    id: uuid.UUID
    name: str
    cosmetic_type: str
    price: int
    sprite_name: str | None = None
    # Background-only metadata (matches game's Background class)
    day_night: bool = True
    high_res: bool = False

    class Config:
        from_attributes = True


class CosmeticListResponse(BaseModel):
    """Response for listing cosmetics."""
    cosmetics: list[CosmeticListItem]
    total: int


class CosmeticDownloadResponse(BaseModel):
    """Response for downloading a purchased cosmetic."""
    id: uuid.UUID
    name: str
    cosmetic_type: str
    json_data: dict[str, Any] | None = None
    sprites: dict[str, str] = Field(default_factory=dict)  # name -> base64 data


# ============================================================================
# Gameplay schemas
# ============================================================================

class GameplayListItem(BaseModel):
    """Gameplay item for shop listing."""
    id: uuid.UUID
    name: str
    description: str | None = None
    price: int

    class Config:
        from_attributes = True


class GameplayListResponse(BaseModel):
    """Response for listing gameplay items."""
    gameplay: list[GameplayListItem]
    total: int


class GameplayDownloadResponse(BaseModel):
    """Response for downloading a purchased gameplay item."""
    id: uuid.UUID
    name: str
    json_data: dict[str, Any] | None = None


# ============================================================================
# Item schemas
# ============================================================================

class ItemListItem(BaseModel):
    """Item for shop listing."""
    id: uuid.UUID
    name: str
    description: str | None = None
    price: int
    sprite_name: str | None = None

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    """Response for listing items."""
    items: list[ItemListItem]
    total: int


class ItemDownloadResponse(BaseModel):
    """Response for downloading a purchased item."""
    id: uuid.UUID
    name: str
    json_data: dict[str, Any] | None = None
    sprites: dict[str, str] = Field(default_factory=dict)  # name -> base64 data


# ============================================================================
# Module schemas (shop-specific)
# ============================================================================

class ModuleShopListItem(BaseModel):
    """Module for shop listing."""
    id: uuid.UUID
    name: str
    version: str
    description: str | None = None
    category: str | None = None
    price: int
    owner_nickname: str
    is_official: bool = False

    class Config:
        from_attributes = True


class ModuleShopListResponse(BaseModel):
    """Response for listing modules in shop."""
    modules: list[ModuleShopListItem]
    total: int


class ModuleDownloadResponse(BaseModel):
    """Response for downloading a purchased module."""
    id: uuid.UUID
    name: str
    version: str
    file_data: str  # base64 encoded zip


# ============================================================================
# Special schemas
# ============================================================================

class SpecialListItem(BaseModel):
    """Special item for shop listing."""
    id: uuid.UUID
    name: str
    description: str | None = None
    price: int
    # "coins" or "contribution_points": the balance the price comes out of.
    currency: str = "coins"
    # What it unlocks ("background"); a game that does not know the type
    # shows the Special as unavailable.
    special_type: str | None = None
    sprite_name: str | None = None
    # Background Specials, from the files on disk (as cosmetics): separate
    # day/dusk/night pictures, and *_high versions.
    day_night: bool = False
    high_res: bool = False
    json_data: dict[str, Any] | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None

    class Config:
        from_attributes = True


class SpecialListResponse(BaseModel):
    """Response for listing specials."""
    specials: list[SpecialListItem]
    total: int


class SpecialDownloadResponse(BaseModel):
    """Response for downloading a purchased special: for a background, every
    picture it has (<sprite_name>[_day|_dusk|_night][_high].png)."""
    id: uuid.UUID
    name: str
    special_type: str | None = None
    currency: str = "coins"
    sprite_name: str | None = None
    day_night: bool = False
    high_res: bool = False
    json_data: dict[str, Any] | None = None
    sprites: dict[str, str] = Field(default_factory=dict)  # file name -> base64 data


# ============================================================================
# Purchase schemas
# ============================================================================

class PurchaseRequest(BaseModel):
    """Request to purchase an item."""
    item_id: uuid.UUID
    purchase_type: str  # module, cosmetic, gameplay, item, special


class PurchaseResponse(BaseModel):
    """Response for a purchase."""
    success: bool
    message: str
    purchase_id: uuid.UUID | None = None
    coins_remaining: int | None = None
    # The balance this purchase was paid from ("coins" or
    # "contribution_points") and, for points, what is left of them.
    currency: str = "coins"
    contribution_points_remaining: int | None = None


class UserPurchaseItem(BaseModel):
    """User's purchased item."""
    id: uuid.UUID
    item_id: uuid.UUID
    purchase_type: str
    price_paid: int
    currency: str = "coins"
    purchased_at: datetime

    class Config:
        from_attributes = True


class UserPurchasesResponse(BaseModel):
    """Response for user's purchases."""
    purchases: list[UserPurchaseItem]
    total: int


# ============================================================================
# Free first module schemas
# ============================================================================

class FreeModuleCheckResponse(BaseModel):
    """Response for checking/claiming free first module."""
    eligible: bool
    granted: bool
    module_id: uuid.UUID | None = None
    module_name: str | None = None
    message: str
