"""contribution points: a second balance, its credits, Specials in either currency

Revision ID: 20261021contrib
Revises: 20261016arena
Create Date: 2026-10-21 00:00:00.000000

Changes:
- users.contribution_points (INTEGER, default 0): earned on the Digimon
  Database, kept apart from the coins.
- contribution_credits: one row per credit sent by the Database, unique by
  the sender's key (external_key), so a retried credit is never added twice;
  user_id NULL while no account has the email.
- shop_specials: currency ('coins' | 'contribution_points', default 'coins'),
  special_type, sprite_name, sort_order.
- user_purchases.currency (default 'coins'): which balance paid.

Additive only: a server still running the previous code keeps working
against the upgraded database.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20261021contrib"
down_revision: str | None = "20261016arena"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS contribution_points INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE shop_specials ADD COLUMN IF NOT EXISTS currency VARCHAR(32) NOT NULL DEFAULT 'coins';
        ALTER TABLE shop_specials ADD COLUMN IF NOT EXISTS special_type VARCHAR(50);
        ALTER TABLE shop_specials ADD COLUMN IF NOT EXISTS sprite_name VARCHAR(255);
        ALTER TABLE shop_specials ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE user_purchases ADD COLUMN IF NOT EXISTS currency VARCHAR(32) NOT NULL DEFAULT 'coins';
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contribution_credits (
            id UUID PRIMARY KEY,
            external_key VARCHAR(256) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            points INTEGER NOT NULL,
            source VARCHAR(64) NOT NULL,
            reason VARCHAR(64),
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            applied_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS ix_contribution_credits_email ON contribution_credits (email);
        CREATE INDEX IF NOT EXISTS ix_contribution_credits_user_id ON contribution_credits (user_id);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS contribution_credits;
        ALTER TABLE user_purchases DROP COLUMN IF EXISTS currency;
        ALTER TABLE shop_specials DROP COLUMN IF EXISTS sort_order;
        ALTER TABLE shop_specials DROP COLUMN IF EXISTS sprite_name;
        ALTER TABLE shop_specials DROP COLUMN IF EXISTS special_type;
        ALTER TABLE shop_specials DROP COLUMN IF EXISTS currency;
        ALTER TABLE users DROP COLUMN IF EXISTS contribution_points;
    """)
