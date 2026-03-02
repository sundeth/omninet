"""
Activity logging service.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.models.logs import ActivityLog, ActivityType


class LoggingService:
    """Service for logging activities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_activity(
        self,
        activity_type: ActivityType,
        user_id: UUID | None = None,
        target_id: UUID | None = None,
        target_type: str | None = None,
        description: str | None = None,
        log_metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ActivityLog:
        """Log an activity."""
        log = ActivityLog(
            activity_type=activity_type,
            user_id=user_id,
            target_id=target_id,
            target_type=target_type,
            description=description,
            log_metadata=log_metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def get_user_activity(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """Get activity logs for a specific user."""
        query = (
            select(ActivityLog)
            .where(ActivityLog.user_id == user_id)
            .order_by(desc(ActivityLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_target_activity(
        self,
        target_id: UUID,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """Get activity logs for a specific target (module, team, etc.)."""
        query = select(ActivityLog).where(ActivityLog.target_id == target_id)
        if target_type:
            query = query.where(ActivityLog.target_type == target_type)
        query = query.order_by(desc(ActivityLog.created_at)).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_activity_by_type(
        self,
        activity_type: ActivityType,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
    ) -> list[ActivityLog]:
        """Get activity logs by type within a date range."""
        query = select(ActivityLog).where(ActivityLog.activity_type == activity_type)
        if start_date:
            query = query.where(ActivityLog.created_at >= start_date)
        if end_date:
            query = query.where(ActivityLog.created_at <= end_date)
        query = query.order_by(desc(ActivityLog.created_at)).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_recent_activity(
        self,
        limit: int = 100,
        activity_types: list[ActivityType] | None = None,
    ) -> list[ActivityLog]:
        """Get recent activity logs."""
        query = select(ActivityLog)
        if activity_types:
            query = query.where(ActivityLog.activity_type.in_(activity_types))
        query = query.order_by(desc(ActivityLog.created_at)).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
