"""
Tests für den Empfänger-Snapshot auf Belegen (DSGVO / Belegaufbewahrung).

Hintergrund: Beim Finalisieren eines Belegs (Status verlässt 'entwurf')
werden die Empfängerdaten aus dem Stammdaten-Kontakt in
invoices.recipient_snapshot eingefroren. PDF/Vorschau rendern ab dann aus
dem Snapshot — spätere Kontakt-Änderungen oder eine DSGVO-Anonymisierung
verändern den Beleg nicht mehr.
"""
import uuid

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice


# ── Hilfen ────────────────────────────────────────────────────────────────────

KONTAKT_DATA = {
    "ansprechperson": "Max Mustermann",
    "adresse": "Musterstraße 1",
    "plz": "5020",
    "ort": "Salzburg",
    "land": "Österreich",
    "uid": "ATU12345678",
    "email": "max@muster.at",
}


def _make_kontakt(db, display_name="Muster GmbH", data=None):
    """Legt einen Stammdaten-Kontakt (EntityRecord) direkt in der DB an."""
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id,
                       display_name=display_name,
                       data=dict(data or KONTAKT_DATA))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id, doc_type="rechnung"):
    resp = client.post("/api/invoices", json={
        "doc_type": doc_type,
        "contact_id": str(contact_id),
        "date": "2026-07-06",
        "positions": [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "2", "unit_price": "100", "tax_rate": "20",
        }],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_entwurf_hat_keinen_snapshot(auth_client, db_session):
    """Neu angelegte Belege sind Entwürfe und tragen noch keinen Snapshot."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    assert inv["status"] == "entwurf"
    assert inv["recipient_snapshot"] is None


def test_finalisieren_friert_empfaenger_ein(auth_client, db_session):
    """Statuswechsel entwurf → offen erzeugt den Snapshot."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/set-status",
                            json={"status": "offen"})
    assert resp.status_code == 200, resp.text
    snap = resp.json()["recipient_snapshot"]
    assert snap is not None
    assert snap["display_name"] == "Muster GmbH"
    assert snap["data"]["adresse"] == "Musterstraße 1"
    assert snap["frozen_at"]
    assert snap["source"] == "finalize"


def test_snapshot_bleibt_bei_kontakt_aenderung_stabil(auth_client, db_session):
    """Kontakt-Änderung NACH Finalisierung verändert den Snapshot nicht."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    # Kontakt nachträglich ändern (z.B. Umzug oder DSGVO-Anonymisierung)
    kontakt.display_name = "Gelöschter Kontakt"
    kontakt.data = {}
    db_session.commit()

    resp = auth_client.get(f"/api/invoices/{inv['id']}")
    snap = resp.json()["recipient_snapshot"]
    assert snap["display_name"] == "Muster GmbH"
    assert snap["data"]["plz"] == "5020"


def test_pdf_vorschau_nutzt_snapshot_nach_kontakt_loeschung(auth_client, db_session):
    """HTML-Vorschau rendert aus dem Snapshot, auch wenn der Kontakt weg ist."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    # Kontakt anonymisieren wie bei einer DSGVO-Löschung
    kontakt.display_name = "Gelöschter Kontakt"
    kontakt.data = {}
    db_session.commit()

    resp = auth_client.get(f"/api/invoices/{inv['id']}/preview")
    assert resp.status_code == 200
    html = resp.text
    assert "Muster GmbH" in html          # eingefrorener Empfänger
    assert "Musterstraße 1" in html
    assert "Gelöschter Kontakt" not in html


def test_entwurf_vorschau_rendert_live(auth_client, db_session):
    """Entwürfe (kein Snapshot) rendern weiterhin live aus den Stammdaten."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    kontakt.display_name = "Neuer Name GmbH"
    db_session.commit()

    resp = auth_client.get(f"/api/invoices/{inv['id']}/preview")
    assert resp.status_code == 200
    assert "Neuer Name GmbH" in resp.text


def test_mark_paid_erzeugt_snapshot_fuer_altbestand(auth_client, db_session):
    """Belege ohne Snapshot (Altbestand) werden bei mark-paid nachgezogen."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/mark-paid",
                            json={"paid_at": "2026-07-06"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recipient_snapshot"] is not None


def test_kontakt_tausch_auf_finalisiertem_beleg_erneuert_snapshot(auth_client, db_session):
    """Wird auf einem finalisierten Beleg der Kontakt getauscht, wird neu eingefroren."""
    kontakt_a = _make_kontakt(db_session, display_name="Firma A")
    kontakt_b = _make_kontakt(db_session, display_name="Firma B",
                              data={"adresse": "Weg 2", "plz": "1010", "ort": "Wien"})
    inv = _create_invoice(auth_client, kontakt_a.id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "doc_type": "rechnung",
        "contact_id": str(kontakt_b.id),
        "date": "2026-07-06",
        "positions": [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "2", "unit_price": "100", "tax_rate": "20",
        }],
    })
    assert resp.status_code == 200, resp.text
    snap = resp.json()["recipient_snapshot"]
    assert snap["display_name"] == "Firma B"


def test_storno_mit_gutschrift_kopiert_snapshot(auth_client, db_session):
    """Die bei Storno erzeugte Gutschrift übernimmt den Empfänger-Snapshot."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "with_credit"})
    assert resp.status_code == 200, resp.text

    gutschrift = db_session.query(Invoice).filter(
        Invoice.related_invoice_id == uuid.UUID(inv["id"]),
        Invoice.doc_type == "gutschrift",
    ).first()
    assert gutschrift is not None
    assert gutschrift.recipient_snapshot is not None
    assert gutschrift.recipient_snapshot["display_name"] == "Muster GmbH"
