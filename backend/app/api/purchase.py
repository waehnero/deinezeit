"""
Eingangsrechnungen (Kreditoren) und Vorsteuer.

Gegenstück zu ``api/invoice.py``, aber bewusst schlanker: Eine
Eingangsrechnung wird nicht erzeugt, sondern abgeschrieben. Es gibt daher
keinen Entwurfs-Status, keine PDF-Erzeugung und keinen Versand — dafür ein
hinterlegtes Original und die Trennung der Steuerarten, an der die
Voranmeldung hängt.

Was übernommen wird, weil es sich auf der Verkaufsseite bewährt hat: die
Periodensperre (in einen abgeschlossenen Monat wird nichts mehr gebucht), die
Fälligkeitsstaffel der offenen Posten und der Umgang mit Zahlungen.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date
from decimal import Decimal

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin, require_loeschen
from app.models.user import User
from app.models.masterdata import EntityRecord
from app.models.purchase import (PurchaseInvoice, PurchaseInvoiceTax,
                                 PurchasePayment, TAX_KINDS)
from app.services import period_service
from app.services import vorsteuer as vorsteuer_service
from app.services import kreditor
from app.schemas.purchase import (
    PurchaseInvoiceCreate, PurchaseInvoiceUpdate, PurchaseInvoiceResponse,
    PurchaseInvoiceListItem, PurchasePaymentCreate, PurchasePaymentResponse,
    PurchasePaymentState, PurchaseOpenItem, PurchaseOpenItemsBySupplier,
    PurchaseOpenItemsResponse, VorsteuerZeile, VorsteuerResponse,
)
from app.core import zeit
from app.core.http import content_disposition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/purchase-invoices", tags=["Eingangsrechnungen"])

CENT = Decimal("0.01")
MAX_UPLOAD = 20 * 1024 * 1024
ERLAUBTE_TYPEN = ("application/pdf", "image/jpeg", "image/png", "image/webp")

# Fälligkeitsstaffel wie auf der Debitorenseite — dieselben Grenzen, damit
# beide Auswertungen vergleichbar bleiben.
BUCKETS = [
    ("nicht_faellig", 0), ("b1_30", 30), ("b31_60", 60), ("b61_90", 90),
    ("b90_plus", 10 ** 6),
]


def _bucket_fuer(tage: int) -> str:
    if tage <= 0:
        return "nicht_faellig"
    for name, grenze in BUCKETS[1:]:
        if tage <= grenze:
            return name
    return "b90_plus"


def _dec(wert) -> Decimal:
    try:
        return Decimal(str(wert or 0))
    except Exception:
        return Decimal("0")


def _zahlstand(inv: PurchaseInvoice) -> tuple:
    gezahlt = sum((_dec(z.amount) for z in inv.payments), Decimal("0"))
    offen = (_dec(inv.gross_total) - gezahlt).quantize(CENT)
    return gezahlt, offen, offen < 0


def _status_neu_ableiten(inv: PurchaseInvoice) -> None:
    """Leitet den Status aus den Zahlungen ab. Storno bleibt Storno."""
    if inv.status == "storniert":
        return
    gezahlt, offen, _ueber = _zahlstand(inv)
    inv.paid_amount = gezahlt if inv.payments else None
    inv.paid_at = max((z.paid_at for z in inv.payments), default=None)
    if not inv.payments:
        inv.status = "offen"
    elif offen <= Decimal("0.00"):
        inv.status = "bezahlt"
    else:
        inv.status = "teilbezahlt"


def _naechste_nummer(db: Session, jahr: int) -> tuple:
    """
    Laufende Nummer für die Ablage, Format ``ER-<Jahr>-<lfd>``.

    Bewusst ohne den Nummernkreis-Mechanismus der Verkaufsbelege: Dort ist die
    Lückenlosigkeit gesetzlich gefordert (§ 11 UStG), hier ist die Nummer eine
    reine Ordnungshilfe für die eigene Ablage.
    """
    hoechste = (db.query(PurchaseInvoice.sequence)
                .filter(PurchaseInvoice.year == jahr)
                .order_by(PurchaseInvoice.sequence.desc()).first())
    naechste = (hoechste[0] or 0) + 1 if hoechste else 1
    return f"ER-{jahr}-{naechste:03d}", naechste


def _lieferant_uebernehmen(db: Session, inv: PurchaseInvoice, supplier_id) -> None:
    """Friert Name und UID des Lieferanten am Beleg ein."""
    inv.supplier_id = supplier_id
    if not supplier_id:
        return
    rec = db.query(EntityRecord).filter(EntityRecord.id == supplier_id).first()
    if rec:
        inv.supplier_name = rec.display_name or ""
        inv.supplier_uid = (rec.data or {}).get("uid") or None


def _steuerzeilen_setzen(db: Session, inv: PurchaseInvoice, zeilen) -> None:
    for alt in list(inv.taxes):
        db.delete(alt)
    inv.taxes = []
    db.flush()
    for i, z in enumerate(zeilen or []):
        db.add(PurchaseInvoiceTax(
            purchase_invoice_id=inv.id, tax_rate=z.tax_rate,
            net_amount=z.net_amount or 0, tax_amount=z.tax_amount or 0,
            sort_order=i,
        ))
    db.flush()
    db.refresh(inv)
    netto, steuer, brutto = vorsteuer_service.summen(inv)
    inv.net_total, inv.tax_total, inv.gross_total = netto, steuer, brutto


def _pruefe_eingaben(body) -> None:
    if body.tax_kind not in TAX_KINDS:
        raise HTTPException(400, f"Unbekannte Steuerart: {body.tax_kind}")
    if not body.taxes:
        raise HTTPException(400, "Ohne Beträge lässt sich die Rechnung nicht buchen — "
                                 "mindestens eine Steuerzeile ist nötig.")
    if not (body.supplier_id or (body.title or "").strip()):
        raise HTTPException(400, "Bitte einen Lieferanten wählen oder wenigstens einen "
                                 "Betreff angeben, damit der Beleg auffindbar bleibt.")


# ─────────────────────────────────────────────────────────────────────────────
# Auswertungen — vor den Platzhalter-Routen, sonst schluckt {invoice_id} sie
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/vorsteuer", response_model=VorsteuerResponse)
def get_vorsteuer(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Vorsteuer und selbst geschuldete Steuer des Zeitraums, je Kennzahl."""
    daten = vorsteuer_service.auswertung(db, date_from, date_to)
    return VorsteuerResponse(
        date_from=date_from, date_to=date_to,
        zeilen=[VorsteuerZeile(**z) for z in daten["zeilen"]],
        vorsteuer_gesamt=daten["vorsteuer_gesamt"],
        schuld_gesamt=daten["schuld_gesamt"],
        nicht_abziehbar=daten["nicht_abziehbar"],
        beleg_anzahl=daten["beleg_anzahl"],
        hinweise=daten["hinweise"],
    )


@router.get("/open-items", response_model=PurchaseOpenItemsResponse)
def get_open_items(
    supplier_id: Optional[UUID] = Query(None),
    stichtag: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Offene Posten der Kreditoren: Was schulde ich wem, und seit wann."""
    heute = stichtag or zeit.heute()
    q = db.query(PurchaseInvoice).filter(PurchaseInvoice.status != "storniert")
    if supplier_id:
        q = q.filter(PurchaseInvoice.supplier_id == supplier_id)
    belege = q.order_by(PurchaseInvoice.due_date.asc().nullslast(),
                        PurchaseInvoice.date.asc()).all()

    items, je_lieferant = [], {}
    buckets = {name: Decimal("0") for name, _ in BUCKETS}
    gesamt = Decimal("0")

    for b in belege:
        gezahlt, offen, _ueber = _zahlstand(b)
        if abs(offen) < CENT:
            continue
        tage = (heute - b.due_date).days if b.due_date else 0
        bucket = _bucket_fuer(tage)
        buckets[bucket] += offen
        gesamt += offen

        eintrag = je_lieferant.setdefault(
            b.supplier_id, {"supplier_id": b.supplier_id,
                            "supplier_name": b.supplier_name,
                            "open_amount": Decimal("0"), "count": 0})
        eintrag["open_amount"] += offen
        eintrag["count"] += 1

        items.append(PurchaseOpenItem(
            id=b.id, internal_number=b.internal_number,
            supplier_number=b.supplier_number, supplier_id=b.supplier_id,
            supplier_name=b.supplier_name, date=b.date, due_date=b.due_date,
            title=b.title, gross_total=b.gross_total, paid_total=gezahlt,
            open_amount=offen, status=b.status,
            days_overdue=max(0, tage), bucket=bucket,
        ))

    return PurchaseOpenItemsResponse(
        items=items,
        by_supplier=sorted((PurchaseOpenItemsBySupplier(**e) for e in je_lieferant.values()),
                           key=lambda e: abs(e.open_amount), reverse=True),
        buckets={k: float(v) for k, v in buckets.items()},
        total_open=gesamt, count=len(items),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[PurchaseInvoiceListItem])
def list_invoices(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PurchaseInvoice)
    if status:
        q = q.filter(PurchaseInvoice.status == status)
    if supplier_id:
        q = q.filter(PurchaseInvoice.supplier_id == supplier_id)
    if date_from:
        q = q.filter(PurchaseInvoice.date >= date_from)
    if date_to:
        q = q.filter(PurchaseInvoice.date <= date_to)
    if search:
        muster = f"%{search}%"
        q = q.filter(
            PurchaseInvoice.supplier_name.ilike(muster) |
            PurchaseInvoice.supplier_number.ilike(muster) |
            PurchaseInvoice.internal_number.ilike(muster) |
            PurchaseInvoice.title.ilike(muster)
        )

    ergebnis = []
    for b in q.order_by(PurchaseInvoice.date.desc(),
                        PurchaseInvoice.created_at.desc()).all():
        _gezahlt, offen, _u = _zahlstand(b)
        ergebnis.append(PurchaseInvoiceListItem(
            id=b.id, internal_number=b.internal_number,
            supplier_name=b.supplier_name, supplier_number=b.supplier_number,
            date=b.date, due_date=b.due_date, title=b.title,
            tax_kind=b.tax_kind, net_total=b.net_total, tax_total=b.tax_total,
            gross_total=b.gross_total, currency=b.currency, status=b.status,
            has_file=bool(b.file_key),
            open_amount=offen if b.status != "storniert" else Decimal("0"),
        ))
    return ergebnis


@router.post("", response_model=PurchaseInvoiceResponse)
def create_invoice(
    body: PurchaseInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erfasst eine Lieferantenrechnung.

    Maßgeblich für die Voranmeldung ist das **Rechnungsdatum**, nicht der Tag
    der Erfassung — deshalb greift die Periodensperre auf dieses Datum.
    """
    _pruefe_eingaben(body)
    period_service.pruefe_periode_offen(db, body.date, "erfasst")

    # Aufwandskonto vorbelegen, wenn keines angegeben wurde: Ein Lieferant wird
    # fast immer auf dasselbe Konto gebucht, und das steht seit Migration 0057
    # am Kontakt. Nur beim **Anlegen** — beim Ändern heißt ein leeres Feld, dass
    # jemand das Konto absichtlich entfernt hat, und es wortlos wieder zu
    # füllen wäre eine Änderung gegen den erklärten Willen.
    konto = body.account_nr
    if not str(konto or "").strip():
        konto = kreditor.aufwandskonto_fuer_lieferant(db, body.supplier_id)

    nummer, lfd = _naechste_nummer(db, body.date.year)
    inv = PurchaseInvoice(
        internal_number=nummer, year=body.date.year, sequence=lfd,
        supplier_number=body.supplier_number, date=body.date,
        delivery_date=body.delivery_date, due_date=body.due_date,
        tax_kind=body.tax_kind, vat_deductible=body.vat_deductible,
        vat_note=body.vat_note, account_nr=konto,
        title=body.title, note=body.note, currency=body.currency,
        created_by=current_user.email, updated_by=current_user.email,
    )
    _lieferant_uebernehmen(db, inv, body.supplier_id)
    db.add(inv)
    db.flush()
    _steuerzeilen_setzen(db, inv, body.taxes)
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{invoice_id}", response_model=PurchaseInvoiceResponse)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    return inv


@router.put("/{invoice_id}", response_model=PurchaseInvoiceResponse)
def update_invoice(
    invoice_id: UUID,
    body: PurchaseInvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ändert eine erfasste Rechnung.

    Anders als beim Verkaufsbeleg gibt es hier keine Belegsperre: Wir haben den
    Beleg nicht ausgestellt, ein Tippfehler bei der Erfassung ist kein
    Verstoß gegen die Belegkette. Die Periodensperre gilt aber für **beide**
    Daten — aus einem abgeschlossenen Monat heraus und in ihn hinein.
    """
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege lassen sich nicht mehr ändern")
    _pruefe_eingaben(body)
    period_service.pruefe_periode_offen(db, inv.date, "geändert")
    period_service.pruefe_periode_offen(db, body.date, "gebucht")

    inv.supplier_number = body.supplier_number
    inv.date = body.date
    inv.delivery_date = body.delivery_date
    inv.due_date = body.due_date
    inv.tax_kind = body.tax_kind
    inv.vat_deductible = body.vat_deductible
    inv.vat_note = body.vat_note
    inv.account_nr = body.account_nr
    inv.title = body.title
    inv.note = body.note
    inv.currency = body.currency
    inv.updated_by = current_user.email
    _lieferant_uebernehmen(db, inv, body.supplier_id)
    _steuerzeilen_setzen(db, inv, body.taxes)
    _status_neu_ableiten(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/cancel", response_model=PurchaseInvoiceResponse,
             dependencies=[Depends(require_loeschen("buchhaltung"))])
def cancel_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Wie beim Verkaufsbeleg: Stornieren ist fachlich ein Löschvorgang und
    # verlangt daher das Löschrecht, nicht nur das Schreibrecht.
    """
    Storniert die Erfassung (Fehlbuchung, Doppelerfassung).

    Der Datensatz bleibt bestehen und wird aus allen Auswertungen genommen —
    gelöscht wird nichts, damit die Erfassung nachvollziehbar bleibt.
    """
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    period_service.pruefe_periode_offen(db, inv.date, "storniert")
    if inv.payments:
        raise HTTPException(400, "Zu diesem Beleg sind Zahlungen erfasst — bitte "
                                 "zuerst die Zahlungen zurücknehmen.")
    inv.status = "storniert"
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Löscht eine Fehlerfassung endgültig — nur für Admins und nur, solange keine
    Zahlung daran hängt. Der Regelfall ist das Stornieren.
    """
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    period_service.pruefe_periode_offen(db, inv.date, "gelöscht")
    if inv.payments:
        raise HTTPException(400, "Zu diesem Beleg sind Zahlungen erfasst")
    db.delete(inv)
    db.commit()
    return Response(status_code=204)


# ─────────────────────────────────────────────────────────────────────────────
# Zahlungen
# ─────────────────────────────────────────────────────────────────────────────

def _zahlstand_antwort(inv: PurchaseInvoice) -> PurchasePaymentState:
    gezahlt, offen, ueber = _zahlstand(inv)
    return PurchasePaymentState(
        purchase_invoice_id=inv.id, status=inv.status,
        gross_total=inv.gross_total, paid_total=gezahlt,
        open_amount=offen, overpaid=ueber,
        payments=[PurchasePaymentResponse.model_validate(z) for z in inv.payments],
    )


@router.get("/{invoice_id}/payments", response_model=PurchasePaymentState)
def list_payments(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    return _zahlstand_antwort(inv)


@router.post("/{invoice_id}/payments", response_model=PurchasePaymentState)
def add_payment(
    invoice_id: UUID,
    body: PurchasePaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erfasst einen Zahlungsausgang. Teilzahlungen sind vorgesehen.

    Die Periodensperre gilt hier bewusst NICHT — gleiche Entscheidung wie auf
    der Verkaufsseite: Eine Zahlung ändert nichts am Belegjournal des
    abgeschlossenen Monats. Wer eine Januarrechnung im März zahlt, muss das
    erfassen können, auch wenn Januar längst zu ist.
    """
    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege können keine Zahlung erhalten")
    if _dec(body.amount) == 0:
        raise HTTPException(400, "Der Zahlbetrag darf nicht null sein")

    db.add(PurchasePayment(
        purchase_invoice_id=inv.id, paid_at=body.paid_at, amount=body.amount,
        method=body.method, reference=body.reference, note=body.note,
        created_by=current_user.email,
    ))
    db.flush()
    db.refresh(inv)
    _status_neu_ableiten(inv)
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return _zahlstand_antwort(inv)


@router.delete("/payments/{payment_id}", response_model=PurchasePaymentState)
def delete_payment(
    payment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Nimmt einen Zahlungsausgang zurück (Fehleingabe)."""
    zahlung = db.query(PurchasePayment).filter(PurchasePayment.id == payment_id).first()
    if not zahlung:
        raise HTTPException(404, "Zahlung nicht gefunden")
    inv = db.query(PurchaseInvoice).filter(
        PurchaseInvoice.id == zahlung.purchase_invoice_id).first()
    db.delete(zahlung)
    db.flush()
    db.refresh(inv)
    _status_neu_ableiten(inv)
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return _zahlstand_antwort(inv)


# ─────────────────────────────────────────────────────────────────────────────
# Originalbeleg
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/file", response_model=PurchaseInvoiceResponse)
def upload_file(
    invoice_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Hinterlegt das Original (PDF oder Foto).

    Ohne Beleg ist der Vorsteuerabzug im Prüfungsfall gefährdet — die
    Auswertung weist deshalb aus, wie viele Rechnungen ohne Original erfasst
    sind.
    """
    from app.services import storage_service

    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    if file.content_type and file.content_type not in ERLAUBTE_TYPEN:
        raise HTTPException(400, f"Dateityp {file.content_type} wird nicht unterstützt. "
                                 f"Erlaubt sind PDF, JPEG, PNG und WebP.")
    daten = file.file.read()
    if len(daten) > MAX_UPLOAD:
        raise HTTPException(400, "Datei zu groß (max. 20 MB)")

    endung = (file.filename or "beleg").rsplit(".", 1)[-1].lower()[:8] or "pdf"
    schluessel = f"eingangsrechnungen/{inv.date.year}/{inv.id}.{endung}"
    # Speicher festhalten: Nach einem Wechsel auf einen anderen Anbieter liegt
    # das Original weiter im alten und wäre sonst nicht mehr auffindbar.
    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(schluessel, daten,
                                    file.content_type or "application/pdf",
                                    db=db, backend=backend)
    except Exception as exc:
        logger.exception("Fehler bei purchase: %s", exc)
        raise HTTPException(500, "Die Datei konnte nicht gespeichert werden (Ursache im Serverlog).")

    inv.file_key = schluessel
    inv.file_name = file.filename
    inv.file_mimetype = file.content_type
    inv.file_provider = backend
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return inv


@router.get("/{invoice_id}/file")
def get_file(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Liefert das hinterlegte Original aus."""
    from app.services import storage_service

    inv = db.query(PurchaseInvoice).filter(PurchaseInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Eingangsrechnung nicht gefunden")
    if not inv.file_key:
        raise HTTPException(404, "Zu diesem Beleg ist kein Original hinterlegt")
    try:
        # Provider der Datei, nicht der gerade aktive — siehe upload_file.
        daten, mime = storage_service.download_file(inv.file_key, db=db,
                                                    backend=inv.file_provider)
    except Exception:
        raise HTTPException(404, "Das Original ist im Speicher nicht auffindbar")
    name = inv.file_name or f"{inv.internal_number or 'beleg'}.pdf"
    return Response(content=daten, media_type=mime or inv.file_mimetype or "application/pdf",
                    headers={"Content-Disposition": content_disposition("inline", name)})
