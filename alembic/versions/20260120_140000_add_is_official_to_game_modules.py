"""add_is_official_to_game_modules

Revision ID: a1b2c3d4e5f6
Revises: f0eebeab7aea
Create Date: 2026-01-20 14:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f0eebeab7aea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_official column with default value of False
    # Official modules are published by the game developers and may be offered
    # for free to new users as their first module
    op.add_column(
        "game_modules",
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Create index for quick lookup of official modules
    op.create_index("ix_game_modules_is_official", "game_modules", ["is_official"])


def downgrade() -> None:
    op.drop_index("ix_game_modules_is_official", table_name="game_modules")
    op.drop_column("game_modules", "is_official")
