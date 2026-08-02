"""Verkauf: Zahlungseingänge als eigene Tabelle (Teilzahlungen)

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-01

Bisher hatte ein Beleg genau zwei Zahlungsfelder: ``paid_at`` und
``paid_amount``. Damit war **eine** Zahlung abbildbar — nicht abbildbar waren
Teilzahlung, Ratenzahlung, Überzahlung, Skontoabzug und selbst die Korrektur
eines falsch erfassten Zahldatums.

1. Neue Tabelle ``invoice_payments`` — ein Eintrag je Zahlungseingang.

2. Bestandsdaten wandern verlustfrei mit: Jeder Beleg mit ``paid_at`` bekommt
   genau einen Zahlungseintrag über ``paid_amount`` (ersatzweise die
   Gesamtsumme, wenn kein Betrag hinterlegt war).

   ``paid_at`` und ``paid_amount`` BLEIBEN am Beleg — sie werden künftig aus
   den Zahlungen abgeleitet (Datum der letzten Zahlung, Summe aller Zahlungen)
   und dienen als Zwischenspeicher. So funktionieren PDF-Erzeugung, Export und
   DSGVO-Auswertung unverändert weiter, statt sie alle gleichzeitig umbauen zu
   müssen.

3. Neuer Belegstatus ``teilbezahlt``. Er wird nicht migriert — bestehende
   Belege sind entweder vollständig bezahlt oder offen.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invoice_payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('paid_at', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        # bank | bar | karte | lastschrift | verrechnung | sonstige
        sa.Column('method', sa.String(length=20), nullable=True),
        sa.Column('reference', sa.String(length=200), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_invoice_payments_invoice_id', 'invoice_payments', ['invoice_id'])
    op.create_index('ix_invoice_payments_paid_at', 'invoice_payments', ['paid_at'])

    # Bestandszahlungen übernehmen
    op.get_bind().execute(sa.text("""
        INSERT INTO invoice_payments (id, invoice_id, paid_at, amount, method, note, created_by)
        SELECT gen_random_uuid(), id, paid_at,
               COALESCE(paid_amount, total, 0), NULL,
               'Aus dem früheren Einzelfeld übernommen', updated_by
          FROM invoices
         WHERE paid_at IS NOT NULL
    """))


def downgrade():
    op.drop_index('ix_invoice_payments_paid_at', table_name='invoice_payments')
    op.drop_index('ix_invoice_payments_invoice_id', table_name='invoice_payments')
    op.drop_table('invoice_payments')
    # paid_at/paid_amount bleiben am Beleg erhalten — es geht nichts verloren.
    op.get_bind().execute(sa.text(
        "UPDATE invoices SET status = 'offen' WHERE status = 'teilbezahlt'"))
