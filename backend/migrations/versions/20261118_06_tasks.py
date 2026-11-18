"""Persist pet task state and idempotency keys."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_06'
down_revision = '20261118_05'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tasks',
                    sa.Column('id', sa.String(32), primary_key=True),
                    sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
                    sa.Column('type', sa.String(24), nullable=False),
                    sa.Column('status', sa.String(16), nullable=False),
                    sa.Column('request_key', sa.String(64), nullable=False, unique=True),
                    sa.Column('payload', sa.JSON(), nullable=False),
                    sa.Column('result', sa.JSON(), nullable=True),
                    sa.Column('attempts', sa.Integer(), nullable=False),
                    sa.Column('lease_until', sa.DateTime(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False))
    op.create_index('ix_tasks_pet_id', 'tasks', ['pet_id'])


def downgrade():
    op.drop_table('tasks')
