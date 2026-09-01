"""Zeitprojekte: Slug 'projektzeiten' -> 'zeitprojekte'

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-01

Der Stammdaten-Typ, auf den Zeiteintraege gebucht werden, heisst in der
Oberflaeche seit Migration 0038 "Zeitprojekte" — technisch trug er aber
weiterhin den Slug ``projektzeiten``. Das ist eine Altlast: 0038 hat den
frueheren Typ ``projekte`` umbenannt und dabei nur den Anzeigenamen
mitgezogen.

Warum das mehr als Kosmetik ist
-------------------------------
Im Modul stehen zwei Begriffe nebeneinander, die verschiedene Dinge meinen:

  Zeitprojekt   = Stammsatz (Kunde/Projekt), auf den gebucht wird
  Projektzeit   = einzelner Zeiteintrag

Solange der Stammdaten-Typ ``projektzeiten`` heisst — also wie die Mehrzahl
des *Zeiteintrags* —, liest sich jede Codestelle doppeldeutig. Genau daran
entstehen Fehler, die beim Lesen nicht auffallen: ``listRecords('projekt-
zeiten')`` sieht aus, als lade es Zeiteintraege.

Die Migration benennt daher nur den Slug um. Datensaetze, Felder, Anhaenge
und Stundenkonten haengen an der ID des Typs und bleiben unberuehrt.

Idempotent: Laeuft die Migration auf einer Installation, die den Typ schon
als ``zeitprojekte`` fuehrt (frische Installation), passiert nichts. Existiert
ausnahmsweise beides, bleibt der bestehende ``zeitprojekte``-Typ unangetastet
und der alte wird nicht angefasst — ein Zusammenfuehren von Datenbestaenden
gehoert nicht in eine Migration.
"""
from alembic import op
import sqlalchemy as sa

revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None

# Reihenfolge = Suchreihenfolge fuer den alten Bestand
ALTE_SLUGS = ('projektzeiten', 'projekte')


def upgrade() -> None:
    conn = op.get_bind()

    neu = conn.execute(sa.text(
        "SELECT id FROM entity_types WHERE slug = 'zeitprojekte'"
    )).first()
    if neu:
        # Schon umbenannt (oder frisch angelegt) — nur den Anzeigenamen
        # sicherstellen, sonst nichts anfassen.
        conn.execute(sa.text(
            "UPDATE entity_types SET name = 'Zeitprojekte' "
            "WHERE slug = 'zeitprojekte' AND name <> 'Zeitprojekte'"
        ))
        return

    for alt in ALTE_SLUGS:
        treffer = conn.execute(sa.text(
            "SELECT id FROM entity_types WHERE slug = :s"
        ), {"s": alt}).first()
        if treffer:
            conn.execute(sa.text(
                "UPDATE entity_types SET slug = 'zeitprojekte', "
                "name = 'Zeitprojekte' WHERE id = :i"
            ), {"i": treffer[0]})
            break

    # Verknuepfungsfelder anderer Typen, die auf den alten Slug zeigen
    # (field_definitions.linked_type_slug), mitziehen — sonst laufen
    # Auswahlfelder nach der Umbenennung ins Leere.
    for alt in ALTE_SLUGS:
        conn.execute(sa.text(
            "UPDATE field_definitions SET linked_type_slug = 'zeitprojekte' "
            "WHERE linked_type_slug = :s"
        ), {"s": alt})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE entity_types SET slug = 'projektzeiten' "
        "WHERE slug = 'zeitprojekte'"
    ))
    conn.execute(sa.text(
        "UPDATE field_definitions SET linked_type_slug = 'projektzeiten' "
        "WHERE linked_type_slug = 'zeitprojekte'"
    ))
