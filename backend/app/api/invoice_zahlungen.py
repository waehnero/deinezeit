"""
Verkauf – Zahlungseingänge und Skonto.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import date
from decimal import Decimal
import logging

from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.invoice import (Invoice, InvoicePayment)
from app.services.invoice_archive import archive_invoice_pdf
from app.services import period_service
from app.services import skonto as skonto_service
from app.schemas.invoice import (
    InvoicePaymentCreate, InvoicePaymentResponse, InvoicePaymentState,
    SkontoVorschau, SkontoZeile, SkontoRequest,
)
from app.core import zeit

from app.api.invoice_common import (
    _audit,
    _recalc_payment_status,
    _zahlstand,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Zahlungseingänge
# ─────────────────────────────────────────────────────────────────────────────

def _zahlstand_antwort(invoice: Invoice) -> InvoicePaymentState:
    gezahlt, offen, ueberzahlt = _zahlstand(invoice)
    return InvoicePaymentState(
        invoice_id=invoice.id, status=invoice.status, total=invoice.total,
        paid_total=gezahlt, open_amount=offen, overpaid=ueberzahlt,
        payments=[InvoicePaymentResponse.model_validate(z) for z in invoice.payments],
    )


@router.get("/{invoice_id}/payments", response_model=InvoicePaymentState)
def list_payments(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Zahlungseingänge eines Belegs samt Zahlstand."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    return _zahlstand_antwort(inv)


@router.post("/{invoice_id}/payments", response_model=InvoicePaymentState)
def add_payment(
    invoice_id: UUID,
    body: InvoicePaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erfasst einen Zahlungseingang.

    Mehrere Zahlungen je Beleg sind ausdrücklich vorgesehen (Teil- und
    Ratenzahlung). Eine Überzahlung wird angenommen und gekennzeichnet statt
    abgelehnt — sie kommt vor, und das System darf daran nicht scheitern.
    """
    from decimal import Decimal

    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if inv.doc_type not in ("rechnung", "gutschrift"):
        raise HTTPException(400, "Nur Rechnungen und Gutschriften können bezahlt werden")
    if inv.status == "entwurf":
        raise HTTPException(400, "Ein Entwurf ist noch nicht ausgestellt — "
                                 "er kann keine Zahlung haben.")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege können keine Zahlung erhalten")
    if Decimal(str(body.amount)) == 0:
        raise HTTPException(400, "Der Zahlbetrag darf nicht null sein")

    zahlung = InvoicePayment(
        invoice_id=inv.id, paid_at=body.paid_at, amount=body.amount,
        method=body.method, reference=body.reference, note=body.note,
        created_by=current_user.email,
    )
    db.add(zahlung)
    db.flush()
    db.refresh(inv)

    alter_status = inv.status
    _recalc_payment_status(db, inv)
    inv.updated_by = current_user.email

    _, offen, ueberzahlt = _zahlstand(inv)
    hinweis = " — Überzahlung" if ueberzahlt else ""
    _audit(db, inv, "zahlung",
           changes={"status": {"alt": alter_status, "neu": inv.status}}
                   if alter_status != inv.status else None,
           note=f"Zahlung {body.paid_at:%d.%m.%Y} über "
                f"{float(body.amount):.2f} {inv.currency}, offen "
                f"{float(offen):.2f}{hinweis}",
           user_email=current_user.email)

    db.flush()
    archive_invoice_pdf(db, inv, "bezahlt") if inv.status == "bezahlt" else None
    db.commit()
    db.refresh(inv)
    return _zahlstand_antwort(inv)


@router.delete("/payments/{payment_id}", response_model=InvoicePaymentState)
def delete_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Nimmt einen Zahlungseingang zurück (Fehleingabe).

    Der Belegstatus wird danach neu abgeleitet. Wird die letzte Zahlung
    entfernt, gilt der Beleg wieder als offen bzw. überfällig.
    """
    zahlung = db.query(InvoicePayment).filter(InvoicePayment.id == payment_id).first()
    if not zahlung:
        raise HTTPException(404, "Zahlung nicht gefunden")

    inv = db.query(Invoice).filter(Invoice.id == zahlung.invoice_id).first()
    beschreibung = (f"Zahlung vom {zahlung.paid_at:%d.%m.%Y} über "
                    f"{float(zahlung.amount):.2f} zurückgenommen")

    db.delete(zahlung)
    db.flush()
    db.refresh(inv)

    alter_status = inv.status
    _recalc_payment_status(db, inv)
    inv.updated_by = current_user.email
    _audit(db, inv, "zahlung",
           changes={"status": {"alt": alter_status, "neu": inv.status}}
                   if alter_status != inv.status else None,
           note=beschreibung, user_email=current_user.email)

    db.commit()
    db.refresh(inv)
    return _zahlstand_antwort(inv)


# ─────────────────────────────────────────────────────────────────────────────
# Skonto
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{invoice_id}/skonto", response_model=SkontoVorschau)
def skonto_vorschau(
    invoice_id: UUID,
    paid_at: Optional[date] = Query(None, description="Zahlungsdatum; Standard: heute"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Was ein Skonto zum angegebenen Zahlungsdatum bedeuten würde — Betrag,
    Aufteilung auf die Steuersätze und die daraus folgende Steuerberichtigung.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    datum = paid_at or zeit.heute()
    _, offen, _ = _zahlstand(inv)
    betrag = skonto_service.betrag(inv)
    frist = skonto_service.frist_ende(inv)
    innerhalb = skonto_service.in_frist(inv, datum)

    hinweis = None
    if not skonto_service.vereinbart(inv):
        hinweis = "Für diesen Beleg ist kein Skonto vereinbart."
    elif not innerhalb:
        hinweis = (f"Die Skontofrist endete am {frist:%d.%m.%Y} — ein Abzug "
                   f"wäre eine freiwillige Zusage." if frist else None)

    return SkontoVorschau(
        invoice_id=inv.id, skonto_percent=inv.skonto_percent,
        skonto_days=inv.skonto_days, frist_ende=frist, in_frist=innerhalb,
        betrag=betrag, open_amount=offen,
        zeilen=[SkontoZeile(**z) for z in skonto_service.aufteilung(inv, betrag)],
        hinweis=hinweis,
    )


@router.post("/{invoice_id}/skonto", response_model=InvoicePaymentState)
def skonto_ausbuchen(
    invoice_id: UUID,
    body: SkontoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Bucht den Restbetrag als gewährten Skonto aus.

    Der Eintrag landet in ``invoice_payments`` mit ``payment_type='skonto'`` und
    dem **Zahlungsdatum** — daran hängt die Umsatzsteuer-Berichtigung nach
    § 16 UStG. Ohne Betragsangabe wird genau der offene Rest ausgebucht; das
    ist der Normalfall, wenn der Kunde gekürzt überwiesen hat.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if inv.doc_type not in ("rechnung", "gutschrift"):
        raise HTTPException(400, "Skonto gibt es nur auf Rechnungen und Gutschriften")
    if inv.status in ("entwurf", "storniert"):
        raise HTTPException(400, "Der Beleg ist nicht ausgestellt oder storniert")

    # Die Berichtigung wirkt im Monat der Zahlung — ist der zu, darf hier
    # nichts mehr entstehen.
    period_service.pruefe_periode_offen(db, body.paid_at, "gebucht")

    _, offen, _ = _zahlstand(inv)
    betrag = Decimal(str(body.amount)) if body.amount is not None else offen
    if betrag <= 0:
        raise HTTPException(400, "Der Skontobetrag muss größer als null sein")
    if betrag > offen:
        raise HTTPException(400, f"Der Skonto ({float(betrag):.2f}) übersteigt den "
                                 f"offenen Betrag ({float(offen):.2f})")

    zahlung = InvoicePayment(
        invoice_id=inv.id, paid_at=body.paid_at, amount=betrag,
        payment_type="skonto", method="verrechnung",
        note=body.note or "Skontoabzug", created_by=current_user.email,
    )
    db.add(zahlung)
    db.flush()
    db.refresh(inv)

    alter_status = inv.status
    _recalc_payment_status(db, inv)
    inv.updated_by = current_user.email

    aufteilung = skonto_service.aufteilung(inv, betrag)
    steuer = sum((z["steuer"] for z in aufteilung), Decimal("0"))
    _audit(db, inv, "skonto",
           changes={"status": {"alt": alter_status, "neu": inv.status}}
                   if alter_status != inv.status else None,
           note=f"Skonto {float(betrag):.2f} {inv.currency} zum "
                f"{body.paid_at:%d.%m.%Y} ausgebucht — davon "
                f"{float(steuer):.2f} Umsatzsteuer-Berichtigung (§ 16 UStG)",
           user_email=current_user.email)

    db.flush()
    if inv.status == "bezahlt":
        archive_invoice_pdf(db, inv, "bezahlt")
    db.commit()
    db.refresh(inv)
    return _zahlstand_antwort(inv)
