"""add_price_and_sell_count_to_game_modules

Revision ID: f0eebeab7aea
Revises: 0000000000aa
Create Date: 2026-01-20 12:09:02.531382+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0eebeab7aea"
down_revision: str | None = "0000000000aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE game_modules
            ADD COLUMN IF NOT EXISTS price      INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS sell_count INTEGER NOT NULL DEFAULT 0;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE game_modules
            DROP COLUMN IF EXISTS sell_count,
            DROP COLUMN IF EXISTS price;
    """)
