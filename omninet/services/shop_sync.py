"""
Shop sync worker - syncs JSON files to database.
Runs daily at midnight to update shop items from JSON files.
"""
import asyncio
import json
import uuid
from datetime import datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.database import async_session_maker
from omninet.models import ShopCosmetic, ShopGameplay, ShopItem, CosmeticType


# Storage paths
STORAGE_PATH = Path(__file__).parent.parent.parent / "storage"
BACKGROUNDS_JSON = STORAGE_PATH / "backgrounds" / "backgrounds.json"
GAMEPLAY_JSON = STORAGE_PATH / "gameplay" / "gameplay.json"
ITEMS_JSON = STORAGE_PATH / "items" / "items.json"


async def sync_backgrounds(db: AsyncSession) -> int:
    """
    Sync backgrounds from JSON to database.
    Updates JSON file with generated IDs for new items.
    Returns count of items synced.
    """
    if not BACKGROUNDS_JSON.exists():
        print(f"[ShopSync] Backgrounds JSON not found: {BACKGROUNDS_JSON}")
        return 0

    with open(BACKGROUNDS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    backgrounds = data.get("backgrounds", [])
    updated = False
    synced = 0

    for bg in backgrounds:
        name = bg.get("name", "")
        price = bg.get("price", 0)
        json_data = bg.get("json", {})
        bg_id = bg.get("id")

        # Generate ID if missing
        if not bg_id:
            bg_id = str(uuid.uuid4())
            bg["id"] = bg_id
            updated = True

        # Check if exists in database
        result = await db.execute(
            select(ShopCosmetic).where(ShopCosmetic.id == uuid.UUID(bg_id))
        )
        existing = result.scalar_one_or_none()

        # Sprite name: bg_<json.name>.png for preview
        sprite_name = f"bg_{json_data.get('name', '')}" if json_data.get("name") else None

        if existing:
            # Update existing
            existing.name = name
            existing.price = price
            existing.json_data = json_data
            existing.sprite_name = sprite_name
            existing.enabled = True
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            cosmetic = ShopCosmetic(
                id=uuid.UUID(bg_id),
                cosmetic_type=CosmeticType.BACKGROUND,
                name=name,
                price=price,
                json_data=json_data,
                sprite_name=sprite_name,
                enabled=True,
            )
            db.add(cosmetic)

        synced += 1

    # Disable items not in JSON
    all_bg_ids = [uuid.UUID(bg["id"]) for bg in backgrounds if bg.get("id")]
    result = await db.execute(
        select(ShopCosmetic).where(
            ShopCosmetic.cosmetic_type == CosmeticType.BACKGROUND,
            ShopCosmetic.id.notin_(all_bg_ids) if all_bg_ids else True,
        )
    )
    for cosmetic in result.scalars():
        if cosmetic.id not in all_bg_ids:
            cosmetic.enabled = False

    await db.commit()

    # Update JSON file with IDs
    if updated:
        with open(BACKGROUNDS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[ShopSync] Updated backgrounds.json with new IDs")

    return synced


async def sync_gameplay(db: AsyncSession) -> int:
    """
    Sync gameplay items from JSON to database.
    Updates JSON file with generated IDs for new items.
    Returns count of items synced.
    """
    if not GAMEPLAY_JSON.exists():
        print(f"[ShopSync] Gameplay JSON not found: {GAMEPLAY_JSON}")
        return 0

    with open(GAMEPLAY_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    gameplay_items = data.get("gameplay", [])
    updated = False
    synced = 0

    for gp in gameplay_items:
        name = gp.get("name", "")
        price = gp.get("price", 0)
        description = gp.get("description", "")
        gp_id = gp.get("id")

        # Generate ID if missing
        if not gp_id:
            gp_id = str(uuid.uuid4())
            gp["id"] = gp_id
            updated = True

        # Build json_data from remaining fields
        json_data = {k: v for k, v in gp.items() if k not in ["id", "name", "price", "description"]}

        # Check if exists in database
        result = await db.execute(
            select(ShopGameplay).where(ShopGameplay.id == uuid.UUID(gp_id))
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.name = name
            existing.price = price
            existing.description = description
            existing.json_data = json_data
            existing.enabled = True
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            gameplay = ShopGameplay(
                id=uuid.UUID(gp_id),
                name=name,
                description=description,
                price=price,
                json_data=json_data,
                enabled=True,
            )
            db.add(gameplay)

        synced += 1

    # Disable items not in JSON
    all_gp_ids = [uuid.UUID(gp["id"]) for gp in gameplay_items if gp.get("id")]
    result = await db.execute(
        select(ShopGameplay).where(
            ShopGameplay.id.notin_(all_gp_ids) if all_gp_ids else True
        )
    )
    for gameplay in result.scalars():
        if gameplay.id not in all_gp_ids:
            gameplay.enabled = False

    await db.commit()

    # Update JSON file with IDs
    if updated:
        with open(GAMEPLAY_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[ShopSync] Updated gameplay.json with new IDs")

    return synced


async def sync_items(db: AsyncSession) -> int:
    """
    Sync items from JSON to database.
    Updates JSON file with generated IDs for new items.
    Returns count of items synced.
    """
    if not ITEMS_JSON.exists():
        print(f"[ShopSync] Items JSON not found: {ITEMS_JSON}")
        return 0

    with open(ITEMS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("item", [])
    updated = False
    synced = 0

    for item in items:
        name = item.get("name", "")
        price = item.get("price", 0)
        json_data = item.get("json", {})
        item_id = item.get("id")

        # Generate ID if missing (use json.id if available)
        if not item_id:
            item_id = json_data.get("id") or str(uuid.uuid4())
            item["id"] = item_id
            updated = True

        # Get sprite name from json data
        sprite_name = json_data.get("sprite_name")
        description = json_data.get("description", "")

        # Check if exists in database
        result = await db.execute(
            select(ShopItem).where(ShopItem.id == uuid.UUID(item_id))
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.name = name
            existing.price = price
            existing.description = description
            existing.json_data = json_data
            existing.sprite_name = sprite_name
            existing.enabled = True
            existing.updated_at = datetime.utcnow()
        else:
            # Create new
            shop_item = ShopItem(
                id=uuid.UUID(item_id),
                name=name,
                description=description,
                price=price,
                json_data=json_data,
                sprite_name=sprite_name,
                enabled=True,
            )
            db.add(shop_item)

        synced += 1

    # Disable items not in JSON
    all_item_ids = [uuid.UUID(item["id"]) for item in items if item.get("id")]
    result = await db.execute(
        select(ShopItem).where(
            ShopItem.id.notin_(all_item_ids) if all_item_ids else True
        )
    )
    for shop_item in result.scalars():
        if shop_item.id not in all_item_ids:
            shop_item.enabled = False

    await db.commit()

    # Update JSON file with IDs
    if updated:
        with open(ITEMS_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[ShopSync] Updated items.json with new IDs")

    return synced


async def run_shop_sync():
    """Run a full shop sync."""
    print("[ShopSync] Starting shop sync...")
    
    async with async_session_maker() as db:
        try:
            bg_count = await sync_backgrounds(db)
            print(f"[ShopSync] Synced {bg_count} backgrounds")
            
            gp_count = await sync_gameplay(db)
            print(f"[ShopSync] Synced {gp_count} gameplay items")
            
            item_count = await sync_items(db)
            print(f"[ShopSync] Synced {item_count} items")
            
            print("[ShopSync] Shop sync complete")
        except Exception as e:
            print(f"[ShopSync] Error during sync: {e}")
            raise


async def shop_sync_worker():
    """
    Background worker that runs shop sync daily at midnight.
    Also runs once on startup.
    """
    # Run once on startup
    print("[ShopSync] Running initial sync on startup...")
    try:
        await run_shop_sync()
    except Exception as e:
        print(f"[ShopSync] Initial sync failed: {e}")

    while True:
        # Calculate time until next midnight
        now = datetime.now()
        next_midnight = datetime.combine(now.date(), time(0, 0)) 
        if now >= next_midnight:
            # Already past midnight today, schedule for tomorrow
            from datetime import timedelta
            next_midnight += timedelta(days=1)
        
        sleep_seconds = (next_midnight - now).total_seconds()
        print(f"[ShopSync] Next sync scheduled in {sleep_seconds / 3600:.1f} hours")
        
        await asyncio.sleep(sleep_seconds)
        
        try:
            await run_shop_sync()
        except Exception as e:
            print(f"[ShopSync] Scheduled sync failed: {e}")


# For manual sync via command line
if __name__ == "__main__":
    asyncio.run(run_shop_sync())
