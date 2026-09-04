"""
Kleine Härtungen aus dem Audit 02.09.2026 (K-24): SEC-010, SEC-011, SEC-014,
BUG-004, BUG-005.
"""
import uuid
from urllib.parse import unquote

from app.core.http import content_disposition


# ── BUG-005: Dateinamen mit Umlauten/Anführungszeichen im Header ─────────────

def test_content_disposition_mit_umlauten_und_anfuehrungszeichen():
    kopf = content_disposition("attachment", 'Bericht "März" 2026.pdf')
    assert kopf.startswith('attachment; filename="Bericht \'M_rz\' 2026.pdf"')
    assert "filename*=UTF-8''" in kopf
    assert unquote(kopf.split("filename*=UTF-8''")[1]) == 'Bericht "März" 2026.pdf'
    assert "\n" not in content_disposition("inline", "a\r\nb.pdf")
    assert content_disposition("inline", "") .startswith('inline; filename="datei"')
    assert content_disposition("sonstwas", "x").startswith("attachment;")


def test_download_header_traegt_utf8_dateinamen(auth_client, monkeypatch):
    from app.services import storage_service
    ablage = {}
    monkeypatch.setattr(storage_service, "upload_file",
                        lambda key, data, mimetype=None, db=None, backend=None: ablage.__setitem__(key, data))
    monkeypatch.setattr(storage_service, "download_file",
                        lambda key, db=None, backend=None: (ablage.get(key, b""), "text/plain"))
    monkeypatch.setattr(storage_service, "current_backend", lambda db=None: "minio")
    resp = auth_client.post(f"/api/datacenter/kontakte/{uuid.uuid4()}/upload",
                            files={"file": ("Größe & Maß.txt", b"x", "text/plain")})
    assert resp.status_code == 200, resp.text
    dl = auth_client.get(f"/api/datacenter/{resp.json()['id']}/download")
    assert dl.status_code == 200
    cd = dl.headers["content-disposition"]
    assert "filename*=UTF-8''Gr%C3%B6%C3%9Fe%20%26%20Ma%C3%9F.txt" in cd


# ── SEC-011: keine internen Fehlertexte nach außen ───────────────────────────

def test_speicherfehler_liefert_generische_meldung(auth_client, monkeypatch):
    from app.services import storage_service
    def kaputt(*a, **kw):
        raise RuntimeError("HTTPConnectionPool(host='minio', port=9000): interner Hostname")
    monkeypatch.setattr(storage_service, "upload_file", kaputt)
    monkeypatch.setattr(storage_service, "current_backend", lambda db=None: "minio")
    resp = auth_client.post(f"/api/datacenter/kontakte/{uuid.uuid4()}/upload",
                            files={"file": ("a.txt", b"x", "text/plain")})
    assert resp.status_code == 500
    assert "minio" not in resp.text and "HTTPConnectionPool" not in resp.text
    assert "Serverlog" in resp.json()["detail"]


# ── SEC-014: limit begrenzt ──────────────────────────────────────────────────

def test_events_limit_ist_begrenzt(auth_client):
    assert auth_client.get("/api/auth/events", params={"limit": 1000000}).status_code == 422
    assert auth_client.get("/api/auth/events", params={"limit": 0}).status_code == 422
    assert auth_client.get("/api/auth/events", params={"limit": 200}).status_code == 200


# ── SEC-010: Backup-Ping ─────────────────────────────────────────────────────

def test_backup_ping_ohne_konfiguration_ist_nicht_offen(client, monkeypatch):
    monkeypatch.delenv("BACKUP_PING_TOKEN", raising=False)
    assert client.post("/api/settings/backup-ping").status_code == 503


def test_backup_ping_verlangt_den_richtigen_token(client, monkeypatch):
    monkeypatch.setenv("BACKUP_PING_TOKEN", "ping-geheim")
    assert client.post("/api/settings/backup-ping").status_code == 401
    assert client.post("/api/settings/backup-ping",
                       headers={"X-Backup-Token": "falsch"}).status_code == 401
    ok = client.post("/api/settings/backup-ping", headers={"X-Backup-Token": "ping-geheim"})
    assert ok.status_code == 200 and ok.json()["ok"] is True


# ── BUG-004: Name in der Reset-Mail wird escaped ─────────────────────────────

def test_reset_mail_escaped_den_namen(client, db_session, monkeypatch):
    from app.services.auth_service import auth_service
    from app.api import auth as auth_api
    from tests.conftest import TEST_USER_PASSWORD
    auth_service.create_user(db_session, email="xss@deinezeit.local",
                             full_name='<img src=x onerror="alert(1)">',
                             password=TEST_USER_PASSWORD, role="employee")
    gesendet = {}
    import app.services.email_service as es
    monkeypatch.setattr(es, "send_email", lambda **kw: gesendet.update(kw))
    resp = client.post("/api/auth/password/forgot", json={"email": "xss@deinezeit.local"})
    assert resp.status_code == 200
    assert "<img" not in gesendet["body_html"]
    assert "&lt;img" in gesendet["body_html"]
