"""
Shop API routes.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.database import get_db
from omninet.models import PurchaseType
from omninet.schemas.shop import (
    CosmeticListItem,
    CosmeticListResponse,
    CosmeticDownloadResponse,
    GameplayListItem,
    GameplayListResponse,
    GameplayDownloadResponse,
    ItemListItem,
    ItemListResponse,
    ItemDownloadResponse,
    ModuleShopListItem,
    ModuleShopListResponse,
    ModuleDownloadResponse,
    SpecialListItem,
    SpecialListResponse,
    PurchaseRequest,
    PurchaseResponse,
    UserPurchaseItem,
    UserPurchasesResponse,
)
from omninet.services.shop import get_shop_service

router = APIRouter(prefix="/shop", tags=["shop"])


# ============================================================================
# Helper to get user from device key
# ============================================================================

async def get_user_from_device_key(
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Get user from device key header."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    return user


# ============================================================================
# Listing endpoints
# ============================================================================

@router.get("/cosmetics", response_model=CosmeticListResponse)
async def list_cosmetics(db: AsyncSession = Depends(get_db)):
    """List all available cosmetics in the shop."""
    shop_service = get_shop_service(db)
    cosmetics = await shop_service.list_cosmetics()
    
    items = [
        CosmeticListItem(
            id=c.id,
            name=c.name,
            cosmetic_type=c.cosmetic_type.value,
            price=c.price,
            sprite_name=c.sprite_name,
        )
        for c in cosmetics
    ]
    
    return CosmeticListResponse(cosmetics=items, total=len(items))


@router.get("/gameplay", response_model=GameplayListResponse)
async def list_gameplay(db: AsyncSession = Depends(get_db)):
    """List all available gameplay items in the shop."""
    shop_service = get_shop_service(db)
    gameplay_items = await shop_service.list_gameplay()
    
    items = [
        GameplayListItem(
            id=g.id,
            name=g.name,
            description=g.description,
            price=g.price,
        )
        for g in gameplay_items
    ]
    
    return GameplayListResponse(gameplay=items, total=len(items))


@router.get("/items", response_model=ItemListResponse)
async def list_items(db: AsyncSession = Depends(get_db)):
    """List all available items in the shop."""
    shop_service = get_shop_service(db)
    shop_items = await shop_service.list_items()
    
    items = [
        ItemListItem(
            id=i.id,
            name=i.name,
            description=i.description,
            price=i.price,
            sprite_name=i.sprite_name,
        )
        for i in shop_items
    ]
    
    return ItemListResponse(items=items, total=len(items))


@router.get("/modules", response_model=ModuleShopListResponse)
async def list_modules(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all available modules in the shop, optionally filtered by category."""
    shop_service = get_shop_service(db)
    modules = await shop_service.list_modules(category=category)
    
    items = [
        ModuleShopListItem(
            id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            category=m.category.name if m.category else None,
            price=m.price,
            owner_nickname=m.owner.nickname if m.owner else "Unknown",
            is_official=m.is_official,
        )
        for m in modules
    ]
    
    return ModuleShopListResponse(modules=items, total=len(items))


@router.get("/specials", response_model=SpecialListResponse)
async def list_specials(db: AsyncSession = Depends(get_db)):
    """List all available special items in the shop."""
    shop_service = get_shop_service(db)
    specials = await shop_service.list_specials()
    
    items = [
        SpecialListItem(
            id=s.id,
            name=s.name,
            description=s.description,
            price=s.price,
            start_date=s.start_date,
            end_date=s.end_date,
        )
        for s in specials
    ]
    
    return SpecialListResponse(specials=items, total=len(items))


# ============================================================================
# Purchase endpoints
# ============================================================================

@router.post("/purchase", response_model=PurchaseResponse)
async def purchase_item(
    request: PurchaseRequest,
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Purchase an item from the shop."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    # Map string to enum
    try:
        purchase_type = PurchaseType(request.purchase_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid purchase type: {request.purchase_type}",
        )
    
    success, message, purchase_id = await shop_service.purchase_item(
        user=user,
        item_id=request.item_id,
        purchase_type=purchase_type,
    )
    
    return PurchaseResponse(
        success=success,
        message=message,
        purchase_id=purchase_id,
        coins_remaining=user.coins if success else None,
    )


@router.get("/purchases", response_model=UserPurchasesResponse)
async def get_user_purchases(
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Get all purchases for the authenticated user."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    purchases = await shop_service.get_user_purchases(user.id)
    
    items = [
        UserPurchaseItem(
            id=p.id,
            item_id=p.item_id,
            purchase_type=p.purchase_type.value,
            price_paid=p.price_paid,
            purchased_at=p.purchased_at,
        )
        for p in purchases
    ]
    
    return UserPurchasesResponse(purchases=items, total=len(items))


# ============================================================================
# Download endpoints
# ============================================================================

@router.get("/download/cosmetic/{item_id}", response_model=CosmeticDownloadResponse)
async def download_cosmetic(
    item_id: uuid.UUID,
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Download a purchased cosmetic."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    result = await shop_service.download_cosmetic(user, item_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cosmetic not found or not owned",
        )
    
    return CosmeticDownloadResponse(**result)


@router.get("/download/gameplay/{item_id}", response_model=GameplayDownloadResponse)
async def download_gameplay(
    item_id: uuid.UUID,
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Download a purchased gameplay item."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    result = await shop_service.download_gameplay(user, item_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gameplay item not found or not owned",
        )
    
    return GameplayDownloadResponse(**result)


@router.get("/download/item/{item_id}", response_model=ItemDownloadResponse)
async def download_item(
    item_id: uuid.UUID,
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Download a purchased item."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    result = await shop_service.download_item(user, item_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or not owned",
        )
    
    return ItemDownloadResponse(**result)


@router.get("/download/module/{item_id}", response_model=ModuleDownloadResponse)
async def download_module(
    item_id: uuid.UUID,
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Download a purchased module."""
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    result = await shop_service.download_module(user, item_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found or not owned",
        )
    
    return ModuleDownloadResponse(**result)


# ============================================================================
# Free first module endpoint
# ============================================================================

@router.post("/claim-free-module")
async def claim_free_module(
    device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if user is eligible for a free first official module and claim it.
    
    New users with no purchases are eligible for one free official module.
    If eligible and an official module exists, it will be automatically granted.
    """
    from omninet.schemas.shop import FreeModuleCheckResponse
    
    shop_service = get_shop_service(db)
    user = await shop_service.get_user_by_device_key(device_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive device key",
        )
    
    # Check if user already has purchases
    has_purchases = await shop_service.user_has_any_purchases(user.id)
    if has_purchases:
        return FreeModuleCheckResponse(
            eligible=False,
            granted=False,
            message="Not eligible - user already has purchases"
        )
    
    # Try to grant free module
    result = await shop_service.check_and_grant_free_module(user)
    
    if result:
        return FreeModuleCheckResponse(
            eligible=True,
            granted=True,
            module_id=uuid.UUID(result["id"]),
            module_name=result["name"],
            message=result["message"]
        )
    else:
        # No official module available
        return FreeModuleCheckResponse(
            eligible=True,
            granted=False,
            message="No official modules available at this time"
        )
