"""Steuerfall am Kontakt und Erlöskonten je Steuerfall

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-31

Dritte Etappe des Artikelstamm-Ausbaus: Das Erlöskonto hängt künftig nicht nur
davon ab, *was* verkauft wird, sondern auch *an wen*.

Der Befund
----------
Im BMD-Export bestimmte sich das Erlöskonto als ``pos.account_nr or
default_erloes`` und der USt-Code allein aus dem Steuersatz. Die Konten 4040
(steuerbefreit), 4050 (innergemeinschaftlich) und 4060 (Reverse Charge) stehen
seit Migration 0013 im Kontenplan, wurden aber nur bebucht, wenn jemand sie an
*jeder einzelnen Position* von Hand eintrug. Eine innergemeinschaftliche
Lieferung landete sonst auf 4000, dem Inlandserlöskonto — und zwar
stillschweigend.

Das ist kein Bedienkomfort, sondern eine Unrichtigkeit in den Büchern.
Zusätzlich hält ``services/tax_rates.py`` fest, dass die UVA-Kennzahl für
steuerfreie Umsätze bewusst nicht geraten wird, weil sie vom Sachverhalt
abhängt: Ausfuhr, innergemeinschaftliche Lieferung und Reverse Charge laufen
über verschiedene Kennzahlen. Genau diesen Sachverhalt macht der Steuerfall
benennbar.

Was diese Migration anlegt
--------------------------
1. Feld ``steuerfall`` am Stammdaten-Typ „Kontakte", Register „Finanz", als
   Auswahlliste mit den vier Fällen. Als Systemfeld, weil die Kontenfindung es
   liest.
2. Tabelle ``article_group_accounts`` — je Artikelgruppe und Steuerfall ein
   Erlöskonto und eine Steuerangabe.
3. Startbelegung für die vorhandenen Artikelgruppen aus den EKR-Konten, sofern
   sie im Kontenplan stehen.

Bestandsdaten
-------------
Nichts ändert sich rückwirkend. Kontakte ohne Angabe gelten als Inland — das
ist genau das bisherige Verhalten. Bereits ausgestellte Belege behalten ihre
Konten, die stehen an der Position.

Die Vorgabe „Inland" ist bewusst gewählt: Wer fälschlich Inland bucht, zahlt zu
viel Steuer — wer fälschlich steuerfrei bucht, schuldet sie nach. Von den
beiden möglichen Irrtümern ist nur der erste schmerzlos heilbar.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


# (Kennung, Anzeigename) — Spiegel von services/steuerfall.py. Bewusst hier
# wiederholt statt importiert: Eine Migration muss auch dann noch laufen, wenn
# der Anwendungscode sich weiterentwickelt hat.
STEUERFAELLE = [
    ('inland',         'Inland'),
    ('ig_lieferung',   'Innergemeinschaftliche Lieferung'),
    ('drittland',      'Ausfuhr (Drittland)'),
    ('reverse_charge', 'Reverse Charge'),
]

# Startbelegung je Steuerfall: (Steuerfall, Kontonummer, USt-Satz, ohne Steuer)
#
# ``inland`` bekommt **keinen** Satz: Ob 20, 13 oder 10 gilt, hängt am Artikel,
# nicht am Kunden. Ein hier eingetragener Satz würde jeden ermäßigten Artikel
# auf den Normalsatz zwingen.
#
# ``ig_lieferung`` und ``drittland`` sind echt steuerbefreit — Satz null, damit
# sie in der Voranmeldung mit Bemessungsgrundlage erscheinen.
#
# ``reverse_charge`` hat gar keinen Satz. Eine Null würde den Umsatz als
# steuerfreien Umsatz ausweisen statt als übergegangene Steuerschuld.
STARTBELEGUNG = [
    ('inland',         '4000', None,  False),
    ('ig_lieferung',   '4050', '0',   False),
    ('drittland',      '4040', '0',   False),
    ('reverse_charge', '4060', None,  True),
]


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Steuerfall am Kontakt ─────────────────────────────────────────────
    optionen = '["' + '", "'.join(name for _, name in STEUERFAELLE) + '"]'
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             is_unique, show_in_list, sort_order, col_span, tab,
             options, default_value, is_system, created_at)
        SELECT gen_random_uuid(), et.id,
               'Steuerfall', 'steuerfall', 'dropdown',
               false, false, false, 26, 4, 'Finanz',
               CAST(:optionen AS jsonb), 'Inland', true, NOW()
        FROM entity_types et
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd
              WHERE fd.entity_type_id = et.id AND fd.key = 'steuerfall'
          )
    """), {"optionen": optionen})

    # ── 2. Konten je Steuerfall ──────────────────────────────────────────────
    op.create_table(
        'article_group_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('article_group_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('article_groups.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('steuerfall', sa.String(30), nullable=False),
        sa.Column('konto_nr', sa.String(20), nullable=True),
        sa.Column('ust_satz', sa.Numeric(5, 2), nullable=True),
        sa.Column('ohne_steuer', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Je Gruppe höchstens eine Zeile pro Steuerfall. Zwei Zeilen für
        # denselben Fall wären nicht bloß unschön: Welche gilt, entschiede die
        # Reihenfolge der Abfrage — also der Zufall.
        sa.UniqueConstraint('article_group_id', 'steuerfall',
                            name='uq_article_group_steuerfall'),
    )

    # ── 3. Startbelegung für vorhandene Gruppen ──────────────────────────────
    # Nur für Konten, die im Kontenplan tatsächlich stehen: In einem umgebauten
    # Kontenplan bleibt die Zeile lieber leer als falsch — die Kaskade fällt
    # dann auf das Gruppenkonto zurück, also auf das bisherige Verhalten.
    for fall, konto, satz, ohne in STARTBELEGUNG:
        conn.execute(sa.text("""
            INSERT INTO article_group_accounts
                (id, article_group_id, steuerfall, konto_nr, ust_satz, ohne_steuer)
            SELECT gen_random_uuid(), g.id, :fall,
                   (SELECT nr FROM accounting_accounts WHERE nr = :konto),
                   CAST(:satz AS numeric), :ohne
            FROM article_groups g
            WHERE EXISTS (SELECT 1 FROM accounting_accounts WHERE nr = :konto)
              AND NOT EXISTS (
                  SELECT 1 FROM article_group_accounts a
                  WHERE a.article_group_id = g.id AND a.steuerfall = :fall
              )
        """), {"fall": fall, "konto": konto, "satz": satz, "ohne": ohne})


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_table('article_group_accounts')
    conn.execute(sa.text("""
        DELETE FROM field_definitions fd
        USING entity_types et
        WHERE fd.entity_type_id = et.id
          AND et.slug = 'kontakte'
          AND fd.key = 'steuerfall'
    """))
