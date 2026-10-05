"""
Season routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from omninet.arena import rules
from omninet.models.battle import Season, SeasonStatus
from omninet.routes.deps import AdminUser, DbSession
from omninet.schemas.battle import SeasonCreate, SeasonResponse
from omninet.services.season import SeasonService

router = APIRouter(prefix="/seasons", tags=["Seasons"])


def season_response(s: Season) -> SeasonResponse:
    return SeasonResponse(
        id=s.id,
        name=s.name,
        description=s.description,
        start_date=s.start_date,
        end_date=s.end_date,
        starts_at=s.starts_at,
        ends_at=s.ends_at,
        status=s.status,
        restrictions=s.restrictions,
        config=rules.season_config(s),
        runtime_version=s.runtime_version,
        reward_multiplier=s.reward_multiplier,
        theme_name=s.theme_name,
        banner_url=s.banner_url,
        created_at=s.created_at,
    )


@router.get("", response_model=list[SeasonResponse])
async def list_seasons(
    db: DbSession,
    status_filter: SeasonStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
):
    """List seasons with optional status filter."""
    season_service = SeasonService(db)
    seasons = await season_service.list_seasons(status=status_filter, limit=limit)
    return [season_response(s) for s in seasons]


@router.get("/current", response_model=SeasonResponse)
async def get_current_season(
    db: DbSession,
):
    """Get the running season (404 between seasons)."""
    season = await SeasonService(db).get_current_season()
    if season is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No arena season is running",
        )
    return season_response(season)


@router.get("/{season_id}", response_model=SeasonResponse)
async def get_season(
    season_id: UUID,
    db: DbSession,
):
    """Get season details by ID."""
    season_service = SeasonService(db)
    season = await season_service.get_by_id(season_id)

    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Season not found",
        )

    return season_response(season)


@router.post("", response_model=SeasonResponse)
async def create_season(
    data: SeasonCreate,
    admin_user: AdminUser,
    db: DbSession,
):
    """Schedule a season (admin only).

    It opens on the first season tick after ``starts_at`` once no other
    season is running; end the running one early with
    POST /admin/arena/season/end.
    """
    if data.ends_at <= data.starts_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ends_at must be after starts_at",
        )

    season = await SeasonService(db).create_season(
        name=data.name,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        description=data.description,
        restrictions=data.restrictions.model_dump(exclude_none=True) if data.restrictions else None,
        config=data.config.model_dump(exclude_none=True) if data.config else None,
        reward_multiplier=data.reward_multiplier,
        theme_name=data.theme_name,
        banner_url=data.banner_url,
    )
    return season_response(season)
