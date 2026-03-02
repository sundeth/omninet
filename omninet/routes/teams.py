"""
Team management routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from omninet.routes.deps import CurrentUser, DbSession
from omninet.schemas.battle import (
    ClaimRewardResponse,
    PetResponse,
    TeamCreate,
    TeamListResponse,
    TeamResponse,
)
from omninet.schemas.common import MessageResponse
from omninet.services.team import TeamService

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("", response_model=list[TeamListResponse])
async def list_my_teams(
    current_user: CurrentUser,
    db: DbSession,
    include_past: bool = False,
):
    """List teams for the current user."""
    team_service = TeamService(db)
    teams = await team_service.get_user_teams(
        user_id=current_user.id,
        include_past_seasons=include_past,
        include_unclaimed_rewards=True,
    )

    return [
        TeamListResponse(
            id=t.id,
            name=t.name,
            score=t.score,
            wins=t.wins,
            losses=t.losses,
            draws=t.draws,
            pet_count=len(t.pets),
            reward_claimed=t.reward_claimed,
            season_name=t.season.name if t.season else None,
            created_at=t.created_at,
        )
        for t in teams
    ]


@router.get("/current", response_model=TeamResponse)
async def get_current_team(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get the current user's active team for this season."""
    team_service = TeamService(db)
    team = await team_service.get_user_current_team(current_user.id)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active team for current season",
        )

    return TeamResponse(
        id=team.id,
        name=team.name,
        score=team.score,
        wins=team.wins,
        losses=team.losses,
        draws=team.draws,
        rewarded_coins=team.rewarded_coins,
        reward_claimed=team.reward_claimed,
        is_active=team.is_active,
        season_id=team.season_id,
        season_name=team.season.name if team.season else None,
        pets=[
            PetResponse(
                id=p.id,
                name=p.name,
                module_name=p.module_name,
                module_version=p.module_version,
                pet_version=p.pet_version,
                stage=p.stage,
                level=p.level,
                atk_main=p.atk_main,
                atk_alt=p.atk_alt,
                atk_alt2=p.atk_alt2,
                power=p.power,
                attribute=p.attribute,
                hp=p.hp,
                star=p.star,
                critical_turn=p.critical_turn,
                extra_data=p.extra_data,
                created_at=p.created_at,
            )
            for p in team.pets
        ],
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get team details by ID."""
    team_service = TeamService(db)
    team = await team_service.get_by_id(team_id)

    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if team.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't own this team",
        )

    return TeamResponse(
        id=team.id,
        name=team.name,
        score=team.score,
        wins=team.wins,
        losses=team.losses,
        draws=team.draws,
        rewarded_coins=team.rewarded_coins,
        reward_claimed=team.reward_claimed,
        is_active=team.is_active,
        season_id=team.season_id,
        season_name=team.season.name if team.season else None,
        pets=[
            PetResponse(
                id=p.id,
                name=p.name,
                module_name=p.module_name,
                module_version=p.module_version,
                pet_version=p.pet_version,
                stage=p.stage,
                level=p.level,
                atk_main=p.atk_main,
                atk_alt=p.atk_alt,
                atk_alt2=p.atk_alt2,
                power=p.power,
                attribute=p.attribute,
                hp=p.hp,
                star=p.star,
                critical_turn=p.critical_turn,
                extra_data=p.extra_data,
                created_at=p.created_at,
            )
            for p in team.pets
        ],
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.post("", response_model=TeamResponse)
async def create_team(
    data: TeamCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Create a new team for the current season."""
    team_service = TeamService(db)

    # Convert pets to dictionaries
    pets_data = [pet.model_dump() for pet in data.pets]

    success, message, team = await team_service.create_team(
        user=current_user,
        pets_data=pets_data,
        team_name=data.name,
    )

    if not success or not team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return TeamResponse(
        id=team.id,
        name=team.name,
        score=team.score,
        wins=team.wins,
        losses=team.losses,
        draws=team.draws,
        rewarded_coins=team.rewarded_coins,
        reward_claimed=team.reward_claimed,
        is_active=team.is_active,
        season_id=team.season_id,
        season_name=team.season.name if team.season else None,
        pets=[
            PetResponse(
                id=p.id,
                name=p.name,
                module_name=p.module_name,
                module_version=p.module_version,
                pet_version=p.pet_version,
                stage=p.stage,
                level=p.level,
                atk_main=p.atk_main,
                atk_alt=p.atk_alt,
                atk_alt2=p.atk_alt2,
                power=p.power,
                attribute=p.attribute,
                hp=p.hp,
                star=p.star,
                critical_turn=p.critical_turn,
                extra_data=p.extra_data,
                created_at=p.created_at,
            )
            for p in team.pets
        ],
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.delete("/{team_id}", response_model=MessageResponse)
async def deactivate_team(
    team_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Deactivate a team."""
    team_service = TeamService(db)
    success, message = await team_service.deactivate_team(current_user, team_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return MessageResponse(message=message)


@router.post("/claim-rewards", response_model=ClaimRewardResponse)
async def claim_rewards(
    current_user: CurrentUser,
    db: DbSession,
):
    """Claim all pending rewards."""
    team_service = TeamService(db)
    coins_claimed, new_balance, teams_processed = await team_service.claim_rewards(
        current_user
    )

    if teams_processed == 0:
        return ClaimRewardResponse(
            coins_claimed=0,
            new_balance=new_balance,
            teams_processed=0,
            message="No rewards to claim",
        )

    return ClaimRewardResponse(
        coins_claimed=coins_claimed,
        new_balance=new_balance,
        teams_processed=teams_processed,
        message=f"Claimed {coins_claimed} coins from {teams_processed} team(s)",
    )
