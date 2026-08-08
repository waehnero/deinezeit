"""
Tests für die Umsatzsteuer-Auswertung und das Erlöskonto je Position.

Deckt die Befunde C-7 und A-16 aus `docs/VERKAUF_ANALYSE.md` ab:

  C-7  Es gab keine Umsatzsteuer-Auswertung. Das Verkaufsbuch lieferte eine
       einzige Summe „MwSt." über alles — für die Voranmeldung braucht es die
       Bemessungsgrundlage je Steuersatz mit der zugehörigen Kennzahl.
  A-16 Das Stammdatenfeld „Erlöskonto" am Artikel wurde nie auf die
       Belegposition durchgereicht; im BMD-Export landete alles auf dem einen
       Standard-Erlöskonto.

Die Kennzahlen 022 (20 %), 029 (10 %) und 006 (13 %) sind belegt. Für
steuerfreie und Reverse-Charge-Umsätze wird bewusst NICHTS geraten — solche
Zeilen erscheinen als „nicht zugeordnet".

Schema analog zu test_verkauf_zahlungen.py.
"""
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import InvoiceSettings
from app.services import tax_rates as tax_rates_service


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data={"email": "info@muster.at"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id=None, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "1", "unit_price": "1000", "tax_rate": "20",
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


def _uva(client, **params):
    resp = client.get("/api/invoices/uva", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _zeile(daten, kennzahl):
    treffer = [z for z in daten["zeilen"] if z["kennzahl"] == kennzahl]
    assert treffer, f"Keine Zeile mit Kennzahl {kennzahl} in {daten['zeilen']}"
    return treffer[0]


def _kennzahl_hinweise(daten):
    """
    Hinweise zu fehlenden Kennzahlen — ohne die, die immer dabeistehen.

    Zwei Hinweise sind Dauergäste: der Vorbehalt „Aufbereitung, keine
    Steuerberatung" und die Meldung, dass im Zeitraum keine Eingangsrechnung
    erfasst ist (in diesen Tests bucht niemand welche). „Keine Hinweise" heißt
    hier also: keine ungeklärte Kennzahl, nicht „gar nichts angemerkt".
    """
    return [h for h in daten["hinweise"]
            if "Vorsteuer" not in h and "Aufbereitung" not in h]


# ── C-7: Auswertung je Steuersatz ─────────────────────────────────────────────

def test_uva_trennt_nach_steuersatz_und_kennzahl(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Beratung", "quantity": "1",
         "unit_price": "1000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung", "quantity": "1",
         "unit_price": "500", "tax_rate": "13"},
        {"pos_type": "item", "description": "Lebensmittel", "quantity": "1",
         "unit_price": "200", "tax_rate": "10"},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    assert Decimal(_zeile(daten, "022")["bemessungsgrundlage"]) == Decimal("1000.00")
    assert Decimal(_zeile(daten, "022")["steuer"]) == Decimal("200.00")
    assert Decimal(_zeile(daten, "006")["bemessungsgrundlage"]) == Decimal("500.00")
    assert Decimal(_zeile(daten, "006")["steuer"]) == Decimal("65.00")
    assert Decimal(_zeile(daten, "029")["bemessungsgrundlage"]) == Decimal("200.00")
    assert Decimal(_zeile(daten, "029")["steuer"]) == Decimal("20.00")

    assert Decimal(daten["kz_000"]) == Decimal("1700.00")
    assert Decimal(daten["steuer_gesamt"]) == Decimal("285.00")
    assert _kennzahl_hinweise(daten) == []      # alle Sätze zugeordnet


def test_uva_ignoriert_entwuerfe(auth_client, db_session):
    _create_invoice(auth_client, _make_kontakt(db_session).id)      # Entwurf
    daten = _uva(auth_client)
    assert daten["zeilen"] == []
    assert Decimal(daten["kz_000"]) == Decimal("0")


def test_uva_ignoriert_angebote(auth_client, db_session):
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id, doc_type="angebot")
    _ausstellen(auth_client, angebot["id"], status="gesendet")
    assert _uva(auth_client)["zeilen"] == []


def test_gutschrift_mindert_die_bemessungsgrundlage(auth_client, db_session):
    """Storno mit Gutschrift muss sich in der Auswertung aufheben."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/cancel", json={"cancel_mode": "with_credit"})

    daten = _uva(auth_client)
    assert Decimal(daten["kz_000"]) == Decimal("0.00")
    assert Decimal(daten["steuer_gesamt"]) == Decimal("0.00")


def test_uva_filtert_nach_zeitraum(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    for tag in ["2026-06-15", "2026-07-15"]:
        inv = _create_invoice(auth_client, kontakt.id, date=tag, delivery_date=tag)
        _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client, date_from="2026-07-01", date_to="2026-07-31")
    assert daten["beleg_anzahl"] == 1
    assert Decimal(daten["kz_000"]) == Decimal("1000.00")


def test_reverse_charge_erscheint_ohne_kennzahl(auth_client, db_session):
    """
    Reverse-Charge-Umsätze laufen je nach Sachverhalt über unterschiedliche
    Kennzahlen — geraten wird hier nichts.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Leistung ins Ausland",
         "quantity": "1", "unit_price": "800", "tax_rate": None},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    rc = [z for z in daten["zeilen"] if z["satz"] is None]
    assert len(rc) == 1
    assert rc[0]["kennzahl"] == ""
    assert rc[0]["zugeordnet"] is False
    assert Decimal(rc[0]["bemessungsgrundlage"]) == Decimal("800.00")
    assert Decimal(rc[0]["steuer"]) == Decimal("0")
    assert any("Reverse-Charge" in h for h in daten["hinweise"])


def test_fehlende_kennzahl_wird_gemeldet(auth_client, db_session):
    """Ein steuerfreier Umsatz ohne gepflegte Kennzahl darf nicht stillschweigen."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Ausfuhrlieferung",
         "quantity": "1", "unit_price": "300", "tax_rate": "0"},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    steuerfrei = [z for z in daten["zeilen"] if z["satz"] == "0.00"]
    assert steuerfrei and steuerfrei[0]["zugeordnet"] is False
    assert any("keine UVA-Kennzahl" in h for h in daten["hinweise"])


def test_gepflegte_kennzahl_wird_verwendet(auth_client, db_session):
    db_session.add(InvoiceSettings(key="tax_rates", value=[
        {"satz": 0, "bezeichnung": "Ausfuhr", "ust_code": "U00",
         "uva_kz": "011", "aktiv": True, "standard": True},
    ]))
    db_session.commit()

    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Ausfuhrlieferung",
         "quantity": "1", "unit_price": "300", "tax_rate": "0"},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    assert _zeile(daten, "011")["zugeordnet"] is True
    assert _kennzahl_hinweise(daten) == []      # alle Sätze zugeordnet


def test_kleinunternehmer_ohne_steuer(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          tax_mode="kleinunternehmer")
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    assert Decimal(daten["steuer_gesamt"]) == Decimal("0")
    assert Decimal(daten["kz_000"]) == Decimal("1000.00")


def test_hinweis_wenn_keine_eingangsrechnung_erfasst_ist(auth_client, db_session):
    """
    Seit Etappe 7 enthält die Auswertung die Vorsteuer. Ist im Zeitraum keine
    Eingangsrechnung erfasst, weist sie null Vorsteuer aus — das kann stimmen,
    ist aber oft schlicht vergessen. Eine Meldung ohne Vorsteuer bedeutet zu
    viel Zahllast, deshalb sagt die Auswertung es ausdrücklich.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    daten = _uva(auth_client)
    assert any("keine Eingangsrechnung erfasst" in h for h in daten["hinweise"])


def test_steuerland_wird_ausgewiesen(auth_client, db_session):
    daten = _uva(auth_client)
    assert daten["country"] == "AT"
    assert daten["country_supported"] is True


def test_fremdes_steuerland_wird_gemeldet(auth_client, db_session):
    """Für andere Länder gelten andere Formulare — das darf nicht untergehen."""
    from app.models.settings import Setting

    db_session.add(Setting(key="company_country", value="DE"))
    db_session.commit()

    daten = _uva(auth_client)
    assert daten["country"] == "DE"
    assert daten["country_supported"] is False
    assert any("Steuerland" in h for h in daten["hinweise"])


def test_uva_ausdruck_liefert_pdf(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    resp = auth_client.get("/api/invoices/uva/pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_uva_ausdruck_auch_ohne_belege(auth_client, db_session):
    """Ein leerer Zeitraum darf den Ausdruck nicht scheitern lassen."""
    resp = auth_client.get("/api/invoices/uva/pdf",
                           params={"date_from": "2030-01-01", "date_to": "2030-01-31"})
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_uva_verlangt_das_modul_buchhaltung(client, db_session, test_user):
    from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

    test_user.allowed_modules = ["verkauf"]
    db_session.commit()
    token = client.post("/api/auth/login", json={
        "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]

    resp = client.get("/api/invoices/uva", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ── A-16: Erlöskonto je Position ──────────────────────────────────────────────

def test_kennzahl_gehoert_zu_den_einstellungen(auth_client, db_session):
    """Die Kennzahl wird mit den Steuersätzen gepflegt, nicht hartkodiert."""
    daten = auth_client.get("/api/invoices/settings/all").json()
    je_satz = {s["satz"]: s["uva_kz"] for s in daten["tax_rates"]}
    assert je_satz[20] == "022"
    assert je_satz[13] == "006"
    assert je_satz[10] == "029"
    assert je_satz[0] == ""          # bewusst offen


def test_kennzahl_wird_nicht_geraten(db_session):
    """Ein unbekannter Satz bekommt keine erfundene Kennzahl."""
    db_session.add(InvoiceSettings(key="tax_rates", value=[
        {"satz": 7, "bezeichnung": "Fremd", "ust_code": "U07", "aktiv": True},
    ]))
    db_session.commit()

    satz = tax_rates_service.get_tax_rates(db_session)[0]
    assert satz["ust_code"] == "U07"      # Code wird abgeleitet …
    assert satz["uva_kz"] == ""           # … die Kennzahl nicht
