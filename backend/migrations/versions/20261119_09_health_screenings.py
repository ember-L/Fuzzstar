"""Health screening tables and video evidence media kind (FRD F05, ARCH 附录D)."""

from alembic import op
import sqlalchemy as sa

revision = '20261119_09'
down_revision = '20261119_08'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('media_uploads', sa.Column('kind', sa.String(8), nullable=False, server_default='photo'))
    op.create_table(
        'health_screenings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('redline_hit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('spirit', sa.String(16), nullable=False),
        sa.Column('appetite', sa.String(16), nullable=False),
        sa.Column('llm_advice', sa.Text(), nullable=True),
        sa.Column('advice_json', sa.JSON(), nullable=True),
        sa.Column('triage_json', sa.JSON(), nullable=False),
        sa.Column('rules_version', sa.String(32), nullable=False),
        sa.Column('task_id', sa.String(32), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_health_screenings_pet_time', 'health_screenings', ['pet_id', 'created_at'])
    op.create_table(
        'screening_symptoms',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('screening_id', sa.Integer(), sa.ForeignKey('health_screenings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('symptom_code', sa.String(32), nullable=False),
        sa.Column('duration', sa.String(8), nullable=False),
        sa.Column('frequency', sa.String(8), nullable=True),
        sa.Column('notes', sa.String(255), nullable=True),
        sa.Column('severe', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_screening_symptoms_screening_id', 'screening_symptoms', ['screening_id'])
    op.create_table(
        'screening_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('screening_id', sa.Integer(), sa.ForeignKey('health_screenings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('media_id', sa.String(32), sa.ForeignKey('media_uploads.id'), nullable=False),
        sa.Column('type', sa.String(8), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('screening_id', 'media_id', name='uk_screening_media'),
    )
    op.create_index('ix_screening_media_screening_id', 'screening_media', ['screening_id'])
    op.create_table(
        'health_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pet_id', sa.Integer(), sa.ForeignKey('pets.id'), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('severity', sa.String(16), nullable=False),
        sa.Column('score_delta', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_health_events_pet_active', 'health_events', ['pet_id', 'active'])


def downgrade():
    op.drop_table('health_events')
    op.drop_table('screening_media')
    op.drop_table('screening_symptoms')
    op.drop_table('health_screenings')
    op.drop_column('media_uploads', 'kind')
