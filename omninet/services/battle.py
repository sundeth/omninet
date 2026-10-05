"""
Battle service: arena battles.

A battle is fought by Omnipet's arena engine (OMNIPET rules with the DMX
default patterns) on the season's runtime snapshot.  The attacker is always
team1.  Both teams' scores move (win / loss / draw per the season config)
and both earn the participation coins; only attacks count against the
attacker's daily allowance.
"""
import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.arena import engine, rules
from omninet.models.battle import BattleResult, GameBattle, GameTeam, Season, SeasonStatus
from omninet.models.logs import ActivityType
from omninet.models.user import User
from omninet.services.logging import LoggingService
from omninet.services.season import utcnow
from omninet.services.team import TeamService, team_entries

#: Version of the stored battle_log (the game's battle.arena.replay reads it).
BATTLE_LOG_VERSION = 2

_RESULTS = {
    "device1": BattleResult.TEAM1_WIN,
    "device2": BattleResult.TEAM2_WIN,
    "draw": BattleResult.DRAW,
}


class BattleService:
    """Service for battle-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)
        self.team_service = TeamService(db)

    async def get_by_id(self, battle_id: UUID) -> GameBattle | None:
        """Get battle by ID."""
        query = (
            select(GameBattle)
            .options(
                selectinload(GameBattle.team1).selectinload(GameTeam.owner),
                selectinload(GameBattle.team1).selectinload(GameTeam.pets),
                selectinload(GameBattle.team2).selectinload(GameTeam.owner),
                selectinload(GameBattle.team2).selectinload(GameTeam.pets),
            )
            .where(GameBattle.id == battle_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_team_battles(
        self,
        team_id: UUID,
        limit: int = 50,
    ) -> list[GameBattle]:
        """Get battles for a team (attacks and defences)."""
        query = (
            select(GameBattle)
            .options(
                selectinload(GameBattle.team1).selectinload(GameTeam.owner),
                selectinload(GameBattle.team2).selectinload(GameTeam.owner),
            )
            .where(
                (GameBattle.team1_id == team_id) | (GameBattle.team2_id == team_id)
            )
            .order_by(GameBattle.fought_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def can_battle(self, team: GameTeam) -> tuple[bool, int]:
        """Whether *team* may attack now. Returns (can_battle, remaining_attacks)."""
        season = team.season
        if season is None or season.status != SeasonStatus.ACTIVE or (
                season.ends_at is not None and utcnow() >= season.ends_at):
            return False, 0
        allowance = rules.season_config(season)["attacks_per_day"]
        used = await self.team_service.count_attacks_today(team)
        remaining = allowance - used
        return remaining > 0, max(0, remaining)

    async def find_battle(
        self,
        user: User,
        team_id: UUID,
    ) -> tuple[bool, str, GameBattle | None, int]:
        """
        Find and execute a battle.
        Returns (success, message, battle, remaining_battles).
        """
        team = await self.team_service.get_by_id(team_id)
        if not team:
            return False, "Team not found", None, 0

        if team.owner_id != user.id:
            return False, "You don't own this team", None, 0

        if not team.is_active:
            return False, "Team is not active", None, 0

        season = team.season
        if season is None or season.status != SeasonStatus.ACTIVE or (
                season.ends_at is not None and utcnow() >= season.ends_at):
            return False, "This team's season has ended", None, 0

        can_fight, remaining = await self.can_battle(team)
        if not can_fight:
            return False, "Daily attack limit reached", None, 0

        opponent = await self.team_service.find_opponent(team, user.id)
        if not opponent:
            return False, "No opponent found", None, remaining

        try:
            battle = await self._execute_battle(team, opponent, season)
        except engine.EngineError as exc:
            return False, str(exc), None, remaining

        await self.logging_service.log_activity(
            activity_type=ActivityType.BATTLE_COMPLETED,
            user_id=user.id,
            target_id=battle.id,
            target_type="battle",
            description=f"Battle completed: {battle.result.value}",
            log_metadata={
                "team1_id": str(team.id),
                "team2_id": str(opponent.id),
                "result": battle.result.value,
            },
        )

        return True, "Battle completed", battle, remaining - 1

    async def _execute_battle(
        self,
        attacker: GameTeam,
        defender: GameTeam,
        season: Season,
    ) -> GameBattle:
        """Fight *attacker* (team1) against *defender* with the arena engine."""
        config = rules.season_config(season)
        seed = secrets.randbits(31)
        team1, team2 = team_entries(attacker), team_entries(defender)
        outcome = await engine.call(
            {
                "command": "battle",
                "team1": team1,
                "team2": team2,
                "seed": seed,
                "rules": {"charge": config["charge"]},
            },
            season.runtime_version,
        )
        result = _RESULTS[outcome["winner"]]

        winner_id = None
        if result == BattleResult.TEAM1_WIN:
            winner_id = attacker.id
            team1_change, team2_change = config["win_score"], config["loss_score"]
        elif result == BattleResult.TEAM2_WIN:
            winner_id = defender.id
            team1_change, team2_change = config["loss_score"], config["win_score"]
        else:
            team1_change = team2_change = config["draw_score"]

        battle_log: dict[str, Any] = {
            "version": BATTLE_LOG_VERSION,
            "engine_version": outcome.get("engine_version"),
            "runtime_version": season.runtime_version,
            "seed": seed,
            "rules": outcome.get("rules"),
            "charges": outcome.get("charges"),
            "attacker": _team_snapshot(attacker, team1),
            "defender": _team_snapshot(defender, team2),
            "hp": outcome["hp"],
            "winner": outcome["winner"],
            "result": outcome["result"],
        }
        turns = len(outcome["result"].get("battle_log", []))

        battle = GameBattle(
            team1_id=attacker.id,
            team2_id=defender.id,
            season_id=season.id,
            winner_id=winner_id,
            result=result,
            battle_log=battle_log,
            team1_score_change=team1_change,
            team2_score_change=team2_change,
            duration_seconds=turns * 3,
            fought_at=utcnow(),
        )
        self.db.add(battle)

        coins = config["participation_coins"]
        await self.team_service.update_team_score(
            attacker, team1_change,
            won=(result == BattleResult.TEAM1_WIN),
            draw=(result == BattleResult.DRAW),
            participation_coins=coins,
        )
        await self.team_service.update_team_score(
            defender, team2_change,
            won=(result == BattleResult.TEAM2_WIN),
            draw=(result == BattleResult.DRAW),
            participation_coins=coins,
        )

        await self.db.flush()
        await self.db.refresh(battle)

        return battle

    async def get_battle_history(
        self,
        user: User,
        team_id: UUID,
    ) -> tuple[bool, str, list[dict]]:
        """Get battle history for a team."""
        team = await self.team_service.get_by_id(team_id)
        if not team:
            return False, "Team not found", []

        if team.owner_id != user.id:
            return False, "You don't own this team", []

        battles = await self.get_team_battles(team_id)

        history = []
        for battle in battles:
            is_team1 = battle.team1_id == team_id
            opponent_team = battle.team2 if is_team1 else battle.team1
            score_change = (
                battle.team1_score_change if is_team1 else battle.team2_score_change
            )
            won = (battle.result == BattleResult.TEAM1_WIN and is_team1) or (
                battle.result == BattleResult.TEAM2_WIN and not is_team1)

            history.append({
                "id": battle.id,
                "opponent_team_id": opponent_team.id,
                "opponent_nickname": opponent_team.owner.nickname if opponent_team.owner else "Unknown",
                "role": "attack" if is_team1 else "defense",
                "won": won,
                "is_draw": battle.result == BattleResult.DRAW,
                "score_change": score_change,
                "fought_at": battle.fought_at,
            })

        return True, "Battle history retrieved", history


def _team_snapshot(team: GameTeam, entries: list[dict]) -> dict:
    """What a replay shows of one side."""
    return {
        "team_id": str(team.id),
        "nickname": team.owner.nickname if team.owner else None,
        "pets": [
            {key: entry.get(key) for key in (
                "module", "module_version", "name", "version", "index", "stage",
                "attribute", "level", "power", "hp", "atk_main", "atk_alt",
                "atk_alt_2", "traited", "shook")}
            for entry in entries
        ],
    }
