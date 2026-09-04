"""
Projektplanung (/api/projektplan): Projekte, Aufgabenbaum, Abhängigkeiten,
Gantt-Termine, Checklisten, Meilensteine — und die Sperren, die gebuchte
Zeiten schützen. Ergänzt im Audit (TEST-001, K-22): Das Modul war bis
04.09.2026 ohne einen einzigen Test.

Nutzt die Standard-Fixtures aus conftest.py (client / test_user / auth_client).
"""
from datetime import datetime, timedelta, timezone

from tests.conftest import TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"
BASIS = "/api/projektplan"


def _projekt(auth_client, **felder):
    resp = auth_client.post(f"{BASIS}/projects", json={"name": "Umbau Halle 3", **felder})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _aufgabe(auth_client, projekt_id, **felder):
    resp = auth_client.post(f"{BASIS}/projects/{projekt_id}/tasks",
                            json={"title": "Aufgabe", **felder})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _als_admin(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


# ── Zugriffsschutz ────────────────────────────────────────────────────────────

def test_ohne_anmeldung_abgelehnt(client):
    assert client.get(f"{BASIS}/projects").status_code in (401, 403)
    assert client.post(f"{BASIS}/projects", json={"name": "x"}).status_code in (401, 403)


# ── Projekte ──────────────────────────────────────────────────────────────────

def test_projekt_anlegen_lesen_aendern(auth_client):
    p = _projekt(auth_client, description="Dach und Fassade", color="#ff8800",
                 start_date="2026-09-07", end_date="2026-10-30")
    assert p["name"] == "Umbau Halle 3"
    assert p["status"] == "offen"
    assert p["tasks"] == [] and p["milestones"] == [] and p["dependencies"] == []

    liste = auth_client.get(f"{BASIS}/projects").json()
    assert [x["id"] for x in liste] == [p["id"]]
    assert liste[0]["task_count"] == 0 and liste[0]["progress_percent"] == 0

    resp = auth_client.put(f"{BASIS}/projects/{p['id']}",
                           json={"name": "Umbau Halle 4", "status": "in_arbeit"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Umbau Halle 4"
    assert resp.json()["status"] == "in_arbeit"


def test_archivierte_projekte_nur_auf_wunsch(auth_client):
    p = _projekt(auth_client)
    auth_client.put(f"{BASIS}/projects/{p['id']}", json={"is_archived": True})
    assert auth_client.get(f"{BASIS}/projects").json() == []
    mit = auth_client.get(f"{BASIS}/projects", params={"include_archived": True}).json()
    assert [x["id"] for x in mit] == [p["id"]]


def test_unbekanntes_projekt_404(auth_client):
    assert auth_client.get(
        f"{BASIS}/projects/00000000-0000-0000-0000-000000000001").status_code == 404


# ── Aufgabenbaum und Fortschritt ──────────────────────────────────────────────

def test_aufgaben_mit_unteraufgaben_und_fortschritt(auth_client):
    p = _projekt(auth_client)
    a = _aufgabe(auth_client, p["id"], title="Planung", progress=100, status="erledigt")
    b = _aufgabe(auth_client, p["id"], title="Ausführung")
    b1 = _aufgabe(auth_client, p["id"], title="Gerüst", parent_task_id=b["id"])
    assert b1["parent_task_id"] == b["id"]

    detail = auth_client.get(f"{BASIS}/projects/{p['id']}").json()
    oben = {t["title"]: t for t in detail["tasks"]}
    assert set(oben) == {"Planung", "Ausführung"}          # Kinder hängen unter dem Elternteil
    assert [k["title"] for k in oben["Ausführung"]["children"]] == ["Gerüst"]

    liste = auth_client.get(f"{BASIS}/projects").json()[0]
    assert liste["task_count"] == 3
    assert liste["done_count"] == 1

    resp = auth_client.put(f"{BASIS}/tasks/{a['id']}", json={"priority": "hoch", "progress": 50})
    assert resp.status_code == 200, resp.text
    assert resp.json()["priority"] == "hoch" and resp.json()["progress"] == 50


def test_gantt_termine_gebuendelt_aendern(auth_client):
    p = _projekt(auth_client)
    a = _aufgabe(auth_client, p["id"], start_date="2026-09-07", due_date="2026-09-09")
    b = _aufgabe(auth_client, p["id"])
    resp = auth_client.put(f"{BASIS}/tasks/dates", json={"updates": [
        {"id": a["id"], "start_date": "2026-09-08", "due_date": "2026-09-12"},
        {"id": b["id"], "due_date": "2026-09-30"},
        {"id": "00000000-0000-0000-0000-000000000009", "due_date": "2026-01-01"},
    ]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 2                     # die Unbekannte wird übergangen

    detail = auth_client.get(f"{BASIS}/projects/{p['id']}").json()
    nach_id = {t["id"]: t for t in detail["tasks"]}
    assert nach_id[a["id"]]["start_date"] == "2026-09-08"
    assert nach_id[a["id"]]["due_date"] == "2026-09-12"
    assert nach_id[b["id"]]["due_date"] == "2026-09-30"


# ── Abhängigkeiten ────────────────────────────────────────────────────────────

def test_abhaengigkeiten_regeln(auth_client):
    p = _projekt(auth_client)
    q = _projekt(auth_client, name="Anderes Projekt")
    a = _aufgabe(auth_client, p["id"], title="A")
    b = _aufgabe(auth_client, p["id"], title="B")
    fremd = _aufgabe(auth_client, q["id"], title="Fremd")

    def verknuepfen(vor, nach, **extra):
        return auth_client.post(f"{BASIS}/dependencies",
                                json={"predecessor_id": vor, "successor_id": nach, **extra})

    assert verknuepfen(a["id"], a["id"]).status_code == 400            # mit sich selbst
    assert verknuepfen(a["id"], fremd["id"]).status_code == 400        # anderes Projekt
    resp = verknuepfen(a["id"], b["id"], dep_type="SS", lag_days=2)
    assert resp.status_code == 200, resp.text
    dep = resp.json()
    assert dep["dep_type"] == "SS" and dep["lag_days"] == 2
    assert verknuepfen(a["id"], b["id"]).status_code == 400            # doppelt
    assert verknuepfen(b["id"], a["id"]).status_code == 400            # Zyklus
    assert verknuepfen(a["id"], b["id"], dep_type="XX").status_code == 422

    detail = auth_client.get(f"{BASIS}/projects/{p['id']}").json()
    assert [d["id"] for d in detail["dependencies"]] == [dep["id"]]

    assert auth_client.delete(f"{BASIS}/dependencies/{dep['id']}").status_code == 200
    assert auth_client.delete(f"{BASIS}/dependencies/{dep['id']}").status_code == 404
    assert auth_client.get(f"{BASIS}/projects/{p['id']}").json()["dependencies"] == []


# ── Löschsperren: gebuchte Zeiten schützen ───────────────────────────────────

def _zeit_buchen(auth_client, db_session, task_id):
    """Zeiteintrag mit Aufgabenbezug — seit Bündel H über den Endpunkt
    (``task_id`` im Zeiteintrag), nicht mehr per Datenbank-Umweg."""
    start = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
    resp = auth_client.post("/api/zeiterfassung/entries", json={
        "project_name": "Umbau", "task_id": task_id,
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(hours=1)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_id"] == task_id
    return resp.json()


def test_aufgabe_mit_gebuchter_zeit_bleibt(auth_client, db_session):
    """Auch wenn die Zeit auf einer UNTERaufgabe hängt, ist die Elternaufgabe
    gesperrt — sonst risse die Kaskade den Zeitbezug mit."""
    p = _projekt(auth_client)
    eltern = _aufgabe(auth_client, p["id"], title="Eltern")
    kind = _aufgabe(auth_client, p["id"], title="Kind", parent_task_id=eltern["id"])
    _zeit_buchen(auth_client, db_session, kind["id"])

    resp = auth_client.delete(f"{BASIS}/tasks/{eltern['id']}")
    assert resp.status_code == 409, resp.text
    assert "1 Zeiteinträge" in resp.json()["detail"]

    # Ohne Buchung geht es — samt Kaskade auf die Kinder
    frei = _aufgabe(auth_client, p["id"], title="Frei")
    _aufgabe(auth_client, p["id"], title="Frei-Kind", parent_task_id=frei["id"])
    assert auth_client.delete(f"{BASIS}/tasks/{frei['id']}").status_code == 200
    titel = {t["title"] for t in auth_client.get(f"{BASIS}/projects/{p['id']}").json()["tasks"]}
    assert titel == {"Eltern"}


def test_unteraufgabe_loeschen_laesst_eltern_stehen(auth_client):
    """Bis 04.09.2026 zeigte die Löschkaskade im Modell vom Kind aufs
    Elternteil (verkehrte Beziehung) — hier der Riegel dagegen."""
    p = _projekt(auth_client)
    eltern = _aufgabe(auth_client, p["id"], title="Eltern")
    kind = _aufgabe(auth_client, p["id"], title="Kind", parent_task_id=eltern["id"])
    assert auth_client.delete(f"{BASIS}/tasks/{kind['id']}").status_code == 200
    titel = [t["title"] for t in auth_client.get(f"{BASIS}/projects/{p['id']}").json()["tasks"]]
    assert titel == ["Eltern"]


def test_projekt_loeschen_nur_admin_und_nicht_mit_zeiten(auth_client, admin_user, db_session):
    p = _projekt(auth_client)
    t = _aufgabe(auth_client, p["id"])
    _zeit_buchen(auth_client, db_session, t["id"])

    assert auth_client.delete(f"{BASIS}/projects/{p['id']}").status_code == 403   # Mitarbeiter

    c = _als_admin(auth_client, admin_user)
    resp = c.delete(f"{BASIS}/projects/{p['id']}")
    assert resp.status_code == 409, resp.text
    assert "archivieren" in resp.json()["detail"]

    leer = _projekt(c, name="Fehlanlage")
    assert c.delete(f"{BASIS}/projects/{leer['id']}").status_code == 200
    assert c.get(f"{BASIS}/projects/{leer['id']}").status_code == 404


# ── Duplizieren und Hochstufen ────────────────────────────────────────────────

def test_projekt_duplizieren_mit_und_ohne_aufgaben(auth_client):
    p = _projekt(auth_client)
    a = _aufgabe(auth_client, p["id"], title="A", status="erledigt", progress=100)
    _aufgabe(auth_client, p["id"], title="A1", parent_task_id=a["id"])
    auth_client.post(f"{BASIS}/projects/{p['id']}/milestones",
                     json={"title": "Rohbau fertig", "due_date": "2026-10-01"})

    resp = auth_client.post(f"{BASIS}/projects/{p['id']}/duplicate",
                            json={"reset_status": True})
    assert resp.status_code == 200, resp.text
    kopie = resp.json()
    assert kopie["id"] != p["id"]
    assert kopie["name"].startswith("Umbau Halle 3")
    assert [t["title"] for t in kopie["tasks"]] == ["A"]
    assert [k["title"] for k in kopie["tasks"][0]["children"]] == ["A1"]
    assert kopie["tasks"][0]["status"] == "offen" and kopie["tasks"][0]["progress"] == 0
    assert [m["title"] for m in kopie["milestones"]] == ["Rohbau fertig"]

    ohne = auth_client.post(f"{BASIS}/projects/{p['id']}/duplicate",
                            json={"name": "Nur Kopf", "include_tasks": False,
                                  "include_milestones": False}).json()
    assert ohne["name"] == "Nur Kopf"
    assert ohne["tasks"] == [] and ohne["milestones"] == []


def test_aufgabe_zum_projekt_hochstufen(auth_client):
    p = _projekt(auth_client)
    a = _aufgabe(auth_client, p["id"], title="Elektrik", description="Neu verkabeln")
    _aufgabe(auth_client, p["id"], title="Verteiler", parent_task_id=a["id"])
    _aufgabe(auth_client, p["id"], title="Leitungen", parent_task_id=a["id"])

    resp = auth_client.post(f"{BASIS}/tasks/{a['id']}/promote", json={})
    assert resp.status_code == 200, resp.text
    neu = resp.json()
    assert neu["name"] == "Elektrik"
    assert neu["description"] == "Neu verkabeln"
    assert neu["origin_task_id"] == a["id"]
    assert {t["title"] for t in neu["tasks"]} == {"Verteiler", "Leitungen"}
    assert all(t["parent_task_id"] is None for t in neu["tasks"])

    assert len(auth_client.get(f"{BASIS}/projects").json()) == 2


# ── Checklisten und Meilensteine ─────────────────────────────────────────────

def test_checkliste_an_projekt_und_aufgabe(auth_client):
    p = _projekt(auth_client)
    t = _aufgabe(auth_client, p["id"])

    assert auth_client.post(f"{BASIS}/checklist/project/{p['id']}",
                            json={"text": "   "}).status_code == 400
    assert auth_client.post(f"{BASIS}/checklist/etwas/{p['id']}",
                            json={"text": "x"}).status_code == 400
    assert auth_client.post(f"{BASIS}/checklist/task/{p['id']}",
                            json={"text": "x"}).status_code == 404

    e1 = auth_client.post(f"{BASIS}/checklist/project/{p['id']}",
                          json={"text": "Genehmigung einholen", "sort_order": 2}).json()
    e2 = auth_client.post(f"{BASIS}/checklist/project/{p['id']}",
                          json={"text": "Angebot prüfen", "sort_order": 1}).json()
    auth_client.post(f"{BASIS}/checklist/task/{t['id']}", json={"text": "Material bestellen"})

    liste = auth_client.get(f"{BASIS}/checklist/project/{p['id']}").json()
    assert [x["id"] for x in liste] == [e2["id"], e1["id"]]          # nach sort_order

    resp = auth_client.put(f"{BASIS}/checklist/item/{e1['id']}", json={"is_done": True})
    assert resp.status_code == 200 and resp.json()["is_done"] is True

    detail = auth_client.get(f"{BASIS}/projects/{p['id']}").json()
    assert len(detail["checklist"]) == 2
    assert [x["text"] for x in detail["tasks"][0]["checklist"]] == ["Material bestellen"]

    assert auth_client.delete(f"{BASIS}/checklist/item/{e2['id']}").status_code == 200
    assert len(auth_client.get(f"{BASIS}/checklist/project/{p['id']}").json()) == 1


def test_checklistpunkt_zur_aufgabe_hochstufen(auth_client):
    p = _projekt(auth_client)
    e = auth_client.post(f"{BASIS}/checklist/project/{p['id']}",
                         json={"text": "Statik prüfen lassen"}).json()
    resp = auth_client.post(f"{BASIS}/checklist/item/{e['id']}/promote")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Statik prüfen lassen"
    assert resp.json()["project_id"] == p["id"]


def test_meilensteine(auth_client):
    p = _projekt(auth_client)
    m = auth_client.post(f"{BASIS}/projects/{p['id']}/milestones",
                         json={"title": "Abnahme", "due_date": "2026-11-15"}).json()
    assert m["is_reached"] is False
    resp = auth_client.put(f"{BASIS}/milestones/{m['id']}", json={"is_reached": True})
    assert resp.status_code == 200 and resp.json()["is_reached"] is True
    assert auth_client.delete(f"{BASIS}/milestones/{m['id']}").status_code == 200
    assert auth_client.get(f"{BASIS}/projects/{p['id']}").json()["milestones"] == []
