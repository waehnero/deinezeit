"""Modulrecht "Buchhaltung" — Bestandsbenutzer behalten ihren Zugriff

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-01

Verkaufsbuch, offene Posten, Kontenplan und Buchhaltungs-Export hängen ab
sofort am neuen Modul ``buchhaltung`` (zusätzlich zu ``verkauf``).

Benutzer mit ``allowed_modules = NULL`` haben ohnehin alle Module — für sie
ändert sich nichts. Wer aber eine ausdrückliche Modul-Liste hat, in der
``verkauf`` steht, würde den Zugriff auf das Verkaufsbuch verlieren, den er
bisher hatte. Deshalb bekommt genau diese Gruppe ``buchhaltung`` dazu.

Ein neues Recht darf niemandem etwas wegnehmen, das er vorher konnte.
"""
from alembic import op
import sqlalchemy as sa

revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().execute(sa.text("""
        UPDATE users
           SET allowed_modules = allowed_modules || '["buchhaltung"]'::jsonb
         WHERE allowed_modules IS NOT NULL
           AND allowed_modules @> '["verkauf"]'::jsonb
           AND NOT (allowed_modules @> '["buchhaltung"]'::jsonb)
    """))


def downgrade():
    op.get_bind().execute(sa.text("""
        UPDATE users
           SET allowed_modules = allowed_modules - 'buchhaltung'
         WHERE allowed_modules IS NOT NULL
    """))
