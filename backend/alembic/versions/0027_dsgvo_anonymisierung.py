"""DSGVO: Anonymisierung von Kontakten + Löschprotokoll

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-06

Erweiterung entity_records:
  - anonymized_at (DateTime): gesetzt, wenn der Datensatz per DSGVO-Löschung
    anonymisiert wurde (Tombstone). Der Datensatz bleibt als Zeile erhalten,
    damit keine Verweise verwaisen — aber ohne Personenbezug.

Neue Tabelle gdpr_deletion_log:
  Löschprotokoll zur Rechenschaftspflicht (Art. 5 Abs. 2 DSGVO).
  Bewusst OHNE personenbezogene Daten — nur Vorgangs-Metadaten.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('entity_records',
                  sa.Column('anonymized_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'gdpr_deletion_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('executed_by', sa.String(length=200), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        # Betroffene Kategorien mit Anzahl, z.B.
        # {"time_entries": 12, "invoices_snapshotted": 3, "attachments": 2, ...}
        sa.Column('categories', postgresql.JSONB(), nullable=True),
        # Umgang mit Datacenter-Dateien: deleted | unlinked | none
        sa.Column('files_action', sa.String(length=20), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
    )
    op.create_index('ix_gdpr_deletion_log_record', 'gdpr_deletion_log', ['record_id'])


def downgrade():
    op.drop_index('ix_gdpr_deletion_log_record', table_name='gdpr_deletion_log')
    op.drop_table('gdpr_deletion_log')
    op.drop_column('entity_records', 'anonymized_at')
