"""quota denial audit (T18)

Revision ID: 20261119_15
Revises: 20261119_14
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_15'
down_revision = '20261119_14'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'quota_denials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('metric', sa.String(16), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_quota_denials_day', 'quota_denials', ['day'])


def downgrade() -> None:
    op.drop_table('quota_denials')
