"""
Tests für die kleineren Befunde aus `docs/VERKAUF_ANALYSE.md`.

  A-14  Der MwSt.-Modus „Ein Satz für alle" war wählbar, wurde aber nirgends
        ausgewertet — er verhielt sich wie „pro Position". Der Benutzer wählte
        etwas aus, das nichts tat.
  A-17e Scheiterte die PDF-Erzeugung des Verkaufsbuchs, kam HTML unter dem
        Namen belegbuch.pdf zurück — der Fehler fiel erst beim Öffnen auf.
  A-17f bulk-send-email committete erst am Ende; ein Fehler in der Mitte riss
        die Statusänderungen der bereits versendeten Belege mit.
  B-3   Die UID des Empfängers ist ab 10.000 € Pflichtangabe — es gab weder
        Prüfung noch Hinweis.

Schema analog zu test_verkauf_abschluss.py.
"""
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceAuditLog
from app.api.invoice import UID_SCHWELLE, _uid_fehlt


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH", uid=None):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    daten = {"email": "info@muster.at"}
    if uid:
        daten["uid"] = uid
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name, data=daten)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id=None, **extra):
    payload = {
        "doc_type": extra.pop("doc_type", "rechnung"),
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


def _ausstellen(client, invoice_id):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": "offen"})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── A-14: Ein Satz für alle ───────────────────────────────────────────────────

def test_ein_satz_fuer_alle_vereinheitlicht_die_positionen(auth_client, db_session):
    """
    Die Regel steckt im Backend, nicht nur im Formular — sonst hinge sie am
    Wohlverhalten des Clients.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          tax_mode="single_rate", positions=[
        {"pos_type": "item", "description": "A", "quantity": "1",
         "unit_price": "100", "tax_rate": "20"},
        {"pos_type": "item", "description": "B", "quantity": "1",
         "unit_price": "100", "tax_rate": "10"},   # abweichend — wird angeglichen
    ])
    saetze = {p["tax_rate"] for p in inv["positions"]}
    assert saetze == {"20.00"}
    assert Decimal(inv["tax_total"]) == Decimal("40.00")


def test_pro_position_laesst_die_saetze_stehen(auth_client, db_session):
    """Gegenprobe — der Standardmodus verändert nichts."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "A", "quantity": "1",
         "unit_price": "100", "tax_rate": "20"},
        {"pos_type": "item", "description": "B", "quantity": "1",
         "unit_price": "100", "tax_rate": "10"},
    ])
    assert {p["tax_rate"] for p in inv["positions"]} == {"20.00", "10.00"}
    assert Decimal(inv["tax_total"]) == Decimal("30.00")


def test_ein_satz_fuer_alle_ohne_gepflegten_satz(auth_client, db_session):
    """Reverse Charge durchgehend: Es gibt nichts anzugleichen, kein Absturz."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          tax_mode="single_rate", positions=[
        {"pos_type": "item", "description": "A", "quantity": "1",
         "unit_price": "100", "tax_rate": None},
    ])
    assert inv["positions"][0]["tax_rate"] is None
    assert Decimal(inv["tax_total"]) == Decimal("0")


# ── A-17e: kein HTML unter .pdf mehr ──────────────────────────────────────────

def test_verkaufsbuch_pdf_ist_ein_pdf(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    resp = auth_client.get("/api/invoices/book/pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


# ── A-17f: Massenversand committet je Beleg ───────────────────────────────────

def test_massenversand_haelt_erfolge_fest(auth_client, db_session, monkeypatch):
    """
    Schlägt der zweite Versand fehl, muss der erste erhalten bleiben.
    Vorher hätte das gemeinsame Commit am Ende beide zurückgerollt — obwohl
    die erste E-Mail längst draußen war.
    """
    from app.api import invoice as invoice_api

    kontakt = _make_kontakt(db_session)
    a = _create_invoice(auth_client, kontakt.id, title="Erster")
    b = _create_invoice(auth_client, kontakt.id, title="Zweiter")

    versendet = []

    def _fake_send(inv, db, *args, **kwargs):
        if inv.title == "Zweiter":
            raise RuntimeError("SMTP nicht erreichbar")
        versendet.append(inv.title)
        inv.status = "gesendet"
        invoice_api._finalize(db, inv)

    monkeypatch.setattr(invoice_api, "_send_invoice_email", _fake_send)

    resp = auth_client.post("/api/invoices/bulk-send-email",
                            json={"invoice_ids": [a["id"], b["id"]]})
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["sent"] == 1
    assert versendet == ["Erster"]

    # Der erfolgreiche Beleg behält seinen Status und seine Nummer
    erster = db_session.query(Invoice).filter_by(id=a["id"]).first()
    db_session.refresh(erster)
    assert erster.status == "gesendet"
    assert erster.number is not None

    # Der gescheiterte bleibt unverändert Entwurf
    zweiter = db_session.query(Invoice).filter_by(id=b["id"]).first()
    db_session.refresh(zweiter)
    assert zweiter.status == "entwurf"
    assert zweiter.number is None


# ── B-3: UID ab 10.000 € ──────────────────────────────────────────────────────

def test_uid_unter_der_schwelle_ohne_hinweis(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)   # 1.200 €
    _ausstellen(auth_client, inv["id"])

    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    assert not [e for e in eintraege if e["action"] == "hinweis"]


def test_fehlende_uid_ueber_der_schwelle_wird_vermerkt(auth_client, db_session):
    """
    Blockiert wird nicht — der Empfänger kann eine Privatperson ohne UID sein.
    Sichtbar gemacht wird es trotzdem.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Großauftrag", "quantity": "1",
         "unit_price": "20000", "tax_rate": "20"},
    ])
    resp = auth_client.post(f"/api/invoices/{inv['id']}/set-status",
                            json={"status": "offen"})
    assert resp.status_code == 200, resp.text      # kein Blocker

    hinweise = [e for e in auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
                if e["action"] == "hinweis"]
    assert len(hinweise) == 1
    assert "UID" in hinweise[0]["note"]


def test_vorhandene_uid_ohne_hinweis(auth_client, db_session):
    kontakt = _make_kontakt(db_session, uid="ATU12345678")
    inv = _create_invoice(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Großauftrag", "quantity": "1",
         "unit_price": "20000", "tax_rate": "20"},
    ])
    _ausstellen(auth_client, inv["id"])

    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    assert not [e for e in eintraege if e["action"] == "hinweis"]


def test_uid_pruefung_gilt_nicht_fuer_angebote(auth_client, db_session):
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id,
                              doc_type="angebot", positions=[
        {"pos_type": "item", "description": "Großauftrag", "quantity": "1",
         "unit_price": "20000", "tax_rate": "20"},
    ])
    obj = db_session.query(Invoice).filter_by(id=angebot["id"]).first()
    assert _uid_fehlt(db_session, obj) is False


def test_pruefliste_meldet_fehlende_uid(auth_client, db_session, admin_user):
    """Vor der Übergabe soll es auffallen — dort gehört die Prüfung hin."""
    from tests.conftest import TEST_USER_PASSWORD
    token = auth_client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD}).json()["access_token"]
    auth_client.headers.update({"Authorization": f"Bearer {token}"})

    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "Großauftrag", "quantity": "1",
         "unit_price": "20000", "tax_rate": "20"},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/periods/2026/7/check").json()
    punkt = [p for p in daten["punkte"] if p["schluessel"] == "uid_fehlt"][0]
    assert punkt["erfuellt"] is False
    assert punkt["anzahl"] == 1
    assert punkt["art"] == "hinweis"
    assert daten["abschluss_moeglich"] is True     # blockiert nicht


def test_schwelle_ist_zehntausend():
    assert UID_SCHWELLE == Decimal("10000")
