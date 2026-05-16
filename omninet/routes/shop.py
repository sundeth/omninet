"""
Shop API routes.
"""
import base64
import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.config import settings
from omninet.database import get_db
from omninet.models import PurchaseType
from omninet.schemas.shop import (
    CosmeticDownloadResponse,
    CosmeticListItem,
    CosmeticListResponse,
    GameplayDownloadResponse,
    GameplayListItem,
    GameplayListResponse,
    ItemDownloadResponse,
    ItemListItem,
    ItemListResponse,
    ModuleDownloadResponse,
    ModuleShopListItem,
    ModuleShopListResponse,
    PurchaseRequest,
    PurchaseResponse,
    SpecialListItem,
    SpecialListResponse,
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
            day_night=getattr(c, 'day_night', True),
            high_res=getattr(c, 'high_res', False),
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
    category: str | None = None,
    device_key: str | None = Header(None, alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """List all available modules in the shop, optionally filtered by category.

    Module pricing is centralized — the DB ``price`` column is ignored.
    Every module is reported at ``settings.module_fixed_price`` unless the
    player has never bought a module before, in which case all modules
    are reported at 0 (the player can pick any one as their free first
    module).  This is the server's source of truth; the client just
    renders whatever ``price`` it receives.
    """
    shop_service = get_shop_service(db)
    modules = await shop_service.list_modules(category=category)

    fixed_price = settings.module_fixed_price
    effective_price = fixed_price

    if device_key:
        user = await shop_service.get_user_by_device_key(device_key)
        if user and not await shop_service.user_has_any_module_purchase(user.id):
            effective_price = 0

    items = [
        ModuleShopListItem(
            id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            category=m.category.name if m.category else None,
            price=effective_price,
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
# Sprite serving
# ============================================================================

# Map URL ``kind`` segment to (shop-service getter, asset-folder name).
# The folder names match the deployed layout under
# ``<shop_assets_base>/<environment>/<folder>/`` — sprites for backgrounds
# live in ``backgrounds`` rather than ``cosmetics`` because that's the
# admin-friendly category split (the only CosmeticType today is BACKGROUND).
_SPRITE_KIND_LOADERS = {
    "item":     (lambda svc, item_id: svc.get_item(item_id),     "items"),
    "cosmetic": (lambda svc, item_id: svc.get_cosmetic(item_id), "backgrounds"),
    "gameplay": (lambda svc, item_id: svc.get_gameplay(item_id), "gameplay"),
    "special":  (lambda svc, item_id: svc.get_special(item_id),  "specials"),
}


_SPRITE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _shop_sprite_candidates(folder: str, sprite_name: str) -> list[str]:
    """Resolve candidate on-disk paths for a sprite.

    DB rows often store ``sprite_name`` without an extension (e.g.
    ``"icon_itm802"`` referring to ``icon_itm802.png``).  Try the raw name
    first, then each common image extension.  Returns the ordered list of
    absolute paths the endpoint should probe.
    """
    safe_name = os.path.basename(sprite_name)
    base_dir = os.path.join(
        settings.shop_assets_base, settings.environment, folder
    )
    candidates = [os.path.join(base_dir, safe_name)]
    if "." not in safe_name:
        candidates.extend(
            os.path.join(base_dir, safe_name + ext) for ext in _SPRITE_EXTENSIONS
        )
    return candidates


def _shop_sprite_path(folder: str, sprite_name: str) -> str:
    """First candidate path for diagnostic display (no extension fixup)."""
    return _shop_sprite_candidates(folder, sprite_name)[0]


@router.get("/{kind}/{item_id}/sprite")
async def get_shop_sprite(
    kind: str,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve the sprite PNG for a shop entry.

    Lookup order:
        1. ``<shop_assets_base>/<environment>/<kind_folder>/<sprite_name>``
           on disk (the per-environment asset tree mounted from the
           share — admins drop files there and they are served live).
        2. ``json_data['sprite_b64']`` blob inline in the DB (fallback
           for one-off entries that didn't ship with a file).

    Returns 404 (with a diagnostic ``detail`` string) if neither produces
    bytes — useful for debugging admin setup.
    """
    spec = _SPRITE_KIND_LOADERS.get(kind)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown sprite kind")
    loader, folder = spec

    shop_service = get_shop_service(db)
    entry = await loader(shop_service, item_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{kind} {item_id} not found")

    sprite_name = getattr(entry, "sprite_name", None) or ""

    # 1) Filesystem (per-environment asset tree).  Try sprite_name as-is
    # first; if it has no extension, also try the common image suffixes
    # so admin doesn't have to update DB rows that store bare basenames.
    if sprite_name:
        for path in _shop_sprite_candidates(folder, sprite_name):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as f:
                    return Response(content=f.read(), media_type="image/png")
            except Exception as exc:
                print(f"[shop] {kind} {item_id} read failed at {path}: {exc}")

    # 2) Inline blob fallback
    json_data = getattr(entry, "json_data", None) or {}
    b64 = json_data.get("sprite_b64") if isinstance(json_data, dict) else None
    if b64:
        try:
            return Response(content=base64.b64decode(b64), media_type="image/png")
        except Exception as exc:
            print(f"[shop] {kind} {item_id} sprite_b64 decode failed: {exc}")

    # Build a full report of what was tried.  Listing the parent
    # directory makes typos / case-mismatch jump out immediately.
    if sprite_name:
        candidates = [os.path.abspath(p) for p in _shop_sprite_candidates(folder, sprite_name)]
        parent_dir = os.path.dirname(candidates[0])
        try:
            available = sorted(os.listdir(parent_dir))[:30]
        except Exception as exc:
            available = [f"<could not list {parent_dir}: {exc}>"]
    else:
        candidates = ["(n/a — sprite_name empty)"]
        parent_dir = "(n/a)"
        available = []

    print(
        f"[shop:v2] {kind} {item_id} sprite miss: "
        f"sprite_name={sprite_name!r} folder={folder!r} "
        f"tried={candidates} dir_listing[:30]={available}"
    )
    raise HTTPException(
        status_code=404,
        detail=(
            f"No sprite for {kind}/{item_id}. "
            f"sprite_name={sprite_name or '(empty)'}, "
            f"tried={candidates}"
        ),
    )


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
