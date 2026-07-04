"""Mail-Import: E-Mail nach Übernahme in Outlook als erledigt kennzeichnen

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-04

Erweiterung mail_accounts:
  - flag_erledigt  (nur Graph-Konten: nach Übernahme eines Vorschlags wird
    die Ursprungs-Mail per flagStatus=complete als erledigt markiert;
    benötigt die Applikationsberechtigung Mail.ReadWrite)
"""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('mail_accounts',
                  sa.Column('flag_erledigt', sa.Boolean(),
                            nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('mail_accounts', 'flag_erledigt')
