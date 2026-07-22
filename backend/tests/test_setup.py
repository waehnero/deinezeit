"""
Tests für den Erstinstallations-Assistenten (api/setup.py).

Prüft:
- Statusabfrage erkennt leere Installation.
- /setup/init legt den ersten Admin an und liefert gültige Tokens.
- Sicherheits-Riegel: sobald ein Benutzer existiert, ist /setup/init gesperrt.
- Passwort-Mindestlänge wird erzwungen.
- Optional übergebene Firma wird als Kontakt angelegt und als Briefkopf
  (company_contact_id) verknüpft.
"""
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

from app.models.masterdata import EntityType, FieldDefinition
from app.models.settings import Setting


ADMIN = {
    "admin_email": "chef@firma.at",
    "admin_full_name": "Chef Chefin",
    "admin_password": "Sicher-Passwort123",
}


# ── Status ────────────────────────────────────────────────────────────────────
def test_status_bei_leerer_installation(client):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_setup"] is True
    assert data["user_count"] == 0


def test_status_nach_vorhandenem_benutzer(client, test_user):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is False


# ── Erstinstallation ──────────────────────────────────────────────────────────
def test_init_legt_admin_an(client):
    resp = client.post("/api/setup/init", json=ADMIN)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"

    # Danach ist die Einrichtung abgeschlossen …
    assert client.get("/api/setup/status").json()["needs_setup"] is False

    # … und der neue Admin kann sich einloggen.
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN["admin_email"], "password": ADMIN["admin_password"]},
    )
    assert login.status_code == 200

    # Der neue Benutzer ist tatsächlich Admin.
    token = data["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_init_gesperrt_wenn_benutzer_existiert(client, test_user):
    resp = client.post("/api/setup/init", json=ADMIN)
    assert resp.status_code == 409


def test_init_passwort_zu_kurz(client):
    resp = client.post("/api/setup/init", json={**ADMIN, "admin_password": "kurz"})
    assert resp.status_code == 400


def test_init_ungueltige_email(client):
    resp = client.post("/api/setup/init", json={**ADMIN, "admin_email": "keinemail"})
    assert resp.status_code == 400


# ── Firma als Briefkopf verknüpfen ────────────────────────────────────────────
def _seed_kontakte_typ(db_session):
    et = EntityType(name="Kontakte", slug="kontakte", tabs=[])
    db_session.add(et)
    db_session.flush()
    db_session.add(FieldDefinition(
        entity_type_id=et.id, name="Firmenname", key="firmenname",
        field_type="text", sort_order=1,
    ))
    db_session.commit()
    return et


def test_init_mit_firma_verknuepft_briefkopf(client, db_session):
    _seed_kontakte_typ(db_session)

    payload = {
        **ADMIN,
        "company": {
            "firmenname": "Muster GmbH",
            "email": "office@muster.at",
            "iban": "AT123456789",
        },
    }
    resp = client.post("/api/setup/init", json=payload)
    assert resp.status_code == 200, resp.text
    contact_id = resp.json()["company_contact_id"]
    assert contact_id

    # Briefkopf-Verknüpfung wurde in den Settings gespeichert.
    stored = {s.key: s.value for s in db_session.query(Setting).all()}
    assert stored.get("company_contact_id") == contact_id
    assert stored.get("company_contact_type") == "kontakte"
    # Firmenname landet zugleich als App-Anzeigename (Einstellungen/Allgemein)
    assert stored.get("company_name") == "Muster GmbH"

    # Über den öffentlichen Endpunkt ist der Firmen-Kontakt abrufbar.
    token = resp.json()["access_token"]
    cc = client.get("/api/settings/company-contact",
                    headers={"Authorization": f"Bearer {token}"})
    assert cc.status_code == 200
    assert cc.json()["contact"]["display_name"] == "Muster GmbH"
