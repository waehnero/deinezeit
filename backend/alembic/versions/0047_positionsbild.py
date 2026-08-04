"""Verkauf: Bild je Belegposition

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-01

Zwei Felder an der Position:

  ``image_key``  Objektspeicher-Schlüssel des Bildes
  ``image_size`` gewählte Druckgröße: klein | mittel | gross

**Warum am Positionsdatensatz und nicht in einer eigenen Tabelle:** Positionen
werden beim Speichern eines Belegs gelöscht und neu angelegt (siehe
``update_invoice``) — eine Position hat also keine dauerhafte Kennung, an der
ein Anhang hängen könnte. Der Speicher-Schlüssel reist stattdessen wie das
Erlöskonto als Feld im Positions-Datensatz mit.

Folge davon: Wird eine Position entfernt, bleibt ihre Bilddatei im Speicher
liegen. Ein Aufräumlauf dafür fehlt bewusst noch.
"""
from alembic import op
import sqlalchemy as sa

revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoice_positions', sa.Column('image_key', sa.String(length=500), nullable=True))
    op.add_column('invoice_positions', sa.Column('image_size', sa.String(length=10), nullable=True))


def downgrade():
    op.drop_column('invoice_positions', 'image_size')
    op.drop_column('invoice_positions', 'image_key')
