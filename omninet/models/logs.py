"""
Activity logging model for tracking server events.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from omninet.database import Base


class ActivityType(enum.Enum):
    """Types of activities that can be logged."""

    # User activities
    USER_REGISTERED = "user_registered"
    USER_VERIFIED = "user_verified"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_DEVICE_ADDED = "user_device_added"
    USER_DEVICE_REMOVED = "user_device_removed"
    USER_PASSWORD_RESET = "user_password_reset"
    USER_COINS_EARNED = "user_coins_earned"
    USER_COINS_SPENT = "user_coins_spent"

    # Module activities
    MODULE_CREATED = "module_created"
    MODULE_UPDATED = "module_updated"
    MODULE_PUBLISHED = "module_published"
    MODULE_UNPUBLISHED = "module_unpublished"
    MODULE_BANNED = "module_banned"
    MODULE_DOWNLOADED = "module_downloaded"
    MODULE_CONTRIBUTOR_ADDED = "module_contributor_added"
    MODULE_CONTRIBUTOR_REMOVED = "module_contributor_removed"

    # Team activities
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_DELETED = "team_deleted"
    TEAM_REWARD_CLAIMED = "team_reward_claimed"

    # Battle activities
    BATTLE_STARTED = "battle_started"
    BATTLE_COMPLETED = "battle_completed"

    # Season activities
    SEASON_CREATED = "season_created"
    SEASON_STARTED = "season_started"
    SEASON_ENDED = "season_ended"

    # Admin activities
    ADMIN_USER_BANNED = "admin_user_banned"
    ADMIN_MODULE_BANNED = "admin_module_banned"
    ADMIN_CONFIG_CHANGED = "admin_config_changed"


class ActivityLog(Base):
    """Log of activities for auditing and history tracking."""

    __tablename__ = "activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    activity_type: Mapped[ActivityType] = mapped_column(
        Enum(ActivityType), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    target_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # user, module, team, battle, season
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<ActivityLog(type={self.activity_type}, user={self.user_id})>"
