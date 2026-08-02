"""
Tests für Zahlungseingänge, Überfälligkeit und offene Posten (Modul Verkauf).

Deckt die Befunde C-2, C-3 und A-17b aus `docs/VERKAUF_ANALYSE.md` ab:

  C-2   Es gab nur ``paid_at``/``paid_amount`` — genau eine Zahlung je Beleg.
        Teilzahlung, Ratenzahlung, Überzahlung und selbst die Korrektur eines
        falschen Zahldatums waren nicht abbildbar.
  C-3   Keine Offene-Posten-Liste, also kein Überblick über die Forderungen.
  A-17b Der Status ``ueberfaellig`` wurde nirgends gesetzt — überfällige
        Rechnungen blieben ewig „offen".

Schema analog zu test_verkauf_steuer.py.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoicePayment, InvoiceAuditLog
from app.services import overdue_service


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
    """Legt einen Beleg über 1.200,00 € brutto an (1.000 netto + 20 %)."""
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "due_date": extra.pop("due_date", "2026-08-05"),
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


def _zahlen(client, invoice_id, betrag, tag="2026-08-01", **extra):
    return client.post(f"/api/invoices/{invoice_id}/payments",
                       json={"paid_at": tag, "amount": str(betrag), **extra})


def _offener_beleg(client, db, **extra):
    inv = _create_invoice(client, _make_kontakt(db).id, **extra)
    _ausstellen(client, inv["id"])
    return inv


# ── C-2: Teilzahlungen ────────────────────────────────────────────────────────

def test_teilzahlung_setzt_status_teilbezahlt(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)

    resp = _zahlen(auth_client, inv["id"], "500.00")
    assert resp.status_code == 200, resp.text
    stand = resp.json()
    assert stand["status"] == "teilbezahlt"
    assert Decimal(stand["paid_total"]) == Decimal("500.00")
    assert Decimal(stand["open_amount"]) == Decimal("700.00")
    assert stand["overpaid"] is False
    assert len(stand["payments"]) == 1


def test_zweite_zahlung_gleicht_aus(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "500.00", "2026-08-01")

    stand = _zahlen(auth_client, inv["id"], "700.00", "2026-08-20").json()
    assert stand["status"] == "bezahlt"
    assert Decimal(stand["open_amount"]) == Decimal("0.00")
    assert len(stand["payments"]) == 2


def test_ueberzahlung_wird_angenommen_und_gekennzeichnet(auth_client, db_session):
    """Eine Überzahlung kommt vor — das System darf daran nicht scheitern."""
    inv = _offener_beleg(auth_client, db_session)

    stand = _zahlen(auth_client, inv["id"], "1300.00").json()
    assert stand["status"] == "bezahlt"
    assert stand["overpaid"] is True
    assert Decimal(stand["open_amount"]) == Decimal("-100.00")


def test_zahlung_zuruecknehmen(auth_client, db_session):
    """Fehleingaben müssen korrigierbar sein — vorher waren sie es nicht."""
    inv = _offener_beleg(auth_client, db_session)
    zahlung_id = _zahlen(auth_client, inv["id"], "1200.00").json()["payments"][0]["id"]

    resp = auth_client.delete(f"/api/invoices/payments/{zahlung_id}")
    assert resp.status_code == 200, resp.text
    stand = resp.json()
    assert stand["payments"] == []
    assert Decimal(stand["open_amount"]) == Decimal("1200.00")
    assert stand["status"] == "offen"


def test_zahlstand_wird_am_beleg_zwischengespeichert(auth_client, db_session):
    """paid_at/paid_amount bleiben gepflegt, damit PDF und Export weiterlaufen."""
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "500.00", "2026-08-01")
    _zahlen(auth_client, inv["id"], "300.00", "2026-08-20")

    beleg = db_session.query(Invoice).filter_by(id=inv["id"]).first()
    db_session.refresh(beleg)
    assert beleg.paid_amount == Decimal("800.00")
    assert beleg.paid_at == date(2026, 8, 20)      # letzte Zahlung


def test_mark_paid_erzeugt_einen_zahlungseintrag(auth_client, db_session):
    """Der alte Weg bleibt bedienbar, landet aber jetzt im Zahlungsjournal."""
    inv = _offener_beleg(auth_client, db_session)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/mark-paid",
                            json={"paid_at": "2026-08-10"})
    assert resp.status_code == 200, resp.text

    stand = auth_client.get(f"/api/invoices/{inv['id']}/payments").json()
    assert len(stand["payments"]) == 1
    assert Decimal(stand["payments"][0]["amount"]) == Decimal("1200.00")
    assert stand["status"] == "bezahlt"


def test_mark_paid_nach_teilzahlung_bucht_nur_den_rest(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "500.00")

    auth_client.post(f"/api/invoices/{inv['id']}/mark-paid", json={"paid_at": "2026-08-10"})

    stand = auth_client.get(f"/api/invoices/{inv['id']}/payments").json()
    assert Decimal(stand["paid_total"]) == Decimal("1200.00")
    assert Decimal(stand["payments"][1]["amount"]) == Decimal("700.00")


def test_gutschrift_wird_negativ_ausgeglichen(auth_client, db_session):
    """Bei einer Gutschrift fließt Geld zurück — Vorzeichen bleibt erhalten."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[{
        "pos_type": "item", "description": "Rückvergütung", "quantity": "-1",
        "unit_price": "1000", "tax_rate": "20",
    }], doc_type="gutschrift")
    _ausstellen(auth_client, inv["id"])

    stand = _zahlen(auth_client, inv["id"], "-1200.00").json()
    assert stand["status"] == "bezahlt"
    assert Decimal(stand["open_amount"]) == Decimal("0.00")


# ── Abweisungen ───────────────────────────────────────────────────────────────

def test_entwurf_kann_keine_zahlung_haben(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    resp = _zahlen(auth_client, inv["id"], "100.00")
    assert resp.status_code == 400
    assert "Entwurf" in resp.json()["detail"]


def test_stornierter_beleg_kann_keine_zahlung_haben(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/cancel", json={"cancel_mode": "status_only"})

    assert _zahlen(auth_client, inv["id"], "100.00").status_code == 400


def test_angebot_kann_keine_zahlung_haben(auth_client, db_session):
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id, doc_type="angebot")
    _ausstellen(auth_client, angebot["id"], status="gesendet")

    assert _zahlen(auth_client, angebot["id"], "100.00").status_code == 400


def test_nullbetrag_abgelehnt(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    assert _zahlen(auth_client, inv["id"], "0").status_code == 400


def test_zahlung_steht_im_protokoll(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "500.00")

    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    zahlungen = [e for e in eintraege if e["action"] == "zahlung"]
    assert len(zahlungen) == 1
    assert "500.00" in zahlungen[0]["note"]
    assert "offen 700.00" in zahlungen[0]["note"]


# ── A-17b: Überfälligkeit ─────────────────────────────────────────────────────

def test_ueberfaellig_wird_automatisch_gesetzt(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session, due_date="2026-08-05")

    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 8, 6)) == 1

    beleg = db_session.query(Invoice).filter_by(id=inv["id"]).first()
    db_session.refresh(beleg)
    assert beleg.status == "ueberfaellig"


def test_nicht_faellige_bleiben_unberuehrt(auth_client, db_session):
    _offener_beleg(auth_client, db_session, due_date="2026-08-05")
    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 8, 4)) == 0


def test_beglichene_werden_nicht_ueberfaellig(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session, due_date="2026-08-05")
    _zahlen(auth_client, inv["id"], "1200.00")

    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 9, 1)) == 0


def test_teilbezahlte_werden_ueberfaellig(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session, due_date="2026-08-05")
    _zahlen(auth_client, inv["id"], "500.00")

    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 9, 1)) == 1


def test_ueberfaelligkeit_ist_wiederholbar(auth_client, db_session):
    """Der Lauf muss idempotent sein — er läuft täglich."""
    _offener_beleg(auth_client, db_session, due_date="2026-08-05")
    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 9, 1)) == 1
    assert overdue_service.markiere_ueberfaellige(db_session, date(2026, 9, 1)) == 0


def test_ueberfaelligkeit_steht_im_protokoll(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session, due_date="2026-08-05")
    overdue_service.markiere_ueberfaellige(db_session, date(2026, 8, 20))

    eintrag = (db_session.query(InvoiceAuditLog)
               .filter_by(invoice_id=inv["id"], changed_by="system:faelligkeit").first())
    assert eintrag is not None
    assert "Zahlungsziel" in eintrag.note


# ── C-3: Offene-Posten-Liste ──────────────────────────────────────────────────

def test_op_liste_zeigt_offene_forderungen(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "200.00")

    daten = auth_client.get("/api/invoices/open-items",
                            params={"stichtag": "2026-08-20"}).json()
    assert daten["count"] == 1
    posten = daten["items"][0]
    assert Decimal(posten["open_amount"]) == Decimal("1000.00")
    assert Decimal(posten["paid_total"]) == Decimal("200.00")
    assert posten["contact_name"] == "Muster GmbH"
    assert posten["days_overdue"] == 15
    assert posten["bucket"] == "b1_30"


def test_op_liste_ohne_beglichene(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    _zahlen(auth_client, inv["id"], "1200.00")

    daten = auth_client.get("/api/invoices/open-items").json()
    assert daten["count"] == 0
    assert Decimal(daten["total_open"]) == Decimal("0")


def test_op_liste_ohne_entwuerfe_und_angebote(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id)                       # Entwurf
    angebot = _create_invoice(auth_client, kontakt.id, doc_type="angebot")
    _ausstellen(auth_client, angebot["id"], status="gesendet")

    assert auth_client.get("/api/invoices/open-items").json()["count"] == 0


def test_op_liste_faelligkeitsstaffel(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    for faellig in ["2026-09-30", "2026-08-20", "2026-07-20", "2026-06-20", "2026-04-20"]:
        inv = _create_invoice(auth_client, kontakt.id, due_date=faellig)
        _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/invoices/open-items",
                            params={"stichtag": "2026-09-01"}).json()
    assert daten["count"] == 5
    # je Staffel genau ein Beleg über 1.200 €
    assert daten["buckets"] == {
        "nicht_faellig": 1200.0, "b1_30": 1200.0, "b31_60": 1200.0,
        "b61_90": 1200.0, "b90_plus": 1200.0,
    }
    assert Decimal(daten["total_open"]) == Decimal("6000.00")


def test_op_liste_summiert_je_kontakt(auth_client, db_session):
    a = _make_kontakt(db_session, display_name="Alpha GmbH")
    b = _make_kontakt(db_session, display_name="Beta GmbH")
    for kontakt, anzahl in [(a, 2), (b, 1)]:
        for _ in range(anzahl):
            inv = _create_invoice(auth_client, kontakt.id)
            _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/invoices/open-items").json()
    je_kontakt = {e["contact_name"]: e for e in daten["by_contact"]}
    assert Decimal(je_kontakt["Alpha GmbH"]["open_amount"]) == Decimal("2400.00")
    assert je_kontakt["Alpha GmbH"]["count"] == 2
    assert Decimal(je_kontakt["Beta GmbH"]["open_amount"]) == Decimal("1200.00")
    # absteigend nach Betrag
    assert daten["by_contact"][0]["contact_name"] == "Alpha GmbH"


def test_op_liste_filtert_nach_kontakt(auth_client, db_session):
    a = _make_kontakt(db_session, display_name="Alpha GmbH")
    b = _make_kontakt(db_session, display_name="Beta GmbH")
    for kontakt in (a, b):
        inv = _create_invoice(auth_client, kontakt.id)
        _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/invoices/open-items",
                            params={"contact_id": str(a.id)}).json()
    assert daten["count"] == 1
    assert daten["items"][0]["contact_name"] == "Alpha GmbH"


def test_op_liste_verlangt_das_modul_buchhaltung(client, db_session, test_user):
    """
    Verkaufsbuch und offene Posten hängen am Zusatzrecht „Buchhaltung": Wer
    Belege schreiben darf, muss nicht zwangsläufig Zahlen und Export sehen.
    """
    from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

    test_user.allowed_modules = ["verkauf"]        # Verkauf ja, Buchhaltung nein
    db_session.commit()

    token = client.post("/api/auth/login", json={
        "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/invoices", headers=kopf).status_code == 200      # Belege: ja
    assert client.get("/api/invoices/open-items", headers=kopf).status_code == 403
    assert client.get("/api/invoices/book/list", headers=kopf).status_code == 403
    assert client.get("/api/accounting/accounts", headers=kopf).status_code == 403

    test_user.allowed_modules = ["verkauf", "buchhaltung"]
    db_session.commit()
    assert client.get("/api/invoices/open-items", headers=kopf).status_code == 200


def test_op_liste_ohne_zahlungsziel_gilt_als_nicht_faellig(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, due_date=None)
    _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/invoices/open-items").json()
    assert daten["items"][0]["bucket"] == "nicht_faellig"
    assert daten["items"][0]["days_overdue"] == 0
