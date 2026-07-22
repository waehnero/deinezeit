"""Anhänge: Speicher-Provider je Datei merken

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-22

Neue Spalte attachments.storage_provider:
  - hält fest, in welchem Speicher (minio | nextcloud | seadrive | onedrive)
    die Datei beim Upload abgelegt wurde.
  - Down-/Vorschau/Share/Löschen nutzen genau diesen Provider — dadurch
    funktioniert Mischbetrieb (z.B. MinIO-Altdateien + neue OneDrive-Dateien),
    auch nachdem der aktive Provider gewechselt wurde.

Bestandsdaten: alle bisherigen Anhänge liegen in MinIO → server_default 'minio'.
"""
from alembic import op
import sqlalchemy as sa

revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attachments', sa.Column(
        'storage_provider', sa.String(length=20), nullable=True,
        server_default='minio'))


def downgrade():
    op.drop_column('attachments', 'storage_provider')
