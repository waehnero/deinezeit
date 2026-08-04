"""
Überfälligkeit — Hintergrund-Automatik.

Der Status ``ueberfaellig`` existierte im Modell von Anfang an, wurde aber
**nirgends gesetzt**: Eine Rechnung blieb nach Ablauf des Zahlungsziels ewig
„offen". Man sah also nicht, welche Forderungen überfällig sind — und ohne
diese Information ist auch kein Mahnwesen möglich.

Der Lauf ist idempotent und läuft täglich mit, wie die Wiederkehr-Automatik.
"""
import os
import time
import threading
from datetime import date


def markiere_ueberfaellige(db, stichtag: date = None) -> int:
    """
    Setzt fällige, noch nicht beglichene Belege auf ``ueberfaellig``.

    Betroffen sind Rechnungen im Status ``offen``, ``gesendet`` oder
    ``teilbezahlt``, deren Zahlungsziel überschritten ist und bei denen noch
    etwas aussteht. Gibt die Anzahl der geänderten Belege zurück.
    """
    from decimal import Decimal
    from app.models.invoice import Invoice, InvoiceAuditLog
    from app.api.invoice import _zahlstand

    heute = stichtag or date.today()

    kandidaten = (db.query(Invoice)
                  .filter(Invoice.doc_type == "rechnung",
                          Invoice.is_recurring_template.is_(False),
                          Invoice.status.in_(["offen", "gesendet", "teilbezahlt"]),
                          Invoice.due_date.isnot(None),
                          Invoice.due_date < heute)
                  .all())

    geaendert = 0
    for beleg in kandidaten:
        _, offen, _ = _zahlstand(beleg)
        if abs(offen) < Decimal("0.01"):
            continue                       # beglichen, nur der Status hinkt
        alter_status = beleg.status
        beleg.status = "ueberfaellig"
        db.add(InvoiceAuditLog(
            invoice_id=beleg.id, action="status",
            changes={"status": {"alt": alter_status, "neu": "ueberfaellig"}},
            note=f"Zahlungsziel am {beleg.due_date:%d.%m.%Y} überschritten, "
                 f"offen {float(offen):.2f} {beleg.currency}",
            changed_by="system:faelligkeit",
        ))
        geaendert += 1

    if geaendert:
        db.commit()
    return geaendert


# ── Hintergrund-Worker ────────────────────────────────────────────────────────
_worker_started = False


def _worker_loop():
    from app.db.base import SessionLocal
    letzter_lauf = None
    # Kurz nach dem Start einmal laufen, danach stündlich aufwachen und täglich
    # arbeiten. Vorher wurde erst nach einer Stunde das erste Mal geprüft — nach
    # einem Neustart am Monatsersten verzögerte sich der Lauf entsprechend.
    time.sleep(60)
    while True:
        try:
            heute = date.today()
            # Bewusst kein "continue": Das würde das Warten am Schleifenende
            # überspringen und den Thread heißlaufen lassen.
            if letzter_lauf != heute:
                db = SessionLocal()
                try:
                    n = markiere_ueberfaellige(db, heute)
                    if n:
                        print(f"[INFO] Fälligkeit: {n} Beleg(e) auf überfällig gesetzt")
                    letzter_lauf = heute
                finally:
                    db.close()
        except Exception as e:
            print(f"[WARN] Fälligkeits-Worker: {e}")
        time.sleep(3600)


def start_overdue_worker():
    """Startet den Fälligkeits-Thread (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_RECURRING_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="overdue-invoices").start()
