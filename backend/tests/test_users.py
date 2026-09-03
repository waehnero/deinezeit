"""
Benutzerverwaltung (/api/users) — Schwerpunkt: Löschen darf keine Fachdaten
vernichten (Audit 02.09.2026, DATA-003).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.user import User
from app.models.zeiterfassung import TimeEntry
from tests.conftest import TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"


def _als_admin(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _zeiteintrag_anlegen(client):
    start = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)
    resp = client.post("/api/zeiterfassung/entries", json={
        "project_name": "Audit", "started_at": start.isoformat(),
        "ended_at": (start + timedelta(hours=1)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_benutzer_mit_zeiteintraegen_wird_nicht_geloescht(auth_client, admin_user,
                                                        test_user, db_session):
    """Statt der bisherigen Kaskade (alle Zeiten weg) kommt 409 mit Aufstellung."""
    eintrag_id = _zeiteintrag_anlegen(auth_client)          # als Standard-Benutzer
    c = _als_admin(auth_client, admin_user)

    resp = c.delete(f"/api/users/{test_user.id}")
    assert resp.status_code == 409, resp.text
    assert "1 Zeiteinträge" in resp.json()["detail"]
    assert "deaktivieren" in resp.json()["detail"].lower()

    # Nichts ist passiert: Konto und Zeiteintrag sind noch da
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == test_user.id).first() is not None
    assert db_session.query(TimeEntry).filter(TimeEntry.id == eintrag_id).first() is not None


def test_benutzer_mit_stammdaten_wird_nicht_geloescht_statt_500(auth_client, admin_user,
                                                                test_user, db_session):
    """Angelegte Stammdaten führten früher zu einem Fremdschlüsselfehler (500)."""
    from app.models.masterdata import EntityType, EntityRecord
    et = EntityType(name="Kontakte", slug="kontakte")
    db_session.add(et); db_session.commit()
    db_session.add(EntityRecord(entity_type_id=et.id, data={"firmenname": "Audit GmbH"},
                                created_by=test_user.id))
    db_session.commit()

    c = _als_admin(auth_client, admin_user)
    resp = c.delete(f"/api/users/{test_user.id}")
    assert resp.status_code == 409, resp.text
    assert "Stammdaten" in resp.json()["detail"]


def test_benutzer_ohne_spuren_wird_geloescht(client, admin_user, db_session):
    """Eine Fehlanlage ohne jede Fachdaten darf weiterhin verschwinden —
    samt Sitzungen und Passkeys (Kaskade am Konto)."""
    from app.services.auth_service import auth_service
    neu = auth_service.create_user(db_session, email="fehlanlage@deinezeit.local",
                                   full_name="Fehl Anlage", password=TEST_USER_PASSWORD,
                                   role="employee")
    # eine Sitzung anlegen, damit es etwas zu kaskadieren gibt
    resp = client.post("/api/auth/login", json={"email": neu.email,
                                                "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200
    neu_token = resp.json()["access_token"]

    c = _als_admin(client, admin_user)
    resp = c.delete(f"/api/users/{neu.id}")
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.query(User).filter(User.id == neu.id).first() is None
    assert db_session.execute(text(
        "SELECT count(*) FROM user_sessions WHERE user_id = :u"), {"u": str(neu.id)}).scalar() == 0
    # Der alte Token ist wertlos
    c.headers.update({"Authorization": f"Bearer {neu_token}"})
    assert c.get("/api/auth/me").status_code == 401


def test_eigenes_konto_und_fremde_rolle(client, admin_user, db_session):
    """Das eigene Konto ist tabu (400); ein Mitarbeiter darf gar nicht löschen
    (403). Ein „letzter Administrator" kann hier nicht entstehen: Wer löscht,
    ist selbst ein aktiver Administrator und kann sich nicht selbst löschen."""
    from app.services.auth_service import auth_service
    zweiter = auth_service.create_user(db_session, email="admin2@deinezeit.local",
                                       full_name="Zweiter Admin", password=TEST_USER_PASSWORD,
                                       role="admin")
    resp = client.post("/api/auth/login", json={"email": zweiter.email,
                                                "password": TEST_USER_PASSWORD})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert client.delete(f"/api/users/{zweiter.id}").status_code == 400      # eigenes Konto
    assert client.delete(f"/api/users/{admin_user.id}").status_code == 200   # einer bleibt

    dritter = auth_service.create_user(db_session, email="admin3@deinezeit.local",
                                       full_name="Dritter", password=TEST_USER_PASSWORD,
                                       role="employee")
    # Mitarbeiter darf gar nicht löschen
    resp = client.post("/api/auth/login", json={"email": dritter.email,
                                                "password": TEST_USER_PASSWORD})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert client.delete(f"/api/users/{zweiter.id}").status_code == 403


def test_datenbank_verhindert_kaskade_auf_zeiteintraege(auth_client, test_user, db_session):
    """Zweiter Riegel unabhängig vom Endpunkt: Der Fremdschlüssel hat keine
    Löschkaskade mehr (Migration 0061) — ein direktes DELETE scheitert."""
    import pytest
    from sqlalchemy.exc import IntegrityError
    _zeiteintrag_anlegen(auth_client)
    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(test_user.id)})
        db_session.commit()
    db_session.rollback()
