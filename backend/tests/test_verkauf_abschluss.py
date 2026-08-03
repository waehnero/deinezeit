"""
Tests für den Monatsabschluss und die Übergabe an die Steuerberatung.

Deckt C-6 und C-8 aus `docs/VERKAUF_ANALYSE.md` ab:

  C-6  Es gab keinen Zeitpunkt, an dem ein Monat „zu" war. Nach der Übergabe
       ließ sich weiter in den Monat buchen, ohne dass etwas gewarnt hätte.
  C-8  Es gab kein Übergabepaket — die Unterlagen mussten einzeln
       zusammengesucht werden.

Schema analog zu test_verkauf_uva.py.
"""
import io
import zipfile

from app.models.masterdata import EntityType, EntityRecord
from app.models.period import AccountingPeriod
from app.services import period_service
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


def _als_admin(client):
    resp = client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _create_invoice(client, contact_id=None, **extra):
    payload = {
        "doc_type": extra.pop("doc_type", "rechnung"),
        "contact_id": str(contact_id) if contact_id else None,
        "date": extra.pop("date", "2026-07-15"),
        "delivery_date": extra.pop("delivery_date", "2026-07-15"),
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


def _abschliessen(client, jahr=2026, monat=7):
    return client.post(f"/api/periods/{jahr}/{monat}/close")


# ── C-6: Prüfliste ────────────────────────────────────────────────────────────

def test_pruefliste_meldet_offene_entwuerfe(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    _create_invoice(auth_client, _make_kontakt(db_session).id)      # bleibt Entwurf

    daten = auth_client.get("/api/periods/2026/7/check").json()
    entwuerfe = [p for p in daten["punkte"] if p["schluessel"] == "entwuerfe"][0]
    assert entwuerfe["erfuellt"] is False
    assert entwuerfe["anzahl"] == 1
    assert entwuerfe["art"] == "blockierend"
    assert daten["abschluss_moeglich"] is False


def test_abschluss_scheitert_an_entwuerfen(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    _create_invoice(auth_client, _make_kontakt(db_session).id)

    resp = _abschliessen(auth_client)
    assert resp.status_code == 400
    assert "Entwurf" in resp.json()["detail"]


def test_pruefliste_sauber_nach_ausstellen(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/periods/2026/7/check").json()
    assert daten["abschluss_moeglich"] is True
    assert daten["monatsname"] == "Juli"
    assert daten["summen"]["anzahl"] == 1
    assert daten["summen"]["brutto"] == 1200.0


def test_hinweis_stoert_den_abschluss_nicht(auth_client, db_session, admin_user):
    """Ein Beleg ohne Kontakt ist ein Hinweis, kein Hindernis."""
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, None)      # ohne Kontakt
    _ausstellen(auth_client, inv["id"])

    daten = auth_client.get("/api/periods/2026/7/check").json()
    ohne = [p for p in daten["punkte"] if p["schluessel"] == "ohne_kontakt"][0]
    assert ohne["erfuellt"] is False
    assert ohne["art"] == "hinweis"
    assert daten["abschluss_moeglich"] is True


# ── C-6: Abschließen und Sperre ───────────────────────────────────────────────

def test_abschluss_haelt_die_kennzahlen_fest(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    resp = _abschliessen(auth_client)
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["status"] == "abgeschlossen"
    assert daten["closed_by"] == "admin@deinezeit.local"
    assert daten["totals"]["brutto"] == 1200.0


def test_kein_neuer_beleg_im_abgeschlossenen_monat(auth_client, db_session, admin_user):
    """Der Kern von C-6 — sonst ist der Abschluss wirkungslos."""
    _als_admin(auth_client)
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _ausstellen(auth_client, inv["id"])
    _abschliessen(auth_client)

    resp = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung", "contact_id": str(kontakt.id),
        "date": "2026-07-20", "delivery_date": "2026-07-20",
        "positions": [{"pos_type": "item", "description": "Nachzügler",
                       "quantity": "1", "unit_price": "500", "tax_rate": "20"}],
    })
    assert resp.status_code == 400
    assert "Juli 2026 ist abgeschlossen" in resp.json()["detail"]


def test_anderer_monat_bleibt_offen(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _ausstellen(auth_client, inv["id"])
    _abschliessen(auth_client)

    august = _create_invoice(auth_client, kontakt.id,
                             date="2026-08-03", delivery_date="2026-08-03")
    assert august["date"] == "2026-08-03"


def test_beleg_im_abgeschlossenen_monat_nicht_aenderbar(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _abschliessen_mit_entwurf_ausstellen(auth_client, inv)

    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-15",
        "delivery_date": "2026-07-15", "notes": "Nachtrag",
        "positions": [{"pos_type": "item", "description": "Beratung",
                       "quantity": "1", "unit_price": "1000", "tax_rate": "20"}],
    })
    assert resp.status_code == 400
    assert "abgeschlossen" in resp.json()["detail"]


def _abschliessen_mit_entwurf_ausstellen(client, inv):
    _ausstellen(client, inv["id"])
    assert _abschliessen(client).status_code == 200


def test_storno_im_abgeschlossenen_monat_gesperrt(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _abschliessen_mit_entwurf_ausstellen(auth_client, inv)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "with_credit"})
    assert resp.status_code == 400


def test_zahlung_bleibt_trotz_abschluss_moeglich(auth_client, db_session, admin_user):
    """
    Zahlungen ändern nichts am Belegjournal des Monats — sie dürfen nicht an
    der Sperre scheitern, sonst lässt sich ein Zahlungseingang aus dem
    Folgemonat nicht mehr erfassen.
    """
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _abschliessen_mit_entwurf_ausstellen(auth_client, inv)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/payments",
                            json={"paid_at": "2026-08-10", "amount": "1200.00"})
    assert resp.status_code == 200, resp.text


def test_abschluss_nur_fuer_admin(auth_client, db_session, test_user):
    assert _abschliessen(auth_client).status_code == 403


# ── C-6: Wiedereröffnen ───────────────────────────────────────────────────────

def test_wiedereroeffnen_braucht_begruendung(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _abschliessen_mit_entwurf_ausstellen(auth_client, inv)

    resp = auth_client.post("/api/periods/2026/7/reopen", json={"grund": "   "})
    assert resp.status_code == 400
    assert "Begründung" in resp.json()["detail"]


def test_wiedereroeffnen_dokumentiert_den_vorgang(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _abschliessen_mit_entwurf_ausstellen(auth_client, inv)

    resp = auth_client.post("/api/periods/2026/7/reopen",
                            json={"grund": "Beleg wurde vergessen"})
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["status"] == "wieder_geoeffnet"
    assert daten["reopen_reason"] == "Beleg wurde vergessen"
    assert daten["reopened_by"] == "admin@deinezeit.local"
    # Der Abschluss bleibt sichtbar — nichts wird verwischt
    assert daten["closed_at"] is not None

    # … und Buchen ist wieder möglich
    neu = _create_invoice(auth_client, kontakt.id, date="2026-07-28",
                          delivery_date="2026-07-28")
    assert neu["date"] == "2026-07-28"


def test_monatsliste_zeigt_alle_zwoelf(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    liste = auth_client.get("/api/periods", params={"jahr": 2026}).json()
    assert len(liste) == 12
    assert liste[0]["monatsname"] == "Jänner"
    assert all(m["status"] == "offen" for m in liste)


# ── C-8: Übergabepaket ────────────────────────────────────────────────────────

def test_paket_enthaelt_alle_unterlagen(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    final = _ausstellen(auth_client, inv["id"])

    resp = auth_client.get("/api/periods/2026/7/package")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        namen = set(z.namelist())
        assert "buchungsjournal.csv" in namen
        assert "belegjournal.pdf" in namen
        assert "umsatzsteuer.pdf" in namen
        assert "verkaufsbuch.csv" in namen
        assert "offene_posten.csv" in namen
        assert "UEBERGABE.txt" in namen
        assert f"belege/{final['number']}.pdf" in namen

        # Keine Fehler-Platzhalter: Jede Datei muss tatsächlich erzeugt worden
        # sein. Ohne diese Zusicherung wäre ein Paket ohne Buchungsjournal
        # unbemerkt durchgegangen — und das ist die Datei, um die es geht.
        assert not [n for n in namen if "_FEHLER" in n]

        # Das Buchungsjournal muss Inhalt haben, nicht nur existieren
        journal = z.read("buchungsjournal.csv").decode("utf-8-sig")
        assert final["number"] in journal

        protokoll = z.read("UEBERGABE.txt").decode("utf-8")
        assert "Juli 2026" in protokoll
        assert "SHA-256" in protokoll
        # Der Vorbehalt zur fehlenden Vorsteuer gehört ins Paket selbst
        assert "Vorsteuer" in protokoll


def test_paket_wird_protokolliert(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    resp = auth_client.get("/api/periods/2026/7/package")
    pruefsumme = resp.headers.get("x-handover-checksum")
    assert pruefsumme and len(pruefsumme) == 64

    historie = auth_client.get("/api/periods/2026/7/handovers").json()
    assert len(historie) == 1
    assert historie[0]["checksum"] == pruefsumme
    assert historie[0]["file_count"] > 0
    assert historie[0]["created_by"] == "admin@deinezeit.local"


def test_zweite_uebergabe_kommt_dazu(auth_client, db_session, admin_user):
    """Jede Erzeugung bleibt erhalten — sonst ist nicht belegbar, was wann rausging."""
    _als_admin(auth_client)
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, inv["id"])

    auth_client.get("/api/periods/2026/7/package")
    auth_client.get("/api/periods/2026/7/package")

    assert len(auth_client.get("/api/periods/2026/7/handovers").json()) == 2


def test_paket_auch_ohne_belege(auth_client, db_session, admin_user):
    _als_admin(auth_client)
    resp = auth_client.get("/api/periods/2026/3/package")
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        assert "UEBERGABE.txt" in z.namelist()


def test_abschluss_verlangt_das_modul_buchhaltung(client, db_session, test_user):
    from tests.conftest import TEST_USER_EMAIL

    test_user.allowed_modules = ["verkauf"]
    db_session.commit()
    token = client.post("/api/auth/login", json={
        "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]

    resp = client.get("/api/periods", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_monatsgrenzen_und_ungueltiger_monat(db_session):
    von, bis = period_service.monatsgrenzen(2026, 2)
    assert (von.day, bis.day) == (1, 28)          # 2026 kein Schaltjahr
    von, bis = period_service.monatsgrenzen(2026, 12)
    assert bis.day == 31

    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        period_service.monatsgrenzen(2026, 13)
