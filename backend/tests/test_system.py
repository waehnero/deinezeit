"""
System-Endpunkte nach dem Wegfall des In-App-Updates (Audit SEC-002, K-21,
04.09.2026) und die Worker-Sperre (OPS-003).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.api import system as system_api
from app.core import worker_sperre
from app.models.user import UserSession
from tests.conftest import TEST_USER_PASSWORD

# backend/ ist immer da (auch im Docker-Testlauf, dort als /app). Das
# Repo-Root mit docker-compose.yml gibt es nur beim Lauf auf dem Host bzw.
# in der CI — im Container wird die Compose-Prüfung übersprungen.
BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
ADMIN_EMAIL = "admin@deinezeit.local"


def _als_admin(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


# ── Das In-App-Update ist weg ────────────────────────────────────────────────

def test_update_endpunkte_existieren_nicht_mehr(client, admin_user):
    c = _als_admin(client, admin_user)
    assert c.get("/api/system/update-status").status_code == 404
    assert c.post("/api/system/update/start").status_code == 404
    assert c.post("/api/system/update/cancel").status_code == 404


def test_backend_kennt_weder_docker_noch_git():
    """Der Riegel gegen Rückfall: Wer das Update wieder einbaut, muss diesen
    Test bewusst ändern — und damit die Begründung in SEC-002 lesen."""
    import inspect
    quelle = inspect.getsource(system_api)
    assert "subprocess" not in quelle
    assert "docker" not in quelle.lower().replace("docker-socket", "").replace(
        "docker-compose", "")

    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    aktiv = "\n".join(z for z in dockerfile.splitlines() if not z.strip().startswith("#"))
    assert "docker-ce-cli" not in aktiv
    assert "download.docker.com" not in aktiv
    assert " git " not in aktiv and "git \\" not in aktiv

    compose_datei = REPO / "docker-compose.yml"
    if not compose_datei.exists():
        pytest.skip("Repo-Root nicht verfügbar (Docker-Testlauf) — Compose-Prüfung läuft in der CI")
    compose = compose_datei.read_text(encoding="utf-8")
    aktiv = "\n".join(z for z in compose.splitlines() if not z.strip().startswith("#"))
    assert "docker.sock" not in aktiv
    assert "/opt/deinezeit:/opt/deinezeit" not in aktiv
    assert "minio/minio:latest" not in aktiv                 # OPS-005
    assert not (REPO / "update.sh").exists()


def test_migration_0062_raeumt_update_zeilen_ab(db_session):
    """Die Migration ist reines SQL; hier wird ihr DELETE nachgestellt."""
    import importlib.util
    pfad = BACKEND / "alembic" / "versions" / "0062_update_zustand_entfernen.py"
    spec = importlib.util.spec_from_file_location("mig0062", pfad)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == "0062" and mig.down_revision == "0061"

    for k in mig._SCHLUESSEL:
        db_session.execute(text(
            "INSERT INTO settings (key, value, updated_at) VALUES (:k, 'x', now())"),
            {"k": k})
    db_session.commit()
    anzahl = db_session.execute(text(
        "SELECT count(*) FROM settings WHERE key LIKE 'update\\_%'")).scalar()
    assert anzahl == 4

    # Genau das SQL der Migration ausführen
    ausgefuehrt = []
    mig.op = type("Op", (), {"execute": staticmethod(lambda sql: ausgefuehrt.append(sql))})
    mig.upgrade()
    assert len(ausgefuehrt) == 1
    db_session.execute(text(ausgefuehrt[0]))
    db_session.commit()
    assert db_session.execute(text(
        "SELECT count(*) FROM settings WHERE key LIKE 'update\\_%'")).scalar() == 0


# ── Aktive Benutzer (unverändert aus der Datenbank) ──────────────────────────

def test_aktive_benutzer_aus_sitzungen(auth_client, test_user, db_session):
    """Zählt Sitzungen der letzten 5 Minuten — nicht ein Dict im Prozess."""
    assert system_api.get_active_user_count(db_session) == 1     # die Anmeldung eben

    s = db_session.query(UserSession).filter(UserSession.user_id == test_user.id).first()
    s.last_used_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()
    assert system_api.get_active_user_count(db_session) == 0

    assert auth_client.get("/api/auth/me").status_code == 200
    db_session.expire_all()
    assert system_api.get_active_user_count(db_session) == 1
    daten = auth_client.get("/api/system/active-users").json()
    assert daten["total_including_me"] == 1 and daten["active_users"] == 0


# ── Worker-Sperre ────────────────────────────────────────────────────────────

def test_worker_sperre_ist_ein_advisory_lock(db_session):
    """Dieselbe Sitzung bekommt den Lock, freigeben geht, und ohne ihn ist
    ``pg_advisory_unlock`` falsch. (Zwei getrennte Sitzungen lassen sich mit
    der Test-Datenbank nicht abbilden — sie erlaubt nur eine Verbindung.)"""
    conn = db_session.connection()
    assert worker_sperre.sperre_versuchen(conn) is True
    assert worker_sperre.sperre_freigeben(conn) is True
    assert worker_sperre.sperre_freigeben(conn) is False
    db_session.rollback()


def test_worker_sperre_startet_in_tests_nichts(monkeypatch):
    """TEST_DATABASE_URL ist gesetzt → kein Thread, kein starter()-Aufruf."""
    aufgerufen = []
    monkeypatch.setattr(worker_sperre, "_gestartet", False)
    worker_sperre.worker_exklusiv_starten(lambda: aufgerufen.append(1))
    assert aufgerufen == []
    assert worker_sperre.ist_anfuehrer() is False


def test_worker_starten_nur_ueber_die_sperre():
    """main.py darf die Worker nur über worker_exklusiv_starten anstoßen."""
    import inspect
    from app import main
    quelle = inspect.getsource(main.startup_event)
    assert "worker_exklusiv_starten(hintergrund_worker_starten)" in quelle
    for name in ("start_background_scanner", "start_recurring_worker",
                 "start_overdue_worker", "start_postecke_worker",
                 "start_backup_worker", "start_ssl_worker"):
        assert name not in quelle, f"{name} wird am Riegel vorbei gestartet"
        assert name in inspect.getsource(main.hintergrund_worker_starten)
