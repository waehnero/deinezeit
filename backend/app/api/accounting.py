"""
Buchhaltungs-API
================
- Kontenplan (CRUD, EKR-Reset)
- BMD-Export für Rechnungen
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date
import io
import csv

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.accounting import AccountingAccount
from app.models.invoice import Invoice, InvoicePosition, InvoiceSettings
from app.models.masterdata import EntityRecord
from app.models.settings import Setting
from app.services import tax_rates as tax_rates_service
from pydantic import BaseModel

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    nr: str
    name: str
    typ: str
    ust_code: Optional[str] = None
    beschreibung: Optional[str] = None
    is_active: bool = True
    is_default_erloes: bool = False

class AccountUpdate(AccountCreate):
    pass

class AccountResponse(AccountCreate):
    id: UUID
    class Config:
        from_attributes = True


# ── Kontenplan ────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=List[AccountResponse])
async def list_accounts(
    typ: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(AccountingAccount)
    if active_only:
        q = q.filter(AccountingAccount.is_active == True)
    if typ:
        q = q.filter(AccountingAccount.typ == typ)
    return q.order_by(AccountingAccount.nr).all()


@router.post("/accounts", response_model=AccountResponse)
async def create_account(
    body: AccountCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    existing = db.query(AccountingAccount).filter_by(nr=body.nr).first()
    if existing:
        raise HTTPException(400, f"Konto {body.nr} existiert bereits")
    acc = AccountingAccount(**body.model_dump())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@router.put("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    body: AccountUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    acc = db.query(AccountingAccount).filter(AccountingAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404, "Konto nicht gefunden")
    for k, v in body.model_dump().items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete("/accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    acc = db.query(AccountingAccount).filter(AccountingAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404, "Konto nicht gefunden")
    db.delete(acc)
    db.commit()


@router.post("/accounts/{account_id}/set-default-erloes", response_model=AccountResponse)
async def set_default_erloes(
    account_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Setzt dieses Konto als Standard-Erlöskonto (hebt andere auf)."""
    db.query(AccountingAccount).update({AccountingAccount.is_default_erloes: False})
    acc = db.query(AccountingAccount).filter(AccountingAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404, "Konto nicht gefunden")
    acc.is_default_erloes = True
    db.commit()
    db.refresh(acc)
    return acc


# ── BMD-Export ────────────────────────────────────────────────────────────────

# BMD NTCS / Classic Buchungsjournal-Format
# Spalten: Datum; Belegnummer; Text; Konto; Gegenkonto; Betrag; USt-Code; USt-Betrag; Währung
#
# Die USt-Codes stehen nicht mehr hier, sondern werden je Steuersatz in den
# Verkaufseinstellungen gepflegt (services/tax_rates.py). Grund: BMD-Codes sind
# kanzleiabhängig, und die frühere Tabelle fiel bei unbekannten Sätzen still
# auf "U20" zurück — ein 13-%-Umsatz wurde damit als 20 % gebucht.

# Buchungsrelevante Belegarten. Angebot, Auftragsbestätigung und Lieferschein
# sind keine Umsätze und dürfen nie in der Buchhaltung landen.
BOOKABLE_DOC_TYPES = ("rechnung", "gutschrift")

# Buchungstext, wenn am Beleg kein Titel gepflegt ist
DOC_TYPE_TEXT = {"rechnung": "Rechnung", "gutschrift": "Gutschrift"}


def _get_contact_nr(db: Session, contact_id, contact_typ: str) -> str:
    """Liest Debitor- oder Kreditornummer aus dem Kontakt-Datensatz."""
    if not contact_id:
        return ""
    record = db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()
    if not record or not record.data:
        return ""
    typ = (record.data.get("typ") or "").lower()
    if "lieferant" in typ or contact_typ == "kreditor":
        return str(record.data.get("kreditornummer", "") or "")
    return str(record.data.get("debitornummer", "") or "")


def _default_erloes_konto(db: Session) -> str:
    acc = db.query(AccountingAccount).filter(
        AccountingAccount.is_default_erloes == True,
        AccountingAccount.is_active == True,
    ).first()
    return acc.nr if acc else "4000"


def _debitor_konto(db: Session) -> str:
    """Standard-Debitorenkonto."""
    acc = db.query(AccountingAccount).filter(
        AccountingAccount.nr == "2000",
        AccountingAccount.is_active == True,
    ).first()
    return acc.nr if acc else "2000"


@router.get("/export/bmd")
async def export_bmd(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    # Leer = alle buchungsrelevanten Belegarten (Rechnung UND Gutschrift).
    # Stand hier früher auf "rechnung" — dadurch fehlten Gutschriften im Export.
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Exportiert die buchungsrelevanten Belege als BMD-Buchungsjournal
    (CSV, Semikolon-getrennt).

    Format je Buchungszeile (eine pro Erlöskonto und USt-Satz pro Beleg):
    Datum; Belegnummer; Buchungstext; Erlöskonto; Debitorenkonto/Debitornr;
    Nettobetrag; USt-Code; USt-Betrag; Währung; Rechnungsnummer; Kontaktname

    Umfang: **Rechnungen und Gutschriften**. Ohne ``doc_type`` werden beide
    exportiert — Gutschriften wurden bisher übersehen, weil der Vorgabewert
    auf "rechnung" stand.

    Stornierte Belege werden nur dann exportiert, wenn zum Storno eine
    Gutschrift erzeugt wurde (``cancel_mode = with_credit``): Dann sind beide
    Belege gebucht und heben einander auf. Beim reinen Status-Storno
    (``status_only``) gab es keine Buchung, der Beleg bleibt außen vor.
    """
    if doc_type and doc_type not in BOOKABLE_DOC_TYPES:
        raise HTTPException(
            400,
            f"'{doc_type}' ist nicht buchungsrelevant. Für die Buchhaltung "
            f"kommen nur {' und '.join(BOOKABLE_DOC_TYPES)} in Frage.",
        )

    q = db.query(Invoice).filter(
        Invoice.is_recurring_template == False,
        Invoice.doc_type.in_([doc_type] if doc_type else list(BOOKABLE_DOC_TYPES)),
        Invoice.status != "entwurf",
        or_(Invoice.status != "storniert", Invoice.cancel_mode == "with_credit"),
    )
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    invoices = q.order_by(Invoice.date.asc(), Invoice.number.asc()).all()

    default_erloes = _default_erloes_konto(db)
    default_debitor = _debitor_konto(db)
    steuersaetze = tax_rates_service.get_tax_rates(db)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    # Header
    writer.writerow([
        "Datum", "Belegnummer", "Buchungstext",
        "Erlöskonto", "Debitorkonto", "Debitornummer",
        "Nettobetrag", "USt-Code", "USt-Betrag", "Bruttobetrag",
        "Währung", "Rechnungsnummer", "Kontakt",
    ])

    for inv in invoices:
        contact_name = ""
        debitor_nr = ""
        if inv.contact_id:
            rec = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
            if rec:
                contact_name = rec.display_name or ""
                debitor_nr = _get_contact_nr(db, inv.contact_id, "debitor")

        # Gruppiere Positionen nach USt-Satz
        from decimal import Decimal
        from collections import defaultdict
        ust_groups: dict = defaultdict(lambda: {"net": Decimal("0"), "tax": Decimal("0")})

        for pos in inv.positions:
            if pos.pos_type == "text":
                continue
            net = pos.line_total or Decimal("0")
            rate = pos.tax_rate
            if inv.tax_mode == "kleinunternehmer":
                ust_code = tax_rates_service.ust_code_for(steuersaetze, 0)
            else:
                ust_code = tax_rates_service.ust_code_for(steuersaetze, rate)

            # Erlöskonto: aus Position > Artikel > Default
            erloes_konto = pos.account_nr or default_erloes

            ust_groups[(erloes_konto, ust_code)]["net"] += net
            if inv.tax_mode != "kleinunternehmer" and rate is not None:
                ust_groups[(erloes_konto, ust_code)]["tax"] += (net * rate / 100).quantize(Decimal("0.01"))

        for (erloes_konto, ust_code), amounts in ust_groups.items():
            net = amounts["net"]
            tax = amounts["tax"]

            # Gutschriften wirken immer umsatzmindernd.
            # Wichtig: Storno-Gutschriften tragen bereits negative Mengen und
            # damit negative Beträge. Ein zusätzliches Umdrehen des Vorzeichens
            # hätte sie wieder positiv gemacht — die Gutschrift wäre als Umsatz
            # gebucht worden. Deshalb wird der Betrag nicht gedreht, sondern
            # auf negativ normiert (greift auch bei manuell erfassten
            # Gutschriften mit positiven Beträgen).
            if inv.doc_type == "gutschrift":
                net = -abs(net)
                tax = -abs(tax)
            gross = net + tax

            writer.writerow([
                inv.date.strftime("%d.%m.%Y"),
                inv.number,
                inv.title or f"{DOC_TYPE_TEXT.get(inv.doc_type, 'Beleg')} {inv.number}",
                erloes_konto,
                default_debitor,
                debitor_nr,
                f"{float(net):.2f}".replace(".", ","),
                ust_code,
                f"{float(tax):.2f}".replace(".", ","),
                f"{float(gross):.2f}".replace(".", ","),
                inv.currency or "EUR",
                inv.number,
                contact_name,
            ])

    output.seek(0)
    period = f"{date_from or 'alle'}_{date_to or 'alle'}"
    filename = f"bmd_export_{period}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
