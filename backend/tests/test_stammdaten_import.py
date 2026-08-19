"""
Stammdaten-Import (Etappe 3)
============================

Geprüft wird das, was beim Import schiefgehen kann, ohne dass es auffällt:

* Ein Probelauf, der doch schreibt.
* Ein Abgleich, der die Dublette trotzdem anlegt.
* Ein Wert, der still zu etwas Falschem wird (Datum → 1970, Zahl → 0).
* Ein Aktualisieren, das gepflegte Felder leert, weil sie in der Datei fehlen.

Die Werte-Deutung wird bewusst über den Endpunkt geprüft und nicht nur an der
Funktion: Der Bericht ist das, was der Benutzer sieht, und er muss zur
tatsächlichen Wirkung passen.
"""
from app.core import berechtigungen as B
from app.models.masterdata import EntityRecord, EntityType, FieldDefinition
from app.models.user import PermissionGroup
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _kopf(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD) -> dict:
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _typ_mit_feldern(db, felder=None):
    """Stammdaten-Typ „Prüfkunden“ mit den Feldern anlegen, die gebraucht werden."""
    typ = EntityType(name="Prüfkunden", slug="pruefkunden")
    db.add(typ)
    db.flush()

    vorgabe = [
        dict(name="Firma", key="firma", field_type="text", sort_order=0),
        dict(name="Kundennummer", key="kundennummer", field_type="text", sort_order=1),
        dict(name="Umsatz", key="umsatz", field_type="number", sort_order=2),
        dict(name="Erstkontakt", key="erstkontakt", field_type="date", sort_order=3),
        dict(name="Newsletter", key="newsletter", field_type="checkbox", sort_order=4),
        dict(name="E-Mail", key="email", field_type="email", sort_order=5),
        dict(name="Art", key="art", field_type="dropdown", sort_order=6,
             options=["Kunde", "Lieferant"]),
    ]
    for daten in (felder if felder is not None else vorgabe):
        db.add(FieldDefinition(entity_type_id=typ.id, **daten))
    db.commit()
    db.refresh(typ)
    return typ


def _import(client, kopf, slug="pruefkunden", **body):
    body.setdefault("rows", [])
    return client.post(f"/api/masterdata/types/{slug}/records/import",
                       headers=kopf, json=body)


def _anzahl(db, typ) -> int:
    return db.query(EntityRecord).filter_by(entity_type_id=typ.id).count()


# ── Werte deuten ─────────────────────────────────────────────────────────────

def test_zahlen_und_datum_werden_oesterreichisch_gelesen(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=False, rows=[
        {"firma": "Musterbau", "umsatz": "1.234,56", "erstkontakt": "31.12.2026"},
    ])
    assert resp.status_code == 200, resp.text
    assert resp.json()["angelegt"] == 1

    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    assert satz.data["umsatz"] == 1234.56
    assert satz.data["erstkontakt"] == "2026-12-31"


def test_maschinelle_schreibweise_geht_auch(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, dry_run=False, rows=[
        {"firma": "Zweitbau", "umsatz": "1234.56", "erstkontakt": "2026-12-31"},
    ])
    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    assert satz.data["umsatz"] == 1234.56
    assert satz.data["erstkontakt"] == "2026-12-31"


def test_unlesbare_werte_werden_beanstandet_statt_geraten(client, test_user, db_session):
    """Der eigentliche Zweck der Prüfung.

    Ein „ungefähr“ gedeutetes Datum fällt erst auf, wenn Monate später
    Auswertungen nicht stimmen — dann ist die Quelldatei längst weg.
    """
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, rows=[
        {"firma": "Krumm", "umsatz": "etwa dreitausend", "erstkontakt": "irgendwann"},
    ])
    assert resp.status_code == 200, resp.text
    gruende = [b["grund"] for b in resp.json()["beanstandungen"]]
    assert any("Zahl" in g for g in gruende)
    assert any("Datum" in g for g in gruende)
    assert _anzahl(db_session, typ) == 0


def test_auswahlfeld_vereinheitlicht_die_schreibweise(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, dry_run=False,
            rows=[{"firma": "Klein", "art": "kunde"}])
    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    # Gespeichert wird die Vorgabe aus der Auswahlliste, nicht die Eingabe —
    # sonst stehen „Kunde“ und „kunde“ getrennt in jedem Filter.
    assert satz.data["art"] == "Kunde"


def test_wert_ausserhalb_der_auswahlliste_wird_beanstandet(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, rows=[{"firma": "Klein", "art": "Interessent"}])
    assert resp.json()["beanstandungen"], resp.text
    assert _anzahl(db_session, typ) == 0


def test_ja_nein_versteht_die_ueblichen_schreibweisen(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, dry_run=False, rows=[
        {"firma": "A", "newsletter": "ja"},
        {"firma": "B", "newsletter": "Nein"},
        {"firma": "C", "newsletter": "X"},
    ])
    werte = {s.data["firma"]: s.data["newsletter"]
             for s in db_session.query(EntityRecord).filter_by(entity_type_id=typ.id)}
    assert werte == {"A": True, "B": False, "C": True}


def test_pflichtfeld_leer_wird_beanstandet(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session, felder=[
        dict(name="Firma", key="firma", field_type="text", is_required=True,
             sort_order=0),
    ])
    kopf = _kopf(client)

    resp = _import(client, kopf, rows=[{"firma": ""}])
    assert resp.json()["beanstandungen"][0]["grund"] == "Pflichtfeld ist leer"
    assert _anzahl(db_session, typ) == 0


# ── Probelauf ────────────────────────────────────────────────────────────────

def test_probelauf_schreibt_nichts(client, test_user, db_session):
    """Der Bericht darf den Bestand nicht anfassen — sonst ist die Zusage
    „nichts wird geschrieben, bevor du das gesehen hast“ gebrochen."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=True, rows=[
        {"firma": "Vorschau", "umsatz": "100"},
        {"firma": "Zweite", "umsatz": "200"},
    ])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["geprueft"] == 2
    assert body["anlegen"] == 2
    assert body["angelegt"] == 0
    assert _anzahl(db_session, typ) == 0


def test_probelauf_ist_die_vorgabe(client, test_user, db_session):
    """Ohne ausdrückliches dry_run=false wird nicht geschrieben."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, rows=[{"firma": "Ohne Angabe"}])
    assert _anzahl(db_session, typ) == 0


# ── Abgleich statt Dubletten ─────────────────────────────────────────────────

def test_abgleich_aktualisiert_statt_dublette(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, dry_run=False, match_field="kundennummer",
            rows=[{"firma": "Musterbau", "kundennummer": "K-1", "umsatz": "100"}])
    assert _anzahl(db_session, typ) == 1

    resp = _import(client, kopf, dry_run=False, match_field="kundennummer",
                   rows=[{"firma": "Musterbau GmbH", "kundennummer": "K-1",
                          "umsatz": "200"}])
    assert resp.json()["aktualisiert"] == 1
    assert resp.json()["angelegt"] == 0
    assert _anzahl(db_session, typ) == 1

    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    assert satz.data["umsatz"] == 200
    assert satz.data["firma"] == "Musterbau GmbH"
    assert satz.display_name == "Musterbau GmbH"


def test_ohne_abgleichsfeld_entsteht_die_dublette(client, test_user, db_session):
    """Das alte Verhalten bleibt erhalten, wenn kein Schlüssel gewählt wird —
    dokumentiert, damit es eine bewusste Wahl bleibt und keine Überraschung."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    for _ in range(2):
        _import(client, kopf, dry_run=False,
                rows=[{"firma": "Musterbau", "kundennummer": "K-1"}])
    assert _anzahl(db_session, typ) == 2


def test_aktualisieren_laesst_nicht_zugeordnete_felder_stehen(client, test_user,
                                                              db_session):
    """Eine Datei mit nur zwei Spalten darf nicht alles andere leeren."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    _import(client, kopf, dry_run=False, match_field="kundennummer",
            rows=[{"firma": "Musterbau", "kundennummer": "K-1",
                   "email": "alt@beispiel.at"}])

    _import(client, kopf, dry_run=False, match_field="kundennummer",
            rows=[{"kundennummer": "K-1", "umsatz": "500"}])

    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    assert satz.data["email"] == "alt@beispiel.at"
    assert satz.data["umsatz"] == 500


def test_doppelter_schluessel_in_der_datei_wird_beanstandet(client, test_user,
                                                            db_session):
    """Sonst gewinnt beim Abgleich die letzte Zeile und die davor verschwindet."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, match_field="kundennummer", rows=[
        {"firma": "Erste", "kundennummer": "K-1"},
        {"firma": "Zweite", "kundennummer": "K-1"},
    ])
    beanstandet = resp.json()["beanstandungen"]
    assert len(beanstandet) == 1
    assert beanstandet[0]["zeile"] == 2
    assert "Zeile 1" in beanstandet[0]["grund"]


def test_leerer_schluessel_wird_beanstandet(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, match_field="kundennummer",
                   rows=[{"firma": "Ohne Nummer", "kundennummer": ""}])
    assert "Abgleichsfeld ist leer" in resp.json()["beanstandungen"][0]["grund"]


def test_unbekanntes_abgleichsfeld_wird_abgewiesen(client, test_user, db_session):
    _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, match_field="gibtsnicht",
                   rows=[{"firma": "Egal"}])
    assert resp.status_code == 400


# ── Umgang mit beanstandeten Zeilen ──────────────────────────────────────────

def test_ohne_zusage_wird_bei_beanstandungen_nichts_geschrieben(client, test_user,
                                                                db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=False, rows=[
        {"firma": "Gut", "umsatz": "100"},
        {"firma": "Krumm", "umsatz": "keine Zahl"},
    ])
    assert resp.json()["angelegt"] == 0
    assert _anzahl(db_session, typ) == 0


def test_mit_zusage_wird_der_rest_geschrieben(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=False, skip_invalid=True, rows=[
        {"firma": "Gut", "umsatz": "100"},
        {"firma": "Krumm", "umsatz": "keine Zahl"},
        {"firma": "Auch gut", "umsatz": "300"},
    ])
    body = resp.json()
    assert body["angelegt"] == 2
    assert body["uebersprungen"] == 1
    assert _anzahl(db_session, typ) == 2


def test_nicht_zugeordnete_spalten_stoeren_nicht(client, test_user, db_session):
    """Der Assistent lässt Spalten bewusst weg — das ist kein Fehler."""
    typ = _typ_mit_feldern(db_session)
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=False,
                   rows=[{"firma": "Musterbau", "unbekannt": "egal"}])
    assert resp.json()["angelegt"] == 1
    satz = db_session.query(EntityRecord).filter_by(entity_type_id=typ.id).one()
    assert "unbekannt" not in satz.data


# ── Rechte ───────────────────────────────────────────────────────────────────

def test_import_verlangt_schreibrecht(client, test_user, db_session):
    typ = _typ_mit_feldern(db_session)
    blatt = B.leeres_rechteblatt()
    blatt["stammdaten"].update({"lesen": True, "umfang": "alle"})
    gruppe = PermissionGroup(name="Stammdaten nur ansehen", rechte=blatt)
    db_session.add(gruppe)
    test_user.groups = [gruppe]
    db_session.commit()
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=False, rows=[{"firma": "Verboten"}])
    assert resp.status_code == 403
    assert _anzahl(db_session, typ) == 0


def test_probelauf_verlangt_ebenfalls_schreibrecht(client, test_user, db_session):
    """Auch der Probelauf bleibt gesperrt: Er verrät sonst über die
    Beanstandungen, welche Datensätze es bereits gibt."""
    _typ_mit_feldern(db_session)
    blatt = B.leeres_rechteblatt()
    blatt["stammdaten"].update({"lesen": True, "umfang": "alle"})
    gruppe = PermissionGroup(name="Nur ansehen", rechte=blatt)
    db_session.add(gruppe)
    test_user.groups = [gruppe]
    db_session.commit()
    kopf = _kopf(client)

    resp = _import(client, kopf, dry_run=True, rows=[{"firma": "Verboten"}])
    assert resp.status_code == 403


def test_unbekannter_typ_liefert_404(client, test_user, db_session):
    kopf = _kopf(client)
    resp = _import(client, kopf, slug="gibtsnicht", rows=[{"firma": "Egal"}])
    assert resp.status_code == 404
