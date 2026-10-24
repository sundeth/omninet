"""
Contribution points credited from outside the game (the Digimon Database).

Each row is one credit, named by the sender's own key (``external_key``, e.g.
``dbgather:DMC:812`` for contribution 812 of the Database's DMC ledger). The
key is unique, so a credit sent again -- a retry after a lost answer, a
backfill run twice -- is answered as a duplicate and never added twice.

A credit names an email, not an account. When an account has that email the
points go onto its ``contribution_points`` at once (``user_id`` and
``applied_at`` set); otherwise the row waits with ``user_id`` NULL and is
claimed when an account with that email next shows itself
(services/contribution.py ``claim_pending``).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from omninet.database import Base


class ContributionCredit(Base):
    """One credit of contribution points, idempotent by ``external_key``."""

    __tablename__ = "contribution_credits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    # Lowercased.
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    # Who sent it ("digimon-database") and why ("contribution", "data_needed").
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # What the sender says the credit is for (module, contribution id, target).
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # When the points reached an account; NULL while waiting for one.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (f"<ContributionCredit(key={self.external_key}, points={self.points}, "
                f"user_id={self.user_id})>")
