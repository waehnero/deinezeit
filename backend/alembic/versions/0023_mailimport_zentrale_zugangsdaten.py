"""Mail-Import: zentrale E-Mail-Zugangsdaten nutzbar

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-03

Erweiterung mail_accounts:
  - use_central_credentials  (Zugangsdaten aus Einstellungen -> System ->
    E-Mail verwenden: ms_tenant_id/ms_client_id/ms_client_secret für Graph
    bzw. smtp_user/smtp_password für IMAP)
"""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mail_accounts',
                  sa.Column('use_central_credentials', sa.Boolean(),
                            nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('mail_accounts', 'use_central_credentials')
