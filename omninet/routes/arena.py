"""
Arena routes: the module list players need, admin runtime/season controls,
and development-only tools for running whole seasons in minutes.

Development tools (``/dev/arena/...``) exist only when ENVIRONMENT=dev, and
need an admin's ``X-Device-Key`` -- or ``X-Dev-Token`` matching
``ARENA_DEV_TOKEN`` when that is set.  The dev server is public, so they are
never open.
"""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from omninet.arena import bots, engine, rules
from omninet.arena.runtime import ArenaRuntime, RuntimeUpdateError
from omninet.config import settings
from omninet.models.battle import GameTeam
from omninet.models.module import GameModule, ModuleStatus
from omninet.routes.deps import AdminUser, DbSession
from omninet.routes.seasons import season_response
from omninet.schemas.battle import (
    ArenaModuleResponse,
    ArenaModulesResponse,
    SeasonConfig,
    SeasonRestrictions,
)
from omninet.services.device import DeviceService
from omninet.services.season import SeasonService

router = APIRouter(tags=["Arena"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _status(db) -> dict:
    service = SeasonService(db)
    active = await service.get_active_season()
    runtime = ArenaRuntime()
    teams = dummies = 0
    if active is not None:
        teams = (await db.execute(
            select(func.count(GameTeam.id)).where(GameTeam.season_id == active.id)
        )).scalar_one()
        dummies = (await db.execute(
            select(func.count(GameTeam.id))
            .where(GameTeam.season_id == active.id)
            .where(GameTeam.is_dummy.is_(True))
        )).scalar_one()
    return {
        "environment": settings.environment,
        "season": season_response(active).model_dump(mode="json") if active else None,
        "teams": teams,
        "dummy_teams": dummies,
        "runtime": runtime.current(),
        "pending_updates": runtime.pending(),
        "schedule": {
            "auto_seasons": settings.arena_auto_seasons,
            "length_hours": settings.arena_season_length_hours,
            "anchor": settings.arena_season_anchor,
            "forced_restrictions": rules.forced_restrictions(),
            "forced_config": rules.forced_config(),
            "defaults": rules.default_config(),
            "tick_seconds": settings.arena_tick_seconds,
        },
    }


async def _queue_published_modules(db) -> list[str]:
    """Queue the current zip of every published module for the next rollover."""
    result = await db.execute(
        select(GameModule)
        .where(GameModule.status == ModuleStatus.PUBLISHED)
        .where(GameModule.file_name.is_not(None))
    )
    runtime = ArenaRuntime()
    queued = []
    for module in result.scalars().all():
        path = settings.modules_path / module.file_name
        if path.is_file():
            await asyncio.to_thread(runtime.queue_module, module.name, path)
            queued.append(module.name)
    return queued


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@router.get("/arena/modules", response_model=ArenaModulesResponse)
async def arena_modules(db: DbSession):
    """Modules the arena can field this season.

    A Digimon from any other module is refused at team creation.
    """
    season = await SeasonService(db).get_current_season()
    version = season.runtime_version if season else None
    try:
        catalog = await engine.catalog(version)
    except engine.EngineError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=str(exc)) from exc
    runtime_dir = engine.runtime_dir_for(version)
    return ArenaModulesResponse(
        runtime_version=runtime_dir.name,
        modules=[ArenaModuleResponse(**m) for m in catalog.get("modules", [])],
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class EndSeasonRequest(BaseModel):
    start_next: bool = True


@router.get("/admin/arena/status")
async def admin_arena_status(admin_user: AdminUser, db: DbSession):
    """Season, runtime and queued updates."""
    return await _status(db)


@router.post("/admin/arena/updates/omnipet")
async def admin_queue_omnipet(
    admin_user: AdminUser,
    file: UploadFile = File(...),
):
    """Queue an Omnipet build zip; it is installed when the season ends."""
    data = await file.read()
    try:
        path = await asyncio.to_thread(ArenaRuntime().queue_omnipet, data)
    except (RuntimeUpdateError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - e.g. a corrupt zip
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Not a usable zip: {exc}") from exc
    return {"queued": path.name, "pending": ArenaRuntime().pending()}


@router.post("/admin/arena/updates/sync-published")
async def admin_sync_published(admin_user: AdminUser, db: DbSession):
    """Queue every published module's current zip for the next rollover."""
    return {"queued": await _queue_published_modules(db), "pending": ArenaRuntime().pending()}


@router.post("/admin/arena/season/end")
async def admin_end_season(
    admin_user: AdminUser,
    db: DbSession,
    data: EndSeasonRequest | None = None,
):
    """End the running season now: ranks, prizes, queued updates, next season."""
    report = await SeasonService(db).tick(
        end_now=True, open_next=(data or EndSeasonRequest()).start_next, wait_for_lock=True)
    return {"report": report, "status": await _status(db)}


@router.post("/admin/arena/tick")
async def admin_tick(admin_user: AdminUser, db: DbSession):
    """Run the season clock once (what the background task does)."""
    return {"report": await SeasonService(db).tick(wait_for_lock=True)}


# ---------------------------------------------------------------------------
# Development only
# ---------------------------------------------------------------------------

async def _dev_access(
    db: DbSession,
    x_dev_token: Annotated[str | None, Header()] = None,
    x_device_key: Annotated[str | None, Header()] = None,
) -> None:
    """ENVIRONMENT=dev, and an admin's device key or the dev token."""
    if not settings.is_dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if settings.arena_dev_token and x_dev_token == settings.arena_dev_token:
        return
    user = await DeviceService(db).validate_secret_key(x_device_key) if x_device_key else None
    if user is None or not user.is_active or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Arena dev tools need an admin X-Device-Key (or X-Dev-Token)",
        )


DevAccess = Annotated[None, Depends(_dev_access)]


class DevSeasonStart(BaseModel):
    """Start a season right now."""

    length_hours: float = Field(1.0, gt=0, description="0.25 = fifteen minutes")
    name: str | None = None
    restrictions: SeasonRestrictions | None = None
    config: SeasonConfig | None = None
    end_current: bool = Field(True, description="Close the running season first")


class DevDummies(BaseModel):
    count: int = Field(10, ge=1, le=200)
    modules: list[str] | None = None
    seed: int | None = None


class DevBots(BaseModel):
    battles: int = Field(5, ge=1, le=500)
    seed: int | None = None


@router.get("/dev/arena/status")
async def dev_status(db: DbSession, _: DevAccess):
    return await _status(db)


@router.post("/dev/arena/season/start")
async def dev_start_season(data: DevSeasonStart, db: DbSession, _: DevAccess):
    """Close the running season (if asked) and open one of the given length.

    ``restrictions`` force the season's theme, e.g. {"allowed_stages": [3]};
    ``config`` its battle settings, e.g. {"attacks_per_day": 50, "charge": "random"}.
    """
    service = SeasonService(db)
    report = {}
    if data.end_current:
        report = await service.tick(end_now=True, open_next=False, wait_for_lock=True)
    elif await service.get_active_season() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A season is running; set end_current")
    season = await service.start_season_now(
        length_hours=data.length_hours,
        name=data.name,
        restrictions=data.restrictions.model_dump(exclude_none=True) if data.restrictions else None,
        config=data.config.model_dump(exclude_none=True) if data.config else None,
    )
    return {"report": report, "season": season_response(season)}


@router.post("/dev/arena/season/end")
async def dev_end_season(
    db: DbSession,
    _: DevAccess,
    data: EndSeasonRequest | None = None,
):
    """End the running season now (ranks, prizes, queued updates)."""
    report = await SeasonService(db).tick(
        end_now=True, open_next=(data or EndSeasonRequest()).start_next, wait_for_lock=True)
    return {"report": report, "status": await _status(db)}


@router.post("/dev/arena/runtime/apply")
async def dev_apply_runtime(db: DbSession, _: DevAccess):
    """Install queued updates now, mid-season (dev only: rules may change)."""
    report = await SeasonService(db).apply_runtime_updates()
    return {"report": report, "runtime": ArenaRuntime().current()}


@router.post("/dev/arena/updates/sync-published")
async def dev_sync_published(db: DbSession, _: DevAccess):
    return {"queued": await _queue_published_modules(db), "pending": ArenaRuntime().pending()}


@router.post("/dev/arena/dummies")
async def dev_dummies(data: DevDummies, db: DbSession, _: DevAccess):
    """Give dummy accounts random legal teams in the running season."""
    try:
        return await bots.create_dummy_teams(db, data.count, data.modules, data.seed)
    except (ValueError, engine.EngineError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/dev/arena/bots/run")
async def dev_bots(data: DevBots, db: DbSession, _: DevAccess):
    """Let dummy teams attack now (real matchmaking, limits and scoring)."""
    return await bots.run_bot_battles(db, data.battles, data.seed)
