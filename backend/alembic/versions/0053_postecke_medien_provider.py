"""Speicher-Provider je Datei für Postecke-Medien (Fotos und Videos)

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-11

Dieselbe Lücke wie bei den Positionsbildern (Migration 0051) und den
Datei-Anhängen (Migration 0039), diesmal in der Postecke: Fotos und Videos
werden über den **gerade aktiven** Speicher hoch- und heruntergeladen sowie
gelöscht. Nach einem Wechsel zwischen MinIO und OneDrive liegen die alten
Dateien weiter im alten Speicher, der Abruf ginge aber an den neuen.

Die Folge ist hier schwerer als beim Löschen allein: Vorschau, Download, das
Veröffentlichen auf Social Media, die öffentlichen Medien-URLs und die
Datacenter-Spiegelung greifen alle auf denselben Schlüssel zu — ältere Medien
wären nach einem Wechsel schlicht unauffindbar, nicht bloß unlöschbar.

Für Videos genügt **eine** Spalte: das Standbild (``poster_key``) liegt in
derselben Zeile und wird im selben Upload-Vorgang geschrieben, also immer im
selben Speicher wie das Video.

``NULL`` bedeutet weiterhin „unbekannt, nimm den aktiven Speicher". Das
entspricht exakt dem bisherigen Verhalten und ist damit kein Bruch für
Bestandsdaten. Ein Backfill mit dem heute aktiven Provider wäre geraten: Hat
der Wechsel schon stattgefunden, stünde in jeder alten Zeile der falsche Wert
— schlimmer als keiner. Bestandsdaten lassen sich stattdessen über die
Speicher-Migration in den Einstellungen sauber umziehen.
"""
from alembic import op
import sqlalchemy as sa

revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_post_fotos',
                  sa.Column('storage_provider', sa.String(length=20), nullable=True))
    op.add_column('social_post_videos',
                  sa.Column('storage_provider', sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column('social_post_videos', 'storage_provider')
    op.drop_column('social_post_fotos', 'storage_provider')
