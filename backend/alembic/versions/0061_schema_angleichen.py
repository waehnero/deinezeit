"""Schema und Modelle angleichen: Löschkaskaden, UNIQUE auf Feldschlüssel

Revision ID: 0061
Revises: 0060
Create Date: 2026-09-03

Hintergrund (Audit 02.09.2026, DATA-003 / DATA-004)
----------------------------------------------------
Die Tests bauen ihr Schema aus den Modellen (``create_all``), die Produktion
bekommt es aus den Migrationen. Beide waren mit 102 Abweichungen
auseinandergelaufen — überwiegend Indexnamen und Nullable-Angaben, die nur in
den Modellen nachgezogen werden mussten (kein Datenbank-Eingriff). Vier
Abweichungen betreffen aber das Verhalten der Datenbank selbst; die stellt
diese Migration richtig. Ab jetzt wacht ``tests/test_migrationen.py``
darüber, dass beides deckungsgleich bleibt.

Was sich in der Datenbank ändert
--------------------------------
1. ``time_entries.user_id``: Löschkaskade entfernt. Bisher löschte das
   Löschen eines Benutzers kommentarlos alle seine Zeiteinträge — auch
   abgerechnete. Jetzt verhindert die Datenbank das Löschen (der Endpunkt
   deaktiviert solche Benutzer stattdessen, siehe api/users.py).
2. ``entity_records.entity_type_id`` und ``field_definitions.entity_type_id``:
   Löschkaskade entfernt. Ein gelöschter Stammdaten-Typ riss bisher alle
   Datensätze und Felder mit — der Endpunkt deaktiviert Typen ohnehin nur,
   aber ein versehentliches ``DELETE`` in der Datenbank hätte alles
   vernichtet. Entspricht dem Beschluss „keine CASCADE-FKs auf Stammdaten".
3. ``time_entry_fields.key``: UNIQUE. Das Modell verlangt es seit jeher, die
   Datenbank prüfte es nicht. Vorab geprüft: keine Duplikate im Bestand
   (Abfrage vom 03.09.2026, 0 Zeilen).

Die Fremdschlüssel behalten ihre bisherigen Namen (PostgreSQL-Vorgabe
``<tabelle>_<spalte>_fkey``), damit Werkzeuge und Modelle sie weiter finden.

Downgrade stellt die Kaskaden wieder her und entfernt das UNIQUE.
"""
from alembic import op

revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None


# (Constraint-Name, Tabelle, Spalte, Zieltabelle)
_FKS = (
    ('time_entries_user_id_fkey',              'time_entries',      'user_id',        'users'),
    ('entity_records_entity_type_id_fkey',     'entity_records',    'entity_type_id', 'entity_types'),
    ('field_definitions_entity_type_id_fkey',  'field_definitions', 'entity_type_id', 'entity_types'),
)


def upgrade():
    for name, tabelle, spalte, ziel in _FKS:
        op.drop_constraint(name, tabelle, type_='foreignkey')
        op.create_foreign_key(name, tabelle, ziel, [spalte], ['id'])

    op.create_unique_constraint('time_entry_fields_key_key',
                                'time_entry_fields', ['key'])


def downgrade():
    op.drop_constraint('time_entry_fields_key_key', 'time_entry_fields',
                       type_='unique')

    for name, tabelle, spalte, ziel in _FKS:
        op.drop_constraint(name, tabelle, type_='foreignkey')
        op.create_foreign_key(name, tabelle, ziel, [spalte], ['id'],
                              ondelete='CASCADE')
