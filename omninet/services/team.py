"""
Team service for managing arena teams.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.arena import engine, rules
from omninet.config import settings
from omninet.models.battle import GameBattle, GamePet, GameTeam, Season, SeasonStatus
from omninet.models.logs import ActivityType
from omninet.models.user import User
from omninet.services.logging import LoggingService
from omninet.services.season import SeasonService, utcnow

#: Every arena team fields exactly this many Digimon (the engine's TEAM_SIZE).
TEAM_SIZE = 3


def team_entries(team: GameTeam) -> list[dict]:
    """The engine battle entries of *team*'s pets, in team order."""
    pets = sorted(team.pets, key=lambda p: (p.extra_data or {}).get("slot", 0))
    return [(p.extra_data or {}).get("arena_entry") for p in pets]


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

    async def get_team_rank(self, team: GameTeam) -> int:
        """Compute a team's 1-indexed rank within its season.

        Rank is by score desc, with ties broken by wins desc then created_at
        asc.  A finished season answers with the rank frozen at its close.
        Inactive teams or teams without a season return 0.
        """
        if team and team.final_rank:
            return team.final_rank
        if not team or not team.season_id or not team.is_active:
            return 0
        # Count teams strictly ahead of this one
        count_query = (
            select(func.count(GameTeam.id))
            .where(GameTeam.season_id == team.season_id)
            .where(GameTeam.is_active.is_(True))
            .where(
                or_(
                    GameTeam.score > team.score,
                    and_(
                        GameTeam.score == team.score,
                        GameTeam.wins > team.wins,
                    ),
                    and_(
                        GameTeam.score == team.score,
                        GameTeam.wins == team.wins,
                        GameTeam.created_at < team.created_at,
                    ),
                )
            )
        )
        result = await self.db.execute(count_query)
        ahead = result.scalar_one() or 0
        return ahead + 1

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
            current_season = await self.season_service.get_current_season()
            current_id = current_season.id if current_season else None
            if include_unclaimed_rewards:
                # Teams from the current season OR finished teams whose
                # results were not claimed yet
                query = query.where(
                    or_(
                        GameTeam.season_id == current_id,
                        GameTeam.reward_claimed.is_(False),
                    )
                )
            else:
                query = query.where(GameTeam.season_id == current_id)

        query = query.order_by(GameTeam.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_current_team(self, user_id: UUID) -> GameTeam | None:
        """Get user's team for the current season."""
        current_season = await self.season_service.get_current_season()
        if current_season is None:
            return None

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
        return result.scalars().first()

    async def count_user_current_teams(self, user_id: UUID, season: Season) -> int:
        """Count user's teams in *season*."""
        query = (
            select(func.count(GameTeam.id))
            .where(GameTeam.owner_id == user_id)
            .where(GameTeam.season_id == season.id)
            .where(GameTeam.is_active.is_(True))
        )
        result = await self.db.execute(query)
        return result.scalar_one()

    async def create_team(
        self,
        user: User,
        pets_data: list[dict],
        team_name: str | None = None,
        is_dummy: bool = False,
    ) -> tuple[bool, str, GameTeam | None]:
        """
        Create a new team for the current season.
        Returns (success, message, team).

        Each upload names a Digimon (module_name, name, pet_version) and
        carries its care ``status``.  The arena engine rebuilds it from the
        server's own module data -- refusing modules the server does not
        have -- and checks the season's restrictions.
        """
        season = await self.season_service.get_current_season()
        if season is None:
            return False, "No arena season is running", None

        current_teams = await self.count_user_current_teams(user.id, season)
        if current_teams >= settings.max_teams_per_user:
            return False, f"Maximum of {settings.max_teams_per_user} team(s) per season", None

        if len(pets_data) != TEAM_SIZE:
            return False, f"A team must have exactly {TEAM_SIZE} Digimon", None

        try:
            answer = await engine.call(
                {
                    "command": "validate_team",
                    "pets": pets_data,
                    "restrictions": season.restrictions or {},
                    "team_size": TEAM_SIZE,
                },
                season.runtime_version,
                raise_on_refusal=False,
            )
        except engine.EngineError as exc:
            return False, str(exc), None
        if not answer.get("ok"):
            errors = answer.get("errors") or []
            message = errors[0]["message"] if errors else answer.get("message", "Team refused")
            return False, message, None
        entries = answer["entries"]

        team = GameTeam(
            owner_id=user.id,
            season_id=season.id,
            name=team_name,
            is_active=True,
            is_dummy=is_dummy,
        )
        self.db.add(team)
        await self.db.flush()

        for slot, (entry, upload) in enumerate(zip(entries, pets_data)):
            self.db.add(GamePet(
                owner_id=user.id,
                team_id=team.id,
                name=entry["name"],
                module_name=entry["module"],
                module_version=entry["module_version"],
                pet_version=str(entry["version"]),
                stage=entry["stage"],
                level=entry["level"],
                atk_main=str(entry["atk_main"]),
                atk_alt=str(entry["atk_alt"]),
                atk_alt2=str(entry.get("atk_alt_2", 0)),
                power=entry["power"],
                attribute=entry["attribute"],
                hp=entry["hp"],
                star=1,
                critical_turn=0,
                extra_data={
                    "slot": slot,
                    "arena_entry": entry,
                    "upload": {
                        "module_version": upload.get("module_version"),
                        "status": upload.get("status"),
                    },
                },
            ))

        await self.db.flush()

        await self.logging_service.log_activity(
            activity_type=ActivityType.TEAM_CREATED,
            user_id=user.id,
            target_id=team.id,
            target_type="team",
            description=f"Team created with {len(entries)} pets",
            log_metadata={"season_id": str(season.id),
                          "runtime_version": season.runtime_version},
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
        Claim the results of every finished season.
        Returns (coins_claimed, new_balance, teams_processed).

        Only teams whose season has closed and paid its prizes qualify, so a
        claim can never come before the prize it should include.  A team
        that earned nothing is still marked claimed: its results were seen.
        """
        query = (
            select(GameTeam)
            .join(Season, GameTeam.season_id == Season.id)
            .where(GameTeam.owner_id == user.id)
            .where(GameTeam.reward_claimed.is_(False))
            .where(Season.status == SeasonStatus.COMPLETED)
            .where(Season.prizes_paid.is_(True))
        )
        result = await self.db.execute(query)
        teams = list(result.scalars().all())

        if not teams:
            return 0, user.coins, 0

        total_coins = sum(t.rewarded_coins for t in teams)

        for team in teams:
            team.reward_claimed = True

        user.coins += total_coins
        await self.db.flush()

        await self.logging_service.log_activity(
            activity_type=ActivityType.TEAM_REWARD_CLAIMED,
            user_id=user.id,
            description=f"Claimed {total_coins} coins from {len(teams)} teams",
            log_metadata={"coins": total_coins, "teams": len(teams)},
        )

        if total_coins:
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
        participation_coins: int | None = None,
    ) -> GameTeam:
        """Update team score after a battle.

        Coin policy: a small participation reward is added per battle
        regardless of outcome.  The headline rewards are paid out at
        season close to the top 3 teams (see SeasonService.close_season).
        """
        team.score += score_change
        if team.score < 0:
            team.score = 0

        if won:
            team.wins += 1
        elif draw:
            team.draws += 1
        else:
            team.losses += 1

        if participation_coins is None:
            participation_coins = settings.arena_participation_coins
        team.rewarded_coins += participation_coins

        await self.db.flush()
        return team

    async def count_attacks_today(self, team: GameTeam, now: datetime | None = None) -> int:
        """Attacks *team* made since today's allowance began.

        Defences do not count: being attacked never costs a team its own
        attacks.
        """
        now = now or utcnow()
        since = rules.attack_day_start(now, team.season.starts_at if team.season else None)
        result = await self.db.execute(
            select(func.count(GameBattle.id))
            .where(GameBattle.team1_id == team.id)
            .where(GameBattle.fought_at >= since)
        )
        return result.scalar_one()

    async def find_opponent(
        self,
        team: GameTeam,
        user_id: UUID,
        now: datetime | None = None,
    ) -> GameTeam | None:
        """A random team of the same season this team has not attacked today."""
        now = now or utcnow()
        since = rules.attack_day_start(now, team.season.starts_at if team.season else None)
        attacked_today = (
            select(GameBattle.team2_id)
            .where(GameBattle.team1_id == team.id)
            .where(GameBattle.fought_at >= since)
        )

        query = (
            select(GameTeam)
            .options(selectinload(GameTeam.pets), selectinload(GameTeam.owner))
            .where(GameTeam.season_id == team.season_id)
            .where(GameTeam.owner_id != user_id)  # Not own team
            .where(GameTeam.is_active.is_(True))
            .where(GameTeam.id.not_in(attacked_today))
            .order_by(func.random())  # Random selection
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


def team_season_ends_at(team: GameTeam) -> datetime | None:
    season = team.season
    if season is None:
        return None
    if season.ends_at is not None:
        return season.ends_at
    return datetime.combine(season.end_date, datetime.min.time(), tzinfo=UTC)
