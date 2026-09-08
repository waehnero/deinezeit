"""
Verkauf – Statusaktionen: Stornieren, bezahlt setzen, Statuswechsel,
Umwandlung Angebot → AB → Rechnung, Abrechnung in Stufen, Duplizieren.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID
from decimal import Decimal
import logging

from app.db.base import get_db
from app.api.deps import (get_current_user, require_loeschen, require_modul_rechte)
from app.models.user import User
from app.models.invoice import (Invoice, InvoicePosition, InvoiceAttachment,
                                 InvoiceSettings,
                                 InvoicePayment)
from app.services.invoice_snapshot import ensure_recipient_snapshot
from app.services.invoice_archive import archive_invoice_pdf
from app.services import period_service
from app.services import positionen as positionen_service
from app.services import angebot as angebot_service
from app.services import anzahlung as anzahlung_service
from app.schemas.invoice import (
    InvoiceResponse, InvoiceCancelRequest, InvoiceMarkPaidRequest,
    InvoiceDuplicateRequest, AnzahlungRequest, SchlussrechnungRequest,
    AbzugZeile, StrangBeleg, StrangResponse,
)
from app.core import zeit

from app.api.invoice_common import (
    DOC_TYPE_LABELS_DE,
    _audit,
    _audit_changes,
    _calc_totals,
    _finalize,
    _next_number,
    _pruefe_periode,
    _pruefe_pflichtangaben,
    _recalc_payment_status,
    _sync_time_entry_status,
    _zahlstand,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Aktionen
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse,
             dependencies=[Depends(require_loeschen("verkauf"))])
def cancel_invoice(
    invoice_id: UUID,
    body: InvoiceCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Zusätzlich zur methodenbasierten Prüfung des Routers (POST → Ändern)
    # verlangt das Stornieren ausdrücklich das LÖSCHRECHT. Ein ausgestellter
    # Beleg lässt sich nicht löschen, das Stornieren ist der einzige Weg, ihn
    # unwirksam zu machen — fachlich also ein Löschvorgang. Wer Rechnungen
    # schreiben darf, soll sie nicht zwangsläufig entwerten können.
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Bereits storniert")
    if inv.doc_type != "rechnung":
        raise HTTPException(400, "Nur Rechnungen können storniert werden")
    if inv.status == "entwurf":
        raise HTTPException(
            400,
            "Entwürfe werden gelöscht, nicht storniert — sie wurden nie "
            "ausgestellt und tragen noch keine Belegnummer.",
        )

    _pruefe_periode(db, inv, "storniert")

    alter_status = inv.status
    ensure_recipient_snapshot(db, inv)
    inv.status = "storniert"
    inv.cancel_mode = body.cancel_mode
    inv.updated_by = current_user.email
    _sync_time_entry_status(db, inv)   # Storno → Zeiten wieder freigeben
    _audit(db, inv, "storniert",
           changes={"status": {"alt": alter_status, "neu": "storniert"}},
           note=("Storno mit Gutschrift" if body.cancel_mode == "with_credit"
                 else "Storno ohne Gegenbuchung"),
           user_email=current_user.email)

    credit_note = None
    if body.cancel_mode == "with_credit":
        year = zeit.jetzt().year
        sequence, number = _next_number(db, "gutschrift", year)
        credit_note = Invoice(
            doc_type="gutschrift",
            number=number,
            year=year,
            sequence=sequence,
            contact_id=inv.contact_id,
            project_id=inv.project_id,
            related_invoice_id=inv.id,
            title=f"Gutschrift zu {inv.number}",
            date=zeit.jetzt().date(),
            # Die Gutschrift betrifft dieselbe Leistung — Zeitraum mitnehmen,
            # sonst fehlt der Pflichtangabe nach § 11 Abs. 1 Z 4 UStG die
            # Grundlage. Altbelege haben noch kein Leistungsdatum (das Feld war
            # über kein Eingabefeld erreichbar); dann tritt das Belegdatum ein,
            # denn am Storno einer alten Rechnung darf das nicht scheitern.
            delivery_date=inv.delivery_date or inv.date,
            delivery_date_to=inv.delivery_date_to,
            tax_mode=inv.tax_mode,
            currency=inv.currency,
            template_id=inv.template_id,
            status="offen",
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        # Gutschrift entsteht direkt als 'offen' → Empfänger sofort einfrieren
        # (Snapshot der Originalrechnung übernehmen, sonst frisch aufbauen)
        credit_note.recipient_snapshot = inv.recipient_snapshot
        db.add(credit_note)
        db.flush()
        ensure_recipient_snapshot(db, credit_note)
        _audit(db, credit_note, "finalisiert",
               changes={"number": {"alt": None, "neu": credit_note.number}},
               note=f"Gutschrift zum Storno von {inv.number}",
               user_email=current_user.email)

        for orig_pos in inv.positions:
            pos = InvoicePosition(
                invoice_id=credit_note.id,
                sort_order=orig_pos.sort_order,
                pos_type=orig_pos.pos_type,
                description=orig_pos.description,
                detail=orig_pos.detail,
                quantity=-orig_pos.quantity,   # negativer Betrag
                unit=orig_pos.unit,
                unit_price=orig_pos.unit_price,
                discount_pct=orig_pos.discount_pct,
                tax_rate=orig_pos.tax_rate,
            )
            db.add(pos)

        db.flush()
        db.refresh(credit_note)
        _calc_totals(credit_note)

    db.flush()
    archive_invoice_pdf(db, inv, "storniert")   # ggf. PDF ins Datacenter archivieren
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
def mark_paid(
    invoice_id: UUID,
    body: InvoiceMarkPaidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    # Bisher ohne jede Prüfung: So ließ sich auch ein Entwurf oder ein Angebot
    # als bezahlt markieren.
    if inv.doc_type not in ("rechnung", "gutschrift"):
        raise HTTPException(400, "Nur Rechnungen und Gutschriften können bezahlt werden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege können nicht bezahlt werden")

    _pruefe_pflichtangaben(inv)      # prüfen, bevor der Beleg verändert wird

    alter_status = inv.status
    neue_nummer = _finalize(db, inv)
    # Ein Entwurf verlässt hiermit den Entwurfsstatus. Ohne diesen Schritt
    # bliebe er "entwurf" — und _recalc_payment_status lässt Entwürfe bewusst
    # unangetastet, der Beleg würde also nie auf "bezahlt" wechseln.
    if inv.status == "entwurf":
        inv.status = "offen"

    # Als vollständig bezahlt markieren heißt jetzt: den offenen Restbetrag als
    # Zahlung erfassen. Damit steht auch dieser Weg im Zahlungsjournal, statt
    # nur zwei Felder am Beleg zu setzen.
    _, offen, _ = _zahlstand(inv)
    betrag = body.paid_amount if body.paid_amount is not None else offen
    db.add(InvoicePayment(
        invoice_id=inv.id, paid_at=body.paid_at, amount=betrag,
        note="Als bezahlt markiert", created_by=current_user.email,
    ))
    db.flush()
    db.refresh(inv)

    _recalc_payment_status(db, inv)
    inv.updated_by = current_user.email
    _audit(db, inv, "bezahlt",
           changes=_audit_changes(alter_status, inv, neue_nummer),
           note=f"Zahlungseingang {body.paid_at:%d.%m.%Y} über "
                f"{float(betrag):.2f} {inv.currency}",
           user_email=current_user.email)
    db.flush()
    archive_invoice_pdf(db, inv, "bezahlt")   # ggf. PDF ins Datacenter archivieren
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/set-status", response_model=InvoiceResponse)
def set_status(
    invoice_id: UUID,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Setzt den Status eines Dokuments.
    Erlaubte Übergänge:
      entwurf   → offen | gesendet
      offen     → gesendet | bezahlt
      gesendet  → offen | bezahlt | angenommen | abgelehnt
      angenommen→ (nur via convert-to-invoice weiter)
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Dokument nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Dokumente können nicht geändert werden")

    new_status = body.get("status")
    # Zahlungsbedingte Status (teilbezahlt/bezahlt) entstehen über die
    # Zahlungserfassung, nicht über diesen Endpunkt — deshalb stehen sie hier
    # nur als Ziel für den Sonderfall „ohne Zahlung als erledigt markieren".
    allowed = {
        "entwurf":      ["offen", "gesendet"],
        "offen":        ["gesendet", "bezahlt"],
        "gesendet":     ["offen", "bezahlt", "angenommen", "abgelehnt"],
        "teilbezahlt":  ["bezahlt", "ueberfaellig"],
        "angenommen":   ["bezahlt"],
        "abgelehnt":    [],
        "bezahlt":      [],
        "ueberfaellig": ["bezahlt", "gesendet"],
    }
    if new_status not in allowed.get(inv.status, []):
        raise HTTPException(400, f"Statuswechsel von '{inv.status}' nach '{new_status}' nicht erlaubt")

    # Pflichtangaben prüfen, BEVOR etwas geändert wird. Andernfalls bliebe bei
    # einem Abbruch ein halb geänderter Beleg in der Sitzung zurück — in der
    # Produktion rollt db.close() das zwar zurück, aber sich darauf zu
    # verlassen ist brüchig.
    _pruefe_pflichtangaben(inv)

    alter_status = inv.status
    inv.status = new_status
    inv.updated_by = current_user.email
    # Verlässt der Beleg den Entwurf, fällt hier die Belegnummer, der
    # Empfänger wird eingefroren und die Zeiteinträge gelten als abgerechnet.
    neue_nummer = _finalize(db, inv)
    _audit(db, inv, "finalisiert" if neue_nummer else "status",
           changes=_audit_changes(alter_status, inv, neue_nummer),
           user_email=current_user.email)
    db.flush()
    # Archivierung nur für die statusbezogenen Auslöser
    if new_status in ("gesendet", "angenommen", "abgelehnt"):
        archive_invoice_pdf(db, inv, new_status)
    db.commit()
    db.refresh(inv)
    return inv


def _pruefe_gueltigkeit(offer: Invoice, trotzdem: bool) -> None:
    """
    Hält die Umwandlung eines abgelaufenen Angebots an — einmal.

    Bewusst als Rückfrage und nicht als Verbot: Ob man ein Angebot nach
    Fristende noch gelten lässt, ist eine kaufmännische Entscheidung und keine
    Sache der Software. Sie soll nur nicht unbemerkt getroffen werden.
    """
    if trotzdem or not angebot_service.ist_abgelaufen(offer):
        return
    raise HTTPException(
        409,
        f"Die Bindefrist dieses Angebots ist am "
        f"{offer.valid_until:%d.%m.%Y} abgelaufen. Wenn du es trotzdem "
        f"umwandeln willst, bestätige das bitte — die Preise stammen dann aus "
        f"einer älteren Kalkulation.")


@router.post("/{invoice_id}/convert-to-ab", response_model=InvoiceResponse)
def convert_to_ab(
    invoice_id: UUID,
    trotz_ablauf: bool = Query(False, description="Abgelaufenes Angebot dennoch umwandeln"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Angebot in Auftragsbestätigung umwandeln."""
    offer = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not offer:
        raise HTTPException(404, "Angebot nicht gefunden")
    if offer.doc_type != "angebot":
        raise HTTPException(400, "Nur Angebote können in eine AB umgewandelt werden")
    _pruefe_gueltigkeit(offer, trotz_ablauf)

    # Standard-Texte für AB laden
    intro_setting = db.query(InvoiceSettings).filter_by(key="default_intro_auftragsbestaetigung").first()
    outro_setting = db.query(InvoiceSettings).filter_by(key="default_outro_auftragsbestaetigung").first()
    intro = (intro_setting.value.strip('"') if intro_setting and isinstance(intro_setting.value, str) else "") or offer.intro_text or ""
    outro = (outro_setting.value.strip('"') if outro_setting and isinstance(outro_setting.value, str) else "") or offer.outro_text or ""

    # Die AB entsteht als Entwurf und bekommt ihre Nummer erst beim Finalisieren
    ab = Invoice(
        doc_type="auftragsbestaetigung",
        contact_id=offer.contact_id, project_id=offer.project_id,
        related_invoice_id=offer.id,
        title=offer.title, date=zeit.jetzt().date(),
        delivery_date=offer.delivery_date, delivery_date_to=offer.delivery_date_to,
        tax_mode=offer.tax_mode, currency=offer.currency,
        template_id=offer.template_id,
        intro_text=intro, outro_text=outro,
        status="entwurf",
        created_by=current_user.email, updated_by=current_user.email,
    )
    db.add(ab)
    db.flush()
    for orig_pos in offer.positions:
        db.add(InvoicePosition(
            invoice_id=ab.id, sort_order=orig_pos.sort_order,
            pos_type=orig_pos.pos_type, description=orig_pos.description,
            detail=orig_pos.detail, quantity=orig_pos.quantity, unit=orig_pos.unit,
            unit_price=orig_pos.unit_price, discount_pct=orig_pos.discount_pct,
            tax_rate=orig_pos.tax_rate,
        ))
    # Das Angebot verlässt den Entwurf → Nummer, Snapshot, Protokoll
    alter_status = offer.status
    offer.status = "angenommen"
    neue_nummer = _finalize(db, offer)
    _audit(db, offer, "finalisiert" if neue_nummer else "status",
           changes=_audit_changes(alter_status, offer, neue_nummer),
           note="In Auftragsbestätigung umgewandelt", user_email=current_user.email)

    db.flush()
    db.refresh(ab)
    _calc_totals(ab)
    db.commit()
    db.refresh(ab)
    return ab


@router.post("/{invoice_id}/convert-to-invoice", response_model=InvoiceResponse)
def convert_to_invoice(
    invoice_id: UUID,
    trotz_ablauf: bool = Query(False, description="Abgelaufenes Angebot dennoch umwandeln"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Angebot oder Auftragsbestätigung in Rechnung umwandeln."""
    offer = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not offer:
        raise HTTPException(404, "Dokument nicht gefunden")
    if offer.doc_type not in ("angebot", "auftragsbestaetigung"):
        raise HTTPException(400, "Nur Angebote oder Auftragsbestätigungen können umgewandelt werden")
    _pruefe_gueltigkeit(offer, trotz_ablauf)

    # Die Rechnung entsteht als Entwurf — Nummer erst beim Finalisieren
    invoice = Invoice(
        doc_type="rechnung",
        contact_id=offer.contact_id,
        project_id=offer.project_id,
        related_invoice_id=offer.id,
        title=offer.title,
        date=zeit.jetzt().date(),
        delivery_date=offer.delivery_date, delivery_date_to=offer.delivery_date_to,
        tax_mode=offer.tax_mode,
        currency=offer.currency,
        template_id=offer.template_id,
        intro_text=offer.intro_text,
        outro_text=offer.outro_text,
        status="entwurf",
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(invoice)
    db.flush()

    for orig_pos in offer.positions:
        pos = InvoicePosition(
            invoice_id=invoice.id,
            sort_order=orig_pos.sort_order,
            pos_type=orig_pos.pos_type,
            description=orig_pos.description,
            detail=orig_pos.detail,
            quantity=orig_pos.quantity,
            unit=orig_pos.unit,
            unit_price=orig_pos.unit_price,
            discount_pct=orig_pos.discount_pct,
            tax_rate=orig_pos.tax_rate,
        )
        db.add(pos)

    # Angebot/AB verlässt den Entwurf → Nummer, Snapshot, Protokoll
    alter_status = offer.status
    offer.status = "angenommen"
    neue_nummer = _finalize(db, offer)
    _audit(db, offer, "finalisiert" if neue_nummer else "status",
           changes=_audit_changes(alter_status, offer, neue_nummer),
           note="In Rechnung umgewandelt", user_email=current_user.email)

    db.flush()
    db.refresh(invoice)
    _calc_totals(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


# ── Abrechnung in Stufen (C-10) ───────────────────────────────────────────────

def _positionen_kopieren(db: Session, ziel: Invoice, quelle: Invoice) -> None:
    """
    Übernimmt die Positionen eines Belegs vollständig.

    Vollständig heißt hier auch: mit Bild und Erlöskonto. Beim Umwandeln eines
    Angebots wurden beide bisher stillschweigend fallengelassen — aus einem
    bebilderten Angebot wurde eine Rechnung ohne Bilder, und das gepflegte
    Erlöskonto der Position ging im Buchhaltungs-Export verloren.

    Der Anzahlungsabzug wird NICHT mitkopiert: Er gehört zu genau der
    Schlussrechnung, in der er entstanden ist.
    """
    for orig in quelle.positions:
        if positionen_service.typ(orig) == positionen_service.ANZAHLUNGSABZUG:
            continue
        db.add(InvoicePosition(
            invoice_id=ziel.id,
            sort_order=orig.sort_order,
            pos_type=orig.pos_type,
            description=orig.description,
            detail=orig.detail,
            quantity=orig.quantity,
            unit=orig.unit,
            unit_price=orig.unit_price,
            discount_pct=orig.discount_pct,
            tax_rate=orig.tax_rate,
            account_nr=orig.account_nr,
            image_key=orig.image_key,
            image_size=orig.image_size,
            image_provider=orig.image_provider,
        ))


@router.get("/{invoice_id}/chain", response_model=StrangResponse)
def get_chain(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_modul_rechte("verkauf")),
):
    """
    Der Abrechnungsstrang eines Belegs: alle Belege des Bauvorhabens und der
    Stand des Abzugs.

    Auch für Belege ohne Strang aufrufbar — dann kommt eine leere Antwort
    zurück statt eines Fehlers. Die Oberfläche kann den Abschnitt so ohne
    Fallunterscheidung einblenden.
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if not inv.chain_id:
        return StrangResponse(chain_id=None)

    chain_id = inv.chain_id
    abzugsfaehig = {b.id for b in anzahlung_service.abzugsfaehige_belege(db, chain_id)}

    belege = []
    for b in anzahlung_service.strang_belege(db, chain_id):
        _, offen, _ = _zahlstand(b)
        belege.append(StrangBeleg(
            id=b.id, doc_type=b.doc_type, number=b.number,
            billing_stage=b.billing_stage,
            stage_label=anzahlung_service.bezeichnung(b.billing_stage)
            if b.doc_type == "rechnung" else DOC_TYPE_LABELS_DE.get(b.doc_type, b.doc_type),
            date=b.date, title=b.title,
            subtotal=b.subtotal, total=b.total, status=b.status,
            open_amount=offen if b.status not in ("entwurf", "storniert") else Decimal("0"),
            deducted=b.id in abzugsfaehig,
        ))

    abzug = anzahlung_service.abzug_je_satz(
        anzahlung_service.abzugsfaehige_belege(db, chain_id))
    zeilen, netto_gesamt, brutto_gesamt = [], Decimal("0"), Decimal("0")
    for satz in sorted(abzug, key=lambda s: (s is None, -(s or 0))):
        netto = abzug[satz]
        steuer = (netto * satz / 100).quantize(Decimal("0.01")) if satz else Decimal("0")
        zeilen.append(AbzugZeile(tax_rate=satz, net_amount=netto, tax_amount=steuer))
        netto_gesamt += netto
        brutto_gesamt += netto + steuer

    return StrangResponse(
        chain_id=chain_id, belege=belege, abzug=zeilen,
        abzug_netto=netto_gesamt, abzug_brutto=brutto_gesamt,
        hat_schlussrechnung=anzahlung_service.hat_schlussrechnung(db, chain_id),
    )


@router.post("/{invoice_id}/anzahlung", response_model=InvoiceResponse)
def create_advance(
    invoice_id: UUID,
    body: AnzahlungRequest,
    trotz_ablauf: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_modul_rechte("verkauf")),
):
    """
    Fordert aus einem Angebot oder einer Auftragsbestätigung eine Anzahlung an.

    Die Anzahlungsrechnung bekommt **eine** Position: den angeforderten Betrag
    zum Steuersatz des Vorbelegs. Sie die Positionen des Angebots anteilig
    nachbilden zu lassen wäre eine Scheingenauigkeit — angezahlt wird auf die
    Auftragssumme, nicht auf einzelne Leistungen.

    Der Steuersatz kommt aus dem Vorbeleg. Sind dort mehrere im Spiel, wird
    abgebrochen statt geraten: Welcher Satz für eine Anzahlung auf einen
    gemischten Auftrag gilt, ist eine steuerliche Frage.
    """
    quelle = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not quelle:
        raise HTTPException(404, "Beleg nicht gefunden")
    if quelle.doc_type not in ("angebot", "auftragsbestaetigung"):
        raise HTTPException(400, "Eine Anzahlung wird aus einem Angebot oder einer "
                                 "Auftragsbestätigung angefordert")
    _pruefe_gueltigkeit(quelle, trotz_ablauf)

    if body.percent is None and body.amount is None:
        raise HTTPException(400, "Bitte einen Prozentsatz oder einen Betrag angeben")
    if body.percent is not None and body.amount is not None:
        raise HTTPException(400, "Bitte entweder einen Prozentsatz oder einen Betrag "
                                 "angeben, nicht beides")

    saetze = {satz for satz, netto in anzahlung_service.netto_je_satz(quelle).items() if netto}
    if len(saetze) > 1:
        raise HTTPException(
            400, "Der Auftrag enthält mehrere Steuersätze. Eine Anzahlung darauf "
                 "muss von Hand erfasst werden — welcher Satz gilt, ist eine "
                 "steuerliche Entscheidung.")
    satz = saetze.pop() if saetze else None

    grundlage = Decimal(str(quelle.subtotal or 0))
    if body.percent is not None:
        if body.percent <= 0 or body.percent > 100:
            raise HTTPException(400, "Der Prozentsatz muss zwischen 0 und 100 liegen")
        betrag = (grundlage * body.percent / 100).quantize(Decimal("0.01"))
    else:
        betrag = Decimal(str(body.amount)).quantize(Decimal("0.01"))
    if betrag <= 0:
        raise HTTPException(400, "Der Anzahlungsbetrag muss größer als null sein")
    if betrag > grundlage > 0:
        raise HTTPException(400, f"Die Anzahlung ({betrag:.2f}) übersteigt die "
                                 f"Auftragssumme ({grundlage:.2f})")

    belegdatum = body.date or zeit.jetzt().date()
    if period_service.ist_gesperrt(db, belegdatum):
        period_service.pruefe_periode_offen(db, belegdatum, "angelegt")

    # Das Angebot eröffnet den Strang, sofern es noch keinem angehört.
    anzahlung_service.strang_anlegen(db, quelle)

    rechnung = Invoice(
        doc_type="rechnung",
        billing_stage="anzahlung",
        chain_id=quelle.chain_id,
        advance_percent=body.percent,
        contact_id=quelle.contact_id,
        project_id=quelle.project_id,
        related_invoice_id=quelle.id,
        title=quelle.title,
        date=belegdatum,
        due_date=body.due_date,
        delivery_date=quelle.delivery_date,
        delivery_date_to=quelle.delivery_date_to,
        tax_mode=quelle.tax_mode,
        currency=quelle.currency,
        template_id=quelle.template_id,
        intro_text=quelle.intro_text,
        status="entwurf",
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(rechnung)
    db.flush()

    if body.description:
        text = body.description
    elif body.percent is not None:
        bezug = f"Angebot {quelle.number}" if quelle.number else "den Auftrag"
        text = f"Anzahlung {body.percent:g} % auf {bezug}"
    else:
        bezug = f"Angebot {quelle.number}" if quelle.number else "den Auftrag"
        text = f"Anzahlung auf {bezug}"

    db.add(InvoicePosition(
        invoice_id=rechnung.id, sort_order=0, pos_type="item",
        description=text, quantity=Decimal("1"), unit_price=betrag, tax_rate=satz,
    ))

    db.flush()
    db.refresh(rechnung)
    _calc_totals(rechnung)
    db.commit()
    db.refresh(rechnung)
    return rechnung


@router.post("/{invoice_id}/schlussrechnung", response_model=InvoiceResponse)
def create_final_invoice(
    invoice_id: UUID,
    body: SchlussrechnungRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_modul_rechte("verkauf")),
):
    """
    Erzeugt die Schlussrechnung eines Strangs.

    Sie enthält die **Gesamtleistung** und zieht davon jede bereits gestellte
    Anzahlungs- und Teilrechnung wieder ab — je Steuersatz eine eigene Zeile.
    Abgezogen wird, was fakturiert wurde, nicht was bezahlt wurde: Die
    Umsatzsteuer entsteht mit der Rechnung. Ein offener Betrag bleibt als
    eigener offener Posten stehen und wird dort gemahnt.

    ``invoice_id`` ist irgendein Beleg des Strangs; die Positionen der
    Gesamtleistung kommen aus ``from_invoice_id`` (üblicherweise dem Angebot)
    oder, wenn nichts angegeben ist, aus dem Kopf des Strangs.
    """
    beleg = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not beleg:
        raise HTTPException(404, "Beleg nicht gefunden")

    anzahlung_service.strang_anlegen(db, beleg)
    chain_id = beleg.chain_id

    if anzahlung_service.hat_schlussrechnung(db, chain_id):
        raise HTTPException(
            409, "Zu diesem Vorgang gibt es bereits eine Schlussrechnung. Eine "
                 "zweite würde dieselben Anzahlungen ein weiteres Mal abziehen.")

    abzuziehen = anzahlung_service.abzugsfaehige_belege(db, chain_id)
    if not abzuziehen:
        raise HTTPException(
            400, "Zu diesem Vorgang gibt es keine gestellte Anzahlungs- oder "
                 "Teilrechnung. Eine Schlussrechnung ohne Abzug ist eine "
                 "gewöhnliche Rechnung.")

    quelle = beleg
    if body.from_invoice_id:
        quelle = db.query(Invoice).filter(Invoice.id == body.from_invoice_id).first()
        if not quelle:
            raise HTTPException(404, "Vorlagebeleg nicht gefunden")
        if anzahlung_service.strang_kopf(quelle) != chain_id:
            raise HTTPException(400, "Der Vorlagebeleg gehört zu einem anderen Vorgang")

    belegdatum = body.date or zeit.jetzt().date()
    if period_service.ist_gesperrt(db, belegdatum):
        period_service.pruefe_periode_offen(db, belegdatum, "angelegt")

    schluss = Invoice(
        doc_type="rechnung",
        billing_stage="schluss",
        chain_id=chain_id,
        contact_id=quelle.contact_id,
        project_id=quelle.project_id,
        related_invoice_id=quelle.id,
        title=quelle.title,
        date=belegdatum,
        due_date=body.due_date,
        delivery_date=quelle.delivery_date,
        delivery_date_to=quelle.delivery_date_to,
        tax_mode=quelle.tax_mode,
        currency=quelle.currency,
        template_id=quelle.template_id,
        intro_text=quelle.intro_text,
        outro_text=quelle.outro_text,
        status="entwurf",
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(schluss)
    db.flush()

    _positionen_kopieren(db, schluss, quelle)
    db.flush()
    db.refresh(schluss)

    anzahlung_service.zeilen_anhaengen(db, schluss, abzuziehen)
    db.flush()
    db.refresh(schluss)
    _calc_totals(schluss)
    db.commit()
    db.refresh(schluss)
    return schluss


@router.post("/{invoice_id}/duplicate", response_model=InvoiceResponse)
def duplicate_invoice(
    invoice_id: UUID,
    body: InvoiceDuplicateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dupliziert einen Beleg als neuen Entwurf gleicher Belegart.
    Die zu übernehmenden Bestandteile werden über die Flags im Request gesteuert
    (Positionen, Texte, Kontakt/Referenz, Anhänge). Nummer wird neu vergeben.
    """
    src = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not src:
        raise HTTPException(404, "Beleg nicht gefunden")

    # Das Duplikat ist ein Entwurf und bekommt seine Nummer erst beim Finalisieren
    dup = Invoice(
        doc_type=src.doc_type,
        date=zeit.jetzt().date(),
        # Leistungsdatum NICHT übernehmen: Das Duplikat betrifft eine neue
        # Leistung; ein mitkopiertes altes Datum wäre schlicht falsch.
        delivery_date=zeit.jetzt().date(),
        tax_mode=src.tax_mode,
        currency=src.currency,
        template_id=src.template_id,
        status="entwurf",
        # Kontakt & Referenz optional
        contact_id=src.contact_id if body.contact else None,
        project_id=src.project_id if body.contact else None,
        title=src.title if body.contact else None,
        reference=src.reference if body.contact else None,
        # Texte optional
        intro_text=src.intro_text if body.texts else None,
        outro_text=src.outro_text if body.texts else None,
        notes=src.notes if body.texts else None,
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(dup)
    db.flush()

    if body.positions:
        for p in src.positions:
            db.add(InvoicePosition(
                invoice_id=dup.id, sort_order=p.sort_order,
                pos_type=p.pos_type, description=p.description, detail=p.detail,
                quantity=p.quantity, unit=p.unit, unit_price=p.unit_price,
                discount_pct=p.discount_pct, tax_rate=p.tax_rate,
                article_id=p.article_id, time_entry_id=p.time_entry_id,
            ))

    if body.attachments:
        for a in src.attachments:
            db.add(InvoiceAttachment(
                invoice_id=dup.id, attach_type=a.attach_type,
                filename=a.filename, file_path=a.file_path,
                datacenter_id=a.datacenter_id, url=a.url,
                mime_type=a.mime_type, file_size=a.file_size,
            ))

    db.flush()
    db.refresh(dup)
    _calc_totals(dup)
    db.commit()
    db.refresh(dup)
    return dup
