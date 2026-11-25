"""remove email verification flow

Revision ID: 20261125_17
Revises: 20261122_16
"""

from alembic import op
import sqlalchemy as sa

revision = '20261125_17'
down_revision = '20261122_16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accounts registered before this change were stuck unverified; mark them
    # usable so nobody is locked out after the verification flow is removed.
    op.execute('UPDATE user_credentials SET verified_at = CURRENT_TIMESTAMP WHERE verified_at IS NULL')
    op.drop_table('verification_mail')
    with op.batch_alter_table('user_credentials') as batch:
        batch.drop_column('verification_hash')
        batch.drop_column('verification_expires_at')


def downgrade() -> None:
    with op.batch_alter_table('user_credentials') as batch:
        batch.add_column(sa.Column('verification_expires_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('verification_hash', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_user_credentials_verification_hash', ['verification_hash'])
    op.create_table(
        'verification_mail',
        sa.Column('credential_id', sa.Integer(), sa.ForeignKey('user_credentials.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('nonce', sa.String(48), nullable=False),
        sa.Column('queued_at', sa.DateTime(), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('failures', sa.Integer(), nullable=False),
    )
    op.create_index('ix_verification_mail_due_at', 'verification_mail', ['due_at'])
