"""add_matches_table

Revision ID: 8b55ced4fdeb
Revises: 1a2b3c4d5e6f
Create Date: 2025-09-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b55ced4fdeb'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('matches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('match_id', sa.String(), nullable=False),
        sa.Column('chat_id', sa.String(), nullable=False),
        sa.Column('winner', sa.String(), nullable=False),
        sa.Column('radiant_players', sa.String(), nullable=True),
        sa.Column('dire_players', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('matches')