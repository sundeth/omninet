"""
Season service: the arena season clock.

One season is ACTIVE at a time.  ``tick`` (run by a background task, and by
the admin/dev tools) does everything that happens at a season boundary, in
this order:

1. close the active season once ``ends_at`` has passed: final ranks, top-3
   prizes (credited once, claimable afterwards);
2. apply queued Omnipet/module updates to the arena runtime -- the only
   moment the battle rules may change;
3. open the next season: a scheduled (UPCOMING) one whose start has come,
   else an automatic one for the current schedule slot.

A Postgres advisory lock keeps two workers from doing this twice.
"""
import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.arena import rules
from omninet.arena.engine import verify_runtime
from omninet.arena.runtime import ArenaRuntime
from omninet.config import settings
from omninet.models.battle import GameTeam, Season, SeasonStatus
from omninet.models.logs import ActivityType
from omninet.services.logging import LoggingService

#: pg advisory lock key for the season clock (any constant bigint).
_SEASON_LOCK_KEY = 72026100501


def utcnow() -> datetime:
    return datetime.now(UTC)


def _end_date(ends_at: datetime) -> date:
    """The last calendar day a season covers ([starts_at, ends_at))."""
    return (ends_at - timedelta(microseconds=1)).date()


class SeasonService:
    """Service for season-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)

    # -- queries -------------------------------------------------------------

    async def get_by_id(self, season_id: UUID) -> Season | None:
        """Get season by ID."""
        query = select(Season).where(Season.id == season_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_active_season(self) -> Season | None:
        """The ACTIVE season (it may be past its end until the next tick)."""
        query = (
            select(Season)
            .where(Season.status == SeasonStatus.ACTIVE)
            .order_by(Season.starts_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_current_season(self, now: datetime | None = None) -> Season | None:
        """The season teams can join and fight in right now, or None."""
        season = await self.get_active_season()
        now = now or utcnow()
        if season is None or season.ends_at is None or now >= season.ends_at:
            return None
        return season

    async def list_seasons(
        self,
        status: SeasonStatus | None = None,
        limit: int = 20,
    ) -> list[Season]:
        """List seasons with optional status filter."""
        query = select(Season)
        if status:
            query = query.where(Season.status == status)
        query = query.order_by(Season.starts_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # -- creating ------------------------------------------------------------

    async def create_season(
        self,
        name: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str | None = None,
        restrictions: dict | None = None,
        config: dict | None = None,
        reward_multiplier: float = 1.0,
        theme_name: str | None = None,
        banner_url: str | None = None,
    ) -> Season:
        """Schedule a season.  It opens on the first tick after ``starts_at``
        when no other season is running."""
        season = Season(
            name=name,
            description=description,
            start_date=starts_at.date(),
            end_date=_end_date(ends_at),
            starts_at=starts_at,
            ends_at=ends_at,
            status=SeasonStatus.UPCOMING,
            restrictions=restrictions or None,
            config=rules.clean_config(config) or None,
            reward_multiplier=reward_multiplier,
            theme_name=theme_name,
            banner_url=banner_url,
        )
        self.db.add(season)
        await self.db.flush()

        await self.logging_service.log_activity(
            activity_type=ActivityType.SEASON_CREATED,
            target_id=season.id,
            target_type="season",
            description=f"Season created: {name}",
            log_metadata={"restrictions": restrictions, "config": config,
                          "starts_at": starts_at.isoformat(),
                          "ends_at": ends_at.isoformat()},
        )
        return season

    async def _activate(self, season: Season) -> None:
        manifest = ArenaRuntime().current()
        season.status = SeasonStatus.ACTIVE
        season.runtime_version = manifest["version"] if manifest else None
        await self.db.flush()
        await self.logging_service.log_activity(
            activity_type=ActivityType.SEASON_STARTED,
            target_id=season.id,
            target_type="season",
            description=f"Season started: {season.name}",
            log_metadata={"runtime_version": season.runtime_version,
                          "ends_at": season.ends_at.isoformat() if season.ends_at else None},
        )

    async def open_auto_season(self, now: datetime) -> Season:
        """An automatic season for the schedule slot containing *now*.

        It starts now (a slot already under way is joined part-way) and
        ends with the slot; ``arena_season_restrictions`` /
        ``arena_season_config`` are forced onto it.
        """
        length = rules.season_length()
        slot_start, slot_end = rules.auto_slot(now, length=length)
        season = await self.create_season(
            name=rules.auto_season_name(slot_start, now, length),
            starts_at=now,
            ends_at=slot_end,
            description="Automatic arena season",
            restrictions=rules.forced_restrictions() or None,
            config=rules.forced_config() or None,
        )
        await self._activate(season)
        return season

    async def start_season_now(
        self,
        length_hours: float,
        name: str | None = None,
        restrictions: dict | None = None,
        config: dict | None = None,
        now: datetime | None = None,
    ) -> Season:
        """Open a season immediately (development / admin).  The caller
        must have closed the running one first."""
        now = now or utcnow()
        ends_at = now + timedelta(hours=max(1 / 60, float(length_hours)))
        season = await self.create_season(
            name=name or f"Season {now:%b %d %H:%M} UTC",
            starts_at=now,
            ends_at=ends_at,
            description="Manually started arena season",
            restrictions=restrictions,
            config=config,
        )
        await self._activate(season)
        return season

    # -- closing -------------------------------------------------------------

    async def close_season(self, season: Season, now: datetime | None = None) -> list[tuple[UUID, int]]:
        """Complete *season*: final ranks, then the top-3 prizes.

        Prizes go to the three best teams that fought at least one battle,
        added to their ``rewarded_coins`` (claimed through
        /teams/claim-rewards) and only once: ``prizes_paid`` guards it.
        Ending early moves ``ends_at`` back to *now*.
        """
        now = now or utcnow()
        if season.ends_at is None or season.ends_at > now:
            season.ends_at = now
            season.end_date = _end_date(now)
        season.status = SeasonStatus.COMPLETED

        query = (
            select(GameTeam)
            .where(GameTeam.season_id == season.id)
            .where(GameTeam.is_active.is_(True))
            .order_by(GameTeam.score.desc(), GameTeam.wins.desc(), GameTeam.created_at.asc())
        )
        result = await self.db.execute(query)
        teams = list(result.scalars().all())
        for rank, team in enumerate(teams, start=1):
            team.final_rank = rank

        awarded: list[tuple[UUID, int]] = []
        if not season.prizes_paid:
            prizes = [
                settings.arena_first_place_coins,
                settings.arena_second_place_coins,
                settings.arena_third_place_coins,
            ]
            multiplier = season.reward_multiplier or 1.0
            # Only a team that fought (attacked or was attacked) can place.
            contenders = [t for t in teams if t.wins + t.losses + t.draws > 0]
            for rank, (team, prize) in enumerate(zip(contenders, prizes), start=1):
                prize = int(round(prize * multiplier))
                if prize <= 0:
                    continue
                team.rewarded_coins += prize
                awarded.append((team.id, prize))
                await self.logging_service.log_activity(
                    activity_type=ActivityType.TEAM_REWARD_CLAIMED,
                    user_id=team.owner_id,
                    target_id=team.id,
                    target_type="team",
                    description=f"Season top-{rank} prize: {prize} coins ({season.name})",
                    log_metadata={
                        "season_id": str(season.id),
                        "rank": rank,
                        "prize": prize,
                        "score": team.score,
                    },
                )
            season.prizes_paid = True

        await self.db.flush()
        await self.logging_service.log_activity(
            activity_type=ActivityType.SEASON_ENDED,
            target_id=season.id,
            target_type="season",
            description=f"Season ended: {season.name}",
            log_metadata={"teams": len(teams), "prizes": len(awarded)},
        )
        return awarded

    # -- the clock -----------------------------------------------------------

    async def _lock(self, wait: bool) -> bool:
        if wait:
            await self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"),
                                  {"k": _SEASON_LOCK_KEY})
            return True
        result = await self.db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"),
                                       {"k": _SEASON_LOCK_KEY})
        return bool(result.scalar())

    async def apply_runtime_updates(self) -> dict | None:
        """Apply queued Omnipet/module updates to the arena runtime now."""
        report = await asyncio.to_thread(ArenaRuntime().apply_pending, verify_runtime)
        if report:
            await self.logging_service.log_activity(
                activity_type=ActivityType.ADMIN_CONFIG_CHANGED,
                target_type="arena_runtime",
                description=("Arena runtime update rejected" if report.get("error")
                             else f"Arena runtime {report.get('version')} installed"),
                log_metadata=report,
            )
        return report

    async def tick(
        self,
        now: datetime | None = None,
        *,
        end_now: bool = False,
        open_next: bool = True,
        wait_for_lock: bool = False,
    ) -> dict:
        """Run the season clock once (see the module docstring).

        *end_now* closes the running season immediately (admin/dev);
        *open_next* False leaves the arena without a season afterwards.
        """
        now = now or utcnow()
        report: dict = {}
        if not await self._lock(wait_for_lock):
            return {"skipped": "another worker holds the season clock"}

        runtime = ArenaRuntime()
        if runtime.current() is None and runtime.has_pending():
            # First install: nothing is running yet, so there is no season
            # boundary to wait for.
            report["runtime"] = await self.apply_runtime_updates()

        active = await self.get_active_season()
        if active is not None and (end_now or active.ends_at is None or now >= active.ends_at):
            report["closed"] = {"id": str(active.id), "name": active.name,
                                "prizes": len(await self.close_season(active, now))}
            # Season boundary: the only moment the rules may change.
            if runtime.has_pending():
                report["runtime"] = await self.apply_runtime_updates()
            active = None

        # A season completed by an older version of this code, or by a crash
        # between the two steps, still owes its prizes.
        result = await self.db.execute(
            select(Season)
            .where(Season.status == SeasonStatus.COMPLETED)
            .where(Season.prizes_paid.is_(False))
        )
        for unpaid in result.scalars().all():
            await self.close_season(unpaid, now)

        if active is None and open_next:
            result = await self.db.execute(
                select(Season)
                .where(Season.status == SeasonStatus.UPCOMING)
                .where(Season.starts_at <= now)
                .order_by(Season.starts_at.asc())
            )
            for scheduled in result.scalars().all():
                if scheduled.ends_at and scheduled.ends_at <= now:
                    # Its whole window passed while another season ran.
                    scheduled.status = SeasonStatus.COMPLETED
                    scheduled.prizes_paid = True
                    continue
                await self._activate(scheduled)
                active = scheduled
                report["opened"] = {"id": str(scheduled.id), "name": scheduled.name}
                break
            if active is None and settings.arena_auto_seasons:
                if ArenaRuntime().current() is not None:
                    season = await self.open_auto_season(now)
                    report["opened"] = {"id": str(season.id), "name": season.name}
                else:
                    report["waiting"] = "no arena runtime installed"

        await self.db.flush()
        return report
