"""deletion jobs, usage counters, plans and entitlements (T17)

Revision ID: 20261119_14
Revises: 20261119_13
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_14'
down_revision = '20261119_13'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'deletion_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('status', sa.String(16), server_default='pending', nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('purge_after', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_deletion_jobs_purge_after', 'deletion_jobs', ['purge_after'])
    op.create_table(
        'usage_counters',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('metric', sa.String(16), nullable=False),
        sa.Column('count', sa.Integer(), server_default='0', nullable=False),
        sa.UniqueConstraint('user_id', 'day', 'metric', name='uk_usage_user_day_metric'),
    )
    op.create_index('ix_usage_counters_user_id', 'usage_counters', ['user_id'])
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(32), nullable=False, unique=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('entitlements', sa.JSON(), nullable=False),
    )
    op.create_table(
        'entitlements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('plans.id'), nullable=False),
        sa.Column('status', sa.String(16), server_default='reserved', nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('entitlements')
    op.drop_table('plans')
    op.drop_table('usage_counters')
    op.drop_table('deletion_jobs')
