"""Zeiteinträge: Abrechnungs-/Sperrstatus je Eintrag

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-11

Neuer Workflow-Status auf time_entries:
  veraenderbar → gesperrt → freigegeben → abgerechnet

Bearbeiten/Löschen ist nur bei 'veraenderbar' möglich. So können auch
manuell (ohne Verkaufsbeleg) abgerechnete Zeiten gekennzeichnet und
geschützt werden.

Bestandsdaten: Einträge, auf die bereits eine Belegposition verweist,
werden auf 'abgerechnet' gesetzt — sie waren faktisch schon abgerechnet.
"""
from alembic import op
import sqlalchemy as sa

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('time_entries',
                  sa.Column('status', sa.String(length=20), nullable=False,
                            server_default='veraenderbar'))
    op.create_index('ix_time_entries_status', 'time_entries', ['status'])

    # Bestand: bereits über Verkaufsbeleg abgerechnete Einträge kennzeichnen
    op.execute("""
        UPDATE time_entries SET status = 'abgerechnet'
        WHERE id IN (
            SELECT time_entry_id FROM invoice_positions
            WHERE time_entry_id IS NOT NULL
        )
    """)


def downgrade():
    op.drop_index('ix_time_entries_status', table_name='time_entries')
    op.drop_column('time_entries', 'status')
