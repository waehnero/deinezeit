"""
Verkauf – gemeinsame Hilfsfunktionen (Nummernkreis, Summen, Zahlstand,
Pflichtangaben, Finalisierung, Belegsperre, PDF-Kontext).

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
import logging
import re

from app.models.invoice import (Invoice, InvoicePosition, InvoiceNumberSequence, InvoiceSettings,
                                 InvoiceAuditLog)
from app.models.settings import Setting
from app.models.masterdata import EntityRecord
from app.services.invoice_snapshot import (ensure_recipient_snapshot,
                                           snapshot_as_contact)
from app.services import anzahlung as anzahlung_service
from app.core import zeit

logger = logging.getLogger(__name__)

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

# Erlaubte Platzhalter im Nummernformat. Der Formatstring kommt aus den
# Einstellungen (nur Administrator), aber ``str.format`` erlaubt darüber auch
# Attributzugriffe wie ``{seq.__class__}`` — ein Nummernformat soll genau zwei
# Dinge einsetzen können und sonst nichts.
_FORMAT_PLATZHALTER = re.compile(r"\{(year|seq)(:[^{}]*)?\}")


def nummernformat_pruefen(fmt: str) -> str:
    """Gibt das Format zurück oder wirft 400, wenn es mehr kann als Jahr und Zähler."""
    rest = _FORMAT_PLATZHALTER.sub("", fmt or "")
    if "{" in rest or "}" in rest:
        raise HTTPException(
            400, "Ungültiges Nummernformat: erlaubt sind nur die Platzhalter "
                 "{year} und {seq} (z. B. RE-{year}-{seq:03d}).")
    return fmt


def _nummernformat(db: Session, doc_type: str) -> str:
    setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
    if setting and setting.value:
        return setting.value.strip('"') if isinstance(setting.value, str) else str(setting.value)
    return f"{TYPE_PREFIX.get(doc_type, 'DO')}-{{year}}-{{seq:03d}}"


def _next_number(db: Session, doc_type: str, year: int) -> tuple[int, str]:
    """Atomarer Zähler — gibt (sequence, formatted_number) zurück.

    Die Zählerzeile wird mit ``FOR UPDATE`` gesperrt (wie beim Artikelstamm,
    services/artikelstamm.py). Ohne die Sperre lesen zwei gleichzeitige
    Belegerstellungen denselben Stand und die zweite scheitert an
    ``invoices.number UNIQUE`` mit einem nackten 500 — oder, ohne diese
    Prüfung, entstünden doppelte Belegnummern (Audit DATA-005). Solange die
    Zeile noch nicht existiert (erster Beleg eines Jahres), fängt ein Unique-
    Verstoß beim Anlegen den Wettlauf ab und es wird erneut gelesen.
    """
    from sqlalchemy.exc import IntegrityError

    seq = (db.query(InvoiceNumberSequence)
             .filter_by(doc_type=doc_type, year=year)
             .with_for_update()
             .first())
    if not seq:
        try:
            with db.begin_nested():
                db.add(InvoiceNumberSequence(doc_type=doc_type, year=year, last_sequence=0))
        except IntegrityError:
            pass    # ein anderer war schneller — dessen Zeile jetzt gesperrt lesen
        seq = (db.query(InvoiceNumberSequence)
                 .filter_by(doc_type=doc_type, year=year)
                 .with_for_update()
                 .one())
    seq.last_sequence += 1
    db.flush()

    number = nummernformat_pruefen(_nummernformat(db, doc_type)).format(
        year=year, seq=seq.last_sequence)
    return seq.last_sequence, number


from app.services.positionen import (WERTZEILEN, gruppen_netto as _gruppen_netto,
                                      rabatt_verteilen as _rabatt_verteilen,
                                      rabattbetrag as _rabattbetrag)


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
    jahr = (invoice.date or zeit.jetzt().date()).year
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
    return invoice.due_date < (stichtag or zeit.heute())


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
