"""add_price_and_sell_count_to_game_modules

Revision ID: f0eebeab7aea
Revises: 0000000000aa
Create Date: 2026-01-20 12:09:02.531382+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0eebeab7aea"
down_revision: str | None = "0000000000aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add price column with default value of 0
    op.add_column(
        "game_modules",
        sa.Column("price", sa.Integer(), nullable=False, server_default="0"),
    )
    # Add sell_count column with default value of 0
    op.add_column(
        "game_modules",
        sa.Column("sell_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("game_modules", "sell_count")
    op.drop_column("game_modules", "price")
