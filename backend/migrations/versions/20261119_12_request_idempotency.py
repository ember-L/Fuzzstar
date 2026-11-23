"""request_idempotency（T14 浅离线幂等补发，FRD F07-5）。

Revision ID: 20261119_12
Revises: 20261119_11
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_12'
down_revision = '20261119_11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'request_idempotency',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint('user_id', 'key', name='uk_idempotency_user_key'),
    )
    op.create_index('ix_request_idempotency_user_id', 'request_idempotency', ['user_id'])


def downgrade() -> None:
    op.drop_table('request_idempotency')
