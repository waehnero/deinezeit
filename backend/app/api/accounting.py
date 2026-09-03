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
from app.services import positionen as positionen_service
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
def list_accounts(
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
def create_account(
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
def update_account(
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
def delete_account(
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
def set_default_erloes(
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

def _gruppe_beginnt(positionen: list, index: int) -> int:
    """
    Index, ab dem die Gruppe der Position bei ``index`` zählt.

    Die Gruppe reicht von der letzten Überschrift oder Zwischensumme davor —
    je nachdem, was zuletzt kam.
    """
    for i in range(index - 1, -1, -1):
        if positionen_service.typ(positionen[i]) in ("heading", "subtotal"):
            return i + 1
    return 0


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


def _konto_ust_code(konto_codes, konto_nr) -> Optional[str]:
    """USt-Code, den das Konto selbst im Kontenplan trägt (z.B. 4050 → UIG)."""
    if not konto_codes or not konto_nr:
        return None
    return konto_codes.get(str(konto_nr)) or None


def _ust_gruppen(inv, default_erloes: str, steuersaetze,
                 konto_codes_map=None) -> dict:
    """
    Buchungsgruppen eines Belegs: ``{(Erlöskonto, USt-Code): {net, tax, rate}}``.

    Eigene Funktion, weil zwei Auswerter sie brauchen — die Buchungszeilen des
    Belegs und die anteilige Verteilung eines später gewährten Skontos. Der
    Steuersatz bleibt in der Gruppe stehen, damit der Skonto daraus wieder
    Netto und Steuer trennen kann.
    """
    from decimal import Decimal
    from collections import defaultdict

    gruppen: dict = defaultdict(lambda: {"net": Decimal("0"), "tax": Decimal("0"),
                                         "rate": Decimal("0")})
    positionen = list(inv.positions)

    for pos in positionen:
        # Überschrift, Freitext und Zwischensumme tragen keinen Umsatz.
        if positionen_service.typ(pos) in positionen_service.GLIEDERUNG:
            continue
        net = pos.line_total or Decimal("0")
        rate = pos.tax_rate
        konto = pos.account_nr or default_erloes

        # Rabattzeile: Sie trägt selbst keinen Steuersatz, sondern mindert
        # die Sätze ihrer Gruppe anteilig. Ohne diese Aufteilung landete
        # der ganze Rabatt auf einem Konto und einem USt-Code.
        if positionen_service.typ(pos) == "discount":
            index = positionen.index(pos)
            gruppe_ab = _gruppe_beginnt(positionen, index)
            gruppe = positionen_service.gruppen_netto(positionen, gruppe_ab, index)
            basis = sum(gruppe.values(), Decimal("0"))
            for satz, anteil in positionen_service.rabatt_verteilen(
                    gruppe, basis, -net).items():
                code = tax_rates_service.ust_code_for(steuersaetze, satz)
                eintrag = gruppen[(konto, code)]
                eintrag["net"] -= anteil
                eintrag["tax"] -= (anteil * satz / 100).quantize(Decimal("0.01"))
                eintrag["rate"] = Decimal(str(satz or 0))
            continue

        if inv.tax_mode == "kleinunternehmer":
            ust_code = tax_rates_service.ust_code_for(steuersaetze, 0)
        else:
            ust_code = tax_rates_service.ust_code_for(steuersaetze, rate)
            # Bei steuerfreien Umsätzen sagt der Satz allein nicht, *warum*
            # keine Steuer anfällt: Ausfuhr, innergemeinschaftliche Lieferung
            # und Steuerbefreiung nach § 6 laufen über verschiedene Codes, und
            # alle drei kommen als „0 %" hier an — vergeben wurde bisher für
            # alle U00. Das Konto weiß es besser, denn 4040, 4050 und 4060
            # tragen im Kontenplan ihren eigenen USt-Code.
            #
            # Nur für Satz 0: Bei einem echten Satz bleibt der Satz maßgeblich.
            # Sonst würde eine 10-%-Position auf dem Konto 4000 (U20) still auf
            # den Normalsatz gebucht — der Fehler, den ``ust_code_for`` gerade
            # verhindert.
            if rate is not None and Decimal(str(rate)) == 0:
                konto_code = _konto_ust_code(konto_codes_map, konto)
                if konto_code:
                    ust_code = konto_code

        eintrag = gruppen[(konto, ust_code)]
        eintrag["net"] += net
        if inv.tax_mode != "kleinunternehmer" and rate is not None:
            eintrag["tax"] += (net * rate / 100).quantize(Decimal("0.01"))
            eintrag["rate"] = Decimal(str(rate))
    return gruppen


def _skonto_zeilen(db: Session, date_from, date_to, default_erloes: str,
                   default_debitor: str, steuersaetze, doc_type=None) -> list:
    """
    Buchungszeilen für gewährte Skonti — datiert auf den **Zahlungseingang**.

    Ein Skonto mindert das Entgelt und erfordert eine Umsatzsteuer-Berichtigung
    (§ 16 UStG) im Zeitraum der Zahlung. Deshalb hängt die Zeile am
    Zahlungsdatum und nicht am Belegdatum — die Rechnung kann längst in einem
    abgeschlossenen Monat liegen.

    Gebucht wird auf **dieselben Erlöskonten und USt-Codes wie der Beleg**,
    anteilig nach deren Bruttoanteil. Ein pauschales Sammelkonto wäre bequemer,
    würde aber bei einem Beleg mit zwei Erlöskonten das falsche entlasten.
    """
    from decimal import Decimal
    from app.models.invoice import InvoicePayment

    q = (db.query(InvoicePayment).join(Invoice, Invoice.id == InvoicePayment.invoice_id)
         .filter(InvoicePayment.payment_type == "skonto",
                 Invoice.is_recurring_template == False))
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    if date_from:
        q = q.filter(InvoicePayment.paid_at >= date_from)
    if date_to:
        q = q.filter(InvoicePayment.paid_at <= date_to)

    zeilen = []
    for zahlung in q.order_by(InvoicePayment.paid_at.asc()).all():
        inv = zahlung.invoice
        gruppen = _ust_gruppen(inv, default_erloes, steuersaetze)
        brutto_je_gruppe = {k: abs(v["net"] + v["tax"]) for k, v in gruppen.items()}
        gesamt = sum(brutto_je_gruppe.values(), Decimal("0"))
        if gesamt <= 0:
            continue

        contact_name, debitor_nr = "", ""
        if inv.contact_id:
            rec = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
            if rec:
                contact_name = rec.display_name or ""
                debitor_nr = _get_contact_nr(db, inv.contact_id, "debitor")

        # Ein Skonto mindert den Erlös (Rechnung) bzw. erhöht ihn wieder
        # (Gutschrift). Das Vorzeichen hängt an der Belegart, nicht am Betrag.
        richtung = Decimal("1") if inv.doc_type == "gutschrift" else Decimal("-1")
        betrag = abs(Decimal(str(zahlung.amount or 0)))
        rest = betrag
        schluessel = list(brutto_je_gruppe)

        for i, key in enumerate(schluessel):
            anteil = (rest if i == len(schluessel) - 1
                      else (betrag * brutto_je_gruppe[key] / gesamt).quantize(Decimal("0.01")))
            rest -= anteil
            if not anteil:
                continue
            satz = gruppen[key]["rate"]
            netto = (anteil * Decimal("100") / (Decimal("100") + satz)).quantize(Decimal("0.01"))
            steuer = anteil - netto
            konto, ust_code = key
            zeilen.append([
                zahlung.paid_at.strftime("%d.%m.%Y"),
                inv.number,
                f"Skonto {inv.number or ''}".strip(),
                konto, default_debitor, debitor_nr,
                f"{float(netto * richtung):.2f}".replace(".", ","),
                ust_code,
                f"{float(steuer * richtung):.2f}".replace(".", ","),
                f"{float(anteil * richtung):.2f}".replace(".", ","),
                inv.currency or "EUR", inv.number, contact_name,
            ])
    return zeilen


def _kreditor_konto(db: Session) -> str:
    """Standard-Kreditorensammelkonto (EKR 3300), sofern im Kontenplan vorhanden."""
    acc = db.query(AccountingAccount).filter(
        AccountingAccount.nr == "3300",
        AccountingAccount.is_active == True,
    ).first()
    return acc.nr if acc else "3300"


@router.get("/export/bmd-eingang")
def export_bmd_eingang(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Buchungsjournal der **Eingangsrechnungen** (CSV, Semikolon-getrennt).

    Bewusst eine eigene Datei und nicht in den Verkaufsexport gemischt: Dort
    heißen die Spalten „Erlöskonto" und „Debitornummer". Eingangsrechnungen
    dort einzureihen hieße, Aufwand unter Erlös und Kreditoren unter Debitoren
    zu stellen — die Kanzlei müsste raten, was gemeint ist.

    Der USt-Code kommt aus derselben gepflegten Tabelle wie beim Verkauf. Ob
    die Kanzlei für Vorsteuer andere Codes verwendet, weiß nur sie; die Spalte
    „Steuerart" nennt deshalb zusätzlich den Sachverhalt im Klartext.
    """
    from decimal import Decimal
    from app.models.purchase import PurchaseInvoice, TAX_KIND_LABELS

    q = db.query(PurchaseInvoice).filter(PurchaseInvoice.status != "storniert")
    if date_from:
        q = q.filter(PurchaseInvoice.date >= date_from)
    if date_to:
        q = q.filter(PurchaseInvoice.date <= date_to)
    belege = q.order_by(PurchaseInvoice.date.asc()).all()

    steuersaetze = tax_rates_service.get_tax_rates(db)
    kreditor = _kreditor_konto(db)
    default_aufwand = "7000"

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Datum", "Beleg-Nr", "Rechnungs-Nr Lieferant", "Buchungstext",
        "Aufwandskonto", "Kreditorkonto", "Nettobetrag", "USt-Code",
        "Steuerbetrag", "Bruttobetrag", "Steuerart", "Vorsteuer abziehbar",
        "Währung", "Lieferant",
    ])

    for inv in belege:
        aufwand = inv.account_nr or default_aufwand
        text = inv.title or f"Eingangsrechnung {inv.supplier_name or ''}".strip()
        for zeile in inv.taxes:
            satz = zeile.tax_rate
            code = tax_rates_service.ust_code_for(steuersaetze, satz)
            netto = Decimal(str(zeile.net_amount or 0))
            steuer = Decimal(str(zeile.tax_amount or 0))
            writer.writerow([
                inv.date.strftime("%d.%m.%Y"),
                inv.internal_number or "",
                inv.supplier_number or "",
                text,
                aufwand,
                kreditor,
                f"{float(netto):.2f}".replace(".", ","),
                code,
                f"{float(steuer):.2f}".replace(".", ","),
                f"{float(netto + steuer):.2f}".replace(".", ","),
                TAX_KIND_LABELS.get(inv.tax_kind, inv.tax_kind),
                "ja" if inv.vat_deductible else "nein",
                inv.currency or "EUR",
                inv.supplier_name or "",
            ])

    output.seek(0)
    zeitraum = f"{date_from or 'alle'}_{date_to or 'alle'}"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="bmd_eingang_{zeitraum}.csv"'},
    )


@router.get("/export/bmd")
def export_bmd(
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
    # USt-Codes des Kontenplans, einmal gelesen: 4050 trägt UIG, 4060 URC,
    # 4040 U00. Bei steuerfreien Positionen entscheidet dieser Code, weil der
    # Steuersatz allein den Sachverhalt nicht kennt.
    konto_codes = {k.nr: k.ust_code for k in db.query(AccountingAccount).all()
                   if k.ust_code}

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

        # Buchungsgruppen je Erlöskonto und USt-Code (Erlöskonto: Position >
        # Artikel > Vorgabe). Die Regel steckt in _ust_gruppen, weil der
        # Skonto-Durchlauf weiter unten dieselbe Aufteilung braucht.
        from decimal import Decimal
        ust_groups = _ust_gruppen(inv, default_erloes, steuersaetze, konto_codes)

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

    # Gewährte Skonti als eigene Zeilen, datiert auf den Zahlungseingang.
    for zeile in _skonto_zeilen(db, date_from, date_to, default_erloes,
                                default_debitor, steuersaetze, doc_type):
        writer.writerow(zeile)

    output.seek(0)
    period = f"{date_from or 'alle'}_{date_to or 'alle'}"
    filename = f"bmd_export_{period}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
