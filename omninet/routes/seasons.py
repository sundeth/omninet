"""
Season routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from omninet.arena import rules
from omninet.models.battle import Season, SeasonStatus, SeasonWinner
from omninet.routes.deps import AdminUser, DbSession, OptionalUser
from omninet.schemas.battle import (
    SeasonCreate,
    SeasonResponse,
    SeasonStandingResponse,
    SeasonWinnerResponse,
)
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


def winner_response(w: SeasonWinner) -> SeasonWinnerResponse:
    return SeasonWinnerResponse(
        season_id=w.season_id,
        season_name=w.season_name,
        rank=w.rank,
        user_id=w.user_id,
        nickname=w.nickname,
        score=w.score,
        wins=w.wins,
        losses=w.losses,
        draws=w.draws,
        prize_coins=w.prize_coins,
        pets=w.pets or [],
        created_at=w.created_at,
    )


@router.get("/{season_id}/winners", response_model=list[SeasonWinnerResponse])
async def get_season_winners(season_id: UUID, db: DbSession):
    """A finished season's podium (empty while it runs)."""
    result = await db.execute(
        select(SeasonWinner)
        .where(SeasonWinner.season_id == season_id)
        .order_by(SeasonWinner.rank.asc()))
    return [winner_response(w) for w in result.scalars().all()]


@router.get("/{season_id}/standings", response_model=list[SeasonStandingResponse])
async def get_season_standings(
    season_id: UUID,
    db: DbSession,
    current_user: OptionalUser = None,
    limit: int = Query(50, ge=1, le=500),
):
    """A season's table: live while it runs, final once it has closed."""
    service = SeasonService(db)
    season = await service.get_by_id(season_id)
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    teams = await service.ranked_teams(season)
    me = current_user.id if current_user else None
    rows = []
    for rank, team in enumerate(teams[:limit], start=1):
        rows.append(SeasonStandingResponse(
            rank=team.final_rank or rank,
            nickname=team.owner.nickname if team.owner else None,
            score=team.score,
            wins=team.wins,
            losses=team.losses,
            draws=team.draws,
            pets=[p.name for p in sorted(team.pets, key=lambda p: (p.extra_data or {}).get("slot", 0))],
            is_you=me is not None and team.owner_id == me,
        ))
    return rows


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
