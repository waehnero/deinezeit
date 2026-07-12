"""
Tests für die allgemeinen Einstellungen (/api/settings) — Schwerpunkt:
Design-/Whitelabel-Felder des Layout-Redesigns (design_template, brand_color,
custom_*_color). Die Settings liegen als Key-Value-Store; die Pydantic-Schemas
(SettingsResponse/SettingsUpdate) bilden die Whitelist der erlaubten Felder.
"""
from tests.conftest import TEST_USER_PASSWORD

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


def test_get_settings_enthaelt_design_felder(client):
    """GET /api/settings liefert die Design-Felder (leer = Vorlagen-Standard)."""
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    for feld in (
        "design_template",
        "brand_color",
        "custom_text_color",
        "custom_bg_color",
        "custom_surface_color",
    ):
        assert feld in data, f"Feld {feld} fehlt in der Settings-Antwort"


def test_admin_kann_design_speichern(client, admin_user):
    """Der Admin kann Designvorlage und Whitelabel-Farben speichern."""
    c = _admin_client(client, admin_user)
    resp = c.put(
        "/api/settings",
        json={
            "design_template": "midnight",
            "brand_color": "#22d3ee",
            "custom_text_color": "#e2e8f0",
            "custom_bg_color": "#0b1220",
            "custom_surface_color": "#121b2e",
        },
    )
    assert resp.status_code == 200, resp.text

    data = c.get("/api/settings").json()
    assert data["design_template"] == "midnight"
    assert data["brand_color"] == "#22d3ee"
    assert data["custom_text_color"] == "#e2e8f0"
    assert data["custom_bg_color"] == "#0b1220"
    assert data["custom_surface_color"] == "#121b2e"


def test_design_zuruecksetzen_auf_vorlage(client, admin_user):
    """Leere Werte setzen die Farb-Overrides zurück (Vorlage gilt wieder)."""
    c = _admin_client(client, admin_user)
    c.put("/api/settings", json={"brand_color": "#ff0000"})
    resp = c.put("/api/settings", json={"brand_color": ""})
    assert resp.status_code == 200
    assert c.get("/api/settings").json()["brand_color"] == ""


def test_normaler_benutzer_darf_nicht_speichern(auth_client):
    """PUT /api/settings ist Admins vorbehalten (403 für normale Benutzer)."""
    resp = auth_client.put(
        "/api/settings", json={"design_template": "aurora"}
    )
    assert resp.status_code == 403
