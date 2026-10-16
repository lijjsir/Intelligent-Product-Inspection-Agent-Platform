"""Persist conversation pinning and distinguish automatic/manual titles."""
import sqlalchemy as sa
from alembic import op

revision = '0104_chat_session_preferences'
down_revision = '0103_quality_risk_realign'
branch_labels = depends_on = None


def upgrade():
    op.add_column('chat_sessions', sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('chat_sessions', sa.Column('title_source', sa.String(16), nullable=False, server_default='auto'))
    sessions = sa.table('chat_sessions', sa.column('title'), sa.column('title_source'))
    op.execute(sessions.update().where(
        sessions.c.title.is_not(None), sessions.c.title != '', sessions.c.title != '新对话',
        ~sessions.c.title.like('____-__-__ __:__'),
        ~sessions.c.title.like('________-____-____-____-____________'),
    ).values(title_source='manual'))


def downgrade():
    op.drop_column('chat_sessions', 'title_source')
    op.drop_column('chat_sessions', 'is_pinned')
