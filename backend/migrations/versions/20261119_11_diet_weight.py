"""diet_records 与 weight_records（T12 建表；体重录入 API/UI 属 T13）。

Revision ID: 20261119_11
Revises: 20261119_10
"""
from alembic import op
import sqlalchemy as sa

revision = '20261119_11'
down_revision = '20261119_10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'diet_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
        sa.Column('food_type', sa.String(length=8), nullable=False),
        sa.Column('food_name', sa.String(length=64), nullable=True),
        sa.Column('amount_g', sa.Numeric(7, 1), nullable=False),
        sa.Column('kcal_est', sa.Numeric(7, 1), nullable=True),
        sa.Column('fed_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index('ix_diet_records_pet_time', 'diet_records', ['pet_id', 'fed_at'])
    op.create_table(
        'weight_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
        sa.Column('weight_kg', sa.Numeric(5, 2), nullable=False),
        sa.Column('measured_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_weight_records_pet_time', 'weight_records', ['pet_id', 'measured_at'])


def downgrade() -> None:
    op.drop_index('ix_weight_records_pet_time', table_name='weight_records')
    op.drop_table('weight_records')
    op.drop_index('ix_diet_records_pet_time', table_name='diet_records')
    op.drop_table('diet_records')
