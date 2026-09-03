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


# ── Sichtbarkeit der Konfiguration (Audit SEC-004) ───────────────────────────

def test_konfiguration_ist_ohne_anmeldung_nicht_sichtbar(client, admin_user):
    """Ohne Anmeldung liefert GET /api/settings nur Darstellungsfelder —
    SMTP-Server, Microsoft-Tenant, Backup-Pfad usw. bleiben leer."""
    c = _admin_client(client, admin_user)
    resp = c.put("/api/settings", json={
        "company_name": "Muster GmbH", "smtp_host": "smtp.muster.at",
        "smtp_user": "postausgang@muster.at", "ms_tenant_id": "tenant-123",
        "backup_dir": "C:/Backups", "webdav_url": "https://cloud.muster.at/dav",
    })
    assert resp.status_code == 200

    # Admin sieht alles (außer den Passwörtern)
    voll = c.get("/api/settings").json()
    assert voll["company_name"] == "Muster GmbH"
    assert voll["smtp_host"] == "smtp.muster.at"
    assert voll["ms_tenant_id"] == "tenant-123"
    assert "smtp_password" not in voll

    # Ohne Token: nur Darstellung
    c.headers.pop("Authorization", None)
    anonym = c.get("/api/settings")
    assert anonym.status_code == 200
    data = anonym.json()
    assert data["company_name"] == "Muster GmbH"
    for feld in ("smtp_host", "smtp_user", "ms_tenant_id", "backup_dir", "webdav_url"):
        assert data[feld] == "", feld

    # Ungültiger Token darf den Endpunkt nicht kaputt machen (Anmeldeseite!)
    c.headers.update({"Authorization": "Bearer kaputt"})
    assert c.get("/api/settings").status_code == 200
    assert c.get("/api/settings").json()["smtp_host"] == ""


def test_mitarbeiter_sieht_konfiguration_nicht(auth_client, client, admin_user):
    """Ein angemeldeter Nicht-Administrator bekommt dieselbe Sicht wie anonym."""
    admin_token = client.post("/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]
    resp = client.put("/api/settings", json={"smtp_host": "smtp.muster.at"},
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200

    # auth_client ist der Standard-Benutzer (employee)
    data = auth_client.get("/api/settings").json()
    assert data["smtp_host"] == ""


# ── Geheimnisse verschlüsselt in der Datenbank (Audit SEC-005) ───────────────

def test_geheimnisse_liegen_verschluesselt_in_der_datenbank(client, admin_user, db_session):
    from sqlalchemy import text
    from app.core.crypto import ist_verschluesselt
    from app.models.settings import Setting

    c = _admin_client(client, admin_user)
    resp = c.put("/api/settings", json={"smtp_password": "ganz-geheim-123",
                                        "smtp_host": "smtp.muster.at",
                                        "ms_client_secret": "client~secret"})
    assert resp.status_code == 200

    # Roh in der Tabelle: Fernet-Token, kein Klartext
    roh = {k: v for k, v in db_session.execute(
        text("SELECT key, value FROM settings WHERE key IN "
             "('smtp_password', 'ms_client_secret', 'smtp_host')")).fetchall()}
    assert roh["smtp_password"] != "ganz-geheim-123"
    assert ist_verschluesselt(roh["smtp_password"])
    assert ist_verschluesselt(roh["ms_client_secret"])
    assert roh["smtp_host"] == "smtp.muster.at"          # kein Geheimnis: Klartext

    # Über das Modell (so lesen Mailversand, Backup, Speicher): Klartext
    db_session.expire_all()
    rows = {r.key: r.value for r in db_session.query(Setting).filter(
        Setting.key.in_(["smtp_password", "ms_client_secret"])).all()}
    assert rows["smtp_password"] == "ganz-geheim-123"
    assert rows["ms_client_secret"] == "client~secret"

    # Nie nach außen — auch nicht an den Administrator
    assert "smtp_password" not in c.get("/api/settings").json()


def test_bestandswert_im_klartext_bleibt_lesbar_und_wird_beim_speichern_verschluesselt(db_session):
    """Zeilen aus der Zeit vor Migration 0060 stehen im Klartext."""
    from sqlalchemy import text
    from app.core.crypto import ist_verschluesselt
    from app.models.settings import Setting

    db_session.execute(text(
        "INSERT INTO settings (key, value) VALUES ('webdav_password', 'alt-klartext')"))
    db_session.commit()

    row = db_session.query(Setting).filter(Setting.key == "webdav_password").first()
    assert row.value == "alt-klartext"

    row.value = "neu-geheim"
    db_session.commit()
    roh = db_session.execute(text(
        "SELECT value FROM settings WHERE key = 'webdav_password'")).scalar()
    assert ist_verschluesselt(roh)
    db_session.expire_all()
    assert db_session.query(Setting).get("webdav_password").value == "neu-geheim"


def test_migration_0060_verschluesselt_bestand(db_session, monkeypatch):
    """Der Nachhol-Schritt der Migration verschlüsselt Klartext und lässt
    bereits verschlüsselte Werte in Ruhe."""
    import importlib.util, pathlib
    from sqlalchemy import text
    from app.core.crypto import ist_verschluesselt, verschluesseln, entschluesseln

    db_session.execute(text(
        "INSERT INTO settings (key, value) VALUES "
        "('smtp_password', 'klar'), ('ms_client_secret', :enc), ('smtp_host', 'h')"),
        {"enc": verschluesseln("schon-verschluesselt")})
    db_session.commit()

    pfad = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / \
        "0060_settings_geheimnisse_verschluesseln.py"
    spec = importlib.util.spec_from_file_location("mig0060", pfad)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    class _Op:                       # Ersatz für alembic.op innerhalb des Tests
        @staticmethod
        def get_bind():
            return db_session.connection()
    monkeypatch.setattr(mig, "op", _Op)
    mig.upgrade()
    db_session.commit()

    roh = {k: v for k, v in db_session.execute(
        text("SELECT key, value FROM settings")).fetchall()}
    assert ist_verschluesselt(roh["smtp_password"])
    assert entschluesseln(roh["smtp_password"]) == "klar"
    assert entschluesseln(roh["ms_client_secret"]) == "schon-verschluesselt"
    assert roh["smtp_host"] == "h"
