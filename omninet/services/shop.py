"""
Shop service for handling shop items, purchases, and downloads.
"""
import base64
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.config import settings
from omninet.models import (
    CosmeticType,
    GameModule,
    ModuleStatus,
    PurchaseType,
    ShopCosmetic,
    ShopGameplay,
    ShopItem,
    ShopSpecial,
    User,
    UserDevice,
    UserPurchase,
)
from omninet.models.shop import (
    CURRENCY_COINS,
    CURRENCY_CONTRIBUTION_POINTS,
    SPECIAL_TYPE_BACKGROUND,
)
from omninet.services.backgrounds import background_flags, background_payload
from omninet.services.contribution import ContributionService


def special_on_sale(special: ShopSpecial, now: datetime | None = None) -> bool:
    """A Special is sold while enabled and inside its dates (either open)."""
    if not special.enabled:
        return False
    now = now or datetime.now(UTC)
    if special.start_date is not None and special.start_date > now:
        return False
    if special.end_date is not None and special.end_date < now:
        return False
    return True


class ShopService:
    """Service for shop operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========================================================================
    # Listing methods
    # ========================================================================

    async def list_cosmetics(self) -> list[ShopCosmetic]:
        """List all enabled cosmetics."""
        result = await self.db.execute(
            select(ShopCosmetic)
            .where(ShopCosmetic.enabled.is_(True))
            .order_by(ShopCosmetic.name)
        )
        return list(result.scalars().all())

    async def list_gameplay(self) -> list[ShopGameplay]:
        """List all enabled gameplay items."""
        result = await self.db.execute(
            select(ShopGameplay)
            .where(ShopGameplay.enabled.is_(True))
            .order_by(ShopGameplay.name)
        )
        return list(result.scalars().all())

    async def list_items(self) -> list[ShopItem]:
        """List all enabled items."""
        result = await self.db.execute(
            select(ShopItem)
            .where(ShopItem.enabled.is_(True))
            .order_by(ShopItem.name)
        )
        return list(result.scalars().all())

    async def list_specials(self) -> list[ShopSpecial]:
        """The Specials on sale now: enabled and inside their dates."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(ShopSpecial)
            .where(
                ShopSpecial.enabled.is_(True),
                or_(ShopSpecial.start_date.is_(None), ShopSpecial.start_date <= now),
                or_(ShopSpecial.end_date.is_(None), ShopSpecial.end_date >= now),
            )
            .order_by(ShopSpecial.sort_order, ShopSpecial.name)
        )
        return list(result.scalars().all())

    async def list_modules(self, category: str | None = None) -> list[GameModule]:
        """List all published modules, optionally filtered by category."""
        query = (
            select(GameModule)
            .options(selectinload(GameModule.owner), selectinload(GameModule.category))
            .where(GameModule.status == ModuleStatus.PUBLISHED)
        )

        if category:
            query = query.join(GameModule.category).where(
                GameModule.category.has(name=category)
            )

        query = query.order_by(GameModule.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ========================================================================
    # Get item methods
    # ========================================================================

    async def get_cosmetic(self, item_id: uuid.UUID) -> ShopCosmetic | None:
        """Get a cosmetic by ID."""
        result = await self.db.execute(
            select(ShopCosmetic).where(ShopCosmetic.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_gameplay(self, item_id: uuid.UUID) -> ShopGameplay | None:
        """Get a gameplay item by ID."""
        result = await self.db.execute(
            select(ShopGameplay).where(ShopGameplay.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_item(self, item_id: uuid.UUID) -> ShopItem | None:
        """Get an item by ID."""
        result = await self.db.execute(
            select(ShopItem).where(ShopItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_special(self, item_id: uuid.UUID) -> ShopSpecial | None:
        """Get a special by ID."""
        result = await self.db.execute(
            select(ShopSpecial).where(ShopSpecial.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_module(self, item_id: uuid.UUID) -> GameModule | None:
        """Get a module by ID."""
        result = await self.db.execute(
            select(GameModule).where(GameModule.id == item_id)
        )
        return result.scalar_one_or_none()

    # ========================================================================
    # Ownership validation
    # ========================================================================

    async def user_owns_item(
        self, user_id: uuid.UUID, item_id: uuid.UUID, purchase_type: PurchaseType
    ) -> bool:
        """Check if user owns an item.

        Items can be bought again and again, so there may be several
        purchases of one: any of them is ownership (scalar_one_or_none()
        raised MultipleResultsFound, a 500 on the item's download)."""
        result = await self.db.execute(
            select(UserPurchase.id).where(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id == item_id,
                UserPurchase.purchase_type == purchase_type,
            ).limit(1)
        )
        return result.scalars().first() is not None

    async def get_user_by_device_key(self, device_key: str) -> User | None:
        """Get user by device secret key."""
        result = await self.db.execute(
            select(UserDevice)
            .options(selectinload(UserDevice.owner))
            .where(UserDevice.secret_key == device_key, UserDevice.is_active.is_(True))
        )
        device = result.scalar_one_or_none()
        return device.owner if device else None

    # ========================================================================
    # Purchase methods
    # ========================================================================

    async def purchase_item(
        self, user: User, item_id: uuid.UUID, purchase_type: PurchaseType
    ) -> tuple[bool, str, uuid.UUID | None]:
        """
        Purchase an item.
        Returns (success, message, purchase_id).
        """
        # Get the item and its price
        price = 0
        item_name = ""
        # Specials may be priced in contribution points instead of coins.
        currency = CURRENCY_COINS
        self.last_currency = CURRENCY_COINS

        if purchase_type == PurchaseType.COSMETIC:
            item = await self.get_cosmetic(item_id)
            if not item or not item.enabled:
                return False, "Cosmetic not found or not available", None
            price = item.price
            item_name = item.name

        elif purchase_type == PurchaseType.GAMEPLAY:
            item = await self.get_gameplay(item_id)
            if not item or not item.enabled:
                return False, "Gameplay item not found or not available", None
            price = item.price
            item_name = item.name

        elif purchase_type == PurchaseType.ITEM:
            item = await self.get_item(item_id)
            if not item or not item.enabled:
                return False, "Item not found or not available", None
            price = item.price
            item_name = item.name

        elif purchase_type == PurchaseType.SPECIAL:
            item = await self.get_special(item_id)
            if not item or not special_on_sale(item):
                return False, "Special not found or not available", None
            price = item.price
            item_name = item.name
            currency = item.currency or CURRENCY_COINS
            if currency not in (CURRENCY_COINS, CURRENCY_CONTRIBUTION_POINTS):
                return False, f"{item_name} cannot be bought yet", None

        elif purchase_type == PurchaseType.MODULE:
            item = await self.get_module(item_id)
            if not item or item.status != ModuleStatus.PUBLISHED:
                return False, "Module not found or not available", None
            item_name = item.name
            # Module pricing is centralized — the DB price column is
            # ignored.  Every module costs ``settings.module_fixed_price``
            # except for the player's very first module purchase across
            # all their linked devices, which is free.
            if await self.user_has_any_module_purchase(user.id):
                price = settings.module_fixed_price
            else:
                price = 0
        else:
            return False, "Invalid purchase type", None

        # Unlocks (modules, cosmetics, gameplay, specials) are bought once and
        # kept; items are consumables, bought again whenever the player has
        # the coins (owner, 2026-10-17). Each purchase is its own row, which
        # the game counts as one item.
        if purchase_type != PurchaseType.ITEM and await self.user_owns_item(user.id, item_id, purchase_type):
            return False, f"You already own {item_name}", None

        if currency == CURRENCY_CONTRIBUTION_POINTS:
            # Paid from the contribution points, never the coins. Points
            # waiting for the account's email count; the balance is taken in
            # one conditional statement, so it cannot be spent twice.
            points = ContributionService(self.db)
            have = await points.balance_of(user)
            if price > 0 and await points.spend_points(user, price) is None:
                return False, (f"Not enough contribution points. Need {price}, "
                               f"have {have}"), None
        else:
            # Check if user has enough coins
            if user.coins < price:
                return False, f"Not enough coins. Need {price}, have {user.coins}", None

            # Deduct coins
            user.coins -= price
        self.last_currency = currency

        # Create purchase record
        purchase = UserPurchase(
            user_id=user.id,
            item_id=item_id,
            purchase_type=purchase_type,
            price_paid=price,
            currency=currency,
        )
        self.db.add(purchase)

        # Increment sell count
        item.sell_count += 1

        await self.db.commit()
        await self.db.refresh(purchase)

        return True, f"Successfully purchased {item_name}", purchase.id

    # ========================================================================
    # Download methods
    # ========================================================================

    async def download_cosmetic(
        self, user: User, item_id: uuid.UUID
    ) -> dict | None:
        """
        Download a purchased cosmetic.
        Returns dict with id, name, cosmetic_type, json_data, sprites.
        """
        if not await self.user_owns_item(user.id, item_id, PurchaseType.COSMETIC):
            return None

        cosmetic = await self.get_cosmetic(item_id)
        if not cosmetic:
            return None

        # A background's pictures, as they are on disk (services/backgrounds):
        # every time of day and resolution it has. The file names were sent
        # with empty contents before (a TODO), so a download saved empty files.
        sprites = {}
        if cosmetic.cosmetic_type == CosmeticType.BACKGROUND:
            json_data = cosmetic.json_data or {}
            base = cosmetic.sprite_name or (
                f"bg_{json_data['name']}" if json_data.get("name") else "")
            if base:
                sprites = background_payload(base)

        return {
            "id": cosmetic.id,
            "name": cosmetic.name,
            "cosmetic_type": cosmetic.cosmetic_type.value,
            "json_data": cosmetic.json_data,
            "sprites": sprites,
        }

    async def download_special(
        self, user: User, item_id: uuid.UUID
    ) -> dict | None:
        """A purchased Special: what it is and, for a background, every
        picture it has. None when not owned (a Special taken off sale stays
        downloadable for those who bought it)."""
        if not await self.user_owns_item(user.id, item_id, PurchaseType.SPECIAL):
            return None
        special = await self.get_special(item_id)
        if not special:
            return None
        sprites = {}
        day_night = high_res = False
        if special.special_type == SPECIAL_TYPE_BACKGROUND and special.sprite_name:
            sprites = background_payload(special.sprite_name)
            day_night, high_res = background_flags(special.sprite_name)
        return {
            "id": special.id,
            "name": special.name,
            "special_type": special.special_type,
            "currency": special.currency or CURRENCY_COINS,
            "sprite_name": special.sprite_name,
            "day_night": day_night,
            "high_res": high_res,
            "json_data": special.json_data,
            "sprites": sprites,
        }

    async def download_gameplay(
        self, user: User, item_id: uuid.UUID
    ) -> dict | None:
        """
        Download a purchased gameplay item.
        Returns dict with id, name, json_data.
        """
        if not await self.user_owns_item(user.id, item_id, PurchaseType.GAMEPLAY):
            return None

        gameplay = await self.get_gameplay(item_id)
        if not gameplay:
            return None

        return {
            "id": gameplay.id,
            "name": gameplay.name,
            "json_data": gameplay.json_data,
        }

    async def download_item(
        self, user: User, item_id: uuid.UUID
    ) -> dict | None:
        """
        Download a purchased item.
        Returns dict with id, name, json_data, sprites.
        """
        if not await self.user_owns_item(user.id, item_id, PurchaseType.ITEM):
            return None

        item = await self.get_item(item_id)
        if not item:
            return None

        # The item's picture, as the shop serves it (<shop assets>/items/, or
        # the entry's inline sprite_b64); empty when there is none, as before.
        sprites = {}
        if item.sprite_name:
            name = Path(item.sprite_name).name
            stem = name[:-4] if name.lower().endswith(".png") else name
            data = ""
            folder = Path(settings.shop_assets_base) / "items"
            for path in (folder / name, folder / f"{stem}.png"):
                if path.is_file():
                    data = base64.b64encode(path.read_bytes()).decode("ascii")
                    break
            if not data and isinstance(item.json_data, dict):
                data = item.json_data.get("sprite_b64") or ""
            sprites[f"{stem}.png"] = data

        return {
            "id": item.id,
            "name": item.name,
            "json_data": item.json_data,
            "sprites": sprites,
        }

    async def download_module(
        self, user: User, item_id: uuid.UUID
    ) -> dict | None:
        """
        Download a purchased module.
        Returns dict with id, name, version, file_data (base64).
        """
        if not await self.user_owns_item(user.id, item_id, PurchaseType.MODULE):
            return None

        module = await self.get_module(item_id)
        if not module or not module.file_name:
            return None

        # Load module zip file
        module_path = Path(settings.MODULES_STORAGE_PATH) / module.file_name
        if not module_path.exists():
            return None

        with open(module_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "id": module.id,
            "name": module.name,
            "version": module.version,
            "file_data": file_data,
        }

    # ========================================================================
    # User purchases
    # ========================================================================

    async def get_user_purchases(self, user_id: uuid.UUID) -> list[UserPurchase]:
        """Get all purchases for a user."""
        result = await self.db.execute(
            select(UserPurchase)
            .where(UserPurchase.user_id == user_id)
            .order_by(UserPurchase.purchased_at.desc())
        )
        return list(result.scalars().all())

    # ========================================================================
    # Free first module for new accounts
    # ========================================================================

    async def get_first_official_module(self) -> GameModule | None:
        """
        Get the first available official module for new users.
        Returns the first published official module sorted by name.
        """
        result = await self.db.execute(
            select(GameModule)
            .where(
                GameModule.status == ModuleStatus.PUBLISHED,
                GameModule.is_official.is_(True)
            )
            .order_by(GameModule.name)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def user_has_any_purchases(self, user_id: uuid.UUID) -> bool:
        """Check if user has made any purchases."""
        result = await self.db.execute(
            select(UserPurchase.id)
            .where(UserPurchase.user_id == user_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def user_has_any_module_purchase(self, user_id: uuid.UUID) -> bool:
        """True if the user has ever purchased (or been granted) a module.

        Used by the module-listing/purchase flow to decide whether the
        player is still eligible for the free-first-module grant.
        """
        result = await self.db.execute(
            select(UserPurchase.id)
            .where(UserPurchase.user_id == user_id)
            .where(UserPurchase.purchase_type == PurchaseType.MODULE)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def grant_free_first_module(
        self, user: User
    ) -> tuple[bool, str, uuid.UUID | None]:
        """
        Grant the first official module for free to a new user.
        Only grants if user has no existing purchases.

        Returns (success, message, module_id).
        """
        # Check if user already has purchases
        if await self.user_has_any_purchases(user.id):
            return False, "User already has purchases", None

        # Get first official module
        official_module = await self.get_first_official_module()
        if not official_module:
            return False, "No official modules available", None

        # Grant the module for free (price_paid = 0)
        purchase = UserPurchase(
            user_id=user.id,
            item_id=official_module.id,
            purchase_type=PurchaseType.MODULE,
            price_paid=0,
        )
        self.db.add(purchase)
        await self.db.commit()
        await self.db.refresh(purchase)

        return True, f"Free module '{official_module.name}' granted", official_module.id

    async def check_and_grant_free_module(
        self, user: User
    ) -> dict | None:
        """
        Check if user is eligible for a free first module and grant it if so.

        Returns module info dict if granted, None otherwise.
        """
        success, message, module_id = await self.grant_free_first_module(user)

        if not success:
            return None

        # Return module info for immediate download
        module = await self.get_module(module_id)
        if module:
            return {
                "id": str(module.id),
                "name": module.name,
                "version": module.version,
                "description": module.description,
                "message": message,
            }
        return None


# Singleton-like access
def get_shop_service(db: AsyncSession) -> ShopService:
    """Get shop service instance."""
    return ShopService(db)
