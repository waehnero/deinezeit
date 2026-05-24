"""
Datacenter API – Anhänge (Dateien + Links)
"""
import os
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.attachment import Attachment
from app.models.masterdata import EntityRecord, EntityType
from app.models.user import User
from app.api.deps import get_current_user
from app.services import storage_service

router = APIRouter(prefix="/datacenter", tags=["Datacenter"])

# Max. Dateigröße: 100 MB
MAX_FILE_SIZE = 100 * 1024 * 1024

# Erlaubte Anbieter für Link-Anhänge
LINK_PROVIDERS = {
    "nextcloud":   "NextCloud",
    "onedrive":    "OneDrive",
    "googledrive": "Google Drive",
    "icloud":      "iCloud",
    "seadrive":    "SeaDrive",
    "dropbox":     "Dropbox",
    "sharepoint":  "SharePoint",
    "custom":      "Externer Link",
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class LinkCreate(BaseModel):
    entity_type:   str
    entity_id:     str
    display_name:  str
    link_url:      str
    link_provider: str = "custom"
    description:   Optional[str] = None


class ShareLinkRequest(BaseModel):
    expires_hours: int = 24   # 1, 8, 24, 168 (7 Tage), 0 = unbegrenzt


class AttachmentResponse(BaseModel):
    id:            str
    entity_type:   str
    entity_id:     str
    type:          str
    display_name:  str
    description:   Optional[str]
    filename:      Optional[str]
    filesize:      Optional[int]
    mimetype:      Optional[str]
    link_url:      Optional[str]
    link_provider: Optional[str]
    has_share_link: bool
    share_expires_at: Optional[str]
    uploaded_by:   Optional[str]
    created_at:    str

    class Config:
        from_attributes = True


def _to_response(a: Attachment) -> dict:
    return {
        "id":            str(a.id),
        "entity_type":   a.entity_type,
        "entity_id":     str(a.entity_id),
        "type":          a.type,
        "display_name":  a.display_name,
        "description":   a.description,
        "filename":      a.filename,
        "filesize":      a.filesize,
        "mimetype":      a.mimetype,
        "link_url":      a.link_url,
        "link_provider": a.link_provider,
        "has_share_link": bool(a.share_token),
        "share_expires_at": a.share_expires_at.isoformat() if a.share_expires_at else None,
        "uploaded_by":   str(a.uploaded_by) if a.uploaded_by else None,
        "created_at":    a.created_at.isoformat() if a.created_at else "",
    }


# ── Alle Anhänge abrufen (optional gefiltert) ────────────────────────────────

def _build_entity_label_map(db: Session, rows) -> dict:
    """
    Baut eine Map { (entity_type, entity_id) -> display_label } auf.
    Für Stammdaten-Einträge wird EntityRecord.display_name genutzt.
    """
    label_map = {}
    # Sammle alle einzigartigen (type, id) Kombinationen
    pairs = set((r.entity_type, str(r.entity_id)) for r in rows)

    for etype, eid in pairs:
        try:
            # Versuche Stammdaten-Eintrag zu finden (EntityRecord mit passendem EntityType.slug)
            et = db.query(EntityType).filter(EntityType.slug == etype).first()
            if et:
                rec = db.query(EntityRecord).filter(
                    EntityRecord.id == eid,
                    EntityRecord.entity_type_id == et.id
                ).first()
                if rec and rec.display_name:
                    label_map[(etype, eid)] = rec.display_name
                elif rec and rec.data:
                    # Fallback: ersten Nicht-Leer-Wert aus data nehmen
                    first_val = next((str(v) for v in rec.data.values() if v), None)
                    if first_val:
                        label_map[(etype, eid)] = first_val
        except Exception:
            pass  # Bei Fehler einfach UUID anzeigen

    return label_map


def _to_response_with_label(attachment: Attachment, label_map: dict) -> dict:
    r = _to_response(attachment)
    key = (attachment.entity_type, str(attachment.entity_id))
    r["entity_label"] = label_map.get(key)
    return r


@router.get("/all")
async def list_all_attachments(
    entity_type: Optional[str] = Query(None),
    entity_id:   Optional[str] = Query(None),
    db:          Session = Depends(get_db),
    _:           User = Depends(get_current_user),
):
    """Alle Anhänge abrufen – optional nach entity_type und/oder entity_id gefiltert."""
    q = db.query(Attachment)
    if entity_type:
        q = q.filter(Attachment.entity_type == entity_type)
    if entity_id:
        q = q.filter(Attachment.entity_id == entity_id)
    rows = q.order_by(Attachment.created_at.desc()).all()
    label_map = _build_entity_label_map(db, rows)
    return {"attachments": [_to_response_with_label(r, label_map) for r in rows]}


# ── Anhänge abrufen ───────────────────────────────────────────────────────────

@router.get("/{entity_type}/{entity_id}")
async def list_attachments(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Anhänge für einen Datensatz abrufen."""
    rows = db.query(Attachment).filter(
        Attachment.entity_type == entity_type,
        Attachment.entity_id   == entity_id,
    ).order_by(Attachment.created_at.desc()).all()

    return {"attachments": [_to_response(r) for r in rows]}


# ── Datei hochladen ───────────────────────────────────────────────────────────

@router.post("/{entity_type}/{entity_id}/upload")
async def upload_file(
    entity_type: str,
    entity_id:   str,
    file:        UploadFile = File(...),
    db:          Session = Depends(get_db),
    current:     User = Depends(get_current_user),
):
    """Datei hochladen und mit Datensatz verknüpfen."""
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Datei zu groß (max. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    filename    = file.filename or "datei"
    mimetype    = file.content_type or "application/octet-stream"
    storage_key = storage_service.build_storage_key(entity_type, entity_id, filename)

    # Eindeutigen Key sicherstellen
    existing = db.query(Attachment).filter(
        Attachment.storage_key == storage_key
    ).first()
    if existing:
        storage_key = storage_service.build_storage_key(
            entity_type, entity_id, f"{uuid.uuid4().hex[:6]}_{filename}"
        )

    storage_service.upload_file(storage_key, data, mimetype)

    attachment = Attachment(
        entity_type  = entity_type,
        entity_id    = entity_id,
        type         = "file",
        storage_key  = storage_key,
        filename     = filename,
        filesize     = len(data),
        mimetype     = mimetype,
        display_name = filename,
        uploaded_by  = current.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    return _to_response(attachment)


# ── Link hinzufügen ───────────────────────────────────────────────────────────

@router.post("/link")
async def add_link(
    body:    LinkCreate,
    db:      Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Externen Cloud-Link als Anhang speichern."""
    if body.link_provider not in LINK_PROVIDERS:
        body.link_provider = "custom"

    attachment = Attachment(
        entity_type   = body.entity_type,
        entity_id     = body.entity_id,
        type          = "link",
        link_url      = body.link_url,
        link_provider = body.link_provider,
        display_name  = body.display_name,
        description   = body.description,
        uploaded_by   = current.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    return _to_response(attachment)


# ── Datei herunterladen (eingeloggte User) ────────────────────────────────────

@router.get("/{attachment_id}/download")
async def download_file(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    """Datei herunterladen (nur für eingeloggte Benutzer)."""
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")

    data, content_type = storage_service.download_file(att.storage_key)

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "Content-Length": str(len(data)),
        }
    )


# ── Share-Link erstellen ──────────────────────────────────────────────────────

@router.post("/{attachment_id}/share-link")
async def create_share_link(
    attachment_id: str,
    body:          ShareLinkRequest,
    db:            Session = Depends(get_db),
    current:       User = Depends(get_current_user),
):
    """Öffentlichen Download-Link erstellen (wie SeaDrive Share-Link)."""
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")

    token = secrets.token_urlsafe(32)
    expires = None
    if body.expires_hours > 0:
        expires = datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)

    att.share_token      = token
    att.share_expires_at = expires
    db.commit()

    base_url = os.environ.get("FRONTEND_URL", "http://localhost")
    share_url = f"{base_url}/api/datacenter/share/{token}"

    return {
        "share_url":    share_url,
        "expires_at":   expires.isoformat() if expires else None,
        "expires_hours": body.expires_hours,
    }


# ── Share-Link löschen ────────────────────────────────────────────────────────

@router.delete("/{attachment_id}/share-link")
async def delete_share_link(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(404, "Anhang nicht gefunden")
    att.share_token      = None
    att.share_expires_at = None
    db.commit()
    return {"ok": True}


# ── Öffentlicher Download via Share-Token (kein Login nötig) ─────────────────

@router.get("/share/{token}")
async def download_via_share_link(
    token: str,
    db:    Session = Depends(get_db),
):
    """Öffentlicher Download via Share-Token — kein Login erforderlich."""
    att = db.query(Attachment).filter(Attachment.share_token == token).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Link ungültig oder abgelaufen")

    if att.share_expires_at and att.share_expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Dieser Download-Link ist abgelaufen")

    data, content_type = storage_service.download_file(att.storage_key)

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "Content-Length": str(len(data)),
        }
    )


# ── Vorschau (Bilder + PDFs direkt im Browser) ───────────────────────────────

@router.get("/{attachment_id}/preview")
async def preview_file(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    """Datei-Vorschau im Browser (für Bilder und PDFs)."""
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")

    preview_types = ["image/", "application/pdf", "text/plain"]
    if not any(att.mimetype.startswith(t) for t in preview_types):
        raise HTTPException(415, "Keine Vorschau für diesen Dateityp")

    data, content_type = storage_service.download_file(att.storage_key)

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'}
    )


# ── Anhang löschen ────────────────────────────────────────────────────────────

@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    """Anhang löschen (Datei aus MinIO + Datenbank-Eintrag)."""
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(404, "Anhang nicht gefunden")

    if att.type == "file" and att.storage_key:
        storage_service.delete_file(att.storage_key)

    db.delete(att)
    db.commit()
    return {"ok": True}


# ── Verfügbare Link-Anbieter ─────────────────────────────────────────────────

@router.get("/providers")
async def get_providers(_: User = Depends(get_current_user)):
    """Liste der unterstützten Cloud-Anbieter für Link-Anhänge."""
    return {"providers": [
        {"key": k, "label": v} for k, v in LINK_PROVIDERS.items()
    ]}
