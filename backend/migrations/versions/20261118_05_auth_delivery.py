"""Persist verification deliveries and auth rate limits."""

from alembic import op
import sqlalchemy as sa

revision = '20261118_05'
down_revision = '20261118_04'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('verification_mail',
                    sa.Column('credential_id', sa.Integer(), sa.ForeignKey('user_credentials.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('nonce', sa.String(48), nullable=False),
                    sa.Column('queued_at', sa.DateTime(), nullable=False),
                    sa.Column('due_at', sa.DateTime(), nullable=True),
                    sa.Column('failures', sa.Integer(), nullable=False))
    op.create_index('ix_verification_mail_due_at', 'verification_mail', ['due_at'])
    op.create_table('auth_rate_buckets',
                    sa.Column('source_hash', sa.String(64), primary_key=True),
                    sa.Column('minute', sa.DateTime(), primary_key=True),
                    sa.Column('requests', sa.Integer(), nullable=False))
    op.create_index('ix_auth_rate_buckets_minute', 'auth_rate_buckets', ['minute'])


def downgrade():
    op.drop_table('auth_rate_buckets')
    op.drop_table('verification_mail')
