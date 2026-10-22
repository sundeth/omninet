"""
Contribution points: credited by the Digimon Database, spent on Specials.

The Database sends one credit per contribution that carried an email
(routes/contributions.py). Each credit is named by the Database's own key, so
sending it again never adds the points twice. The email finds the account; a
credit for an email no account has yet is kept and claimed by the first
account that shows itself with that email (claim_pending, called where the
game reads the balance).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from omninet.models.contribution import ContributionCredit
from omninet.models.user import User

#: What credit() answers for one credit.
CREDITED = "credited"     # the account's balance went up
PENDING = "pending"       # kept: no account has the email yet
DUPLICATE = "duplicate"   # that key was credited before; nothing changed


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


class ContributionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(func.lower(User.email) == email)
        )
        return result.scalars().first()

    async def add_points(self, user: User, points: int) -> int:
        """Add (or, negative, take) points in one statement and return the
        new balance, so two requests at once cannot lose an update."""
        result = await self.db.execute(
            update(User)
            .where(User.id == user.id)
            .values(contribution_points=User.contribution_points + points)
            .returning(User.contribution_points)
            # The loaded User is set by hand below: synchronizing would expire
            # its updated_at (onupdate), a lazy load async code cannot do.
            .execution_options(synchronize_session=False)
        )
        balance = int(result.scalar_one())
        set_committed_value(user, "contribution_points", balance)
        return balance

    async def spend_points(self, user: User, points: int) -> int | None:
        """Take *points* if the balance covers them: the new balance, or None
        (nothing taken). One conditional statement, so a balance cannot be
        spent twice by two purchases at once."""
        result = await self.db.execute(
            update(User)
            .where(User.id == user.id, User.contribution_points >= points)
            .values(contribution_points=User.contribution_points - points)
            .returning(User.contribution_points)
            .execution_options(synchronize_session=False)
        )
        balance = result.scalar_one_or_none()
        if balance is None:
            return None
        set_committed_value(user, "contribution_points", int(balance))
        return int(balance)

    async def credit(
        self,
        key: str,
        email: str,
        points: int,
        source: str,
        reason: str | None = None,
        details: dict | None = None,
    ) -> tuple[str, ContributionCredit]:
        """Record one credit and, when an account has the email, add its
        points. Returns (CREDITED | PENDING | DUPLICATE, the credit row).

        Idempotent by *key*: a key seen before changes nothing. Runs in a
        savepoint, so a duplicate inserted by a concurrent request is
        answered as DUPLICATE without spoiling the rest of the batch."""
        email = normalize_email(email)
        existing = await self._by_key(key)
        if existing is not None:
            return DUPLICATE, existing

        user = await self._user_by_email(email)
        row = ContributionCredit(
            id=uuid.uuid4(), external_key=key, email=email, points=points,
            source=source, reason=reason, details=details,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(row)
                await self.db.flush()
                if user is not None:
                    await self.add_points(user, points)
                    row.user_id = user.id
                    row.applied_at = datetime.now(UTC)
                    await self.db.flush()
        except IntegrityError:
            existing = await self._by_key(key)
            if existing is None:
                raise
            return DUPLICATE, existing
        return (CREDITED if user is not None else PENDING), row

    async def _by_key(self, key: str) -> ContributionCredit | None:
        result = await self.db.execute(
            select(ContributionCredit).where(ContributionCredit.external_key == key)
        )
        return result.scalar_one_or_none()

    async def claim_pending(self, user: User) -> int:
        """Credits waiting for this account's email go onto its balance.
        Returns the points added (0 almost always: one indexed query)."""
        email = normalize_email(user.email)
        if not email:
            return 0
        result = await self.db.execute(
            update(ContributionCredit)
            .where(ContributionCredit.user_id.is_(None), ContributionCredit.email == email)
            .values(user_id=user.id, applied_at=datetime.now(UTC))
            .returning(ContributionCredit.points)
            .execution_options(synchronize_session=False)
        )
        points = sum(int(p) for p in result.scalars().all())
        if points:
            await self.add_points(user, points)
        return points

    async def balance_of(self, user: User) -> int:
        """The balance after claiming anything waiting for the account."""
        await self.claim_pending(user)
        return int(user.contribution_points or 0)
