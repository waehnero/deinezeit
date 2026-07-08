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
    from app.api.invoice import _next_number, _calc_totals

    year = doc_date.year
    sequence, number = _next_number(db, "rechnung", year)

    child = Invoice(
        doc_type="rechnung",
        number=number, year=year, sequence=sequence,
        contact_id=tpl.contact_id, project_id=tpl.project_id,
        title=tpl.title, date=doc_date,
        reference=tpl.reference,
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


def materialize_due_recurring(db, today: date = None) -> int:
    """
    Erzeugt für alle fälligen Vorlagen die Entwürfe. Gibt die Anzahl erzeugter
    Belege zurück. Idempotent bezogen auf ``recurring_next`` (jeder Termin wird
    genau einmal erzeugt, weil das Datum danach weitergesetzt wird).
    """
    from app.models.invoice import Invoice

    if today is None:
        today = date.today()

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
            _create_child(db, tpl, tpl.recurring_next)
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
    # Erststart kurz verzögern, dann täglich prüfen (Schleife wacht stündlich auf)
    last_run_day = None
    while True:
        time.sleep(3600)  # stündlich aufwachen
        try:
            heute = date.today()
            if last_run_day == heute:
                continue
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


def start_recurring_worker():
    """Startet den Wiederkehr-Thread (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_RECURRING_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="recurring-invoices").start()
