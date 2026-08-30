"""Artikelstamm: Artikelgruppen, Nummernkreis, erweiterte Felder

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-30

Ausgangslage
------------
Der Artikelstamm kannte fünf Felder: ``bezeichnung``, ``artikelnummer``,
``preis``, ``beschreibung`` (alle aus Migration 0010) und ``erloes_konto``
als freien Text (0013). Damit fehlte praktisch alles, was ein Artikelstamm
in einer Warenwirtschaft ausmacht:

* **Keine Artikelnummer-Vergabe.** Jede Nummer wurde von Hand getippt.
* **Keine Gruppen.** Weder für Auswertungen noch als Ort für die
  Buchungsvorgabe. Das Erlöskonto musste an jedem Artikel einzeln stehen —
  in der Praxis stand es nirgends.
* **Kein USt-Satz und keine Einheit.** Besonders auffällig bei der Einheit:
  Der Belegpicker liest seit jeher ``r.data.einheit``, doch dieses Feld gab
  es gar nicht. Der Fallback ``'Stk'`` griff also immer.

Was diese Migration anlegt
--------------------------
1. ``article_groups`` — Artikelgruppe mit Präfix und laufendem Zähler für die
   Artikelnummer sowie Erlös- und Aufwandskonto. Zwei Gruppen als Startbestand.
2. ``field_definitions.lookup_source`` und ``.is_system`` — der neue Feldtyp
   ``lookup`` (Auswahl aus Kontenplan bzw. Artikelgruppen) braucht eine Quelle,
   und Felder, auf die andere Module angewiesen sind, dürfen nicht mehr
   gelöscht werden.
3. 22 neue Artikelfelder auf fünf Registern; die fünf bestehenden werden
   einsortiert und ``erloes_konto`` von Text auf ``lookup`` umgestellt.

Warum die Gruppe eine eigene Tabelle ist und kein weiterer Stammdaten-Typ:
An ihr hängen ein Zähler, der unter einer Zeilensperre hochgezählt werden muss,
und Kontenzuordnungen, die geprüft gehören. Beides ist im JSONB-Baukasten der
EntityRecords nicht sauber zu haben. Der Kontenplan ist aus demselben Grund
eine eigene Tabelle.

Bestandsdaten
-------------
Nichts wird überschrieben. ``erloes_konto`` behält seinen Schlüssel und seinen
Inhalt — der lookup-Typ speichert dieselbe Kontonummer als Zeichenkette, es
ändert sich nur die Eingabehilfe. Vorhandene Artikel behalten ihre von Hand
vergebenen Nummern; die automatische Vergabe greift nur, wenn das Feld beim
Anlegen leer bleibt.

Die neuen Felder werden einzeln über ``NOT EXISTS`` angelegt statt über die
Sammelbedingung „Typ hat noch gar keine Felder", die 0010 verwendet hat. Sonst
würde die Migration bei jedem Bestand mit Artikeln wirkungslos durchlaufen —
also genau dort, wo sie gebraucht wird.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


# ── Neue Artikelfelder ────────────────────────────────────────────────────────
# (key, name, typ, register, sortierung, breite, pflicht, in_liste,
#  platzhalter, optionen, vorgabe, lookup-quelle, systemfeld)
#
# Die Sortierung lässt zwischen den Registern Lücken (10er, 200er, 300er …),
# damit später ein Feld dazwischen passt, ohne alles neu zu nummerieren.
NEUE_FELDER = [
    # ── Allgemein ────────────────────────────────────────────────────────────
    ('zusatz', 'Zusatz', 'text', 'Allgemein', 30, 6, False, False,
     'z.B. Ausführung, Farbe, Größe', None, None, None, False),
    ('artikelgruppe', 'Artikelgruppe', 'lookup', 'Allgemein', 40, 4, False, True,
     None, None, None, 'artikelgruppen', True),
    ('artikelart', 'Artikelart', 'dropdown', 'Allgemein', 50, 4, False, False,
     None, ['Ware', 'Dienstleistung', 'Leistung (Zeit)', 'Sonstiges'],
     None, None, False),
    ('suchbegriff', 'Suchbegriff', 'text', 'Allgemein', 60, 4, False, False,
     'Kurzform für die Schnellsuche', None, None, None, False),
    ('ean', 'EAN / GTIN', 'text', 'Allgemein', 70, 4, False, False,
     '13-stellig', None, None, None, False),
    ('infotext', 'Interner Hinweis', 'textarea', 'Allgemein', 90, 12, False, False,
     'Nur intern sichtbar — erscheint auf keinem Beleg', None, None, None, False),
    ('bild', 'Artikelbild', 'image', 'Allgemein', 95, 12, False, False,
     None, None, None, None, False),

    # ── Preise ───────────────────────────────────────────────────────────────
    ('einheit', 'Einheit', 'dropdown', 'Preise', 200, 3, False, True,
     None, ['Stk', 'h', 'Tag', 'Pauschale', 'm', 'm²', 'm³', 'lfm',
            'kg', 't', 'Liter', 'km'], 'Stk', None, True),
    ('preis_ist_brutto', 'Preis ist Bruttopreis', 'checkbox', 'Preise', 220, 3,
     False, False, None, None, None, None, False),
    ('ust_satz', 'USt-Satz', 'dropdown', 'Preise', 230, 3, False, False,
     None, ['20', '13', '10', '0', 'Reverse Charge'], None, None, True),
    ('rabattfaehig', 'Rabattfähig', 'checkbox', 'Preise', 240, 3, False, False,
     None, None, 'true', None, False),
    ('max_rabatt', 'Höchstrabatt %', 'number', 'Preise', 250, 3, False, False,
     '0', None, None, None, False),

    # ── Einkauf ──────────────────────────────────────────────────────────────
    ('ek_preis', 'Einkaufspreis netto', 'number', 'Einkauf', 300, 3, False, False,
     '0.00', None, None, None, False),
    ('lieferant', 'Lieferant', 'relation', 'Einkauf', 310, 6, False, False,
     None, None, None, None, False),
    ('lieferanten_artikelnummer', 'Artikelnummer beim Lieferanten', 'text',
     'Einkauf', 320, 3, False, False, None, None, None, None, False),

    # ── Buchhaltung ──────────────────────────────────────────────────────────
    ('aufwand_konto', 'Aufwandskonto', 'lookup', 'Buchhaltung', 410, 4, False, False,
     None, None, None, 'konten', False),
    ('kostenstelle', 'Kostenstelle', 'text', 'Buchhaltung', 420, 4, False, False,
     None, None, None, None, False),

    # ── Lager ────────────────────────────────────────────────────────────────
    ('lagerfuehrung', 'Lagergeführt', 'checkbox', 'Lager', 500, 3, False, False,
     None, None, None, None, False),
    ('bestand', 'Bestand', 'number', 'Lager', 510, 3, False, False,
     '0', None, None, None, False),
    ('mindestbestand', 'Mindestbestand', 'number', 'Lager', 520, 3, False, False,
     '0', None, None, None, False),
    ('lagerort', 'Lagerort', 'text', 'Lager', 530, 3, False, False,
     'z.B. Regal B3', None, None, None, False),
    ('gewicht_kg', 'Gewicht (kg)', 'number', 'Lager', 540, 3, False, False,
     '0.000', None, None, None, False),
]

# Bestehende Felder einsortieren: (key, register, sortierung, breite)
#
# ``bezeichnung`` bleibt mit Absicht vor ``artikelnummer``. Der Anzeigename
# eines Datensatzes ist der Wert des ERSTEN Textfeldes nach Sortierung
# (``_extract_display_name``) — stünde die Nummer davor, hieße jeder Artikel
# in allen Listen und Auswahlfeldern plötzlich „ART-0001" statt nach seiner
# Bezeichnung.
BESTEHENDE_FELDER = [
    ('bezeichnung',   'Allgemein',    10,  6),
    ('artikelnummer', 'Allgemein',    20,  3),
    ('beschreibung',  'Allgemein',    80, 12),
    ('preis',         'Preise',      210,  3),
    ('erloes_konto',  'Buchhaltung', 400,  4),
]

# Felder, auf die andere Module angewiesen sind (Belegpicker, Kontenkaskade).
SYSTEMFELDER = ['bezeichnung', 'artikelnummer', 'beschreibung', 'preis',
                'einheit', 'ust_satz', 'artikelgruppe', 'erloes_konto']

TABS = ['Allgemein', 'Preise', 'Einkauf', 'Buchhaltung', 'Lager']


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Artikelgruppen ────────────────────────────────────────────────────
    op.create_table(
        'article_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('nr', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('beschreibung', sa.String(500), nullable=True),
        sa.Column('praefix', sa.String(10), nullable=True),
        sa.Column('naechste_nummer', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('stellen', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('erloes_konto_nr', sa.String(20), nullable=True),
        sa.Column('aufwand_konto_nr', sa.String(20), nullable=True),
        sa.Column('ust_satz', sa.Numeric(5, 2), nullable=True),
        sa.Column('artikelart', sa.String(30), nullable=True),
        sa.Column('einheit', sa.String(30), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Kein zusätzlicher Index auf ``nr``: Die Unique-Bedingung bringt schon
    # einen mit, ein zweiter wäre nur Ballast beim Schreiben.

    # Startbestand. Ohne ihn stünde die Artikelanlage nach der Erstinstallation
    # vor einem leeren Auswahlfeld und könnte keine Nummer vergeben — die
    # Automatik wäre da, aber unbenutzbar.
    #
    # 4000 ist im EKR-Seed (Migration 0013) als Standard-Erlöskonto gesetzt;
    # 5000 ist der Wareneinsatz. Beide werden nur zugeordnet, wenn sie im
    # Kontenplan tatsächlich stehen — in einem umgebauten Kontenplan bleibt das
    # Feld lieber leer als falsch.
    conn.execute(sa.text("""
        INSERT INTO article_groups (nr, name, beschreibung, praefix, stellen,
                                    erloes_konto_nr, aufwand_konto_nr,
                                    artikelart, einheit, sort_order)
        SELECT 'DL', 'Dienstleistung', 'Arbeitsleistung, Beratung, Regiestunden',
               'DL', 4,
               (SELECT nr FROM accounting_accounts WHERE nr = '4000'),
               NULL, 'dienstleistung', 'h', 1
        WHERE NOT EXISTS (SELECT 1 FROM article_groups WHERE nr = 'DL')
    """))
    conn.execute(sa.text("""
        INSERT INTO article_groups (nr, name, beschreibung, praefix, stellen,
                                    erloes_konto_nr, aufwand_konto_nr,
                                    artikelart, einheit, sort_order)
        SELECT 'WA', 'Ware', 'Handelsware und Material',
               'WA', 4,
               (SELECT nr FROM accounting_accounts WHERE nr = '4000'),
               (SELECT nr FROM accounting_accounts WHERE nr = '5000'),
               'ware', 'Stk', 2
        WHERE NOT EXISTS (SELECT 1 FROM article_groups WHERE nr = 'WA')
    """))

    # ── 2. Felddefinitionen erweitern ────────────────────────────────────────
    op.add_column('field_definitions',
                  sa.Column('lookup_source', sa.String(50), nullable=True))
    op.add_column('field_definitions',
                  sa.Column('is_system', sa.Boolean(), nullable=False,
                            server_default='false'))

    # ── 3. Register am Artikel-Typ ───────────────────────────────────────────
    conn.execute(sa.text("""
        UPDATE entity_types
        SET tabs = CAST(:tabs AS jsonb)
        WHERE slug = 'artikel'
    """), {"tabs": '["' + '", "'.join(TABS) + '"]'})

    # ── 4. Bestehende Felder einsortieren ────────────────────────────────────
    for key, tab, sort_order, col_span in BESTEHENDE_FELDER:
        conn.execute(sa.text("""
            UPDATE field_definitions fd
            SET tab = :tab, sort_order = :sort_order, col_span = :col_span
            FROM entity_types et
            WHERE fd.entity_type_id = et.id
              AND et.slug = 'artikel'
              AND fd.key = :key
        """), {"key": key, "tab": tab, "sort_order": sort_order,
               "col_span": col_span})

    # ``erloes_konto`` war ein freies Textfeld — die Kontonummer musste man
    # auswendig wissen. Als lookup-Feld kommt sie aus dem Kontenplan. Der
    # gespeicherte Wert bleibt derselbe (die Nummer als Zeichenkette), deshalb
    # ist keine Datenumstellung nötig.
    conn.execute(sa.text("""
        UPDATE field_definitions fd
        SET field_type = 'lookup', lookup_source = 'konten', placeholder = NULL
        FROM entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'artikel'
          AND fd.key = 'erloes_konto'
    """))

    # Die Artikelnummer ist ab jetzt eindeutig. Rückwirkend geprüft wird nicht:
    # Doppelte aus der Zeit der Handeingabe würden die Migration sonst
    # abbrechen lassen. Die Vergabe weicht Kollisionen aus, und die Prüfung
    # greift ab der nächsten Eingabe.
    conn.execute(sa.text("""
        UPDATE field_definitions fd
        SET is_unique = true, placeholder = 'wird automatisch vergeben'
        FROM entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'artikel'
          AND fd.key = 'artikelnummer'
    """))

    # ── 5. Neue Felder anlegen ───────────────────────────────────────────────
    for (key, name, typ, tab, sort_order, col_span, pflicht, in_liste,
         platzhalter, optionen, vorgabe, quelle, _system) in NEUE_FELDER:
        conn.execute(sa.text("""
            INSERT INTO field_definitions
                (id, entity_type_id, name, key, field_type, is_required,
                 is_unique, show_in_list, sort_order, col_span, tab,
                 options, placeholder, default_value, linked_type_slug,
                 lookup_source, is_system, created_at)
            SELECT gen_random_uuid(), et.id, :name, :key, :typ, :pflicht,
                   false, :in_liste, :sort_order, :col_span, :tab,
                   CAST(:optionen AS jsonb),
                   :platzhalter, :vorgabe, :ziel_typ,
                   :quelle, false, NOW()
            FROM entity_types et
            WHERE et.slug = 'artikel'
              AND NOT EXISTS (
                  SELECT 1 FROM field_definitions fd
                  WHERE fd.entity_type_id = et.id AND fd.key = :key
              )
        """), {
            "name": name, "key": key, "typ": typ, "pflicht": pflicht,
            "in_liste": in_liste, "sort_order": sort_order,
            "col_span": col_span, "tab": tab,
            "optionen": ('["' + '", "'.join(optionen) + '"]') if optionen else None,
            "platzhalter": platzhalter, "vorgabe": vorgabe, "quelle": quelle,
            # Nur das Lieferanten-Feld ist eine Verknüpfung — und zwar auf die
            # Kontakte, denn Kunden und Lieferanten liegen seit Migration 0010
            # in einem gemeinsamen Stammdaten-Typ.
            "ziel_typ": 'kontakte' if typ == 'relation' else None,
        })

    # ── 6. Systemfelder kennzeichnen ─────────────────────────────────────────
    conn.execute(sa.text("""
        UPDATE field_definitions fd
        SET is_system = true
        FROM entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'artikel'
          AND fd.key = ANY(:keys)
    """), {"keys": SYSTEMFELDER})


def downgrade() -> None:
    conn = op.get_bind()

    # Neue Felder entfernen. Die Werte in ``entity_records.data`` bleiben stehen
    # — sie stören nicht und wären beim erneuten Hochmigrieren wieder da.
    conn.execute(sa.text("""
        DELETE FROM field_definitions fd
        USING entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'artikel'
          AND fd.key = ANY(:keys)
    """), {"keys": [f[0] for f in NEUE_FELDER]})

    # erloes_konto zurück auf Text
    conn.execute(sa.text("""
        UPDATE field_definitions fd
        SET field_type = 'text', lookup_source = NULL, placeholder = 'z.B. 4000'
        FROM entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'artikel'
          AND fd.key = 'erloes_konto'
    """))

    conn.execute(sa.text("UPDATE entity_types SET tabs = '[]'::jsonb WHERE slug = 'artikel'"))

    op.drop_column('field_definitions', 'is_system')
    op.drop_column('field_definitions', 'lookup_source')
    op.drop_table('article_groups')
