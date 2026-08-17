"""Rechtegruppen mit Lesen/Schreiben/Löschen je Modul

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-17

Zweite Etappe der Sicherheits-Überarbeitung. Ersetzt die reine
An/Aus-Modulfreigabe (``users.allowed_modules``) durch Gruppen mit
abgestuften Rechten.

Was vorher fehlte
-----------------
* **Kein Unterschied zwischen Ansehen und Ändern.** Wer Rechnungen sehen
  durfte, durfte sie auch stornieren; die einzige Abhilfe war, das ganze
  Modul zu sperren.
* **Keine Bündelung.** Zwölf Mitarbeiter mit gleicher Tätigkeit hießen zwölfmal
  dieselbe Klickarbeit — und beim dreizehnten fiel nicht auf, dass ein Häkchen
  fehlte.

Neu
---
* ``permission_groups`` — Gruppe mit Rechteblatt als JSONB
  (je Modul ``lesen``/``schreiben``/``loeschen`` plus ``umfang``).
* ``user_groups`` — Zuordnung, ein Benutzer kann in mehreren Gruppen sein
  (Rechte addieren sich).
* ``users.permission_overrides`` — individuelle Abweichungen; ein Entzug hier
  gewinnt gegen jede Gruppe.

Übernahme des Bestands (Beschluss 17.08.2026)
---------------------------------------------
Für **jede vorkommende Kombination** aus ``allowed_modules`` wird eine Gruppe
angelegt und die betroffenen Benutzer werden ihr zugeordnet. Niemand gewinnt
oder verliert dabei ein Recht: Die alten Freigaben kannten kein
Lesen/Schreiben-Gefälle, also werden alle drei Rechte gesetzt und der Umfang
auf ``alle``. Alles andere wäre eine stille Rechteänderung an lebenden Konten.

Die so entstandenen Gruppen heißen nach ihrem Inhalt („Zeiterfassung,
Aufgaben"). Das ist absichtlich nüchtern — sie sollen umbenannt und
zusammengelegt werden; ein erfundener Name wie „Team 2" würde sich dagegen
festsetzen.

``allowed_modules`` bleibt erhalten. Die Spalte ist der Rückfall für Benutzer
ohne Gruppe und macht die Übernahme im Nachhinein prüfbar. Wer sie später
entfernen will, sollte vorher bestätigen, dass jeder aktive Benutzer in
mindestens einer Gruppe ist.

Mitgelieferte Gruppen: Administratoren, Mitarbeiter, Buchhaltung. Sie sind als
``ist_system`` gekennzeichnet — änderbar und umbenennbar, aber nicht löschbar,
damit eine Installation nicht ohne jede Gruppe dasteht.
"""
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None

# Muss zu core/modules.MODULE_KEYS passen. Hier bewusst kopiert und nicht
# importiert: Eine Migration beschreibt einen Zustand zu einem Zeitpunkt. Zieht
# sie ihre Werte aus dem laufenden Code, ändert sich ihr Ergebnis rückwirkend,
# sobald später ein Modul hinzukommt — und ein alter Datenbestand ließe sich
# nicht mehr reproduzierbar hochziehen.
MODULE = ("dashboard", "zeiterfassung", "aufgaben", "projekte", "verkauf",
          "buchhaltung", "postecke", "stammdaten", "datacenter")
NUR_LESEN = {"dashboard"}
MODUL_LABELS = {
    "dashboard": "Dashboard", "zeiterfassung": "Zeiterfassung",
    "aufgaben": "Aufgaben", "projekte": "Projekte", "verkauf": "Verkauf",
    "buchhaltung": "Buchhaltung", "postecke": "Postecke",
    "stammdaten": "Stammdaten", "datacenter": "Datacenter",
}


def _blatt(module, umfang="alle"):
    """Rechteblatt: für die genannten Module alle Rechte, sonst keine."""
    blatt = {}
    for modul in MODULE:
        rechte = ("lesen",) if modul in NUR_LESEN else ("lesen", "schreiben", "loeschen")
        erlaubt = modul in module
        blatt[modul] = {r: erlaubt for r in rechte}
        blatt[modul]["umfang"] = umfang if erlaubt else "eigene"
    return blatt


def upgrade():
    # ── Tabellen ──────────────────────────────────────────────────────────────
    op.create_table(
        'permission_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False, unique=True),
        sa.Column('beschreibung', sa.String(length=500), nullable=True),
        sa.Column('rechte', postgresql.JSONB(), nullable=False),
        sa.Column('ist_system', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )

    op.create_table(
        'user_groups',
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('group_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('permission_groups.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_user_groups_group_id', 'user_groups', ['group_id'])

    op.add_column('users', sa.Column('permission_overrides',
                                     postgresql.JSONB(), nullable=True))

    bind = op.get_bind()

    def gruppe_anlegen(name, beschreibung, blatt, ist_system, sort_order):
        gid = uuid.uuid4()
        bind.execute(sa.text("""
            INSERT INTO permission_groups
                   (id, name, beschreibung, rechte, ist_system, sort_order)
            VALUES (:id, :name, :beschreibung, CAST(:rechte AS jsonb),
                    :ist_system, :sort_order)
        """), {"id": gid, "name": name, "beschreibung": beschreibung,
               "rechte": json.dumps(blatt), "ist_system": ist_system,
               "sort_order": sort_order})
        return gid

    # ── Mitgelieferte Gruppen ─────────────────────────────────────────────────
    g_admin = gruppe_anlegen(
        "Administratoren",
        "Vollzugriff auf alle Module einschließlich Benutzer- und "
        "Rechteverwaltung.",
        _blatt(MODULE), True, 10)

    g_mitarbeiter = gruppe_anlegen(
        "Mitarbeiter",
        "Zeiterfassung, Aufgaben und Projekte — jeweils die eigenen "
        "Datensätze. Stammdaten und Dashboard nur zum Ansehen.",
        {
            **_blatt(("zeiterfassung", "aufgaben", "projekte"), umfang="eigene"),
            "dashboard":  {"lesen": True, "umfang": "eigene"},
            "stammdaten": {"lesen": True, "schreiben": False,
                           "loeschen": False, "umfang": "alle"},
            "datacenter": {"lesen": True, "schreiben": True,
                           "loeschen": False, "umfang": "alle"},
        },
        True, 20)

    g_buchhaltung = gruppe_anlegen(
        "Buchhaltung",
        "Verkauf und Buchhaltung mit Schreibrecht, Stammdaten pflegen. "
        "Löschen von Belegen bleibt bewusst außen vor.",
        {
            **_blatt(("verkauf", "buchhaltung", "stammdaten", "datacenter")),
            "dashboard": {"lesen": True, "umfang": "alle"},
            # Belege werden storniert, nicht gelöscht — dieses Recht gehört
            # nicht zur täglichen Arbeit und ist hier ausdrücklich nicht gesetzt.
            "verkauf":     {"lesen": True, "schreiben": True,
                            "loeschen": False, "umfang": "alle"},
            "buchhaltung": {"lesen": True, "schreiben": True,
                            "loeschen": False, "umfang": "alle"},
        },
        True, 30)

    # ── Bestandsübernahme ─────────────────────────────────────────────────────
    # Administratoren zuerst: Sie hatten ohnehin immer alles.
    bind.execute(sa.text("""
        INSERT INTO user_groups (user_id, group_id)
        SELECT id, :gid FROM users WHERE role = 'admin'
        ON CONFLICT DO NOTHING
    """), {"gid": g_admin})

    # Alle übrigen nach ihrer bisherigen Modulkombination gruppieren.
    zeilen = bind.execute(sa.text("""
        SELECT id, allowed_modules FROM users WHERE role <> 'admin'
    """)).fetchall()

    bekannte: dict[tuple, uuid.UUID] = {}
    for zeile in zeilen:
        rohliste = zeile.allowed_modules
        if rohliste is None:
            # NULL hieß „alle Module erlaubt".
            schluessel = ("__alle__",)
            module = tuple(MODULE)
        else:
            module = tuple(sorted(m for m in rohliste if m in MODULE))
            schluessel = module

        if schluessel not in bekannte:
            if schluessel == ("__alle__",):
                name = "Alle Module (übernommen)"
                beschreibung = ("Aus der bisherigen Einstellung „alle Module "
                                "erlaubt“ übernommen. Bitte prüfen und bei "
                                "Bedarf einschränken.")
            elif not module:
                name = "Kein Modulzugriff (übernommen)"
                beschreibung = ("Diese Benutzer hatten bisher keinen "
                                "Modulzugriff.")
            else:
                bezeichnungen = ", ".join(MODUL_LABELS[m] for m in module)
                name = f"{bezeichnungen} (übernommen)"[:100]
                beschreibung = ("Aus den bisherigen Einzelrechten übernommen. "
                                "Name und Rechte können angepasst werden.")
            bekannte[schluessel] = gruppe_anlegen(
                name, beschreibung, _blatt(module), False, 100)

        bind.execute(sa.text("""
            INSERT INTO user_groups (user_id, group_id)
            VALUES (:uid, :gid) ON CONFLICT DO NOTHING
        """), {"uid": zeile.id, "gid": bekannte[schluessel]})

    print(f"[0055] Rechtegruppen angelegt: 3 mitgeliefert, "
          f"{len(bekannte)} aus dem Bestand übernommen.")


def downgrade():
    # allowed_modules wurde nie überschrieben, die alten Rechte sind also
    # unverändert vorhanden — der Rückbau verliert nur die Gruppen selbst und
    # damit die feinere Abstufung.
    op.drop_column('users', 'permission_overrides')
    op.drop_index('ix_user_groups_group_id', table_name='user_groups')
    op.drop_table('user_groups')
    op.drop_table('permission_groups')
