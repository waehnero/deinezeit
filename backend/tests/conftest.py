"""
Gemeinsame Test-Fixtures für DeineZeit (pytest).

Grundidee:
- Die Tests laufen gegen eine ECHTE PostgreSQL-Test-Datenbank (nicht SQLite),
  weil die Modelle Postgres-spezifische Typen nutzen (UUID, JSONB).
- Vor jedem Test werden die Tabellen frisch angelegt und danach wieder
  verworfen → jeder Test startet auf einer sauberen DB (keine Seiteneffekte).
- Die FastAPI-Dependency `get_db` wird auf die Test-Session umgebogen, sodass
  die App im Test gegen die Test-DB arbeitet.

Die Verbindungs-URL kommt aus der Umgebungsvariablen TEST_DATABASE_URL.
Das Skript ./test.sh (im Projekt-Wurzelverzeichnis) setzt sie automatisch.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Alle Modelle importieren, damit Base.metadata sämtliche Tabellen kennt.
from app.models import *  # noqa: F401,F403
from app.db.base import Base, get_db
from app.api.deps import get_current_user
from app.main import app
from app.services.auth_service import auth_service


# ── Test-Datenbank ────────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    # Fallback für lokalen Lauf ohne ./test.sh; bei Bedarf anpassen.
    "postgresql://deinezeit:deinezeit@db:5432/deinezeit_test",
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    """Frische DB pro Test: Tabellen anlegen, Session liefern, danach aufräumen."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    """
    TestClient, dessen get_db-Dependency auf die Test-Session zeigt.
    So arbeitet die komplette App im Test gegen die Test-DB.
    """
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session wird in db_session-Fixture geschlossen

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Benutzer-/Auth-Hilfen ─────────────────────────────────────────────────────
TEST_USER_EMAIL = "test@deinezeit.local"
TEST_USER_PASSWORD = "Test-Passwort123!"


@pytest.fixture()
def test_user(db_session):
    """Legt einen aktiven Standard-Benutzer (employee) in der Test-DB an."""
    return auth_service.create_user(
        db_session,
        email=TEST_USER_EMAIL,
        full_name="Test Benutzer",
        password=TEST_USER_PASSWORD,
        role="employee",
    )


@pytest.fixture()
def admin_user(db_session):
    """Legt einen aktiven Admin-Benutzer in der Test-DB an."""
    return auth_service.create_user(
        db_session,
        email="admin@deinezeit.local",
        full_name="Test Admin",
        password=TEST_USER_PASSWORD,
        role="admin",
    )


@pytest.fixture()
def auth_client(client, test_user):
    """
    Wie `client`, aber mit eingeloggtem Standard-Benutzer:
    der Authorization-Header (Bearer-Token) ist gesetzt.
    """
    resp = client.post(
        "/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, f"Login im Fixture fehlgeschlagen: {resp.text}"
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
