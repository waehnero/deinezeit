"""Verkauf: Monatsabschluss und Übergabe an die Steuerberatung

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-01

Bisher gab es keinen Zeitpunkt, an dem ein Monat „zu" war. Nach der Übergabe
an die Steuerberatung ließ sich jederzeit noch ein Beleg mit Datum in diesem
Monat anlegen oder ändern, ohne dass irgendetwas gewarnt hätte — die übergebenen
Zahlen stimmten danach nicht mehr mit dem System überein.

1. ``accounting_periods`` — ein Eintrag je abgeschlossenem Kalendermonat.
   Solange kein Eintrag existiert, ist der Monat offen. Es wird also nichts
   vorab angelegt; ein Monat entsteht erst durch seinen Abschluss.

   Wiedereröffnen ist möglich, aber nur mit Begründung, und der Vorgang bleibt
   als Eintrag erhalten (``reopened_at``/``reopened_by``/``reopen_reason``).
   Ein spurloses Zurücknehmen soll es nicht geben.

2. ``period_handovers`` — je erzeugtem Übergabepaket ein Eintrag mit Zeitpunkt,
   Benutzer, Dateianzahl und SHA-256-Prüfsumme. Damit ist bei Rückfragen
   belegbar, was die Steuerberatung tatsächlich bekommen hat.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accounting_periods',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        # abgeschlossen | wieder_geoeffnet
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_by', sa.String(length=200), nullable=True),
        sa.Column('reopened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reopened_by', sa.String(length=200), nullable=True),
        sa.Column('reopen_reason', sa.String(length=500), nullable=True),
        # Kennzahlen zum Zeitpunkt des Abschlusses (Netto/Steuer/Brutto/Anzahl)
        sa.Column('totals', postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint('year', 'month', name='uq_accounting_period'),
    )
    op.create_index('ix_accounting_periods_jahr_monat',
                    'accounting_periods', ['year', 'month'])

    op.create_table(
        'period_handovers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(length=200), nullable=True),
        sa.Column('file_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('byte_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('checksum', sa.String(length=64), nullable=True),   # SHA-256
        sa.Column('note', sa.String(length=500), nullable=True),
    )
    op.create_index('ix_period_handovers_jahr_monat',
                    'period_handovers', ['year', 'month'])


def downgrade():
    op.drop_index('ix_period_handovers_jahr_monat', table_name='period_handovers')
    op.drop_table('period_handovers')
    op.drop_index('ix_accounting_periods_jahr_monat', table_name='accounting_periods')
    op.drop_table('accounting_periods')
