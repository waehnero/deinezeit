"""
Storage Service – Provider-Abstraktion

Unterstützte Provider:
  minio   – lokaler MinIO Objektspeicher (Standard)
  webdav  – WebDAV-kompatibler Cloudspeicher (Nextcloud, SeaDrive, ...)
"""
import os
import io
import secrets
import time
import threading
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Optional, Tuple

from minio import Minio
from minio.error import S3Error


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def build_storage_key(entity_type: str, entity_id: str, filename: str) -> str:
    """Einheitlicher Pfad: z.B. kontakte/uuid/dokument.pdf"""
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    return f"{entity_type}/{entity_id}/{safe_name}"


def generate_share_token() -> str:
    return secrets.token_urlsafe(32)


# ── Provider-Interface ────────────────────────────────────────────────────────

class StorageProvider(ABC):
    @abstractmethod
    def upload(self, storage_key: str, data: bytes, mimetype: str) -> None: ...

    @abstractmethod
    def download(self, storage_key: str) -> Tuple[bytes, str]: ...

    @abstractmethod
    def delete(self, storage_key: str) -> None: ...

    @abstractmethod
    def test_connection(self) -> dict: ...


# ── MinIO Provider ────────────────────────────────────────────────────────────

class MinioProvider(StorageProvider):
    def __init__(self):
        self.endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
        self.access   = os.environ.get("MINIO_ROOT_USER", "minioadmin")
        self.secret   = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
        self.bucket   = os.environ.get("MINIO_BUCKET", "deinezeit-files")

    def _client(self) -> Minio:
        return Minio(self.endpoint, access_key=self.access, secret_key=self.secret, secure=False)

    def _ensure_bucket(self):
        c = self._client()
        if not c.bucket_exists(self.bucket):
            c.make_bucket(self.bucket)

    def upload(self, storage_key: str, data: bytes, mimetype: str) -> None:
        c = self._client()
        self._ensure_bucket()
        c.put_object(self.bucket, storage_key, io.BytesIO(data),
                     length=len(data), content_type=mimetype)

    def download(self, storage_key: str) -> Tuple[bytes, str]:
        c = self._client()
        response = c.get_object(self.bucket, storage_key)
        try:
            data = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream")
        finally:
            response.close()
            response.release_conn()
        return data, content_type

    def delete(self, storage_key: str) -> None:
        c = self._client()
        try:
            c.remove_object(self.bucket, storage_key)
        except S3Error:
            pass

    def test_connection(self) -> dict:
        try:
            self._client().list_buckets()
            return {"ok": True, "message": "MinIO erreichbar"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── WebDAV Provider (Nextcloud / SeaDrive / beliebig) ─────────────────────────

class WebDavProvider(StorageProvider):
    """
    Generischer WebDAV-Provider.

    base_url    Basis-URL des WebDAV-Endpunkts, z.B.:
                  Nextcloud : https://cloud.example.com/remote.php/dav/files/USERNAME
                  SeaDrive  : https://seadrive.example.com/seafdav
    username    WebDAV-Benutzername
    password    WebDAV-Passwort (oder App-Passwort)
    root_folder Übergeordneter Ordner in der Cloud, z.B. "DeineZeit"
    """

    def __init__(self, base_url: str, username: str, password: str,
                 root_folder: str = "DeineZeit"):
        self.base_url    = base_url.rstrip('/')
        self.username    = username
        self.password    = password
        self.root_folder = root_folder.strip('/')

    def _auth(self):
        return (self.username, self.password)

    def _url(self, path: str = "") -> str:
        base = f"{self.base_url}/{self.root_folder}"
        if path:
            return f"{base}/{path.lstrip('/')}"
        return base

    def _ensure_dirs(self, storage_key: str) -> None:
        """Legt alle übergeordneten Ordner via MKCOL an (ignoriert 405 = bereits vorhanden)."""
        import requests
        parts = storage_key.split('/')
        # Root-Ordner
        requests.request("MKCOL", self._url(), auth=self._auth(), timeout=10)
        # Unterordner
        for i in range(len(parts) - 1):
            folder = '/'.join(parts[:i + 1])
            requests.request("MKCOL", self._url(folder), auth=self._auth(), timeout=10)

    def upload(self, storage_key: str, data: bytes, mimetype: str) -> None:
        import requests
        self._ensure_dirs(storage_key)
        resp = requests.put(
            self._url(storage_key), data=data, auth=self._auth(),
            headers={"Content-Type": mimetype}, timeout=120,
        )
        resp.raise_for_status()

    def download(self, storage_key: str) -> Tuple[bytes, str]:
        import requests
        resp = requests.get(self._url(storage_key), auth=self._auth(), timeout=60)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "application/octet-stream")
        return resp.content, ct

    def delete(self, storage_key: str) -> None:
        import requests
        try:
            requests.delete(self._url(storage_key), auth=self._auth(), timeout=15)
        except Exception:
            pass

    def test_connection(self) -> dict:
        import requests
        try:
            resp = requests.request(
                "PROPFIND", self._url(), auth=self._auth(),
                headers={"Depth": "0"}, timeout=10,
            )
            if resp.status_code in (200, 207):
                return {"ok": True, "message": f"Verbunden – Ordner '{self.root_folder}' gefunden"}
            if resp.status_code == 404:
                mk = requests.request("MKCOL", self._url(), auth=self._auth(), timeout=10)
                if mk.status_code in (200, 201, 405):
                    return {"ok": True, "message": f"Verbunden – Ordner '{self.root_folder}' angelegt"}
                return {"ok": False, "message": f"Ordner konnte nicht angelegt werden (HTTP {mk.status_code})"}
            if resp.status_code == 401:
                return {"ok": False, "message": "Authentifizierung fehlgeschlagen – Benutzername/Passwort prüfen"}
            return {"ok": False, "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}




# ── OneDrive Provider (Microsoft Graph API) ───────────────────────────────────

class OneDriveProvider(StorageProvider):
    """
    Microsoft OneDrive / SharePoint via Graph API.

    Authentifizierung: Client Credentials Flow (App-Berechtigung Files.ReadWrite.All)

    drive_type      'personal'    → /me/drive/root  (persönliches OneDrive)
                    'sharepoint'  → /sites/{site_id}/drive/root
    tenant_id       Azure Tenant-ID
    client_id       Azure App-Client-ID
    client_secret   Azure App-Secret
    site_id         Nur für drive_type='sharepoint'
    root_folder     Übergeordneter Ordner in OneDrive, z.B. 'DeineZeit'
    """

    _token_cache: dict = {}
    _token_lock = __import__('threading').Lock()

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 drive_type: str = 'personal', site_id: str = '',
                 root_folder: str = 'DeineZeit'):
        self.tenant_id     = tenant_id
        self.client_id     = client_id
        self.client_secret = client_secret
        self.drive_type    = drive_type
        self.site_id       = site_id.strip('/')
        self.root_folder   = root_folder.strip('/')

    def _get_token(self) -> str:
        import requests as req, time
        key = (self.tenant_id, self.client_id)
        with OneDriveProvider._token_lock:
            cached = OneDriveProvider._token_cache.get(key)
            if cached and cached[1] > time.monotonic() + 60:
                return cached[0]
        resp = req.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id,
                  "client_secret": self.client_secret,
                  "scope": "https://graph.microsoft.com/.default"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_at = time.monotonic() + int(data.get("expires_in", 3600))
        with OneDriveProvider._token_lock:
            OneDriveProvider._token_cache[key] = (token, expires_at)
        return token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _drive_base(self) -> str:
        if self.drive_type == 'sharepoint' and self.site_id:
            return f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive/root"
        return "https://graph.microsoft.com/v1.0/me/drive/root"

    def _item_url(self, storage_key: str) -> str:
        path = f"{self.root_folder}/{storage_key}".lstrip('/')
        return f"{self._drive_base()}:/{path}:"

    def _ensure_folder(self, folder_path: str) -> None:
        import requests as req
        parts = folder_path.strip('/').split('/')
        for i in range(len(parts)):
            parent_path = '/'.join(parts[:i])
            child = parts[i]
            if parent_path:
                url = f"{self._drive_base()}:/{self.root_folder}/{parent_path}:/children"
            else:
                url = f"{self._drive_base()}:/{self.root_folder}:/children"
            try:
                req.post(url, headers={**self._headers(), "Content-Type": "application/json"},
                         json={"name": child, "folder": {},
                               "@microsoft.graph.conflictBehavior": "fail"},
                         timeout=10)
            except Exception:
                pass

    def upload(self, storage_key: str, data: bytes, mimetype: str) -> None:
        import requests as req
        parts = storage_key.split('/')
        if len(parts) > 1:
            self._ensure_folder('/'.join(parts[:-1]))
        resp = req.put(
            f"{self._item_url(storage_key)}:/content",
            headers={**self._headers(), "Content-Type": mimetype},
            data=data, timeout=120,
        )
        resp.raise_for_status()

    def download(self, storage_key: str) -> Tuple[bytes, str]:
        import requests as req
        meta = req.get(self._item_url(storage_key), headers=self._headers(), timeout=15)
        meta.raise_for_status()
        dl_url = meta.json().get("@microsoft.graph.downloadUrl")
        resp = req.get(dl_url or f"{self._item_url(storage_key)}:/content",
                       headers=(None if dl_url else self._headers()), timeout=60)
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

    def delete(self, storage_key: str) -> None:
        import requests as req
        try:
            req.delete(self._item_url(storage_key), headers=self._headers(), timeout=15)
        except Exception:
            pass

    def test_connection(self) -> dict:
        import requests as req
        try:
            self._get_token()
        except Exception as e:
            return {"ok": False, "message": f"Token-Fehler: {e}"}
        try:
            base_url = (f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive"
                        if self.drive_type == 'sharepoint' and self.site_id
                        else "https://graph.microsoft.com/v1.0/me/drive")
            resp = req.get(base_url, headers=self._headers(), timeout=10)
            if resp.status_code == 403:
                return {"ok": False, "message": "Keine Berechtigung – Files.ReadWrite.All in Azure prüfen"}
            if resp.status_code != 200:
                return {"ok": False, "message": f"Graph API: HTTP {resp.status_code}"}
            name = resp.json().get("name", "OneDrive")
            # Root-Ordner anlegen falls nötig
            chk = req.get(f"{self._drive_base()}:/{self.root_folder}:", headers=self._headers(), timeout=10)
            if chk.status_code == 404:
                mk = req.post(f"{self._drive_base()}/children",
                              headers={**self._headers(), "Content-Type": "application/json"},
                              json={"name": self.root_folder, "folder": {},
                                    "@microsoft.graph.conflictBehavior": "fail"},
                              timeout=10)
                msg = "angelegt" if mk.status_code in (200, 201, 409) else f"HTTP {mk.status_code}"
                return {"ok": True, "message": f"Verbunden mit '{name}' – Ordner '{self.root_folder}' {msg}"}
            return {"ok": True, "message": f"Verbunden mit '{name}' – Ordner '{self.root_folder}' gefunden"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── Provider-Cache ────────────────────────────────────────────────────────────

_cache_lock: threading.Lock     = threading.Lock()
_cached_provider: Optional[StorageProvider] = None
_cache_expires:   float         = 0.0
_CACHE_TTL:       float         = 30.0   # Sekunden


def invalidate_provider_cache() -> None:
    """Nach Änderung der Storage-Settings aufrufen."""
    global _cached_provider, _cache_expires
    with _cache_lock:
        _cached_provider = None
        _cache_expires   = 0.0


def _build_provider(settings: dict) -> StorageProvider:
    backend = settings.get("storage_backend", "minio")
    if backend in ("webdav", "nextcloud", "seadrive"):
        return WebDavProvider(
            base_url    = settings.get("webdav_url", ""),
            username    = settings.get("webdav_user", ""),
            password    = settings.get("webdav_password", ""),
            root_folder = settings.get("webdav_root_folder", "DeineZeit"),
        )
    if backend == "onedrive":
        # Eigene Credentials oder Graph-Mail-Credentials wiederverwenden
        use_graph = settings.get("onedrive_use_graph_creds", "false") == "true"
        return OneDriveProvider(
            tenant_id     = settings.get("ms_tenant_id" if use_graph else "onedrive_tenant_id", ""),
            client_id     = settings.get("ms_client_id" if use_graph else "onedrive_client_id", ""),
            client_secret = settings.get("ms_client_secret" if use_graph else "onedrive_client_secret", ""),
            drive_type    = settings.get("onedrive_drive_type", "personal"),
            site_id       = settings.get("onedrive_site_id", ""),
            root_folder   = settings.get("onedrive_root_folder", "DeineZeit"),
        )
    return MinioProvider()


def get_provider(db=None) -> StorageProvider:
    """Gibt den konfigurierten Provider zurück (gecacht für 30 s)."""
    global _cached_provider, _cache_expires

    now = time.monotonic()
    with _cache_lock:
        if _cached_provider is not None and now < _cache_expires:
            return _cached_provider

    settings: dict = {}
    if db is not None:
        try:
            from app.models.settings import Setting
            rows = db.query(Setting).filter(
                Setting.key.in_([
                    "storage_backend",
                    "webdav_url", "webdav_user", "webdav_password", "webdav_root_folder",
                    "onedrive_use_graph_creds", "onedrive_tenant_id", "onedrive_client_id",
                    "onedrive_client_secret", "onedrive_drive_type", "onedrive_site_id",
                    "onedrive_root_folder",
                    "ms_tenant_id", "ms_client_id", "ms_client_secret",
                ])
            ).all()
            settings = {r.key: r.value for r in rows}
        except Exception:
            pass

    provider = _build_provider(settings)
    with _cache_lock:
        _cached_provider = provider
        _cache_expires   = now + _CACHE_TTL

    return provider


# ── Kompatibilitätsfunktionen (bestehende call-sites bleiben unverändert) ─────

def upload_file(storage_key: str, data: bytes, mimetype: str, db=None) -> None:
    get_provider(db).upload(storage_key, data, mimetype)


def download_file(storage_key: str, db=None) -> Tuple[bytes, str]:
    return get_provider(db).download(storage_key)


def delete_file(storage_key: str, db=None) -> None:
    get_provider(db).delete(storage_key)


def ensure_bucket(db=None) -> None:
    """Rückwärtskompatibel – nur für MinIO relevant."""
    p = get_provider(db)
    if isinstance(p, MinioProvider):
        p._ensure_bucket()
