"""chat sessions and messages (T15)

Revision ID: 20261119_13
Revises: 20261119_12
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_13'
down_revision = '20261119_12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('chat_sessions.id'), nullable=False),
        sa.Column('role', sa.String(8), nullable=False),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('audio_url', sa.String(512), nullable=True),
        sa.Column('emotion_label', sa.String(32), nullable=True),
        sa.Column('emotion_confidence', sa.Numeric(4, 3), nullable=True),
        sa.Column('task_id', sa.String(32), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_chat_messages_session_time', 'chat_messages', ['session_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_chat_messages_session_time', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_table('chat_sessions')
