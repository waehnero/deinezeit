"""Stammdaten: entity_types, field_definitions, entity_records

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stammdaten-Typen (z.B. Kunden, Lieferanten, Projekte)
    op.create_table(
        'entity_types',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('color', sa.String(20), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Felddefinitionen
    op.create_table(
        'field_definitions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type_id', UUID(as_uuid=True),
                  sa.ForeignKey('entity_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('field_type', sa.String(30), nullable=False),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_unique', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('show_in_list', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('options', JSONB, nullable=True),
        sa.Column('placeholder', sa.String(200), nullable=True),
        sa.Column('default_value', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_field_definitions_entity_type_id', 'field_definitions', ['entity_type_id'])

    # Datensätze
    op.create_table(
        'entity_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type_id', UUID(as_uuid=True),
                  sa.ForeignKey('entity_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('data', JSONB, nullable=False, server_default='{}'),
        sa.Column('display_name', sa.String(300), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_entity_records_entity_type_id', 'entity_records', ['entity_type_id'])
    op.create_index('ix_entity_records_data', 'entity_records', ['data'], postgresql_using='gin')

    # Standard-Stammdaten-Typen anlegen
    op.execute("""
        INSERT INTO entity_types (id, name, slug, icon, color, description, sort_order)
        VALUES
            (gen_random_uuid(), 'Kunden',     'kunden',     'Users',      '#3b82f6', 'Kundenstammdaten', 1),
            (gen_random_uuid(), 'Lieferanten','lieferanten','Package',    '#10b981', 'Lieferantenstammdaten', 2),
            (gen_random_uuid(), 'Projekte',   'projekte',   'FolderOpen', '#8b5cf6', 'Projektverwaltung', 3)
    """)

    # Standard-Felder für Kunden
    op.execute("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.name, fd.key, fd.field_type, fd.is_required::boolean, fd.show_in_list::boolean,
            fd.sort_order::integer, fd.placeholder
        FROM entity_types et,
        (VALUES
            ('Firmenname',      'firmenname',      'text',     'true',  'true',  '1', 'z.B. Muster GmbH'),
            ('Ansprechperson',  'ansprechperson',  'text',     'false', 'true',  '2', 'Vor- und Nachname'),
            ('E-Mail',          'email',           'email',    'false', 'true',  '3', 'info@firma.at'),
            ('Telefon',         'telefon',         'phone',    'false', 'false', '4', '+43 1 234 567'),
            ('Adresse',         'adresse',         'textarea', 'false', 'false', '5', 'Straße, PLZ Ort'),
            ('Webseite',        'webseite',        'url',      'false', 'false', '6', 'https://'),
            ('Notizen',         'notizen',         'textarea', 'false', 'false', '7', '')
        ) AS fd(name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        WHERE et.slug = 'kunden'
    """)

    # Standard-Felder für Lieferanten
    op.execute("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.name, fd.key, fd.field_type, fd.is_required::boolean, fd.show_in_list::boolean,
            fd.sort_order::integer, fd.placeholder
        FROM entity_types et,
        (VALUES
            ('Firmenname',      'firmenname',      'text',     'true',  'true',  '1', 'z.B. Lieferant GmbH'),
            ('Ansprechperson',  'ansprechperson',  'text',     'false', 'true',  '2', 'Vor- und Nachname'),
            ('E-Mail',          'email',           'email',    'false', 'true',  '3', 'info@lieferant.at'),
            ('Telefon',         'telefon',         'phone',    'false', 'false', '4', '+43 1 234 567'),
            ('Adresse',         'adresse',         'textarea', 'false', 'false', '5', 'Straße, PLZ Ort'),
            ('Lieferkategorien','lieferkategorien','text',     'false', 'false', '6', 'z.B. Büromaterial'),
            ('Notizen',         'notizen',         'textarea', 'false', 'false', '7', '')
        ) AS fd(name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        WHERE et.slug = 'lieferanten'
    """)

    # Standard-Felder für Projekte
    op.execute("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.name, fd.key, fd.field_type, fd.is_required::boolean, fd.show_in_list::boolean,
            fd.sort_order::integer, fd.placeholder
        FROM entity_types et,
        (VALUES
            ('Projektname',     'projektname',     'text',     'true',  'true',  '1', 'z.B. Website Relaunch'),
            ('Kunde',           'kunde',           'text',     'false', 'true',  '2', 'Zugehöriger Kunde'),
            ('Status',          'status',          'dropdown', 'false', 'true',  '3', ''),
            ('Startdatum',      'startdatum',      'date',     'false', 'true',  '4', ''),
            ('Enddatum',        'enddatum',        'date',     'false', 'false', '5', ''),
            ('Budget',          'budget',          'number',   'false', 'false', '6', '0.00'),
            ('Beschreibung',    'beschreibung',    'textarea', 'false', 'false', '7', '')
        ) AS fd(name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        WHERE et.slug = 'projekte'
    """)

    # Dropdown-Optionen für Projekt-Status
    op.execute("""
        UPDATE field_definitions
        SET options = '["Geplant", "In Bearbeitung", "Abgeschlossen", "Pausiert", "Abgebrochen"]'::jsonb
        WHERE key = 'status'
        AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'projekte')
    """)


def downgrade() -> None:
    op.drop_table('entity_records')
    op.drop_table('field_definitions')
    op.drop_table('entity_types')
