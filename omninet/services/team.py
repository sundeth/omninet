"""
Team service for managing arena teams.
"""
import json
import random
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.arena import engine, rules
from omninet.config import settings
from omninet.models.battle import GameBattle, GamePet, GameTeam, Season, SeasonStatus
from omninet.models.logs import ActivityType
from omninet.models.module import GameModule, ModuleStatus
from omninet.models.user import User
from omninet.services.logging import LoggingService
from omninet.services.season import SeasonService, standing_key, utcnow

#: The most Digimon an arena team fields (the battle has three lanes); a
#: season's config sets the allowed range (rules.season_config).
TEAM_SIZE = rules.TEAM_SIZE_LIMIT

#: pg advisory lock namespace for one team's attack allowance (any constant).
_ATTACK_LOCK_NS = 72026101


def team_entries(team: GameTeam) -> list[dict]:
    """The engine battle entries of *team*'s pets, in team order."""
    return [(p.extra_data or {}).get("arena_entry") for p in team_pets(team)]


def team_pets(team: GameTeam) -> list[GamePet]:
    """*team*'s pets in team order."""
    return sorted(team.pets, key=lambda p: (p.extra_data or {}).get("slot", 0))


async def published_module_names(db: AsyncSession) -> set[str]:
    """Names of the modules published on Omninet: the only ones that may
    field Digimon in the arena (the runtime may carry others)."""
    result = await db.execute(
        select(GameModule.name).where(GameModule.status == ModuleStatus.PUBLISHED))
    return {name for name in result.scalars().all() if name}


def _uid(upload: dict) -> str | None:
    uid = str(upload.get("uid") or "").strip()
    return uid or None


def _species(upload: dict) -> tuple[str, str]:
    """(name, version) of an upload, as GamePet rows store them."""
    version = upload.get("pet_version")
    try:
        version = str(int(version))
    except (TypeError, ValueError):
        version = str(version) if version is not None else ""
    return str(upload.get("name") or ""), version


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
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_team_rank(self, team: GameTeam) -> int:
        """Compute a team's 1-indexed rank within its season.

        The season table's order (``season.standing_key``): teams that have
        fought first, then score desc, wins desc and created_at asc -- the
        order the final ranks and prizes follow.  A finished season answers
        with the rank frozen at its close.  Inactive teams or teams without
        a season return 0.
        """
        if team and team.final_rank:
            return team.final_rank
        if not team or not team.season_id or not team.is_active:
            return 0
        result = await self.db.execute(
            select(GameTeam.id, GameTeam.score, GameTeam.wins, GameTeam.losses,
                   GameTeam.draws, GameTeam.created_at)
            .where(GameTeam.season_id == team.season_id)
            .where(GameTeam.is_active.is_(True))
        )
        rows = sorted(result.all(), key=standing_key)
        for rank, row in enumerate(rows, start=1):
            if row.id == team.id:
                return rank
        return 0

    async def count_season_teams(self, season_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(GameTeam.id))
            .where(GameTeam.season_id == season_id)
            .where(GameTeam.is_active.is_(True)))
        return result.scalar_one() or 0

    async def battle_split(self, team: GameTeam) -> dict:
        """Attacks made, defences fought and defences won by *team*."""
        result = await self.db.execute(
            select(
                func.count().filter(GameBattle.team1_id == team.id),
                func.count().filter(GameBattle.team2_id == team.id),
                func.count().filter(GameBattle.winner_id == team.id,
                                    GameBattle.team2_id == team.id),
            ).where(or_(GameBattle.team1_id == team.id, GameBattle.team2_id == team.id)))
        attacks, defences, defence_wins = result.one()
        return {"attacks": attacks or 0, "defences": defences or 0,
                "defence_wins": defence_wins or 0}

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

    async def _identity_problem(self, season: Season, pets_data: list[dict]) -> str | None:
        """Why a Digimon of this upload may not join *season*, or None.

        A Digimon (the game's ``uid``, kept through evolution) fights one
        season per species form: it may come back once it has evolved.  It
        cannot sit on two teams of the same season either.
        """
        uids = [_uid(p) for p in pets_data]
        known = [u for u in uids if u]
        if len(known) != len(set(known)):
            return "The same Digimon is on the team twice"
        if not known:
            return None
        result = await self.db.execute(
            select(GamePet, GameTeam, Season)
            .join(GameTeam, GamePet.team_id == GameTeam.id)
            .join(Season, GameTeam.season_id == Season.id)
            .where(GamePet.pet_uid.in_(known))
            .where(GameTeam.is_active.is_(True))
        )
        for pet, team, past in result.all():
            upload = next(p for p in pets_data if _uid(p) == pet.pet_uid)
            name, version = _species(upload)
            if past.id == season.id:
                return f"{name} is already on a team this season"
            if (pet.name, str(pet.pet_version or "")) == (name, version):
                return (f"{name} already fought in {past.name}. "
                        "It can return once it evolves.")
        return None

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
        carries its care ``status``; ``uid`` identifies the Digimon across
        seasons and ``pet_json`` is its full save copy, kept with the team.
        The arena engine rebuilds it from the server's own module data --
        refusing modules the server does not have, and species values that
        contradict the server's -- and checks the season's restrictions.
        Only published modules may field Digimon.
        """
        season = await self.season_service.get_current_season()
        if season is None:
            return False, "No arena season is running", None

        current_teams = await self.count_user_current_teams(user.id, season)
        if current_teams >= settings.max_teams_per_user:
            return False, f"Maximum of {settings.max_teams_per_user} team(s) per season", None

        config = rules.season_config(season)
        low, high = config["min_team_size"], config["max_team_size"]
        if not low <= len(pets_data) <= high:
            if low == high:
                return False, f"This season's teams have exactly {low} Digimon", None
            return False, f"This season's teams have {low} to {high} Digimon", None

        published = await published_module_names(self.db)
        for upload in pets_data:
            module_name = upload.get("module_name")
            if module_name not in published:
                return False, f"{module_name} is not a published module", None
            pet_json = upload.get("pet_json")
            if pet_json is not None and len(json.dumps(pet_json, default=str)) > settings.arena_pet_json_max_bytes:
                return False, f"{upload.get('name')}: save copy too large", None

        problem = await self._identity_problem(season, pets_data)
        if problem:
            return False, problem, None

        try:
            answer = await engine.call(
                {
                    "command": "validate_team",
                    "pets": pets_data,
                    "restrictions": season.restrictions or {},
                    "team_size": len(pets_data),
                    "min_team_size": low,
                    "max_team_size": high,
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
                pet_uid=_uid(upload),
                battles=0, wins=0, losses=0, draws=0,
                extra_data={
                    "slot": slot,
                    "arena_entry": entry,
                    "upload": {
                        "module_version": upload.get("module_version"),
                        "status": upload.get("status"),
                        "base": upload.get("base"),
                    },
                    "pet_json": upload.get("pet_json"),
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
        The teams are locked while they are marked, so two claims at once
        cannot pay the same coins twice.
        """
        query = (
            select(GameTeam)
            .join(Season, GameTeam.season_id == Season.id)
            .where(GameTeam.owner_id == user.id)
            .where(GameTeam.reward_claimed.is_(False))
            .where(Season.status == SeasonStatus.COMPLETED)
            .where(Season.prizes_paid.is_(True))
            .with_for_update(of=GameTeam)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(query)
        teams = list(result.scalars().all())

        if not teams:
            return 0, user.coins, 0

        total_coins = sum(t.rewarded_coins for t in teams)

        for team in teams:
            team.reward_claimed = True

        await self.db.execute(
            update(User).where(User.id == user.id).values(coins=User.coins + total_coins))
        await self.db.flush()
        await self.db.refresh(user, attribute_names=["coins"])

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

    async def record_battle(
        self,
        team: GameTeam,
        score_change: int,
        won: bool,
        draw: bool = False,
        participation_coins: int | None = None,
    ) -> None:
        """Add one battle's outcome to *team* and to each of its Digimon.

        Written as single UPDATE statements (score floored at 0) so battles
        that touch the same team at once -- it may defend against several
        attackers -- never lose each other's results.  Every Digimon on the
        team shares the team's outcome.

        Coin policy: a small participation reward is added per battle
        regardless of outcome.  The headline rewards are paid out at
        season close to the best teams (see SeasonService.close_season).
        """
        if participation_coins is None:
            participation_coins = settings.arena_participation_coins
        lost = not won and not draw
        await self.db.execute(
            update(GameTeam)
            .where(GameTeam.id == team.id)
            .values(
                score=func.greatest(0, GameTeam.score + score_change),
                wins=GameTeam.wins + int(won),
                losses=GameTeam.losses + int(lost),
                draws=GameTeam.draws + int(draw),
                rewarded_coins=GameTeam.rewarded_coins + participation_coins,
            )
        )
        await self.db.execute(
            update(GamePet)
            .where(GamePet.team_id == team.id)
            .values(
                battles=GamePet.battles + 1,
                wins=GamePet.wins + int(won),
                losses=GamePet.losses + int(lost),
                draws=GamePet.draws + int(draw),
            )
        )

    async def lock_attacks(self, team: GameTeam) -> None:
        """Hold *team*'s attack allowance until this transaction ends, so
        two attacks at once cannot both spend the last one."""
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, hashtext(:team))"),
            {"ns": _ATTACK_LOCK_NS, "team": str(team.id)})

    def _day_start(self, team: GameTeam, now: datetime) -> datetime:
        season = team.season
        config = rules.season_config(season) if season else {}
        return rules.attack_day_start(
            now, season.starts_at if season else None, config.get("day_minutes"))

    def next_attack_day(self, team: GameTeam, now: datetime | None = None) -> datetime:
        """When *team*'s next attack allowance begins."""
        now = now or utcnow()
        season = team.season
        config = rules.season_config(season) if season else {}
        return rules.next_attack_day(
            now, season.starts_at if season else None, config.get("day_minutes"))

    async def count_attacks_today(self, team: GameTeam, now: datetime | None = None) -> int:
        """Attacks *team* made since today's allowance began.

        Defences do not count: being attacked never costs a team its own
        attacks.
        """
        since = self._day_start(team, now or utcnow())
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
        rng: random.Random | None = None,
    ) -> GameTeam | None:
        """The fairest opponent for *team* among the other players' teams.

        Matchmaking spreads battles out instead of drawing at random:

        1. the teams *team* has attacked least today, so it fights every
           other team once before it fights anyone twice in a day;
        2. among those, the teams attacked least today by anyone, so no team
           is picked as a defender far more often than the others (a team
           that rarely attacks is not singled out for it);
        3. then the teams *team* has attacked least this season, and those
           attacked least this season, so the same pairs do not keep meeting
           day after day;
        4. then the closest team size; remaining ties are drawn at random.
        """
        now = now or utcnow()
        rng = rng or random.Random()
        since = self._day_start(team, now)

        result = await self.db.execute(
            select(GameTeam)
            .options(selectinload(GameTeam.pets), selectinload(GameTeam.owner))
            .where(GameTeam.season_id == team.season_id)
            .where(GameTeam.owner_id != user_id)  # Not own team
            .where(GameTeam.id != team.id)
            .where(GameTeam.is_active.is_(True))
        )
        candidates = list(result.scalars().all())
        if not candidates:
            return None

        result = await self.db.execute(
            select(GameBattle.team2_id, func.count(),
                   func.count().filter(GameBattle.fought_at >= since))
            .where(GameBattle.season_id == team.season_id)
            .where(GameBattle.team1_id == team.id)
            .group_by(GameBattle.team2_id)
        )
        attacked = {row[0]: (row[2], row[1]) for row in result.all()}

        result = await self.db.execute(
            select(GameBattle.team2_id, func.count(),
                   func.count().filter(GameBattle.fought_at >= since))
            .where(GameBattle.season_id == team.season_id)
            .group_by(GameBattle.team2_id)
        )
        defended = {row[0]: (row[2], row[1]) for row in result.all()}

        size = len(team.pets)

        def fairness(candidate: GameTeam) -> tuple:
            mine_today, mine_season = attacked.get(candidate.id, (0, 0))
            def_today, def_season = defended.get(candidate.id, (0, 0))
            return (mine_today, def_today, mine_season, def_season,
                    abs(len(candidate.pets) - size), rng.random())

        return min(candidates, key=fairness)


def team_season_ends_at(team: GameTeam) -> datetime | None:
    season = team.season
    if season is None:
        return None
    if season.ends_at is not None:
        return season.ends_at
    return datetime.combine(season.end_date, datetime.min.time(), tzinfo=UTC)
