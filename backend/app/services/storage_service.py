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

def _safe_segment(s: str) -> str:
    """Ordner-/Dateinamen für Cloud-Speicher säubern (kein '/','\\', keine
    Rand-Punkte). Erlaubt sind Buchstaben/Ziffern und gängige Zeichen."""
    s = "".join(c for c in (s or "") if c.isalnum() or c in "._- ()&+#").strip()
    return s.strip(" .")


def folder_name_for(db, entity_id, fallback: str = None) -> str:
    """Menschenlesbares Ordnersegment für eine Entität (z.B. Kundenname).
    Reihenfolge: fallback (z.B. denormalisierter contact_name) → Stammdaten-
    display_name → als letzte Rückfalloption die ID."""
    seg = _safe_segment(fallback)
    if not seg and db is not None and entity_id is not None:
        try:
            from app.models.masterdata import EntityRecord
            rec = db.query(EntityRecord).filter(EntityRecord.id == entity_id).first()
            seg = _safe_segment(rec.display_name) if rec else ""
        except Exception:
            seg = ""
    return seg or str(entity_id)


def build_storage_key(entity_type: str, entity_id: str, filename: str, db=None) -> str:
    """Einheitlicher Pfad: kontakte/<Kundenname>/dokument.pdf
    Ohne db (oder ohne auflösbaren Namen) fällt der Ordner auf die ID zurück."""
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    folder = folder_name_for(db, entity_id)
    return f"{entity_type}/{folder}/{safe_name}"


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

    drive_type      'personal'    → /users/{user}/drive/root  (persönliches OneDrive
                                     eines Benutzers; App-only kann NICHT /me nutzen,
                                     daher UPN/E-Mail via `user` nötig)
                    'sharepoint'  → /sites/{site_id}/drive/root
    tenant_id       Azure Tenant-ID
    client_id       Azure App-Client-ID
    client_secret   Azure App-Secret
    site_id         Nur für drive_type='sharepoint'
    user            Nur für drive_type='personal': UPN/E-Mail des OneDrive-Besitzers
    root_folder     Übergeordneter Ordner in OneDrive, z.B. 'DeineZeit'
    """

    _token_cache: dict = {}
    _token_lock = __import__('threading').Lock()

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 drive_type: str = 'personal', site_id: str = '',
                 root_folder: str = 'DeineZeit', user: str = ''):
        self.tenant_id     = tenant_id
        self.client_id     = client_id
        self.client_secret = client_secret
        self.drive_type    = drive_type
        self.site_id       = site_id.strip('/')
        self.user          = (user or '').strip().strip('/')
        # OneDrive/Graph nutzt '/'-Pfade; Windows-Backslashes tolerieren und normalisieren
        self.root_folder   = (root_folder or '').replace('\\', '/').strip().strip('/')

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

    def _drive_prefix(self) -> str:
        """Graph-Basis bis '/drive' – je nach Laufwerkstyp.
        personal → /users/{upn}/drive (App-only kann /me nicht nutzen)."""
        if self.drive_type == 'sharepoint' and self.site_id:
            return f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive"
        if self.drive_type == 'personal' and self.user:
            return f"https://graph.microsoft.com/v1.0/users/{self.user}/drive"
        return "https://graph.microsoft.com/v1.0/me/drive"

    def _drive_base(self) -> str:
        return f"{self._drive_prefix()}/root"

    def _norm_key(self, storage_key: str) -> str:
        return (storage_key or '').replace('\\', '/').lstrip('/')

    def _item_url(self, storage_key: str) -> str:
        # Vollständiger Pfad unter dem Laufwerk; OHNE abschließenden ':'
        # (Navigationssuffixe wie ':/content' werden vom Aufrufer angehängt).
        path = f"{self.root_folder}/{self._norm_key(storage_key)}".strip('/')
        return f"{self._drive_base()}:/{path}"

    def _ensure_path(self, folder_path: str) -> None:
        """Legt jedes Segment eines (absoluten) Ordnerpfads unter dem Laufwerk an.
        Bereits vorhandene Ordner ⇒ 409, wird ignoriert. Best-effort."""
        import requests as req
        parts = [p for p in (folder_path or '').replace('\\', '/').strip('/').split('/') if p]
        for i in range(len(parts)):
            parent = '/'.join(parts[:i])
            child  = parts[i]
            url = (f"{self._drive_base()}:/{parent}:/children" if parent
                   else f"{self._drive_base()}/children")
            try:
                req.post(url, headers={**self._headers(), "Content-Type": "application/json"},
                         json={"name": child, "folder": {},
                               "@microsoft.graph.conflictBehavior": "fail"},
                         timeout=10)
            except Exception:
                pass

    def upload(self, storage_key: str, data: bytes, mimetype: str) -> None:
        import requests as req
        key = self._norm_key(storage_key)
        full = f"{self.root_folder}/{key}".strip('/')
        folder = '/'.join(full.split('/')[:-1])   # kompletter Zielordner inkl. root_folder
        if folder:
            self._ensure_path(folder)
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

    def item_meta(self, storage_key: str) -> Optional[dict]:
        """Metadaten (u.a. 'webUrl', 'size') einer Datei; None wenn nicht vorhanden."""
        import requests as req
        r = req.get(self._item_url(storage_key), headers=self._headers(), timeout=15)
        return r.json() if r.status_code == 200 else None

    def list_children(self, subpath: str = "") -> list:
        """Listet die Dateien/Ordner unter root_folder[/subpath].
        Gibt Graph-Items zurück (u.a. 'name', 'lastModifiedDateTime')."""
        import requests as req
        path = f"{self.root_folder}/{subpath}".strip('/')
        url = f"{self._drive_base()}:/{path}:/children" if path else f"{self._drive_base()}/children"
        resp = req.get(url, headers=self._headers(), timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json().get("value", [])

    def test_connection(self) -> dict:
        import requests as req
        try:
            self._get_token()
        except Exception as e:
            return {"ok": False, "message": f"Token-Fehler: {e}"}
        try:
            if self.drive_type == 'personal' and not self.user:
                return {"ok": False, "message": "Persönliches OneDrive: bitte Benutzer (E-Mail/UPN) angeben – App-only kann /me nicht verwenden"}
            base_url = self._drive_prefix()
            resp = req.get(base_url, headers=self._headers(), timeout=10)
            if resp.status_code == 403:
                return {"ok": False, "message": "Keine Berechtigung – Files.ReadWrite.All in Azure prüfen"}
            if resp.status_code != 200:
                detail = ""
                try:
                    detail = resp.json().get("error", {}).get("message", "")
                except Exception:
                    pass
                return {"ok": False, "message": f"Graph API: HTTP {resp.status_code}" + (f" – {detail}" if detail else "")}
            name = resp.json().get("name", "OneDrive")
            # (Ggf. verschachtelten) Root-Ordner anlegen falls nötig
            chk = req.get(f"{self._drive_base()}:/{self.root_folder}", headers=self._headers(), timeout=10)
            if chk.status_code == 404:
                self._ensure_path(self.root_folder)
                # Erfolg der Anlage verifizieren
                chk2 = req.get(f"{self._drive_base()}:/{self.root_folder}", headers=self._headers(), timeout=10)
                if chk2.status_code != 200:
                    detail = ""
                    try:
                        detail = chk2.json().get("error", {}).get("message", "")
                    except Exception:
                        pass
                    return {"ok": False, "message": f"Ordner '{self.root_folder}' konnte nicht angelegt werden (HTTP {chk2.status_code}{f' – {detail}' if detail else ''})"}
                return {"ok": True, "message": f"Verbunden mit '{name}' – Ordner '{self.root_folder}' angelegt"}
            if chk.status_code != 200:
                return {"ok": False, "message": f"Ordner-Prüfung fehlgeschlagen: HTTP {chk.status_code}"}
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


_SETTINGS_KEYS = [
    "storage_backend",
    "webdav_url", "webdav_user", "webdav_password", "webdav_root_folder",
    "onedrive_use_graph_creds", "onedrive_tenant_id", "onedrive_client_id",
    "onedrive_client_secret", "onedrive_drive_type", "onedrive_site_id",
    "onedrive_user", "onedrive_root_folder",
    "ms_tenant_id", "ms_client_id", "ms_client_secret",
]


def _load_storage_settings(db) -> dict:
    if db is None:
        return {}
    try:
        from app.models.settings import Setting
        rows = db.query(Setting).filter(Setting.key.in_(_SETTINGS_KEYS)).all()
        return {r.key: r.value for r in rows}
    except Exception:
        return {}


def current_backend(db=None) -> str:
    """Aktuell konfigurierter Speicher-Backend-Name (für 'welcher Provider beim Upload')."""
    return (_load_storage_settings(db).get("storage_backend") or "minio")


def _build_provider(settings: dict, backend: str = None) -> StorageProvider:
    backend = backend or settings.get("storage_backend", "minio")
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
            user          = settings.get("onedrive_user", ""),
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

    settings = _load_storage_settings(db)
    provider = _build_provider(settings)
    with _cache_lock:
        _cached_provider = provider
        _cache_expires   = now + _CACHE_TTL

    return provider


def build_provider_for(backend: str, db=None) -> StorageProvider:
    """Baut (ungecacht) einen Provider für EINEN bestimmten Backend-Namen.
    Für Down-/Vorschau/Löschen anhand des je Datei gespeicherten Providers –
    unabhängig vom aktuell aktiven Speicher (Mischbetrieb)."""
    if not backend:
        return get_provider(db)
    return _build_provider(_load_storage_settings(db), backend=backend)


# ── Konsolidierung: alle Dateien auf den aktiven Provider umziehen ─────────────

def migration_status(db) -> dict:
    """Übersicht: aktiver Provider, Verteilung der Dateien je Provider, offene Anzahl."""
    from app.models.attachment import Attachment
    active = current_backend(db)
    rows = db.query(Attachment).filter(
        Attachment.type == "file", Attachment.storage_key.isnot(None)).all()
    counts: dict = {}
    pending = 0
    for a in rows:
        prov = a.storage_provider or "minio"
        counts[prov] = counts.get(prov, 0) + 1
        if prov != active:
            pending += 1
    return {"active": active, "counts": counts, "pending": pending, "total": len(rows)}


def migrate_all_to_active(db, delete_source: bool = False) -> dict:
    """Kopiert alle Dateien, die NICHT beim aktiven Provider liegen, dorthin um.
    Pro Datei: laden (Quell-Provider) → hochladen (Ziel) → verifizieren →
    storage_provider aktualisieren → optional Quelle löschen. Fehler je Datei
    werden gesammelt, der Rest läuft weiter."""
    from app.models.attachment import Attachment
    active = current_backend(db)
    target = build_provider_for(active, db)

    rows = db.query(Attachment).filter(
        Attachment.type == "file", Attachment.storage_key.isnot(None)).all()

    migrated = skipped = failed = 0
    errors: list = []
    for a in rows:
        src_name = a.storage_provider or "minio"
        if src_name == active:
            skipped += 1
            continue
        label = a.filename or a.storage_key
        try:
            src = build_provider_for(src_name, db)
            data, mime = src.download(a.storage_key)
            target.upload(a.storage_key, data, mime or a.mimetype or "application/octet-stream")
            # Verifizieren, dass die Datei am Ziel liegt (soweit der Provider das kann)
            if isinstance(target, OneDriveProvider) and target.item_meta(a.storage_key) is None:
                raise RuntimeError("Zieldatei nach Upload nicht auffindbar")
            a.storage_provider = active
            db.add(a)
            db.flush()
            if delete_source:
                try:
                    src.delete(a.storage_key)
                except Exception:
                    pass
            migrated += 1
        except Exception as e:
            failed += 1
            errors.append(f"{label}: {e}")
    db.commit()
    return {"ok": failed == 0, "active": active,
            "migrated": migrated, "skipped": skipped, "failed": failed,
            "errors": errors[:25]}


# ── Ordnerstruktur auf Kundennamen umstellen (Re-Path) ────────────────────────

def _desired_key(db, att) -> str:
    """Gewünschter storage_key mit Namensordner statt ID im 2. Pfadsegment.
    Restlicher Pfad (Unterordner, Dateiname) bleibt erhalten."""
    if not att.storage_key:
        return None
    parts = att.storage_key.split('/')
    if len(parts) < 3:
        return att.storage_key
    parts[1] = folder_name_for(db, att.entity_id, att.contact_name)
    return '/'.join(parts)


def repath_status(db) -> dict:
    """Wie viele Dateien liegen noch unter einem ID-Ordner (statt Namensordner)."""
    from app.models.attachment import Attachment
    rows = db.query(Attachment).filter(
        Attachment.type == "file", Attachment.storage_key.isnot(None)).all()
    pending = sum(1 for a in rows if _desired_key(db, a) != a.storage_key)
    return {"pending": pending, "total": len(rows)}


def repath_all_to_names(db, delete_source: bool = True) -> dict:
    """Verschiebt Dateien von ID-Ordnern in Namensordner (im jeweiligen Speicher)
    und aktualisiert storage_key (+ verknüpfte Beleg-Pfade). Best-effort je Datei."""
    from app.models.attachment import Attachment
    from app.models.invoice import InvoiceAttachment

    rows = db.query(Attachment).filter(
        Attachment.type == "file", Attachment.storage_key.isnot(None)).all()

    moved = skipped = failed = 0
    errors: list = []
    for a in rows:
        new_key = _desired_key(db, a)
        if not new_key or new_key == a.storage_key:
            skipped += 1
            continue
        label = a.filename or a.storage_key
        try:
            prov = build_provider_for(a.storage_provider or "minio", db)
            data, mime = prov.download(a.storage_key)
            prov.upload(new_key, data, mime or a.mimetype or "application/octet-stream")
            if isinstance(prov, OneDriveProvider) and prov.item_meta(new_key) is None:
                raise RuntimeError("Zieldatei nach Verschieben nicht auffindbar")
            old_key = a.storage_key
            # Verknüpfte Beleg-Anhänge (Verträge) mitziehen
            db.query(InvoiceAttachment).filter(
                InvoiceAttachment.datacenter_id == a.id).update(
                {"file_path": new_key}, synchronize_session=False)
            a.storage_key = new_key
            db.add(a)
            db.flush()
            if delete_source:
                try:
                    prov.delete(old_key)
                except Exception:
                    pass
            moved += 1
        except Exception as e:
            failed += 1
            errors.append(f"{label}: {e}")
    db.commit()
    return {"ok": failed == 0, "moved": moved, "skipped": skipped,
            "failed": failed, "errors": errors[:25]}


# ── Kompatibilitätsfunktionen (bestehende call-sites bleiben unverändert) ─────

def upload_file(storage_key: str, data: bytes, mimetype: str, db=None, backend: str = None) -> None:
    provider = build_provider_for(backend, db) if backend else get_provider(db)
    provider.upload(storage_key, data, mimetype)


def download_file(storage_key: str, db=None, backend: str = None) -> Tuple[bytes, str]:
    provider = build_provider_for(backend, db) if backend else get_provider(db)
    return provider.download(storage_key)


def delete_file(storage_key: str, db=None, backend: str = None) -> None:
    provider = build_provider_for(backend, db) if backend else get_provider(db)
    provider.delete(storage_key)


def ensure_bucket(db=None) -> None:
    """Rückwärtskompatibel – nur für MinIO relevant."""
    p = get_provider(db)
    if isinstance(p, MinioProvider):
        p._ensure_bucket()
