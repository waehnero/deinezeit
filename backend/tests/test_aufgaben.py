"""
Tests für das Aufgabenmodul (zentrale To-do-Liste).

Nutzt die Standard-Fixtures aus conftest.py:
  client / test_user / auth_client (siehe test_auth.py als Vorlage).
"""
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _neue_aufgabe(auth_client, **overrides):
    payload = {"title": "Testaufgabe", **overrides}
    resp = auth_client.post("/api/aufgaben/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Zugriffsschutz ────────────────────────────────────────────────────────────
def test_liste_ohne_token_abgelehnt(client):
    resp = client.get("/api/aufgaben/")
    assert resp.status_code in (401, 403)


def test_anlegen_ohne_token_abgelehnt(client):
    resp = client.post("/api/aufgaben/", json={"title": "x"})
    assert resp.status_code in (401, 403)


# ── CRUD ──────────────────────────────────────────────────────────────────────
def test_aufgabe_anlegen(auth_client):
    data = _neue_aufgabe(auth_client, description="Beschreibung",
                         priority="hoch", due_date="2026-07-10")
    assert data["title"] == "Testaufgabe"
    assert data["status"] == "offen"
    assert data["priority"] == "hoch"
    assert data["due_date"] == "2026-07-10"
    assert data["source"] == "manuell"
    assert data["created_by_name"] == "Test Benutzer"
    assert data["completed_at"] is None


def test_aufgabe_lesen(auth_client):
    created = _neue_aufgabe(auth_client)
    resp = auth_client.get(f"/api/aufgaben/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_aufgabe_aendern(auth_client):
    created = _neue_aufgabe(auth_client)
    resp = auth_client.put(f"/api/aufgaben/{created['id']}",
                           json={"title": "Geändert", "priority": "kritisch"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Geändert"
    assert data["priority"] == "kritisch"


def test_aufgabe_loeschen(auth_client):
    created = _neue_aufgabe(auth_client)
    resp = auth_client.delete(f"/api/aufgaben/{created['id']}")
    assert resp.status_code == 204
    resp = auth_client.get(f"/api/aufgaben/{created['id']}")
    assert resp.status_code == 404


def test_unbekannte_aufgabe_404(auth_client):
    resp = auth_client.get("/api/aufgaben/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ── Erledigt-Logik ────────────────────────────────────────────────────────────
def test_erledigt_setzt_completed_at(auth_client):
    created = _neue_aufgabe(auth_client)
    resp = auth_client.put(f"/api/aufgaben/{created['id']}", json={"status": "erledigt"})
    assert resp.status_code == 200
    assert resp.json()["completed_at"] is not None

    # Zurück auf offen -> completed_at wird wieder entfernt
    resp = auth_client.put(f"/api/aufgaben/{created['id']}", json={"status": "offen"})
    assert resp.json()["completed_at"] is None


# ── Filter ────────────────────────────────────────────────────────────────────
def test_filter_status_und_prioritaet(auth_client):
    _neue_aufgabe(auth_client, title="A", priority="hoch")
    _neue_aufgabe(auth_client, title="B", priority="niedrig")
    resp = auth_client.get("/api/aufgaben/", params={"priority": "niedrig"})
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert titles == ["B"] or set(titles) == {"B"}


def test_filter_volltext(auth_client):
    _neue_aufgabe(auth_client, title="Rechnung schreiben")
    _neue_aufgabe(auth_client, title="Anruf Kunde")
    resp = auth_client.get("/api/aufgaben/", params={"q": "rechnung"})
    assert [t["title"] for t in resp.json()] == ["Rechnung schreiben"]


def test_filter_faelligkeit(auth_client):
    _neue_aufgabe(auth_client, title="Frueh", due_date="2026-07-05")
    _neue_aufgabe(auth_client, title="Spaet", due_date="2026-08-05")
    resp = auth_client.get("/api/aufgaben/",
                           params={"due_from": "2026-08-01", "due_to": "2026-08-31"})
    assert [t["title"] for t in resp.json()] == ["Spaet"]


def test_filter_mine(auth_client, test_user):
    _neue_aufgabe(auth_client, title="Meine")
    resp = auth_client.get("/api/aufgaben/", params={"mine": True})
    assert [t["title"] for t in resp.json()] == ["Meine"]


# ── Zuweisung (denormalisierter Name) ─────────────────────────────────────────
def test_zuweisung_aufloesen(auth_client, test_user):
    created = _neue_aufgabe(auth_client, assignee_id=str(test_user.id))
    assert created["assignee_name"] == "Test Benutzer"

    # Zuweisung entfernen
    resp = auth_client.put(f"/api/aufgaben/{created['id']}", json={"assignee_id": None})
    assert resp.json()["assignee_name"] is None


def test_zuweisung_unbekannter_benutzer_404(auth_client):
    resp = auth_client.post("/api/aufgaben/", json={
        "title": "x", "assignee_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 404


# ── Verknüpfung Projektplan ───────────────────────────────────────────────────
def test_verknuepfung_planungsaufgabe(auth_client):
    # Planungsprojekt + Aufgabe über die Projektplan-API anlegen
    resp = auth_client.post("/api/projektplan/projects", json={"name": "Projekt X"})
    assert resp.status_code in (200, 201), resp.text
    project_id = resp.json()["id"]
    resp = auth_client.post(f"/api/projektplan/projects/{project_id}/tasks",
                            json={"title": "Vorgang 1"})
    assert resp.status_code in (200, 201), resp.text
    task_id = resp.json()["id"]

    todo = _neue_aufgabe(auth_client, planning_task_id=task_id)
    assert todo["planning_task_title"] == "Vorgang 1"
    # Projekt wird automatisch mitgezogen
    assert todo["planning_project_id"] == project_id
    assert todo["planning_project_name"] == "Projekt X"


def test_verknuepfung_unbekannte_planungsaufgabe_404(auth_client):
    resp = auth_client.post("/api/aufgaben/", json={
        "title": "x", "planning_task_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 404


# ── Eingeblendete Projektplan-Aufgaben ────────────────────────────────────────
def _planungsaufgabe(auth_client, projekt_name="Projekt Y", **task_overrides):
    resp = auth_client.post("/api/projektplan/projects", json={"name": projekt_name})
    assert resp.status_code in (200, 201), resp.text
    project_id = resp.json()["id"]
    resp = auth_client.post(f"/api/projektplan/projects/{project_id}/tasks",
                            json={"title": "Projektvorgang", **task_overrides})
    assert resp.status_code in (200, 201), resp.text
    return project_id, resp.json()["id"]


def test_projektplan_aufgabe_erscheint_in_liste(auth_client):
    project_id, task_id = _planungsaufgabe(auth_client)
    resp = auth_client.get("/api/aufgaben/")
    assert resp.status_code == 200
    eintraege = {t["id"]: t for t in resp.json()}
    assert task_id in eintraege
    t = eintraege[task_id]
    assert t["source"] == "projektplan"
    assert t["title"] == "Projektvorgang"
    assert t["planning_project_id"] == project_id


def test_projektplan_meilenstein_nicht_in_liste(auth_client):
    _, task_id = _planungsaufgabe(auth_client, projekt_name="Projekt M",
                                  is_milestone=True)
    resp = auth_client.get("/api/aufgaben/")
    assert task_id not in [t["id"] for t in resp.json()]


def test_projektplan_ausblendbar(auth_client):
    _, task_id = _planungsaufgabe(auth_client)
    resp = auth_client.get("/api/aufgaben/", params={"include_projektplan": False})
    assert task_id not in [t["id"] for t in resp.json()]


def test_projektplan_aufgabe_status_aendern(auth_client):
    project_id, task_id = _planungsaufgabe(auth_client)
    # Über die Aufgaben-API auf erledigt setzen …
    resp = auth_client.put(f"/api/aufgaben/{task_id}", json={"status": "erledigt"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "erledigt"
    # … und im Projektplan prüfen (inkl. Fortschritt 100)
    resp = auth_client.get(f"/api/projektplan/projects/{project_id}")
    tasks = resp.json()["tasks"]
    def _finde(liste):
        for t in liste:
            if t["id"] == task_id:
                return t
            sub = _finde(t.get("children") or [])
            if sub:
                return sub
        return None
    task = _finde(tasks)
    assert task is not None
    assert task["status"] == "erledigt"
    assert task["progress"] == 100


def test_projektplan_aufgabe_loeschen_abgelehnt(auth_client):
    _, task_id = _planungsaufgabe(auth_client)
    resp = auth_client.delete(f"/api/aufgaben/{task_id}")
    assert resp.status_code == 400


# ── Einstellungen ─────────────────────────────────────────────────────────────
def test_einstellungen_defaults(auth_client):
    resp = auth_client.get("/api/aufgaben/einstellungen")
    assert resp.status_code == 200
    data = resp.json()
    values = [s["value"] for s in data["statuses"]]
    assert "offen" in values and "erledigt" in values
    assert data["done_status"] == "erledigt"


def test_einstellungen_schreiben_nur_admin(auth_client):
    resp = auth_client.put("/api/aufgaben/einstellungen", json={
        "statuses": [], "priorities": [], "done_status": "erledigt"})
    assert resp.status_code == 403


def test_einstellungen_schreiben_als_admin(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": "admin@deinezeit.local",
                             "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})

    body = {
        "statuses": [{"value": "neu", "label": "Neu", "color": "#000000"}],
        "priorities": [{"value": "p1", "label": "P1", "color": "#ff0000"}],
        "done_status": "fertig",
    }
    resp = client.put("/api/aufgaben/einstellungen", json=body)
    assert resp.status_code == 200

    resp = client.get("/api/aufgaben/einstellungen")
    data = resp.json()
    assert data["statuses"][0]["value"] == "neu"
    assert data["done_status"] == "fertig"
