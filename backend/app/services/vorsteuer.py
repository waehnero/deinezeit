"""
Vorsteuer und Erwerbsteuer aus Eingangsrechnungen.

Bis hierher enthielt die Umsatzsteuer-Auswertung nur die Umsatzseite und trug
den Vermerk, dass die Vorsteuer vor der Abgabe zu ergänzen sei. Damit war sie
eine Zuarbeit, keine Voranmeldung.

**Der Punkt, an dem es fachlich interessant wird:** Reverse Charge und
innergemeinschaftlicher Erwerb erzeugen *zwei* Einträge, nicht einen. Der
Empfänger schuldet die Steuer (Kennzahl 057 bzw. 070 mit den Satz-Kennzahlen)
und darf sie im selben Zeitraum als Vorsteuer abziehen (066 bzw. 065) — sofern
er zum Abzug berechtigt ist. Wird nur die eine Seite gebucht, steht in der
Voranmeldung eine Steuerschuld ohne Gegenposten.

**Was hier NICHT geraten wird:** Belegt und eingetragen sind 060 (Vorsteuer
Inland), 065 (Vorsteuer aus innergemeinschaftlichem Erwerb), 057 (übergegangene
Steuerschuld) und 070 (Gesamtbetrag der innergemeinschaftlichen Erwerbe). Für
die Vorsteuer aus Reverse Charge und für die Einfuhrumsatzsteuer hängt die
Kennzahl vom Sachverhalt ab; sie bleiben leer, werden als „nicht zugeordnet"
ausgewiesen und sind in den Einstellungen pflegbar — dieselbe Regel wie bei den
Umsatz-Kennzahlen.
"""
from decimal import Decimal

from app.models.purchase import TAX_KIND_LABELS

CENT = Decimal("0.01")

# Schlüssel in den Verkaufseinstellungen (InvoiceSettings)
KENNZAHLEN_KEY = "vorsteuer_kennzahlen"

# Vorgaben. Leerer String = bewusst offen, muss gepflegt werden.
DEFAULT_KENNZAHLEN = {
    "vorsteuer_inland":  "060",   # Vorsteuern (Inland)
    "vorsteuer_ig":      "065",   # Vorsteuern aus innergemeinschaftlichem Erwerb
    "vorsteuer_rc":      "",      # Vorsteuer zur übergegangenen Steuerschuld
    "vorsteuer_einfuhr": "",      # Einfuhrumsatzsteuer
    "steuerschuld_rc":   "057",   # Steuerschuld § 19 (Leistungsempfänger)
    "erwerb_gesamt":     "070",   # Gesamtbetrag der innergemeinschaftlichen Erwerbe
}

BEZEICHNUNGEN = {
    "vorsteuer_inland":  "Vorsteuern (Inland)",
    "vorsteuer_ig":      "Vorsteuer aus innergemeinschaftlichem Erwerb",
    "vorsteuer_rc":      "Vorsteuer zur übergegangenen Steuerschuld",
    "vorsteuer_einfuhr": "Einfuhrumsatzsteuer",
    "steuerschuld_rc":   "Steuerschuld als Leistungsempfänger (Reverse Charge)",
    "erwerb_gesamt":     "Innergemeinschaftliche Erwerbe",
}

# Welche Steuerart welche Kennzahl für die Vorsteuer belegt
VORSTEUER_SCHLUESSEL = {
    "normal":         "vorsteuer_inland",
    "ig_erwerb":      "vorsteuer_ig",
    "reverse_charge": "vorsteuer_rc",
    "einfuhr":        "vorsteuer_einfuhr",
}

# Steuerarten, bei denen der Empfänger die Steuer selbst schuldet
SCHULD_SCHLUESSEL = {
    "reverse_charge": "steuerschuld_rc",
    "ig_erwerb":      "erwerb_gesamt",
}


def get_kennzahlen(db) -> dict:
    """Gepflegte Kennzahlen, ergänzt um die belegten Vorgaben."""
    from app.models.invoice import InvoiceSettings
    werte = dict(DEFAULT_KENNZAHLEN)
    row = db.query(InvoiceSettings).filter_by(key=KENNZAHLEN_KEY).first()
    if row is not None and isinstance(row.value, dict):
        for k, v in row.value.items():
            if k in werte and isinstance(v, str):
                werte[k] = v.strip()
    return werte


def _dec(wert) -> Decimal:
    try:
        return Decimal(str(wert or 0))
    except Exception:
        return Decimal("0")


def belege(db, date_from=None, date_to=None) -> list:
    """
    Eingangsrechnungen des Zeitraums, stornierte ausgenommen.

    Maßgeblich ist das **Rechnungsdatum**, nicht das Erfassungsdatum: Eine im
    August erfasste Julirechnung gehört in die Voranmeldung für Juli.
    """
    from app.models.purchase import PurchaseInvoice
    q = db.query(PurchaseInvoice).filter(PurchaseInvoice.status != "storniert")
    if date_from:
        q = q.filter(PurchaseInvoice.date >= date_from)
    if date_to:
        q = q.filter(PurchaseInvoice.date <= date_to)
    return q.order_by(PurchaseInvoice.date.asc()).all()


def auswertung(db, date_from=None, date_to=None) -> dict:
    """
    Vorsteuer- und Erwerbsteuerzeilen für die Voranmeldung.

    Rückgabe:
      ``zeilen``    Liste aus {schluessel, kennzahl, bezeichnung, betrag,
                    grundlage, art, zugeordnet}
      ``vorsteuer_gesamt``   Summe der abziehbaren Vorsteuer
      ``schuld_gesamt``      Summe der selbst geschuldeten Steuer
      ``hinweise``           Klartext zu allem, was Aufmerksamkeit braucht
    """
    from collections import defaultdict

    kennzahlen = get_kennzahlen(db)
    vorsteuer = defaultdict(lambda: Decimal("0"))
    grundlage = defaultdict(lambda: Decimal("0"))
    schuld = defaultdict(lambda: Decimal("0"))
    schuld_basis = defaultdict(lambda: Decimal("0"))
    nicht_abziehbar = Decimal("0")
    ohne_beleg = 0
    anzahl = 0

    for beleg in belege(db, date_from, date_to):
        anzahl += 1
        if not beleg.file_key:
            ohne_beleg += 1
        art = beleg.tax_kind or "normal"
        netto = sum((_dec(z.net_amount) for z in beleg.taxes), Decimal("0"))
        steuer = sum((_dec(z.tax_amount) for z in beleg.taxes), Decimal("0"))

        # Selbst geschuldete Steuer: Sie entsteht unabhängig davon, ob die
        # Vorsteuer abziehbar ist. Wer nicht abzugsberechtigt ist, schuldet
        # sie trotzdem — das ist der teure Fall, den man sehen muss.
        schluessel_schuld = SCHULD_SCHLUESSEL.get(art)
        if schluessel_schuld:
            schuld[schluessel_schuld] += steuer
            schuld_basis[schluessel_schuld] += netto

        if art == "ohne_vorsteuer" or not beleg.vat_deductible:
            nicht_abziehbar += steuer
            continue

        schluessel_vst = VORSTEUER_SCHLUESSEL.get(art)
        if schluessel_vst:
            vorsteuer[schluessel_vst] += steuer
            grundlage[schluessel_vst] += netto

    zeilen, hinweise = [], []
    offene_kennzahl = False

    def _zeile(schluessel, betrag, basis, art):
        nonlocal offene_kennzahl
        kz = kennzahlen.get(schluessel, "")
        if not kz:
            offene_kennzahl = True
        zeilen.append({
            "schluessel": schluessel, "kennzahl": kz,
            "bezeichnung": BEZEICHNUNGEN.get(schluessel, schluessel),
            "betrag": betrag.quantize(CENT), "grundlage": basis.quantize(CENT),
            "art": art, "zugeordnet": bool(kz),
        })

    for schluessel in ("erwerb_gesamt", "steuerschuld_rc"):
        if schuld[schluessel] or schuld_basis[schluessel]:
            _zeile(schluessel, schuld[schluessel], schuld_basis[schluessel], "steuerschuld")

    for schluessel in ("vorsteuer_inland", "vorsteuer_ig", "vorsteuer_rc", "vorsteuer_einfuhr"):
        if vorsteuer[schluessel]:
            _zeile(schluessel, vorsteuer[schluessel], grundlage[schluessel], "vorsteuer")

    if offene_kennzahl:
        hinweise.append(
            "Für mindestens eine Zeile ist keine UVA-Kennzahl hinterlegt. Sie ist "
            "in den Verkaufseinstellungen unter „Vorsteuer-Kennzahlen“ zu ergänzen — "
            "geraten wird sie bewusst nicht.")
    if nicht_abziehbar:
        hinweise.append(
            f"{float(nicht_abziehbar):.2f} an Steuer ist als nicht abziehbar erfasst "
            f"(§ 12 UStG) und daher NICHT als Vorsteuer enthalten.")
    if ohne_beleg:
        hinweise.append(
            f"{ohne_beleg} von {anzahl} Eingangsrechnungen haben kein hinterlegtes "
            f"Original. Ohne Beleg ist der Vorsteuerabzug im Prüfungsfall gefährdet "
            f"(§ 12 Abs. 1 iVm § 11 UStG).")

    return {
        "zeilen": zeilen,
        "vorsteuer_gesamt": sum(vorsteuer.values(), Decimal("0")).quantize(CENT),
        "schuld_gesamt": sum(schuld.values(), Decimal("0")).quantize(CENT),
        "nicht_abziehbar": nicht_abziehbar.quantize(CENT),
        "beleg_anzahl": anzahl,
        "hinweise": hinweise,
    }


def summen(invoice) -> tuple:
    """Netto-, Steuer- und Bruttosumme aus den Steuerzeilen eines Belegs."""
    netto = sum((_dec(z.net_amount) for z in invoice.taxes), Decimal("0"))
    steuer = sum((_dec(z.tax_amount) for z in invoice.taxes), Decimal("0"))
    # Bei Reverse Charge und innergemeinschaftlichem Erwerb steht auf der
    # Rechnung KEINE Steuer — der Rechnungsbetrag ist der Nettobetrag. Die
    # Steuer schuldet der Empfänger und zahlt sie ans Finanzamt, nicht an den
    # Lieferanten. Sie gehört deshalb nicht in den zu zahlenden Betrag.
    if (invoice.tax_kind or "normal") in ("reverse_charge", "ig_erwerb"):
        return netto.quantize(CENT), steuer.quantize(CENT), netto.quantize(CENT)
    return netto.quantize(CENT), steuer.quantize(CENT), (netto + steuer).quantize(CENT)


def kind_label(kind: str) -> str:
    return TAX_KIND_LABELS.get(kind, kind)
