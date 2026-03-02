"""
Season routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from omninet.models.battle import SeasonStatus
from omninet.routes.deps import AdminUser, DbSession
from omninet.schemas.battle import SeasonCreate, SeasonResponse
from omninet.services.season import SeasonService

router = APIRouter(prefix="/seasons", tags=["Seasons"])


@router.get("", response_model=list[SeasonResponse])
async def list_seasons(
    db: DbSession,
    status_filter: SeasonStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
):
    """List seasons with optional status filter."""
    season_service = SeasonService(db)
    seasons = await season_service.list_seasons(status=status_filter, limit=limit)

    return [
        SeasonResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            start_date=s.start_date,
            end_date=s.end_date,
            status=s.status,
            restrictions=s.restrictions,
            reward_multiplier=s.reward_multiplier,
            theme_name=s.theme_name,
            banner_url=s.banner_url,
            created_at=s.created_at,
        )
        for s in seasons
    ]


@router.get("/current", response_model=SeasonResponse)
async def get_current_season(
    db: DbSession,
):
    """Get the currently active season."""
    season_service = SeasonService(db)
    season = await season_service.get_or_create_weekly_season()

    return SeasonResponse(
        id=season.id,
        name=season.name,
        description=season.description,
        start_date=season.start_date,
        end_date=season.end_date,
        status=season.status,
        restrictions=season.restrictions,
        reward_multiplier=season.reward_multiplier,
        theme_name=season.theme_name,
        banner_url=season.banner_url,
        created_at=season.created_at,
    )


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

    return SeasonResponse(
        id=season.id,
        name=season.name,
        description=season.description,
        start_date=season.start_date,
        end_date=season.end_date,
        status=season.status,
        restrictions=season.restrictions,
        reward_multiplier=season.reward_multiplier,
        theme_name=season.theme_name,
        banner_url=season.banner_url,
        created_at=season.created_at,
    )


@router.post("", response_model=SeasonResponse)
async def create_season(
    data: SeasonCreate,
    admin_user: AdminUser,
    db: DbSession,
):
    """Create a new season (admin only)."""
    season_service = SeasonService(db)

    # Validate dates
    if data.end_date <= data.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be after start date",
        )

    season = await season_service.create_season(
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        description=data.description,
        restrictions=data.restrictions.model_dump() if data.restrictions else None,
        reward_multiplier=data.reward_multiplier,
        theme_name=data.theme_name,
        banner_url=data.banner_url,
    )

    return SeasonResponse(
        id=season.id,
        name=season.name,
        description=season.description,
        start_date=season.start_date,
        end_date=season.end_date,
        status=season.status,
        restrictions=season.restrictions,
        reward_multiplier=season.reward_multiplier,
        theme_name=season.theme_name,
        banner_url=season.banner_url,
        created_at=season.created_at,
    )
