"""Rechnungen: Empfänger-Snapshot (DSGVO-Vorbereitung)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-06

Erweiterung invoices:
  - recipient_snapshot (JSONB): eingefrorene Empfängerdaten
    {"display_name": ..., "data": {...}, "frozen_at": ..., "source": ...}

Zweck: Belege (Rechnungen etc.) unterliegen der Aufbewahrungspflicht
(§ 132 BAO / § 147 AO) und müssen unverändert reproduzierbar bleiben.
Bisher wurde der Empfänger beim PDF-Rendern LIVE aus den Stammdaten
(entity_records) gelesen — Kontakt-Änderungen oder eine spätere
DSGVO-Löschung hätten alte Belege verändert bzw. unbrauchbar gemacht.

Der Snapshot wird beim Finalisieren eines Belegs eingefroren (Status
verlässt 'entwurf'). Dieses Backfill friert alle bereits finalisierten
Belege mit noch existierendem Kontakt nach.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices',
                  sa.Column('recipient_snapshot', postgresql.JSONB(), nullable=True))

    # ── Backfill: finalisierte Belege mit existierendem Kontakt einfrieren ──
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE invoices i
        SET recipient_snapshot = jsonb_build_object(
            'display_name', er.display_name,
            'data',         COALESCE(er.data, '{}'::jsonb),
            'frozen_at',    to_char(now() AT TIME ZONE 'utc',
                                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
            'source',       'backfill'
        )
        FROM entity_records er
        WHERE i.contact_id = er.id
          AND i.status != 'entwurf'
          AND i.recipient_snapshot IS NULL
    """))


def downgrade():
    op.drop_column('invoices', 'recipient_snapshot')
