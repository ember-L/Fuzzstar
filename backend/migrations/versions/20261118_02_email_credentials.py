"""Add email credentials and single-use verification tokens."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_02'
down_revision = '20261118_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(16), nullable=False),
        sa.Column('identifier', sa.String(128), nullable=False),
        sa.Column('secret_hash', sa.String(255), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('verification_hash', sa.String(64), unique=True, nullable=True),
        sa.Column('verification_expires_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('type', 'identifier', name='uk_credential_type_identifier'),
    )
    op.create_index('ix_user_credentials_user_id', 'user_credentials', ['user_id'])


def downgrade():
    op.drop_table('user_credentials')
