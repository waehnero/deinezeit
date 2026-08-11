"""
Mengeneinheiten nach UN/ECE Recommendation 20.

In DeineZeit ist die Einheit einer Position Freitext („Stk", „h", „m²"). Für
eine E-Rechnung verlangt EN 16931 einen Code aus einer festen Liste: ``C62``
für Stück, ``HUR`` für Stunde, ``MTK`` für Quadratmeter.

**Unbekanntes wird gemeldet, nicht geraten.** Die Versuchung wäre, bei einer
unbekannten Einheit einfach ``C62`` („Stück") zu setzen — die Datei wäre dann
formal gültig und inhaltlich falsch. Eine Rechnung über „12 Stück" statt „12
Stunden" fällt niemandem auf, bis jemand sie prüft. Deshalb: kein Rückfall,
sondern ein Hinweis, den der Anwender auflöst.

Die Liste deckt ab, was im Handwerk und in der Dienstleistung vorkommt. Sie
darf wachsen; die Codes stammen aus UN/ECE Rec 20 und sind nicht frei
wählbar.
"""

# Schreibweise (klein, ohne Leerzeichen) → UN/ECE-Rec-20-Code
ZUORDNUNG = {
    # Stück und Anzahl
    "stk": "C62", "stk.": "C62", "stück": "C62", "stueck": "C62",
    "st": "C62", "st.": "C62", "x": "C62", "ea": "C62", "pcs": "C62",
    "c62": "C62",
    "psch": "C62", "pausch": "C62", "pauschal": "C62", "pauschale": "C62",

    # Zeit
    "h": "HUR", "std": "HUR", "std.": "HUR", "stunde": "HUR",
    "stunden": "HUR", "hr": "HUR", "hur": "HUR",
    "min": "MIN", "minute": "MIN", "minuten": "MIN",
    "tag": "DAY", "tage": "DAY", "t": "DAY", "d": "DAY", "day": "DAY",
    "woche": "WEE", "wochen": "WEE",
    "monat": "MON", "monate": "MON",
    "jahr": "ANN", "jahre": "ANN",

    # Länge
    "m": "MTR", "meter": "MTR", "lfm": "MTR", "lm": "MTR", "laufmeter": "MTR",
    "mm": "MMT", "cm": "CMT", "km": "KMT",

    # Fläche und Volumen
    "m2": "MTK", "m²": "MTK", "qm": "MTK", "quadratmeter": "MTK",
    "m3": "MTQ", "m³": "MTQ", "cbm": "MTQ", "kubikmeter": "MTQ",
    "l": "LTR", "liter": "LTR", "ml": "MLT",

    # Gewicht
    "kg": "KGM", "kilogramm": "KGM",
    "g": "GRM", "gramm": "GRM",
    "t_gewicht": "TNE", "tonne": "TNE", "tonnen": "TNE",

    # Gebinde
    "pkg": "XPK", "packung": "XPK", "paket": "XPK",
    "set": "SET", "satz": "SET",
    "rolle": "NRL", "rollen": "NRL",
    "palette": "XPX", "paletten": "XPX",

    # Sonstiges
    "%": "P1", "prozent": "P1",
    "kwh": "KWH",
}

# Einheit für eine Position ohne Angabe. „Stück" ist hier keine Annahme über
# den Inhalt, sondern die vorgesehene Bedeutung von „keine Einheit" — EN 16931
# verlangt zwingend einen Code.
VORGABE = "C62"


def code(einheit: str) -> str:
    """
    Gibt den Normcode zurück oder ``None``, wenn die Einheit unbekannt ist.

    Leer heißt „ohne Einheit" und ergibt die Vorgabe. Eine gefüllte, aber
    unbekannte Einheit ergibt ``None`` — der Aufrufer muss das melden.
    """
    if einheit is None:
        return VORGABE
    schluessel = str(einheit).strip().lower()
    if not schluessel:
        return VORGABE
    return ZUORDNUNG.get(schluessel)


def unbekannte(einheiten) -> list:
    """Die unbekannten Einheiten einer Sammlung, ohne Wiederholungen."""
    offen = []
    for e in einheiten:
        if code(e) is None and str(e).strip() not in offen:
            offen.append(str(e).strip())
    return offen
