from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, extract
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import json

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin, require_module
from app.models.user import User
from app.models.invoice import (Invoice, InvoicePosition, InvoiceAttachment,
                                 InvoiceNumberSequence, InvoiceSettings,
                                 InvoiceAuditLog, InvoicePayment, InvoiceDunning)
from app.models.settings import Setting
from app.models.email_template import EmailTemplate
from app.models.masterdata import EntityRecord
from app.services.invoice_pdf import generate_pdf, generate_html_preview
from app.services.invoice_snapshot import (ensure_recipient_snapshot,
                                           snapshot_as_contact)
from app.services.invoice_archive import archive_invoice_pdf
from app.services import period_service
from app.services import positionen as positionen_service
from app.services import skonto as skonto_service
from app.services import dunning as dunning_service
from app.services import angebot as angebot_service
from app.services import anzahlung as anzahlung_service
from app.services.erechnung import beleg as erechnung_service
from app.services import auswertungen as auswertungen_service
from app.schemas.invoice import (
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceListItem,
    InvoiceCancelRequest, InvoiceMarkPaidRequest,
    InvoiceBookFilter, InvoiceSettingsUpdate, NextNumberResponse,
    InvoicePositionResponse, InvoiceAttachmentResponse,
    InvoiceDuplicateRequest, InvoiceAuditEntry,
    InvoicePaymentCreate, InvoicePaymentResponse, InvoicePaymentState,
    OpenItem, OpenItemsByContact, OpenItemsResponse,
    UvaZeile, UvaResponse,
    DunningCandidate, DunningRunResponse, DunningCreateRequest, DunningEntry,
    DunningBlockRequest, DunningBatchRequest, DunningLevelConfig,
    SkontoVorschau, SkontoZeile, SkontoRequest,
    ERechnungPruefung,
    UmsatzJahrResponse, UmsatzKundeResponse, UmsatzArtikelResponse,
    AngebotsquoteResponse,
    AnzahlungRequest, SchlussrechnungRequest,
    AbzugZeile, StrangBeleg, StrangResponse,
)

router = APIRouter(prefix="/invoices", tags=["Rechnungen"])


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

TYPE_PREFIX = {
    "rechnung":             "RE",
    "angebot":              "AN",
    "auftragsbestaetigung": "AB",
    "gutschrift":           "GS",
    "lieferschein":         "LS",
}

def _next_number(db: Session, doc_type: str, year: int) -> tuple[int, str]:
    """Atomarer Zähler — gibt (sequence, formatted_number) zurück."""
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=year).first()
    if not seq:
        seq = InvoiceNumberSequence(doc_type=doc_type, year=year, last_sequence=0)
        db.add(seq)
        db.flush()
    seq.last_sequence += 1
    db.flush()

    # Format aus Einstellungen lesen (Fallback)
    fmt_key = f"number_format_{doc_type}"
    setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
    if setting and setting.value:
        fmt = setting.value.strip('"') if isinstance(setting.value, str) else str(setting.value)
    else:
        prefix = TYPE_PREFIX.get(doc_type, "DO")
        fmt = f"{prefix}-{{year}}-{{seq:03d}}"

    number = fmt.format(year=year, seq=seq.last_sequence)
    return seq.last_sequence, number


from app.services.positionen import (WERTZEILEN, gruppen_netto as _gruppen_netto,
                                      rabatt_verteilen as _rabatt_verteilen,
                                      rabattbetrag as _rabattbetrag, typ as _postyp)


def _calc_totals(invoice: Invoice) -> None:
    """
    Positionen neu berechnen und Summen auf den Beleg schreiben.

    Die Steuer wird **je Steuersatz** summiert und dann einmal gerundet.
    Vorher wurde je Position gerundet — bei mehreren Positionen wich die
    gespeicherte Summe dadurch um Cent von der MwSt.-Aufschlüsselung auf dem
    PDF ab, und auf dem gedruckten Beleg ergab Netto + MwSt. nicht die
    Gesamtsumme. Kaufmännisch korrekt ist: je Satz summieren, dann runden.

    Textzeilen tragen nichts zur Summe bei (der PDF- und der BMD-Export
    überspringen sie ebenfalls).
    """
    from collections import defaultdict

    # „Ein Satz für alle": Der erste gepflegte Steuersatz gilt für jede
    # Position. Die Regel steckt bewusst hier und nicht nur im Formular —
    # der Modus war bis dahin wirkungslos und verhielt sich wie „pro Position",
    # der Benutzer wählte also etwas aus, das nichts tat.
    if invoice.tax_mode == "single_rate":
        gepflegte = [p.tax_rate for p in invoice.positions
                     if (p.pos_type or "item") in WERTZEILEN and p.tax_rate is not None]
        if gepflegte:
            for pos in invoice.positions:
                if (pos.pos_type or "item") in WERTZEILEN:
                    pos.tax_rate = gepflegte[0]

    positionen = list(invoice.positions)
    subtotal = Decimal("0")
    netto_je_satz: dict = defaultdict(lambda: Decimal("0"))
    gruppe_ab = 0          # Index, ab dem die laufende Gruppe zählt

    for i, pos in enumerate(positionen):
        typ = pos.pos_type or "item"

        # Überschrift und Freitext tragen keinen Betrag. Nur die Überschrift
        # eröffnet eine Gruppe — eine erläuternde Textzeile mitten in einer
        # Gruppe soll sie nicht zerreißen.
        if typ in ("text", "heading"):
            pos.line_total = Decimal("0")
            if typ == "heading":
                gruppe_ab = i + 1
            continue

        # Zwischensumme: Anzeigewert der laufenden Gruppe, danach neue Gruppe.
        # Rabattzeilen der Gruppe zählen mit — die Zwischensumme soll zeigen,
        # was die Gruppe tatsächlich kostet.
        if typ == "subtotal":
            pos.line_total = sum(
                (p.line_total or Decimal("0")) for p in positionen[gruppe_ab:i]
                if (p.pos_type or "item") not in ("text", "heading", "subtotal"))
            gruppe_ab = i + 1
            continue

        # Rabattzeile: fester Betrag oder Prozent der laufenden Gruppe.
        if typ == "discount":
            gruppe_je_satz = _gruppen_netto(positionen, gruppe_ab, i)
            basis = sum(gruppe_je_satz.values(), Decimal("0"))
            betrag = _rabattbetrag(pos, basis)
            pos.line_total = -betrag
            subtotal -= betrag
            for satz, anteil in _rabatt_verteilen(gruppe_je_satz, basis, betrag).items():
                netto_je_satz[satz] -= anteil
            continue

        # Gewöhnliche Position
        qty = pos.quantity or Decimal("0")
        price = pos.unit_price or Decimal("0")
        base = qty * price
        if pos.discount_pct:
            base = base * (1 - pos.discount_pct / 100)
        base = base.quantize(Decimal("0.01"))
        pos.line_total = base
        subtotal += base
        if pos.tax_rate is not None:
            netto_je_satz[pos.tax_rate] += base

    tax_total = Decimal("0")
    if invoice.tax_mode != "kleinunternehmer":
        for satz, netto in netto_je_satz.items():
            tax_total += (netto * satz / 100).quantize(Decimal("0.01"))

    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = subtotal + tax_total


def _set_time_entry_status(db: Session, entry_ids, neuer_status: str) -> None:
    """Setzt den Status der angegebenen Zeiteinträge. Kein Commit."""
    ids = [i for i in entry_ids if i]
    if not ids:
        return
    from app.models.zeiterfassung import TimeEntry
    db.query(TimeEntry).filter(TimeEntry.id.in_(ids)).update(
        {TimeEntry.status: neuer_status}, synchronize_session=False)


def _time_entry_ids(invoice: Invoice) -> set:
    """Zeiteinträge, die aktuell über Positionen am Beleg hängen."""
    return {p.time_entry_id for p in invoice.positions if p.time_entry_id}


def _sync_time_entry_status(db: Session, invoice: Invoice) -> None:
    """
    Hält den Status der verknüpften Zeiteinträge am Beleg ausgerichtet.

    * Beleg ist noch Entwurf → nichts tun. Die Stunden bleiben bewusst offen,
      ein verworfener Entwurf soll sie nicht blockieren.
    * Beleg verlässt den Entwurf → Zeiteinträge werden ``abgerechnet``.
    * Beleg wird storniert → Zeiteinträge werden wieder ``freigegeben``,
      die Leistung ist dann erneut zu fakturieren.

    Die Entwurfs-Regel steckt bewusst hier und nicht bei den Aufrufern, damit
    sie an einer einzigen Stelle gilt. Kein Commit — der Aufrufer committet.
    """
    if invoice.status == "entwurf":
        return
    neuer_status = "freigegeben" if invoice.status == "storniert" else "abgerechnet"
    _set_time_entry_status(db, _time_entry_ids(invoice), neuer_status)


# ─────────────────────────────────────────────────────────────────────────────
# Nummernvergabe, Änderungsprotokoll und Belegsperre
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_number(db: Session, invoice: Invoice) -> bool:
    """
    Vergibt die Belegnummer, sobald der Beleg den Entwurf verlässt.

    Entwürfe bleiben nummernlos — sonst hinterlässt jeder verworfene Entwurf
    eine Lücke im Nummernkreis (§ 11 Abs. 1 Z 3 UStG / § 131 BAO). Gibt True
    zurück, wenn eine Nummer neu vergeben wurde. Kein Commit.
    """
    if invoice.number:
        return False
    jahr = (invoice.date or datetime.now().date()).year
    sequence, number = _next_number(db, invoice.doc_type, jahr)
    invoice.year = jahr
    invoice.sequence = sequence
    invoice.number = number
    return True


def _audit(db: Session, invoice: Invoice, action: str, *,
           changes: dict = None, note: str = None, user_email: str = None) -> None:
    """Schreibt einen Eintrag ins Änderungsprotokoll. Kein Commit."""
    db.add(InvoiceAuditLog(
        invoice_id=invoice.id,
        action=action,
        changes=changes or None,
        note=note,
        changed_by=user_email,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Zahlungen
# ─────────────────────────────────────────────────────────────────────────────

# Status, die ein Zahlungseingang nicht überschreiben darf
ZAHLUNG_UNBERUEHRT = ("entwurf", "storniert", "angenommen", "abgelehnt")


def _zahlstand(invoice: Invoice) -> tuple:
    """
    Gibt (Summe der Zahlungen, offener Betrag, überzahlt?) zurück.

    Vorzeichen bleiben erhalten: Eine Gutschrift hat eine negative Summe, ihre
    Rückzahlung wird ebenfalls negativ erfasst. Der offene Betrag ist damit für
    beide Belegarten schlicht ``total - gezahlt``.
    """
    from decimal import Decimal
    gezahlt = sum((Decimal(str(z.amount or 0)) for z in invoice.payments), Decimal("0"))
    gesamt = Decimal(str(invoice.total or 0))
    offen = (gesamt - gezahlt).quantize(Decimal("0.01"))
    # Überzahlt heißt: über das Ziel hinausgeschossen — bei einer Rechnung
    # wurde zu viel überwiesen, bei einer Gutschrift zu viel erstattet.
    ueberzahlt = (offen < 0) if gesamt >= 0 else (offen > 0)
    return gezahlt, offen, ueberzahlt


def _recalc_payment_status(db: Session, invoice: Invoice) -> None:
    """
    Leitet Zahlstand und Status aus den erfassten Zahlungen ab.

    ``paid_at``/``paid_amount`` am Beleg werden dabei als Zwischenspeicher
    mitgeführt (Datum der letzten Zahlung, Summe aller Zahlungen), damit PDF,
    Export und DSGVO-Auswertung unverändert weiterarbeiten.

    Entwürfe, stornierte, angenommene und abgelehnte Belege behalten ihren
    Status — dort hat ein Zahlungseingang nichts verloren. Kein Commit.
    """
    from decimal import Decimal

    gezahlt, offen, _ = _zahlstand(invoice)
    invoice.paid_amount = gezahlt if invoice.payments else None
    invoice.paid_at = max((z.paid_at for z in invoice.payments), default=None)

    if invoice.status in ZAHLUNG_UNBERUEHRT:
        return

    if not invoice.payments:
        # Alle Zahlungen entfernt → zurück auf offen bzw. überfällig.
        # Dass der Beleg zuvor „gesendet" war, lässt sich nicht rekonstruieren.
        invoice.status = "ueberfaellig" if _ist_ueberfaellig(invoice) else "offen"
    elif abs(offen) < Decimal("0.01"):
        invoice.status = "bezahlt"
    elif (offen < 0) if Decimal(str(invoice.total or 0)) >= 0 else (offen > 0):
        invoice.status = "bezahlt"          # überzahlt gilt als beglichen
    else:
        invoice.status = "teilbezahlt"


def _ist_ueberfaellig(invoice: Invoice, stichtag: date = None) -> bool:
    """Zahlungsziel überschritten und noch etwas offen?"""
    if not invoice.due_date:
        return False
    return invoice.due_date < (stichtag or date.today())


def _pruefe_periode(db: Session, invoice: Invoice, vorgang: str = "geändert") -> None:
    """
    Wirft 400, wenn das Belegdatum in einem abgeschlossenen Monat liegt.

    Ohne diese Sperre wäre der Monatsabschluss wirkungslos: Man könnte nach der
    Übergabe an die Buchhaltung weiter Belege in den Monat buchen, und die
    übergebenen Zahlen stimmten nicht mehr.
    """
    from app.services.period_service import pruefe_periode_offen
    pruefe_periode_offen(db, invoice.date, vorgang)


def _pruefe_pflichtangaben(invoice: Invoice) -> None:
    """
    Prüft die Pflichtangaben, bevor ein Beleg ausgestellt wird.

    Das Liefer-/Leistungsdatum ist nach § 11 Abs. 1 Z 4 UStG Pflicht — fehlt
    es, verliert der Empfänger den Vorsteuerabzug. Geprüft wird bewusst erst
    beim Ausstellen und nicht schon beim Speichern: Am Entwurf soll man
    arbeiten können, auch wenn das Leistungsdatum noch nicht feststeht.

    Nur Rechnungen und Gutschriften sind betroffen; Angebot, Auftrags-
    bestätigung und Lieferschein rechnen nichts ab.
    """
    if invoice.doc_type not in ("rechnung", "gutschrift"):
        return
    if invoice.delivery_date:
        if invoice.delivery_date_to and invoice.delivery_date_to < invoice.delivery_date:
            raise HTTPException(
                400, "Der Leistungszeitraum endet vor seinem Beginn — bitte die "
                     "beiden Daten prüfen.")
        return
    raise HTTPException(
        400,
        "Das Liefer-/Leistungsdatum fehlt. Es ist eine Pflichtangabe nach "
        "§ 11 Abs. 1 Z 4 UStG — ohne sie verliert der Empfänger den "
        "Vorsteuerabzug. Bitte im Beleg ergänzen und erneut ausstellen.",
    )


UID_SCHWELLE = Decimal("10000")


def _uid_fehlt(db: Session, invoice: Invoice) -> bool:
    """
    Fehlt die UID des Empfängers, obwohl sie Pflichtangabe wäre?

    Ab 10.000 € Rechnungsbetrag verlangt § 11 Abs. 1 Z 2 UStG die UID des
    Leistungsempfängers. Das wird bewusst **nicht** blockiert: Der Empfänger
    kann eine Privatperson ohne UID sein, dann gibt es nichts einzutragen.
    Gemeldet wird es trotzdem — am Beleg im Protokoll und in der Prüfliste des
    Monatsabschlusses, wo es vor der Übergabe auffällt.
    """
    if invoice.doc_type not in ("rechnung", "gutschrift"):
        return False
    if abs(Decimal(str(invoice.total or 0))) <= UID_SCHWELLE:
        return False
    quelle = (invoice.recipient_snapshot or {}).get("data") if invoice.recipient_snapshot else None
    if quelle is None and invoice.contact_id:
        rec = db.query(EntityRecord).filter(EntityRecord.id == invoice.contact_id).first()
        quelle = (rec.data or {}) if rec else {}
    return not (quelle or {}).get("uid", "").strip()


def _finalize(db: Session, invoice: Invoice) -> bool:
    """
    Sammelvorgang für „Beleg verlässt den Entwurf".

    Nummer vergeben, Empfängerdaten einfrieren, Zeiteinträge nachziehen — in
    dieser Reihenfolge, damit die Nummer feststeht, bevor das Archiv-PDF
    erzeugt wird. Gibt True zurück, wenn eine Nummer neu vergeben wurde.
    Den Protokolleintrag schreibt der Aufrufer, weil nur er den Anlass kennt.
    Kein Commit.
    """
    _pruefe_pflichtangaben(invoice)
    _pruefe_periode(db, invoice, "ausgestellt")
    neue_nummer = _ensure_number(db, invoice)
    ensure_recipient_snapshot(db, invoice)
    _sync_time_entry_status(db, invoice)

    # Fehlende UID über der Schwelle blockiert nicht, wird aber am Beleg
    # vermerkt — sonst fällt es niemandem auf.
    if _uid_fehlt(db, invoice):
        _audit(db, invoice, "hinweis",
               note=f"UID des Empfängers fehlt. Ab "
                    f"{float(UID_SCHWELLE):.0f} € Rechnungsbetrag ist sie nach "
                    f"§ 11 Abs. 1 Z 2 UStG Pflichtangabe — ohne sie verliert ein "
                    f"unternehmerischer Empfänger den Vorsteuerabzug.",
               user_email=invoice.updated_by)

    # Schlussrechnung: Zieht sie mehr ab, als sie an Leistung ausweist, wurde
    # sie vermutlich mit der Restleistung statt der Gesamtleistung gefüllt.
    # Ein Hinweis, keine Sperre — es gibt Fälle, in denen der Kunde tatsächlich
    # etwas zurückbekommt, und das darf die Software nicht verbieten.
    if invoice.billing_stage == "schluss" and invoice.chain_id:
        abzug = anzahlung_service.abzug_je_satz(
            anzahlung_service.abzugsfaehige_belege(db, invoice.chain_id,
                                                   ausser_id=invoice.id))
        for hinweis in anzahlung_service.pruefe_abzug(invoice, abzug):
            _audit(db, invoice, "hinweis", note=hinweis, user_email=invoice.updated_by)
    return neue_nummer


def _audit_changes(alter_status: str, invoice: Invoice, neue_nummer: bool) -> dict:
    """Baut das Änderungs-Dict für einen Statuswechsel."""
    changes = {"status": {"alt": alter_status, "neu": invoice.status}}
    if neue_nummer:
        changes["number"] = {"alt": None, "neu": invoice.number}
    return changes


# Felder, die nach dem Finalisieren nicht mehr geändert werden dürfen.
# Maßstab: Alles, was auf dem Beleg gedruckt wird oder die Buchung bestimmt.
# Das PDF wird bei jedem Abruf neu erzeugt — eine Änderung an diesen Feldern
# würde den bereits versendeten Beleg rückwirkend verändern.
GESPERRTE_FELDER = {
    "date":             "Belegdatum",
    "due_date":         "Zahlungsziel",
    "delivery_date":    "Liefer-/Leistungsdatum",
    "delivery_date_to": "Ende des Leistungszeitraums",
    # Die Bindefrist steht auf dem Angebot. Sie nachträglich zu verlängern
    # hieße, dem Kunden stillschweigend etwas anderes zuzusagen, als er
    # bekommen hat.
    "valid_until":      "Gültig bis",
    "contact_id":    "Empfänger",
    "title":         "Titel / Betreff",
    "reference":     "Referenz",
    "intro_text":    "Einleitungstext",
    "outro_text":    "Schlusstext",
    "tax_mode":      "MwSt.-Modus",
    "currency":      "Währung",
    "template_id":   "PDF-Vorlage",
    # Die Skonto-Bedingung steht auf dem Beleg und ist Teil der Vereinbarung
    # mit dem Kunden — nachträglich änderbar wäre sie eine stille Zusage.
    "skonto_percent": "Skontosatz",
    "skonto_days":    "Skontofrist",
}
# Weiterhin änderbar, weil nicht Bestandteil des gedruckten Belegs:
#   notes (interne Notiz), project_id (Zuordnung), Anhänge und Verträge.


def _pruefe_stufe(doc_type: str, stufe: str) -> None:
    """
    Die Abrechnungsstufe gibt es nur an einer Rechnung.

    Ein Angebot mit der Stufe „Schlussrechnung" wäre sinnlos, würde aber in
    der Abzugsrechnung mitzählen und dort echten Schaden anrichten.
    """
    if not stufe:
        return
    if stufe not in anzahlung_service.STUFEN:
        raise HTTPException(400, f"Unbekannte Abrechnungsstufe: {stufe}. "
                                 f"Erlaubt: {', '.join(anzahlung_service.STUFEN)}")
    if doc_type != "rechnung":
        raise HTTPException(400, "Anzahlung, Teil- und Schlussrechnung gibt es nur "
                                 "als Rechnung")


def _verwaiste_bilder_entfernen(db: Session, kandidaten: dict) -> int:
    """
    Löscht Positionsbilder, auf die keine Position mehr zeigt.

    Aufgerufen, nachdem die Positionen eines Belegs ersetzt wurden. Wird eine
    Position mit Bild entfernt, blieb die Datei bisher für immer im Speicher —
    ein Aufräumlauf dafür fehlte, weil sich der Objektspeicher nicht auflisten
    lässt. Beim Ersetzen wissen wir aber genau, welche Schlüssel betroffen sind;
    das ist der Moment, in dem es ohne Suchlauf geht.

    Geprüft wird gegen ALLE Positionen, nicht nur die des Belegs: Ein Bild kann
    beim Duplizieren eines Belegs mitgereist sein und dann noch anderswo
    verwendet werden. Fehler beim Löschen werden geschluckt — eine Datei, die
    liegen bleibt, darf das Speichern des Belegs nicht verhindern.

    ``kandidaten`` ist ``{schlüssel: provider}``. Der Provider muss mit, sonst
    wird im Mischbetrieb im falschen Speicher gelöscht — die Datei bliebe
    liegen, und zwar unbemerkt.
    """
    if not kandidaten:
        return 0
    from app.services import storage_service

    noch_verwendet = {
        k for (k,) in db.query(InvoicePosition.image_key)
        .filter(InvoicePosition.image_key.in_(list(kandidaten))).distinct().all()
    }
    entfernt = 0
    for schluessel, provider in kandidaten.items():
        if schluessel in noch_verwendet:
            continue
        try:
            storage_service.delete_file(schluessel, db=db, backend=provider)
            entfernt += 1
        except Exception as e:
            print(f"[WARN] Verwaistes Positionsbild {schluessel} nicht löschbar: {e}")
    return entfernt


def _positions_fingerprint(positions) -> list:
    """
    Vergleichbare Darstellung der Positionen inklusive Reihenfolge.

    Zahlen laufen über Decimal.normalize(), damit "2" und "2.0000" als gleich
    gelten — sonst meldet die Sperre eine Änderung, wo keine ist.
    """
    from decimal import Decimal as _D

    def zahl(v):
        return None if v is None else str(_D(str(v)).normalize())

    def text(v):
        return None if v is None else str(v)

    return [
        (
            i, text(p.pos_type), text(p.description), text(p.detail),
            zahl(p.quantity), text(p.unit), zahl(p.unit_price),
            zahl(p.discount_pct), zahl(p.tax_rate),
            text(p.account_nr), text(p.article_id), text(p.time_entry_id),
        )
        for i, p in enumerate(positions)
    ]


def _pruefe_belegsperre(inv: Invoice, body) -> dict:
    """
    Prüft eine Änderung an einem finalisierten Beleg.

    Gibt die erlaubten Änderungen als Protokoll-Dict zurück oder wirft 400 mit
    Klartext, welche Felder gesperrt sind. Korrekturen laufen über Storno und
    Neuausstellung — so halten es sevDesk, lexware, BMD und myfactory auch.
    """
    verletzt = []
    for feld, label in GESPERRTE_FELDER.items():
        alt = getattr(inv, feld, None)
        neu = getattr(body, feld, None)
        if (alt or None) != (neu or None):
            verletzt.append(label)

    if _positions_fingerprint(inv.positions) != _positions_fingerprint(body.positions):
        verletzt.append("Positionen")

    if verletzt:
        raise HTTPException(
            400,
            f"Der Beleg ist finalisiert — {', '.join(verletzt)} "
            f"{'sind' if len(verletzt) > 1 else 'ist'} nicht mehr änderbar. "
            "Für eine inhaltliche Korrektur den Beleg stornieren und neu "
            "ausstellen. Änderbar bleiben die interne Notiz und die "
            "Projektzuordnung.",
        )

    # Erlaubte Änderungen fürs Protokoll festhalten
    aenderungen = {}
    for feld in ("notes", "project_id"):
        alt, neu = getattr(inv, feld, None), getattr(body, feld, None)
        if (alt or None) != (neu or None):
            aenderungen[feld] = {"alt": str(alt) if alt else None,
                                 "neu": str(neu) if neu else None}
    return aenderungen


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[InvoiceListItem])
async def list_invoices(
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Wiederkehrende Vorlagen laufen bewusst in der Hauptliste mit (violett
    # markiert); der eigene Tab "Wiederkehrend" zeigt sie zusätzlich gefiltert.
    q = db.query(Invoice)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    if status:
        q = q.filter(Invoice.status == status)
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if search:
        like = f"%{search}%"
        # Kontakt- und Projekt-Datensätze (beide EntityRecord) mit passendem Namen
        entity_subq = db.query(EntityRecord.id).filter(EntityRecord.display_name.ilike(like))
        # Belege mit passendem Positions-/Artikeltext
        pos_subq = db.query(InvoicePosition.invoice_id).filter(or_(
            InvoicePosition.description.ilike(like),
            InvoicePosition.detail.ilike(like),
        ))
        q = q.filter(or_(
            Invoice.number.ilike(like),
            Invoice.title.ilike(like),
            Invoice.reference.ilike(like),
            Invoice.contact_id.in_(entity_subq),   # Suche nach Kontakt
            Invoice.project_id.in_(entity_subq),    # Suche nach Projekt
            Invoice.id.in_(pos_subq),               # Suche nach Artikel/Positionstext
        ))
    invoices = q.order_by(Invoice.date.desc(), Invoice.number.desc()).offset(skip).limit(limit).all()

    # Batch-Lookup Kontaktnamen
    contact_ids = list({inv.contact_id for inv in invoices if inv.contact_id})
    contact_map: dict = {}
    if contact_ids:
        recs = db.query(EntityRecord).filter(EntityRecord.id.in_(contact_ids)).all()
        for r in recs:
            contact_map[r.id] = r.display_name or ""

    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "doc_type": inv.doc_type,
            "number": inv.number,
            "date": inv.date,
            "due_date": inv.due_date,
            "contact_id": inv.contact_id,
            "contact_name": contact_map.get(inv.contact_id) if inv.contact_id else None,
            "title": inv.title,
            "total": inv.total,
            "currency": inv.currency,
            "status": inv.status,
            "created_at": inv.created_at,
            "is_recurring_template": inv.is_recurring_template,
            "recurring_source_id": inv.recurring_source_id,
            "valid_until": inv.valid_until,
            # Abgeleitet, nicht gespeichert — siehe services/angebot.py
            "expired": angebot_service.ist_abgelaufen(inv),
            "billing_stage": inv.billing_stage,
            "chain_id": inv.chain_id,
        })
    return result


@router.post("", response_model=InvoiceResponse)
async def create_invoice(
    body: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.doc_type not in TYPE_PREFIX:
        raise HTTPException(400, f"Ungültiger doc_type: {body.doc_type}")

    if body.date and period_service.ist_gesperrt(db, body.date):
        period_service.pruefe_periode_offen(db, body.date, "angelegt")

    _pruefe_stufe(body.doc_type, body.billing_stage)

    # Bewusst OHNE Nummer: Der Beleg entsteht als Entwurf, die Nummer fällt
    # erst beim Finalisieren (siehe _ensure_number).
    data = body.model_dump(exclude={"positions"})
    data["created_by"] = current_user.email
    data["updated_by"] = current_user.email
    # Bindefrist vorbelegen, wenn der Anwender keine angegeben hat. Ohne
    # Vorbelegung müsste sie bei jedem Angebot getippt werden — und wird
    # vergessen.
    if not data.get("valid_until"):
        data["valid_until"] = angebot_service.vorbelegen(db, body.doc_type, body.date)

    invoice = Invoice(**data)
    db.add(invoice)
    db.flush()

    # Eine Rechnung mit Abrechnungsstufe, die keinem Strang zugeordnet wurde,
    # eröffnet einen eigenen. Sonst stünde sie allein da und die spätere
    # Schlussrechnung fände sie nicht.
    if invoice.billing_stage and not invoice.chain_id:
        anzahlung_service.strang_anlegen(db, invoice)

    for i, pos_data in enumerate(body.positions):
        pos = InvoicePosition(invoice_id=invoice.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    db.refresh(invoice)
    _calc_totals(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/templates", response_model=List[InvoiceListItem])
async def list_recurring_templates(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Invoice).filter(Invoice.is_recurring_template == True)\
             .order_by(Invoice.created_at.desc()).all()


@router.get("/next-number", response_model=NextNumberResponse)
async def get_next_number(
    doc_type: str = Query("rechnung"),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    y = year or datetime.now().year
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    next_seq = (seq.last_sequence + 1) if seq else 1
    fmt_key = f"number_format_{doc_type}"
    setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
    if setting and setting.value:
        fmt = setting.value.strip('"') if isinstance(setting.value, str) else str(setting.value)
    else:
        prefix = TYPE_PREFIX.get(doc_type, "DO")
        fmt = f"{prefix}-{{year}}-{{seq:03d}}"
    preview = fmt.format(year=y, seq=next_seq)
    return {"doc_type": doc_type, "year": y, "next_sequence": next_seq, "preview": preview}

DOC_TYPES_LIST = ["rechnung", "angebot", "auftragsbestaetigung", "gutschrift", "lieferschein"]
DOC_TYPE_DEFAULTS = {
    "rechnung":             "RE-{year}-{seq:03d}",
    "angebot":              "AN-{year}-{seq:03d}",
    "auftragsbestaetigung": "AB-{year}-{seq:03d}",
    "gutschrift":           "GS-{year}-{seq:03d}",
    "lieferschein":         "LS-{year}-{seq:03d}",
}


@router.get("/number-sequences")
async def get_number_sequences(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt Nummernkreise (Format + aktueller Zähler) für alle Dokumenttypen zurück."""
    y = year or datetime.now().year
    result = []
    for doc_type in DOC_TYPES_LIST:
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
        fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
              or DOC_TYPE_DEFAULTS[doc_type]
        last = seq.last_sequence if seq else 0
        # Vorschau nächste Nummer
        preview = fmt.format(year=y, seq=last + 1)
        result.append({
            "doc_type": doc_type,
            "year": y,
            "format": fmt,
            "last_sequence": last,
            "next_sequence": last + 1,
            "next_preview": preview,
        })
    return result


@router.put("/number-sequences/{doc_type}")
async def update_number_sequence(
    doc_type: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Aktualisiert Format und/oder Zählerstand für einen Dokumenttyp.
    Body: { year, format, last_sequence }
    """
    if doc_type not in DOC_TYPES_LIST:
        raise HTTPException(400, f"Ungültiger Dokumenttyp: {doc_type}")

    y = body.get("year", datetime.now().year)

    # Format speichern
    if "format" in body:
        fmt_key = f"number_format_{doc_type}"
        setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
        if setting:
            setting.value = body["format"]
        else:
            setting = InvoiceSettings(key=fmt_key, value=body["format"])
            db.add(setting)

    # Zählerstand setzen — nur aufwärts.
    # Ein Zurücksetzen würde eine bereits vergebene Nummer ein zweites Mal
    # erzeugen; der UNIQUE-Index auf invoices.number bricht dann mit einem
    # unverständlichen Serverfehler ab.
    if "last_sequence" in body:
        new_seq = int(body["last_sequence"])
        if new_seq < 0:
            raise HTTPException(400, "Zählerstand darf nicht negativ sein")
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        if seq:
            if new_seq < seq.last_sequence:
                raise HTTPException(
                    400,
                    f"Der Zählerstand kann nur erhöht werden (aktuell "
                    f"{seq.last_sequence}). Ein Zurücksetzen würde eine bereits "
                    f"vergebene Belegnummer erneut erzeugen.",
                )
            seq.last_sequence = new_seq
        else:
            seq = InvoiceNumberSequence(doc_type=doc_type, year=y, last_sequence=new_seq)
            db.add(seq)

    db.commit()

    # Aktuellen Stand zurückgeben
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
    fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
          or DOC_TYPE_DEFAULTS[doc_type]
    last = seq.last_sequence if seq else 0
    return {
        "doc_type": doc_type,
        "year": y,
        "format": fmt,
        "last_sequence": last,
        "next_sequence": last + 1,
        "next_preview": fmt.format(year=y, seq=last + 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Belegeinstellungen (Key-Value-Store: Bankdaten, Vorlagen, Texte, Steuersätze)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings/all")
async def get_invoice_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt alle Belegeinstellungen als Dict {key: value} zurück."""
    werte = {r.key: r.value for r in db.query(InvoiceSettings).all()}
    # Die WIRKSAMEN Archiv-Auslöser mitliefern, auch wenn nichts gespeichert
    # ist. Sonst müsste die Oberfläche einen eigenen Vorgabewert vorhalten —
    # und würde ihn beim nächsten Speichern über den echten schreiben.
    from app.services.invoice_archive import get_archive_triggers
    from app.services import tax_rates as tax_rates_service
    werte.setdefault("archive_triggers", get_archive_triggers(db))
    # Dasselbe für die Steuersätze: Die Oberfläche soll die wirksamen Sätze
    # anzeigen, ohne eine eigene Kopie der Vorgabewerte vorzuhalten.
    werte["tax_rates"] = tax_rates_service.as_json(tax_rates_service.get_tax_rates(db))
    # Ebenso die Mahnstufen und die Zinsparameter: Die Oberfläche soll die
    # wirksamen Werte zeigen, nicht eine zweite Kopie der Vorgaben pflegen.
    werte["dunning_levels"] = dunning_service.get_levels(db)
    zins = dunning_service.get_zins_einstellungen(db)
    werte.setdefault("dunning_base_rate",
                     None if zins["basiszinssatz"] is None else float(zins["basiszinssatz"]))
    werte.setdefault("dunning_surcharge_b2b", float(zins["aufschlag_b2b"]))
    werte.setdefault("dunning_rate_b2c", float(zins["zins_b2c"]))
    werte.setdefault("dunning_interest_mode", zins["modus"])
    werte.setdefault("default_offer_valid_days", angebot_service.vorgabe_tage(db))
    # E-Rechnung ist standardmäßig AUS. Sie ändert das Dateiformat jedes
    # versendeten Belegs — das gehört eingeschaltet, nicht stillschweigend
    # übernommen.
    werte.setdefault("erechnung_aktiv", erechnung_service.ist_aktiv(db))
    return werte


@router.put("/settings/{key}")
async def update_invoice_setting(
    key: str,
    body: InvoiceSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Speichert eine einzelne Belegeinstellung (Upsert). Wert ist beliebiges JSON."""
    setting = db.query(InvoiceSettings).filter_by(key=key).first()
    if setting:
        setting.value = body.value
    else:
        setting = InvoiceSettings(key=key, value=body.value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": setting.value}


@router.get("/template-preview/{template_id}")
async def template_preview(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """HTML-Vorschau einer PDF-Vorlage mit Beispieldaten (Einstellungen → Belegeinstellungen)."""
    from types import SimpleNamespace
    from decimal import Decimal
    from datetime import timedelta

    if template_id not in (1, 2, 3, 4, 5):
        raise HTTPException(404, "Unbekannte Vorlage")

    settings     = {r.key: r.value for r in db.query(Setting).all()}
    inv_settings = {r.key: r.value for r in db.query(InvoiceSettings).all()}

    # Eigener Firmen-Kontakt als Absender (falls verknüpft)
    sender_contact = None
    cid = settings.get("company_contact_id")
    if cid:
        try:
            sender_contact = db.query(EntityRecord).filter(EntityRecord.id == UUID(cid)).first()
        except Exception:
            pass

    # Beispiel-Empfänger und -Positionen, damit die Vorschau realistisch aussieht
    recipient = SimpleNamespace(
        display_name="Musterfirma GmbH",
        data={"ansprechperson": "Max Mustermann", "adresse": "Musterstraße 1",
              "plz": "1010", "ort": "Wien", "land": "Österreich", "uid": "ATU12345678"},
    )
    positions = [
        SimpleNamespace(pos_type="item", description="Beratung & Konzeption",
                        detail="Workshop inkl. Vor- und Nachbereitung",
                        quantity=Decimal("8"), unit="Std.", unit_price=Decimal("120"),
                        discount_pct=None, tax_rate=Decimal("20"), line_total=Decimal("960.00")),
        SimpleNamespace(pos_type="item", description="Entwicklung Webanwendung",
                        detail=None, quantity=Decimal("24"), unit="Std.", unit_price=Decimal("95"),
                        discount_pct=Decimal("10"), tax_rate=Decimal("20"), line_total=Decimal("2052.00")),
        SimpleNamespace(pos_type="item", description="Hosting-Pauschale",
                        detail=None, quantity=Decimal("1"), unit="Pausch.", unit_price=Decimal("49.90"),
                        discount_pct=None, tax_rate=Decimal("20"), line_total=Decimal("49.90")),
    ]
    subtotal  = sum((p.line_total for p in positions), Decimal("0"))
    tax_total = (subtotal * Decimal("0.20")).quantize(Decimal("0.01"))
    today = date.today()
    demo_invoice = SimpleNamespace(
        doc_type="rechnung", status="offen", tax_mode="normal",
        number="RE-2026-042", date=today, due_date=today + timedelta(days=30),
        delivery_date=None, reference="Beispiel-Projekt",
        intro_text="Vielen Dank für Ihren Auftrag! Wir stellen folgende Leistungen in Rechnung:",
        outro_text="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
        subtotal=subtotal, tax_total=tax_total, total=subtotal + tax_total,
    )

    html = generate_html_preview(demo_invoice, positions, settings, inv_settings,
                                 sender_contact, recipient, template_id=template_id)
    return Response(content=html, media_type="text/html")


# ─────────────────────────────────────────────────────────────────────────────
# Belegbuch
# ─────────────────────────────────────────────────────────────────────────────

def _book_query(db: Session, date_from: Optional[date], date_to: Optional[date],
                doc_type: Optional[str]):
    """Gemeinsame Abfragelogik für Belegbuch-Endpoints."""
    q = db.query(Invoice).filter(Invoice.status != "entwurf")
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    return q.order_by(Invoice.date, Invoice.number)


@router.get("/book/list", dependencies=[Depends(require_module("buchhaltung"))])
async def get_book_list(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch-Liste mit Summen."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    # Kontaktnamen gesammelt laden (statt einer Abfrage je Beleg) und den
    # gepflegten Anzeigenamen verwenden — die Keys 'name'/'firma' gibt es in
    # den Stammdaten-Feldern nicht, die Spalte blieb dadurch immer leer.
    contact_ids = list({inv.contact_id for inv in invoices if inv.contact_id})
    contact_map: dict = {}
    if contact_ids:
        for r in db.query(EntityRecord).filter(EntityRecord.id.in_(contact_ids)).all():
            contact_map[r.id] = r.display_name or ""

    rows = []
    for inv in invoices:
        contact_name = contact_map.get(inv.contact_id) if inv.contact_id else None
        rows.append({
            "id": str(inv.id),
            "number": inv.number,
            "doc_type": inv.doc_type,
            "date": inv.date.isoformat() if inv.date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "title": inv.title,
            "contact_name": contact_name,
            "subtotal": float(inv.subtotal or 0),
            "tax_total": float(inv.tax_total or 0),
            "total": float(inv.total or 0),
            "status": inv.status,
            "currency": inv.currency,
        })

    return {
        "invoices": rows,
        "summary": {
            "count": len(rows),
            "total_net": float(total_net),
            "total_tax": float(total_tax),
            "total_gross": float(total_gross),
        },
    }


@router.get("/book/csv", dependencies=[Depends(require_module("buchhaltung"))])
async def get_book_csv(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als CSV-Download."""
    import csv as csv_mod
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    output = io.StringIO()
    writer = csv_mod.writer(output, delimiter=";")
    writer.writerow(["Nummer", "Typ", "Datum", "Fällig", "Titel", "Netto", "MwSt.", "Brutto", "Status"])

    for inv in invoices:
        writer.writerow([
            inv.number,
            inv.doc_type,
            inv.date.strftime("%d.%m.%Y") if inv.date else "",
            inv.due_date.strftime("%d.%m.%Y") if inv.due_date else "",
            inv.title or "",
            str(inv.subtotal or 0).replace(".", ","),
            str(inv.tax_total or 0).replace(".", ","),
            str(inv.total or 0).replace(".", ","),
            inv.status,
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=belegbuch.csv"},
    )


@router.get("/book/pdf", dependencies=[Depends(require_module("buchhaltung"))])
async def get_book_pdf(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als PDF-Download."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    def fmt_date(d):
        return d.strftime("%d.%m.%Y") if d else "—"

    def fmt_eur(n):
        return f"{float(n):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    period_label = ""
    if date_from and date_to:
        period_label = f"{fmt_date(date_from)} – {fmt_date(date_to)}"
    elif date_from:
        period_label = f"ab {fmt_date(date_from)}"
    elif date_to:
        period_label = f"bis {fmt_date(date_to)}"
    else:
        period_label = "Alle Zeiträume"

    rows_html = ""
    for inv in invoices:
        status_map = {
            "offen": "Offen", "bezahlt": "Bezahlt", "ueberfaellig": "Überfällig",
            "storniert": "Storniert", "gesendet": "Gesendet",
            "angenommen": "Angenommen", "abgelehnt": "Abgelehnt",
        }
        rows_html += f"""
        <tr>
          <td>{inv.number}</td>
          <td>{fmt_date(inv.date)}</td>
          <td>{fmt_date(inv.due_date)}</td>
          <td>{inv.title or '—'}</td>
          <td class="r">{fmt_eur(inv.subtotal or 0)}</td>
          <td class="r">{fmt_eur(inv.tax_total or 0)}</td>
          <td class="r"><b>{fmt_eur(inv.total or 0)}</b></td>
          <td>{status_map.get(inv.status, inv.status)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }}
  h1 {{ font-size: 16px; margin-bottom: 4px; }}
  p.sub {{ color: #666; font-size: 10px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #f3f4f6; text-align: left; padding: 6px 8px; border-bottom: 2px solid #d1d5db; font-size: 10px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; }}
  .r {{ text-align: right; }}
  tfoot td {{ font-weight: bold; background: #f9fafb; border-top: 2px solid #d1d5db; }}
</style>
</head><body>
<h1>Belegbuch</h1>
<p class="sub">Zeitraum: {period_label} &nbsp;|&nbsp; {len(invoices)} Dokumente</p>
<table>
  <thead><tr>
    <th>Nummer</th><th>Datum</th><th>Fällig</th><th>Titel</th>
    <th class="r">Netto</th><th class="r">MwSt.</th><th class="r">Brutto</th><th>Status</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
  <tfoot><tr>
    <td colspan="4">Gesamt ({len(invoices)})</td>
    <td class="r">{fmt_eur(total_net)}</td>
    <td class="r">{fmt_eur(total_tax)}</td>
    <td class="r">{fmt_eur(total_gross)}</td>
    <td></td>
  </tr></tfoot>
</table>
</body></html>"""

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    except Exception as e:
        # Kein HTML-Rückfall mehr: Der Browser lud die Datei als
        # „belegbuch.pdf" herunter und bekam HTML — der Fehler fiel erst beim
        # Öffnen auf, und dann sah es nach einer kaputten Datei aus statt nach
        # einem Serverproblem.
        raise HTTPException(500, f"PDF konnte nicht erzeugt werden: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=belegbuch.pdf"},
    )


@router.post("/positions/image")
async def upload_position_image(
    size: str = Query("mittel", description="klein | mittel | gross"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Nimmt ein Bild für eine Belegposition entgegen und verkleinert es sofort
    auf die gewählte Druckgröße.

    Bewusst **nicht** an eine Position gebunden: Positionen werden beim
    Speichern gelöscht und neu angelegt, haben also keine dauerhafte Kennung.
    Zurück kommt der Speicher-Schlüssel, den das Formular als Feld der Position
    mitführt — genau wie das Erlöskonto.
    """
    from app.services import position_image, storage_service

    if file.content_type and file.content_type not in position_image.ERLAUBTE_TYPEN:
        raise HTTPException(400, f"Dateityp {file.content_type} wird nicht unterstützt. "
                                 f"Erlaubt sind JPEG, PNG, WebP und GIF.")
    rohdaten = await file.read()
    if len(rohdaten) > position_image.MAX_UPLOAD:
        raise HTTPException(400, "Bild zu groß (max. 15 MB)")

    daten, mime, endung = position_image.verkleinern(rohdaten, size)
    schluessel = position_image.speicher_schluessel(endung)
    # Den Speicher festhalten, in den wir schreiben. Ohne diese Angabe wird die
    # Datei nach einem Speicherwechsel am falschen Ort gesucht — dieselbe
    # Lehre wie bei den Anhängen (Migration 0039).
    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(schluessel, daten, mime, db=db, backend=backend)
    except Exception as exc:
        raise HTTPException(500, f"Speicher-Fehler: {exc}")

    return {"image_key": schluessel, "image_size": size, "image_provider": backend,
            "breite_mm": position_image.breite_mm(size), "bytes": len(daten)}


@router.get("/positions/image")
async def get_position_image(
    key: str = Query(..., description="Speicher-Schlüssel aus dem Upload"),
    provider: Optional[str] = Query(None, description="Speicher der Datei; leer = aktiver"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Liefert ein Positionsbild aus — für die Vorschau im Formular."""
    from app.services import storage_service
    if not key.startswith("belege/positionsbilder/"):
        raise HTTPException(400, "Ungültiger Bildschlüssel")
    try:
        daten, mime = storage_service.download_file(key, db=db, backend=provider)
    except Exception:
        raise HTTPException(404, "Bild nicht gefunden")
    return Response(content=daten, media_type=mime or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/uva", response_model=UvaResponse,
            dependencies=[Depends(require_module("buchhaltung"))])
async def get_uva(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Umsatzsteuer-Auswertung für die Voranmeldung (Formular U30).

    Liefert je Steuersatz die Bemessungsgrundlage und den Steuerbetrag, dazu
    die Kennzahl aus den Verkaufseinstellungen. Belegt sind 022 (20 %),
    029 (10 %) und 006 (13 %); für steuerfreie Umsätze hängt die Kennzahl vom
    Sachverhalt ab (Ausfuhr, innergemeinschaftliche Lieferung, Reverse Charge)
    und wird bewusst nicht geraten — solche Zeilen erscheinen mit dem Vermerk
    „Kennzahl nicht zugeordnet".

    Enthalten sind Rechnungen und Gutschriften, die ausgestellt und nicht
    storniert sind. Gutschriften mindern die Bemessungsgrundlage, weil ihre
    Beträge negativ geführt werden.

    **Das ist eine Aufbereitung, keine Steuerberatung.** Die Zuordnung von
    Sonderfällen gehört geprüft, bevor die Zahlen in die Voranmeldung gehen.
    """
    from decimal import Decimal
    from collections import defaultdict
    from app.services import tax_rates as tax_rates_service

    belege = _book_query(db, date_from, date_to, None).filter(
        Invoice.doc_type.in_(["rechnung", "gutschrift"]),
        Invoice.is_recurring_template == False,
        or_(Invoice.status != "storniert", Invoice.cancel_mode == "with_credit"),
    ).all()

    saetze = tax_rates_service.get_tax_rates(db)
    kz_je_satz = {s["satz"]: (s["uva_kz"], s["bezeichnung"]) for s in saetze}

    netto_je_satz: dict = defaultdict(lambda: Decimal("0"))
    rc_netto = Decimal("0")

    for beleg in belege:
        if beleg.tax_mode == "kleinunternehmer":
            # Unecht steuerbefreit: kein Satz, kein Steuerbetrag. Die
            # Bemessungsgrundlage ist die gespeicherte Nettosumme.
            netto_je_satz[Decimal("0")] += Decimal(str(beleg.subtotal or 0))
            continue
        # Über den Positionen-Dienst statt über eine eigene Schleife: Nur er
        # kennt die Gliederungszeilen und verteilt eine Rabattzeile anteilig
        # auf die Sätze ihrer Gruppe. Die frühere Schleife hier zählte einen
        # Rabatt mangels Steuersatz als Reverse-Charge-Umsatz — die
        # Bemessungsgrundlage war damit auf beiden Seiten falsch.
        for satz, netto in positionen_service.netto_je_satz(
                list(beleg.positions), beleg.tax_mode).items():
            if satz is None:
                rc_netto += netto            # Reverse Charge: kein Satz am Beleg
            else:
                netto_je_satz[Decimal(str(satz))] += netto

    # Skonto mindert das Entgelt im Monat der Zahlung (§ 16 UStG) — nicht im
    # Monat der Rechnung. Deshalb hängt die Korrektur am Zahlungsdatum und
    # kommt hier als eigener Posten dazu, statt den Beleg rückwirkend zu ändern.
    # Der Steuerbetrag wird weiter unten aus der Bemessungsgrundlage gerechnet;
    # die geminderte Grundlage ergibt damit automatisch die berichtigte Steuer.
    korrektur = skonto_service.korrektur_je_satz(db, date_from, date_to)
    skonto_gesamt = Decimal("0")
    for satz, wert in korrektur["netto"].items():
        if satz is None:
            rc_netto += wert
        else:
            netto_je_satz[Decimal(str(satz))] += wert
        skonto_gesamt += wert

    land = tax_rates_service.get_company_country(db)
    land_unterstuetzt = land in tax_rates_service.SUPPORTED_COUNTRIES

    zeilen, hinweise = [], []
    kz_gesamt = Decimal("0")
    steuer_gesamt = Decimal("0")

    if not land_unterstuetzt:
        hinweise.append(
            f"Als Steuerland ist „{land}“ eingestellt. Die Kennzahlen unten "
            f"stammen aus dem österreichischen Formular U30 und passen dann "
            f"nicht — die Beträge je Steuersatz stimmen, die Zuordnung nicht.")

    # Der frühere Vermerk „enthält nur die Umsatzseite" ist mit den
    # Eingangsrechnungen entfallen — die Vorsteuer kommt jetzt weiter unten
    # dazu. Der Vorbehalt bleibt trotzdem: Aufbereitung, keine Steuerberatung.
    hinweise.append(
        "Diese Auswertung ist eine Aufbereitung aus den erfassten Belegen. "
        "Sonderfälle gehören vor der Abgabe mit der Steuerberatung geprüft.")

    if skonto_gesamt:
        hinweise.append(
            f"Enthalten ist eine Entgeltminderung aus gewährten Skonti von "
            f"{float(-skonto_gesamt):.2f} netto (§ 16 UStG). Sie wirkt im "
            f"Monat der Zahlung — die zugehörigen Rechnungen können aus einem "
            f"früheren Zeitraum stammen.")

    for satz in sorted(netto_je_satz, reverse=True):
        netto = netto_je_satz[satz]
        steuer = (netto * satz / 100).quantize(Decimal("0.01"))
        kennzahl, bezeichnung = kz_je_satz.get(satz, ("", f"{satz} %"))
        zeilen.append(UvaZeile(
            kennzahl=kennzahl, bezeichnung=bezeichnung, satz=satz,
            bemessungsgrundlage=netto, steuer=steuer, zugeordnet=bool(kennzahl),
        ))
        kz_gesamt += netto
        steuer_gesamt += steuer
        if not kennzahl:
            hinweise.append(
                f"Für den Steuersatz {bezeichnung} ist keine UVA-Kennzahl "
                f"hinterlegt — bitte in den Verkaufseinstellungen ergänzen.")

    if rc_netto:
        zeilen.append(UvaZeile(
            kennzahl="", bezeichnung="Reverse Charge (Steuerschuld geht über)",
            satz=None, bemessungsgrundlage=rc_netto, steuer=Decimal("0"),
            zugeordnet=False,
        ))
        kz_gesamt += rc_netto
        hinweise.append(
            "Reverse-Charge-Umsätze laufen je nach Sachverhalt über "
            "unterschiedliche Kennzahlen (z.B. innergemeinschaftliche "
            "Lieferung oder Bauleistung). Die Zuordnung gehört mit der "
            "Steuerberatung geklärt.")

    # ── Vorsteuerseite aus den Eingangsrechnungen ────────────────────────────
    #
    # Bis Etappe 7 endete die Auswertung hier, mit dem Vermerk, dass die
    # Vorsteuer fehlt. Reverse Charge und innergemeinschaftlicher Erwerb
    # erzeugen dabei ZWEI Zeilen: die selbst geschuldete Steuer und — bei
    # Abzugsberechtigung — die gleich hohe Vorsteuer.
    from app.services import vorsteuer as vorsteuer_service
    vst = vorsteuer_service.auswertung(db, date_from, date_to)

    for z in vst["zeilen"]:
        zeilen.append(UvaZeile(
            kennzahl=z["kennzahl"], bezeichnung=z["bezeichnung"], satz=None,
            bemessungsgrundlage=z["grundlage"], steuer=z["betrag"],
            zugeordnet=z["zugeordnet"],
        ))
        # Selbst geschuldete Steuer erhöht die Zahllast, Vorsteuer mindert sie.
        # Die Bemessungsgrundlage der Umsatzseite (KZ 000) bleibt unberührt —
        # dort gehören nur eigene Umsätze hinein.
        steuer_gesamt += z["betrag"] if z["art"] == "steuerschuld" else -z["betrag"]

    hinweise.extend(vst["hinweise"])
    if vst["beleg_anzahl"] == 0:
        hinweise.append(
            "Im Zeitraum ist keine Eingangsrechnung erfasst — die Auswertung "
            "enthält damit keine Vorsteuer. Bitte prüfen, ob das stimmt.")

    return UvaResponse(
        date_from=date_from, date_to=date_to,
        country=land, country_supported=land_unterstuetzt, zeilen=zeilen,
        kz_000=kz_gesamt, steuer_gesamt=steuer_gesamt,
        beleg_anzahl=len(belege) + vst["beleg_anzahl"], hinweise=hinweise,
    )


@router.get("/uva/pdf", dependencies=[Depends(require_module("buchhaltung"))])
async def get_uva_pdf(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Umsatzsteuer-Auswertung als Ausdruck, Zeile für Zeile nach dem Formular U30.

    Bewusst ein Ausdruck zum Abtippen und **keine** Übermittlung: DeineZeit
    erfasst keine Eingangsrechnungen, damit fehlt die gesamte Vorsteuerseite
    der Voranmeldung. Eine Meldung mit Vorsteuer null würde deutlich zu viel
    Umsatzsteuer ausweisen. Der Ausdruck sagt das an mehreren Stellen deutlich.
    """
    from app.services import tax_rates as tax_rates_service

    daten = await get_uva(date_from=date_from, date_to=date_to, db=db, _=current_user)
    settings = {r.key: r.value for r in db.query(Setting).all()}
    firma = settings.get("company_name", "") or "—"
    land = tax_rates_service.SUPPORTED_COUNTRIES.get(daten.country, daten.country)

    def eur(n):
        return f"{float(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def dat(d):
        return d.strftime("%d.%m.%Y") if d else "—"

    zeitraum = (f"{dat(date_from)} – {dat(date_to)}" if (date_from or date_to)
                else "Alle Zeiträume")

    zeilen_html = ""
    for z in daten.zeilen:
        kz = z.kennzahl or '<span class="offen">nicht zugeordnet</span>'
        zeilen_html += f"""
        <tr>
          <td class="kz">{kz}</td>
          <td>{z.bezeichnung}</td>
          <td class="r">{eur(z.bemessungsgrundlage)}</td>
          <td class="r">{eur(z.steuer)}</td>
        </tr>"""

    hinweise_html = "".join(f"<li>{h}</li>" for h in daten.hinweise)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 2cm; }}
      body {{ font-family: Arial, sans-serif; font-size: 10.5pt; color: #222; }}
      h1 {{ font-size: 15pt; margin: 0 0 2px 0; }}
      .sub {{ color: #666; font-size: 9pt; margin-bottom: 18px; }}
      .warn {{ background: #fff4e5; border: 1px solid #f0c48a; border-radius: 4px;
               padding: 10px 12px; margin-bottom: 18px; font-size: 9pt; }}
      .warn b {{ display: block; margin-bottom: 3px; }}
      .warn ul {{ margin: 6px 0 0 16px; padding: 0; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
      th {{ background: #f3f4f6; text-align: left; padding: 6px 8px;
            border-bottom: 2px solid #d1d5db; font-size: 9pt; }}
      td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }}
      .r {{ text-align: right; }}
      .kz {{ font-family: "Courier New", monospace; font-weight: bold; width: 3.5cm; }}
      .offen {{ color: #b45309; font-weight: normal; font-family: Arial; }}
      tfoot td {{ font-weight: bold; background: #f9fafb; border-top: 2px solid #d1d5db; }}
      .fuss {{ margin-top: 22px; font-size: 8pt; color: #777; line-height: 1.5; }}
    </style></head><body>
      <h1>Umsatzsteuer — Aufstellung der Umsätze</h1>
      <p class="sub">{firma} &nbsp;|&nbsp; Zeitraum: {zeitraum}
         &nbsp;|&nbsp; Steuerland: {land}
         &nbsp;|&nbsp; {daten.beleg_anzahl} Belege
         &nbsp;|&nbsp; erstellt am {date.today():%d.%m.%Y}</p>

      <div class="warn">
        <b>Diese Aufstellung ist keine vollständige Umsatzsteuervoranmeldung.</b>
        Sie enthält ausschließlich die Umsatzseite. Vorsteuer (KZ 060),
        Einfuhrumsatzsteuer (KZ 061) und innergemeinschaftliche Erwerbe
        (KZ 070 ff.) werden in DeineZeit nicht erfasst und sind vor der Abgabe
        zu ergänzen. Die Kennzahlen folgen dem österreichischen Formular U30.
        {"<ul>" + hinweise_html + "</ul>" if hinweise_html else ""}
      </div>

      <table>
        <thead><tr>
          <th>Kennzahl</th><th>Bezeichnung</th>
          <th class="r">Bemessungsgrundlage</th><th class="r">Umsatzsteuer</th>
        </tr></thead>
        <tbody>{zeilen_html or '<tr><td colspan="4">Keine umsatzsteuerrelevanten Belege im Zeitraum.</td></tr>'}</tbody>
        <tfoot><tr>
          <td class="kz">000</td>
          <td>Gesamtbetrag der Bemessungsgrundlage</td>
          <td class="r">{eur(daten.kz_000)}</td>
          <td class="r">{eur(daten.steuer_gesamt)}</td>
        </tr></tfoot>
      </table>

      <p class="fuss">
        Aufbereitung aus den Verkaufsbelegen, keine Steuerberatung. Enthalten sind
        ausgestellte Rechnungen und Gutschriften; Entwürfe, Angebote,
        Auftragsbestätigungen und Lieferscheine bleiben unberücksichtigt.
        Stornierte Belege zählen nur mit, wenn eine Gutschrift dagegensteht.
        Die Zuordnung der Kennzahlen — besonders bei Ausfuhr, innergemeinschaftlichen
        Lieferungen und Reverse Charge — gehört mit der Steuerberatung geprüft.
      </p>
    </body></html>"""

    try:
        import weasyprint
        pdf = weasyprint.HTML(string=html).write_pdf()
    except Exception as e:
        raise HTTPException(500, f"PDF konnte nicht erzeugt werden: {e}")

    name = f"umsatzsteuer_{date_from or 'alle'}_{date_to or ''}".rstrip("_")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


# ─────────────────────────────────────────────────────────────────────────────
# Offene Posten
#
# Muss VOR "/{invoice_id}" stehen, sonst schluckt die Detailroute den Pfad.
# ─────────────────────────────────────────────────────────────────────────────

# Fälligkeitsstaffel — die übliche Einteilung in Debitorenauswertungen
BUCKETS = [
    ("nicht_faellig", "Nicht fällig"),
    ("b1_30",         "1–30 Tage"),
    ("b31_60",        "31–60 Tage"),
    ("b61_90",        "61–90 Tage"),
    ("b90_plus",      "über 90 Tage"),
]


def _bucket_fuer(tage: int) -> str:
    if tage <= 0:
        return "nicht_faellig"
    if tage <= 30:
        return "b1_30"
    if tage <= 60:
        return "b31_60"
    if tage <= 90:
        return "b61_90"
    return "b90_plus"


@router.get("/open-items", response_model=OpenItemsResponse, dependencies=[Depends(require_module("buchhaltung"))])
async def get_open_items(
    contact_id: Optional[UUID] = Query(None),
    stichtag: Optional[date] = Query(None, description="Standard: heute"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Offene-Posten-Liste mit Fälligkeitsstaffel.

    Die Standardauswertung der Debitorenbuchhaltung: Welche ausgestellten
    Belege sind noch nicht (vollständig) beglichen, wie lange schon, und wie
    verteilt sich das auf die Kunden.

    Enthalten sind Rechnungen und Gutschriften, die ausgestellt und nicht
    storniert sind und bei denen noch etwas offen ist. Entwürfe, Angebote,
    Auftragsbestätigungen und Lieferscheine sind keine Forderungen.
    """
    from decimal import Decimal

    heute = stichtag or date.today()

    q = db.query(Invoice).filter(
        Invoice.is_recurring_template == False,
        Invoice.doc_type.in_(["rechnung", "gutschrift"]),
        Invoice.status.notin_(["entwurf", "storniert"]),
    )
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    belege = q.order_by(Invoice.due_date.asc().nullslast(), Invoice.date.asc()).all()

    kontakt_ids = list({b.contact_id for b in belege if b.contact_id})
    kontakt_map = {}
    if kontakt_ids:
        for r in db.query(EntityRecord).filter(EntityRecord.id.in_(kontakt_ids)).all():
            kontakt_map[r.id] = r.display_name or ""

    items, summen_je_kontakt = [], {}
    buckets = {schluessel: Decimal("0") for schluessel, _ in BUCKETS}
    gesamt_offen = Decimal("0")

    for b in belege:
        gezahlt, offen, _ueber = _zahlstand(b)
        if abs(offen) < Decimal("0.01"):
            continue                      # beglichen — kein offener Posten

        tage = (heute - b.due_date).days if b.due_date else 0
        bucket = _bucket_fuer(tage)
        buckets[bucket] += offen
        gesamt_offen += offen

        eintrag = summen_je_kontakt.setdefault(
            b.contact_id, {"contact_id": b.contact_id,
                           "contact_name": kontakt_map.get(b.contact_id),
                           "open_amount": Decimal("0"), "count": 0})
        eintrag["open_amount"] += offen
        eintrag["count"] += 1

        items.append(OpenItem(
            id=b.id, number=b.number, doc_type=b.doc_type, date=b.date,
            due_date=b.due_date, contact_id=b.contact_id,
            contact_name=kontakt_map.get(b.contact_id), title=b.title,
            total=b.total, paid_total=gezahlt, open_amount=offen,
            status=b.status, days_overdue=max(0, tage), bucket=bucket,
        ))

    return OpenItemsResponse(
        items=items,
        by_contact=sorted(
            (OpenItemsByContact(**e) for e in summen_je_kontakt.values()),
            key=lambda e: abs(e.open_amount), reverse=True),
        buckets={k: float(v) for k, v in buckets.items()},
        total_open=gesamt_offen,
        count=len(items),
    )


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
async def list_payments(
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
async def add_payment(
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
async def delete_payment(
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
# Mahnwesen
#
# Die Reihenfolge der Routen ist hier wichtig: Alles unter „/dunning/…" muss
# VOR „/{invoice_id}" stehen, sonst schluckt der Platzhalter den festen Pfad.
#
# Sämtliche Mahn-Endpunkte hängen am Zusatzrecht „Buchhaltung" — genau wie die
# Offene-Posten-Liste. Der Mahnlauf zeigt dieselben Zahlen: welcher Kunde
# schuldet wie viel seit wann. Wäre er ohne das Recht erreichbar, stünde die
# Sperre der OP-Liste nur auf dem Papier.
MAHN_RECHT = [Depends(require_module("buchhaltung"))]
# ─────────────────────────────────────────────────────────────────────────────

def _kontakt(db: Session, contact_id):
    if not contact_id:
        return None
    return db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()


@router.get("/dunning/run", response_model=DunningRunResponse, dependencies=MAHN_RECHT)
async def dunning_run(
    stichtag: Optional[date] = Query(None, description="Standard: heute"),
    contact_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Mahnlauf-Vorschau: was wäre heute zu mahnen.

    Verschickt wird hier nichts. Die Liste enthält bewusst auch die nicht
    mahnbaren Belege samt Begründung — sonst rätselt man, warum eine Rechnung
    fehlt, die man erwartet hätte.
    """
    daten = dunning_service.kandidaten(db, stichtag, contact_id)
    return DunningRunResponse(
        stichtag=daten["stichtag"],
        items=[DunningCandidate(**z) for z in daten["items"]],
        dunnable_count=daten["dunnable_count"],
        levels=[DunningLevelConfig(**s) for s in daten["levels"]],
        interest_hint=daten["interest_hint"],
    )


def _mahnung_erzeugen(db: Session, inv: Invoice, level: Optional[int],
                      stichtag: date, force: bool, benutzer: str,
                      batch_id=None) -> InvoiceDunning:
    """
    Gemeinsamer Kern von Einzel- und Sammelmahnung.

    Wirft 400 mit einer Begründung, wenn nicht gemahnt werden darf. Die
    Mahnsperre ist auch mit ``force`` nicht zu übergehen: Sie wurde bewusst
    gesetzt, ein Sammellauf darf sie nicht versehentlich aushebeln.
    """
    if inv.doc_type != "rechnung":
        raise HTTPException(400, "Nur Rechnungen können gemahnt werden")
    if inv.status in ("entwurf", "storniert"):
        raise HTTPException(400, "Entwürfe und stornierte Belege werden nicht gemahnt")

    kontakt = _kontakt(db, inv.contact_id)
    grund = dunning_service.sperrgrund(inv, dunning_service.kontakt_gesperrt(kontakt))
    if grund:
        raise HTTPException(400, grund)

    _, offen, _ = _zahlstand(inv)
    if offen <= Decimal("0.00"):
        raise HTTPException(400, "Der Beleg ist beglichen — es gibt nichts zu mahnen")

    stufen = dunning_service.get_levels(db)
    if level is None:
        stufe = dunning_service.naechste_stufe(inv, stufen)
        if stufe is None:
            raise HTTPException(400, "Alle Mahnstufen sind ausgeschöpft")
    else:
        stufe = next((s for s in stufen if s["level"] == level), None)
        if stufe is None:
            raise HTTPException(400, f"Mahnstufe {level} ist nicht eingerichtet")

    if not force:
        ab = dunning_service.mahnbar_ab(inv, stufe)
        if ab is None:
            raise HTTPException(400, "Ohne Zahlungsziel gibt es keinen Verzug — "
                                     "bitte zuerst ein Zahlungsziel hinterlegen.")
        if ab > stichtag:
            raise HTTPException(400, f"Diese Mahnstufe ist erst ab "
                                     f"{ab:%d.%m.%Y} an der Reihe.")

    eintrag = dunning_service.mahnung_anlegen(
        db, inv, stufe, stichtag=stichtag, benutzer=benutzer,
        batch_id=batch_id, kontakt=kontakt)

    bezeichnung = stufe.get("label") or f"Stufe {stufe['level']}"
    _audit(db, inv, "mahnung",
           note=f"{bezeichnung} erstellt — offen "
                f"{float(eintrag.open_amount):.2f} {inv.currency}, Gebühr "
                f"{float(eintrag.fee):.2f}, Zinsen {float(eintrag.interest):.2f}",
           user_email=benutzer)
    return eintrag


@router.post("/dunning/batch", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
async def dunning_batch(
    body: DunningBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sammelmahnlauf über eine Auswahl von Belegen.

    Belege desselben Kunden teilen sich eine ``batch_id`` — daraus entsteht das
    Sammelschreiben. Ein einzelner abgelehnter Beleg (Sperre, Wartezeit) lässt
    den Lauf NICHT scheitern: Er wird übersprungen, der Rest läuft durch.
    Andernfalls müsste man den Lauf nach jedem Sonderfall neu zusammenstellen.
    """
    stichtag = body.dunned_at or date.today()
    if not body.invoice_ids:
        raise HTTPException(400, "Keine Belege ausgewählt")

    belege = db.query(Invoice).filter(Invoice.id.in_(body.invoice_ids)).all()
    batch_je_kontakt: dict = {}
    ergebnis = []

    for inv in belege:
        schluessel = inv.contact_id or inv.id
        batch_id = batch_je_kontakt.setdefault(schluessel, uuid4())
        try:
            ergebnis.append(_mahnung_erzeugen(
                db, inv, None, stichtag, body.force, current_user.email, batch_id))
        except HTTPException:
            continue                    # Begründung steht im Mahnlauf

    if not ergebnis:
        raise HTTPException(400, "Kein einziger der gewählten Belege war mahnbar")
    db.commit()
    return ergebnis


@router.get("/dunning/{dunning_id}/pdf", dependencies=MAHN_RECHT)
async def dunning_pdf(
    dunning_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Mahnschreiben als PDF. Bei einer Sammelmahnung stehen alle Belege des Laufs drauf."""
    from app.services.dunning_pdf import generate_dunning_pdf

    eintrag = db.query(InvoiceDunning).filter(InvoiceDunning.id == dunning_id).first()
    if not eintrag:
        raise HTTPException(404, "Mahnung nicht gefunden")

    pdf_bytes, dateiname = generate_dunning_pdf(db, eintrag)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{dateiname}"'})


@router.delete("/dunning/{dunning_id}", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
async def dunning_zuruecknehmen(
    dunning_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Nimmt eine Mahnung zurück (Fehleingabe) und setzt die Stufe auf den
    verbliebenen Höchststand zurück.

    Das Schreiben selbst ist damit natürlich nicht zurückgeholt — der Vorgang
    bleibt deshalb im Änderungsprotokoll stehen.
    """
    eintrag = db.query(InvoiceDunning).filter(InvoiceDunning.id == dunning_id).first()
    if not eintrag:
        raise HTTPException(404, "Mahnung nicht gefunden")

    inv = db.query(Invoice).filter(Invoice.id == eintrag.invoice_id).first()
    beschreibung = (f"{eintrag.label or f'Stufe {eintrag.level}'} vom "
                    f"{eintrag.dunned_at:%d.%m.%Y} zurückgenommen")
    db.delete(eintrag)
    db.flush()
    db.refresh(inv)

    rest = sorted(inv.dunnings, key=lambda d: d.level)
    inv.dunning_level = rest[-1].level if rest else 0
    inv.dunning_last_at = max((d.dunned_at for d in rest), default=None)
    _audit(db, inv, "mahnung", note=beschreibung, user_email=current_user.email)

    db.commit()
    db.refresh(inv)
    return sorted(inv.dunnings, key=lambda d: d.level)


@router.get("/{invoice_id}/dunning", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
async def dunning_historie(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Mahnhistorie eines Belegs."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    return sorted(inv.dunnings, key=lambda d: d.level)


@router.post("/{invoice_id}/dunning", response_model=DunningEntry, dependencies=MAHN_RECHT)
async def dunning_anlegen(
    invoice_id: UUID,
    body: DunningCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erzeugt eine Mahnung zu einem einzelnen Beleg."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    eintrag = _mahnung_erzeugen(db, inv, body.level, body.dunned_at or date.today(),
                                body.force, current_user.email)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.post("/{invoice_id}/dunning-block", response_model=InvoiceResponse, dependencies=MAHN_RECHT)
async def dunning_sperre(
    invoice_id: UUID,
    body: DunningBlockRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Setzt oder löst die Mahnsperre für einen Beleg (Ratenvereinbarung,
    strittige Forderung, Klärung mit dem Kunden).
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    inv.dunning_blocked = bool(body.blocked)
    inv.dunning_block_reason = body.reason if body.blocked else None
    inv.updated_by = current_user.email
    _audit(db, inv, "mahnung",
           note=(f"Mahnsperre gesetzt: {body.reason or 'ohne Begründung'}"
                 if body.blocked else "Mahnsperre aufgehoben"),
           user_email=current_user.email)
    db.commit()
    db.refresh(inv)
    return inv


# ─────────────────────────────────────────────────────────────────────────────
# Skonto
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{invoice_id}/skonto", response_model=SkontoVorschau)
async def skonto_vorschau(
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

    datum = paid_at or date.today()
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
async def skonto_ausbuchen(
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


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return inv


@router.get("/{invoice_id}/audit", response_model=List[InvoiceAuditEntry])
async def get_invoice_audit(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Änderungsprotokoll eines Belegs, neueste Änderung zuerst.

    Protokolliert wird ab dem Finalisieren — am Entwurf wird laufend
    gearbeitet, das wäre nur Rauschen.
    """
    if not db.query(Invoice.id).filter(Invoice.id == invoice_id).first():
        raise HTTPException(404, "Beleg nicht gefunden")
    return (db.query(InvoiceAuditLog)
            .filter(InvoiceAuditLog.invoice_id == invoice_id)
            .order_by(InvoiceAuditLog.changed_at.desc())
            .all())


# ── Auswertungen (C-15) ───────────────────────────────────────────────────────
#
# Alle vier hinter dem Modulrecht `buchhaltung`: Sie zeigen dieselben Zahlen
# wie Verkaufsbuch und UVA, nur anders geschnitten. Ein Recht, das dort greift
# und hier nicht, wäre über die Auswertung umgehbar.

AUSWERTUNG_RECHT = [Depends(require_module("buchhaltung"))]


@router.get("/auswertung/umsatz-jahr", response_model=UmsatzJahrResponse,
            dependencies=AUSWERTUNG_RECHT)
async def umsatz_je_monat(
    jahr: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Monatsumsatz eines Jahres mit Vorjahresvergleich."""
    return auswertungen_service.je_monat(db, jahr or datetime.now().year)


@router.get("/auswertung/umsatz-kunden", response_model=UmsatzKundeResponse,
            dependencies=AUSWERTUNG_RECHT)
async def umsatz_je_kunde(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(0, ge=0, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Rangliste der Kunden. ``limit=0`` gibt alle zurück."""
    return auswertungen_service.je_kunde(db, date_from, date_to, limit)


@router.get("/auswertung/umsatz-artikel", response_model=UmsatzArtikelResponse,
            dependencies=AUSWERTUNG_RECHT)
async def umsatz_je_artikel(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(0, ge=0, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Rangliste der Artikel.

    Die Antwort nennt ausdrücklich, wie viel Umsatz sich **keinem** Artikel
    zuordnen ließ — bei überwiegend frei getippten Positionen ist die Liste
    sonst eine Genauigkeit, die es nicht gibt.
    """
    return auswertungen_service.je_artikel(db, date_from, date_to, limit)


@router.get("/auswertung/angebotsquote", response_model=AngebotsquoteResponse,
            dependencies=AUSWERTUNG_RECHT)
async def angebotsquote(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Wie viele Angebote zu Aufträgen werden, gezählt nach Angebotsdatum."""
    return auswertungen_service.angebotsquote(db, date_from, date_to)


# ── E-Rechnung (C-5) ──────────────────────────────────────────────────────────

@router.get("/{invoice_id}/erechnung/pruefen", response_model=ERechnungPruefung)
async def check_einvoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_module("verkauf")),
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
async def download_einvoice_xml(
    invoice_id: UUID,
    trotz_luecken: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_module("verkauf")),
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
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Beleg als PDF herunterladen (Vorlage + Fußzeile wie in den Einstellungen)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)
    xml = erechnung_service.xml_fuer_pdf(db, inv, inv_settings_d,
                                          sender_contact, recipient_contact)
    try:
        pdf_bytes = generate_pdf(inv, inv.positions, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, db=db,
                                 erechnung_xml=xml)
    except Exception as e:
        raise HTTPException(500, f"PDF konnte nicht erzeugt werden: {str(e)}")

    filename = f"{(inv.number or 'beleg').replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{invoice_id}/preview")
async def preview_invoice_html(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """HTML-Vorschau eines Belegs (für das Vorschau-Popup im Beleg-Formular)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)
    html = generate_html_preview(inv, inv.positions, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, db=db)
    return Response(content=html, media_type="text/html")


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege können nicht bearbeitet werden")
    # Beide Daten prüfen: aus einem abgeschlossenen Monat heraus- und in
    # einen hineinzubuchen ist gleichermaßen gesperrt.
    _pruefe_periode(db, inv)
    period_service.pruefe_periode_offen(db, body.date, "angelegt")

    # ── Finalisierter Beleg: nur noch Nicht-Gedrucktes änderbar ──────────────
    if inv.status != "entwurf":
        erlaubte_aenderungen = _pruefe_belegsperre(inv, body)   # wirft 400 bei Verstoß

        inv.notes = body.notes
        inv.project_id = body.project_id
        inv.updated_by = current_user.email
        # Altbestand ohne Snapshot nachziehen (Empfänger ist gesperrt, ein
        # force-Neuaufbau kommt daher nicht mehr vor)
        ensure_recipient_snapshot(db, inv)

        if erlaubte_aenderungen:
            _audit(db, inv, "bearbeitet", changes=erlaubte_aenderungen,
                   user_email=current_user.email)

        db.commit()
        db.refresh(inv)
        return inv

    # ── Entwurf: frei bearbeitbar ────────────────────────────────────────────
    _pruefe_stufe(inv.doc_type, body.billing_stage)
    update_data = body.model_dump(exclude={"positions"})
    for k, v in update_data.items():
        setattr(inv, k, v)
    inv.updated_by = current_user.email
    # Wer eine Rechnung nachträglich zur Anzahlung erklärt, eröffnet damit
    # einen Strang — sonst fände die spätere Schlussrechnung sie nicht.
    if inv.billing_stage and not inv.chain_id:
        anzahlung_service.strang_anlegen(db, inv)

    # Positionen ersetzen. Vorher merken, welche Bilder daran hingen — beim
    # Speichern werden alle Positionen gelöscht und neu angelegt, und ein Bild,
    # dessen Position verschwindet, bliebe sonst für immer im Speicher liegen.
    alte_bilder = {p.image_key: p.image_provider for p in inv.positions if p.image_key}

    db.query(InvoicePosition).filter(InvoicePosition.invoice_id == invoice_id).delete()
    for i, pos_data in enumerate(body.positions):
        # Der Anzahlungsabzug wird nicht vom Formular übernommen, sondern
        # gleich darunter neu gerechnet: Er hängt an den bereits gestellten
        # Rechnungen, nicht an dem, was im Browser stand. Käme in der
        # Zwischenzeit eine weitere Teilrechnung dazu, wäre der Abzug aus dem
        # Formular veraltet — und niemand würde es merken.
        if (pos_data.pos_type or "item") == positionen_service.ANZAHLUNGSABZUG:
            continue
        pos = InvoicePosition(invoice_id=inv.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    if inv.billing_stage == "schluss" and inv.chain_id:
        # Erst auffrischen: Die Positionen wurden per Massenlöschung ersetzt,
        # die Beziehung am Beleg zeigt sonst noch den alten Stand — und die
        # Abzugszeile bekäme eine Sortierung, die schon vergeben ist.
        db.refresh(inv)
        anzahlung_service.zeilen_anhaengen(
            db, inv,
            anzahlung_service.abzugsfaehige_belege(db, inv.chain_id, ausser_id=inv.id))
        db.flush()

    _verwaiste_bilder_entfernen(db, alte_bilder)
    db.refresh(inv)
    _calc_totals(inv)
    # Zeiteinträge bleiben am Entwurf bewusst unangetastet — sie werden erst
    # beim Finalisieren auf 'abgerechnet' gezogen (_sync_time_entry_status).
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    # Nur Entwürfe. Ein stornierter Beleg wurde ausgestellt und unterliegt der
    # Aufbewahrungspflicht (§ 132 BAO) — er bleibt erhalten. Entwürfe haben
    # keine Nummer, ihr Löschen reißt daher auch keine Lücke mehr.
    if inv.status != "entwurf":
        raise HTTPException(
            400,
            "Nur Entwürfe können gelöscht werden. Ausgestellte Belege — auch "
            "stornierte — unterliegen der Aufbewahrungspflicht.",
        )
    # Bilder der Positionen mitnehmen, sonst bleiben sie im Speicher zurück.
    bilder = {p.image_key: p.image_provider for p in inv.positions if p.image_key}
    db.delete(inv)
    db.flush()
    _verwaiste_bilder_entfernen(db, bilder)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Aktionen
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: UUID,
    body: InvoiceCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
        year = datetime.now().year
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
            date=datetime.now().date(),
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
async def mark_paid(
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
async def set_status(
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
async def convert_to_ab(
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
        title=offer.title, date=datetime.now().date(),
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
async def convert_to_invoice(
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
        date=datetime.now().date(),
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
async def get_chain(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    __=Depends(require_module("verkauf")),
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
async def create_advance(
    invoice_id: UUID,
    body: AnzahlungRequest,
    trotz_ablauf: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_module("verkauf")),
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

    belegdatum = body.date or datetime.now().date()
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
async def create_final_invoice(
    invoice_id: UUID,
    body: SchlussrechnungRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_module("verkauf")),
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

    belegdatum = body.date or datetime.now().date()
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
async def duplicate_invoice(
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
        date=datetime.now().date(),
        # Leistungsdatum NICHT übernehmen: Das Duplikat betrifft eine neue
        # Leistung; ein mitkopiertes altes Datum wäre schlicht falsch.
        delivery_date=datetime.now().date(),
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


# ─────────────────────────────────────────────────────────────────────────────
# Vertrag zu wiederkehrender Rechnung (Nachweis/Referenz zur Serie)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/contract", response_model=InvoiceAttachmentResponse)
async def upload_contract(
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

    data = await file.read()
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
        raise HTTPException(500, f"Speicher-Fehler: {exc}")

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
async def download_contract(
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
                    headers={"Content-Disposition": f'inline; filename="{att.filename or "vertrag"}"'})


@router.delete("/contract/{attachment_id}", status_code=204)
async def delete_contract(
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
# ─────────────────────────────────────────────────────────────────────────────

DOC_TYPE_LABELS_DE = {
    "rechnung":             "Rechnung",
    "angebot":              "Angebot",
    "auftragsbestaetigung": "Auftragsbestätigung",
    "gutschrift":           "Gutschrift",
    "lieferschein":         "Lieferschein",
}



def _load_pdf_context(db: Session, invoice: Invoice):
    """Lädt Settings, InvoiceSettings, Sender- und Empfängerkontakt."""
    settings = {r.key: r.value for r in db.query(Setting).all()}
    inv_settings = {r.key: r.value for r in db.query(InvoiceSettings).all()}

    sender_contact = None
    cid = settings.get("company_contact_id")
    if cid:
        try:
            from uuid import UUID as _UUID
            sender_contact = db.query(EntityRecord).filter(EntityRecord.id == _UUID(cid)).first()
        except Exception:
            pass

    # Empfänger: finalisierte Belege rendern aus dem eingefrorenen Snapshot
    # (Belegaufbewahrung / DSGVO) — nur Entwürfe lesen live aus den Stammdaten.
    recipient_contact = snapshot_as_contact(invoice.recipient_snapshot)
    if recipient_contact is None and invoice.contact_id:
        recipient_contact = db.query(EntityRecord).filter(EntityRecord.id == invoice.contact_id).first()

    return settings, inv_settings, sender_contact, recipient_contact


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
async def send_invoice_email(
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
        raise HTTPException(500, f"E-Mail konnte nicht gesendet werden: {str(e)}")

    return {"ok": True, "to": to_email, "number": inv.number}


@router.post("/bulk-send-email")
async def bulk_send_email(
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


# ─────────────────────────────────────────────────────────────────────────────
# Zeiteinträge für Rechnung vorschlagen
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/email-templates/{doc_type}")
async def get_email_template(
    doc_type: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Lädt die E-Mail-Vorlage für eine Belegart."""
    tmpl = db.query(EmailTemplate).filter(EmailTemplate.doc_type == doc_type).first()
    if not tmpl:
        return {"doc_type": doc_type, "subject": "", "body_html": ""}
    return {"doc_type": tmpl.doc_type, "subject": tmpl.subject, "body_html": tmpl.body_html}


@router.put("/email-templates/{doc_type}")
async def update_email_template(
    doc_type: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Speichert die E-Mail-Vorlage für eine Belegart."""
    tmpl = db.query(EmailTemplate).filter(EmailTemplate.doc_type == doc_type).first()
    if not tmpl:
        tmpl = EmailTemplate(doc_type=doc_type)
        db.add(tmpl)
    tmpl.subject   = body.get("subject", "")
    tmpl.body_html = body.get("body_html", "")
    db.commit()
    return {"ok": True}


@router.get("/time-entries/unbilled")
async def get_unbilled_time_entries(
    contact_id: Optional[UUID] = Query(None),
    project_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Gibt die verrechenbaren, noch nicht fakturierten Zeiteinträge zurück.

    Ein Eintrag erscheint hier, wenn er
      * abgeschlossen ist (``ended_at`` gesetzt — laufende Timer zählen nicht),
      * als verrechenbar markiert ist (``billable``),
      * den Status ``freigegeben`` hat (erst nach der Freigabe darf fakturiert
        werden — siehe Abrechnungs-Workflow in ``models/zeiterfassung.py``) und
      * auf keinem gültigen Beleg liegt.

    Positionen **stornierter** Belege zählen dabei nicht: Wird eine Rechnung
    storniert, sollen die darauf abgerechneten Stunden wieder fakturierbar sein.
    """
    from app.models.zeiterfassung import TimeEntry

    # Zeiteinträge, die bereits auf einem gültigen (nicht stornierten) Beleg liegen
    billed_subq = (
        db.query(InvoicePosition.time_entry_id)
        .join(Invoice, Invoice.id == InvoicePosition.invoice_id)
        .filter(InvoicePosition.time_entry_id.isnot(None),
                Invoice.status != "storniert")
    )

    q = db.query(TimeEntry).filter(
        TimeEntry.ended_at.isnot(None),
        TimeEntry.billable.is_(True),
        TimeEntry.status == "freigegeben",
        TimeEntry.id.notin_(billed_subq),
    )

    # Kontakt-/Projektfilter mit Namens-Rückfall:
    # Nicht jeder Zeiteintrag trägt eine contact_id/project_id — Einträge aus
    # „KI nachtragen" und älterer Erfassung haben nur den Namen. Ohne diesen
    # Rückfall verschwinden sie aus dem Übernahme-Dialog, sobald am Beleg ein
    # Kontakt gewählt ist. Verglichen wird der Anzeigename exakt (aber ohne
    # Rücksicht auf Groß-/Kleinschreibung), damit „Muster GmbH“ nicht auch
    # „Mustermann GmbH“ einsammelt.
    def _mit_namensrueckfall(query, ziel_id, id_spalte, name_spalte):
        rec = db.query(EntityRecord).filter(EntityRecord.id == ziel_id).first()
        name = (rec.display_name or "").strip() if rec else ""
        bedingungen = [id_spalte == ziel_id]
        if name:
            bedingungen.append(and_(id_spalte.is_(None), name_spalte.ilike(name)))
        return query.filter(or_(*bedingungen))

    if contact_id:
        q = _mit_namensrueckfall(q, contact_id, TimeEntry.contact_id, TimeEntry.contact_name)
    if project_id:
        q = _mit_namensrueckfall(q, project_id, TimeEntry.project_id, TimeEntry.project_name)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            TimeEntry.note.ilike(like),
            TimeEntry.contact_name.ilike(like),
            TimeEntry.project_name.ilike(like),
            TimeEntry.task_title.ilike(like),
        ))

    entries = q.order_by(TimeEntry.started_at.desc()).limit(limit).all()

    result = []
    for e in entries:
        minuten = e.duration_minutes or 0
        result.append({
            "id":               str(e.id),
            "started_at":       e.started_at.isoformat() if e.started_at else None,
            "ended_at":         e.ended_at.isoformat() if e.ended_at else None,
            "duration_minutes": minuten,
            "duration_hours":   round(minuten / 60, 2),
            "description":      e.note or e.task_title or "Zeitaufwand",
            "note":             e.note or "",
            # Das Frontend liest `contact`/`project`; die *_name-Schlüssel
            # bleiben für ältere Aufrufer zusätzlich erhalten.
            "contact":          e.contact_name or "",
            "project":          e.project_name or "",
            "contact_name":     e.contact_name or "",
            "project_name":     e.project_name or "",
            "contact_id":       str(e.contact_id) if e.contact_id else None,
            "project_id":       str(e.project_id) if e.project_id else None,
            "billable":         e.billable,
        })
    return result
