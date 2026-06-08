import os
import io
import shutil
import subprocess
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from PIL import Image

from app.db.base import get_db
from app.models.settings import Setting
from app.models.user import User
from app.models.masterdata import EntityType, EntityRecord, FieldDefinition
from app.schemas.settings import SettingsResponse, SettingsUpdate, TestEmailRequest
from app.api.deps import get_current_user, require_admin

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


# ── Öffentlich: alle Settings lesen ──────────────────────────────────────────
@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    data = _load(db)
    # Secrets niemals zurückgeben
    safe = {k: v for k, v in data.items() if k not in ('smtp_password', 'ms_client_secret')}
    return SettingsResponse(**{k: safe.get(k, '') for k in SettingsResponse.model_fields})


# ── Admin: Settings aktualisieren ────────────────────────────────────────────
@router.put("")
async def update_settings(
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
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    os.makedirs(LOGO_PATH, exist_ok=True)

    ext = os.path.splitext(file.filename or "logo.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        raise HTTPException(400, "Nur PNG, JPG, SVG und WebP erlaubt")

    raw_bytes = await file.read()

    # SVGs können nicht mit Pillow verarbeitet werden → nur Original speichern
    if ext == ".svg":
        orig_path = os.path.join(LOGO_PATH, f"logo_original{ext}")
        # Alte Logos entfernen
        for old in os.listdir(LOGO_PATH):
            try:
                os.remove(os.path.join(LOGO_PATH, old))
            except Exception:
                pass
        with open(orig_path, "wb") as f:
            f.write(raw_bytes)

        logo_url = f"/api/static/logo/logo_original{ext}"
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

    logo_url        = f"/api/static/logo/logo_original{ext}"
    logo_header_url = "/api/static/logo/logo_header.png"
    logo_favicon_url = "/api/static/logo/logo_favicon.png"

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
async def delete_logo(
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
async def upload_favicon(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Eigenes Favicon hochladen (ersetzt die auto-generierte Variante)."""
    os.makedirs(LOGO_PATH, exist_ok=True)

    ext = os.path.splitext(file.filename or "favicon.png")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".ico", ".svg"):
        raise HTTPException(400, "Nur PNG, JPG, ICO und SVG erlaubt")

    raw_bytes = await file.read()

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

    favicon_url = f"/api/static/logo/logo_favicon{ext}"
    _save(db, "logo_favicon_url", favicon_url)
    return {"logo_favicon_url": favicon_url}


# ── Admin: Verknüpften Firmen-Kontakt abrufen ─────────────────────────────────
@router.get("/company-contact")
async def get_company_contact(
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
async def get_contact_options(
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
async def test_email(
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
async def backup_ping(
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
async def download_backup(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        parts   = db_url.replace("postgresql://", "").split("@")
        user_pw = parts[0].split(":")
        host_db = parts[1].split("/")
        db_user = user_pw[0]
        db_pass = user_pw[1] if len(user_pw) > 1 else ""
        db_host = host_db[0].split(":")[0]
        db_name = host_db[1]
    except Exception:
        raise HTTPException(500, "Datenbank-URL konnte nicht geparst werden")

    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass

    try:
        result = subprocess.run(
            ["pg_dump", "-h", db_host, "-U", db_user, "-d", db_name, "--no-owner"],
            capture_output=True, text=True, env=env, timeout=60
        )
        if result.returncode != 0:
            raise HTTPException(500, f"pg_dump Fehler: {result.stderr[:200]}")

        dump_bytes = result.stdout.encode("utf-8")
        timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename   = f"deinezeit_backup_{timestamp}.sql"

        _save(db, "backup_last_at", datetime.now(timezone.utc).isoformat())

        return StreamingResponse(
            io.BytesIO(dump_bytes),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "Backup-Timeout nach 60 Sekunden")
    except FileNotFoundError:
        raise HTTPException(500, "pg_dump nicht gefunden — bitte Container neu bauen (Dockerfile wurde aktualisiert)")


# ── Storage-Provider ──────────────────────────────────────────────────────────

class StorageTestRequest(BaseModel):
    storage_backend:    str = "minio"
    webdav_url:         str = ""
    webdav_user:        str = ""
    webdav_password:    str = ""
    webdav_root_folder: str = "DeineZeit"


@router.post("/storage/test")
async def test_storage_connection(
    body:    StorageTestRequest,
    _:       User = Depends(require_admin),
):
    """Verbindungstest für den gewählten Storage-Provider."""
    from app.services.storage_service import MinioProvider, WebDavProvider
    if body.storage_backend == "webdav":
        provider = WebDavProvider(
            base_url    = body.webdav_url,
            username    = body.webdav_user,
            password    = body.webdav_password,
            root_folder = body.webdav_root_folder,
        )
    else:
        provider = MinioProvider()
    return provider.test_connection()


@router.post("/storage/apply")
async def apply_storage_settings(
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin),
):
    """Provider-Cache leeren damit neue Storage-Settings sofort aktiv werden."""
    from app.services.storage_service import invalidate_provider_cache
    invalidate_provider_cache()
    return {"ok": True}
