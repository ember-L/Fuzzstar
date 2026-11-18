"""Persist owned photo upload tickets and verified object versions."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_07'
down_revision = '20261118_06'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('media_uploads',
                    sa.Column('id', sa.String(32), primary_key=True),
                    sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
                    sa.Column('content_type', sa.String(16), nullable=False),
                    sa.Column('size_bytes', sa.Integer(), nullable=False),
                    sa.Column('expires_at', sa.DateTime(), nullable=False),
                    sa.Column('version_id', sa.String(1024), nullable=True))
    op.create_index('ix_media_uploads_pet_id', 'media_uploads', ['pet_id'])


def downgrade():
    op.drop_table('media_uploads')
