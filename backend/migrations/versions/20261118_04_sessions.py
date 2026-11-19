"""Add rotating refresh-token sessions."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_04'
down_revision = '20261118_03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_sessions',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
                    sa.Column('revoked_at', sa.DateTime(), nullable=True))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_table('refresh_tokens',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('session_id', sa.Integer(), sa.ForeignKey('auth_sessions.id'), nullable=False),
                    sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
                    sa.Column('expires_at', sa.DateTime(), nullable=False),
                    sa.Column('used_at', sa.DateTime(), nullable=True))
    op.create_index('ix_refresh_tokens_session_id', 'refresh_tokens', ['session_id'])


def downgrade():
    op.drop_table('refresh_tokens')
    op.drop_table('auth_sessions')
