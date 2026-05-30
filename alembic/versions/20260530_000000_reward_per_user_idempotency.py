"""reward: per-user idempotency key, drop global unique

Revision ID: 20260530reward
Revises: 20260516_120000_add_day_night_and_high_res_to_shop_cosmetics
Create Date: 2026-05-30 00:00:00.000000

Changes:
- Drop the global unique index on reward_claims.idempotency_key
- Add composite unique constraint on (user_id, idempotency_key)
- Widen idempotency_key column from VARCHAR(64) to VARCHAR(256)
  (keys are now human-readable strings, not fixed-length SHA-256 hex)
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260530reward"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_reward_claims_idempotency_key")
    op.execute("ALTER TABLE reward_claims DROP CONSTRAINT IF EXISTS reward_claims_idempotency_key_key")
    op.execute("ALTER TABLE reward_claims ALTER COLUMN idempotency_key TYPE VARCHAR(256)")
    op.execute("""
        ALTER TABLE reward_claims
        ADD CONSTRAINT uq_reward_claims_user_key
        UNIQUE (user_id, idempotency_key)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE reward_claims DROP CONSTRAINT IF EXISTS uq_reward_claims_user_key")
    op.execute("ALTER TABLE reward_claims ALTER COLUMN idempotency_key TYPE VARCHAR(64)")
    op.execute("CREATE UNIQUE INDEX ix_reward_claims_idempotency_key ON reward_claims (idempotency_key)")
