"""
Smoke-Test: Läuft die App überhaupt und antworten die Health-Endpoints?
Der einfachste mögliche Test – gut als Einstieg und als CI-Mindestprüfung.

Es gibt zwei Health-Endpoints:
- /api/health         (direkt in app/main.py, liefert auch die Version)
- /api/system/health  (im system-Router)
"""


def test_health_root(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_system(client):
    resp = client.get("/api/system/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
