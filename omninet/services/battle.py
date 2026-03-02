"""
Battle service for managing battles.
"""
import random
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.models.battle import GameBattle, GameTeam, GamePet, BattleResult
from omninet.models.user import User
from omninet.models.logs import ActivityType
from omninet.services.logging import LoggingService
from omninet.services.team import TeamService
from omninet.config import settings


class BattleService:
    """Service for battle-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)
        self.team_service = TeamService(db)

    async def get_by_id(self, battle_id: UUID) -> Optional[GameBattle]:
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
        limit: int = 20,
    ) -> list[GameBattle]:
        """Get battles for a team."""
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

    async def count_daily_battles(self, team_id: UUID) -> int:
        """Count battles fought by a team today."""
        today = date.today()
        query = (
            select(func.count(GameBattle.id))
            .where(
                (GameBattle.team1_id == team_id) | (GameBattle.team2_id == team_id)
            )
            .where(func.date(GameBattle.fought_at) == today)
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def can_battle(self, team_id: UUID) -> tuple[bool, int]:
        """Check if a team can battle. Returns (can_battle, remaining_battles)."""
        daily_battles = await self.count_daily_battles(team_id)
        remaining = settings.max_daily_battles - daily_battles
        return remaining > 0, max(0, remaining)

    async def find_battle(
        self,
        user: User,
        team_id: UUID,
    ) -> tuple[bool, str, Optional[GameBattle], int]:
        """
        Find and execute a battle.
        Returns (success, message, battle, remaining_battles).
        """
        # Get user's team
        team = await self.team_service.get_by_id(team_id)
        if not team:
            return False, "Team not found", None, 0

        if team.owner_id != user.id:
            return False, "You don't own this team", None, 0

        if not team.is_active:
            return False, "Team is not active", None, 0

        # Check daily battle limit
        can_fight, remaining = await self.can_battle(team_id)
        if not can_fight:
            return False, "Daily battle limit reached", None, 0

        # Find opponent
        opponent = await self.team_service.find_opponent(team, user.id)
        if not opponent:
            return False, "No opponent found", None, remaining

        # Execute battle
        battle = await self._execute_battle(team, opponent)

        # Log activity
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
        team1: GameTeam,
        team2: GameTeam,
    ) -> GameBattle:
        """Execute a battle between two teams."""
        # Run battle simulation
        result, battle_log, duration = self._simulate_battle(team1, team2)

        # Determine winner
        winner_id = None
        if result == BattleResult.TEAM1_WIN:
            winner_id = team1.id
        elif result == BattleResult.TEAM2_WIN:
            winner_id = team2.id

        # Calculate score changes
        base_score = 25
        if result == BattleResult.TEAM1_WIN:
            team1_change = base_score
            team2_change = -base_score // 2
        elif result == BattleResult.TEAM2_WIN:
            team1_change = -base_score // 2
            team2_change = base_score
        else:
            team1_change = 5
            team2_change = 5

        # Create battle record
        battle = GameBattle(
            team1_id=team1.id,
            team2_id=team2.id,
            season_id=team1.season_id,
            winner_id=winner_id,
            result=result,
            battle_log=battle_log,
            team1_score_change=team1_change,
            team2_score_change=team2_change,
            duration_seconds=duration,
        )
        self.db.add(battle)

        # Update team scores
        await self.team_service.update_team_score(
            team1, team1_change,
            won=(result == BattleResult.TEAM1_WIN),
            draw=(result == BattleResult.DRAW),
        )
        await self.team_service.update_team_score(
            team2, team2_change,
            won=(result == BattleResult.TEAM2_WIN),
            draw=(result == BattleResult.DRAW),
        )

        await self.db.flush()
        await self.db.refresh(battle)

        return battle

    def _simulate_battle(
        self,
        team1: GameTeam,
        team2: GameTeam,
    ) -> tuple[BattleResult, dict[str, Any], int]:
        """
        Simulate a battle between two teams.
        Returns (result, battle_log, duration_seconds).
        
        This is a simplified battle simulation. The actual game has
        a more complex battle system that could be ported here.
        """
        battle_log = {
            "version": "1.0",
            "team1": {
                "id": str(team1.id),
                "name": team1.name,
                "pets": [self._pet_to_dict(p) for p in team1.pets],
            },
            "team2": {
                "id": str(team2.id),
                "name": team2.name,
                "pets": [self._pet_to_dict(p) for p in team2.pets],
            },
            "rounds": [],
        }

        # Simple battle simulation based on total power
        team1_power = sum(p.power + p.hp + (p.level * 10) for p in team1.pets)
        team2_power = sum(p.power + p.hp + (p.level * 10) for p in team2.pets)

        # Add some randomness
        team1_score = team1_power + random.randint(-50, 50)
        team2_score = team2_power + random.randint(-50, 50)

        # Simulate rounds
        rounds = []
        t1_hp = team1_power
        t2_hp = team2_power
        round_num = 0

        while t1_hp > 0 and t2_hp > 0 and round_num < 20:
            round_num += 1

            # Team 1 attacks
            t1_damage = random.randint(10, 50) + (team1_power // 20)
            t2_hp -= t1_damage

            # Team 2 attacks
            t2_damage = random.randint(10, 50) + (team2_power // 20)
            t1_hp -= t2_damage

            rounds.append({
                "round": round_num,
                "team1_action": {
                    "type": "attack",
                    "damage": t1_damage,
                    "pet_index": round_num % len(team1.pets),
                },
                "team2_action": {
                    "type": "attack",
                    "damage": t2_damage,
                    "pet_index": round_num % len(team2.pets),
                },
                "team1_hp": max(0, t1_hp),
                "team2_hp": max(0, t2_hp),
            })

        battle_log["rounds"] = rounds
        battle_log["total_rounds"] = round_num

        # Determine result
        if t1_hp <= 0 and t2_hp <= 0:
            result = BattleResult.DRAW
            battle_log["winner"] = "draw"
        elif t1_hp > t2_hp:
            result = BattleResult.TEAM1_WIN
            battle_log["winner"] = str(team1.id)
        elif t2_hp > t1_hp:
            result = BattleResult.TEAM2_WIN
            battle_log["winner"] = str(team2.id)
        else:
            # Tie based on remaining HP, use initial power as tiebreaker
            if team1_score >= team2_score:
                result = BattleResult.TEAM1_WIN
                battle_log["winner"] = str(team1.id)
            else:
                result = BattleResult.TEAM2_WIN
                battle_log["winner"] = str(team2.id)

        # Estimate duration (2-3 seconds per round)
        duration = round_num * random.randint(2, 3)

        return result, battle_log, duration

    def _pet_to_dict(self, pet: GamePet) -> dict:
        """Convert pet to dictionary for battle log."""
        return {
            "id": str(pet.id),
            "name": pet.name,
            "module_name": pet.module_name,
            "stage": pet.stage,
            "level": pet.level,
            "power": pet.power,
            "hp": pet.hp,
            "attribute": pet.attribute,
            "atk_main": pet.atk_main,
            "atk_alt": pet.atk_alt,
            "atk_alt2": pet.atk_alt2,
            "star": pet.star,
        }

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

            won = False
            if battle.result == BattleResult.TEAM1_WIN and is_team1:
                won = True
            elif battle.result == BattleResult.TEAM2_WIN and not is_team1:
                won = True

            history.append({
                "id": battle.id,
                "opponent_team_id": opponent_team.id,
                "opponent_nickname": opponent_team.owner.nickname if opponent_team.owner else "Unknown",
                "won": won,
                "is_draw": battle.result == BattleResult.DRAW,
                "score_change": score_change,
                "fought_at": battle.fought_at,
            })

        return True, "Battle history retrieved", history
