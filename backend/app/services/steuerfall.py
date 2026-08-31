"""
Steuerfälle — welcher Sachverhalt liegt einem Umsatz zugrunde.

Bis hierher kannte DeineZeit nur den Steuer*satz*. Das reicht für das Inland,
aber nicht darüber hinaus: Eine innergemeinschaftliche Lieferung, eine Ausfuhr
ins Drittland und ein Reverse-Charge-Umsatz sehen auf dem Beleg alle gleich aus
— kein Steuerbetrag — gehören aber auf verschiedene Erlöskonten und in
verschiedene Zeilen der Voranmeldung.

Woran das bisher scheiterte
---------------------------
Im BMD-Export bestimmte sich das Erlöskonto als ``pos.account_nr or
default_erloes`` und der USt-Code allein aus dem Steuersatz. Die Konten 4040
(steuerbefreit), 4050 (innergemeinschaftlich) und 4060 (Reverse Charge) stehen
zwar seit Migration 0013 im Kontenplan, wurden aber nur bebucht, wenn jemand
sie an *jeder einzelnen Position* von Hand eintrug. Eine IG-Lieferung landete
sonst auf 4000, dem Inlandskonto.

``tax_rates.py`` hält dazu ausdrücklich fest, dass die UVA-Kennzahl für
steuerfreie Umsätze nicht geraten wird, weil sie vom Sachverhalt abhängt.
Dieser Sachverhalt ist der Steuerfall.

Warum eine feste Liste
----------------------
SelectLine lässt beliebige Kunden- und Erlöskontengruppen zu und bildet daraus
eine freie Matrix. Hier ist die Liste absichtlich fest: Die Fälle stehen im
UStG, nicht im Belieben des Anwenders, und jeder zusätzliche Fall bräuchte
ohnehin Code (Kennzahl, Meldelogik). Eine freie Liste würde nur die Illusion
erzeugen, man könne einen fünften Fall durch Anlegen eines Datensatzes
einführen.
"""
from typing import Optional

# Kennung → Anzeigename. Reihenfolge ist die Anzeigereihenfolge.
STEUERFAELLE = [
    ("inland",         "Inland"),
    ("ig_lieferung",   "Innergemeinschaftliche Lieferung"),
    ("drittland",      "Ausfuhr (Drittland)"),
    ("reverse_charge", "Reverse Charge"),
]

KENNUNGEN = [k for k, _ in STEUERFAELLE]
BEZEICHNUNGEN = dict(STEUERFAELLE)

# Der Fall, der gilt, wenn am Kontakt nichts steht. Bewusst das Inland: Das
# ist der Normalfall, und es ist der einzige, bei dem eine falsche Annahme
# nicht zu einer zu Unrecht steuerfrei gestellten Lieferung führt. Wer
# fälschlich Inland bucht, zahlt zu viel Steuer — wer fälschlich steuerfrei
# bucht, schuldet sie nach.
VORGABE = "inland"

# Fälle, in denen der Beleg keine österreichische Umsatzsteuer ausweist. Nur
# hier darf der Steuerfall den Satz des Artikels überstimmen.
OHNE_INLANDSSTEUER = {"ig_lieferung", "drittland", "reverse_charge"}


def ist_gueltig(kennung: Optional[str]) -> bool:
    return kennung in KENNUNGEN


def normieren(kennung: Optional[str]) -> str:
    """Rohwert aus dem Kontakt-Datensatz auf eine gültige Kennung bringen.

    Unbekanntes und Leeres wird zum Inland. Ein Tippfehler im Stammsatz darf
    keinen Umsatz stillschweigend steuerfrei stellen.
    """
    if kennung is None:
        return VORGABE
    wert = str(kennung).strip()
    if not wert:
        return VORGABE
    # Auch den Anzeigenamen annehmen: Der Kontakt speichert den Wert einer
    # Auswahlliste, und wer die Liste im Feld-Editor umbenennt, hätte sonst
    # lauter ungültige Stammsätze.
    if wert in KENNUNGEN:
        return wert
    for kennung_, name in STEUERFAELLE:
        if wert.lower() == name.lower():
            return kennung_
    return VORGABE


def bezeichnung(kennung: Optional[str]) -> str:
    return BEZEICHNUNGEN.get(normieren(kennung), BEZEICHNUNGEN[VORGABE])
