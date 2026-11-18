"""Add body type to pet profiles for placeholder group selection (FRD F03-4)."""

from alembic import op
import sqlalchemy as sa

revision = '20261119_08'
down_revision = '20261118_07'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pets', sa.Column('body_type', sa.String(16), nullable=False, server_default='standard'))


def downgrade():
    op.drop_column('pets', 'body_type')
