"""
Team service for managing game teams.
"""
from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.config import settings
from omninet.models.battle import GamePet, GameTeam
from omninet.models.logs import ActivityType
from omninet.models.user import User
from omninet.services.logging import LoggingService
from omninet.services.season import SeasonService


class TeamService:
    """Service for team-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)
        self.season_service = SeasonService(db)

    async def get_by_id(self, team_id: UUID) -> GameTeam | None:
        """Get team by ID with pets."""
        query = (
            select(GameTeam)
            .options(
                selectinload(GameTeam.pets),
                selectinload(GameTeam.owner),
                selectinload(GameTeam.season),
            )
            .where(GameTeam.id == team_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_teams(
        self,
        user_id: UUID,
        include_past_seasons: bool = False,
        include_unclaimed_rewards: bool = True,
    ) -> list[GameTeam]:
        """Get teams for a user."""
        query = (
            select(GameTeam)
            .options(
                selectinload(GameTeam.pets),
                selectinload(GameTeam.season),
            )
            .where(GameTeam.owner_id == user_id)
        )

        if not include_past_seasons:
            # Get current season
            current_season = await self.season_service.get_current_season()
            if current_season:
                if include_unclaimed_rewards:
                    # Include teams from current season OR teams with unclaimed rewards
                    query = query.where(
                        or_(
                            GameTeam.season_id == current_season.id,
                            and_(
                                GameTeam.reward_claimed.is_(False),
                                GameTeam.rewarded_coins > 0,
                            ),
                        )
                    )
                else:
                    query = query.where(GameTeam.season_id == current_season.id)

        query = query.order_by(GameTeam.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_current_team(self, user_id: UUID) -> GameTeam | None:
        """Get user's team for the current season."""
        current_season = await self.season_service.get_or_create_weekly_season()

        query = (
            select(GameTeam)
            .options(
                selectinload(GameTeam.pets),
                selectinload(GameTeam.season),
            )
            .where(GameTeam.owner_id == user_id)
            .where(GameTeam.season_id == current_season.id)
            .where(GameTeam.is_active.is_(True))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def count_user_current_teams(self, user_id: UUID) -> int:
        """Count user's teams in current season."""
        current_season = await self.season_service.get_or_create_weekly_season()

        query = (
            select(func.count(GameTeam.id))
            .where(GameTeam.owner_id == user_id)
            .where(GameTeam.season_id == current_season.id)
            .where(GameTeam.is_active.is_(True))
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def create_team(
        self,
        user: User,
        pets_data: list[dict],
        team_name: str | None = None,
    ) -> tuple[bool, str, GameTeam | None]:
        """
        Create a new team for the current season.
        Returns (success, message, team).
        """
        # Check team limit
        current_teams = await self.count_user_current_teams(user.id)
        if current_teams >= settings.max_teams_per_user:
            return False, f"Maximum of {settings.max_teams_per_user} team(s) per season", None

        # Get current season
        season = await self.season_service.get_or_create_weekly_season()

        # Validate pets count
        if len(pets_data) < 1 or len(pets_data) > 3:
            return False, "Team must have between 1 and 3 pets", None

        # Create team
        team = GameTeam(
            owner_id=user.id,
            season_id=season.id,
            name=team_name,
            is_active=True,
        )
        self.db.add(team)
        await self.db.flush()

        # Create pets
        for pet_data in pets_data:
            pet = GamePet(
                owner_id=user.id,
                team_id=team.id,
                name=pet_data.get("name", "Unknown"),
                module_name=pet_data.get("module_name", ""),
                module_version=pet_data.get("module_version", "1.0.0"),
                pet_version=pet_data.get("pet_version"),
                stage=pet_data.get("stage", 1),
                level=pet_data.get("level", 1),
                atk_main=pet_data.get("atk_main", ""),
                atk_alt=pet_data.get("atk_alt"),
                atk_alt2=pet_data.get("atk_alt2"),
                power=pet_data.get("power", 0),
                attribute=pet_data.get("attribute"),
                hp=pet_data.get("hp", 100),
                star=pet_data.get("star", 1),
                critical_turn=pet_data.get("critical_turn", 0),
                extra_data=pet_data.get("extra_data"),
            )

            # Validate pet against season restrictions
            if not self.season_service.is_pet_allowed_in_season(season, pet):
                return (
                    False,
                    f"Pet '{pet.name}' does not meet season restrictions",
                    None,
                )

            self.db.add(pet)

        await self.db.flush()
        await self.db.refresh(team)

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.TEAM_CREATED,
            user_id=user.id,
            target_id=team.id,
            target_type="team",
            description=f"Team created with {len(pets_data)} pets",
            metadata={"season_id": str(season.id)},
        )

        # Reload with relationships
        return True, "Team created successfully", await self.get_by_id(team.id)

    async def deactivate_team(self, user: User, team_id: UUID) -> tuple[bool, str]:
        """Deactivate a team."""
        team = await self.get_by_id(team_id)
        if not team:
            return False, "Team not found"

        if team.owner_id != user.id:
            return False, "You don't own this team"

        team.is_active = False
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.TEAM_DELETED,
            user_id=user.id,
            target_id=team.id,
            target_type="team",
            description="Team deactivated",
        )

        return True, "Team deactivated"

    async def claim_rewards(self, user: User) -> tuple[int, int, int]:
        """
        Claim all pending rewards for a user.
        Returns (coins_claimed, new_balance, teams_processed).
        """
        # Find teams with unclaimed rewards
        query = (
            select(GameTeam)
            .where(GameTeam.owner_id == user.id)
            .where(GameTeam.reward_claimed.is_(False))
            .where(GameTeam.rewarded_coins > 0)
        )
        result = await self.db.execute(query)
        teams = list(result.scalars().all())

        if not teams:
            return 0, user.coins, 0

        total_coins = sum(t.rewarded_coins for t in teams)

        # Claim rewards
        for team in teams:
            team.reward_claimed = True

        # Update user coins
        user.coins += total_coins
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.TEAM_REWARD_CLAIMED,
            user_id=user.id,
            description=f"Claimed {total_coins} coins from {len(teams)} teams",
            metadata={"coins": total_coins, "teams": len(teams)},
        )

        await self.logging_service.log_activity(
            activity_type=ActivityType.USER_COINS_EARNED,
            user_id=user.id,
            description=f"Earned {total_coins} coins from battle rewards",
            log_metadata={"amount": total_coins, "source": "battle_rewards"},
        )

        return total_coins, user.coins, len(teams)

    async def update_team_score(
        self,
        team: GameTeam,
        score_change: int,
        won: bool,
        draw: bool = False,
    ) -> GameTeam:
        """Update team score after a battle."""
        team.score += score_change
        if team.score < 0:
            team.score = 0

        if won:
            team.wins += 1
        elif draw:
            team.draws += 1
        else:
            team.losses += 1

        # Calculate reward coins (based on score)
        if won:
            team.rewarded_coins += max(10, score_change)
        elif draw:
            team.rewarded_coins += 5

        await self.db.flush()
        return team

    async def find_opponent(
        self,
        team: GameTeam,
        user_id: UUID,
    ) -> GameTeam | None:
        """Find a random opponent team that hasn't been matched yet today."""
        from omninet.models.battle import GameBattle

        today = date.today()

        # Get teams the user has already fought today
        subquery = (
            select(GameBattle.team2_id)
            .where(GameBattle.team1_id == team.id)
            .where(func.date(GameBattle.fought_at) == today)
        ).union(
            select(GameBattle.team1_id)
            .where(GameBattle.team2_id == team.id)
            .where(func.date(GameBattle.fought_at) == today)
        )

        # Find opponent from same season
        query = (
            select(GameTeam)
            .options(selectinload(GameTeam.pets), selectinload(GameTeam.owner))
            .where(GameTeam.season_id == team.season_id)
            .where(GameTeam.owner_id != user_id)  # Not own team
            .where(GameTeam.is_active.is_(True))
            .where(GameTeam.id.not_in(subquery))  # Not fought today
            .order_by(func.random())  # Random selection
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
