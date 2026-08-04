"""
Skonto (C-9) — Entgeltminderung mit Umsatzsteuer-Berichtigung.

Zahlt der Kunde binnen Frist gekürzt, ist die Differenz **kein Zahlungsausfall
und kein Erlösverzicht ohne Folgen**, sondern eine Minderung des Entgelts. Die
Umsatzsteuer ist nach § 16 UStG zu berichtigen — und zwar in dem
Voranmeldungszeitraum, in dem die Änderung eingetreten ist, also **im Monat der
Zahlung**, nicht im Monat der Rechnung.

Daraus folgen zwei Dinge, die das ganze Modul prägen:

1. Der Skonto wird als Eintrag in ``invoice_payments`` mit
   ``payment_type='skonto'`` und dem **Zahlungsdatum** geführt. So schließt er
   den Beleg wie eine Zahlung, bleibt aber unterscheidbar.

2. Die Aufteilung auf die Steuersätze läuft über dieselbe Regel wie ein
   Positionsrabatt (``positionen.rabatt_verteilen``). Bei gemischten Sätzen auf
   einem Beleg wäre alles andere falsch: Der Skonto mindert jeden Satz
   anteilig, nicht den höchsten zuerst.

Nicht abgebildet ist der Fall, dass ein abgeschlossener Monat betroffen wäre —
das kann nicht passieren, weil die Buchung am Zahlungsdatum hängt und ein
abgeschlossener Monat keine neuen Zahlungen mehr annimmt.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.services import positionen as positionen_service

CENT = Decimal("0.01")


def _dec(wert, vorgabe="0") -> Decimal:
    try:
        return Decimal(str(wert if wert is not None else vorgabe))
    except Exception:
        return Decimal(vorgabe)


def vereinbart(invoice) -> bool:
    """Hat der Beleg überhaupt eine Skonto-Bedingung?"""
    return bool(invoice.skonto_percent and Decimal(str(invoice.skonto_percent)) > 0)


def frist_ende(invoice):
    """
    Letzter Tag der Skontofrist. Gerechnet ab **Rechnungsdatum**, nicht ab
    Fälligkeit — so steht es in der Zahlungsbedingung („10 Tage 2 % Skonto,
    30 Tage netto").
    """
    if not vereinbart(invoice) or invoice.skonto_days is None or not invoice.date:
        return None
    return invoice.date + timedelta(days=int(invoice.skonto_days))


def in_frist(invoice, zahldatum: date) -> bool:
    ende = frist_ende(invoice)
    return bool(ende and zahldatum and zahldatum <= ende)


def betrag(invoice) -> Decimal:
    """
    Skontobetrag laut Vereinbarung: Prozentsatz vom **Bruttobetrag** des Belegs.

    Das ist die im deutschsprachigen Raum übliche Lesart der Klausel. Wer vom
    Netto rechnen will, trägt einen entsprechend angepassten Prozentsatz ein.
    """
    if not vereinbart(invoice):
        return Decimal("0.00")
    brutto = _dec(invoice.total)
    return (brutto * _dec(invoice.skonto_percent) / Decimal("100")).quantize(
        CENT, rounding=ROUND_HALF_UP)


def brutto_je_satz(invoice) -> dict:
    """
    Bruttobeträge des Belegs je Steuersatz — Verteilungsschlüssel für den Skonto.

    ``None`` als Schlüssel steht für Reverse Charge; dort gibt es keine
    Umsatzsteuer, brutto und netto sind identisch.
    """
    if invoice.tax_mode == "kleinunternehmer":
        # Unecht steuerbefreit: keine Umsatzsteuer, alles hängt an 0 %.
        summe = _dec(invoice.subtotal)
        return {Decimal("0"): summe} if summe else {}

    netto = positionen_service.netto_je_satz(list(invoice.positions), invoice.tax_mode)
    werte = {}
    for satz, wert in netto.items():
        if satz is None:
            werte[None] = wert
        else:
            werte[satz] = (wert * (Decimal("100") + _dec(satz)) / Decimal("100")).quantize(CENT)
    return {s: w for s, w in werte.items() if w}


def aufteilung(invoice, skonto_brutto: Decimal) -> list:
    """
    Zerlegt den Skontobetrag je Steuersatz in Entgeltminderung und
    Steuerberichtigung.

    Ergebnis: Liste aus ``{"satz", "brutto", "netto", "steuer"}``. Die Summe der
    Bruttoanteile entspricht exakt dem übergebenen Betrag — die
    Rundungsdifferenz trägt derselbe Satz wie beim Positionsrabatt.
    """
    skonto_brutto = _dec(skonto_brutto).quantize(CENT)
    if skonto_brutto <= 0:
        return []

    basis_je_satz = brutto_je_satz(invoice)
    basis = sum(basis_je_satz.values(), Decimal("0"))
    if basis <= 0:
        return []

    # Reverse Charge hat den Schlüssel None; rabatt_verteilen sortiert die
    # Schlüssel und käme mit None ins Straucheln. Ersatzschlüssel setzen und
    # danach zurückübersetzen.
    RC = Decimal("-1")
    umgeschluesselt = {(RC if s is None else s): w for s, w in basis_je_satz.items()}

    zeilen = []
    for satz, anteil in positionen_service.rabatt_verteilen(
            umgeschluesselt, basis, skonto_brutto).items():
        if not anteil:
            continue
        echter_satz = None if satz == RC else satz
        teiler = Decimal("100") + (Decimal("0") if echter_satz is None else _dec(echter_satz))
        netto = (anteil * Decimal("100") / teiler).quantize(CENT, rounding=ROUND_HALF_UP)
        zeilen.append({
            "satz": echter_satz,
            "brutto": anteil,
            "netto": netto,
            "steuer": (anteil - netto).quantize(CENT),
        })
    zeilen.sort(key=lambda z: (z["satz"] is None, -(z["satz"] or Decimal("0"))))
    return zeilen


def korrektur_je_satz(db, date_from, date_to) -> dict:
    """
    Entgelt- und Steuerminderungen aus Skonti im Zeitraum, je Steuersatz.

    Maßgeblich ist das **Zahlungsdatum** des Skonto-Eintrags: Die Berichtigung
    gehört in die Voranmeldung des Monats, in dem der Kunde gekürzt gezahlt
    hat — nicht in den Monat der Rechnung, der da längst abgeschlossen sein kann.
    """
    from collections import defaultdict
    from app.models.invoice import Invoice, InvoicePayment

    q = (db.query(InvoicePayment).join(Invoice, Invoice.id == InvoicePayment.invoice_id)
         .filter(InvoicePayment.payment_type == "skonto"))
    if date_from:
        q = q.filter(InvoicePayment.paid_at >= date_from)
    if date_to:
        q = q.filter(InvoicePayment.paid_at <= date_to)

    netto = defaultdict(lambda: Decimal("0"))
    steuer = defaultdict(lambda: Decimal("0"))
    for zahlung in q.all():
        for zeile in aufteilung(zahlung.invoice, zahlung.amount):
            netto[zeile["satz"]] -= zeile["netto"]
            steuer[zeile["satz"]] -= zeile["steuer"]
    return {"netto": dict(netto), "steuer": dict(steuer)}
