"""
Artikelstamm-Tests — Artikelgruppen, Nummernvergabe, Kontenkaskade.

Deckt ab:
- CRUD der Artikelgruppen inkl. Admin-Schutz und Kontenprüfung
- Automatische Artikelnummer: Vergabe, Fortzählen, Kollisionen, Vorrang der
  von Hand eingetragenen Nummer, Vorschlag ohne Zählerverbrauch
- Kontenkaskade Artikel → Gruppe → Standard-Erlöskonto
- Reverse Charge als Nicht-Steuersatz (nicht als 0 %)
- Schutz der Systemfelder gegen Löschen und Typwechsel

Die Tests bauen ihre Stammdaten selbst auf: Die Testreihe läuft gegen ein per
``Base.metadata.create_all`` erzeugtes Schema, nicht gegen die Migrationen —
die Seed-Daten aus 0056 sind hier also nicht vorhanden.

Gleiche Fixtures wie test_auth.py (siehe tests/conftest.py).
"""
from decimal import Decimal

import pytest

from app.models.accounting import AccountingAccount
from app.models.masterdata import (ArticleGroup, EntityRecord, EntityType,
                                   FieldDefinition)
from app.services import artikelstamm
from tests.conftest import TEST_USER_PASSWORD


# ── Hilfen ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(client, admin_user):
    """Wie `client`, aber mit eingeloggtem Admin (Bearer-Token gesetzt)."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


@pytest.fixture()
def konten(db_session):
    """Ein Minimal-Kontenplan: Standard-Erlöskonto 4000 und Wareneinsatz 5000."""
    eintraege = [
        AccountingAccount(nr="4000", name="Erlöse 20% USt", typ="ertrag",
                          ust_code="U20", is_default_erloes=True),
        AccountingAccount(nr="4020", name="Erlöse 10% USt", typ="ertrag",
                          ust_code="U10"),
        AccountingAccount(nr="5000", name="Wareneinsatz", typ="aufwand"),
    ]
    db_session.add_all(eintraege)
    db_session.commit()
    return eintraege


@pytest.fixture()
def artikel_typ(db_session):
    """Stammdaten-Typ „Artikel" mit den Feldern, die 0056 anlegt."""
    et = EntityType(name="Artikel", slug="artikel", icon="Package", tabs=[])
    db_session.add(et)
    db_session.flush()

    # (Name, Schlüssel, Typ, Sortierung, Systemfeld, eindeutig)
    # Die Sortierung ist nicht Zierde: ``_extract_display_name`` nimmt das
    # erste Textfeld — deshalb muss „bezeichnung" vor „artikelnummer" stehen,
    # genau wie in Migration 0056.
    felder = [
        ("Bezeichnung", "bezeichnung", "text", 10, True, False),
        ("Artikelnummer", "artikelnummer", "text", 20, True, True),
        ("Artikelgruppe", "artikelgruppe", "lookup", 40, True, False),
        ("Preis", "preis", "number", 210, True, False),
        ("USt-Satz", "ust_satz", "dropdown", 230, True, False),
        ("Erlöskonto", "erloes_konto", "lookup", 400, True, False),
        ("Aufwandskonto", "aufwand_konto", "lookup", 410, False, False),
        ("Lagerort", "lagerort", "text", 530, False, False),
    ]
    for name, key, typ, sort_order, system, eindeutig in felder:
        db_session.add(FieldDefinition(
            entity_type_id=et.id, name=name, key=key, field_type=typ,
            sort_order=sort_order, is_system=system, is_unique=eindeutig,
            lookup_source=('konten' if key.endswith('_konto')
                           else 'artikelgruppen' if key == 'artikelgruppe'
                           else None),
        ))
    db_session.commit()
    db_session.refresh(et)
    return et


@pytest.fixture()
def gruppe_dl(db_session, konten):
    """Artikelgruppe „Dienstleistung" mit Erlöskonto 4020."""
    g = ArticleGroup(nr="DL", name="Dienstleistung", praefix="DL", stellen=4,
                     naechste_nummer=1, erloes_konto_nr="4020",
                     ust_satz=Decimal("20.00"), einheit="h",
                     artikelart="dienstleistung")
    db_session.add(g)
    db_session.commit()
    db_session.refresh(g)
    return g


def _artikel_anlegen(client, daten):
    resp = client.post("/api/masterdata/types/artikel/records", json={"data": daten})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Artikelgruppen: CRUD ──────────────────────────────────────────────────────

def test_gruppe_anlegen_und_lesen(admin_client, konten, artikel_typ):
    resp = admin_client.post("/api/masterdata/artikelgruppen", json={
        "nr": "WA", "name": "Ware", "praefix": "WA", "stellen": 4,
        "erloes_konto_nr": "4000", "aufwand_konto_nr": "5000",
        "ust_satz": "20", "einheit": "Stk",
    })
    assert resp.status_code == 200, resp.text
    gruppe = resp.json()
    assert gruppe["nr"] == "WA"
    assert gruppe["erloes_konto_nr"] == "4000"
    # Die Vorschau zeigt, was als Nächstes vergeben wird — ohne zu verbrauchen
    assert gruppe["naechste_artikelnummer"] == "WA-0001"
    assert gruppe["artikel_anzahl"] == 0

    liste = admin_client.get("/api/masterdata/artikelgruppen")
    assert liste.status_code == 200
    assert [g["nr"] for g in liste.json()] == ["WA"]


def test_gruppe_anlegen_nur_admin(auth_client, konten):
    resp = auth_client.post("/api/masterdata/artikelgruppen",
                            json={"nr": "WA", "name": "Ware"})
    assert resp.status_code == 403


def test_gruppe_lesen_ist_fuer_alle_offen(auth_client, gruppe_dl):
    """Auch ohne Adminrechte — die Gruppe ist ein Auswahlfeld im Artikel."""
    resp = auth_client.get("/api/masterdata/artikelgruppen")
    assert resp.status_code == 200
    assert [g["nr"] for g in resp.json()] == ["DL"]


def test_gruppe_lehnt_unbekanntes_konto_ab(admin_client, konten):
    """Ein Tippfehler im Konto fällt beim Speichern auf, nicht erst beim Export."""
    resp = admin_client.post("/api/masterdata/artikelgruppen", json={
        "nr": "WA", "name": "Ware", "erloes_konto_nr": "4999",
    })
    assert resp.status_code == 400
    assert "Kontenplan" in resp.json()["detail"]


def test_gruppe_kurzschluessel_ist_eindeutig(admin_client, konten, gruppe_dl):
    resp = admin_client.post("/api/masterdata/artikelgruppen",
                             json={"nr": "DL", "name": "Doppelt"})
    assert resp.status_code == 409


def test_kurzschluessel_nicht_aenderbar_wenn_artikel_daran_haengen(
        admin_client, artikel_typ, gruppe_dl):
    """Die Artikel speichern den Kurzschlüssel als Wert.

    Ihn umzubenennen würde jeden Artikel von seiner Gruppe abschneiden — ohne
    Fehlermeldung, weil die Kaskade dann einfach auf die Vorgabe zurückfällt.
    """
    _artikel_anlegen(admin_client, {"bezeichnung": "Beratung", "artikelgruppe": "DL"})

    resp = admin_client.put(f"/api/masterdata/artikelgruppen/{gruppe_dl.id}",
                            json={"nr": "BE"})
    assert resp.status_code == 409
    assert "1 Artikel" in resp.json()["detail"]


def test_gruppe_mit_artikeln_nicht_loeschbar(admin_client, artikel_typ, gruppe_dl):
    _artikel_anlegen(admin_client, {"bezeichnung": "Beratung", "artikelgruppe": "DL"})

    resp = admin_client.delete(f"/api/masterdata/artikelgruppen/{gruppe_dl.id}")
    assert resp.status_code == 409
    assert "inaktiv" in resp.json()["detail"]


def test_leere_gruppe_loeschbar(admin_client, artikel_typ, gruppe_dl):
    resp = admin_client.delete(f"/api/masterdata/artikelgruppen/{gruppe_dl.id}")
    assert resp.status_code == 200


# ── Nummernvergabe ────────────────────────────────────────────────────────────

def test_artikelnummer_wird_automatisch_vergeben(admin_client, artikel_typ, gruppe_dl):
    artikel = _artikel_anlegen(admin_client, {"bezeichnung": "Beratung",
                                              "artikelgruppe": "DL"})
    assert artikel["data"]["artikelnummer"] == "DL-0001"


def test_zaehler_laeuft_weiter(admin_client, artikel_typ, gruppe_dl):
    nummern = [
        _artikel_anlegen(admin_client, {"bezeichnung": f"Leistung {i}",
                                        "artikelgruppe": "DL"})["data"]["artikelnummer"]
        for i in range(3)
    ]
    assert nummern == ["DL-0001", "DL-0002", "DL-0003"]


def test_eigene_nummer_hat_vorrang(admin_client, artikel_typ, gruppe_dl, db_session):
    """Wer Altdaten übernimmt, tippt die Nummer — dann bleibt der Zähler stehen."""
    artikel = _artikel_anlegen(admin_client, {
        "bezeichnung": "Altbestand", "artikelgruppe": "DL",
        "artikelnummer": "ALT-42",
    })
    assert artikel["data"]["artikelnummer"] == "ALT-42"

    db_session.refresh(gruppe_dl)
    assert gruppe_dl.naechste_nummer == 1


def test_vergabe_weicht_bestehender_nummer_aus(admin_client, artikel_typ,
                                               gruppe_dl, db_session):
    """DL-0001 ist von Hand vergeben — die Automatik nimmt DL-0002.

    Ohne dieses Ausweichen liefe die Anlage in die Eindeutigkeitsprüfung, und
    zwar beim zweiten Benutzer mit einem Formular voller Eingaben.
    """
    _artikel_anlegen(admin_client, {"bezeichnung": "Von Hand",
                                    "artikelgruppe": "DL",
                                    "artikelnummer": "DL-0001"})

    zweiter = _artikel_anlegen(admin_client, {"bezeichnung": "Automatisch",
                                              "artikelgruppe": "DL"})
    assert zweiter["data"]["artikelnummer"] == "DL-0002"


def test_ohne_gruppe_keine_nummer(admin_client, artikel_typ, gruppe_dl):
    """Der Zähler hängt an der Gruppe — ohne Gruppe gibt es nichts zu zählen."""
    artikel = _artikel_anlegen(admin_client, {"bezeichnung": "Einzelstück"})
    assert not artikel["data"].get("artikelnummer")


def test_vorschlag_verbraucht_den_zaehler_nicht(admin_client, artikel_typ,
                                                gruppe_dl, db_session):
    """Ein geöffnetes und wieder verworfenes Formular darf keine Lücke reißen."""
    for _ in range(3):
        resp = admin_client.get("/api/masterdata/artikel/naechste-nummer",
                                params={"gruppe": "DL"})
        assert resp.status_code == 200
        assert resp.json()["artikelnummer"] == "DL-0001"

    db_session.refresh(gruppe_dl)
    assert gruppe_dl.naechste_nummer == 1


def test_vorschlag_fuer_unbekannte_gruppe(admin_client, artikel_typ):
    resp = admin_client.get("/api/masterdata/artikel/naechste-nummer",
                            params={"gruppe": "XX"})
    assert resp.status_code == 404


def test_doppelte_artikelnummer_wird_abgelehnt(admin_client, artikel_typ, gruppe_dl):
    """``is_unique`` stand seit 0010 an der Felddefinition und wurde nie geprüft.

    Mit der automatischen Vergabe wird daraus ein Erfordernis: Zwei Artikel mit
    derselben Nummer fielen sonst erst im Belegbuch auf.
    """
    _artikel_anlegen(admin_client, {"bezeichnung": "Erster",
                                    "artikelgruppe": "DL",
                                    "artikelnummer": "X-1"})

    resp = admin_client.post("/api/masterdata/types/artikel/records", json={
        "data": {"bezeichnung": "Zweiter", "artikelgruppe": "DL",
                 "artikelnummer": "X-1"},
    })
    assert resp.status_code == 409
    assert "bereits vergeben" in resp.json()["detail"]


def test_eigener_datensatz_kollidiert_nicht_mit_sich_selbst(
        admin_client, artikel_typ, gruppe_dl):
    """Beim Bearbeiten darf die eigene Nummer stehen bleiben."""
    artikel = _artikel_anlegen(admin_client, {"bezeichnung": "Beratung",
                                              "artikelgruppe": "DL",
                                              "artikelnummer": "X-1"})

    resp = admin_client.put(
        f"/api/masterdata/types/artikel/records/{artikel['id']}",
        json={"data": {"bezeichnung": "Beratung neu", "artikelgruppe": "DL",
                       "artikelnummer": "X-1"}})
    assert resp.status_code == 200, resp.text


def test_leere_nummer_ist_nicht_doppelt(admin_client, konten, artikel_typ):
    """Zwei Artikel ohne Nummer sind kein Konflikt — leer ist kein Wert."""
    _artikel_anlegen(admin_client, {"bezeichnung": "Ohne A"})
    zweiter = admin_client.post("/api/masterdata/types/artikel/records", json={
        "data": {"bezeichnung": "Ohne B"}})
    assert zweiter.status_code == 200, zweiter.text


def test_stellen_wirken_auf_die_nummer(admin_client, konten, artikel_typ, db_session):
    gruppe = ArticleGroup(nr="MA", name="Material", praefix="MAT", stellen=6,
                          naechste_nummer=7)
    db_session.add(gruppe)
    db_session.commit()

    artikel = _artikel_anlegen(admin_client, {"bezeichnung": "Schraube",
                                              "artikelgruppe": "MA"})
    assert artikel["data"]["artikelnummer"] == "MAT-000007"


# ── Kontenkaskade ─────────────────────────────────────────────────────────────

def test_kaskade_artikel_gewinnt_gegen_gruppe(db_session, konten, gruppe_dl):
    erloes, _ = artikelstamm.konten_fuer_artikel(
        db_session, {"artikelgruppe": "DL", "erloes_konto": "4000"})
    assert erloes == "4000"


def test_kaskade_faellt_auf_die_gruppe_zurueck(db_session, konten, gruppe_dl):
    erloes, _ = artikelstamm.konten_fuer_artikel(db_session, {"artikelgruppe": "DL"})
    assert erloes == "4020"


def test_kaskade_faellt_auf_das_standardkonto_zurueck(db_session, konten):
    """Weder Artikel noch Gruppe sagen etwas — dann gilt das Standard-Erlöskonto."""
    erloes, _ = artikelstamm.konten_fuer_artikel(db_session, {})
    assert erloes == "4000"


def test_leeres_feld_zaehlt_als_nicht_gesetzt(db_session, konten, gruppe_dl):
    """Ein leeres Formularfeld kommt als "" an, nicht als None.

    Ohne diese Umdeutung bliebe die Kaskade beim Artikel stehen und befragte
    die Gruppe nie — der häufigste Fall wäre der einzige, der nicht ginge.
    """
    erloes, _ = artikelstamm.konten_fuer_artikel(
        db_session, {"artikelgruppe": "DL", "erloes_konto": "   "})
    assert erloes == "4020"


def test_aufwandskonto_hat_keine_stille_vorgabe(db_session, konten, gruppe_dl):
    """Beim Erlös gibt es einen Standard, beim Aufwand bewusst nicht."""
    _, aufwand = artikelstamm.konten_fuer_artikel(db_session, {"artikelgruppe": "DL"})
    assert aufwand is None


def test_vorgaben_endpunkt_liefert_die_kaskade(admin_client, artikel_typ, gruppe_dl):
    artikel = _artikel_anlegen(admin_client, {"bezeichnung": "Beratung",
                                              "artikelgruppe": "DL"})

    resp = admin_client.get(f"/api/masterdata/artikel/{artikel['id']}/vorgaben")
    assert resp.status_code == 200
    v = resp.json()
    assert v["erloes_konto"] == "4020"
    assert Decimal(v["ust_satz"]) == Decimal("20.00")
    assert v["einheit"] == "h"          # von der Gruppe geerbt
    assert v["reverse_charge"] is False


# ── Reverse Charge ────────────────────────────────────────────────────────────

def test_reverse_charge_ist_kein_steuersatz(db_session, konten, gruppe_dl):
    """Reverse Charge heißt: gar kein Satz — nicht 0 %.

    Eine Null erschiene in der UVA als steuerfreier Umsatz und wäre damit
    schlicht falsch. Geprüft wird die *Bedingung* (Satz ist None bei gesetztem
    Kennzeichen), nicht bloß, dass irgendein Wert herauskommt.
    """
    vorgaben = artikelstamm.vorgaben_fuer_artikel(
        db_session, {"artikelgruppe": "DL", "ust_satz": "Reverse Charge"})
    assert vorgaben["reverse_charge"] is True
    assert vorgaben["ust_satz"] is None


def test_null_prozent_bleibt_null_prozent(db_session, konten, gruppe_dl):
    """Gegenprobe: 0 % ist ein echter Satz und darf nicht zu None werden."""
    vorgaben = artikelstamm.vorgaben_fuer_artikel(
        db_session, {"artikelgruppe": "DL", "ust_satz": "0"})
    assert vorgaben["reverse_charge"] is False
    assert vorgaben["ust_satz"] == Decimal("0")


def test_ust_satz_des_artikels_gewinnt(db_session, konten, gruppe_dl):
    vorgaben = artikelstamm.vorgaben_fuer_artikel(
        db_session, {"artikelgruppe": "DL", "ust_satz": "10"})
    assert vorgaben["ust_satz"] == Decimal("10")


# ── Systemfelder ──────────────────────────────────────────────────────────────

def _feld(db_session, artikel_typ, key):
    return (db_session.query(FieldDefinition)
            .filter(FieldDefinition.entity_type_id == artikel_typ.id,
                    FieldDefinition.key == key)
            .one())


def test_systemfeld_nicht_loeschbar(admin_client, db_session, artikel_typ):
    """Der Belegpicker liest preis, einheit und erloes_konto direkt.

    Verschwindet eines davon, kommt im Beleg still eine Null an — ohne
    Fehlermeldung, an der man es merken würde.
    """
    feld = _feld(db_session, artikel_typ, "preis")
    resp = admin_client.delete(f"/api/masterdata/types/artikel/fields/{feld.id}")
    assert resp.status_code == 400
    assert "Systemfeld" in resp.json()["detail"]

    # und es steht noch da
    assert _feld(db_session, artikel_typ, "preis") is not None


def test_normales_feld_bleibt_loeschbar(admin_client, db_session, artikel_typ):
    """Gegenprobe: Der Schutz gilt nur für Systemfelder."""
    feld = _feld(db_session, artikel_typ, "lagerort")
    resp = admin_client.delete(f"/api/masterdata/types/artikel/fields/{feld.id}")
    assert resp.status_code == 200


def test_systemfeld_behaelt_seinen_typ(admin_client, db_session, artikel_typ):
    feld = _feld(db_session, artikel_typ, "preis")
    resp = admin_client.put(f"/api/masterdata/types/artikel/fields/{feld.id}",
                            json={"field_type": "text"})
    assert resp.status_code == 400


def test_systemfeld_laesst_sich_umbenennen(admin_client, db_session, artikel_typ):
    """Umbenennen, verschieben und ausblenden bleibt erlaubt — nur nicht mehr."""
    feld = _feld(db_session, artikel_typ, "preis")
    resp = admin_client.put(f"/api/masterdata/types/artikel/fields/{feld.id}",
                            json={"name": "Verkaufspreis", "show_in_list": False})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Verkaufspreis"


def test_umbenennen_loescht_die_auswahlliste_nicht(admin_client, db_session,
                                                   artikel_typ):
    """Ein Umbenennen darf die Optionen eines Auswahlfeldes nicht leeren.

    Genau das ist passiert: ``update_field`` schreibt ``options`` auch bei
    ``None`` (damit sich eine Liste absichtlich leeren lässt), und der
    Feld-Editor schickt nur Name, Pflicht und Listenanzeige — Pydantic füllte
    den Rest mit ``None``. Eine Umbenennung hat damit lautlos die ganze
    Auswahlliste gelöscht.

    Geprüft wird die *Bedingung* (die Optionen stehen danach noch da), nicht
    bloß, dass der Aufruf mit 200 endet.
    """
    feld = _feld(db_session, artikel_typ, "ust_satz")
    feld.options = ["20", "13", "10", "0", "Reverse Charge"]
    db_session.commit()

    resp = admin_client.put(f"/api/masterdata/types/artikel/fields/{feld.id}",
                            json={"name": "Umsatzsteuer"})
    assert resp.status_code == 200
    assert resp.json()["options"] == ["20", "13", "10", "0", "Reverse Charge"]

    db_session.refresh(feld)
    assert feld.options == ["20", "13", "10", "0", "Reverse Charge"]


def test_auswahlliste_laesst_sich_absichtlich_aendern(admin_client, db_session,
                                                      artikel_typ):
    """Gegenprobe: Wer die Optionen mitschickt, ändert sie auch."""
    feld = _feld(db_session, artikel_typ, "ust_satz")
    feld.options = ["20", "10"]
    db_session.commit()

    resp = admin_client.put(f"/api/masterdata/types/artikel/fields/{feld.id}",
                            json={"options": ["20", "13", "10"]})
    assert resp.status_code == 200
    assert resp.json()["options"] == ["20", "13", "10"]


# ── Neue Feldtypen ────────────────────────────────────────────────────────────

def test_lookup_feld_braucht_eine_quelle(admin_client, artikel_typ):
    resp = admin_client.post("/api/masterdata/types/artikel/fields", json={
        "name": "Nebenkonto", "key": "nebenkonto", "field_type": "lookup",
    })
    assert resp.status_code == 400
    assert "lookup_source" in resp.json()["detail"]


def test_lookup_feld_mit_quelle_wird_angelegt(admin_client, artikel_typ):
    resp = admin_client.post("/api/masterdata/types/artikel/fields", json={
        "name": "Nebenkonto", "key": "nebenkonto", "field_type": "lookup",
        "lookup_source": "konten",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["lookup_source"] == "konten"
    assert resp.json()["is_system"] is False


def test_unbekannte_lookup_quelle_wird_abgelehnt(admin_client, artikel_typ):
    resp = admin_client.post("/api/masterdata/types/artikel/fields", json={
        "name": "Irgendwas", "key": "irgendwas", "field_type": "lookup",
        "lookup_source": "mondphase",
    })
    assert resp.status_code == 400


# ── Bilder ────────────────────────────────────────────────────────────────────

def test_bild_endpunkt_lehnt_fremde_schluessel_ab(admin_client):
    """Ohne Präfix-Prüfung wäre der Endpunkt ein Leseweg auf den ganzen Speicher.

    Wer einen Schlüssel raten kann, bekäme sonst jede Datei — Belege und
    Vertragsanhänge eingeschlossen.
    """
    resp = admin_client.get("/api/masterdata/bild",
                            params={"key": "belege/vertraege/geheim.pdf"})
    assert resp.status_code == 400
