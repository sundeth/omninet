"""
Development-only dummy players.

Dummy accounts (``arenabot1``, ``arenabot2``, ...) get random but legal
teams built by the arena engine from the server's own modules, respecting
the running season's restrictions, and can attack on their own -- through
the same battle path a player uses -- so a whole season can be exercised in
minutes.  Nothing here may run outside the dev environment.
"""
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.arena import engine
from omninet.config import settings
from omninet.models.battle import GameTeam
from omninet.services.battle import BattleService
from omninet.services.season import SeasonService
from omninet.services.team import TEAM_SIZE, TeamService
from omninet.services.user import UserService

BOT_PREFIX = "arenabot"


def require_dev() -> None:
    if not settings.is_dev:
        raise PermissionError("Arena development tools are dev-only")


async def create_dummy_teams(
    db: AsyncSession,
    count: int = 10,
    modules: list[str] | None = None,
    seed: int | None = None,
) -> dict:
    """Give ``count`` dummy accounts a team in the running season.

    Accounts are reused across runs; an account that already has a team
    this season is skipped.
    """
    require_dev()
    season = await SeasonService(db).get_current_season()
    if season is None:
        raise ValueError("No arena season is running")
    user_service = UserService(db)
    team_service = TeamService(db)
    rng = random.Random(seed)
    created, skipped, failed = [], [], []

    for i in range(1, count + 1):
        nickname = f"{BOT_PREFIX}{i}"
        user = await user_service.get_by_nickname(nickname)
        if user is None:
            user = await user_service.create_user(
                nickname=nickname,
                email=f"{nickname}@dev.local",
                password="devdummy",
                type_name="Standard",
                is_verified=True,
                is_active=True,
            )
        if await team_service.get_user_current_team(user.id) is not None:
            skipped.append(nickname)
            continue
        answer = await engine.call(
            {
                "command": "random_team",
                "seed": rng.randrange(2**31),
                "restrictions": season.restrictions or {},
                "team_size": TEAM_SIZE,
                "modules": modules,
            },
            season.runtime_version,
        )
        ok, message, _team = await team_service.create_team(
            user=user,
            pets_data=answer["pets"],
            team_name=f"{nickname}'s squad",
            is_dummy=True,
        )
        (created if ok else failed).append(nickname if ok else f"{nickname}: {message}")

    await db.flush()
    return {"season": season.name, "created": created, "skipped": skipped, "failed": failed}


async def run_bot_battles(db: AsyncSession, battles: int = 5, seed: int | None = None) -> dict:
    """Let dummy teams with attacks left attack, up to *battles* times.

    Uses BattleService.find_battle, so the daily allowance, matchmaking and
    scoring are the real ones; dummies attack real players' teams too, which
    gives those players defences to watch.
    """
    require_dev()
    season = await SeasonService(db).get_current_season()
    if season is None:
        return {"battles": 0, "reason": "no season running"}
    result = await db.execute(
        select(GameTeam)
        .options(selectinload(GameTeam.owner))
        .where(GameTeam.season_id == season.id)
        .where(GameTeam.is_dummy.is_(True))
        .where(GameTeam.is_active.is_(True))
    )
    teams = list(result.scalars().all())
    rng = random.Random(seed)
    rng.shuffle(teams)
    service = BattleService(db)
    fought, outcomes = 0, []
    for team in teams:
        if fought >= battles:
            break
        ok, message, battle, _remaining = await service.find_battle(team.owner, team.id)
        if ok and battle is not None:
            fought += 1
            outcomes.append({"attacker": team.owner.nickname, "result": battle.result.value})
        else:
            outcomes.append({"attacker": team.owner.nickname, "skipped": message})
    await db.flush()
    return {"battles": fought, "season": season.name, "outcomes": outcomes}
