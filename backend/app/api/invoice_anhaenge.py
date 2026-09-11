"""
Verkauf – Vertragsanhang zu wiederkehrenden Rechnungen.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
import logging

from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.invoice import (Invoice, InvoiceAttachment)
from app.schemas.invoice import (
    InvoiceAttachmentResponse,
)
from app.core.http import content_disposition

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Vertrag zu wiederkehrender Rechnung (Nachweis/Referenz zur Serie)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/contract", response_model=InvoiceAttachmentResponse)
def upload_contract(
    invoice_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Hinterlegt ein Vertrags-Dokument an einem (wiederkehrenden) Beleg.

    Der Vertrag wird zusätzlich im Datacenter unter dem Kunden im Ordner
    "Verträge" abgelegt (Dateiname inkl. Belegnummer für den Kontext) und über
    ``datacenter_id`` mit dem Beleg verknüpft.
    """
    from app.services import storage_service
    from app.models.attachment import Attachment
    from app.models.masterdata import EntityRecord

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if not inv.contact_id:
        raise HTTPException(400, "Kein Kontakt am Beleg – der Vertrag kann nicht "
                                 "unter dem Kunden abgelegt werden. Bitte zuerst einen Kontakt wählen.")

    # Obergrenze für hinterlegte Verträge
    MAX_CONTRACTS = 10
    vorhanden = (db.query(InvoiceAttachment)
                 .filter(InvoiceAttachment.invoice_id == inv.id,
                         InvoiceAttachment.attach_type == "contract").count())
    if vorhanden >= MAX_CONTRACTS:
        raise HTTPException(400, f"Maximal {MAX_CONTRACTS} Verträge je Beleg möglich.")

    data = file.file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "Datei zu groß (max. 25 MB)")
    orig = file.filename or "vertrag.pdf"
    mimetype = file.content_type or "application/octet-stream"
    safe_num = (inv.number or "beleg").replace("/", "-")

    # Storage-Key unter Kontakt → Verträge; Belegnummer im Namen für Kontext.
    # Kurzer Zufalls-Präfix im Storage-Pfad verhindert Überschreiben bei
    # gleichnamigen Verträgen (Anzeigename bleibt sauber).
    def _safe(s: str) -> str:
        return "".join(c for c in s if c.isalnum() or c in "._- ").strip() or "datei"
    stored_name = f"{safe_num}_{orig}"
    unique = uuid4().hex[:6]
    _folder = storage_service.folder_name_for(db, inv.contact_id)
    storage_key = f"kontakte/{_folder}/Vertraege/{unique}_{_safe(stored_name)}"
    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(storage_key, data, mimetype, db=db, backend=backend)
    except Exception as exc:
        logger.exception("Fehler bei invoice: %s", exc)
        raise HTTPException(500, "Die Datei konnte nicht gespeichert werden (Ursache im Serverlog).") from exc

    rec = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
    contact_name = rec.display_name if rec else None

    # 1) Datacenter-Eintrag unter dem Kunden, Ordner "Verträge"
    dc = Attachment(
        entity_type="kontakte", entity_id=inv.contact_id,
        type="file", storage_key=storage_key, storage_provider=backend,
        filename=stored_name, filesize=len(data), mimetype=mimetype,
        display_name=f"Vertrag {inv.number} – {orig}",
        contact_id=inv.contact_id, contact_name=contact_name,
        folder="Verträge",
    )
    db.add(dc)
    db.flush()

    # 2) Verknüpfung am Beleg (für Anzeige/Download im Formular)
    att = InvoiceAttachment(
        invoice_id=inv.id, attach_type="contract",
        filename=orig, file_path=storage_key, datacenter_id=dc.id,
        mime_type=mimetype, file_size=len(data),
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/contract/{attachment_id}/download")
def download_contract(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Lädt ein bestimmtes hinterlegtes Vertrags-Dokument herunter."""
    from app.services import storage_service
    from app.models.attachment import Attachment
    att = db.query(InvoiceAttachment).filter(
        InvoiceAttachment.id == attachment_id,
        InvoiceAttachment.attach_type == "contract").first()
    if not att or not att.file_path:
        raise HTTPException(404, "Vertrag nicht gefunden")
    # Provider aus dem verknüpften Datacenter-Eintrag ermitteln (Mischbetrieb)
    backend = None
    if att.datacenter_id:
        dc = db.query(Attachment).filter(Attachment.id == att.datacenter_id).first()
        backend = dc.storage_provider if dc else None
    data, mime = storage_service.download_file(att.file_path, db=db, backend=backend)
    return Response(content=data, media_type=mime or att.mime_type or "application/octet-stream",
                    headers={"Content-Disposition": content_disposition("inline", att.filename or "vertrag")})


@router.delete("/contract/{attachment_id}", status_code=204)
def delete_contract(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Entfernt ein hinterlegtes Vertrags-Dokument (Beleg-Verknüpfung + Datacenter)."""
    from app.services import storage_service
    from app.models.attachment import Attachment
    att = db.query(InvoiceAttachment).filter(
        InvoiceAttachment.id == attachment_id,
        InvoiceAttachment.attach_type == "contract").first()
    if not att:
        raise HTTPException(404, "Vertrag nicht gefunden")

    # Verknüpften Datacenter-Eintrag entfernen
    if att.datacenter_id:
        dc = db.query(Attachment).filter(Attachment.id == att.datacenter_id).first()
        if dc:
            db.delete(dc)

    # Physische Datei einmal löschen
    if att.file_path:
        try:
            storage_service.delete_file(att.file_path, db=db)
        except Exception:
            pass
    db.delete(att)
    db.commit()
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────────────
# E-Mail-Versand
