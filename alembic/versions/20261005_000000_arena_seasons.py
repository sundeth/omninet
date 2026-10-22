"""arena seasons: datetimes, config, runtime snapshot, final ranks

Revision ID: 20261005arena
Revises: 20260530reward
Create Date: 2026-10-05 00:00:00.000000

Changes:
- seasons: starts_at / ends_at (TIMESTAMPTZ), config (JSON),
  runtime_version (VARCHAR(100)), prizes_paid (BOOLEAN)
- game_teams: final_rank (INTEGER), is_dummy (BOOLEAN)
- Backfill: existing seasons get starts_at = start_date 00:00 UTC and
  ends_at = the day after end_date 00:00 UTC; seasons already COMPLETED
  were paid by the old close logic, so they are marked prizes_paid.
- A season still ACTIVE from the old code is closed without prizes (its
  teams carry client-sent stats the arena engine cannot fight).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261005arena"
down_revision: str | None = "20260530reward"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE seasons ADD COLUMN IF NOT EXISTS starts_at TIMESTAMPTZ;
        ALTER TABLE seasons ADD COLUMN IF NOT EXISTS ends_at TIMESTAMPTZ;
        ALTER TABLE seasons ADD COLUMN IF NOT EXISTS config JSON;
        ALTER TABLE seasons ADD COLUMN IF NOT EXISTS runtime_version VARCHAR(100);
        ALTER TABLE seasons ADD COLUMN IF NOT EXISTS prizes_paid BOOLEAN NOT NULL DEFAULT false;
    """)
    op.execute("""
        UPDATE seasons
           SET starts_at = (start_date::timestamp AT TIME ZONE 'UTC')
         WHERE starts_at IS NULL;
        UPDATE seasons
           SET ends_at = ((end_date + 1)::timestamp AT TIME ZONE 'UTC')
         WHERE ends_at IS NULL;
        UPDATE seasons SET prizes_paid = true WHERE status = 'completed';
    """)
    # A season left ACTIVE by the old date-based code holds teams whose
    # stats the client sent; the new engine cannot fight them.  Close it
    # without prizes; the season clock opens a fresh one.
    op.execute("""
        UPDATE seasons
           SET status = 'completed', prizes_paid = true
         WHERE status = 'active' AND runtime_version IS NULL;
    """)
    op.execute("""
        ALTER TABLE game_teams ADD COLUMN IF NOT EXISTS final_rank INTEGER;
        ALTER TABLE game_teams ADD COLUMN IF NOT EXISTS is_dummy BOOLEAN NOT NULL DEFAULT false;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE game_teams DROP COLUMN IF EXISTS is_dummy;
        ALTER TABLE game_teams DROP COLUMN IF EXISTS final_rank;
        ALTER TABLE seasons DROP COLUMN IF EXISTS prizes_paid;
        ALTER TABLE seasons DROP COLUMN IF EXISTS runtime_version;
        ALTER TABLE seasons DROP COLUMN IF EXISTS config;
        ALTER TABLE seasons DROP COLUMN IF EXISTS ends_at;
        ALTER TABLE seasons DROP COLUMN IF EXISTS starts_at;
    """)
