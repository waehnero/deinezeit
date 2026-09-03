"""
Wiederkehrende Rechnungen – Hintergrund-Automatik.

Eine wiederkehrende Rechnung ist eine Vorlage (Invoice mit
``is_recurring_template = True``). Sie wird nicht selbst versendet, sondern
erzeugt gemäß Intervall automatisch **Entwürfe** (neue Rechnungen mit
``recurring_source_id`` = Vorlage). Die Automatik läuft – wie der Mail-Scanner –
in einem eigenen Daemon-Thread (in Tests deaktiviert).

Ablauf je Vorlage:
  * ``recurring_next`` = nächstes Fälligkeitsdatum.
  * Ist es <= heute (und <= ``recurring_end``), wird ein Entwurf angelegt und
    ``recurring_next`` um das Intervall weitergesetzt (Nachhol-Logik in einer
    Schleife, falls mehrere Termine überfällig sind).
  * Ist ``recurring_end`` überschritten, stoppt die Serie (``recurring_next`` = None).
"""

import os
import time
import threading
from datetime import date, datetime, timezone, timedelta
from app.core import zeit


def _add_months(d: date, months: int) -> date:
    """Addiert Monate und respektiert Monatsenden (z.B. 31.01 + 1M = 28./29.02)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # letzter gültiger Tag des Zielmonats
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


def advance(d: date, interval: str) -> date:
    """Berechnet das nächste Fälligkeitsdatum gemäß Intervall."""
    if interval == "weekly":
        return d + timedelta(weeks=1)
    if interval == "quarterly":
        return _add_months(d, 3)
    if interval == "yearly":
        return _add_months(d, 12)
    # default: monatlich
    return _add_months(d, 1)


def _create_child(db, tpl, doc_date: date):
    """Legt einen Rechnungs-Entwurf aus der Vorlage an (Positionen inklusive)."""
    from app.models.invoice import Invoice, InvoicePosition
    from app.api.invoice import _calc_totals

    # Der erzeugte Beleg ist ein Entwurf und bleibt nummernlos, bis er
    # finalisiert wird. Andernfalls würde jede nicht verschickte Serienrechnung
    # eine Nummer verbrauchen und eine Lücke im Nummernkreis hinterlassen.
    child = Invoice(
        doc_type="rechnung",
        contact_id=tpl.contact_id, project_id=tpl.project_id,
        title=tpl.title, date=doc_date,
        reference=tpl.reference,
        # Leistungsdatum: der Termin dieser Serienrechnung. Die Vorlage trägt
        # ein altes Datum, das hier nichts zu suchen hat — das Leistungsdatum
        # ist Pflichtangabe und muss zum erzeugten Beleg passen.
        delivery_date=doc_date,
        intro_text=tpl.intro_text, outro_text=tpl.outro_text, notes=tpl.notes,
        tax_mode=tpl.tax_mode, currency=tpl.currency, template_id=tpl.template_id,
        status="entwurf",
        recurring_source_id=tpl.id,
        created_by="system:wiederkehrend", updated_by="system:wiederkehrend",
    )
    db.add(child)
    db.flush()

    for p in tpl.positions:
        db.add(InvoicePosition(
            invoice_id=child.id, sort_order=p.sort_order,
            pos_type=p.pos_type, description=p.description, detail=p.detail,
            quantity=p.quantity, unit=p.unit, unit_price=p.unit_price,
            discount_pct=p.discount_pct, tax_rate=p.tax_rate,
            article_id=p.article_id,
        ))

    db.flush()
    db.refresh(child)
    _calc_totals(child)
    return child


def _erinnerung_anlegen(db, tpl, termin: date) -> None:
    """
    Legt statt eines Belegs eine Aufgabe an (Modus ``remind``).

    Bewusst eine Aufgabe und keine E-Mail: In den Aufgaben schaut man ohnehin
    täglich, eine Mail geht im Posteingang zwischen allem anderen unter. Die
    Aufgabe verweist über ``record_id`` auf den Kunden, damit der Weg von der
    Erinnerung zum Beleg kurz bleibt.
    """
    from app.models.aufgaben import Todo
    from app.models.masterdata import EntityRecord

    kunde = None
    if tpl.contact_id:
        rec = db.query(EntityRecord).filter(EntityRecord.id == tpl.contact_id).first()
        kunde = rec.display_name if rec else None

    bezeichnung = tpl.title or "Wiederkehrende Rechnung"
    db.add(Todo(
        title=f"Rechnung fällig: {bezeichnung}" + (f" ({kunde})" if kunde else ""),
        description=(
            f"Die wiederkehrende Vorlage „{bezeichnung}“ ist zum "
            f"{termin:%d.%m.%Y} fällig.\n\n"
            f"Eingestellt ist „nur erinnern“ — es wurde absichtlich kein Beleg "
            f"erzeugt. Bitte prüfen und die Rechnung von Hand anlegen."
        ),
        status="offen", priority="mittel", due_date=termin,
        record_id=tpl.contact_id, record_name=kunde,
        record_type_slug="kontakte" if tpl.contact_id else None,
        source="wiederkehrend",
        source_meta={"vorlage_id": str(tpl.id), "termin": termin.isoformat()},
        created_by_name="System (wiederkehrend)",
    ))


def _versenden(db, beleg) -> tuple:
    """
    Stellt den Beleg aus und verschickt ihn (Modus ``create_and_send``).

    Gibt ``(erfolg, meldung)`` zurück. **Scheitert der Versand, bleibt der
    Beleg ausgestellt stehen** — er hat dann bereits eine Nummer, und die
    zurückzunehmen hieße, eine Lücke in den Nummernkreis zu reißen. Statt
    dessen wird der Fehlschlag im Änderungsprotokoll vermerkt; der Beleg ist
    danach von Hand zu versenden.
    """
    from app.api.invoice import _load_pdf_context, _send_invoice_email, _audit

    empfaenger = ""
    settings_d, inv_settings_d, sender_contact, recipient_contact = \
        _load_pdf_context(db, beleg)
    if recipient_contact is not None:
        empfaenger = (recipient_contact.data or {}).get("email", "") or ""
    if not empfaenger:
        _audit(db, beleg, "hinweis",
               note="Automatischer Versand nicht möglich: Der Kunde hat keine "
                    "E-Mail-Adresse. Der Beleg ist ausgestellt und wartet auf "
                    "den Versand von Hand.",
               user_email="system:wiederkehrend")
        return False, "keine E-Mail-Adresse hinterlegt"

    try:
        _send_invoice_email(beleg, db, settings_d, inv_settings_d,
                            sender_contact, recipient_contact, empfaenger,
                            "system:wiederkehrend")
        return True, empfaenger
    except Exception as e:
        # Der Beleg bleibt ausgestellt — siehe Docstring.
        _audit(db, beleg, "hinweis",
               note=f"Automatischer Versand fehlgeschlagen: {e}. Der Beleg ist "
                    f"ausgestellt und wartet auf den Versand von Hand.",
               user_email="system:wiederkehrend")
        print(f"[WARN] Wiederkehrend: Versand von {beleg.number} fehlgeschlagen: {e}")
        return False, str(e)


def _abarbeiten(db, tpl, termin: date) -> str:
    """
    Führt für einen fälligen Termin aus, was die Vorlage vorsieht.

    Gibt zurück, was passiert ist: ``erinnert``, ``entwurf`` oder ``versendet``.
    ``create`` bleibt der Vorgabewert — die beiden anderen Modi standen zwar
    seit jeher im Modell, wurden aber nie ausgewertet, sodass jede Vorlage
    stillschweigend Entwürfe erzeugte.
    """
    from app.api.invoice import _finalize, _audit, _audit_changes
    from app.services.invoice_archive import archive_invoice_pdf

    modus = tpl.recurring_action or "create"

    if modus == "remind":
        _erinnerung_anlegen(db, tpl, termin)
        return "erinnert"

    kind = _create_child(db, tpl, termin)

    if modus == "create_and_send":
        # Reihenfolge wie im set-status-Endpunkt: erst den Status setzen,
        # dann finalisieren — dabei fällt die Belegnummer, der Empfänger wird
        # eingefroren und die Zeiteinträge gelten als abgerechnet.
        alter_status = kind.status
        kind.status = "gesendet"
        neue_nummer = _finalize(db, kind)
        _audit(db, kind, "finalisiert" if neue_nummer else "status",
               changes=_audit_changes(alter_status, kind, neue_nummer),
               note="Automatisch aus wiederkehrender Vorlage ausgestellt",
               user_email="system:wiederkehrend")
        db.flush()
        archive_invoice_pdf(db, kind, "gesendet")
        erfolg, _meldung = _versenden(db, kind)
        return "versendet" if erfolg else "entwurf"

    return "entwurf"


def materialize_due_recurring(db, today: date = None) -> int:
    """
    Arbeitet alle fälligen Vorlagen ab. Gibt die Anzahl der erledigten Termine
    zurück. Idempotent bezogen auf ``recurring_next`` (jeder Termin wird genau
    einmal abgearbeitet, weil das Datum danach weitergesetzt wird).

    Was je Termin geschieht, hängt an ``recurring_action``:
    erinnern, Entwurf anlegen oder anlegen und versenden.
    """
    from app.models.invoice import Invoice

    if today is None:
        today = zeit.heute()

    templates = (db.query(Invoice)
                 .filter(Invoice.is_recurring_template.is_(True),
                         Invoice.recurring_next.isnot(None),
                         Invoice.recurring_next <= today)
                 .all())

    created = 0
    for tpl in templates:
        interval = tpl.recurring_interval or "monthly"
        # Nachhol-Schleife für mehrere überfällige Termine
        while tpl.recurring_next and tpl.recurring_next <= today:
            if tpl.recurring_end and tpl.recurring_next > tpl.recurring_end:
                tpl.recurring_next = None
                break
            _abarbeiten(db, tpl, tpl.recurring_next)
            created += 1
            nxt = advance(tpl.recurring_next, interval)
            if tpl.recurring_end and nxt > tpl.recurring_end:
                tpl.recurring_next = None
                break
            tpl.recurring_next = nxt
        db.flush()

    if created:
        db.commit()
    return created


# ── Hintergrund-Worker ────────────────────────────────────────────────────────
_worker_started = False


def _worker_loop():
    from app.db.base import SessionLocal
    last_run_day = None
    # Kurz nach dem Start einmal laufen, danach stündlich aufwachen. Vorher
    # verging bis zur ersten Prüfung eine volle Stunde — fällige Serienbelege
    # entstanden nach einem Neustart entsprechend spät.
    time.sleep(60)
    while True:
        try:
            heute = zeit.heute()
            # Bewusst kein "continue": Das würde das Warten am Schleifenende
            # überspringen und den Thread heißlaufen lassen.
            if last_run_day != heute:
                db = SessionLocal()
                try:
                    n = materialize_due_recurring(db, heute)
                    if n:
                        print(f"[INFO] Wiederkehrend: {n} Rechnungs-Entwurf/-Entwürfe erstellt")
                    last_run_day = heute
                finally:
                    db.close()
        except Exception as e:
            print(f"[WARN] Wiederkehrend-Worker: {e}")
        time.sleep(3600)  # stündlich aufwachen


def start_recurring_worker():
    """Startet den Wiederkehr-Thread (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_RECURRING_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="recurring-invoices").start()
