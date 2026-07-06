"""
DSGVO-Endpunkte (Datenschutz-Bereich in den Einstellungen)
==========================================================

  GET  /gdpr/records/{record_id}/report  — Betroffenheitsanalyse (Vorschau)
  POST /gdpr/records/{record_id}/erase   — Löschung (Anonymisierung) ausführen
  GET  /gdpr/log                         — Löschprotokoll

Alles Admin-only. Die Löschung erzeugt zwei PDF-Berichte:
  - Löschbescheinigung für die betroffene Person (mit Personenbezug):
    wird NUR in der Response (Base64) übergeben, nie gespeichert.
  - Anonymisiertes Löschprotokoll: wird im Datacenter des Mandanten abgelegt.
"""
import base64
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import require_admin
from app.models.user import User
from app.models.masterdata import EntityRecord
from app.models.attachment import Attachment
from app.models.settings import Setting
from app.models.gdpr import GdprDeletionLog
from app.services import gdpr as gdpr_service
from app.services import storage_service
from app.services.gdpr import GdprBlockedError
from app.services.gdpr_pdf import build_erasure_pdf

router = APIRouter(prefix="/gdpr", tags=["Datenschutz (DSGVO)"])


class EraseRequest(BaseModel):
    # "deleted" = Datacenter-Dateien des Kontakts endgültig löschen,
    # "none"    = Dateien behalten (Kontaktbezug wird anonymisiert)
    files_action: str = "none"
    note: Optional[str] = None


def _get_record(db: Session, record_id: UUID) -> EntityRecord:
    record = db.query(EntityRecord).filter(EntityRecord.id == record_id).first()
    if not record:
        raise HTTPException(404, "Datensatz nicht gefunden")
    return record


def _company_context(db: Session) -> tuple[str, list[str], Optional[UUID]]:
    """Firmenname, Adresszeilen und Kontakt-ID des Mandanten (Verantwortlicher)."""
    settings = {r.key: r.value for r in db.query(Setting).all()}
    company_name = settings.get("company_name", "DeineZeit")
    contact_id = None
    lines = [company_name]
    cid = settings.get("company_contact_id", "")
    if cid:
        try:
            contact_id = UUID(str(cid).strip('"'))
            rec = db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()
            if rec:
                d = rec.data or {}
                lines = [rec.display_name or company_name]
                if d.get("adresse"):
                    lines.append(d["adresse"])
                plz_ort = f"{d.get('plz', '')} {d.get('ort', '')}".strip()
                if plz_ort:
                    lines.append(plz_ort)
                if d.get("email"):
                    lines.append(d["email"])
        except (ValueError, TypeError):
            contact_id = None
    return company_name, lines, contact_id


@router.get("/records/{record_id}/report")
async def get_report(
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Betroffenheitsanalyse: was würde anonymisiert, was blockiert."""
    record = _get_record(db, record_id)
    return gdpr_service.build_report(db, record)


@router.post("/records/{record_id}/erase")
async def erase_record(
    record_id: UUID,
    body: EraseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Führt die DSGVO-Löschung (Anonymisierung) aus."""
    if body.files_action not in ("none", "deleted"):
        raise HTTPException(400, "files_action muss 'none' oder 'deleted' sein")

    record = _get_record(db, record_id)
    if record.anonymized_at:
        raise HTTPException(400, "Kontakt wurde bereits anonymisiert")

    blockers = gdpr_service.check_blockers(db, record)
    if blockers:
        raise HTTPException(409, {"message": "Löschung blockiert", "blockers": blockers})

    # Report VOR der Löschung erstellen (Zahlen + Personendaten für die
    # Bescheinigung an die betroffene Person)
    report = gdpr_service.build_report(db, record)

    # 1. Datacenter-Dateien des Kontakts löschen (falls gewünscht)
    files_deleted = 0
    if body.files_action == "deleted":
        atts = db.query(Attachment).filter(Attachment.contact_id == record.id).all()
        for att in atts:
            if att.type == "file" and att.storage_key:
                try:
                    storage_service.delete_file(att.storage_key, db=db)
                except Exception:
                    pass  # Objekt fehlt im Storage → Eintrag trotzdem entfernen
            db.delete(att)
            files_deleted += 1
        db.flush()

    # 2. Anonymisieren (inkl. Snapshot-Backfill + Löschprotokoll)
    try:
        categories = gdpr_service.anonymize_contact(
            db, record,
            executed_by=current_user.email,
            files_action=body.files_action,
            note=body.note,
        )
    except GdprBlockedError as e:
        raise HTTPException(409, {"message": "Löschung blockiert", "blockers": e.blockers})
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Zahlen fürs Protokoll/PDF zusammenführen (Report zeigt Stand VOR Löschung)
    categories["attachments_deleted"] = files_deleted
    report["categories"].update({
        "invoices_snapshotted": categories.get("invoices_snapshotted", 0),
    })

    log = db.query(GdprDeletionLog).filter(
        GdprDeletionLog.record_id == record.id
    ).order_by(GdprDeletionLog.executed_at.desc()).first()
    log.categories = categories

    company_name, company_lines, company_contact_id = _company_context(db)

    # 3. PDF für die betroffene Person (mit Personenbezug — nur Download)
    personal_pdf = build_erasure_pdf(
        variant="personal", report=report, log_id=str(log.id),
        executed_at=log.executed_at, executed_by=log.executed_by,
        files_action=body.files_action, company_name=company_name,
        company_lines=company_lines, note=body.note,
    )

    # 4. Anonymisiertes Protokoll im Datacenter des Mandanten ablegen
    filed_attachment_id = None
    anon_pdf = build_erasure_pdf(
        variant="anonymized", report=report, log_id=str(log.id),
        executed_at=log.executed_at, executed_by=log.executed_by,
        files_action=body.files_action, company_name=company_name,
        company_lines=company_lines,
    )
    filename = f"DSGVO-Loeschprotokoll-{log.executed_at.strftime('%Y-%m-%d')}-{str(log.id)[:8]}.pdf"
    try:
        storage_key = storage_service.build_storage_key("dsgvo", str(log.id), filename)
        storage_service.upload_file(storage_key, anon_pdf, "application/pdf", db=db)
        filed = Attachment(
            entity_type="dsgvo", entity_id=log.id,
            type="file", storage_key=storage_key,
            filename=filename, filesize=len(anon_pdf), mimetype="application/pdf",
            display_name=filename, uploaded_by=current_user.id,
            contact_id=company_contact_id,
            contact_name=company_name if company_contact_id else None,
        )
        db.add(filed)
        db.flush()
        filed_attachment_id = str(filed.id)
    except Exception:
        # Ablage ist best-effort (z.B. Storage nicht erreichbar) — die Löschung
        # selbst und das DB-Protokoll sind davon unabhängig gültig.
        filed_attachment_id = None

    db.commit()

    return {
        "ok": True,
        "log_id": str(log.id),
        "categories": categories,
        "files_deleted": files_deleted,
        "filed_attachment_id": filed_attachment_id,
        "certificate_filename": f"DSGVO-Loeschbescheinigung-{log.executed_at.strftime('%Y-%m-%d')}.pdf",
        "certificate_pdf_b64": base64.b64encode(personal_pdf).decode(),
    }


@router.get("/log")
async def get_deletion_log(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Löschprotokoll (ohne Personenbezug), neueste zuerst."""
    logs = db.query(GdprDeletionLog).order_by(GdprDeletionLog.executed_at.desc()).all()
    return [{
        "id": str(l.id),
        "record_id": str(l.record_id),
        "executed_by": l.executed_by,
        "executed_at": l.executed_at.isoformat() if l.executed_at else None,
        "categories": l.categories or {},
        "files_action": l.files_action,
        "note": l.note,
    } for l in logs]
