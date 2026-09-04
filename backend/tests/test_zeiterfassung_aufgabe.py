"""
Aufgabenbezug im Zeiteintrag (Bündel H, 04.09.2026).

``time_entries.task_id`` gab es seit Migration 0016, doch kein Endpunkt setzte
die Spalte — die Löschsperren im Projektplan und die „gebuchten Minuten" je
Aufgabe liefen ins Leere. Jetzt nimmt die Zeiterfassung ``task_id`` an, prüft
die Aufgabe und übernimmt ihren Titel.
"""
from datetime import datetime, timedelta, timezone

BASIS = "/api/projektplan"


def _projekt_mit_aufgabe(auth_client, projekt="Umbau Halle 3", aufgabe="Gerüst", **task):
    p = auth_client.post(f"{BASIS}/projects", json={"name": projekt}).json()
    t = auth_client.post(f"{BASIS}/projects/{p['id']}/tasks",
                         json={"title": aufgabe, **task}).json()
    return p, t


def _eintrag(auth_client, **felder):
    start = datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc)
    return auth_client.post("/api/zeiterfassung/entries", json={
        "project_name": "Umbau", "started_at": start.isoformat(),
        "ended_at": (start + timedelta(hours=1)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {}, **felder,
    })


def test_eintrag_uebernimmt_den_aufgabentitel(auth_client):
    _, t = _projekt_mit_aufgabe(auth_client)
    resp = _eintrag(auth_client, task_id=t["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_id"] == t["id"]
    assert resp.json()["task_title"] == "Gerüst"

    # …und die Aufgabe zeigt die gebuchten Minuten
    detail = auth_client.get(f"{BASIS}/projects/{t['project_id']}").json()
    assert detail["tasks"][0]["logged_minutes"] == 60


def test_unbekannte_aufgabe_wird_abgelehnt(auth_client):
    resp = _eintrag(auth_client, task_id="00000000-0000-0000-0000-000000000042")
    assert resp.status_code == 404
    assert "Aufgabe" in resp.json()["detail"]


def test_ohne_aufgabe_bleibt_alles_wie_bisher(auth_client):
    resp = _eintrag(auth_client)
    assert resp.status_code == 200
    assert resp.json()["task_id"] is None and resp.json()["task_title"] is None


def test_bezug_aendern_und_loesen(auth_client):
    _, a = _projekt_mit_aufgabe(auth_client, aufgabe="A")
    _, b = _projekt_mit_aufgabe(auth_client, projekt="Zweites", aufgabe="B")
    e = _eintrag(auth_client, task_id=a["id"]).json()

    # Feld weggelassen → Bezug bleibt
    resp = auth_client.put(f"/api/zeiterfassung/entries/{e['id']}", json={"note": "x"})
    assert resp.json()["task_id"] == a["id"]
    # umhängen
    resp = auth_client.put(f"/api/zeiterfassung/entries/{e['id']}", json={"task_id": b["id"]})
    assert resp.json()["task_id"] == b["id"] and resp.json()["task_title"] == "B"
    # ausdrücklich null → gelöst
    resp = auth_client.put(f"/api/zeiterfassung/entries/{e['id']}", json={"task_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_id"] is None and resp.json()["task_title"] is None


def test_timer_start_mit_aufgabe(auth_client):
    _, t = _projekt_mit_aufgabe(auth_client)
    resp = auth_client.post("/api/zeiterfassung/start", json={
        "project_name": "Umbau", "task_id": t["id"],
        "started_at": datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc).isoformat(),
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_title"] == "Gerüst" and resp.json()["is_running"] is True


def test_aufgabenauswahl_zeigt_nur_offene_aus_aktiven_projekten(auth_client):
    p, offen = _projekt_mit_aufgabe(auth_client, aufgabe="Offen")
    auth_client.post(f"{BASIS}/projects/{p['id']}/tasks",
                     json={"title": "Erledigt", "status": "erledigt"})
    auth_client.post(f"{BASIS}/projects/{p['id']}/tasks",
                     json={"title": "Meilenstein", "is_milestone": True})
    q, _ = _projekt_mit_aufgabe(auth_client, projekt="Archiv", aufgabe="Alt")
    auth_client.put(f"{BASIS}/projects/{q['id']}", json={"is_archived": True})

    liste = auth_client.get("/api/zeiterfassung/aufgaben").json()
    assert [(x["project_name"], x["title"]) for x in liste] == [("Umbau Halle 3", "Offen")]
    assert liste[0]["id"] == offen["id"]

    assert auth_client.get("/api/zeiterfassung/aufgaben", params={"q": "off"}).json()[0]["title"] == "Offen"
    assert auth_client.get("/api/zeiterfassung/aufgaben", params={"q": "gibtesnicht"}).json() == []


def test_aufgabenauswahl_braucht_kein_projektmodul(client, test_user, db_session):
    """Wer Zeiten erfasst, hat nicht zwingend das Modul „Projekte"."""
    from app.models.projektplan import PlanningProject, Task
    proj = PlanningProject(name="Fremdes Projekt"); db_session.add(proj); db_session.flush()
    db_session.add(Task(project_id=proj.id, title="Sichtbar")); db_session.commit()

    from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD
    resp = client.post("/api/auth/login", json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD})
    kopf = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    # Modul „Projekte" entziehen, Zeiterfassung behalten
    from app.models.user import User
    u = db_session.query(User).filter(User.id == test_user.id).first()
    u.allowed_modules = ["dashboard", "zeiterfassung"]; db_session.commit()

    assert client.get(f"{BASIS}/projects", headers=kopf).status_code == 403
    assert client.get("/api/zeiterfassung/aufgaben", headers=kopf).status_code == 200
