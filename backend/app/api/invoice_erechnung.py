"""
Verkauf – E-Rechnung (Factur-X): Prüfung und XML-Download.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from uuid import UUID
import logging

from app.db.base import get_db
from app.api.deps import (get_current_user, require_modul_rechte)
from app.models.user import User
from app.models.invoice import Invoice
from app.services.erechnung import beleg as erechnung_service
from app.schemas.invoice import (
    ERechnungPruefung,
)
from app.core.http import content_disposition

from app.api.invoice_common import (
    _load_pdf_context,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ── E-Rechnung (C-5) ──────────────────────────────────────────────────────────

@router.get("/{invoice_id}/erechnung/pruefen", response_model=ERechnungPruefung)
def check_einvoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_modul_rechte("verkauf")),
):
    """
    Was einer E-Rechnung dieses Belegs noch fehlt.

    Auch aufrufbar, wenn die E-Rechnung ausgeschaltet ist — man will vor dem
    Einschalten wissen, was auf einen zukommt.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    _settings, inv_settings, verkaeufer, empfaenger = _load_pdf_context(db, inv)
    fehlt = erechnung_service.pruefen(inv, inv_settings, verkaeufer, empfaenger)
    return ERechnungPruefung(
        aktiv=erechnung_service.ist_aktiv(db),
        moeglich=not fehlt and inv.doc_type in erechnung_service.BELEGARTEN,
        fehlende_angaben=fehlt,
        format="ZUGFeRD 2.5 / Factur-X, Profil EN 16931",
    )


@router.get("/{invoice_id}/erechnung/xml")
def download_einvoice_xml(
    invoice_id: UUID,
    trotz_luecken: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_modul_rechte("verkauf")),
):
    """
    Das reine XML herunterladen — zum Prüfen und für Empfänger, die kein PDF
    wollen.

    Bei fehlenden Pflichtangaben kommt HTTP 409 mit der Liste. Mit
    ``trotz_luecken`` gibt es die Datei dennoch: Beim Einrichten hilft es,
    die halbfertige Datei zu sehen. Verschicken darf man sie nicht.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if inv.doc_type not in erechnung_service.BELEGARTEN:
        raise HTTPException(400, "Eine E-Rechnung gibt es nur für Rechnungen "
                                 "und Gutschriften")

    _settings, inv_settings, verkaeufer, empfaenger = _load_pdf_context(db, inv)
    xml, fehlt = erechnung_service.xml_erzeugen(
        inv, inv_settings, verkaeufer, empfaenger, trotz_luecken=trotz_luecken)
    if xml is None:
        raise HTTPException(409, "Die E-Rechnung ist noch nicht vollständig: "
                                 + " ".join(fehlt))

    name = f"{(inv.number or 'beleg').replace('/', '-')}-factur-x.xml"
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": content_disposition("attachment", name)},
    )
