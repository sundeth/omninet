"""
Shop-related Pydantic schemas.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

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
    sprite_name: Optional[str] = None
    
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
    json_data: Optional[dict[str, Any]] = None
    sprites: dict[str, str] = Field(default_factory=dict)  # name -> base64 data


# ============================================================================
# Gameplay schemas
# ============================================================================

class GameplayListItem(BaseModel):
    """Gameplay item for shop listing."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
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
    json_data: Optional[dict[str, Any]] = None


# ============================================================================
# Item schemas
# ============================================================================

class ItemListItem(BaseModel):
    """Item for shop listing."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    price: int
    sprite_name: Optional[str] = None
    
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
    json_data: Optional[dict[str, Any]] = None
    sprites: dict[str, str] = Field(default_factory=dict)  # name -> base64 data


# ============================================================================
# Module schemas (shop-specific)
# ============================================================================

class ModuleShopListItem(BaseModel):
    """Module for shop listing."""
    id: uuid.UUID
    name: str
    version: str
    description: Optional[str] = None
    category: Optional[str] = None
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
    description: Optional[str] = None
    price: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SpecialListResponse(BaseModel):
    """Response for listing specials."""
    specials: list[SpecialListItem]
    total: int


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
    purchase_id: Optional[uuid.UUID] = None
    coins_remaining: Optional[int] = None


class UserPurchaseItem(BaseModel):
    """User's purchased item."""
    id: uuid.UUID
    item_id: uuid.UUID
    purchase_type: str
    price_paid: int
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
    module_id: Optional[uuid.UUID] = None
    module_name: Optional[str] = None
    message: str
