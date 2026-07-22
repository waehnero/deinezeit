"""Erstinstallation: Seed-Korrekturen (Register, Zahlungsziel, Zeitprojekte)

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-22

Korrigiert die Seed-/Stammdaten-Defaults, damit eine frische Installation
out-of-the-box zum bereits gepflegten Zustand passt. Alle Schritte sind
idempotent und nicht-destruktiv — sie greifen sowohl bei Neu- als auch bei
Bestandsinstallationen, ohne Nutzerdaten zu zerstoeren.

Umfang:
  1. Kontakte-Register aufraeumen:
     - defensiv: Tippfehler-Register "Finaz" -> "Finanz" (Felder + tabs-Array)
     - Basisfelder ohne Register (tab IS NULL) -> Register "Standard"
     - tabs-Array auf ["Standard", <bestehende>, "Finanz"] normalisieren
     - Feld "Zahlungsziel" im Register "Finanz" ergaenzen (falls fehlt)
  2. Zeitprojekte:
     - Typ slug 'projekte'/Name "Projekte" -> slug 'projektzeiten',
       Name "Zeitprojekte" (nur wenn 'projektzeiten' noch nicht existiert)
     - Feld "Kunde" (Text) -> Feld "Kontakt" (Verknuepfung zu Kontakte);
       bestehende "kunde"-Werte werden best-effort per Namensabgleich in das
       neue Verknuepfungsfeld uebernommen, die Feld-Definition "Kunde" entfernt
"""
import json
from alembic import op
import sqlalchemy as sa

revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # =========================================================================
    # 1. KONTAKTE-REGISTER
    # =========================================================================

    # 1a. Defensiv: falsch geschriebenes Register "Finaz" -> "Finanz" (Felder)
    conn.execute(sa.text("""
        UPDATE field_definitions
        SET tab = 'Finanz'
        WHERE tab = 'Finaz'
          AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
    """))

    # 1b. Basisfelder ohne Register -> "Standard"
    conn.execute(sa.text("""
        UPDATE field_definitions
        SET tab = 'Standard'
        WHERE tab IS NULL
          AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
    """))

    # 1c. tabs-Array normalisieren: "Standard" zuerst, "Finanz" hinten,
    #     bestehende (benutzerdefinierte) Register in der Mitte, ohne Duplikate.
    kt = conn.execute(sa.text(
        "SELECT tabs FROM entity_types WHERE slug = 'kontakte'"
    )).first()
    if kt:
        current = kt[0] or []
        # Tippfehler auch im Array beheben
        current = ['Finanz' if t == 'Finaz' else t for t in current]
        ordered = []
        for t in ['Standard'] + list(current) + ['Finanz']:
            if t and t not in ordered:
                ordered.append(t)
        conn.execute(
            sa.text("UPDATE entity_types SET tabs = CAST(:t AS jsonb) WHERE slug = 'kontakte'"),
            {"t": json.dumps(ordered)},
        )

    # 1d. Feld "Zahlungsziel" ins Register "Finanz". Das Feld existiert seit
    #     Migration 0010 (Typ number). Es wird ins Finanz-Register verschoben;
    #     nur falls es (aus welchem Grund auch immer) fehlt, wird es angelegt.
    moved = conn.execute(sa.text("""
        UPDATE field_definitions
        SET tab = 'Finanz'
        WHERE key = 'zahlungsziel'
          AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
    """))
    if getattr(moved, "rowcount", 0) == 0:
        conn.execute(sa.text("""
            INSERT INTO field_definitions
                (id, entity_type_id, name, key, field_type, is_required,
                 show_in_list, sort_order, placeholder, tab)
            SELECT
                gen_random_uuid(), et.id,
                'Zahlungsziel', 'zahlungsziel', 'number',
                false, false, 19, '30', 'Finanz'
            FROM entity_types et
            WHERE et.slug = 'kontakte'
        """))

    # =========================================================================
    # 2. ZEITPROJEKTE (frueher "Projekte")
    # =========================================================================

    # 2a. Typ umbenennen: nur wenn 'projektzeiten' noch nicht existiert und
    #     ein alter 'projekte'-Typ vorhanden ist (frische Installation).
    pz = conn.execute(sa.text(
        "SELECT id FROM entity_types WHERE slug = 'projektzeiten'"
    )).first()
    if not pz:
        alt = conn.execute(sa.text(
            "SELECT id FROM entity_types WHERE slug = 'projekte'"
        )).first()
        if alt:
            conn.execute(sa.text("""
                UPDATE entity_types
                SET slug = 'projektzeiten', name = 'Zeitprojekte'
                WHERE slug = 'projekte'
            """))
            pz = alt

    if pz:
        pz_id = pz[0]

        # Anzeigename konsequent auf "Zeitprojekte" setzen (Bestand mitziehen)
        conn.execute(sa.text(
            "UPDATE entity_types SET name = 'Zeitprojekte' WHERE id = :i"
        ), {"i": pz_id})

        # 2b. Verknuepfungsfeld "Kontakt" anlegen (nur wenn fehlt)
        conn.execute(sa.text("""
            INSERT INTO field_definitions
                (id, entity_type_id, name, key, field_type, is_required,
                 show_in_list, sort_order, placeholder, linked_type_slug)
            SELECT
                gen_random_uuid(), :i,
                'Kontakt', 'kontakt', 'relation',
                false, true, 2, NULL, 'kontakte'
            WHERE NOT EXISTS (
                SELECT 1 FROM field_definitions fd
                WHERE fd.entity_type_id = :i AND fd.key = 'kontakt'
            )
        """), {"i": pz_id})

        # 2c. Bestehende "kunde"-Textwerte best-effort in "kontakt" uebernehmen
        kontakte = conn.execute(sa.text("""
            SELECT er.id, er.display_name
            FROM entity_records er
            JOIN entity_types et ON et.id = er.entity_type_id
            WHERE et.slug = 'kontakte' AND er.display_name IS NOT NULL
        """)).fetchall()
        lookup = {}
        for kid, kname in kontakte:
            key = (kname or '').strip().lower()
            if key and key not in lookup:
                lookup[key] = (str(kid), kname)

        records = conn.execute(sa.text(
            "SELECT id, data FROM entity_records WHERE entity_type_id = :i"
        ), {"i": pz_id}).fetchall()
        for rid, data in records:
            data = data or {}
            if data.get('kontakt'):
                continue
            kunde = data.get('kunde')
            if isinstance(kunde, str) and kunde.strip():
                match = lookup.get(kunde.strip().lower())
                if match:
                    new_data = dict(data)
                    new_data['kontakt'] = {"id": match[0], "display_name": match[1]}
                    conn.execute(sa.text(
                        "UPDATE entity_records SET data = CAST(:d AS jsonb) WHERE id = :r"
                    ), {"d": json.dumps(new_data), "r": rid})

        # 2d. Feld-Definition "Kunde" entfernen (Werte in data bleiben erhalten)
        conn.execute(sa.text("""
            DELETE FROM field_definitions
            WHERE entity_type_id = :i AND key = 'kunde'
        """), {"i": pz_id})


def downgrade() -> None:
    conn = op.get_bind()

    # Zeitprojekte: Kontakt-Feld entfernen, Kunde-Textfeld wiederherstellen,
    # Typ zurueckbenennen (Werte werden nicht rueckuebertragen).
    pz = conn.execute(sa.text(
        "SELECT id FROM entity_types WHERE slug = 'projektzeiten'"
    )).first()
    if pz:
        pz_id = pz[0]
        conn.execute(sa.text("""
            DELETE FROM field_definitions
            WHERE entity_type_id = :i AND key = 'kontakt'
        """), {"i": pz_id})
        conn.execute(sa.text("""
            INSERT INTO field_definitions
                (id, entity_type_id, name, key, field_type, is_required,
                 show_in_list, sort_order, placeholder)
            SELECT gen_random_uuid(), :i, 'Kunde', 'kunde', 'text',
                   false, true, 2, 'Zugehöriger Kunde'
            WHERE NOT EXISTS (
                SELECT 1 FROM field_definitions fd
                WHERE fd.entity_type_id = :i AND fd.key = 'kunde'
            )
        """), {"i": pz_id})

    # Zahlungsziel-Feld existiert seit 0010 — nicht loeschen, nur Register loesen.
    conn.execute(sa.text("""
        UPDATE field_definitions
        SET tab = NULL
        WHERE key = 'zahlungsziel'
          AND entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
    """))
    # Bewusst keine Ruecknahme der uebrigen Register-Zuordnung/Namen — nicht destruktiv.
