"""
Angebotsgültigkeit (A-17h).

Ein Angebot ohne Bindefrist bindet einen unbefristet an Preise, die vor Monaten
kalkuliert wurden. Die Frist steht deshalb auf dem Beleg und wird in der Liste
ausgewiesen.

**Was hier bewusst NICHT passiert: das Angebot automatisch abzulehnen.**
Abgelaufen und abgelehnt sind zwei verschiedene Dinge — der Kunde meldet sich
oft nach Fristende doch noch. Ein Hintergrundlauf, der stumpf auf ``abgelehnt``
setzt, macht die Zahlen im Bericht ordentlich und die Angebotsverfolgung
wertlos. Der Ablauf wird darum aus dem Datum abgeleitet und angezeigt; wer nach
Fristende umwandelt, wird gefragt, nicht gehindert.
"""
from datetime import date, timedelta
from app.core import zeit

# Schlüssel in den Verkaufseinstellungen; Wert = Tage ab Belegdatum
VORGABE_KEY = "default_offer_valid_days"
VORGABE_TAGE = 30


def vorgabe_tage(db) -> int:
    """Wie viele Tage ein neues Angebot vorbelegt gültig ist."""
    from app.models.invoice import InvoiceSettings
    row = db.query(InvoiceSettings).filter_by(key=VORGABE_KEY).first()
    if row is None or row.value in (None, ""):
        return VORGABE_TAGE
    try:
        tage = int(row.value)
    except (TypeError, ValueError):
        return VORGABE_TAGE
    # Null oder negativ heißt „keine Vorbelegung" — dann bleibt das Feld leer,
    # statt ein Datum in der Vergangenheit zu erfinden.
    return tage if tage > 0 else 0


def vorbelegen(db, doc_type: str, belegdatum: date):
    """
    Gültigkeitsdatum für einen neuen Beleg — oder ``None``.

    Nur für Angebote: Eine Rechnung hat ein Zahlungsziel, keine Bindefrist.
    """
    if doc_type != "angebot" or not belegdatum:
        return None
    tage = vorgabe_tage(db)
    return belegdatum + timedelta(days=tage) if tage else None


def ist_abgelaufen(invoice, stichtag: date = None) -> bool:
    """
    Ist die Bindefrist überschritten?

    Nur Angebote laufen ab, und nur solche, die noch offen sind: Ein
    angenommenes Angebot ist erledigt, ein abgelehntes auch — beide nachträglich
    als „abgelaufen" auszuweisen wäre bloß Lärm.
    """
    if invoice.doc_type != "angebot" or not invoice.valid_until:
        return False
    if invoice.status in ("angenommen", "abgelehnt", "storniert", "entwurf"):
        return False
    return invoice.valid_until < (stichtag or zeit.heute())


def resttage(invoice, stichtag: date = None):
    """Tage bis zum Fristende; negativ, wenn vorbei. ``None`` ohne Frist."""
    if invoice.doc_type != "angebot" or not invoice.valid_until:
        return None
    return (invoice.valid_until - (stichtag or zeit.heute())).days
