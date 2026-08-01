"""Verkauf: Leistungszeitraum (Bis-Datum zum Liefer-/Leistungsdatum)

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-01

Das Liefer-/Leistungsdatum ist Pflichtangabe nach § 11 Abs. 1 Z 4 UStG. Die
Spalte ``delivery_date`` gab es bereits, sie war nur über kein Eingabefeld
erreichbar und blieb deshalb immer leer.

Für Zeitabrechnung und Wartungsverträge reicht ein einzelnes Datum nicht —
dort gehört ein Zeitraum auf den Beleg („Leistungszeitraum 01.07.–31.07.2026").
Statt weiterer Felder bekommt das vorhandene Datum ein optionales Bis-Datum:

  * ``delivery_date_to`` leer  → einzelnes Leistungsdatum
  * ``delivery_date_to`` gesetzt → Zeitraum von ``delivery_date`` bis dorthin

Bestandsdaten bleiben unberührt (alle Belege haben bisher gar kein
Leistungsdatum, siehe oben).
"""
from alembic import op
import sqlalchemy as sa

revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('delivery_date_to', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('invoices', 'delivery_date_to')
