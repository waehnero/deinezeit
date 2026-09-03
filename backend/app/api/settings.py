import os
import io
import re as _re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from PIL import Image

from app.db.base import get_db
from app.models.settings import Setting
from app.models.user import User, UserRole
from app.models.masterdata import EntityType, EntityRecord, FieldDefinition
from app.schemas.settings import SettingsResponse, SettingsUpdate, TestEmailRequest
from app.api.deps import get_current_user, require_admin
from app.core import zeit

router = APIRouter(prefix="/settings", tags=["Einstellungen"])

STATIC_DIR = "/app/static"
LOGO_PATH  = os.path.join(STATIC_DIR, "logo")


def _load(db: Session) -> dict:
    rows = db.query(Setting).all()
    return {r.key: r.value for r in rows}


def _save(db: Session, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.now(timezone.utc)))
    db.commit()


# Muster, die in einem SVG auf ausführbaren Inhalt hindeuten. Logo und Favicon
# werden unter /api/static unter der Adresse der Anwendung ausgeliefert; ein
# SVG mit Skript liefe dort mit den Rechten des Betrachters. Hochladen darf
# zwar nur ein Administrator, aber ein unbedacht aus dem Netz übernommenes
# Logo soll trotzdem nicht zur Hintertür werden (Audit SEC-013).
_SVG_AKTIV = _re.compile(
    rb"<\s*script|<\s*foreignObject|<\s*iframe|<\s*embed|<\s*object"
    rb"|\bon[a-z]+\s*=|javascript\s*:|<\s*use[^>]+href\s*=\s*[\"']?\s*(?:https?:|//)",
    _re.IGNORECASE,
)


def _svg_pruefen(raw: bytes) -> None:
    """Bricht mit 400 ab, wenn das SVG Skripte oder Fremdinhalte einbettet."""
    if _SVG_AKTIV.search(raw):
        raise HTTPException(
            400, "Das SVG enthält Skripte oder eingebettete Fremdinhalte und "
                 "wird nicht angenommen. Bitte ein bereinigtes SVG oder PNG verwenden.")


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _generate_logo_variants(original_bytes: bytes, ext: str) -> tuple[bytes, bytes, bytes]:
    """
    Generiert drei Logo-Varianten aus dem Original.
    Gibt zurück: (original_bytes, header_png_bytes, favicon_png_bytes)
    """
    img = Image.open(io.BytesIO(original_bytes))

    # RGBA sicherstellen (Transparenz)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # ── Variante 1: Header (600×120, zentriert, transparenter Hintergrund) ──
    header = Image.new('RGBA', (600, 120), (0, 0, 0, 0))
    thumb = img.copy()
    thumb.thumbnail((580, 110), Image.LANCZOS)   # etwas kleiner für Rand
    x = (600 - thumb.width) // 2
    y = (120 - thumb.height) // 2
    header.paste(thumb, (x, y), thumb)

    # ── Variante 2: Favicon (32×32, zentriert) ────────────────────────────
    favicon = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    fav = img.copy()
    fav.thumbnail((32, 32), Image.LANCZOS)
    x = (32 - fav.width) // 2
    y = (32 - fav.height) // 2
    favicon.paste(fav, (x, y), fav)

    return original_bytes, _pil_to_png_bytes(header), _pil_to_png_bytes(favicon)


# ── Settings lesen ────────────────────────────────────────────────────────────
#
# Der Endpunkt ist bewusst ohne Anmeldung erreichbar: Die Anmeldeseite braucht
# Firmenname, Farben und Logo, bevor jemand angemeldet ist. Bis 02.09.2026
# bekam ein Unbekannter darüber aber die komplette Konfiguration (SMTP-Server
# und -Benutzer, Microsoft-Tenant, WebDAV-Adresse, Backup-Pfad …) — alles bis
# auf die Passwörter (Audit SEC-004). Jetzt gilt: ohne Anmeldung oder ohne
# Administratorrecht nur die Darstellungsfelder; die vollständige
# Konfiguration sieht nur ein Administrator (die Einstellungsseite).

#: Felder, die jeder sehen darf — auch vor der Anmeldung.
OEFFENTLICHE_FELDER = frozenset({
    "company_name", "app_subtitle", "color_theme", "design_template",
    "brand_color", "custom_text_color", "custom_bg_color", "custom_surface_color",
    "logo_url", "logo_header_url", "logo_favicon_url", "sidebar_logo_source",
})

#: Felder, die nie nach außen gehen — auch nicht an Administratoren. Sie werden
#: nur gesetzt, nie gelesen (die Einstellungsseite zeigt ein leeres Feld).
GEHEIME_FELDER = frozenset({
    "smtp_password", "ms_client_secret", "webdav_password",
    "onedrive_client_secret", "backup_onedrive_client_secret",
})

_optional_bearer = HTTPBearer(auto_error=False)


def _ist_admin(request: Request, db: Session,
               credentials: Optional[HTTPAuthorizationCredentials]) -> bool:
    """Prüft still, ob ein gültiger Administrator-Token mitkommt.

    Kein 401 bei fehlendem oder ungültigem Token — der Endpunkt muss für die
    Anmeldeseite weiterhin ohne Anmeldung antworten."""
    if credentials is None:
        return False
    try:
        user = get_current_user(request, credentials, db)
    except HTTPException:
        return False
    return user.role == UserRole.admin


@router.get("", response_model=SettingsResponse)
def get_settings(
    request: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
):
    data = _load(db)
    if _ist_admin(request, db, credentials):
        erlaubt = set(SettingsResponse.model_fields) - GEHEIME_FELDER
    else:
        erlaubt = OEFFENTLICHE_FELDER
    werte = {k: (data.get(k, '') if k in erlaubt else '')
             for k in SettingsResponse.model_fields}
    return SettingsResponse(**werte)


# ── Admin: Settings aktualisieren ────────────────────────────────────────────
@router.put("")
def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _save(db, key, str(value))

    # backup.cfg aktualisieren wenn Backup-Einstellungen geändert wurden
    backup_keys = {"backup_dir", "backup_keep_days", "backup_schedule_time"}
    if updates.keys() & backup_keys:
        cfg_path = "/opt/deinezeit/backup.cfg"
        all_settings = _load(db)
        backup_dir   = all_settings.get("backup_dir", "")
        keep_days    = all_settings.get("backup_keep_days", "30")
        schedule     = all_settings.get("backup_schedule_time", "02:00")
        if backup_dir:
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(f"BACKUP_DIR={backup_dir}\n")
                    f.write(f"KEEP_DAYS={keep_days}\n")
                    f.write(f"BACKUP_SCHEDULE_TIME={schedule}\n")
            except Exception:
                pass  # Kein Fehler wenn Datei nicht beschreibbar (z.B. Produktionsserver)

    return {"ok": True}


# ── Admin: Logo hochladen (generiert 3 Varianten automatisch) ────────────────
@router.post("/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    os.makedirs(LOGO_PATH, exist_ok=True)

    ext = os.path.splitext(file.filename or "logo.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        raise HTTPException(400, "Nur PNG, JPG, SVG und WebP erlaubt")

    raw_bytes = file.file.read()

    # SVGs können nicht mit Pillow verarbeitet werden → nur Original speichern
    if ext == ".svg":
        _svg_pruefen(raw_bytes)
        orig_path = os.path.join(LOGO_PATH, f"logo_original{ext}")
        # Alte Logos entfernen
        for old in os.listdir(LOGO_PATH):
            try:
                os.remove(os.path.join(LOGO_PATH, old))
            except Exception:
                pass
        with open(orig_path, "wb") as f:
            f.write(raw_bytes)

        # Cache-Buster: Dateiname bleibt gleich, daher würde der Browser sonst
        # das alte gecachte Bild weiter anzeigen
        v = int(zeit.jetzt().timestamp())
        logo_url = f"/api/static/logo/logo_original{ext}?v={v}"
        _save(db, "logo_url",        logo_url)
        _save(db, "logo_header_url", logo_url)
        _save(db, "logo_favicon_url", logo_url)
        return {"logo_url": logo_url, "logo_header_url": logo_url, "logo_favicon_url": logo_url}

    try:
        orig_bytes, header_bytes, favicon_bytes = _generate_logo_variants(raw_bytes, ext)
    except Exception as e:
        raise HTTPException(400, f"Bild konnte nicht verarbeitet werden: {str(e)}")

    # Alte Logos entfernen
    for old in os.listdir(LOGO_PATH):
        try:
            os.remove(os.path.join(LOGO_PATH, old))
        except Exception:
            pass

    # Original speichern
    orig_path = os.path.join(LOGO_PATH, f"logo_original{ext}")
    with open(orig_path, "wb") as f:
        f.write(orig_bytes)

    # Header-Variante speichern (600×120)
    header_path = os.path.join(LOGO_PATH, "logo_header.png")
    with open(header_path, "wb") as f:
        f.write(header_bytes)

    # Favicon speichern (32×32)
    favicon_path = os.path.join(LOGO_PATH, "logo_favicon.png")
    with open(favicon_path, "wb") as f:
        f.write(favicon_bytes)

    # Cache-Buster: Dateinamen bleiben gleich, daher würde der Browser sonst
    # die alten gecachten Bilder weiter anzeigen
    v = int(zeit.jetzt().timestamp())
    logo_url        = f"/api/static/logo/logo_original{ext}?v={v}"
    logo_header_url = f"/api/static/logo/logo_header.png?v={v}"
    logo_favicon_url = f"/api/static/logo/logo_favicon.png?v={v}"

    _save(db, "logo_url",         logo_url)
    _save(db, "logo_header_url",  logo_header_url)
    _save(db, "logo_favicon_url", logo_favicon_url)

    return {
        "logo_url":         logo_url,
        "logo_header_url":  logo_header_url,
        "logo_favicon_url": logo_favicon_url,
    }


# ── Admin: Logo löschen ───────────────────────────────────────────────────────
@router.delete("/logo")
def delete_logo(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if os.path.exists(LOGO_PATH):
        shutil.rmtree(LOGO_PATH)
    _save(db, "logo_url",         "")
    _save(db, "logo_header_url",  "")
    _save(db, "logo_favicon_url", "")
    return {"ok": True}


# ── Admin: Favicon separat hochladen ─────────────────────────────────────────
@router.post("/favicon")
def upload_favicon(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Eigenes Favicon hochladen (ersetzt die auto-generierte Variante)."""
    os.makedirs(LOGO_PATH, exist_ok=True)

    ext = os.path.splitext(file.filename or "favicon.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".ico", ".svg"):
        raise HTTPException(400, "Nur PNG, JPG, ICO und SVG erlaubt")

    raw_bytes = file.file.read()

    if ext == ".svg":
        _svg_pruefen(raw_bytes)

    if ext not in (".ico", ".svg"):
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            fav = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            thumb = img.copy()
            thumb.thumbnail((32, 32), Image.LANCZOS)
            x = (32 - thumb.width) // 2
            y = (32 - thumb.height) // 2
            fav.paste(thumb, (x, y), thumb)
            raw_bytes = _pil_to_png_bytes(fav)
            ext = ".png"
        except Exception as e:
            raise HTTPException(400, f"Favicon konnte nicht verarbeitet werden: {str(e)}")

    # Alten Favicon entfernen
    for fname in os.listdir(LOGO_PATH):
        if fname.startswith("logo_favicon"):
            try:
                os.remove(os.path.join(LOGO_PATH, fname))
            except Exception:
                pass

    favicon_path = os.path.join(LOGO_PATH, f"logo_favicon{ext}")
    with open(favicon_path, "wb") as f:
        f.write(raw_bytes)

    favicon_url = f"/api/static/logo/logo_favicon{ext}?v={int(zeit.jetzt().timestamp())}"
    _save(db, "logo_favicon_url", favicon_url)
    return {"logo_favicon_url": favicon_url}


# ── Admin: Verknüpften Firmen-Kontakt abrufen ─────────────────────────────────
@router.get("/company-contact")
def get_company_contact(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt die Stammdaten des verknüpften Firmen-Kontakts zurück."""
    data = _load(db)
    contact_id   = data.get("company_contact_id", "")
    contact_type = data.get("company_contact_type", "")

    if not contact_id:
        return {"contact": None}

    record = db.query(EntityRecord).filter(
        EntityRecord.id == contact_id
    ).first()

    if not record:
        return {"contact": None}

    entity_type = db.query(EntityType).filter(
        EntityType.id == record.entity_type_id
    ).first()

    fields = db.query(FieldDefinition).filter(
        FieldDefinition.entity_type_id == record.entity_type_id
    ).order_by(FieldDefinition.sort_order).all()

    field_map = {f.key: f.name for f in fields}

    return {
        "contact": {
            "id":           str(record.id),
            "display_name": record.display_name,
            "type_name":    entity_type.name if entity_type else contact_type,
            "type_slug":    entity_type.slug if entity_type else contact_type,
            "data":         record.data or {},
            "field_labels": field_map,
        }
    }


# ── Öffentlich: Liste aller Kontakte für den Selektor ────────────────────────
@router.get("/contact-options")
def get_contact_options(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Stammdaten-Datensätze für den Firmen-Kontakt-Selektor."""
    types = db.query(EntityType).filter(EntityType.is_active == True).order_by(
        EntityType.sort_order, EntityType.name
    ).all()

    result = []
    for et in types:
        records = db.query(EntityRecord).filter(
            EntityRecord.entity_type_id == et.id
        ).order_by(EntityRecord.display_name).all()

        if records:
            result.append({
                "type_name": et.name,
                "type_slug": et.slug,
                "records": [
                    {"id": str(r.id), "display_name": r.display_name or "(kein Name)"}
                    for r in records
                ],
            })

    return {"groups": result}


# ── Admin: Test-E-Mail senden ─────────────────────────────────────────────────
@router.post("/test-email")
def test_email(
    body: TestEmailRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.services.email_service import send_email

    data     = _load(db)
    provider = data.get("email_provider", "smtp")

    try:
        send_email(
            settings  = data,
            to_email  = body.to_email,
            subject   = "DeineZeit – Test-E-Mail",
            body_text = (
                "Das ist eine Test-E-Mail von DeineZeit.\n\n"
                f"Versandmethode: {'Microsoft Graph API' if provider == 'graph' else 'SMTP'}\n"
                "Konfiguration funktioniert korrekt."
            ),
        )
        method = "Microsoft Graph API" if provider == "graph" else "SMTP"
        return {"ok": True, "message": f"Test-Mail via {method} an {body.to_email} gesendet"}

    except Exception as e:
        raise HTTPException(400, f"E-Mail konnte nicht gesendet werden: {str(e)}")


# ── Backup-Ping: durch Token gesichert ───────────────────────────────────────
@router.post("/backup-ping")
def backup_ping(
    request: Request,
    db: Session = Depends(get_db),
):
    """Wird von backup.ps1 nach erfolgreichem Backup aufgerufen (Token-gesichert)."""
    from fastapi import Header
    token = request.headers.get("X-Backup-Token", "")
    expected = os.environ.get("BACKUP_PING_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Ungültiger Backup-Token")
    import json
    now_iso = datetime.now(timezone.utc).isoformat()

    history_raw = db.query(Setting).filter(Setting.key == "backup_history").first()
    try:
        history = json.loads(history_raw.value) if history_raw and history_raw.value else []
    except Exception:
        history = []

    history.insert(0, now_iso)
    history = history[:3]

    _save(db, "backup_last_at", now_iso)
    _save(db, "backup_history", json.dumps(history))
    return {"ok": True}


# ── Admin: Datenbank-Backup herunterladen ─────────────────────────────────────
@router.get("/backup/download")
def download_backup(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Backup als ZIP: Datenbank + alle Dateien des Objektspeichers + Manifest
    (Audit DATA-002 — vorher nur der SQL-Dump)."""
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from app.services.backup_service import create_backup_archive, backup_dateiname
    try:
        zip_pfad, _manifest = create_backup_archive(db)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    _save(db, "backup_last_at", datetime.now(timezone.utc).isoformat())

    def _aufraeumen(pfad=zip_pfad):
        try:
            os.remove(pfad)
        except OSError:
            pass

    return FileResponse(
        zip_pfad, media_type="application/zip", filename=backup_dateiname("zip"),
        background=BackgroundTask(_aufraeumen),
    )


# ── Backup-Ziel OneDrive (serverseitig via Graph) ─────────────────────────────

class BackupOneDriveTestRequest(BaseModel):
    use_graph_creds: str = "false"   # 'true' = ms_*-Felder wiederverwenden
    tenant_id:       str = ""
    client_id:       str = ""
    client_secret:   str = ""
    drive_type:      str = "personal"  # 'personal' | 'sharepoint'
    site_id:         str = ""
    user:            str = ""            # UPN/E-Mail für drive_type='personal'
    folder:          str = "DeineZeit-Backups"


@router.post("/backup/onedrive/test")
def test_backup_onedrive(
    body: BackupOneDriveTestRequest,
    db:   Session = Depends(get_db),
    _:    User    = Depends(require_admin),
):
    """Verbindungstest für das OneDrive-Backup-Ziel."""
    from app.services.storage_service import OneDriveProvider
    if body.use_graph_creds == "true":
        rows = {r.key: r.value for r in db.query(Setting).filter(
            Setting.key.in_(["ms_tenant_id", "ms_client_id", "ms_client_secret"])
        ).all()}
        tenant_id     = (rows.get("ms_tenant_id") or "").strip()
        client_id     = (rows.get("ms_client_id") or "").strip()
        client_secret = (rows.get("ms_client_secret") or "").strip()
        src = "aus E-Mail-Einstellungen"
    else:
        tenant_id     = (body.tenant_id or "").strip()
        client_id     = (body.client_id or "").strip()
        client_secret = (body.client_secret or "").strip()
        # Leeres Secret im Test → gespeichertes Secret verwenden (Feld wird maskiert)
        if not client_secret:
            saved = db.query(Setting).filter(
                Setting.key == "backup_onedrive_client_secret").first()
            client_secret = (saved.value if saved else "").strip()
        src = "manuell eingegeben"
    if not all([tenant_id, client_id, client_secret]):
        fehlt = [n for n, v in (("Tenant-ID", tenant_id), ("Client-ID", client_id),
                                ("Client-Secret", client_secret)) if not v]
        return {"ok": False,
                "message": f"Zugangsdaten unvollständig ({src}): {', '.join(fehlt)} fehlt"}
    provider = OneDriveProvider(
        tenant_id     = tenant_id,
        client_id     = client_id,
        client_secret = client_secret,
        drive_type    = body.drive_type,
        site_id       = body.site_id,
        user          = body.user,
        root_folder   = body.folder or "DeineZeit-Backups",
    )
    return provider.test_connection()


@router.post("/backup/run")
def run_backup_now(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Erzeugt sofort einen DB-Dump und lädt ihn nach OneDrive hoch (manueller Trigger)."""
    from app.services.backup_service import run_onedrive_backup
    try:
        return run_onedrive_backup(db)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(400, f"OneDrive-Backup fehlgeschlagen: {e}")


# ── Storage-Provider ──────────────────────────────────────────────────────────

class StorageTestRequest(BaseModel):
    storage_backend:    str = "minio"
    # WebDAV
    webdav_url:         str = ""
    webdav_user:        str = ""
    webdav_password:    str = ""
    webdav_root_folder: str = "DeineZeit"
    # OneDrive / Microsoft Graph
    onedrive_use_graph_creds: str = "false"   # 'true' = ms_*-Felder wiederverwenden
    onedrive_tenant_id:       str = ""
    onedrive_client_id:       str = ""
    onedrive_client_secret:   str = ""
    onedrive_drive_type:      str = "personal"  # 'personal' | 'sharepoint'
    onedrive_site_id:         str = ""
    onedrive_user:            str = ""            # UPN/E-Mail für drive_type='personal'
    onedrive_root_folder:     str = "DeineZeit"


@router.post("/storage/test")
def test_storage_connection(
    body: StorageTestRequest,
    db:   Session = Depends(get_db),
    _:    User    = Depends(require_admin),
):
    """Verbindungstest für den gewählten Storage-Provider."""
    from app.services.storage_service import MinioProvider, WebDavProvider, OneDriveProvider
    if body.storage_backend == "webdav":
        provider = WebDavProvider(
            base_url    = body.webdav_url,
            username    = body.webdav_user,
            password    = body.webdav_password,
            root_folder = body.webdav_root_folder,
        )
    elif body.storage_backend == "onedrive":
        if body.onedrive_use_graph_creds == "true":
            from app.models.settings import Setting as _Setting
            rows = {r.key: r.value for r in db.query(_Setting).filter(
                _Setting.key.in_(["ms_tenant_id", "ms_client_id", "ms_client_secret"])
            ).all()}
            tenant_id     = (rows.get("ms_tenant_id") or "").strip()
            client_id     = (rows.get("ms_client_id") or "").strip()
            client_secret = (rows.get("ms_client_secret") or "").strip()
            src = "aus E-Mail-Einstellungen"
        else:
            tenant_id     = (body.onedrive_tenant_id or "").strip()
            client_id     = (body.onedrive_client_id or "").strip()
            client_secret = (body.onedrive_client_secret or "").strip()
            src = "manuell eingegeben"
        if not all([tenant_id, client_id, client_secret]):
            fehlt = [n for n, v in (("Tenant-ID", tenant_id), ("Client-ID", client_id),
                                    ("Client-Secret", client_secret)) if not v]
            return {"ok": False,
                    "message": f"Zugangsdaten unvollständig ({src}): {', '.join(fehlt)} fehlt"}
        provider = OneDriveProvider(
            tenant_id     = tenant_id,
            client_id     = client_id,
            client_secret = client_secret,
            drive_type    = body.onedrive_drive_type,
            site_id       = body.onedrive_site_id,
            user          = body.onedrive_user,
            root_folder   = body.onedrive_root_folder,
        )
    else:
        provider = MinioProvider()
    return provider.test_connection()


@router.post("/storage/apply")
def apply_storage_settings(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Provider-Cache leeren damit neue Storage-Settings sofort aktiv werden."""
    from app.services.storage_service import invalidate_provider_cache
    invalidate_provider_cache()
    return {"ok": True}


# ── Konsolidierung: alle Dateien auf den aktiven Provider umziehen ─────────────

class StorageMigrateRequest(BaseModel):
    delete_source: bool = False   # Quelldateien nach erfolgreichem Kopieren löschen


@router.get("/storage/migration-status")
def storage_migration_status(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Wie viele Dateien liegen (nicht) beim aktiven Speicher."""
    from app.services.storage_service import migration_status
    return migration_status(db)


@router.post("/storage/migrate")
def storage_migrate(
    body: StorageMigrateRequest,
    db:   Session = Depends(get_db),
    _:    User    = Depends(require_admin),
):
    """Verschiebt alle Dateien zum aktuell aktiven Speicher-Provider."""
    from app.services.storage_service import migrate_all_to_active
    return migrate_all_to_active(db, delete_source=body.delete_source)


@router.get("/storage/repath-status")
def storage_repath_status(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Wie viele Dateien liegen noch unter einem ID-Ordner statt Kundennamen."""
    from app.services.storage_service import repath_status
    return repath_status(db)


@router.post("/storage/repath")
def storage_repath(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Stellt die Ordnerstruktur im Speicher auf Kundennamen um (verschiebt Dateien)."""
    from app.services.storage_service import repath_all_to_names
    return repath_all_to_names(db, delete_source=True)
