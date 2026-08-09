"""
Tests für Anzahlungs-, Teil- und Schlussrechnung (C-10).

Der teuerste Fehler in diesem Bereich ist unsichtbar: Wird die Anzahlung in
der Schlussrechnung nicht abgezogen, führt man dieselbe Umsatzsteuer zweimal
ab. Nichts stürzt ab, keine Summe sieht falsch aus — es fällt erst bei einer
Prüfung auf. Deshalb liegt der Schwerpunkt dieser Tests auf der UVA über den
gesamten Vorgang, nicht auf den Beträgen des einzelnen Belegs.

Entscheidungen, die hier festgehalten werden:

  * Die Abrechnungsstufe ist ein **Feld an der Rechnung**, keine eigene
    Belegart — sonst fiele eine Anzahlungsrechnung aus UVA, Zahlungen und
    Mahnwesen heraus, weil dort auf ``doc_type == "rechnung"`` geprüft wird.
  * Abgezogen wird alles **Fakturierte**, nicht das Bezahlte.
  * Je Steuersatz eine eigene Abzugszeile.

Schema analog zu test_verkauf_uva.py.
"""
from decimal import Decimal

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.services import anzahlung as anzahlung_service


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Bauherr GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data={"email": "buero@bauherr.at", "uid": "ATU12345678"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create(client, contact_id, doc_type="angebot", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Sanierung Dachgeschoss"),
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Gesamtleistung laut Leistungsverzeichnis",
            "quantity": "1", "unit_price": "10000", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ausstellen(client, invoice_id, status="offen"):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _anzahlung(client, quelle_id, **body):
    resp = client.post(f"/api/invoices/{quelle_id}/anzahlung", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _schluss(client, beleg_id, **body):
    resp = client.post(f"/api/invoices/{beleg_id}/schlussrechnung", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _uva(client, **params):
    resp = client.get("/api/invoices/uva", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _zeile(daten, kennzahl):
    treffer = [z for z in daten["zeilen"] if z["kennzahl"] == kennzahl]
    assert treffer, f"Keine Zeile mit Kennzahl {kennzahl} in {daten['zeilen']}"
    return treffer[0]


def _abzugszeilen(beleg):
    return [p for p in beleg["positions"] if p["pos_type"] == "advance_deduction"]


# ── Die Anzahlung entsteht ────────────────────────────────────────────────────

def test_prozent_wird_in_einen_betrag_umgerechnet(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    rechnung = _anzahlung(auth_client, angebot["id"], percent="30")

    assert rechnung["doc_type"] == "rechnung"
    assert rechnung["billing_stage"] == "anzahlung"
    assert Decimal(rechnung["subtotal"]) == Decimal("3000.00")     # 30 % von 10.000
    assert Decimal(rechnung["total"]) == Decimal("3600.00")        # + 20 % USt.
    assert Decimal(rechnung["advance_percent"]) == Decimal("30.00")


def test_fester_betrag_geht_auch(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    rechnung = _anzahlung(auth_client, angebot["id"], amount="2500")
    assert Decimal(rechnung["subtotal"]) == Decimal("2500.00")
    assert rechnung["advance_percent"] is None


def test_prozent_und_betrag_zugleich_abgelehnt(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/anzahlung",
                            json={"percent": "30", "amount": "2500"})
    assert resp.status_code == 400
    assert "nicht beides" in resp.json()["detail"]


def test_anzahlung_ueber_der_auftragssumme_abgelehnt(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/anzahlung",
                            json={"amount": "12000"})
    assert resp.status_code == 400
    assert "übersteigt" in resp.json()["detail"]


def test_gemischte_steuersaetze_werden_nicht_geraten(auth_client, db_session):
    """
    Welcher Satz für eine Anzahlung auf einen gemischten Auftrag gilt, ist eine
    steuerliche Frage. Die Software bricht ab, statt sich einen auszusuchen.
    """
    angebot = _create(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Bauleistung", "quantity": "1",
         "unit_price": "8000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung Monteure", "quantity": "1",
         "unit_price": "2000", "tax_rate": "13"},
    ])
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/anzahlung",
                            json={"percent": "30"})
    assert resp.status_code == 400
    assert "mehrere Steuersätze" in resp.json()["detail"]


def test_anzahlung_nur_aus_angebot_oder_ab(auth_client, db_session):
    rechnung = _create(auth_client, _make_kontakt(db_session).id, doc_type="rechnung")
    resp = auth_client.post(f"/api/invoices/{rechnung['id']}/anzahlung",
                            json={"percent": "30"})
    assert resp.status_code == 400


def test_stufe_gibt_es_nur_an_der_rechnung(auth_client, db_session):
    """Ein Angebot mit der Stufe „Schlussrechnung" würde im Abzug mitzählen."""
    resp = auth_client.post("/api/invoices", json={
        "doc_type": "angebot", "contact_id": str(_make_kontakt(db_session).id),
        "date": "2026-07-06", "delivery_date": "2026-07-06",
        "billing_stage": "schluss",
        "positions": [{"pos_type": "item", "description": "X", "quantity": "1",
                       "unit_price": "100", "tax_rate": "20"}],
    })
    assert resp.status_code == 400


# ── Der Strang ────────────────────────────────────────────────────────────────

def test_angebot_und_anzahlung_haengen_zusammen(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    rechnung = _anzahlung(auth_client, angebot["id"], percent="30")

    # Der Kopf zeigt auf sich selbst — sonst bräuchte jede Abfrage einen
    # Sonderfall für den ersten Beleg.
    assert rechnung["chain_id"] == angebot["id"]
    strang = auth_client.get(f"/api/invoices/{rechnung['id']}/chain").json()
    assert {b["id"] for b in strang["belege"]} == {angebot["id"], rechnung["id"]}


def test_beleg_ohne_strang_liefert_leere_antwort(auth_client, db_session):
    """Die Oberfläche soll den Abschnitt ohne Fallunterscheidung einblenden."""
    rechnung = _create(auth_client, _make_kontakt(db_session).id, doc_type="rechnung")
    strang = auth_client.get(f"/api/invoices/{rechnung['id']}/chain").json()
    assert strang["chain_id"] is None
    assert strang["belege"] == []


def test_freie_anzahlung_eroeffnet_einen_eigenen_strang(auth_client, db_session):
    """Ohne Vorbeleg — mündlich beauftragt, Anzahlung direkt gestellt."""
    rechnung = _create(auth_client, _make_kontakt(db_session).id, doc_type="rechnung",
                       billing_stage="anzahlung")
    assert rechnung["chain_id"] == rechnung["id"]


# ── Der Abzug ─────────────────────────────────────────────────────────────────

def test_schlussrechnung_zieht_die_anzahlung_ab(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])

    assert schluss["billing_stage"] == "schluss"
    abzug = _abzugszeilen(schluss)
    assert len(abzug) == 1
    assert Decimal(abzug[0]["line_total"]) == Decimal("-3000.00")
    assert Decimal(abzug[0]["tax_rate"]) == Decimal("20.00")

    # 10.000 Gesamtleistung − 3.000 Anzahlung = 7.000 netto, 8.400 brutto
    assert Decimal(schluss["subtotal"]) == Decimal("7000.00")
    assert Decimal(schluss["tax_total"]) == Decimal("1400.00")
    assert Decimal(schluss["total"]) == Decimal("8400.00")


def test_abzug_je_steuersatz_getrennt(auth_client, db_session):
    """
    Der Kern der Sache: Bei gemischten Sätzen muss der Abzug getrennt
    ausgewiesen werden. Eine Sammelzeile hinge an einem Satz, und die
    MwSt.-Aufschlüsselung auf dem Beleg ginge nicht mehr auf.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Bauleistung", "quantity": "1",
         "unit_price": "8000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung Monteure", "quantity": "1",
         "unit_price": "2000", "tax_rate": "13"},
    ])

    # Zwei Teilrechnungen, je ein Satz — so, wie es tatsächlich abgerechnet wird
    teil1 = _create(auth_client, kontakt.id, doc_type="rechnung",
                    billing_stage="teil", chain_id=angebot["id"], positions=[
        {"pos_type": "item", "description": "1. Bauabschnitt", "quantity": "1",
         "unit_price": "3000", "tax_rate": "20"}])
    teil2 = _create(auth_client, kontakt.id, doc_type="rechnung",
                    billing_stage="teil", chain_id=angebot["id"], positions=[
        {"pos_type": "item", "description": "Nächtigungen Mai", "quantity": "1",
         "unit_price": "800", "tax_rate": "13"}])
    _ausstellen(auth_client, teil1["id"])
    _ausstellen(auth_client, teil2["id"])

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    abzug = {Decimal(z["tax_rate"]): Decimal(z["line_total"]) for z in _abzugszeilen(schluss)}

    assert abzug == {Decimal("20.00"): Decimal("-3000.00"),
                     Decimal("13.00"): Decimal("-800.00")}
    assert Decimal(schluss["subtotal"]) == Decimal("6200.00")     # 10.000 − 3.800
    # Steuer je Satz: (8000−3000)·20 % + (2000−800)·13 % = 1000 + 156
    assert Decimal(schluss["tax_total"]) == Decimal("1156.00")


def test_unbezahlte_anzahlung_wird_trotzdem_abgezogen(auth_client, db_session):
    """
    Die Entscheidung, die man leicht falsch trifft: Abgezogen wird, was
    fakturiert wurde. Die Umsatzsteuer entsteht mit der Rechnung — würde nur
    Bezahltes abgezogen, wäre sie bei einer offenen Anzahlung zweimal fällig.
    """
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])       # gestellt, aber nicht bezahlt

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    assert Decimal(_abzugszeilen(schluss)[0]["line_total"]) == Decimal("-3000.00")

    # …und der unbezahlte Betrag bleibt ein eigener offener Posten
    op = auth_client.get("/api/invoices/open-items").json()
    offene = {z["id"]: Decimal(z["open_amount"]) for z in op["items"]}
    assert offene.get(anzahlung["id"]) == Decimal("3600.00")


def test_entwurf_wird_nicht_abgezogen(auth_client, db_session):
    """Eine Anzahlungsrechnung im Entwurf hat den Kunden nie erreicht."""
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    _anzahlung(auth_client, angebot["id"], percent="30")       # bleibt Entwurf

    resp = auth_client.post(f"/api/invoices/{angebot['id']}/schlussrechnung", json={})
    assert resp.status_code == 400
    assert "keine gestellte" in resp.json()["detail"]


def test_stornierte_anzahlung_wird_nicht_abgezogen(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id)
    a1 = _anzahlung(auth_client, angebot["id"], amount="3000")
    a2 = _anzahlung(auth_client, angebot["id"], amount="2000")
    _ausstellen(auth_client, a1["id"])
    _ausstellen(auth_client, a2["id"])
    auth_client.post(f"/api/invoices/{a1['id']}/cancel", json={"cancel_mode": "status_only"})

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    assert Decimal(_abzugszeilen(schluss)[0]["line_total"]) == Decimal("-2000.00")


def test_zweite_schlussrechnung_abgelehnt(auth_client, db_session):
    """Sie würde dieselben Anzahlungen ein zweites Mal abziehen."""
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    _ausstellen(auth_client, schluss["id"])

    resp = auth_client.post(f"/api/invoices/{angebot['id']}/schlussrechnung",
                            json={"from_invoice_id": angebot["id"]})
    assert resp.status_code == 409
    assert "bereits eine Schlussrechnung" in resp.json()["detail"]


def test_abzug_wird_beim_speichern_neu_gerechnet(auth_client, db_session):
    """
    Kommt zwischen dem Erzeugen und dem Speichern eine weitere Teilrechnung
    dazu, wäre der Abzug aus dem Formular veraltet. Er wird deshalb serverseitig
    neu gerechnet — und ein von Hand mitgeschickter Abzug verworfen.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id)
    a1 = _anzahlung(auth_client, angebot["id"], amount="3000")
    _ausstellen(auth_client, a1["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])

    # Inzwischen geht eine Teilrechnung hinaus
    teil = _create(auth_client, kontakt.id, doc_type="rechnung", billing_stage="teil",
                   chain_id=angebot["id"], positions=[
        {"pos_type": "item", "description": "2. Abschnitt", "quantity": "1",
         "unit_price": "1500", "tax_rate": "20"}])
    _ausstellen(auth_client, teil["id"])

    # Der Browser schickt den alten Stand zurück — samt manipuliertem Abzug
    resp = auth_client.put(f"/api/invoices/{schluss['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06", "billing_stage": "schluss",
        "chain_id": angebot["id"],
        "positions": [
            {"pos_type": "item", "description": "Gesamtleistung", "quantity": "1",
             "unit_price": "10000", "tax_rate": "20"},
            {"pos_type": "advance_deduction", "description": "geschummelt",
             "quantity": "1", "unit_price": "-1", "tax_rate": "20"},
        ],
    })
    assert resp.status_code == 200
    aktualisiert = resp.json()
    abzug = _abzugszeilen(aktualisiert)
    assert len(abzug) == 1
    assert Decimal(abzug[0]["line_total"]) == Decimal("-4500.00")   # 3000 + 1500
    assert Decimal(aktualisiert["subtotal"]) == Decimal("5500.00")


# ── Umsatzsteuer über den ganzen Vorgang ──────────────────────────────────────

def test_uva_zaehlt_den_umsatz_genau_einmal(auth_client, db_session):
    """
    Der wichtigste Test der Etappe. Anzahlung und Schlussrechnung liegen im
    selben Monat; zusammen dürfen sie genau die Gesamtleistung ergeben — nicht
    das Anderthalbfache.
    """
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    _ausstellen(auth_client, schluss["id"])

    daten = _uva(auth_client)
    # 3.000 (Anzahlung) + 7.000 (Schlussrechnung nach Abzug) = 10.000
    assert Decimal(_zeile(daten, "022")["bemessungsgrundlage"]) == Decimal("10000.00")
    assert Decimal(_zeile(daten, "022")["steuer"]) == Decimal("2000.00")
    assert Decimal(daten["kz_000"]) == Decimal("10000.00")


def test_uva_ueber_zwei_monate(auth_client, db_session):
    """
    Der Regelfall im Bau: Anzahlung im Juli, Schlussrechnung im September. Die
    Steuer der Anzahlung gehört in den Juli und darf im September nicht noch
    einmal auftauchen — der Abzug sorgt genau dafür.
    """
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="40", date="2026-07-10")
    _ausstellen(auth_client, anzahlung["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"],
                       date="2026-09-15")
    _ausstellen(auth_client, schluss["id"])

    juli = _uva(auth_client, date_from="2026-07-01", date_to="2026-07-31")
    assert Decimal(_zeile(juli, "022")["bemessungsgrundlage"]) == Decimal("4000.00")

    september = _uva(auth_client, date_from="2026-09-01", date_to="2026-09-30")
    assert Decimal(_zeile(september, "022")["bemessungsgrundlage"]) == Decimal("6000.00")


def test_anzahlung_erscheint_im_buchungsjournal(auth_client, db_session):
    """
    Die Probe darauf, dass die Stufe ein Feld und keine eigene Belegart ist:
    Der Export prüft auf ``doc_type``. Eine neue Belegart wäre hier lautlos
    verschwunden.
    """
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    # Belegdatum ausdrücklich setzen: Ohne Angabe bekommt die
    # Anzahlungsrechnung den heutigen Tag, nicht das Datum des Angebots — und
    # der Test suchte im falschen Monat.
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30", date="2026-07-10")
    anzahlung = _ausstellen(auth_client, anzahlung["id"])
    assert anzahlung["number"], "Die Nummer fällt beim Ausstellen"
    assert anzahlung["date"] == "2026-07-10"

    resp = auth_client.get("/api/invoices/book/list",
                           params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    assert resp.status_code == 200
    nummern = {z.get("number") for z in resp.json()["invoices"]}
    assert anzahlung["number"] in nummern


# ── Der Beleg ─────────────────────────────────────────────────────────────────

def test_beleg_heisst_anzahlungsrechnung(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])

    html = auth_client.get(f"/api/invoices/{anzahlung['id']}/preview").text
    assert "ANZAHLUNGSRECHNUNG" in html.upper()


def test_abzug_steht_auf_der_schlussrechnung(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    anzahlung = _ausstellen(auth_client, anzahlung["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    _ausstellen(auth_client, schluss["id"])

    html = auth_client.get(f"/api/invoices/{schluss['id']}/preview").text
    assert "SCHLUSSRECHNUNG" in html.upper()
    # Die abgezogene Rechnung muss beim Namen genannt sein — mit dem Papier in
    # der Hand hilft eine Verknüpfung im Datenbestand niemandem.
    assert anzahlung["number"] in html
    assert "Abzüglich" in html


def test_positionsbild_ueberlebt_die_schlussrechnung(auth_client, db_session, monkeypatch):
    """
    Beim Umwandeln gingen Bild und Erlöskonto der Position bisher verloren.
    Das war schon vorher falsch und fällt hier erst recht auf: Die
    Schlussrechnung soll dem Angebot entsprechen.
    """
    ablage = {}
    monkeypatch.setattr("app.services.storage_service.upload_file",
                        lambda key, data, mimetype=None, db=None, backend=None:
                        ablage.__setitem__(key, (data, mimetype)))
    monkeypatch.setattr("app.services.storage_service.download_file",
                        lambda key, db=None, backend=None: ablage[key])
    monkeypatch.setattr("app.services.storage_service.delete_file",
                        lambda key, db=None, backend=None: ablage.pop(key, None))

    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id, positions=[{
        "pos_type": "item", "description": "Gesamtleistung", "quantity": "1",
        "unit_price": "10000", "tax_rate": "20",
        "account_nr": "4010", "image_key": "belege/positionsbilder/x.jpg",
        "image_size": "mittel", "image_provider": "minio",
    }])
    anzahlung = _anzahlung(auth_client, angebot["id"], percent="30")
    _ausstellen(auth_client, anzahlung["id"])

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    leistung = [p for p in schluss["positions"] if p["pos_type"] == "item"][0]
    assert leistung["account_nr"] == "4010"
    assert leistung["image_key"] == "belege/positionsbilder/x.jpg"
    assert leistung["image_provider"] == "minio"


# ── Prüfung auf Überabzug ─────────────────────────────────────────────────────

def test_ueberabzug_wird_vermerkt_nicht_verboten(auth_client, db_session):
    """
    Wer die Schlussrechnung mit der Restleistung statt der Gesamtleistung
    füllt, zieht mehr ab, als sie ausweist. Das wird protokolliert, nicht
    verhindert: Es gibt Fälle, in denen der Kunde tatsächlich etwas
    zurückbekommt.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id)
    anzahlung = _anzahlung(auth_client, angebot["id"], amount="6000")
    _ausstellen(auth_client, anzahlung["id"])
    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])

    # Positionen auf die Restleistung eindampfen — der klassische Fehlgriff
    auth_client.put(f"/api/invoices/{schluss['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06", "billing_stage": "schluss",
        "chain_id": angebot["id"],
        "positions": [{"pos_type": "item", "description": "Restleistung",
                       "quantity": "1", "unit_price": "4000", "tax_rate": "20"}],
    })
    _ausstellen(auth_client, schluss["id"])

    protokoll = auth_client.get(f"/api/invoices/{schluss['id']}/audit").json()
    hinweise = [e["note"] for e in protokoll if e["action"] == "hinweis" and e.get("note")]
    assert any("Gesamtleistung oder nur den Rest" in h for h in hinweise)


# ── Der Service für sich ──────────────────────────────────────────────────────

def test_bezeichnung_je_stufe():
    assert anzahlung_service.bezeichnung("anzahlung") == "Anzahlungsrechnung"
    assert anzahlung_service.bezeichnung("teil") == "Teilrechnung"
    assert anzahlung_service.bezeichnung("schluss") == "Schlussrechnung"
    assert anzahlung_service.bezeichnung(None) == "Rechnung"


def test_abzugszeilen_ohne_belege_bleiben_leer():
    assert anzahlung_service.abzugszeilen([]) == []


def test_abzug_bucht_auf_das_erloeskonto_der_anzahlung(auth_client, db_session):
    """
    Der Umsatz muss dort zurückgenommen werden, wo er gebucht wurde. Ginge der
    Abzug auf das Standard-Erlöskonto, während die Anzahlung auf 4010 lag,
    stimmte die Summe zwar — die Konten aber nicht.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id)
    teil = _create(auth_client, kontakt.id, doc_type="rechnung", billing_stage="teil",
                   chain_id=angebot["id"], positions=[
        {"pos_type": "item", "description": "1. Abschnitt", "quantity": "1",
         "unit_price": "3000", "tax_rate": "20", "account_nr": "4010"}])
    _ausstellen(auth_client, teil["id"])

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    assert _abzugszeilen(schluss)[0]["account_nr"] == "4010"


def test_gemischte_konten_fallen_auf_den_standard_zurueck(auth_client, db_session):
    """
    Verteilt sich die abgezogene Rechnung auf mehrere Erlöskonten, gibt es kein
    einzelnes richtiges. Dann bleibt das Feld leer und es greift das
    Standardkonto — bewusst offengelassen statt geraten.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id)
    teil = _create(auth_client, kontakt.id, doc_type="rechnung", billing_stage="teil",
                   chain_id=angebot["id"], positions=[
        {"pos_type": "item", "description": "Material", "quantity": "1",
         "unit_price": "2000", "tax_rate": "20", "account_nr": "4010"},
        {"pos_type": "item", "description": "Arbeit", "quantity": "1",
         "unit_price": "1000", "tax_rate": "20", "account_nr": "4020"}])
    _ausstellen(auth_client, teil["id"])

    schluss = _schluss(auth_client, angebot["id"], from_invoice_id=angebot["id"])
    abzug = _abzugszeilen(schluss)
    assert len(abzug) == 1
    assert abzug[0]["account_nr"] is None
    assert Decimal(abzug[0]["line_total"]) == Decimal("-3000.00")
