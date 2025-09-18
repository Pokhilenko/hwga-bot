"""Initial Dota stats tables

Revision ID: 000000000001
Revises:
Create Date: 2025-09-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '000000000001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Reference
    op.create_table('heroes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name_slug', sa.Text(), nullable=False),
        sa.Column('localized_name', sa.Text(), nullable=False),
        sa.Column('primary_attr', sa.Text(), nullable=True),
        sa.Column('roles', sa.ARRAY(sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name_slug')
    )

    op.create_table('items',
        sa.Column('name_slug', sa.Text(), nullable=False),
        sa.Column('localized_name', sa.Text(), nullable=True),
        sa.Column('cost', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('name_slug')
    )

    # Matches and participants
    op.create_table('matches',
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('start_time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('duration_sec', sa.Integer(), nullable=True),
        sa.Column('radiant_win', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('match_id')
    )

    op.create_table('match_players',
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('steam32_id', sa.Integer(), nullable=False),
        sa.Column('hero_id', sa.Integer(), nullable=True),
        sa.Column('kills', sa.SmallInteger(), nullable=True),
        sa.Column('deaths', sa.SmallInteger(), nullable=True),
        sa.Column('assists', sa.SmallInteger(), nullable=True),
        sa.Column('is_radiant', sa.Boolean(), nullable=True),
        sa.Column('last_hits', sa.Integer(), nullable=True),
        sa.Column('gpm', sa.Integer(), nullable=True),
        sa.Column('xpm', sa.Integer(), nullable=True),
        sa.Column('lane_role', sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['matches.match_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['hero_id'], ['heroes.id'], ),
        sa.PrimaryKeyConstraint('match_id', 'steam32_id')
    )

    op.create_table('player_items',
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('steam32_id', sa.Integer(), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('item_slug', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['item_slug'], ['items.name_slug'], ),
        sa.PrimaryKeyConstraint('match_id', 'steam32_id', 'slot')
    )

    op.create_table('player_skills',
        sa.Column('match_id', sa.BigInteger(), nullable=False),
        sa.Column('steam32_id', sa.Integer(), nullable=False),
        sa.Column('order_idx', sa.SmallInteger(), nullable=False),
        sa.Column('ability_id', sa.Integer(), nullable=True),
        sa.Column('time_seconds', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('match_id', 'steam32_id', 'order_idx')
    )

    # Shadow tables for Telegram DB data
    op.create_table('ext_steam_links',
        sa.Column('steam32_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('steam32_id')
    )

    op.create_table('ext_chat_members',
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('chat_id', 'user_id')
    )

    # Indexes
    op.create_index('ix_match_players_steam32_id', 'match_players', ['steam32_id'], unique=False)
    op.create_index('ix_matches_start_time', 'matches', ['start_time'], unique=False)
    op.create_index('ix_ext_steam_links_steam32_id', 'ext_steam_links', ['steam32_id'], unique=False)
    op.create_index('ix_ext_chat_members_chat_id_user_id', 'ext_chat_members', ['chat_id', 'user_id'], unique=False)

    # Materialized View (to be refreshed on sync)
    # Note: This materialized view depends on data from the Telegram DB, which is external.
    # The ETL process should ensure ext_steam_links and ext_chat_members are up-to-date before refreshing this view.
    op.execute("""
        CREATE MATERIALIZED VIEW chat_party_matches AS
        SELECT
          m.match_id,
          ecm.chat_id,
          COUNT(*) FILTER (WHERE ecm.user_id IS NOT NULL) AS chat_players_count
        FROM matches m
        JOIN match_players mp USING (match_id)
        LEFT JOIN ext_steam_links esl ON esl.steam32_id = mp.steam32_id
        LEFT JOIN ext_chat_members ecm ON ecm.user_id = esl.user_id
        GROUP BY m.match_id, ecm.chat_id;
    """)

    op.create_unique_constraint('chat_party_matches_match_id_chat_id_idx', 'chat_party_matches', ['match_id', 'chat_id'])


def downgrade():
    op.drop_constraint('chat_party_matches_match_id_chat_id_idx', 'chat_party_matches', type='unique')
    op.drop_view('chat_party_matches')
    op.drop_index('ix_ext_chat_members_chat_id_user_id', table_name='ext_chat_members')
    op.drop_index('ix_ext_steam_links_steam32_id', table_name='ext_steam_links')
    op.drop_index('ix_matches_start_time', table_name='matches')
    op.drop_index('ix_match_players_steam32_id', table_name='match_players')
    op.drop_table('ext_chat_members')
    op.drop_table('ext_steam_links')
    op.drop_table('player_skills')
    op.drop_table('player_items')
    op.drop_table('match_players')
    op.drop_table('matches')
    op.drop_table('items')
    op.drop_table('heroes')
