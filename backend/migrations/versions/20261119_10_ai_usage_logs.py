"""ai_usage_logs: LLM 调用成本审计（T10；task_id 对齐 tasks 的 32 位 hex 主键）。

Revision ID: 20261119_10
Revises: 20261119_09
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_10'
down_revision = '20261119_09'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_usage_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('task_id', sa.String(length=32), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('media_seconds', sa.Float(), nullable=True),
        sa.Column('cost_est', sa.Numeric(10, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_ai_usage_logs_created_at', 'ai_usage_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_usage_logs_created_at', table_name='ai_usage_logs')
    op.drop_table('ai_usage_logs')
