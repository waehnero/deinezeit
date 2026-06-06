"""Logo-Varianten, Favicon und Firmen-Kontakt in Settings

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

NEW_KEYS = [
    ('logo_header_url',      ''),   # 600x120 für Berichtskopf
    ('logo_favicon_url',     ''),   # 32x32 für Browser-Tab
    ('company_contact_id',   ''),   # UUID des verknüpften Kontakts
    ('company_contact_type', ''),   # Slug des Stammdaten-Typs
]


def upgrade():
    now = datetime.now(timezone.utc)
    settings_table = sa.table(
        'settings',
        sa.column('key',        sa.String),
        sa.column('value',      sa.Text),
        sa.column('updated_at', sa.DateTime),
    )

    # Nur einfügen wenn noch nicht vorhanden (idempotent)
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(
        sa.text("SELECT key FROM settings")
    )}

    rows = [
        {'key': k, 'value': v, 'updated_at': now}
        for k, v in NEW_KEYS
        if k not in existing
    ]
    if rows:
        op.bulk_insert(settings_table, rows)


def downgrade():
    keys = [k for k, _ in NEW_KEYS]
    op.execute(
        sa.text("DELETE FROM settings WHERE key = ANY(:keys)").bindparams(keys=keys)
    )
