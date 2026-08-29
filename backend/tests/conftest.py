"""
Gemeinsame Test-Fixtures für DeineZeit (pytest).

Grundidee:
- Die Tests laufen gegen eine ECHTE PostgreSQL-Test-Datenbank (nicht SQLite),
  weil die Modelle Postgres-spezifische Typen nutzen (UUID, JSONB).
- Das Schema wird EINMAL pro Testlauf angelegt; vor jedem einzelnen Test werden
  nur die Daten geleert → jeder Test startet auf einer sauberen DB (keine
  Seiteneffekte), ohne dass 45 Tabellen 786-mal neu gebaut werden.
- Die FastAPI-Dependency `get_db` wird auf die Test-Session umgebogen, sodass
  die App im Test gegen die Test-DB arbeitet.

Die Verbindungs-URL kommt aus der Umgebungsvariablen TEST_DATABASE_URL.
Das Skript ./test.sh (im Projekt-Wurzelverzeichnis) setzt sie automatisch.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Umgebung für den Testlauf festnageln ──────────────────────────────────────
# MUSS vor dem ersten Import aus ``app`` stehen: Die Einstellungen werden beim
# Import gelesen, spätere Änderungen kämen zu spät.
#
# Warum: Der Refresh-Token liegt in einem Cookie, dessen ``secure``-Kennzeichen
# aus ``FRONTEND_URL`` abgeleitet wird (``_cookie_sicher()`` in api/auth.py).
# Läuft die Testreihe auf dem Server, steht dort ``https://…`` in der ``.env``,
# das Cookie wird ``secure`` gesetzt — und der Testclient spricht ``http``,
# schickt es also nie zurück. ``/api/auth/refresh`` antwortet dann völlig
# korrekt mit 401, und vier Tests scheitern an der Maschine statt am Code.
#
# Eine Testreihe, die je nach Rechner anders ausgeht, ist wertlos: Man gewöhnt
# sich an die roten Zeilen und übersieht die erste echte.
os.environ["FRONTEND_URL"] = "http://testserver"

# Alle Modelle importieren, damit Base.metadata sämtliche Tabellen kennt.
from app.models import *  # noqa: F401,F403
from app.db.base import Base, get_db
from app.api.deps import get_current_user
from app.main import app
from app.services.auth_service import auth_service


# ── Passwort-Hashing für Tests entschärfen ────────────────────────────────────
# bcrypt ist mit Absicht langsam — im Betrieb ist genau das seine Aufgabe. In
# den Tests ist es der grösste einzelne Zeitfresser: Jedes Anlegen eines
# Benutzers und jede Anmeldung kostet mit den Standard-12-Runden rund eine
# Drittelsekunde, und die Fixtures tun beides hunderte Male.
#
# Vier Runden statt zwölf bedeutet 2^8 = 256-mal schneller. Gehasht und geprüft
# wird weiterhin echt mit bcrypt, nur eben mit weniger Wiederholungen — die
# Tests prüfen also unverändert denselben Code. Der Produktivbetrieb ist davon
# nicht berührt: diese Datei wird ausschliesslich von pytest geladen.
from app.core.security import pwd_context                       # noqa: E402
pwd_context.update(bcrypt__rounds=4)


# ── Test-Datenbank ────────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    # Fallback für lokalen Lauf ohne ./test.sh; bei Bedarf anpassen.
    "postgresql://deinezeit:deinezeit@db:5432/deinezeit_test",
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def _schema():
    """Legt das Schema EINMAL für den gesamten Testlauf an.

    Vorher geschah das pro Test: 45 Tabellen anlegen und wieder verwerfen, mal
    786 Tests — rund 70.000 DDL-Anweisungen für ein Schema, das sich während
    des Laufs kein einziges Mal ändert.

    Das `drop_all` zu Beginn räumt Reste eines abgebrochenen früheren Laufs
    weg; ohne das würde ein veraltetes Schema stehenbleiben und die Tests mit
    schwer deutbaren Fehlern scheitern lassen.
    """
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:                                            # noqa: BLE001
        pass            # z.B. Tabellen aus einer alten Schema-Version
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


_TABELLENLISTE = None


def _tabellenliste() -> str:
    """Alle Tabellennamen als eine Aufzählung für ein einziges TRUNCATE."""
    global _TABELLENLISTE
    if _TABELLENLISTE is None:
        _TABELLENLISTE = ", ".join(f'"{t.name}"'
                                   for t in Base.metadata.sorted_tables)
    return _TABELLENLISTE


@pytest.fixture()
def db_session(_schema):
    """Saubere DB pro Test: Daten leeren, Session liefern, danach schliessen.

    `TRUNCATE ... RESTART IDENTITY CASCADE` über alle Tabellen in einer
    einzigen Anweisung ist gleichwertig zum früheren Neuaufbau des Schemas —
    die Tabellen sind leer und die Zähler stehen wieder am Anfang — kostet
    aber Millisekunden statt Sekunden.

    Geleert wird VOR dem Test, nicht danach: So startet auch der Test sauber,
    der auf einen abgestürzten Vorgänger folgt.
    """
    with engine.begin() as conn:
        # Ohne Zeitlimit würde ein vergessener offener Zugriff aus einem
        # früheren Test hier ewig warten und der Testlauf bliebe stumm hängen.
        # Mit Limit gibt es stattdessen eine klare Fehlermeldung.
        conn.execute(text("SET lock_timeout = '15s'"))
        conn.execute(text(f"TRUNCATE {_tabellenliste()} RESTART IDENTITY CASCADE"))

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


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
    # Rate-Limiting in Tests deaktivieren: alle Requests kommen vom selben
    # TestClient ("testclient"), dadurch würde z.B. das Login-Limit (10/min)
    # bei Modulen mit vielen auth_client-Tests fälschlich zuschlagen.
    # Achtung: auth.py nutzt eine EIGENE Limiter-Instanz -> beide abschalten.
    from app.api.auth import limiter as auth_limiter
    app.state.limiter.enabled = False
    auth_limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    app.state.limiter.enabled = True
    auth_limiter.enabled = True
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
