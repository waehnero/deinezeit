"""
Verkauf – E-Mail-Versand von Belegen (einzeln und gesammelt).

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.invoice import Invoice
from app.models.email_template import EmailTemplate
from app.models.masterdata import EntityRecord
from app.services.invoice_snapshot import snapshot_as_contact
from app.services.invoice_archive import archive_invoice_pdf
from app.services import anzahlung as anzahlung_service
from app.services.erechnung import beleg as erechnung_service

from app.api.invoice_common import (
    DOC_TYPE_LABELS_DE,
    _audit,
    _audit_changes,
    _ensure_number,
    _finalize,
    _load_pdf_context,
    _pruefe_pflichtangaben,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────

def _send_invoice_email(inv: Invoice, db, settings_d: dict, inv_settings_d: dict,
                         sender_contact, recipient_contact, to_email: str, current_user_email: str,
                         extra_attachments: list = None, cc_email: str = None,
                         custom_subject: str = None, custom_body_html: str = None):
    """Generiert PDF und versendet per E-Mail.
    extra_attachments: Liste von Dicts mit:
      - type='datacenter': {type, id}  → wird aus Storage geladen
      - type='local':      {type, filename, mime_type, data_b64}  → base64-kodiert
    """
    import base64
    from app.services.invoice_pdf import generate_pdf
    from app.services.email_service import send_email
    from app.models.attachment import Attachment
    from app.services import storage_service

    # Die Abrechnungsstufe schlägt die Belegart — im Betreff der E-Mail soll
    # „Anzahlungsrechnung" stehen, nicht bloß „Rechnung".
    doc_label    = (anzahlung_service.bezeichnung(inv.billing_stage)
                    if inv.doc_type == "rechnung" and inv.billing_stage
                    else DOC_TYPE_LABELS_DE.get(inv.doc_type, inv.doc_type))
    company_name = settings_d.get("company_name", "DeineZeit")

    # Pflichtangaben VOR dem Versand prüfen — sonst geht der Beleg raus und
    # scheitert erst danach am Statuswechsel.
    _pruefe_pflichtangaben(inv)

    # ── Der Beleg verlässt den Entwurf, BEVOR das PDF entsteht ──────────────
    #
    # Das PDF trägt ein Wasserzeichen, solange der Beleg ein Entwurf ist, und
    # es rendert den Empfänger live statt aus dem eingefrorenen Snapshot.
    # Wurde erst gesendet und danach finalisiert, bekam der Kunde deshalb
    # einen Beleg mit „ENTWURF" quer darüber — beim zweiten Versand war es
    # weg. Ebenso liefen die Prüfungen auf Leistungsdatum und Periodensperre
    # erst NACH dem Versand: Die Mail war beim Kunden, und der Server meldete
    # anschließend einen Fehler.
    #
    # Sicher ist das, weil der Aufrufer erst nach erfolgreichem Versand
    # committet — scheitert die Zustellung, bleibt der Beleg Entwurf.
    if inv.status not in ("bezahlt", "storniert", "angenommen", "abgelehnt",
                          "gesendet"):
        alter_status = inv.status
        inv.status = "gesendet"
        inv.updated_by = current_user_email
        neue_nummer = _finalize(db, inv)
        _audit(db, inv, "finalisiert" if neue_nummer else "status",
               changes=_audit_changes(alter_status, inv, neue_nummer),
               note=f"Per E-Mail an {to_email}", user_email=current_user_email)
        db.add(inv)
    else:
        # Schon ausgestellt: Status bleibt, eine fehlende Nummer (Altbestand)
        # wird nachgezogen. Der erneute Versand wird trotzdem vermerkt —
        # „wann ging der Beleg zum zweiten Mal hinaus" ist eine Frage, die
        # tatsächlich gestellt wird.
        _ensure_number(db, inv)
        _audit(db, inv, "hinweis", note=f"Erneut per E-Mail an {to_email}",
               user_email=current_user_email)
    db.flush()

    # Empfänger jetzt aus dem eingefrorenen Snapshot lesen. Sonst entstünde
    # das versendete PDF aus den Live-Stammdaten, jeder spätere Nachdruck aber
    # aus dem Snapshot — zwei Fassungen desselben Belegs.
    recipient_contact = snapshot_as_contact(inv.recipient_snapshot) or recipient_contact

    # Der versendete Beleg ist die eigentliche E-Rechnung: Ist sie
    # eingeschaltet und vollständig, geht das hybride PDF hinaus — sichtbar
    # unverändert, nur mit den Daten darin.
    xml = erechnung_service.xml_fuer_pdf(db, inv, inv_settings_d,
                                          sender_contact, recipient_contact)
    pdf_bytes = generate_pdf(inv, inv.positions, settings_d, inv_settings_d,
                              sender_contact, recipient_contact, db=db,
                              erechnung_xml=xml)

    filename = f"{(inv.number or 'beleg').replace('/', '-')}.pdf"

    # Platzhalter für Vorlagen
    contact_name = ""
    if recipient_contact:
        contact_name = recipient_contact.display_name or ""
    betrag_str = f"{float(inv.total or 0):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    datum_str  = inv.date.strftime("%d.%m.%Y") if inv.date else ""
    faellig_str = inv.due_date.strftime("%d.%m.%Y") if inv.due_date else ""
    placeholders = {
        "nummer":   inv.number or "",
        "belegart": doc_label,
        "firma":    company_name,
        "kontakt":  contact_name,
        "betrag":   betrag_str,
        "datum":    datum_str,
        "faellig":  faellig_str,
    }

    def _fill(text: str) -> str:
        for k, v in placeholders.items():
            text = text.replace("{" + k + "}", v)
        return text

    if custom_subject or custom_body_html:
        subject   = _fill(custom_subject or "")
        body_html = _fill(custom_body_html or "")
        body      = ""  # plain-text fallback leer wenn HTML vorhanden
    else:
        # Vorlage aus DB laden
        tmpl = db.query(EmailTemplate).filter(EmailTemplate.doc_type == inv.doc_type).first()
        if tmpl and tmpl.subject:
            subject   = _fill(tmpl.subject)
            body_html = _fill(tmpl.body_html or "")
            body      = ""
        else:
            # Fallback (kein Template konfiguriert)
            subject   = f"{doc_label} {inv.number} von {company_name}"
            body_html = ""
            body      = (
                f"Sehr geehrte Damen und Herren,\n\n"
                f"anbei erhalten Sie {doc_label} {inv.number}.\n\n"
                f"Mit freundlichen Grüßen\n{company_name}"
            )

    attachments = [{"filename": filename, "data": pdf_bytes, "mime_type": "application/pdf"}]

    for att in (extra_attachments or []):
        try:
            if att.get("type") == "datacenter":
                dc = db.query(Attachment).filter(Attachment.id == att["id"]).first()
                if dc and dc.storage_key:
                    data, mime = storage_service.download_file(dc.storage_key)
                    attachments.append({
                        "filename":  dc.filename or dc.display_name or "anhang",
                        "data":      data,
                        "mime_type": mime or dc.mimetype or "application/octet-stream",
                    })
            elif att.get("type") == "local":
                data = base64.b64decode(att.get("data_b64", ""))
                attachments.append({
                    "filename":  att.get("filename", "anhang"),
                    "data":      data,
                    "mime_type": att.get("mime_type", "application/octet-stream"),
                })
        except Exception:
            pass  # Einzelner fehlerhafter Anhang soll Versand nicht blockieren

    send_email(
        settings=settings_d,
        to_email=to_email,
        subject=subject,
        body_text=body,
        body_html=body_html if body_html else None,
        attachments=attachments,
        cc_email=cc_email or None,
    )

    # Der Statuswechsel ist oben schon passiert — vor der PDF-Erzeugung.

    # Bei aktiviertem Auslöser PDF ins Datacenter archivieren (E-Mail-Versand)
    db.flush()
    archive_invoice_pdf(db, inv, "email")


@router.post("/{invoice_id}/send-email")
def send_invoice_email(
    invoice_id: UUID,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Versendet einen Beleg per E-Mail.
    Body: { to_email: str (optional — wird sonst aus Kontakt gelesen) }
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)

    to_email = body.get("to_email", "")
    cc_email         = body.get("cc_email", "") or None
    custom_subject   = body.get("subject") or None
    custom_body_html = body.get("body_html") or None
    if not to_email and inv.contact_id:
        # Bevorzugt LIVE aus dem Kontakt (Snapshot-E-Mail könnte veraltet sein)
        live = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
        if live:
            to_email = (live.data or {}).get("email", "")
    if not to_email and recipient_contact:
        to_email = (recipient_contact.data or {}).get("email", "")
    if not to_email:
        raise HTTPException(400, "Keine E-Mail-Adresse vorhanden. Bitte im Kontakt hinterlegen.")

    extra_attachments = body.get("extra_attachments", [])

    try:
        _send_invoice_email(inv, db, settings_d, inv_settings_d,
                             sender_contact, recipient_contact, to_email, current_user.email,
                             extra_attachments=extra_attachments, cc_email=cc_email,
                             custom_subject=custom_subject, custom_body_html=custom_body_html)
        db.commit()
    except HTTPException:
        # Die Prüfungen auf Leistungsdatum und Periodensperre laufen jetzt VOR
        # dem Versand und melden im Klartext, was fehlt. Als „E-Mail konnte
        # nicht gesendet werden" verkleidet wäre das irreführend — gesendet
        # wurde ja gerade nicht, und der Grund liegt am Beleg.
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Fehler bei invoice: %s", e)
        raise HTTPException(500, "Die E-Mail konnte nicht gesendet werden (Ursache im Serverlog).")

    return {"ok": True, "to": to_email, "number": inv.number}


@router.post("/bulk-send-email")
def bulk_send_email(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Versendet mehrere Belege per E-Mail.
    Body: { invoice_ids: [str, ...] }
    """
    from uuid import UUID as _UUID
    ids = [_UUID(i) for i in body.get("invoice_ids", [])]
    if not ids:
        raise HTTPException(400, "Keine Belege angegeben")

    results = []
    for inv_id in ids:
        inv = db.query(Invoice).filter(Invoice.id == inv_id).first()
        if not inv:
            results.append({"id": str(inv_id), "ok": False, "error": "Nicht gefunden"})
            continue

        settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)

        to_email = ""
        if inv.contact_id:
            live = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
            if live:
                to_email = (live.data or {}).get("email", "")
        if not to_email and recipient_contact:
            to_email = (recipient_contact.data or {}).get("email", "")
        if not to_email:
            results.append({"id": str(inv_id), "number": inv.number, "ok": False,
                             "error": "Keine E-Mail-Adresse im Kontakt"})
            continue

        # Je Beleg committen statt einmal am Ende: Sonst reißt ein Fehler beim
        # fünften Beleg die Statusänderungen der vier davor mit — obwohl deren
        # E-Mails längst raus sind. Ein Rollback holt keine E-Mail zurück.
        try:
            _send_invoice_email(inv, db, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, to_email, current_user.email)
            db.commit()
            results.append({"id": str(inv_id), "number": inv.number, "ok": True, "to": to_email})
        except HTTPException as e:
            db.rollback()
            # detail statt str(e): Sonst stünde „400: Das Liefer-/Leistungs-
            # datum fehlt…" in der Liste, mit Statuscode als Präfix.
            results.append({"id": str(inv_id), "number": inv.number, "ok": False,
                            "error": str(e.detail)})
        except Exception as e:
            db.rollback()
            results.append({"id": str(inv_id), "number": inv.number, "ok": False, "error": str(e)})

    sent = sum(1 for r in results if r["ok"])
    return {"sent": sent, "total": len(ids), "results": results}
