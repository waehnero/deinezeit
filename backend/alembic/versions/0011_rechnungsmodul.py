"""Rechnungsmodul: invoices, invoice_positions, invoice_attachments, invoice_settings

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03

Erstellt alle Tabellen für:
  - Rechnungen, Angebote, Gutschriften, Lieferscheine
  - Positionen (aus Artikel-Stammdaten oder Freitext)
  - Anhänge (lokaler Upload, Datacenter, externe Links)
  - Einstellungen (Bankverbindung, Nummerierung, MwSt.-Sätze)
  - Wiederkehrende Rechnungsvorlagen
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. invoices
    # -------------------------------------------------------------------------
    op.create_table(
        'invoices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Typ & Nummer
        sa.Column('doc_type', sa.String(20), nullable=False),       # rechnung | angebot | gutschrift | lieferschein
        sa.Column('number', sa.String(50), nullable=False, unique=True),  # RE-2026-001
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('sequence', sa.Integer, nullable=False),

        # Bezüge
        sa.Column('contact_id', UUID(as_uuid=True), nullable=True),        # entity_records.id (Kontakt)
        sa.Column('project_id', UUID(as_uuid=True), nullable=True),        # entity_records.id (Projekt)
        sa.Column('related_invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=True),  # Gutschrift → Original

        # Daten
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('date', sa.Date, nullable=False),
        sa.Column('due_date', sa.Date, nullable=True),
        sa.Column('delivery_date', sa.Date, nullable=True),
        sa.Column('reference', sa.String(200), nullable=True),          # Kundennummer/Bestellnummer
        sa.Column('intro_text', sa.Text, nullable=True),
        sa.Column('outro_text', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),                     # interne Notiz

        # MwSt.-Modus
        sa.Column('tax_mode', sa.String(30), nullable=False, server_default='per_position'),
        # per_position | single_rate | kleinunternehmer

        # Beträge (werden bei Speichern berechnet und gecacht)
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('tax_total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='EUR'),

        # Status
        sa.Column('status', sa.String(30), nullable=False, server_default='entwurf'),
        # entwurf | gesendet | offen | bezahlt | ueberfaellig | storniert | angenommen | abgelehnt
        sa.Column('cancel_mode', sa.String(20), nullable=True),         # status_only | with_credit
        sa.Column('paid_at', sa.Date, nullable=True),
        sa.Column('paid_amount', sa.Numeric(12, 2), nullable=True),

        # PDF-Vorlage (1–5)
        sa.Column('template_id', sa.Integer, nullable=False, server_default='1'),

        # Wiederkehrend
        sa.Column('is_recurring_template', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('recurring_interval', sa.String(20), nullable=True),  # weekly | monthly | quarterly | yearly
        sa.Column('recurring_next', sa.Date, nullable=True),
        sa.Column('recurring_action', sa.String(20), nullable=True),    # remind | create | create_and_send
        sa.Column('recurring_end', sa.Date, nullable=True),
        sa.Column('recurring_source_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=True),

        # Audit
        sa.Column('created_by', sa.String(200), nullable=True),
        sa.Column('updated_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_invoices_doc_type', 'invoices', ['doc_type'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_contact_id', 'invoices', ['contact_id'])
    op.create_index('ix_invoices_date', 'invoices', ['date'])
    op.create_index('ix_invoices_year_type', 'invoices', ['year', 'doc_type'])

    # -------------------------------------------------------------------------
    # 2. invoice_positions
    # -------------------------------------------------------------------------
    op.create_table(
        'invoice_positions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),

        # Artikel-Verknüpfung (optional — sonst Freitext)
        sa.Column('article_id', UUID(as_uuid=True), nullable=True),    # entity_records.id (Artikel)

        # Positionsdaten
        sa.Column('pos_type', sa.String(20), nullable=False, server_default='item'),
        # item | text | time_entry | discount | subtotal
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('detail', sa.Text, nullable=True),
        sa.Column('quantity', sa.Numeric(10, 4), nullable=False, server_default='1'),
        sa.Column('unit', sa.String(30), nullable=True),                # Stk, h, km, ...
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('discount_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('tax_rate', sa.Numeric(5, 2), nullable=True),         # 20.00 | 10.00 | 0.00 | null = reverse charge
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False, server_default='0'),

        # Zeiterfassung-Verknüpfung
        sa.Column('time_entry_id', UUID(as_uuid=True), nullable=True),  # time_entries.id

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_invoice_positions_invoice_id', 'invoice_positions', ['invoice_id'])

    # -------------------------------------------------------------------------
    # 3. invoice_attachments
    # -------------------------------------------------------------------------
    op.create_table(
        'invoice_attachments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attach_type', sa.String(20), nullable=False),        # upload | datacenter | external
        sa.Column('filename', sa.String(300), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=True),          # für upload
        sa.Column('datacenter_id', UUID(as_uuid=True), nullable=True),  # für datacenter
        sa.Column('url', sa.String(1000), nullable=True),               # für external
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('file_size', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_invoice_attachments_invoice_id', 'invoice_attachments', ['invoice_id'])

    # -------------------------------------------------------------------------
    # 4. invoice_number_sequences  (Zähler pro Typ+Jahr)
    # -------------------------------------------------------------------------
    op.create_table(
        'invoice_number_sequences',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('doc_type', sa.String(20), nullable=False),
        sa.Column('year', sa.Integer, nullable=False),
        sa.Column('last_sequence', sa.Integer, nullable=False, server_default='0'),
        sa.UniqueConstraint('doc_type', 'year', name='uq_invoice_seq_type_year'),
    )

    # -------------------------------------------------------------------------
    # 5. invoice_settings  (Bankdaten, MwSt.-Sätze, Standard-Texte etc.)
    # -------------------------------------------------------------------------
    op.create_table(
        'invoice_settings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('key', sa.String(100), nullable=False, unique=True),
        sa.Column('value', JSONB, nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Standard-Einstellungen befüllen
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO invoice_settings (key, value) VALUES
        ('bank', '{"iban": "", "bic": "", "bank": ""}'::jsonb),
        ('tax_rates', '[20, 10, 0]'::jsonb),
        ('default_tax_rate', '20'::jsonb),
        ('default_payment_days', '30'::jsonb),
        ('default_intro_rechnung', '"Wir erlauben uns, folgende Leistungen in Rechnung zu stellen:"'::jsonb),
        ('default_intro_angebot', '"Wir freuen uns, Ihnen folgendes Angebot zu unterbreiten:"'::jsonb),
        ('default_outro_rechnung', '"Wir bitten um Überweisung des Betrages innerhalb von 30 Tagen."'::jsonb),
        ('kleinunternehmer_text', '"Gemäß § 6 Abs. 1 Z 27 UStG wird keine Umsatzsteuer berechnet."'::jsonb),
        ('reverse_charge_text', '"Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)"'::jsonb),
        ('number_format_rechnung', '"RE-{year}-{seq:03d}"'::jsonb),
        ('number_format_angebot', '"AN-{year}-{seq:03d}"'::jsonb),
        ('number_format_gutschrift', '"GS-{year}-{seq:03d}"'::jsonb),
        ('number_format_lieferschein', '"LS-{year}-{seq:03d}"'::jsonb)
        ON CONFLICT (key) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_table('invoice_settings')
    op.drop_table('invoice_number_sequences')
    op.drop_table('invoice_attachments')
    op.drop_table('invoice_positions')
    op.drop_table('invoices')
