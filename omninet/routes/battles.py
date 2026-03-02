"""
Battle routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from omninet.routes.deps import DbSession, CurrentUser
from omninet.schemas.battle import (
    BattleResponse,
    BattleHistoryResponse,
    BattleHistoryListResponse,
    FindBattleResponse,
)
from omninet.services.battle import BattleService
from omninet.services.team import TeamService

router = APIRouter(prefix="/battles", tags=["Battles"])


@router.get("/{battle_id}", response_model=BattleResponse)
async def get_battle(
    battle_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get battle details by ID (including full battle log)."""
    battle_service = BattleService(db)
    battle = await battle_service.get_by_id(battle_id)

    if not battle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Battle not found",
        )

    # Check if user owns one of the teams
    if (
        battle.team1.owner_id != current_user.id
        and battle.team2.owner_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't own either team in this battle",
        )

    return BattleResponse(
        id=battle.id,
        team1_id=battle.team1_id,
        team2_id=battle.team2_id,
        result=battle.result,
        winner_id=battle.winner_id,
        team1_score_change=battle.team1_score_change,
        team2_score_change=battle.team2_score_change,
        duration_seconds=battle.duration_seconds,
        fought_at=battle.fought_at,
        battle_log=battle.battle_log,
    )


@router.get("/team/{team_id}/history", response_model=BattleHistoryListResponse)
async def get_team_battle_history(
    team_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get battle history for a team."""
    battle_service = BattleService(db)
    team_service = TeamService(db)

    # Verify ownership
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

    success, message, history = await battle_service.get_battle_history(
        current_user, team_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return BattleHistoryListResponse(
        team_id=team_id,
        team_name=team.name,
        battles=[
            BattleHistoryResponse(
                id=h["id"],
                opponent_team_id=h["opponent_team_id"],
                opponent_nickname=h["opponent_nickname"],
                won=h["won"],
                score_change=h["score_change"],
                fought_at=h["fought_at"],
            )
            for h in history
        ],
        total_battles=len(history),
    )


@router.post("/find/{team_id}", response_model=FindBattleResponse)
async def find_battle(
    team_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Find and execute a battle for a team."""
    battle_service = BattleService(db)
    success, message, battle, remaining = await battle_service.find_battle(
        user=current_user,
        team_id=team_id,
    )

    if not success:
        return FindBattleResponse(
            battle_found=False,
            message=message,
            battle=None,
            daily_battles_remaining=remaining,
        )

    return FindBattleResponse(
        battle_found=True,
        message=message,
        battle=BattleResponse(
            id=battle.id,
            team1_id=battle.team1_id,
            team2_id=battle.team2_id,
            result=battle.result,
            winner_id=battle.winner_id,
            team1_score_change=battle.team1_score_change,
            team2_score_change=battle.team2_score_change,
            duration_seconds=battle.duration_seconds,
            fought_at=battle.fought_at,
            battle_log=battle.battle_log,
        ) if battle else None,
        daily_battles_remaining=remaining,
    )
