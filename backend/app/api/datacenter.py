"""
Datacenter API – Anhänge (Dateien + Links)

WICHTIGE ROUTE-REIHENFOLGE:
  Alle spezifischen GET-Routen (/{id}/download, /{id}/preview, /share/{token})
  müssen VOR der generischen GET /{entity_type}/{entity_id} Route stehen,
  da FastAPI/Starlette in Definitionsreihenfolge matched und /{a}/{b} auch
  /{id}/preview abfangen würde.
"""
import io
import os
import uuid
import email
import secrets
import html as html_mod
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse, Response, HTMLResponse
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

# Mimetypes die eine Vorschau unterstützen
PREVIEW_MIMETYPES = [
    "image/",
    "application/pdf",
    "text/plain",
    "message/rfc822",            # .eml
    "text/rfc822",               # .eml (alternativ)
    "application/vnd.ms-outlook", # .msg
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class LinkCreate(BaseModel):
    entity_type:   str
    entity_id:     str
    display_name:  str
    link_url:      str
    link_provider: str = "custom"
    description:   Optional[str] = None


class ShareLinkRequest(BaseModel):
    expires_hours: int = 24


class ShareLinkExtendRequest(BaseModel):
    expires_hours: int = 168  # 0 = unbegrenzt


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
        "share_token":   a.share_token,
        "share_expires_at": a.share_expires_at.isoformat() if a.share_expires_at else None,
        "uploaded_by":   str(a.uploaded_by) if a.uploaded_by else None,
        "created_at":    a.created_at.isoformat() if a.created_at else "",
    }


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _build_entity_label_map(db: Session, rows) -> dict:
    label_map = {}
    pairs = set((r.entity_type, str(r.entity_id)) for r in rows)
    for etype, eid in pairs:
        try:
            et = db.query(EntityType).filter(EntityType.slug == etype).first()
            if et:
                rec = db.query(EntityRecord).filter(
                    EntityRecord.id == eid,
                    EntityRecord.entity_type_id == et.id
                ).first()
                if rec and rec.display_name:
                    label_map[(etype, eid)] = rec.display_name
                elif rec and rec.data:
                    first_val = next((str(v) for v in rec.data.values() if v), None)
                    if first_val:
                        label_map[(etype, eid)] = first_val
        except Exception:
            pass
    return label_map


def _to_response_with_label(attachment: Attachment, label_map: dict) -> dict:
    r = _to_response(attachment)
    key = (attachment.entity_type, str(attachment.entity_id))
    r["entity_label"] = label_map.get(key)
    return r


def _render_eml_preview(raw: bytes) -> str:
    """Parst eine .eml-Datei und gibt HTML für die Vorschau zurück."""
    try:
        msg = email.message_from_bytes(raw)
    except Exception:
        return "<p>E-Mail konnte nicht gelesen werden.</p>"

    def h(s):
        return html_mod.escape(str(s or ""))

    headers_html = ""
    for field in ("From", "To", "CC", "Subject", "Date"):
        val = msg.get(field, "")
        if val:
            headers_html += f'<tr><th>{h(field)}</th><td>{h(val)}</td></tr>'

    # Body extrahieren
    body_text = ""
    body_html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html" and not body_html:
                try:
                    body_html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
            elif ct == "text/plain" and not body_text:
                try:
                    body_text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                if msg.get_content_type() == "text/html":
                    body_html = payload.decode(charset, errors="replace")
                else:
                    body_text = payload.decode(charset, errors="replace")
        except Exception:
            pass

    if body_html:
        # HTML-Body in Sandbox-iframe
        body_content = f"""
          <div style="font-size:13px;color:#555;margin-bottom:8px;">
            ⚠️ HTML-Inhalt wird in isolierter Vorschau angezeigt
          </div>
          <iframe srcdoc="{h(body_html)}"
            style="width:100%;height:calc(100% - 160px);border:1px solid #e5e7eb;border-radius:8px;"
            sandbox="allow-same-origin"></iframe>"""
    else:
        escaped = h(body_text) if body_text else "<em style='color:#999'>Kein Inhalt</em>"
        body_content = f'<pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.6;color:#374151">{escaped}</pre>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f9fafb; color: #111827; padding: 16px; height: 100vh; overflow: hidden; }}
    .card {{ background: white; border-radius: 12px; border: 1px solid #e5e7eb; padding: 16px;
             margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ width: 70px; text-align: left; color: #6b7280; font-size: 12px;
          font-weight: 600; padding: 4px 8px 4px 0; vertical-align: top; }}
    td {{ font-size: 13px; color: #111827; padding: 4px 0; word-break: break-word; }}
    .body {{ background: white; border-radius: 12px; border: 1px solid #e5e7eb;
             padding: 16px; height: calc(100vh - 180px); overflow-y: auto; }}
  </style>
</head>
<body>
  <div class="card">
    <table>{headers_html}</table>
  </div>
  <div class="body">{body_content}</div>
</body>
</html>"""


def _render_msg_preview(raw: bytes) -> str:
    """Parst eine .msg-Datei (Outlook) und gibt HTML für die Vorschau zurück."""
    try:
        import extract_msg
        msg = extract_msg.Message(io.BytesIO(raw))
    except Exception as e:
        return f"<p>MSG-Datei konnte nicht gelesen werden: {html_mod.escape(str(e))}</p>"

    def h(s):
        return html_mod.escape(str(s or ""))

    headers_html = ""
    for field, val in [
        ("From",    msg.sender),
        ("To",      msg.to),
        ("CC",      msg.cc),
        ("Subject", msg.subject),
        ("Date",    str(msg.date) if msg.date else ""),
    ]:
        if val:
            headers_html += f'<tr><th>{h(field)}</th><td>{h(val)}</td></tr>'

    # HTML-Body bevorzugen, sonst Plain-Text
    body_html = getattr(msg, "htmlBody", None)
    body_text = msg.body or ""

    if body_html:
        if isinstance(body_html, bytes):
            body_html = body_html.decode("utf-8", errors="replace")
        body_content = f"""
          <div style="font-size:13px;color:#555;margin-bottom:8px;">
            ⚠️ HTML-Inhalt wird in isolierter Vorschau angezeigt
          </div>
          <iframe srcdoc="{h(body_html)}"
            style="width:100%;height:calc(100% - 160px);border:1px solid #e5e7eb;border-radius:8px;"
            sandbox="allow-same-origin"></iframe>"""
    else:
        escaped = h(body_text) if body_text else "<em style='color:#999'>Kein Inhalt</em>"
        body_content = f'<pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.6;color:#374151">{escaped}</pre>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f9fafb; color: #111827; padding: 16px; height: 100vh; overflow: hidden; }}
    .card {{ background: white; border-radius: 12px; border: 1px solid #e5e7eb; padding: 16px;
             margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ width: 70px; text-align: left; color: #6b7280; font-size: 12px;
          font-weight: 600; padding: 4px 8px 4px 0; vertical-align: top; }}
    td {{ font-size: 13px; color: #111827; padding: 4px 0; word-break: break-word; }}
    .body {{ background: white; border-radius: 12px; border: 1px solid #e5e7eb;
             padding: 16px; height: calc(100vh - 180px); overflow-y: auto; }}
  </style>
</head>
<body>
  <div class="card">
    <table>{headers_html}</table>
  </div>
  <div class="body">{body_content}</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════════════════════
# ROUTEN – Reihenfolge ist entscheidend!
# 1. Literal-Routen  (/all, /providers, /link, /share/...)
# 2. /{id}/suffix   (download, preview, share-link) – VOR /{type}/{id}!
# 3. /{type}/{id}   (generische 2-Segment-Route)
# 4. /{type}/{id}/upload
# 5. DELETE /{id}
# ════════════════════════════════════════════════════════════════════════════════

# ── 1a. Alle Anhänge abrufen ─────────────────────────────────────────────────

@router.get("/all")
async def list_all_attachments(
    entity_type: Optional[str] = Query(None),
    entity_id:   Optional[str] = Query(None),
    db:          Session = Depends(get_db),
    _:           User = Depends(get_current_user),
):
    q = db.query(Attachment)
    if entity_type:
        q = q.filter(Attachment.entity_type == entity_type)
    if entity_id:
        q = q.filter(Attachment.entity_id == entity_id)
    rows = q.order_by(Attachment.created_at.desc()).all()
    label_map = _build_entity_label_map(db, rows)
    return {"attachments": [_to_response_with_label(r, label_map) for r in rows]}


# ── 1b. Link-Anbieter ────────────────────────────────────────────────────────

@router.get("/providers")
async def get_providers(_: User = Depends(get_current_user)):
    return {"providers": [{"key": k, "label": v} for k, v in LINK_PROVIDERS.items()]}


# ── 1c. Öffentlicher Download via Share-Token (kein Login) ───────────────────

@router.get("/share/{token}")
async def download_via_share_link(
    token: str,
    db:    Session = Depends(get_db),
):
    att = db.query(Attachment).filter(Attachment.share_token == token).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Link ungültig oder abgelaufen")
    if att.share_expires_at and att.share_expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Dieser Download-Link ist abgelaufen")

    data, content_type = storage_service.download_file(att.storage_key)
    return Response(
        content=data, media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "Content-Length": str(len(data)),
        }
    )


# ── 1d. Link hinzufügen ──────────────────────────────────────────────────────

@router.post("/link")
async def add_link(
    body:    LinkCreate,
    db:      Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if body.link_provider not in LINK_PROVIDERS:
        body.link_provider = "custom"
    attachment = Attachment(
        entity_type=body.entity_type, entity_id=body.entity_id,
        type="link", link_url=body.link_url, link_provider=body.link_provider,
        display_name=body.display_name, description=body.description,
        uploaded_by=current.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _to_response(attachment)


# ── 2a. Download (eingeloggt) ─────────────────────────────────────────────────

@router.get("/{attachment_id}/download")
async def download_file(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")
    data, content_type = storage_service.download_file(att.storage_key)
    return Response(
        content=data, media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename}"',
            "Content-Length": str(len(data)),
        }
    )


# ── 2b. Vorschau ──────────────────────────────────────────────────────────────

@router.get("/{attachment_id}/preview")
async def preview_file(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")

    mimetype = att.mimetype or "application/octet-stream"
    filename_lower = (att.filename or "").lower()
    is_eml = mimetype in ("message/rfc822", "text/rfc822") or filename_lower.endswith(".eml")
    is_msg = mimetype == "application/vnd.ms-outlook" or filename_lower.endswith(".msg")

    # EML/MSG immer erlauben, auch wenn Browser "application/octet-stream" gesendet hat
    if not is_eml and not is_msg and not any(mimetype.startswith(t) for t in PREVIEW_MIMETYPES):
        raise HTTPException(415, "Keine Vorschau für diesen Dateityp")

    data, content_type = storage_service.download_file(att.storage_key)

    if is_msg:
        return HTMLResponse(content=_render_msg_preview(data))

    # EML-Vorschau als HTML rendern
    if is_eml:
        html_content = _render_eml_preview(data)
        return HTMLResponse(content=html_content)

    return Response(
        content=data, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'}
    )


# ── 2c. Share-Link erstellen ──────────────────────────────────────────────────

@router.post("/{attachment_id}/share-link")
async def create_share_link(
    attachment_id: str,
    body:          ShareLinkRequest,
    db:            Session = Depends(get_db),
    current:       User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or att.type != "file":
        raise HTTPException(404, "Anhang nicht gefunden")

    token   = secrets.token_urlsafe(32)
    expires = None
    if body.expires_hours > 0:
        expires = datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)

    att.share_token      = token
    att.share_expires_at = expires
    db.commit()

    base_url  = os.environ.get("FRONTEND_URL", "http://localhost")
    share_url = f"{base_url}/api/datacenter/share/{token}"
    return {"share_url": share_url, "expires_at": expires.isoformat() if expires else None,
            "expires_hours": body.expires_hours}


# ── 2d. Share-Link verlängern ─────────────────────────────────────────────────

@router.patch("/{attachment_id}/share-link")
async def extend_share_link(
    attachment_id: str,
    body:          ShareLinkExtendRequest,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att or not att.share_token:
        raise HTTPException(404, "Kein aktiver Share-Link für diesen Anhang")

    att.share_expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)
        if body.expires_hours > 0 else None
    )
    db.commit()

    base_url = os.environ.get("FRONTEND_URL", "http://localhost")
    return {
        "share_url":  f"{base_url}/api/datacenter/share/{att.share_token}",
        "expires_at": att.share_expires_at.isoformat() if att.share_expires_at else None,
    }


# ── 2e. Share-Link löschen ────────────────────────────────────────────────────

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


# ── 3. Anhänge eines Datensatzes abrufen ──────────────────────────────────────

@router.get("/{entity_type}/{entity_id}")
async def list_attachments(
    entity_type: str,
    entity_id:   str,
    db:          Session = Depends(get_db),
    _:           User = Depends(get_current_user),
):
    rows = db.query(Attachment).filter(
        Attachment.entity_type == entity_type,
        Attachment.entity_id   == entity_id,
    ).order_by(Attachment.created_at.desc()).all()
    return {"attachments": [_to_response(r) for r in rows]}


# ── 4. Datei hochladen ────────────────────────────────────────────────────────

@router.post("/{entity_type}/{entity_id}/upload")
async def upload_file(
    entity_type: str,
    entity_id:   str,
    file:        UploadFile = File(...),
    db:          Session = Depends(get_db),
    current:     User = Depends(get_current_user),
):
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Datei zu groß (max. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    filename    = file.filename or "datei"
    mimetype    = file.content_type or "application/octet-stream"
    storage_key = storage_service.build_storage_key(entity_type, entity_id, filename)

    if db.query(Attachment).filter(Attachment.storage_key == storage_key).first():
        storage_key = storage_service.build_storage_key(
            entity_type, entity_id, f"{uuid.uuid4().hex[:6]}_{filename}"
        )

    storage_service.upload_file(storage_key, data, mimetype)

    attachment = Attachment(
        entity_type=entity_type, entity_id=entity_id,
        type="file", storage_key=storage_key,
        filename=filename, filesize=len(data), mimetype=mimetype,
        display_name=filename, uploaded_by=current.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _to_response(attachment)


# ── 5. Anhang löschen ─────────────────────────────────────────────────────────

@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    db:            Session = Depends(get_db),
    _:             User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not att:
        raise HTTPException(404, "Anhang nicht gefunden")
    if att.type == "file" and att.storage_key:
        storage_service.delete_file(att.storage_key)
    db.delete(att)
    db.commit()
    return {"ok": True}
