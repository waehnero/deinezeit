"""Standard-Aufwandskonto am Lieferanten

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-31

Zweite Etappe des Artikelstamm-Ausbaus — die Einkaufsseite.

Ausgangslage
------------
Die Eingangsrechnung führt seit jeher ein einziges ``account_nr`` am Belegkopf,
und im Formular war das ein **freies Textfeld** mit dem Platzhalter „z.B. 7600"
— eine Kontonummer, die im mitgelieferten EKR gar nicht vorkommt. Wer eine
Lieferantenrechnung erfasste, musste die Kontonummer auswendig wissen und
richtig tippen; ein Zahlendreher fiel erst beim Export an die Buchhaltung auf.

Warum kein Artikelbezug
-----------------------
Ursprünglich war für diese Etappe geplant, das Aufwandskonto des Artikels in
die Eingangsrechnung durchzureichen — analog zum Erlöskonto im Verkauf. Beim
Bauen zeigte sich, dass ``PurchaseInvoice`` **keine Positionen** hat: Es gibt
im Einkauf nichts, woran ein Artikel hängen könnte. Positionen für den Einkauf
einzuführen wäre ein eigenes großes Vorhaben (Wareneingang, Lagerzugang,
Summenlogik) und nicht das Anhängsel, als das es geplant war.

Beschlossen wurde deshalb am 31.08.2026 der kleine, sofort nützliche Weg: das
Konto hängt am **Lieferanten**. Das deckt den Alltag ab, weil ein Lieferant
fast immer auf dasselbe Konto gebucht wird — und es entspricht der
Lieferanten-Kontengruppe bei SelectLine, nur ohne deren Steuerfall-Matrix.

Was diese Migration anlegt
--------------------------
Ein Feld ``aufwand_konto`` am Stammdaten-Typ „Kontakte", Register „Finanz",
direkt nach der Kreditornummer. Feldtyp ``lookup`` mit Quelle ``konten`` — der
Typ kam mit 0056 dazu und füllt die Auswahl aus dem Kontenplan, statt eine
Nummer tippen zu lassen.

Als Systemfeld gekennzeichnet: Der Einkauf liest es beim Anlegen einer
Eingangsrechnung. Verschwände es, käme die Vorbelegung wortlos nicht mehr —
dieselbe Überlegung wie bei den Artikelfeldern in 0056.
"""
from alembic import op
import sqlalchemy as sa

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Register „Finanz" gibt es am Kontakt seit Migration 0013 (Debitor- und
    # Kreditornummer, sort_order 23 und 24). Das Konto gehört daneben.
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             is_unique, show_in_list, sort_order, col_span, tab,
             lookup_source, is_system, created_at)
        SELECT gen_random_uuid(), et.id,
               'Standard-Aufwandskonto', 'aufwand_konto', 'lookup',
               false, false, false, 25, 4, 'Finanz',
               'konten', true, NOW()
        FROM entity_types et
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd
              WHERE fd.entity_type_id = et.id AND fd.key = 'aufwand_konto'
          )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    # Die Werte in ``entity_records.data`` bleiben stehen — sie stören nicht
    # und wären beim erneuten Hochmigrieren wieder da. Bereits erfasste
    # Eingangsrechnungen behalten ihr Konto ohnehin, es steht am Beleg.
    conn.execute(sa.text("""
        DELETE FROM field_definitions fd
        USING entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'kontakte'
          AND fd.key = 'aufwand_konto'
    """))
