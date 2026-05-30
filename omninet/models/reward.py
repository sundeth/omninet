"""
Reward claim tracking model.

Each row records one successful coin grant.  Duplicate claims are blocked by
a composite unique constraint on (user_id, idempotency_key): the same key can
appear for different users (e.g. two players both unlock the same module) but
cannot be reused by the same player.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from omninet.database import Base


class RewardClaim(Base):
    """Audit log + idempotency guard for in-game coin reward events."""

    __tablename__ = "reward_claims"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_reward_claims_user_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    coins_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<RewardClaim(user_id={self.user_id}, event={self.event_type}, "
            f"coins={self.coins_awarded})>"
        )
