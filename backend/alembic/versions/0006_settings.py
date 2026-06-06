"""Settings-Tabelle

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


DEFAULTS = [
    ('company_name',    'DeineZeit'),
    ('app_subtitle',    'Zeiterfassung & Stammdaten'),
    ('color_theme',     'orange'),
    ('logo_url',        ''),
    ('smtp_host',       ''),
    ('smtp_port',       '587'),
    ('smtp_user',       ''),
    ('smtp_password',   ''),
    ('smtp_from_name',  ''),
    ('smtp_from_email', ''),
    ('smtp_tls',        'true'),
    ('backup_keep_days','30'),
    ('backup_last_at',  ''),
]


def upgrade():
    op.create_table(
        'settings',
        sa.Column('key',        sa.String(100), primary_key=True),
        sa.Column('value',      sa.Text,        nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Standard-Werte eintragen
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        sa.table('settings',
            sa.column('key',        sa.String),
            sa.column('value',      sa.Text),
            sa.column('updated_at', sa.DateTime),
        ),
        [{'key': k, 'value': v, 'updated_at': now} for k, v in DEFAULTS]
    )


def downgrade():
    op.drop_table('settings')
