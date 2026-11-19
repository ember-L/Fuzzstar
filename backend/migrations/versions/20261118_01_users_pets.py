"""Create the initial users and pets tables."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('nickname', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'pets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('species', sa.String(16), nullable=False),
        sa.Column('breed', sa.String(64), nullable=True),
        sa.Column('sex', sa.String(16), nullable=False),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('neutered', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pets_user_status', 'pets', ['user_id', 'status'])


def downgrade():
    op.drop_table('pets')
    op.drop_table('users')
