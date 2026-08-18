"""
Tests für die Modulrechte (users.allowed_modules).

Regelwerk (Beschluss 2026-07-12):
- NULL = alle Module erlaubt (Standard, Bestandsverhalten).
- Admin hat immer alle Module, unabhängig von allowed_modules.
- Router ganzer Module liefern 403 ohne Freischaltung.
- Stammdaten: Lesen für alle, Schreiben nur mit Modul 'stammdaten'.
- Datacenter: Übersicht (/all, /stats) nur mit Modul; Anhänge je
  Datensatz bleiben offen (Anhang-Panels anderer Module).
- Nur der Admin darf Modulrechte setzen; unbekannte Keys → 400.
"""
import pytest

from app.core.modules import MODULE_KEYS, user_modules
from tests.conftest import TEST_USER_PASSWORD


def _login(client, email):
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _set_modules(db, user, modules):
    user.allowed_modules = modules
    db.commit()


# ── Grundlagen ────────────────────────────────────────────────────────────────

def test_default_alle_module(db_session, test_user, admin_user):
    assert user_modules(test_user) == list(MODULE_KEYS)
    # Admin: immer alle, auch mit leerer Liste
    admin_user.allowed_modules = []
    assert user_modules(admin_user) == list(MODULE_KEYS)


def test_me_liefert_module(client, db_session, test_user):
    _set_modules(db_session, test_user, ["zeiterfassung"])
    headers = _login(client, test_user.email)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["modules"] == ["zeiterfassung"]
    assert resp.json()["allowed_modules"] == ["zeiterfassung"]


# ── Router-Sperren ────────────────────────────────────────────────────────────

def test_gesperrte_module_liefern_403(client, db_session, test_user):
    _set_modules(db_session, test_user, ["zeiterfassung"])
    headers = _login(client, test_user.email)

    # Freigeschaltet: Zeiterfassung geht
    resp = client.get("/api/zeiterfassung/entries", headers=headers)
    assert resp.status_code == 200

    # Gesperrt: Aufgaben, Projekte, Verkauf, Postecke
    for url in ("/api/aufgaben/", "/api/projektplan/projects",
                "/api/invoices", "/api/postecke/posts"):
        resp = client.get(url, headers=headers)
        assert resp.status_code == 403, f"{url}: {resp.status_code}"


def test_admin_ignoriert_sperren(client, db_session, admin_user):
    _set_modules(db_session, admin_user, [])
    headers = _login(client, admin_user.email)
    resp = client.get("/api/aufgaben/", headers=headers)
    assert resp.status_code == 200


def test_stammdaten_lesen_offen_schreiben_gesperrt(client, db_session, test_user):
    _set_modules(db_session, test_user, ["zeiterfassung"])
    headers = _login(client, test_user.email)

    # Lesen: erlaubt (Auswahlfelder in anderen Modulen)
    resp = client.get("/api/masterdata/types", headers=headers)
    assert resp.status_code == 200

    # Schreiben: gesperrt ohne Modul 'stammdaten'
    # (Typ existiert evtl. nicht — wichtig ist der 403 VOR der 404-Prüfung)
    resp = client.post("/api/masterdata/types/kontakte/records",
                       json={"data": {"name": "Test"}}, headers=headers)
    assert resp.status_code == 403


def test_datacenter_uebersicht_gesperrt_anhaenge_offen(client, db_session, test_user):
    _set_modules(db_session, test_user, ["zeiterfassung"])
    headers = _login(client, test_user.email)

    # Übersicht + Widget-Stats: gesperrt
    assert client.get("/api/datacenter/all", headers=headers).status_code == 403
    assert client.get("/api/datacenter/stats", headers=headers).status_code == 403

    # Anhänge eines Datensatzes: offen (Anhang-Panel z.B. am Zeiteintrag)
    resp = client.get(
        "/api/datacenter/zeiterfassung/00000000-0000-0000-0000-000000000001",
        headers=headers)
    assert resp.status_code == 200


# ── Verwaltung durch den Admin ────────────────────────────────────────────────

def test_admin_setzt_module_ueber_gruppen(client, db_session, test_user,
                                          admin_user):
    """Modulrechte vergibt der Administrator über Gruppen, nicht mehr je Benutzer.

    Vorher setzte dieser Test ``allowed_modules`` unmittelbar. Seit Migration
    0055 kommen die Rechte aus Gruppen, und seit Teiletappe 2c weist die
    Benutzerverwaltung genau die zu. Das alte Feld wird ausdrücklich abgelehnt
    statt still ignoriert — ein Häkchen, das gesetzt aussieht und nichts
    bewirkt, hat hier schon einmal Zeit gekostet.
    """
    from app.core import berechtigungen as B
    from app.models.user import PermissionGroup

    admin_headers = _login(client, admin_user.email)

    # Das alte Feld wird nicht mehr angenommen.
    resp = client.put(f"/api/users/{test_user.id}",
                      json={"allowed_modules": ["zeiterfassung", "aufgaben"]},
                      headers=admin_headers)
    assert resp.status_code == 400
    assert "Rechtegruppen" in resp.json()["detail"]

    # Der neue Weg: Gruppe anlegen und zuweisen.
    blatt = B.leeres_rechteblatt()
    for modul in ("zeiterfassung", "aufgaben"):
        for recht in B.rechte_fuer_modul(modul):
            blatt[modul][recht] = True
    gruppe = PermissionGroup(name="Zeit und Aufgaben", rechte=blatt)
    db_session.add(gruppe)
    db_session.commit()

    resp = client.put(f"/api/groups/users/{test_user.id}/groups",
                      json={"group_ids": [str(gruppe.id)]},
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert sorted(resp.json()["module"]) == ["aufgaben", "zeiterfassung"]

    # Und die Modul-Liste an /auth/me folgt derselben Quelle.
    db_session.refresh(test_user)
    assert sorted(test_user.modules) == ["aufgaben", "zeiterfassung"]

    # Normale Benutzer dürfen keine Benutzer bearbeiten
    user_headers = _login(client, test_user.email)
    resp = client.put(f"/api/users/{test_user.id}",
                      json={"allowed_modules": []}, headers=user_headers)
    assert resp.status_code == 403
