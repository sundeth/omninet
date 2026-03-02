"""
Season service for managing battle seasons.
"""
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.models.battle import Season, SeasonStatus, GamePet
from omninet.models.logs import ActivityType
from omninet.services.logging import LoggingService


class SeasonService:
    """Service for season-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)

    async def get_by_id(self, season_id: UUID) -> Optional[Season]:
        """Get season by ID."""
        query = select(Season).where(Season.id == season_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_current_season(self) -> Optional[Season]:
        """Get the currently active season."""
        today = date.today()
        query = (
            select(Season)
            .where(Season.status == SeasonStatus.ACTIVE)
            .where(Season.start_date <= today)
            .where(Season.end_date >= today)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_weekly_season(self) -> Season:
        """
        Get the current weekly season or create a new one.
        Weekly seasons run from Sunday to Saturday.
        """
        today = date.today()
        
        # Find start of current week (Sunday)
        days_since_sunday = today.weekday() + 1
        if days_since_sunday == 7:
            days_since_sunday = 0
        week_start = today - timedelta(days=days_since_sunday)
        week_end = week_start + timedelta(days=6)

        # Check if season exists for this week
        query = (
            select(Season)
            .where(Season.start_date == week_start)
            .where(Season.end_date == week_end)
        )
        result = await self.db.execute(query)
        season = result.scalar_one_or_none()

        if season:
            return season

        # Create new weekly season
        season = Season(
            name=f"Week of {week_start.strftime('%B %d, %Y')}",
            description="Weekly battle season",
            start_date=week_start,
            end_date=week_end,
            status=SeasonStatus.ACTIVE,
            reward_multiplier=1.0,
        )
        self.db.add(season)
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.SEASON_STARTED,
            target_id=season.id,
            target_type="season",
            description=f"Weekly season started: {season.name}",
        )

        return season

    async def create_season(
        self,
        name: str,
        start_date: date,
        end_date: date,
        description: Optional[str] = None,
        restrictions: Optional[dict] = None,
        reward_multiplier: float = 1.0,
        theme_name: Optional[str] = None,
        banner_url: Optional[str] = None,
    ) -> Season:
        """Create a new season."""
        # Determine initial status
        today = date.today()
        if start_date > today:
            status = SeasonStatus.UPCOMING
        elif end_date < today:
            status = SeasonStatus.COMPLETED
        else:
            status = SeasonStatus.ACTIVE

        season = Season(
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            status=status,
            restrictions=restrictions,
            reward_multiplier=reward_multiplier,
            theme_name=theme_name,
            banner_url=banner_url,
        )
        self.db.add(season)
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.SEASON_CREATED,
            target_id=season.id,
            target_type="season",
            description=f"Season created: {name}",
            log_metadata={"restrictions": restrictions},
        )

        return season

    async def update_season_statuses(self) -> None:
        """Update season statuses based on dates."""
        today = date.today()

        # Find seasons that should be active
        query = (
            select(Season)
            .where(Season.status == SeasonStatus.UPCOMING)
            .where(Season.start_date <= today)
        )
        result = await self.db.execute(query)
        for season in result.scalars().all():
            season.status = SeasonStatus.ACTIVE
            await self.logging_service.log_activity(
                activity_type=ActivityType.SEASON_STARTED,
                target_id=season.id,
                target_type="season",
                description=f"Season started: {season.name}",
            )

        # Find seasons that should be completed
        query = (
            select(Season)
            .where(Season.status == SeasonStatus.ACTIVE)
            .where(Season.end_date < today)
        )
        result = await self.db.execute(query)
        for season in result.scalars().all():
            season.status = SeasonStatus.COMPLETED
            await self.logging_service.log_activity(
                activity_type=ActivityType.SEASON_ENDED,
                target_id=season.id,
                target_type="season",
                description=f"Season ended: {season.name}",
            )

        await self.db.flush()

    async def list_seasons(
        self,
        status: Optional[SeasonStatus] = None,
        limit: int = 20,
    ) -> list[Season]:
        """List seasons with optional status filter."""
        query = select(Season)
        if status:
            query = query.where(Season.status == status)
        query = query.order_by(Season.start_date.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def is_pet_allowed_in_season(self, season: Season, pet: GamePet) -> bool:
        """Check if a pet is allowed in a season based on restrictions."""
        if not season.restrictions:
            return True

        restrictions = season.restrictions

        # Check stage restriction
        if "allowed_stages" in restrictions:
            if pet.stage not in restrictions["allowed_stages"]:
                return False

        # Check attribute restriction
        if "allowed_attributes" in restrictions:
            if pet.attribute not in restrictions["allowed_attributes"]:
                return False

        # Check module restriction
        if "allowed_modules" in restrictions:
            if pet.module_name not in restrictions["allowed_modules"]:
                return False

        return True


# Need to import timedelta
from datetime import timedelta
