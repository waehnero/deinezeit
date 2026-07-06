"""
Tests für die DSGVO-Löschung (Anonymisierung) von Kontakten.

Getestet wird der Service app/services/gdpr.py direkt gegen die Test-DB:
Betroffenheits-Report, Blocker (Firmenkontakt, offene Belege, laufende
Projekte), die Anonymisierung über alle Tabellen und das Löschprotokoll.
"""
from datetime import date, datetime, timezone

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.models.zeiterfassung import TimeEntry
from app.models.attachment import Attachment
from app.models.projektplan import PlanningProject, Task, ChecklistItem
from app.models.aufgaben import Todo
from app.models.invoice import Invoice
from app.models.settings import Setting
from app.models.gdpr import GdprDeletionLog
from app.services import gdpr
from app.services.gdpr import ANONYM_NAME, GdprBlockedError


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(
        entity_type_id=et.id,
        display_name=display_name,
        data={"adresse": "Musterstraße 1", "plz": "5020", "ort": "Salzburg",
              "email": "max@muster.at"},
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _make_invoice(db, contact_id, status="bezahlt", inv_date=None, number=None,
                  doc_type="rechnung"):
    inv = Invoice(
        doc_type=doc_type,
        number=number or f"RE-TEST-{datetime.now(timezone.utc).timestamp()}",
        year=2026, sequence=1,
        contact_id=contact_id,
        date=inv_date or date(2026, 7, 6),
        status=status,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _make_umfeld(db, kontakt, user):
    """Legt je einen Verweis in allen Modulen an (Zeiteintrag, Projekt, …)."""
    db.add(TimeEntry(user_id=user.id, contact_id=kontakt.id,
                     contact_name=kontakt.display_name,
                     started_at=datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
                     ended_at=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)))
    proj = PlanningProject(name="Testprojekt", contact_id=kontakt.id,
                           contact_name=kontakt.display_name,
                           status="abgeschlossen", is_archived=True)
    db.add(proj)
    db.flush()
    db.add(Task(project_id=proj.id, title="Aufgabe 1", contact_id=kontakt.id,
                contact_name=kontakt.display_name))
    db.add(ChecklistItem(parent_type="project", parent_id=proj.id,
                         text="Check 1", assignee_contact_id=kontakt.id,
                         assignee_name=kontakt.display_name))
    db.add(Todo(title="Todo 1", record_id=kontakt.id,
                record_name=kontakt.display_name, record_type_slug="kontakte"))
    db.add(Attachment(entity_type="kontakt", entity_id=kontakt.id, type="link",
                      link_url="https://example.com", display_name="Datei 1",
                      contact_id=kontakt.id, contact_name=kontakt.display_name))
    db.commit()
    return proj


# ── Report ────────────────────────────────────────────────────────────────────

def test_report_zaehlt_alle_verweise(db_session, test_user):
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)
    _make_invoice(db_session, kontakt.id, status="bezahlt")

    report = gdpr.build_report(db_session, kontakt)
    c = report["categories"]
    assert c["time_entries"] == 1
    assert c["invoices_total"] == 1
    assert c["invoices_retention"] == 1
    assert c["planning_projects"] == 1
    assert c["planning_tasks"] == 1
    assert c["checklist_items"] == 1
    assert c["todos"] == 1
    assert c["attachments"] == 1
    assert report["blockers"] == []
    assert report["record"]["display_name"] == "Muster GmbH"
    # Frist: jüngster Beleg 2026 + 7 Jahre → löschbar ab 1.1.2034
    assert report["retention"]["years"] == 7
    assert report["retention"]["deletable_after"] == "2034-01-01"


def test_retention_jahre_aus_einstellung(db_session):
    kontakt = _make_kontakt(db_session)
    _make_invoice(db_session, kontakt.id, status="bezahlt", inv_date=date(2026, 3, 1))
    db_session.add(Setting(key="gdpr_retention_years", value="10"))
    db_session.commit()

    report = gdpr.build_report(db_session, kontakt)
    assert report["retention"]["years"] == 10
    assert report["retention"]["deletable_after"] == "2037-01-01"


# ── Blocker ───────────────────────────────────────────────────────────────────

def test_blocker_firmenkontakt(db_session):
    kontakt = _make_kontakt(db_session)
    db_session.add(Setting(key="company_contact_id", value=str(kontakt.id)))
    db_session.commit()

    with pytest.raises(GdprBlockedError) as exc:
        gdpr.anonymize_contact(db_session, kontakt)
    assert exc.value.blockers[0]["code"] == "company_contact"


def test_blocker_nicht_abgeschlossene_rechnung(db_session):
    """Rechnungen blockieren, solange sie weder bezahlt noch storniert sind."""
    kontakt = _make_kontakt(db_session)
    inv = _make_invoice(db_session, kontakt.id, status="offen")

    with pytest.raises(GdprBlockedError) as exc:
        gdpr.anonymize_contact(db_session, kontakt)
    assert exc.value.blockers[0]["code"] == "open_invoices"

    # Nach Bezahlung ist der Blocker weg
    inv.status = "bezahlt"
    db_session.commit()
    assert gdpr.check_blockers(db_session, kontakt) == []


def test_stornierte_rechnung_blockiert_nicht(db_session):
    kontakt = _make_kontakt(db_session)
    _make_invoice(db_session, kontakt.id, status="storniert")
    assert gdpr.check_blockers(db_session, kontakt) == []


def test_andere_belegarten_blockieren_nicht(db_session):
    """Angebote, ABs und Lieferscheine blockieren unabhängig vom Status nicht."""
    kontakt = _make_kontakt(db_session)
    _make_invoice(db_session, kontakt.id, status="offen",    doc_type="angebot",              number="AN-T-1")
    _make_invoice(db_session, kontakt.id, status="gesendet", doc_type="auftragsbestaetigung", number="AB-T-1")
    _make_invoice(db_session, kontakt.id, status="entwurf",  doc_type="lieferschein",         number="LS-T-1")
    assert gdpr.check_blockers(db_session, kontakt) == []


def test_laufendes_projekt_blockiert_nicht(db_session):
    """Projekt-/Aufgabenstatus ist für die Löschung unerheblich."""
    kontakt = _make_kontakt(db_session)
    db_session.add(PlanningProject(name="Laufend", contact_id=kontakt.id,
                                   contact_name=kontakt.display_name, status="offen"))
    db_session.commit()
    assert gdpr.check_blockers(db_session, kontakt) == []


# ── Anonymisierung ────────────────────────────────────────────────────────────

def test_anonymisierung_ueber_alle_tabellen(db_session, test_user):
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)
    inv = _make_invoice(db_session, kontakt.id, status="bezahlt")
    kontakt_id = kontakt.id

    categories = gdpr.anonymize_contact(db_session, kontakt,
                                        executed_by="admin@deinezeit.local",
                                        files_action="unlinked")
    db_session.commit()

    # Tombstone: Zeile bleibt, Personenbezug weg
    rec = db_session.query(EntityRecord).filter_by(id=kontakt_id).first()
    assert rec is not None
    assert rec.display_name == ANONYM_NAME
    assert rec.data == {}
    assert rec.anonymized_at is not None

    # Denormalisierte Namen überall ersetzt
    assert db_session.query(TimeEntry).filter_by(contact_id=kontakt_id).first().contact_name == ANONYM_NAME
    assert db_session.query(PlanningProject).filter_by(contact_id=kontakt_id).first().contact_name == ANONYM_NAME
    assert db_session.query(Task).filter_by(contact_id=kontakt_id).first().contact_name == ANONYM_NAME
    assert db_session.query(ChecklistItem).filter_by(assignee_contact_id=kontakt_id).first().assignee_name == ANONYM_NAME
    assert db_session.query(Todo).filter_by(record_id=kontakt_id).first().record_name == ANONYM_NAME
    assert db_session.query(Attachment).filter_by(contact_id=kontakt_id).first().contact_name == ANONYM_NAME

    # Beleg: Snapshot wurde nachgezogen (Altbestand ohne Snapshot)
    db_session.refresh(inv)
    assert inv.recipient_snapshot is not None
    assert inv.recipient_snapshot["display_name"] == "Muster GmbH"
    assert categories["invoices_snapshotted"] == 1

    # IDs bleiben bestehen → nichts verwaist
    assert db_session.query(TimeEntry).filter_by(contact_id=kontakt_id).count() == 1


def test_loeschprotokoll_ohne_personenbezug(db_session, test_user):
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)
    kontakt_id = kontakt.id

    gdpr.anonymize_contact(db_session, kontakt,
                           executed_by="admin@deinezeit.local",
                           files_action="none")
    db_session.commit()

    log = db_session.query(GdprDeletionLog).filter_by(record_id=kontakt_id).first()
    assert log is not None
    assert log.executed_by == "admin@deinezeit.local"
    assert log.executed_at is not None
    assert log.categories["time_entries"] == 1
    assert log.files_action == "none"
    # Kein Personenbezug im Protokoll
    import json
    dump = json.dumps(log.categories) + (log.note or "")
    assert "Muster GmbH" not in dump
    assert "max@muster.at" not in dump


def test_doppelte_anonymisierung_abgelehnt(db_session):
    kontakt = _make_kontakt(db_session)
    gdpr.anonymize_contact(db_session, kontakt)
    db_session.commit()

    with pytest.raises(ValueError):
        gdpr.anonymize_contact(db_session, kontakt)


# ── API-Endpunkte ─────────────────────────────────────────────────────────────

from tests.conftest import TEST_USER_PASSWORD  # noqa: E402

ADMIN_EMAIL = "admin@deinezeit.local"


def _admin_client(client, admin_user):
    """Loggt den Admin ein und setzt den Bearer-Token am Client."""
    resp = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def test_gdpr_endpunkte_erfordern_admin(auth_client, db_session):
    """Normale Benutzer (employee) haben keinen Zugriff auf /gdpr."""
    kontakt = _make_kontakt(db_session)
    assert auth_client.get(f"/api/gdpr/records/{kontakt.id}/report").status_code == 403
    assert auth_client.post(f"/api/gdpr/records/{kontakt.id}/erase",
                            json={"files_action": "none"}).status_code == 403
    assert auth_client.get("/api/gdpr/log").status_code == 403


def test_report_endpoint(client, admin_user, db_session, test_user):
    admin = _admin_client(client, admin_user)
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)

    resp = admin.get(f"/api/gdpr/records/{kontakt.id}/report")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["record"]["display_name"] == "Muster GmbH"
    assert body["categories"]["time_entries"] == 1
    assert body["blockers"] == []

    # Unbekannter Datensatz → 404
    import uuid as _uuid
    assert admin.get(f"/api/gdpr/records/{_uuid.uuid4()}/report").status_code == 404


def test_erase_endpoint_blockiert_bei_offener_rechnung(client, admin_user, db_session):
    admin = _admin_client(client, admin_user)
    kontakt = _make_kontakt(db_session)
    _make_invoice(db_session, kontakt.id, status="offen")

    resp = admin.post(f"/api/gdpr/records/{kontakt.id}/erase",
                      json={"files_action": "none"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["blockers"][0]["code"] == "open_invoices"


def test_erase_endpoint_komplett(client, admin_user, db_session, test_user):
    """Voller Löschvorgang über die API: Anonymisierung, PDF, Protokoll."""
    admin = _admin_client(client, admin_user)
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)
    _make_invoice(db_session, kontakt.id, status="bezahlt")
    kontakt_id = kontakt.id

    resp = admin.post(f"/api/gdpr/records/{kontakt_id}/erase",
                      json={"files_action": "none",
                            "note": "Löschung auf Anfrage vom 01.07.2026"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["categories"]["time_entries"] == 1

    # Bescheinigung ist ein echtes PDF (Base64, beginnt mit %PDF)
    import base64
    pdf = base64.b64decode(body["certificate_pdf_b64"])
    assert pdf[:4] == b"%PDF"
    assert body["certificate_filename"].endswith(".pdf")

    # Kontakt ist anonymisiert
    rec = db_session.query(EntityRecord).filter_by(id=kontakt_id).first()
    assert rec.display_name == ANONYM_NAME
    assert rec.anonymized_at is not None

    # Löschprotokoll über die API abrufbar, ohne Personenbezug
    log_resp = admin.get("/api/gdpr/log")
    assert log_resp.status_code == 200
    logs = log_resp.json()
    assert len(logs) == 1
    assert logs[0]["id"] == body["log_id"]
    assert "Muster GmbH" not in str(logs[0])

    # Doppelte Löschung → 400
    resp2 = admin.post(f"/api/gdpr/records/{kontakt_id}/erase",
                       json={"files_action": "none"})
    assert resp2.status_code == 400


def test_erase_endpoint_loescht_dateien(client, admin_user, db_session, test_user):
    """files_action='deleted' entfernt die Datacenter-Einträge des Kontakts."""
    admin = _admin_client(client, admin_user)
    kontakt = _make_kontakt(db_session)
    _make_umfeld(db_session, kontakt, test_user)   # enthält 1 Attachment (Link)
    kontakt_id = kontakt.id

    resp = admin.post(f"/api/gdpr/records/{kontakt_id}/erase",
                      json={"files_action": "deleted"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["files_deleted"] == 1
    assert db_session.query(Attachment).filter_by(contact_id=kontakt_id).count() == 0
