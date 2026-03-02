"""add_price_and_sell_count_to_game_modules

Revision ID: f0eebeab7aea
Revises:
Create Date: 2026-01-20 12:09:02.531382+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0eebeab7aea"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
