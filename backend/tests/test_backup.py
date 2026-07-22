"""
Backup-Tests – serverseitiges OneDrive-Backup (Ziel 'onedrive').

Deckt ab:
- Round-Trip der neuen Backup-Settings (backup_target, backup_onedrive_*),
  inkl. Maskierung des Client-Secrets bei GET.
- Admin-Schutz der neuen Endpunkte (/backup/onedrive/test, /backup/run).
- Verdrahtung des Verbindungstests (kein 500; Provider-Ergebnis wird
  durchgereicht) – ohne echten Netzwerkzugriff (Graph wird gemockt).

Gleiche Fixtures wie test_auth.py (siehe tests/conftest.py).
"""
import pytest
from tests.conftest import TEST_USER_PASSWORD


# ── Admin-Client-Hilfe ────────────────────────────────────────────────────────
@pytest.fixture()
def admin_client(client, admin_user):
    """Wie `client`, aber mit eingeloggtem Admin (Bearer-Token gesetzt)."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ── Settings-Round-Trip ───────────────────────────────────────────────────────
def test_backup_settings_roundtrip_und_secret_maskiert(admin_client):
    payload = {
        "backup_target":                   "onedrive",
        "backup_schedule_time":            "03:30",
        "backup_keep_days":                "14",
        "backup_onedrive_use_graph_creds": "false",
        "backup_onedrive_tenant_id":       "tenant-abc",
        "backup_onedrive_client_id":       "client-abc",
        "backup_onedrive_client_secret":   "streng-geheim",
        "backup_onedrive_drive_type":      "sharepoint",
        "backup_onedrive_site_id":         "contoso.sharepoint.com,guid,guid",
        "backup_onedrive_folder":          "DZ-Backups",
    }
    r = admin_client.put("/api/settings", json=payload)
    assert r.status_code == 200

    data = admin_client.get("/api/settings").json()
    assert data["backup_target"]              == "onedrive"
    assert data["backup_schedule_time"]       == "03:30"
    assert data["backup_keep_days"]           == "14"
    assert data["backup_onedrive_tenant_id"]  == "tenant-abc"
    assert data["backup_onedrive_drive_type"] == "sharepoint"
    assert data["backup_onedrive_folder"]     == "DZ-Backups"
    # Secret darf NIE zurückkommen
    assert "backup_onedrive_client_secret" not in data


# ── Admin-Schutz ──────────────────────────────────────────────────────────────
def test_backup_onedrive_test_ohne_login_abgelehnt(client):
    # Admin-Endpunkte liefern ohne Token 403 (HTTPBearer „Not authenticated")
    r = client.post("/api/settings/backup/onedrive/test", json={})
    assert r.status_code in (401, 403)


def test_backup_onedrive_test_als_employee_403(auth_client):
    r = auth_client.post("/api/settings/backup/onedrive/test", json={})
    assert r.status_code == 403


def test_backup_run_ohne_login_abgelehnt(client):
    r = client.post("/api/settings/backup/run")
    assert r.status_code in (401, 403)


def test_backup_run_als_employee_403(auth_client):
    r = auth_client.post("/api/settings/backup/run")
    assert r.status_code == 403


# ── Verbindungstest: Verdrahtung ohne Netzwerk ───────────────────────────────
def test_backup_onedrive_test_reicht_providerergebnis_durch(admin_client, monkeypatch):
    """Graph-Aufruf wird gemockt: Endpoint darf keinen 500 werfen und muss das
    Provider-Resultat 1:1 zurückgeben."""
    from app.services import storage_service

    def fake_test_connection(self):
        # Wir prüfen zugleich, dass die Felder korrekt übergeben wurden.
        assert self.tenant_id == "t-1"
        assert self.root_folder == "DZ-Backups"
        return {"ok": True, "message": "Verbunden (Mock)"}

    monkeypatch.setattr(storage_service.OneDriveProvider,
                        "test_connection", fake_test_connection)

    r = admin_client.post("/api/settings/backup/onedrive/test", json={
        "use_graph_creds": "false",
        "tenant_id":       "t-1",
        "client_id":       "c-1",
        "client_secret":   "s-1",
        "drive_type":      "sharepoint",
        "site_id":         "site-1",
        "folder":          "DZ-Backups",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True, "message": "Verbunden (Mock)"}


def test_backup_onedrive_test_leere_creds_kein_500(admin_client, monkeypatch):
    """Auch bei leeren Zugangsdaten liefert der Endpoint sauber ok:false statt 500."""
    from app.services import storage_service

    def fake_test_connection(self):
        return {"ok": False, "message": "Token-Fehler: keine Zugangsdaten"}

    monkeypatch.setattr(storage_service.OneDriveProvider,
                        "test_connection", fake_test_connection)

    r = admin_client.post("/api/settings/backup/onedrive/test", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ── Speicher-Konsolidierung (Migration) ───────────────────────────────────────
def _mk_attachment(db, storage_provider, storage_key, filename):
    from app.models.attachment import Attachment
    import uuid
    a = Attachment(
        entity_type="kontakte", entity_id=uuid.uuid4(), type="file",
        storage_key=storage_key, storage_provider=storage_provider,
        filename=filename, display_name=filename, mimetype="text/plain",
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def test_migration_status_zaehlt_offene(admin_client, db_session, monkeypatch):
    from app.services import storage_service
    monkeypatch.setattr(storage_service, "current_backend", lambda db=None: "onedrive")
    _mk_attachment(db_session, "minio",    "kontakte/a/x.txt", "x.txt")
    _mk_attachment(db_session, "onedrive", "kontakte/a/y.txt", "y.txt")
    r = admin_client.get("/api/settings/storage/migration-status")
    assert r.status_code == 200
    data = r.json()
    assert data["active"] == "onedrive"
    assert data["total"] == 2
    assert data["pending"] == 1          # nur die minio-Datei ist offen
    assert data["counts"]["minio"] == 1


def test_migrate_kopiert_und_setzt_provider(admin_client, db_session, monkeypatch):
    """Migration lädt aus dem Quell-Provider, lädt in den Ziel-Provider und
    aktualisiert storage_provider. Provider werden gemockt (kein Netzwerk)."""
    from app.services import storage_service

    store = {"kontakte/a/x.txt": b"hallo"}
    uploaded = {}

    class FakeSrc:
        def download(self, key): return store[key], "text/plain"
        def delete(self, key): store.pop(key, None)
    class FakeTarget:
        def upload(self, key, data, mime): uploaded[key] = data

    monkeypatch.setattr(storage_service, "current_backend", lambda db=None: "onedrive")
    def fake_build(backend, db=None):
        return FakeTarget() if backend == "onedrive" else FakeSrc()
    monkeypatch.setattr(storage_service, "build_provider_for", fake_build)

    att = _mk_attachment(db_session, "minio", "kontakte/a/x.txt", "x.txt")

    r = admin_client.post("/api/settings/storage/migrate", json={"delete_source": True})
    assert r.status_code == 200
    data = r.json()
    assert data["migrated"] == 1 and data["failed"] == 0
    assert uploaded.get("kontakte/a/x.txt") == b"hallo"     # ans Ziel kopiert
    assert "kontakte/a/x.txt" not in store                  # Quelle gelöscht
    db_session.refresh(att)
    assert att.storage_provider == "onedrive"               # Provider aktualisiert


def test_migrate_erfordert_admin(auth_client):
    r = auth_client.post("/api/settings/storage/migrate", json={})
    assert r.status_code == 403


# ── Re-Path: Ordnerstruktur auf Kundennamen ───────────────────────────────────
def _mk_named_attachment(db, storage_key, contact_name):
    from app.models.attachment import Attachment
    import uuid
    a = Attachment(
        entity_type="kontakte", entity_id=uuid.uuid4(), type="file",
        storage_key=storage_key, storage_provider="minio",
        filename="x.txt", display_name="x.txt", mimetype="text/plain",
        contact_name=contact_name,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def test_repath_verschiebt_in_namensordner(admin_client, db_session, monkeypatch):
    from app.services import storage_service

    store = {}
    moved_from = []

    class FakeProv:
        def download(self, key): return b"data", "text/plain"
        def upload(self, key, data, mime): store[key] = data
        def delete(self, key): moved_from.append(key)

    monkeypatch.setattr(storage_service, "build_provider_for", lambda backend, db=None: FakeProv())

    a = _mk_named_attachment(db_session, "kontakte/some-uuid/x.txt", "WWInterface GmbH")

    # Status meldet 1 offene Datei
    st = admin_client.get("/api/settings/storage/repath-status").json()
    assert st["pending"] == 1

    r = admin_client.post("/api/settings/storage/repath")
    assert r.status_code == 200
    data = r.json()
    assert data["moved"] == 1 and data["failed"] == 0
    assert "kontakte/WWInterface GmbH/x.txt" in store       # ans Namensziel kopiert
    assert "kontakte/some-uuid/x.txt" in moved_from          # alte Datei gelöscht
    db_session.refresh(a)
    assert a.storage_key == "kontakte/WWInterface GmbH/x.txt"


def test_repath_erfordert_admin(auth_client):
    r = auth_client.post("/api/settings/storage/repath")
    assert r.status_code == 403
