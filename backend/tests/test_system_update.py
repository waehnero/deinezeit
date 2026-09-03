"""
Update-Zustand und aktive Benutzer liegen nicht mehr im Arbeitsspeicher eines
Prozesses, sondern in der Datenbank (Audit 02.09.2026, OPS-003).
"""
from datetime import datetime, timedelta, timezone

from app.api import system as system_api
from app.models.user import UserSession
from tests.conftest import TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"


def _als_admin(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def test_update_zustand_liegt_in_der_datenbank(client, admin_user, db_session):
    """Was ein Prozess schreibt, liest jeder andere über die Datenbank."""
    assert client.get("/api/system/update-status").json()["status"] == "idle"

    geplant = datetime.now(timezone.utc) + timedelta(minutes=2)
    system_api._update_state_schreiben(db_session, status="notifying",
                                       scheduled_at=geplant.isoformat(),
                                       initiated_by="Test Admin", message="Gleich!")
    daten = client.get("/api/system/update-status").json()
    assert daten["status"] == "notifying"
    assert daten["pending"] is True
    assert 100 < daten["countdown_seconds"] <= 120
    assert daten["initiated_by"] == "Test Admin"

    # Abbrechen über den Endpunkt wirkt auf die Datenbank
    c = _als_admin(client, admin_user)
    assert c.post("/api/system/update/cancel").status_code == 200
    assert system_api._update_state_lesen(db_session)["status"] == "idle"
    assert c.post("/api/system/update/cancel").status_code == 409


def test_update_start_verweigert_doppelt_und_lokal(client, admin_user, db_session, monkeypatch):
    c = _als_admin(client, admin_user)
    # Die lokale Docker-Umgebung setzt DEPLOY_MODE=local (docker-compose.local.yml);
    # dort antwortet der Endpunkt schon vor der Doppelt-Prüfung mit 400. Der
    # Test darf nicht davon abhängen, wo er läuft.
    monkeypatch.delenv("DEPLOY_MODE", raising=False)
    system_api._update_state_schreiben(db_session, status="notifying")
    assert c.post("/api/system/update/start").status_code == 409

    system_api._update_state_schreiben(db_session, status="idle")
    monkeypatch.setenv("DEPLOY_MODE", "local")
    assert c.post("/api/system/update/start").status_code == 400


def test_neustart_setzt_liegengebliebenen_zustand_zurueck(db_session, monkeypatch):
    system_api._update_state_schreiben(db_session, status="updating", message="…")
    monkeypatch.setattr(system_api, "SessionLocal", lambda: db_session)
    # _mit_db schließt die Sitzung — für den Test unschädlich machen
    monkeypatch.setattr(db_session, "close", lambda: None)
    system_api.update_zustand_nach_neustart_zuruecksetzen()
    assert system_api._update_state_lesen(db_session)["status"] == "idle"


def test_aktive_benutzer_aus_sitzungen(auth_client, test_user, db_session):
    """Zählt Sitzungen der letzten 5 Minuten — nicht ein Dict im Prozess."""
    assert system_api.get_active_user_count(db_session) == 1     # die Anmeldung eben

    # Sitzung „altern" lassen → zählt nicht mehr
    s = db_session.query(UserSession).filter(UserSession.user_id == test_user.id).first()
    s.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()
    assert system_api.get_active_user_count(db_session) == 0

    # Ein Zugriff schreibt last_used_at fort (auth_service.zugriff_vermerken)
    assert auth_client.get("/api/auth/me").status_code == 200
    db_session.expire_all()
    assert system_api.get_active_user_count(db_session) == 1
    daten = auth_client.get("/api/system/active-users").json()
    assert daten["total_including_me"] == 1 and daten["active_users"] == 0
