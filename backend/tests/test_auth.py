"""
Auth-Tests – dienen zugleich als VORLAGE für weitere Modul-Tests.

Muster, das hier gezeigt wird und kopiert werden soll:
- `client`     → App mit Test-DB, ohne Login (für öffentliche/abgelehnte Zugriffe)
- `test_user`  → ein angelegter Benutzer in der Test-DB
- `auth_client`→ App mit bereits eingeloggtem Benutzer (Bearer-Token gesetzt)

Für ein neues Modul `xy` entsprechend `tests/test_xy.py` anlegen und dieselben
Fixtures verwenden.
"""
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


# ── Login ─────────────────────────────────────────────────────────────────────
def test_login_erfolgreich(client, test_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]          # nicht leer
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["requires_totp"] is False


def test_login_falsches_passwort(client, test_user):
    resp = client.post(
        "/api/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "falsch"},
    )
    assert resp.status_code == 401


def test_login_unbekannter_benutzer(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "gibtsnicht@deinezeit.local", "password": "egal"},
    )
    assert resp.status_code == 401


# ── /me (geschützter Endpoint) ────────────────────────────────────────────────
def test_me_ohne_token_abgelehnt(client):
    resp = client.get("/api/auth/me")
    # Ohne Authorization-Header darf kein Zugriff möglich sein.
    assert resp.status_code in (401, 403)


def test_me_mit_token(auth_client):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == TEST_USER_EMAIL
    assert data["full_name"] == "Test Benutzer"
    assert data["role"] == "employee"
    assert data["is_active"] is True
