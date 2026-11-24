"""admin console audit log

Revision ID: 20261122_16
Revises: 20261119_15
"""
from alembic import op
import sqlalchemy as sa

revision = '20261122_16'
down_revision = '20261119_15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('admin_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('admin_email', sa.String(128), nullable=True),
        sa.Column('admin_nickname', sa.String(64), nullable=True),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('target_type', sa.String(16), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_admin_audit_logs_created_at', 'admin_audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_admin_audit_logs_created_at', table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
