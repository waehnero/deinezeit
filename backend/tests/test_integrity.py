"""
Tests für die Löschregeln / Datenintegrität (Bugfix Datenzusammenhänge).

Regelwerk (Beschluss 2026-07-11):
- Stammdaten löschen: nur Admin, nur ohne Verweise anderer Module (sonst 409).
- Mit Verweisen: archivieren (Admin) + wiederherstellen; archivierte Datensätze
  verschwinden aus der Standard-Liste.
- Zeiteinträge: nur eigene löschen/ändern (Admin: alle); abgerechnete
  Einträge (Belegposition verweist darauf) sind gesperrt.
- Projektplan: Projekte/Aufgaben mit gebuchten Zeiteinträgen sind unlöschbar.
"""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.models.zeiterfassung import TimeEntry
from app.models.invoice import Invoice, InvoicePosition
from app.models.projektplan import PlanningProject, Task
from app.services import integrity

from tests.conftest import TEST_USER_PASSWORD


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _login(client, email):
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_record(db, slug="kontakte", name="Muster GmbH"):
    et = db.query(EntityType).filter_by(slug=slug).first()
    if not et:
        et = EntityType(name=slug.capitalize(), slug=slug)
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=name,
                       data={"name": name})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _make_entry(db, user_id, contact_id=None, project_id=None):
    now = datetime.now(timezone.utc)
    e = TimeEntry(user_id=user_id, contact_id=contact_id, project_id=project_id,
                  started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=1))
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _bill_entry(db, entry):
    """Zeiteintrag 'abrechnen': Beleg + Position mit time_entry_id anlegen."""
    inv = Invoice(doc_type="rechnung", number="RE-INT-1", year=2026,
                  sequence=1, status="gestellt", date=date(2026, 7, 1))
    db.add(inv)
    db.flush()
    pos = InvoicePosition(invoice_id=inv.id, description="Stunden",
                          pos_type="time_entry", time_entry_id=entry.id,
                          quantity=Decimal("1"), unit_price=Decimal("100"),
                          line_total=Decimal("100"))
    db.add(pos)
    db.commit()
    return inv


# ── Stammdaten löschen ────────────────────────────────────────────────────────

def test_delete_record_verweigert_fuer_normale_benutzer(client, db_session, test_user, admin_user):
    rec = _make_record(db_session)
    headers = _login(client, test_user.email)
    resp = client.delete(f"/api/masterdata/types/kontakte/records/{rec.id}",
                         headers=headers)
    assert resp.status_code == 403


def test_delete_record_ohne_verweise_als_admin(client, db_session, admin_user):
    rec = _make_record(db_session)
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/masterdata/types/kontakte/records/{rec.id}",
                         headers=headers)
    assert resp.status_code == 200
    assert db_session.query(EntityRecord).filter_by(id=rec.id).first() is None


def test_delete_record_mit_zeiteintrag_blockiert(client, db_session, test_user, admin_user):
    rec = _make_record(db_session)
    _make_entry(db_session, test_user.id, contact_id=rec.id)
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/masterdata/types/kontakte/records/{rec.id}",
                         headers=headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "zeiteintraege" in detail["references"]
    # Datensatz existiert weiterhin
    assert db_session.query(EntityRecord).filter_by(id=rec.id).first() is not None


def test_delete_record_mit_beleg_blockiert(client, db_session, admin_user):
    rec = _make_record(db_session)
    inv = Invoice(doc_type="rechnung", number="RE-INT-2", year=2026,
                  sequence=2, status="bezahlt", contact_id=rec.id,
                  date=date(2026, 7, 1))
    db_session.add(inv)
    db_session.commit()
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/masterdata/types/kontakte/records/{rec.id}",
                         headers=headers)
    assert resp.status_code == 409
    assert "belege" in resp.json()["detail"]["references"]


def test_references_endpoint(client, db_session, test_user, admin_user):
    rec = _make_record(db_session)
    _make_entry(db_session, test_user.id, contact_id=rec.id)
    headers = _login(client, test_user.email)
    resp = client.get(f"/api/masterdata/types/kontakte/records/{rec.id}/references",
                      headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_references"] is True
    assert body["deletable"] is False
    assert body["references"]["zeiteintraege"]["count"] == 1


# ── Archivieren / Wiederherstellen ───────────────────────────────────────────

def test_archivieren_und_wiederherstellen(client, db_session, test_user, admin_user):
    rec = _make_record(db_session)
    admin_headers = _login(client, admin_user.email)
    user_headers = _login(client, test_user.email)

    # Normale Benutzer dürfen nicht archivieren
    resp = client.post(f"/api/masterdata/types/kontakte/records/{rec.id}/archive",
                       headers=user_headers)
    assert resp.status_code == 403

    # Admin archiviert
    resp = client.post(f"/api/masterdata/types/kontakte/records/{rec.id}/archive",
                       headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None

    # Standard-Liste: weg; Archiv-Liste: da
    resp = client.get("/api/masterdata/types/kontakte/records", headers=user_headers)
    assert resp.json()["total"] == 0
    resp = client.get("/api/masterdata/types/kontakte/records?archived=only",
                      headers=user_headers)
    assert resp.json()["total"] == 1

    # Doppelt archivieren → 400
    resp = client.post(f"/api/masterdata/types/kontakte/records/{rec.id}/archive",
                       headers=admin_headers)
    assert resp.status_code == 400

    # Wiederherstellen
    resp = client.post(f"/api/masterdata/types/kontakte/records/{rec.id}/restore",
                       headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is None
    resp = client.get("/api/masterdata/types/kontakte/records", headers=user_headers)
    assert resp.json()["total"] == 1


# ── Zeiteinträge ──────────────────────────────────────────────────────────────

def test_fremden_zeiteintrag_loeschen_verboten(client, db_session, test_user, admin_user):
    fremder = _make_entry(db_session, admin_user.id)
    headers = _login(client, test_user.email)
    resp = client.delete(f"/api/zeiterfassung/entries/{fremder.id}", headers=headers)
    assert resp.status_code == 403
    # Eigener Eintrag geht
    eigener = _make_entry(db_session, test_user.id)
    resp = client.delete(f"/api/zeiterfassung/entries/{eigener.id}", headers=headers)
    assert resp.status_code == 200


def test_admin_darf_fremde_eintraege_loeschen(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/zeiterfassung/entries/{entry.id}", headers=headers)
    assert resp.status_code == 200


def test_abgerechneter_zeiteintrag_gesperrt(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    _bill_entry(db_session, entry)
    headers = _login(client, test_user.email)

    # Löschen gesperrt (auch für den Eigentümer)
    resp = client.delete(f"/api/zeiterfassung/entries/{entry.id}", headers=headers)
    assert resp.status_code == 409

    # Bearbeiten gesperrt
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}",
                      json={"note": "nachträglich geändert"}, headers=headers)
    assert resp.status_code == 409

    # Auch der Admin darf abgerechnete Einträge nicht löschen
    admin_headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/zeiterfassung/entries/{entry.id}",
                         headers=admin_headers)
    assert resp.status_code == 409


# ── Zeiteintrag-Status (Abrechnungs-Workflow) ─────────────────────────────────

def test_mitarbeiter_darf_eigene_freigeben(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    headers = _login(client, test_user.email)

    # veraenderbar → freigegeben: erlaubt
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}/status",
                      json={"status": "freigegeben"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "freigegeben"

    # weiterer Wechsel (freigegeben → abgerechnet): nur Admin
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}/status",
                      json={"status": "abgerechnet"}, headers=headers)
    assert resp.status_code == 403


def test_mitarbeiter_darf_fremde_nicht_freigeben(client, db_session, test_user, admin_user):
    fremder = _make_entry(db_session, admin_user.id)
    headers = _login(client, test_user.email)
    resp = client.put(f"/api/zeiterfassung/entries/{fremder.id}/status",
                      json={"status": "freigegeben"}, headers=headers)
    assert resp.status_code == 403


def test_nicht_veraenderbarer_eintrag_gesperrt(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    admin_headers = _login(client, admin_user.email)
    user_headers = _login(client, test_user.email)

    # Admin sperrt den Eintrag
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}/status",
                      json={"status": "gesperrt"}, headers=admin_headers)
    assert resp.status_code == 200

    # Eigentümer kann weder bearbeiten noch löschen
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}",
                      json={"note": "Änderung"}, headers=user_headers)
    assert resp.status_code == 409
    resp = client.delete(f"/api/zeiterfassung/entries/{entry.id}", headers=user_headers)
    assert resp.status_code == 409

    # Admin setzt zurück auf veraenderbar → löschen geht wieder
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}/status",
                      json={"status": "veraenderbar"}, headers=admin_headers)
    assert resp.status_code == 200
    resp = client.delete(f"/api/zeiterfassung/entries/{entry.id}", headers=user_headers)
    assert resp.status_code == 200


def test_beleg_abgerechnet_nicht_zuruecksetzbar(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    _bill_entry(db_session, entry)
    entry.status = "abgerechnet"
    db_session.commit()

    admin_headers = _login(client, admin_user.email)
    resp = client.put(f"/api/zeiterfassung/entries/{entry.id}/status",
                      json={"status": "veraenderbar"}, headers=admin_headers)
    assert resp.status_code == 409  # erst Beleg stornieren


def test_status_batch(client, db_session, test_user, admin_user):
    eigene = [_make_entry(db_session, test_user.id) for _ in range(2)]
    fremd = _make_entry(db_session, admin_user.id)
    headers = _login(client, test_user.email)

    resp = client.post("/api/zeiterfassung/entries/status-batch",
                       json={"entry_ids": [str(e.id) for e in eigene] + [str(fremd.id)],
                             "status": "freigegeben"},
                       headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["changed"] == 2          # eigene freigegeben
    assert len(body["skipped"]) == 1     # fremder übersprungen

    # Ungültiger Status → 400
    resp = client.post("/api/zeiterfassung/entries/status-batch",
                       json={"entry_ids": [str(eigene[0].id)], "status": "quatsch"},
                       headers=headers)
    assert resp.status_code == 400


# ── Projektplan ───────────────────────────────────────────────────────────────

def _make_planning(db):
    proj = PlanningProject(name="Testprojekt")
    db.add(proj)
    db.flush()
    task = Task(project_id=proj.id, title="Aufgabe A")
    db.add(task)
    db.commit()
    db.refresh(proj)
    db.refresh(task)
    return proj, task


def test_projekt_mit_gebuchten_zeiten_unloeschbar(client, db_session, test_user, admin_user):
    proj, task = _make_planning(db_session)
    entry = _make_entry(db_session, test_user.id)
    entry.task_id = task.id
    db_session.commit()

    admin_headers = _login(client, admin_user.email)

    # Projekt löschen: 409 wegen gebuchter Zeiten
    resp = client.delete(f"/api/projektplan/projects/{proj.id}", headers=admin_headers)
    assert resp.status_code == 409

    # Aufgabe löschen: ebenfalls 409
    resp = client.delete(f"/api/projektplan/tasks/{task.id}", headers=admin_headers)
    assert resp.status_code == 409

    # Normale Benutzer dürfen Projekte gar nicht löschen
    user_headers = _login(client, test_user.email)
    resp = client.delete(f"/api/projektplan/projects/{proj.id}", headers=user_headers)
    assert resp.status_code == 403


def test_projekt_ohne_zeiten_loeschbar(client, db_session, admin_user):
    proj, task = _make_planning(db_session)
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/projektplan/projects/{proj.id}", headers=headers)
    assert resp.status_code == 200


# ── Aufgaben (Todos) ──────────────────────────────────────────────────────────

def _make_todo(db, created_by=None, **kwargs):
    from app.models.aufgaben import Todo
    t = Todo(title="Testaufgabe", created_by=created_by, **kwargs)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_todo_nur_beteiligte_duerfen_loeschen(client, db_session, test_user, admin_user):
    fremde = _make_todo(db_session, created_by=admin_user.id)
    headers = _login(client, test_user.email)
    resp = client.delete(f"/api/aufgaben/{fremde.id}", headers=headers)
    assert resp.status_code == 403

    eigene = _make_todo(db_session, created_by=test_user.id)
    resp = client.delete(f"/api/aufgaben/{eigene.id}", headers=headers)
    assert resp.status_code == 204


def test_todo_mit_zeiteintrag_unloeschbar(client, db_session, test_user, admin_user):
    entry = _make_entry(db_session, test_user.id)
    todo = _make_todo(db_session, created_by=test_user.id, time_entry_id=entry.id)
    headers = _login(client, test_user.email)
    resp = client.delete(f"/api/aufgaben/{todo.id}", headers=headers)
    assert resp.status_code == 409

    # Archivieren geht stattdessen
    resp = client.put(f"/api/aufgaben/{todo.id}",
                      json={"is_archived": True}, headers=headers)
    assert resp.status_code == 200


# ── Datacenter-Anhänge ────────────────────────────────────────────────────────

def _make_attachment(db, contact_id=None, folder=None):
    from app.models.attachment import Attachment
    att = Attachment(entity_type="kontakte", entity_id=contact_id or _uuid4(),
                     type="link", link_url="https://example.org",
                     display_name="Testdatei", contact_id=contact_id,
                     folder=folder)
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def _uuid4():
    import uuid
    return uuid.uuid4()


def test_anhang_mit_belegverknuepfung_unloeschbar(client, db_session, test_user, admin_user):
    from app.models.invoice import Invoice, InvoiceAttachment
    att = _make_attachment(db_session, folder="Verträge")
    inv = Invoice(doc_type="rechnung", number="RE-INT-3", year=2026,
                  sequence=3, status="gestellt", date=date(2026, 7, 1))
    db_session.add(inv)
    db_session.flush()
    db_session.add(InvoiceAttachment(invoice_id=inv.id, attach_type="contract",
                                     datacenter_id=att.id))
    db_session.commit()

    # Auch der Admin muss über das Verkaufsmodul gehen
    headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/datacenter/{att.id}", headers=headers)
    assert resp.status_code == 409
    assert "RE-INT-3" in resp.json()["detail"]


def test_belegarchiv_ordner_nur_admin(client, db_session, test_user, admin_user):
    att = _make_attachment(db_session, folder="Rechnungen")
    user_headers = _login(client, test_user.email)
    resp = client.delete(f"/api/datacenter/{att.id}", headers=user_headers)
    assert resp.status_code == 403

    admin_headers = _login(client, admin_user.email)
    resp = client.delete(f"/api/datacenter/{att.id}", headers=admin_headers)
    assert resp.status_code == 200


def test_normaler_anhang_loeschbar(client, db_session, test_user, admin_user):
    att = _make_attachment(db_session, folder=None)
    headers = _login(client, test_user.email)
    resp = client.delete(f"/api/datacenter/{att.id}", headers=headers)
    assert resp.status_code == 200


# ── Stundenkonten-FK (RESTRICT) ───────────────────────────────────────────────

def test_projektzeit_mit_stundenkonto_nicht_loeschbar_db(db_session, test_user):
    """Die DB selbst verhindert das Löschen einer Projektzeit mit Stundenkonten."""
    from datetime import date
    from sqlalchemy.exc import IntegrityError
    from app.models.zeiterfassung import Stundenkonto

    rec = _make_record(db_session, slug="projektzeiten", name="Projekt X")
    konto = Stundenkonto(project_id=rec.id, stunden=Decimal("10"),
                         erworben_am=date(2026, 7, 1))
    db_session.add(konto)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.delete(rec)
        db_session.commit()
    db_session.rollback()


def test_integrity_service_zaehlt_stundenkonten(db_session, test_user):
    from datetime import date
    from app.models.zeiterfassung import Stundenkonto

    rec = _make_record(db_session, slug="projektzeiten", name="Projekt Y")
    db_session.add(Stundenkonto(project_id=rec.id, stunden=Decimal("5"),
                                erworben_am=date(2026, 7, 1)))
    db_session.commit()

    refs = integrity.count_references(db_session, rec.id)
    assert refs["stundenkonten"]["count"] == 1
    assert integrity.has_references(db_session, rec.id) is True
