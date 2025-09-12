"""add_game_participants_table

Revision ID: de5113c4c3e0
Revises: 8b55ced4fdeb
Create Date: 2025-09-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de5113c4c3e0'
down_revision: Union[str, Sequence[str], None] = '8b55ced4fdeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('game_participants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('chat_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('poll_end_time', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('game_participants')