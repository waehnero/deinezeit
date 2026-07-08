"""
Tests für die Verkauf-Erweiterungen:

  1. Duplizieren von Belegen mit selektiven Optionen
  2. Wiederkehrende Rechnungen (Auto-Erstellung als Entwurf)
  3. Erweiterte Suche (Kontakt / Artikel / Projekt)
  4. PDF-Archivierung: Auslöser-Parametrisierung & Gating

Schema analog zu test_invoice_snapshot.py.
"""
from datetime import date

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceSettings
from app.services import recurring_service
from app.services import invoice_archive


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


def _create_invoice(client, contact_id, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Projekt März"),
        "intro_text": extra.pop("intro_text", "Vielen Dank für Ihren Auftrag."),
        "date": extra.pop("date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Spezialberatung",
            "quantity": "2", "unit_price": "100", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Feature 1: Duplizieren ────────────────────────────────────────────────────

def test_duplicate_uebernimmt_positionen_und_kontakt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/duplicate",
                            json={"positions": True, "texts": True,
                                  "contact": True, "attachments": False})
    assert resp.status_code == 200, resp.text
    dup = resp.json()
    assert dup["id"] != inv["id"]
    assert dup["number"] != inv["number"]
    assert dup["status"] == "entwurf"
    assert dup["contact_id"] == inv["contact_id"]
    assert len(dup["positions"]) == len(inv["positions"])
    assert dup["intro_text"] == inv["intro_text"]


def test_duplicate_ohne_texte_und_kontakt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/duplicate",
                            json={"positions": True, "texts": False,
                                  "contact": False, "attachments": False})
    assert resp.status_code == 200, resp.text
    dup = resp.json()
    assert dup["intro_text"] is None
    assert dup["contact_id"] is None
    assert dup["title"] is None
    assert len(dup["positions"]) == 1   # Positionen trotzdem übernommen


# ── Feature 2: Wiederkehrende Rechnungen ──────────────────────────────────────

def test_advance_monatswechsel_am_monatsende():
    # 31.01 + 1 Monat → 28.02 (2026 kein Schaltjahr)
    assert recurring_service.advance(date(2026, 1, 31), "monthly") == date(2026, 2, 28)
    assert recurring_service.advance(date(2026, 1, 15), "weekly") == date(2026, 1, 22)
    assert recurring_service.advance(date(2026, 1, 15), "quarterly") == date(2026, 4, 15)
    assert recurring_service.advance(date(2026, 1, 15), "yearly") == date(2027, 1, 15)


def test_wiederkehrend_erzeugt_entwuerfe(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id,
                    is_recurring_template=True,
                    recurring_interval="monthly",
                    recurring_next="2026-01-01",
                    date="2026-01-01")

    # Stichtag 15.03.2026 → Termine 01.01, 01.02, 01.03 fällig = 3 Entwürfe
    created = recurring_service.materialize_due_recurring(db_session, date(2026, 3, 15))
    assert created == 3

    kinder = db_session.query(Invoice).filter(Invoice.recurring_source_id.isnot(None)).all()
    assert len(kinder) == 3
    assert all(k.status == "entwurf" for k in kinder)
    assert all(k.doc_type == "rechnung" for k in kinder)

    tpl = db_session.query(Invoice).filter(Invoice.is_recurring_template.is_(True)).first()
    assert tpl.recurring_next == date(2026, 4, 1)   # weitergesetzt


def test_wiederkehrend_stoppt_am_enddatum(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id,
                    is_recurring_template=True,
                    recurring_interval="monthly",
                    recurring_next="2026-01-01",
                    recurring_end="2026-02-15",
                    date="2026-01-01")

    created = recurring_service.materialize_due_recurring(db_session, date(2026, 6, 1))
    assert created == 2   # nur 01.01 und 01.02, danach Enddatum überschritten
    tpl = db_session.query(Invoice).filter(Invoice.is_recurring_template.is_(True)).first()
    assert tpl.recurring_next is None


def test_templates_in_hauptliste_und_eigenem_tab(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id,
                    is_recurring_template=True, recurring_interval="monthly",
                    recurring_next="2026-01-01")
    # Vorlage läuft in der Hauptliste mit (markiert)
    liste = auth_client.get("/api/invoices").json()
    assert any(i["is_recurring_template"] for i in liste)
    # und erscheint zusätzlich im eigenen Wiederkehrend-Tab
    templates = auth_client.get("/api/invoices/templates").json()
    assert len(templates) == 1


# ── Feature 3: Erweiterte Suche ───────────────────────────────────────────────

def test_suche_nach_kontaktname(auth_client, db_session):
    kontakt = _make_kontakt(db_session, display_name="Sonnenschein AG")
    _create_invoice(auth_client, kontakt.id, title="Irgendwas")

    treffer = auth_client.get("/api/invoices", params={"search": "Sonnenschein"}).json()
    assert len(treffer) == 1
    assert treffer[0]["contact_name"] == "Sonnenschein AG"


def test_suche_nach_positionstext(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id,
                    positions=[{"pos_type": "item", "description": "Spezialberatung XY",
                                "quantity": "1", "unit_price": "50", "tax_rate": "20"}])

    treffer = auth_client.get("/api/invoices", params={"search": "Spezialberatung"}).json()
    assert len(treffer) == 1


# ── Feature 4: Archiv-Auslöser ────────────────────────────────────────────────

def test_archive_triggers_default_und_gesetzt(db_session):
    assert invoice_archive.get_archive_triggers(db_session) == invoice_archive.DEFAULT_TRIGGERS
    db_session.add(InvoiceSettings(key="archive_triggers", value=["gesendet", "bezahlt"]))
    db_session.commit()
    assert set(invoice_archive.get_archive_triggers(db_session)) == {"gesendet", "bezahlt"}


def test_archive_gating_ohne_trigger(auth_client, db_session):
    """Nicht aktivierter Auslöser → keine Archivierung (kein PDF/Upload nötig)."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    inv_obj = db_session.query(Invoice).filter_by(id=inv["id"]).first()

    db_session.add(InvoiceSettings(key="archive_triggers", value=["bezahlt"]))
    db_session.commit()

    # Auslöser 'email' ist NICHT aktiviert → False, ohne PDF-Erzeugung
    assert invoice_archive.archive_invoice_pdf(db_session, inv_obj, "email") is False


def test_archive_gating_ohne_kontakt(db_session):
    """Ohne Kontakt kann nicht archiviert werden."""
    inv = Invoice(doc_type="rechnung", number="RE-2026-999", year=2026, sequence=999,
                  date=date(2026, 7, 6), contact_id=None)
    db_session.add(inv)
    db_session.commit()
    assert invoice_archive.archive_invoice_pdf(db_session, inv, "email") is False
