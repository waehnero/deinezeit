"""Verkauf: Belegnummer erst beim Finalisieren + Änderungsprotokoll

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-01

Hintergrund: § 11 Abs. 1 Z 3 UStG verlangt eine fortlaufende Belegnummer,
§ 131 BAO die lückenlose Aufzeichnung. Bisher bekam schon der Entwurf eine
Nummer — wurde er gelöscht, blieb eine unerklärliche Lücke im Nummernkreis.
Ab jetzt fällt die Nummer erst, wenn der Beleg den Entwurf verlässt.

1. invoices.number / year / sequence werden NULL-fähig.
   Entwürfe haben keine Nummer mehr. Der UNIQUE-Index auf `number` bleibt —
   PostgreSQL lässt beliebig viele NULL-Werte zu, jede vergebene Nummer
   bleibt also weiterhin eindeutig.

   BESTANDSDATEN werden bewusst NICHT angefasst: Vorhandene Entwürfe behalten
   ihre bereits vergebene Nummer. Sie wieder freizugeben würde bedeuten, dass
   ein zweiter Beleg dieselbe Nummer bekommt — genau das soll nicht passieren.

2. Neue Tabelle invoice_audit_log — Änderungsprotokoll je Beleg.
   Aufbau angelehnt an gdpr_deletion_log: eine Zeile je Vorgang, die
   Feldänderungen liegen als JSONB darin.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Nummer, Jahr und laufende Nummer dürfen leer sein (Entwürfe)
    op.alter_column('invoices', 'number',
                    existing_type=sa.String(length=50), nullable=True)
    op.alter_column('invoices', 'year',
                    existing_type=sa.Integer(), nullable=True)
    op.alter_column('invoices', 'sequence',
                    existing_type=sa.Integer(), nullable=True)

    # 2. Änderungsprotokoll
    op.create_table(
        'invoice_audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('changes', postgresql.JSONB(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('changed_by', sa.String(length=200), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.create_index('ix_invoice_audit_log_invoice_id',
                    'invoice_audit_log', ['invoice_id'])


def downgrade():
    op.drop_index('ix_invoice_audit_log_invoice_id', table_name='invoice_audit_log')
    op.drop_table('invoice_audit_log')

    # Zurück auf NOT NULL: Entwürfe ohne Nummer bekommen einen Platzhalter,
    # sonst schlägt die Umstellung fehl.
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE invoices
           SET number   = 'ENTWURF-' || left(id::text, 8),
               year     = COALESCE(year, EXTRACT(YEAR FROM date)::int),
               sequence = COALESCE(sequence, 0)
         WHERE number IS NULL
    """))
    op.alter_column('invoices', 'sequence',
                    existing_type=sa.Integer(), nullable=False)
    op.alter_column('invoices', 'year',
                    existing_type=sa.Integer(), nullable=False)
    op.alter_column('invoices', 'number',
                    existing_type=sa.String(length=50), nullable=False)
