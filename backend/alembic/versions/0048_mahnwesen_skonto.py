"""Verkauf: Mahnwesen und Skonto

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-04

Drei Bausteine:

1. **Tabelle ``invoice_dunnings``** — eine Zeile je verschickter Mahnung.
   Gebühr, Zinsen und der offene Betrag werden zum Mahnzeitpunkt
   **eingefroren**. Eine später eintreffende Teilzahlung darf nicht rückwirkend
   verändern, was im Mahnschreiben gestanden hat; das Schreiben ist raus.

2. **Felder am Beleg** — Mahnsperre (mit Begründung) sowie die erreichte
   Mahnstufe und das Datum der letzten Mahnung als Zwischenspeicher, damit
   Listen und Filter nicht für jeden Beleg die Historie laden müssen.
   Dazu die Skonto-Bedingung (Prozentsatz + Frist in Tagen).

3. **``payment_type`` an ``invoice_payments``** — ein gewährter Skonto schließt
   den Beleg wie eine Zahlung, ist aber **keine**: Er mindert das Entgelt und
   erfordert eine Umsatzsteuer-Berichtigung nach § 16 UStG. Buchhaltung und
   UVA müssen ihn deshalb unterscheiden können. Bestehende Einträge sind
   allesamt echte Zahlungen — daher der Vorgabewert ``zahlung``.

Ergänzend wird bei den Kontakten das Feld **Mahnsperre** im Register „Finanz"
angelegt (Kunde in Insolvenz, Ratenvereinbarung, laufende Klärung). Ohne dieses
Feld gäbe es die Sperre nur je Beleg — bei einem Kunden mit zwanzig offenen
Rechnungen wäre das unbrauchbar.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0048'
down_revision = '0047'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Mahnhistorie ────────────────────────────────────────────────────────
    op.create_table(
        'invoice_dunnings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=True),
        sa.Column('dunned_at', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('open_amount', sa.Numeric(12, 2), nullable=False,
                  server_default='0'),
        sa.Column('fee', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('interest', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('interest_rate', sa.Numeric(6, 3), nullable=True),
        sa.Column('interest_days', sa.Integer(), nullable=True),
        # Sammelmahnung: mehrere Belege eines Kunden auf einem Schreiben teilen
        # sich eine batch_id.
        sa.Column('batch_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_to', sa.String(length=300), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_invoice_dunnings_invoice_id', 'invoice_dunnings', ['invoice_id'])
    op.create_index('ix_invoice_dunnings_batch_id', 'invoice_dunnings', ['batch_id'])
    op.create_index('ix_invoice_dunnings_dunned_at', 'invoice_dunnings', ['dunned_at'])

    # 2. Felder am Beleg ─────────────────────────────────────────────────────
    op.add_column('invoices', sa.Column('dunning_blocked', sa.Boolean(),
                                        nullable=False, server_default=sa.false()))
    op.add_column('invoices', sa.Column('dunning_block_reason', sa.String(length=300),
                                        nullable=True))
    op.add_column('invoices', sa.Column('dunning_level', sa.Integer(),
                                        nullable=False, server_default='0'))
    op.add_column('invoices', sa.Column('dunning_last_at', sa.Date(), nullable=True))
    op.add_column('invoices', sa.Column('skonto_percent', sa.Numeric(5, 2), nullable=True))
    op.add_column('invoices', sa.Column('skonto_days', sa.Integer(), nullable=True))

    # 3. Zahlungsart ─────────────────────────────────────────────────────────
    op.add_column('invoice_payments', sa.Column('payment_type', sa.String(length=20),
                                                nullable=False, server_default='zahlung'))

    # 4. Kontaktfeld „Mahnsperre" im Register Finanz ─────────────────────────
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             show_in_list, sort_order, placeholder, tab)
        SELECT gen_random_uuid(), et.id,
               'Mahnsperre', 'mahnsperre', 'checkbox',
               false, false, 20, '', 'Finanz'
        FROM entity_types et
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd
              WHERE fd.entity_type_id = et.id AND fd.key = 'mahnsperre'
          )
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM field_definitions
        WHERE key = 'mahnsperre'
          AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
    """))
    op.drop_column('invoice_payments', 'payment_type')
    op.drop_column('invoices', 'skonto_days')
    op.drop_column('invoices', 'skonto_percent')
    op.drop_column('invoices', 'dunning_last_at')
    op.drop_column('invoices', 'dunning_level')
    op.drop_column('invoices', 'dunning_block_reason')
    op.drop_column('invoices', 'dunning_blocked')
    op.drop_index('ix_invoice_dunnings_dunned_at', table_name='invoice_dunnings')
    op.drop_index('ix_invoice_dunnings_batch_id', table_name='invoice_dunnings')
    op.drop_index('ix_invoice_dunnings_invoice_id', table_name='invoice_dunnings')
    op.drop_table('invoice_dunnings')
