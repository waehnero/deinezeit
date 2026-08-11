"""
Tests für die Umsatzauswertungen (C-15).

Eine Auswertung ist nur so viel wert wie ihre Abgrenzung. Der Schwerpunkt liegt
deshalb nicht auf dem Rechnen, sondern auf der Frage **was zählt** — und darauf,
dass die Antwort dieselbe ist wie im Verkaufsbuch und in der UVA. Zwei
Auswertungen im selben Haus, die zum selben Monat verschiedene Zahlen nennen,
kosten mehr Zeit als sie sparen.

Stichtag ist das **Belegdatum** (Entscheidung Oliver), nicht der
Zahlungseingang.

Schema analog zu test_verkauf_uva.py.
"""
from decimal import Decimal

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.services import auswertungen


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _typ(db, slug, name):
    et = db.query(EntityType).filter_by(slug=slug).first()
    if not et:
        et = EntityType(name=name, slug=slug)
        db.add(et)
        db.flush()
    return et


def _record(db, slug, name, daten=None):
    rec = EntityRecord(entity_type_id=_typ(db, slug, slug.capitalize()).id,
                       display_name=name, data=daten or {})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _kontakt(db, name="Bauherr GmbH"):
    return _record(db, "kontakte", name, {"email": "buero@bauherr.at"})


def _artikel(db, name="Estrich"):
    return _record(db, "artikel", name, {"preis": 100})


def _create(client, contact_id=None, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Auftrag"),
        "date": extra.pop("date", "2026-03-10"),
        "delivery_date": extra.pop("delivery_date", "2026-03-10"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Leistung", "quantity": "1",
            "unit": "Stk", "unit_price": "1000", "tax_rate": "20",
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


def _jahr(client, jahr=2026):
    resp = client.get("/api/invoices/auswertung/umsatz-jahr", params={"jahr": jahr})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _kunden(client, **params):
    resp = client.get("/api/invoices/auswertung/umsatz-kunden", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _artikel_liste(client, **params):
    resp = client.get("/api/invoices/auswertung/umsatz-artikel", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _quote(client, **params):
    resp = client.get("/api/invoices/auswertung/angebotsquote", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _monat(daten, monat):
    return [m for m in daten["monate"] if m["monat"] == monat][0]


# ── Abgrenzung: was zählt ─────────────────────────────────────────────────────

def test_ausgestellte_rechnung_zaehlt(auth_client, db_session):
    _ausstellen(auth_client, _create(auth_client, _kontakt(db_session).id)["id"])
    daten = _jahr(auth_client)
    assert Decimal(_monat(daten, 3)["netto"]) == Decimal("1000.00")
    assert Decimal(daten["netto_gesamt"]) == Decimal("1000.00")
    assert daten["belege_gesamt"] == 1


def test_entwurf_zaehlt_nicht(auth_client, db_session):
    """Er ist beim Kunden nie angekommen."""
    _create(auth_client, _kontakt(db_session).id)
    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("0")


def test_angebot_ist_kein_umsatz(auth_client, db_session):
    _ausstellen(auth_client,
                _create(auth_client, _kontakt(db_session).id, doc_type="angebot")["id"],
                status="gesendet")
    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("0")


def test_gutschrift_mindert_den_umsatz(auth_client, db_session):
    kontakt = _kontakt(db_session)
    _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])
    _ausstellen(auth_client, _create(auth_client, kontakt.id, doc_type="gutschrift",
                                     positions=[{
        "pos_type": "item", "description": "Nachlass", "quantity": "1",
        "unit": "Stk", "unit_price": "-300", "tax_rate": "20"}])["id"])

    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("700.00")


def test_storno_mit_gutschrift_hebt_sich_auf(auth_client, db_session):
    """
    Der stornierte Beleg bleibt in der Auswertung, die Gutschrift dagegen
    ebenfalls — zusammen ergibt das null. Ihn herauszunehmen UND die Gutschrift
    zu zählen ergäbe einen negativen Umsatz.
    """
    kontakt = _kontakt(db_session)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])
    auth_client.post(f"/api/invoices/{rechnung['id']}/cancel",
                     json={"cancel_mode": "with_credit"})

    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("0")


def test_storno_ohne_gutschrift_verschwindet(auth_client, db_session):
    kontakt = _kontakt(db_session)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])
    auth_client.post(f"/api/invoices/{rechnung['id']}/cancel",
                     json={"cancel_mode": "status_only"})

    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("0")


def test_abgrenzung_deckt_sich_mit_dem_verkaufsbuch(auth_client, db_session):
    """
    Die Probe, auf die es ankommt: Auswertung und Verkaufsbuch müssen für
    denselben Zeitraum dieselbe Nettosumme nennen.
    """
    kontakt = _kontakt(db_session)
    for betrag in ("1000", "2500", "333.33"):
        _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[{
            "pos_type": "item", "description": "Leistung", "quantity": "1",
            "unit": "Stk", "unit_price": betrag, "tax_rate": "20"}])["id"])

    buch = auth_client.get("/api/invoices/book/list", params={
        "date_from": "2026-01-01", "date_to": "2026-12-31"}).json()
    aus_dem_buch = Decimal(str(buch["summary"]["total_net"]))

    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == aus_dem_buch


# ── Rechnen ───────────────────────────────────────────────────────────────────

def test_rabatt_mindert_den_umsatz(auth_client, db_session):
    """
    Gerechnet wird über denselben Dienst wie PDF und UVA — ein Gruppenrabatt
    zählt deshalb genauso.
    """
    _ausstellen(auth_client, _create(auth_client, _kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Leistung", "quantity": "1",
         "unit": "Stk", "unit_price": "1000", "tax_rate": "20"},
        {"pos_type": "discount", "description": "Nachlass", "quantity": "1",
         "unit_price": "100", "tax_rate": None},
    ])["id"])
    assert Decimal(_jahr(auth_client)["netto_gesamt"]) == Decimal("900.00")


def test_anzahlung_und_schlussrechnung_zaehlen_zusammen_einmal(auth_client, db_session):
    """
    Wie in der UVA: Die Anzahlung zählt, die Schlussrechnung nur der Rest.
    Zusammen ergeben sie die Gesamtleistung — nicht das Anderthalbfache.
    """
    kontakt = _kontakt(db_session)
    angebot = _create(auth_client, kontakt.id, doc_type="angebot", positions=[{
        "pos_type": "item", "description": "Gesamtleistung", "quantity": "1",
        "unit": "Stk", "unit_price": "10000", "tax_rate": "20"}])
    anzahlung = auth_client.post(f"/api/invoices/{angebot['id']}/anzahlung",
                                 json={"percent": "30", "date": "2026-03-10"}).json()
    _ausstellen(auth_client, anzahlung["id"])
    schluss = auth_client.post(f"/api/invoices/{angebot['id']}/schlussrechnung",
                               json={"from_invoice_id": angebot["id"],
                                     "date": "2026-05-20"}).json()
    _ausstellen(auth_client, schluss["id"])

    daten = _jahr(auth_client)
    assert Decimal(_monat(daten, 3)["netto"]) == Decimal("3000.00")
    assert Decimal(_monat(daten, 5)["netto"]) == Decimal("7000.00")
    assert Decimal(daten["netto_gesamt"]) == Decimal("10000.00")


def test_alle_zwoelf_monate_kommen_zurueck(auth_client, db_session):
    """Eine Lücke in der Reihe liest sich wie ein fehlender Monat."""
    daten = _jahr(auth_client)
    assert [m["monat"] for m in daten["monate"]] == list(range(1, 13))


def test_vorjahr_wird_mitgeliefert(auth_client, db_session):
    kontakt = _kontakt(db_session)
    _ausstellen(auth_client, _create(auth_client, kontakt.id, date="2025-03-10",
                                     delivery_date="2025-03-10")["id"])
    daten = _jahr(auth_client, 2026)
    assert Decimal(_monat(daten, 3)["vorjahr"]) == Decimal("1000.00")
    assert Decimal(daten["vorjahr_gesamt"]) == Decimal("1000.00")
    assert Decimal(daten["netto_gesamt"]) == Decimal("0")


# ── Je Kunde ──────────────────────────────────────────────────────────────────

def test_kunden_nach_umsatz_sortiert(auth_client, db_session):
    klein = _kontakt(db_session, "Kleiner Kunde")
    gross = _kontakt(db_session, "Großer Kunde")
    _ausstellen(auth_client, _create(auth_client, klein.id)["id"])
    _ausstellen(auth_client, _create(auth_client, gross.id, positions=[{
        "pos_type": "item", "description": "Leistung", "quantity": "1",
        "unit": "Stk", "unit_price": "4000", "tax_rate": "20"}])["id"])

    daten = _kunden(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert [z["name"] for z in daten["zeilen"]] == ["Großer Kunde", "Kleiner Kunde"]
    assert Decimal(daten["zeilen"][0]["anteil"]) == Decimal("80.0")
    assert Decimal(daten["netto_gesamt"]) == Decimal("5000.00")


def test_anteil_bleibt_am_gesamtumsatz_auch_bei_gekuerzter_liste(auth_client, db_session):
    """
    Sonst summierten sich die Anteile der obersten paar auf 100 % — und die
    Frage „wie abhängig bin ich vom größten Kunden" bekäme eine zu große
    Antwort.
    """
    for i, betrag in enumerate(("4000", "3000", "2000", "1000")):
        k = _kontakt(db_session, f"Kunde {i}")
        _ausstellen(auth_client, _create(auth_client, k.id, positions=[{
            "pos_type": "item", "description": "Leistung", "quantity": "1",
            "unit": "Stk", "unit_price": betrag, "tax_rate": "20"}])["id"])

    daten = _kunden(auth_client, date_from="2026-01-01", date_to="2026-12-31", limit=2)
    assert len(daten["zeilen"]) == 2
    assert daten["kunden"] == 4
    # 4000 von 10000 — nicht 4000 von 7000
    assert Decimal(daten["zeilen"][0]["anteil"]) == Decimal("40.0")
    assert Decimal(daten["netto_gesamt"]) == Decimal("10000.00")


def test_beleg_ohne_kontakt_verschwindet_nicht(auth_client, db_session):
    """Barverkauf und Altbestand — sie werden benannt, nicht unterschlagen."""
    _ausstellen(auth_client, _create(auth_client, None)["id"])
    daten = _kunden(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["zeilen"][0]["contact_id"] is None
    assert "ohne Kontakt" in daten["zeilen"][0]["name"]
    assert Decimal(daten["netto_gesamt"]) == Decimal("1000.00")


# ── Je Artikel ────────────────────────────────────────────────────────────────

def test_artikel_werden_zusammengefasst(auth_client, db_session):
    artikel = _artikel(db_session, "Estrich")
    kontakt = _kontakt(db_session)
    for menge in ("2", "3"):
        _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[{
            "pos_type": "item", "description": "Estrich", "quantity": menge,
            "unit": "m²", "unit_price": "100", "tax_rate": "20",
            "article_id": str(artikel.id)}])["id"])

    daten = _artikel_liste(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert len(daten["zeilen"]) == 1
    assert daten["zeilen"][0]["name"] == "Estrich"
    assert Decimal(daten["zeilen"][0]["netto"]) == Decimal("500.00")
    assert Decimal(daten["zeilen"][0]["menge"]) == Decimal("5")
    assert daten["zeilen"][0]["belege"] == 2


def test_freie_positionen_werden_ausgewiesen_nicht_geraten(auth_client, db_session):
    """
    Der Kern dieser Auswertung. Frei getippte Positionen unter ihrem Text zu
    gruppieren würde „Regiestunden" und „Regiestunde" zu zwei Artikeln machen
    und eine Genauigkeit vortäuschen, die es nicht gibt. Stattdessen steht in
    der Antwort, wie viel Umsatz sich nicht zuordnen ließ.
    """
    artikel = _artikel(db_session, "Estrich")
    kontakt = _kontakt(db_session)
    _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[{
        "pos_type": "item", "description": "Estrich", "quantity": "1",
        "unit": "m²", "unit_price": "200", "tax_rate": "20",
        "article_id": str(artikel.id)}])["id"])
    _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[{
        "pos_type": "item", "description": "Irgendwas Getipptes", "quantity": "1",
        "unit": "Stk", "unit_price": "800", "tax_rate": "20"}])["id"])

    daten = _artikel_liste(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert len(daten["zeilen"]) == 1
    assert Decimal(daten["ohne_artikel_netto"]) == Decimal("800.00")
    assert daten["ohne_artikel_belege"] == 1
    assert Decimal(daten["ohne_artikel_anteil"]) == Decimal("80.0")
    # Die Summe umfasst beides — sonst wäre der Anteil nicht lesbar
    assert Decimal(daten["netto_gesamt"]) == Decimal("1000.00")


def test_rabatt_verteilt_sich_auf_die_artikel(auth_client, db_session):
    """
    Ein Gruppenrabatt hängt an keiner einzelnen Position. Ohne Verteilung wäre
    die Summe der Artikel größer als der Umsatz des Belegs — und größer als
    der Jahresumsatz, den dieselbe Seite daneben anzeigt.
    """
    artikel = _artikel(db_session, "Estrich")
    _ausstellen(auth_client, _create(auth_client, _kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Estrich", "quantity": "1",
         "unit": "m²", "unit_price": "1000", "tax_rate": "20",
         "article_id": str(artikel.id)},
        {"pos_type": "discount", "description": "Nachlass", "quantity": "1",
         "unit_price": "200", "tax_rate": None},
    ])["id"])

    daten = _artikel_liste(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert Decimal(daten["zeilen"][0]["netto"]) == Decimal("800.00")
    assert Decimal(daten["netto_gesamt"]) == Decimal(_jahr(auth_client)["netto_gesamt"])


# ── Angebotsquote ─────────────────────────────────────────────────────────────

def test_angenommenes_angebot_gilt_als_gewonnen(auth_client, db_session):
    kontakt = _kontakt(db_session)
    a = _create(auth_client, kontakt.id, doc_type="angebot")
    _ausstellen(auth_client, a["id"], status="gesendet")
    auth_client.post(f"/api/invoices/{a['id']}/set-status", json={"status": "angenommen"})

    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["gewonnen"] == 1
    assert Decimal(daten["quote"]) == Decimal("100.0")


def test_umgewandeltes_angebot_gilt_auch_ohne_statuswechsel(auth_client, db_session):
    """
    Wer aus einem gesendeten Angebot direkt eine Rechnung macht, hat es
    faktisch gewonnen — auch ohne je auf „angenommen" geklickt zu haben.
    """
    kontakt = _kontakt(db_session)
    a = _create(auth_client, kontakt.id, doc_type="angebot")
    _ausstellen(auth_client, a["id"], status="gesendet")

    # `trotz_ablauf`, weil das Angebot auf 2026-03-10 datiert ist und die
    # Bindefrist aus Etappe 9 (30 Tage) längst abgelaufen wäre. Ein festes
    # Datum in der Zukunft wäre die schlechtere Wahl: Es würde irgendwann
    # selbst zur Vergangenheit und den Test ohne Vorwarnung rot machen.
    resp = auth_client.post(f"/api/invoices/{a['id']}/convert-to-invoice",
                            params={"trotz_ablauf": True})
    assert resp.status_code == 200, resp.text
    _ausstellen(auth_client, resp.json()["id"])

    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["gewonnen"] == 1
    assert daten["verloren"] == 0


def test_abgelehntes_angebot_zaehlt_als_verloren(auth_client, db_session):
    kontakt = _kontakt(db_session)
    for ziel in ("angenommen", "abgelehnt", "abgelehnt"):
        a = _create(auth_client, kontakt.id, doc_type="angebot")
        _ausstellen(auth_client, a["id"], status="gesendet")
        auth_client.post(f"/api/invoices/{a['id']}/set-status", json={"status": ziel})

    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert (daten["gewonnen"], daten["verloren"]) == (1, 2)
    assert Decimal(daten["quote"]) == Decimal("33.3")


def test_offene_angebote_druecken_die_quote_nicht(auth_client, db_session):
    """
    Die Quote rechnet auf die ENTSCHIEDENEN Angebote. Offene mitzuzählen würde
    sie drücken, solange noch nichts entschieden ist — und jeden Monat
    rückwirkend verändern.
    """
    kontakt = _kontakt(db_session)
    a = _create(auth_client, kontakt.id, doc_type="angebot")
    _ausstellen(auth_client, a["id"], status="gesendet")
    auth_client.post(f"/api/invoices/{a['id']}/set-status", json={"status": "angenommen"})
    for _ in range(3):
        offen = _create(auth_client, kontakt.id, doc_type="angebot")
        _ausstellen(auth_client, offen["id"], status="gesendet")

    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["offen"] == 3
    assert Decimal(daten["quote"]) == Decimal("100.0")


def test_ohne_entscheidung_gibt_es_keine_quote(auth_client, db_session):
    """0 % wäre eine Aussage, die es nicht gibt."""
    kontakt = _kontakt(db_session)
    a = _create(auth_client, kontakt.id, doc_type="angebot")
    _ausstellen(auth_client, a["id"], status="gesendet")

    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["gesamt"] == 1
    assert daten["quote"] is None


def test_angebotsentwurf_kann_man_nicht_verlieren(auth_client, db_session):
    _create(auth_client, _kontakt(db_session).id, doc_type="angebot")
    daten = _quote(auth_client, date_from="2026-01-01", date_to="2026-12-31")
    assert daten["gesamt"] == 0


# ── Rechte ────────────────────────────────────────────────────────────────────

def test_auswertungen_verlangen_das_modul_buchhaltung(client, db_session, test_user):
    """
    Sie zeigen dieselben Zahlen wie Verkaufsbuch und UVA, nur anders
    geschnitten. Ein Recht, das dort greift und hier nicht, wäre über die
    Auswertung umgehbar.

    Muster wie in test_verkauf_uva.py.
    """
    from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

    test_user.allowed_modules = ["verkauf"]
    db_session.commit()
    token = client.post("/api/auth/login", json={
        "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}

    for pfad in ("umsatz-jahr", "umsatz-kunden", "umsatz-artikel", "angebotsquote"):
        resp = client.get(f"/api/invoices/auswertung/{pfad}", headers=kopf)
        assert resp.status_code == 403, f"{pfad}: {resp.status_code}"


# ── Der Dienst für sich ───────────────────────────────────────────────────────

def test_leerer_zeitraum_liefert_nullen_statt_fehler(auth_client, db_session):
    daten = _kunden(auth_client, date_from="2020-01-01", date_to="2020-12-31")
    assert daten["zeilen"] == []
    assert Decimal(daten["netto_gesamt"]) == Decimal("0")

    artikel = _artikel_liste(auth_client, date_from="2020-01-01", date_to="2020-12-31")
    assert Decimal(artikel["ohne_artikel_anteil"]) == Decimal("0")


def test_umsatzarten_sind_nur_rechnung_und_gutschrift():
    assert auswertungen.UMSATZARTEN == ("rechnung", "gutschrift")
