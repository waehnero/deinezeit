"""
Tests für Belegsperre, Nummernkreis und Änderungsprotokoll (Modul Verkauf).

Deckt die Befunde A-7, A-9, A-10, A-11 und B-4 aus `docs/VERKAUF_ANALYSE.md` ab:

  A-7  Finalisierte Belege waren frei editierbar (Positionen, Beträge, Empfänger)
  A-9  doc_type ließ sich per PUT ändern — Belegart passte dann nicht zur Nummer
  A-10 Die Nummer fiel schon beim Entwurf; ein gelöschter Entwurf riss eine Lücke
  A-11 Der Zählerstand ließ sich zurücksetzen → doppelte Belegnummer
  B-4  Es gab kein Änderungsprotokoll

Schema analog zu test_verkauf_buchhaltung.py.
"""
from datetime import date

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceAuditLog
from tests.conftest import TEST_USER_PASSWORD


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


STANDARD_POSITION = {
    "pos_type": "item", "description": "Beratung",
    "quantity": "2", "unit_price": "100", "tax_rate": "20",
}


def _create_invoice(client, contact_id=None, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Projekt Juli"),
        "date": extra.pop("date", "2026-07-06"),
        "positions": extra.pop("positions", [dict(STANDARD_POSITION)]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _als_admin(client):
    """
    Setzt den Admin-Token am Client.

    Belege löschen und Nummernkreise ändern sind Admin-Vorgänge
    (``require_admin``) — der Standard-Testbenutzer ist ein Mitarbeiter.
    """
    resp = client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _finalisieren(client, invoice_id, status="offen"):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _put(client, invoice_id, **felder):
    """PUT mit vollständigem Rumpf; einzelne Felder lassen sich überschreiben."""
    body = {
        "contact_id": felder.pop("contact_id", None),
        "title": felder.pop("title", "Projekt Juli"),
        "date": felder.pop("date", "2026-07-06"),
        "positions": felder.pop("positions", [dict(STANDARD_POSITION)]),
    }
    body.update(felder)
    return client.put(f"/api/invoices/{invoice_id}", json=body)


# ── A-10: Nummer erst beim Finalisieren ───────────────────────────────────────

def test_entwurf_hat_keine_nummer(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    assert inv["number"] is None
    assert inv["year"] is None
    assert inv["sequence"] is None
    assert inv["status"] == "entwurf"


def test_finalisieren_vergibt_die_nummer(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    final = _finalisieren(auth_client, inv["id"])
    assert final["number"] == "RE-2026-001"
    assert final["year"] == 2026
    assert final["sequence"] == 1


def test_geloeschter_entwurf_reisst_keine_luecke(auth_client, db_session, admin_user):
    """
    Kern von A-10: Früher verbrauchte jeder Entwurf sofort eine Nummer. Wurde er
    gelöscht, fehlte sie im Nummernkreis — § 11 Abs. 1 Z 3 UStG verlangt aber
    eine fortlaufende Nummer.
    """
    _als_admin(auth_client)          # Löschen ist Admin-Sache
    kontakt = _make_kontakt(db_session)
    verworfen = _create_invoice(auth_client, kontakt.id)
    assert auth_client.delete(f"/api/invoices/{verworfen['id']}").status_code == 204

    echt = _create_invoice(auth_client, kontakt.id)
    assert _finalisieren(auth_client, echt["id"])["number"] == "RE-2026-001"


def test_reihenfolge_richtet_sich_nach_dem_finalisieren(auth_client, db_session):
    """Wer zuerst ausgestellt wird, bekommt die kleinere Nummer — nicht wer zuerst angelegt wurde."""
    kontakt = _make_kontakt(db_session)
    zuerst_angelegt = _create_invoice(auth_client, kontakt.id, title="A")
    danach_angelegt = _create_invoice(auth_client, kontakt.id, title="B")

    assert _finalisieren(auth_client, danach_angelegt["id"])["number"] == "RE-2026-001"
    assert _finalisieren(auth_client, zuerst_angelegt["id"])["number"] == "RE-2026-002"


def test_duplikat_bleibt_nummernlos(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])

    dup = auth_client.post(f"/api/invoices/{inv['id']}/duplicate", json={}).json()
    assert dup["number"] is None
    assert dup["status"] == "entwurf"


def test_umwandlung_nummeriert_nur_die_quelle(auth_client, db_session):
    """Das Angebot wird ausgestellt, die entstehende Rechnung ist ein Entwurf."""
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id, doc_type="angebot")
    assert angebot["number"] is None

    rechnung = auth_client.post(f"/api/invoices/{angebot['id']}/convert-to-invoice").json()
    assert rechnung["number"] is None
    assert rechnung["status"] == "entwurf"

    quelle = auth_client.get(f"/api/invoices/{angebot['id']}").json()
    assert quelle["number"] == "AN-2026-001"
    assert quelle["status"] == "angenommen"


def test_wiederkehrende_erzeugung_bleibt_nummernlos(auth_client, db_session):
    from app.services import recurring_service

    _create_invoice(auth_client, _make_kontakt(db_session).id,
                    is_recurring_template=True, recurring_interval="monthly",
                    recurring_next="2026-01-01", date="2026-01-01")
    assert recurring_service.materialize_due_recurring(db_session, date(2026, 2, 15)) == 2

    kinder = db_session.query(Invoice).filter(Invoice.recurring_source_id.isnot(None)).all()
    assert all(k.number is None for k in kinder)


# ── A-11: Zählerstand nur aufwärts ────────────────────────────────────────────

def test_zaehler_laesst_sich_nicht_zuruecksetzen(auth_client, db_session, admin_user):
    _als_admin(auth_client)

    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])          # Zähler steht auf 1

    resp = auth_client.put("/api/invoices/number-sequences/rechnung",
                           json={"year": 2026, "last_sequence": 0})
    assert resp.status_code == 400
    assert "erhöht" in resp.json()["detail"]

    # Aufwärts bleibt erlaubt (z.B. Übernahme aus einem Altsystem)
    resp = auth_client.put("/api/invoices/number-sequences/rechnung",
                           json={"year": 2026, "last_sequence": 500})
    assert resp.status_code == 200
    assert resp.json()["next_sequence"] == 501


# ── A-7 / A-9: Belegsperre ────────────────────────────────────────────────────

def test_entwurf_bleibt_frei_bearbeitbar(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = _put(auth_client, inv["id"], contact_id=str(kontakt.id), title="Anderer Titel",
                positions=[{"pos_type": "item", "description": "Ganz was anderes",
                            "quantity": "5", "unit_price": "42", "tax_rate": "10"}])
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Anderer Titel"
    assert float(resp.json()["subtotal"]) == 210.0


def test_positionen_auf_ausgestelltem_beleg_gesperrt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    resp = _put(auth_client, inv["id"], contact_id=str(kontakt.id),
                positions=[{"pos_type": "item", "description": "Beratung",
                            "quantity": "20", "unit_price": "100", "tax_rate": "20"}])
    assert resp.status_code == 400
    assert "Positionen" in resp.json()["detail"]

    # Betrag unverändert
    assert float(auth_client.get(f"/api/invoices/{inv['id']}").json()["total"]) == 240.0


def test_gedruckte_felder_auf_ausgestelltem_beleg_gesperrt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    for feld, wert, erwartet in [
        ("title",      "Neuer Titel",  "Titel"),
        ("date",       "2026-09-01",   "Belegdatum"),
        ("intro_text", "Anderer Text", "Einleitungstext"),
        ("tax_mode",   "kleinunternehmer", "MwSt.-Modus"),
    ]:
        resp = _put(auth_client, inv["id"], contact_id=str(kontakt.id), **{feld: wert})
        assert resp.status_code == 400, f"{feld} hätte gesperrt sein müssen"
        assert erwartet in resp.json()["detail"]


def test_interne_notiz_bleibt_aenderbar(auth_client, db_session):
    """Die Notiz steht nicht auf dem Beleg und bleibt daher offen."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    resp = _put(auth_client, inv["id"], contact_id=str(kontakt.id),
                notes="Kunde hat telefonisch zugesagt")
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "Kunde hat telefonisch zugesagt"


def test_unveraenderte_uebermittlung_ist_keine_aenderung(auth_client, db_session):
    """
    Das Formular schickt beim Speichern immer den kompletten Beleg zurück.
    Wenn nichts verändert wurde, darf die Sperre nicht anschlagen — sonst
    ließe sich nicht einmal die Notiz speichern.
    """
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    aktuell = auth_client.get(f"/api/invoices/{inv['id']}").json()
    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": aktuell["contact_id"],
        "title": aktuell["title"],
        "date": aktuell["date"],
        "tax_mode": aktuell["tax_mode"],
        "currency": aktuell["currency"],
        "template_id": aktuell["template_id"],
        "notes": "nur die Notiz ist neu",
        "positions": [{
            "pos_type": p["pos_type"], "description": p["description"],
            "quantity": p["quantity"], "unit_price": p["unit_price"],
            "tax_rate": p["tax_rate"], "unit": p["unit"], "detail": p["detail"],
        } for p in aktuell["positions"]],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "nur die Notiz ist neu"


def test_belegart_laesst_sich_nicht_umbiegen(auth_client, db_session):
    """A-9: doc_type ist kein Feld von InvoiceUpdate — die Belegart bleibt."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)

    resp = _put(auth_client, inv["id"], contact_id=str(kontakt.id), doc_type="angebot")
    assert resp.status_code == 200, resp.text
    assert resp.json()["doc_type"] == "rechnung"


# ── Lebenszyklus: Löschen und Stornieren ──────────────────────────────────────

def test_ausgestellter_beleg_nicht_loeschbar(auth_client, db_session, admin_user):
    """Auch der Admin kommt nicht an einen ausgestellten Beleg."""
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.delete(f"/api/invoices/{inv['id']}")
    assert resp.status_code == 400
    assert "Aufbewahrungspflicht" in resp.json()["detail"]


def test_stornierter_beleg_nicht_loeschbar(auth_client, db_session, admin_user):
    """Auch nach dem Storno bleibt der Beleg erhalten (§ 132 BAO)."""
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/cancel", json={"cancel_mode": "status_only"})

    assert auth_client.delete(f"/api/invoices/{inv['id']}").status_code == 400


def test_entwurf_wird_geloescht_nicht_storniert(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "with_credit"})
    assert resp.status_code == 400
    assert "gelöscht" in resp.json()["detail"]


def test_angebot_kann_nicht_bezahlt_werden(auth_client, db_session):
    """A-8: mark-paid prüfte weder Belegart noch Status."""
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id, doc_type="angebot")
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/mark-paid",
                            json={"paid_at": "2026-07-10"})
    assert resp.status_code == 400


# ── B-4: Änderungsprotokoll ───────────────────────────────────────────────────

def test_protokoll_haelt_ausstellung_fest(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    # Am Entwurf wird nichts protokolliert
    assert auth_client.get(f"/api/invoices/{inv['id']}/audit").json() == []

    _finalisieren(auth_client, inv["id"])
    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    assert len(eintraege) == 1
    e = eintraege[0]
    assert e["action"] == "finalisiert"
    assert e["changes"]["status"] == {"alt": "entwurf", "neu": "offen"}
    assert e["changes"]["number"]["neu"] == "RE-2026-001"
    assert e["changed_by"] == "test@deinezeit.local"


def test_protokoll_haelt_notizaenderung_fest(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])
    _put(auth_client, inv["id"], contact_id=str(kontakt.id), notes="Zahlung avisiert")

    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    bearbeitet = [e for e in eintraege if e["action"] == "bearbeitet"]
    assert len(bearbeitet) == 1
    assert bearbeitet[0]["changes"]["notes"]["neu"] == "Zahlung avisiert"


def test_protokoll_haelt_zahlung_und_storno_fest(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/mark-paid", json={"paid_at": "2026-07-10"})

    aktionen = [e["action"] for e in auth_client.get(f"/api/invoices/{inv['id']}/audit").json()]
    assert "bezahlt" in aktionen

    inv2 = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv2["id"])
    auth_client.post(f"/api/invoices/{inv2['id']}/cancel", json={"cancel_mode": "with_credit"})

    eintraege = auth_client.get(f"/api/invoices/{inv2['id']}/audit").json()
    storno = [e for e in eintraege if e["action"] == "storniert"]
    assert len(storno) == 1
    assert "Gutschrift" in storno[0]["note"]


def test_protokoll_neueste_zuerst(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "gesendet"})

    eintraege = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()

    # Der Wechsel auf 'gesendet' ist zugleich ein Archiv-Auslöser und
    # hinterlässt deshalb einen zusätzlichen Eintrag. Statt auf eine feste
    # Anzahl zu prüfen, wird hier die Sortierung geprüft — darum geht es.
    zeiten = [e["changed_at"] for e in eintraege]
    assert zeiten == sorted(zeiten, reverse=True)

    status_eintraege = [e for e in eintraege if e["action"] == "status"]
    assert status_eintraege[0]["changes"]["status"]["neu"] == "gesendet"


def test_protokoll_unbekannter_beleg_404(auth_client, db_session):
    from uuid import uuid4
    assert auth_client.get(f"/api/invoices/{uuid4()}/audit").status_code == 404


def test_protokoll_haengt_am_beleg_und_verschwindet_mit_ihm(auth_client, db_session):
    """Wird ein Entwurf gelöscht, räumt die FK-Kaskade das Protokoll mit ab."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _finalisieren(auth_client, inv["id"])
    assert db_session.query(InvoiceAuditLog).count() == 1

    obj = db_session.query(Invoice).filter(Invoice.id == inv["id"]).first()
    db_session.delete(obj)
    db_session.commit()
    assert db_session.query(InvoiceAuditLog).count() == 0
