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
    # reward_claims was never created by a prior migration (only by create_all),
    # so we handle both cases in one DO block:
    #   - table absent  → CREATE it with the target schema
    #   - table present → ALTER from the old global-unique schema to the new
    #                     per-user composite unique schema
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'reward_claims'
            ) THEN
                CREATE TABLE reward_claims (
                    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    idempotency_key VARCHAR(256) NOT NULL,
                    event_type  VARCHAR(32) NOT NULL,
                    coins_awarded INTEGER    NOT NULL,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT uq_reward_claims_user_key UNIQUE (user_id, idempotency_key)
                );
                CREATE INDEX ix_reward_claims_user_id ON reward_claims (user_id);
                CREATE INDEX ix_reward_claims_idempotency_key ON reward_claims (idempotency_key);
            ELSE
                DROP INDEX IF EXISTS ix_reward_claims_idempotency_key;
                ALTER TABLE reward_claims
                    DROP CONSTRAINT IF EXISTS reward_claims_idempotency_key_key;
                ALTER TABLE reward_claims
                    ALTER COLUMN idempotency_key TYPE VARCHAR(256);
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_schema = 'public'
                      AND constraint_name = 'uq_reward_claims_user_key'
                ) THEN
                    ALTER TABLE reward_claims
                        ADD CONSTRAINT uq_reward_claims_user_key
                        UNIQUE (user_id, idempotency_key);
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'reward_claims'
            ) THEN
                ALTER TABLE reward_claims
                    DROP CONSTRAINT IF EXISTS uq_reward_claims_user_key;
                ALTER TABLE reward_claims
                    ALTER COLUMN idempotency_key TYPE VARCHAR(64);
                IF NOT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = 'reward_claims'
                      AND indexname = 'ix_reward_claims_idempotency_key'
                ) THEN
                    CREATE UNIQUE INDEX ix_reward_claims_idempotency_key
                        ON reward_claims (idempotency_key);
                END IF;
            END IF;
        END $$;
    """)
