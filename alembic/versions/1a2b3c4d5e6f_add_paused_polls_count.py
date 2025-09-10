"""Add paused_polls_count to chat_settings

Revision ID: 1a2b3c4d5e6f
Revises: e91e32867611
Create Date: 2025-09-10 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'e91e32867611'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('chat_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('paused_polls_count', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('chat_settings', schema=None) as batch_op:
        batch_op.drop_column('paused_polls_count')
