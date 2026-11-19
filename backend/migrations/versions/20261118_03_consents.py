"""Add versioned consent records."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_03'
down_revision = '20261118_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'consents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(16), nullable=False),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('granted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_consents_user_id', 'consents', ['user_id'])


def downgrade():
    op.drop_table('consents')
