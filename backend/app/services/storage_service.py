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
                    "storage_backend", "webdav_url", "webdav_user",
                    "webdav_password", "webdav_root_folder",
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
