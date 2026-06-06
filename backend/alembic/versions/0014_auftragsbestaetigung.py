"""Auftragsbestätigung: Nummernkreis AB + Statusübergänge erweitert

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-05

Fügt den Dokumenttyp "auftragsbestaetigung" (AB) zum System hinzu:
  - Standard-Nummernformat AB-{year}-{seq:03d}
  - Default-Texte für Auftragsbestätigungen
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO invoice_settings (key, value)
        VALUES
            ('number_format_auftragsbestaetigung', '"AB-{year}-{seq:03d}"'::jsonb),
            ('default_intro_auftragsbestaetigung', '"Vielen Dank für Ihren Auftrag! Wir bestätigen hiermit folgende Leistungen:"'::jsonb),
            ('default_outro_auftragsbestaetigung', '"Wir freuen uns auf die Zusammenarbeit und werden uns umgehend mit Ihnen in Verbindung setzen."'::jsonb)
        ON CONFLICT (key) DO NOTHING
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM invoice_settings
        WHERE key IN (
            'number_format_auftragsbestaetigung',
            'default_intro_auftragsbestaetigung',
            'default_outro_auftragsbestaetigung'
        )
    """))
