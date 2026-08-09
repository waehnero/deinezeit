"""Speicher-Provider je Datei für Positionsbilder und Eingangsrechnungen

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-08

Bei den Datei-Anhängen wird der Provider seit Migration 0039 je Datei
gespeichert (``attachments.storage_provider``), weil im Mischbetrieb sonst am
falschen Ort gesucht wird: Nach einem Wechsel von MinIO auf OneDrive liegen die
alten Dateien weiter in MinIO, der Abruf ginge aber an OneDrive.

Für **Positionsbilder** und die **Originale der Eingangsrechnungen** wurde das
übersehen. Beide laden über den gerade aktiven Speicher hoch, herunter und
löschen dort — im Mischbetrieb sind damit ältere Bilder in der Vorschau und im
PDF nicht auffindbar und lassen sich auch nicht aufräumen.

``NULL`` bedeutet weiterhin „unbekannt, nimm den aktiven Speicher". Das ist
genau das bisherige Verhalten und damit kein Bruch für Bestandsdaten. Ein
Backfill mit dem heute aktiven Provider wäre geraten: Hat der Wechsel schon
stattgefunden, stünde in jeder alten Zeile der falsche Wert — schlimmer als
keiner.
"""
from alembic import op
import sqlalchemy as sa

revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoice_positions',
                  sa.Column('image_provider', sa.String(length=20), nullable=True))
    op.add_column('purchase_invoices',
                  sa.Column('file_provider', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('purchase_invoices', 'file_provider')
    op.drop_column('invoice_positions', 'image_provider')
