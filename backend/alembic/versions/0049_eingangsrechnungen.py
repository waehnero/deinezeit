"""Buchhaltung: Eingangsrechnungen und Vorsteuer

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-07

DeineZeit kannte bisher nur die Umsatzseite. Jede Umsatzsteuer-Auswertung trug
deshalb den Vermerk, dass die Vorsteuer fehlt und vor der Abgabe zu ergänzen
ist — eine Voranmeldung ließ sich damit nicht erstellen.

Drei Tabellen:

1. ``purchase_invoices`` — der Kopf. Bewusst OHNE Positionen: Eine
   Eingangsrechnung wird nie gedruckt, sie wird gebucht. Was Buchhaltung und
   Voranmeldung brauchen, sind Lieferant, Datum, Leistungsdatum, Aufwandskonto
   und die Beträge je Steuersatz. Artikelzeilen wären Tipparbeit ohne Empfänger.

   ``supplier_name`` friert den Lieferantennamen ein — analog zum
   Empfänger-Snapshot beim Verkaufsbeleg. Eine spätere Umbenennung oder eine
   DSGVO-Anonymisierung darf einen gebuchten Beleg nicht verändern.

   ``tax_kind`` unterscheidet die Fälle, die in der Voranmeldung verschiedene
   Kennzahlen belegen: normal, Reverse Charge (§ 19), innergemeinschaftlicher
   Erwerb, Einfuhr, ohne Vorsteuerabzug.

   ``vat_deductible`` trennt davon die Frage, ob die Vorsteuer überhaupt
   abziehbar ist (§ 12 UStG — z. B. PKW, Repräsentation). Beides ist nötig:
   Ein innergemeinschaftlicher Erwerb kann abziehbar sein oder nicht.

2. ``purchase_invoice_taxes`` — je Steuersatz eine Zeile mit Netto und
   Steuerbetrag. Der Steuerbetrag wird erfasst und NICHT gerechnet: Auf der
   Lieferantenrechnung steht ein bestimmter Betrag, und der gehört gebucht,
   auch wenn er um einen Cent von der eigenen Rundung abweicht.

3. ``purchase_payments`` — Zahlungsausgänge, Aufbau wie ``invoice_payments``.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'purchase_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        # Eigene laufende Nummer für die Ablage — die Rechnungsnummer des
        # Lieferanten taugt dafür nicht: Sie ist nicht eindeutig über alle
        # Lieferanten und folgt keiner Ordnung, die wir kennen.
        sa.Column('internal_number', sa.String(50), nullable=True, unique=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('sequence', sa.Integer(), nullable=True),

        sa.Column('supplier_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('supplier_name', sa.String(300), nullable=True),
        sa.Column('supplier_number', sa.String(100), nullable=True),   # Rechnungs-Nr. des Lieferanten
        sa.Column('supplier_uid', sa.String(50), nullable=True),

        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('delivery_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),

        # normal | reverse_charge | ig_erwerb | einfuhr | ohne_vorsteuer
        sa.Column('tax_kind', sa.String(20), nullable=False, server_default='normal'),
        sa.Column('vat_deductible', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('vat_note', sa.String(300), nullable=True),

        sa.Column('account_nr', sa.String(20), nullable=True),          # Aufwandskonto
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),

        sa.Column('net_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('tax_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('gross_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),

        # offen | teilbezahlt | bezahlt | storniert
        sa.Column('status', sa.String(20), nullable=False, server_default='offen'),
        sa.Column('paid_at', sa.Date(), nullable=True),
        sa.Column('paid_amount', sa.Numeric(12, 2), nullable=True),

        # Original als PDF/Bild im Objektspeicher
        sa.Column('file_key', sa.String(500), nullable=True),
        sa.Column('file_name', sa.String(300), nullable=True),
        sa.Column('file_mimetype', sa.String(100), nullable=True),

        sa.Column('created_by', sa.String(200), nullable=True),
        sa.Column('updated_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_purchase_invoices_date', 'purchase_invoices', ['date'])
    op.create_index('ix_purchase_invoices_supplier', 'purchase_invoices', ['supplier_id'])
    op.create_index('ix_purchase_invoices_status', 'purchase_invoices', ['status'])

    op.create_table(
        'purchase_invoice_taxes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('purchase_invoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('purchase_invoices.id', ondelete='CASCADE'), nullable=False),
        # NULL = kein Steuersatz (Reverse Charge auf der Eingangsseite)
        sa.Column('tax_rate', sa.Numeric(5, 2), nullable=True),
        sa.Column('net_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_purchase_invoice_taxes_beleg', 'purchase_invoice_taxes',
                    ['purchase_invoice_id'])

    op.create_table(
        'purchase_payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('purchase_invoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('purchase_invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('paid_at', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('method', sa.String(20), nullable=True),
        sa.Column('reference', sa.String(200), nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('created_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_purchase_payments_beleg', 'purchase_payments', ['purchase_invoice_id'])
    op.create_index('ix_purchase_payments_datum', 'purchase_payments', ['paid_at'])


def downgrade():
    op.drop_index('ix_purchase_payments_datum', table_name='purchase_payments')
    op.drop_index('ix_purchase_payments_beleg', table_name='purchase_payments')
    op.drop_table('purchase_payments')
    op.drop_index('ix_purchase_invoice_taxes_beleg', table_name='purchase_invoice_taxes')
    op.drop_table('purchase_invoice_taxes')
    op.drop_index('ix_purchase_invoices_status', table_name='purchase_invoices')
    op.drop_index('ix_purchase_invoices_supplier', table_name='purchase_invoices')
    op.drop_index('ix_purchase_invoices_date', table_name='purchase_invoices')
    op.drop_table('purchase_invoices')
