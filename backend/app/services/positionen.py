"""
Positionstypen und ihre Rechenregeln — eine Quelle für alle Auswerter.

Ein Beleg kennt sechs Zeilentypen:

  ``item``       gewöhnliche Position mit Menge, Preis und Steuersatz
  ``time_entry`` wie ``item``, zusätzlich mit einem Zeiteintrag verknüpft
  ``heading``    Überschrift — eröffnet eine Gruppe, trägt keinen Betrag
  ``text``       Freitext zur Erläuterung, ohne Gruppenwirkung
  ``subtotal``   Zwischensumme der laufenden Gruppe, danach neue Gruppe
  ``discount``   Rabatt auf die laufende Gruppe (Betrag oder Prozent)

Die Gruppe reicht von der letzten Überschrift **oder** der letzten
Zwischensumme — je nachdem, was zuletzt kam.

**Warum das hier liegt und nicht in der API:** Die Aufteilung eines Rabatts
auf die Steuersätze einer Gruppe brauchen drei Stellen — die gespeicherten
Summen, die MwSt.-Aufschlüsselung auf dem PDF und der Buchhaltungs-Export.
Dreimal dieselbe Regel zu schreiben heißt, sie irgendwann zweimal richtig und
einmal falsch zu haben.
"""
from collections import defaultdict
from decimal import Decimal


# Zeilen, die einen eigenen Betrag tragen
WERTZEILEN = ("item", "time_entry", "discount")
# Zeilen, die nur der Gliederung dienen
GLIEDERUNG = ("heading", "text", "subtotal")


def typ(pos) -> str:
    return getattr(pos, "pos_type", None) or "item"


def gruppen_netto(positionen: list, ab: int, bis: int) -> dict:
    """
    Netto je Steuersatz innerhalb einer Gruppe — Grundlage für eine Rabattzeile.

    Frühere Rabattzeilen der Gruppe zählen bewusst NICHT mit: Zwei Rabatte
    beziehen sich beide auf denselben Ausgangsbetrag. Alles andere wäre beim
    Lesen des Belegs nicht nachvollziehbar.
    """
    werte = defaultdict(lambda: Decimal("0"))
    for p in positionen[ab:bis]:
        if typ(p) not in ("item", "time_entry"):
            continue
        if p.tax_rate is not None:
            werte[p.tax_rate] += p.line_total or Decimal("0")
    return werte


def rabatt_verteilen(gruppe_je_satz: dict, basis: Decimal, betrag: Decimal) -> dict:
    """
    Verteilt einen Rabattbetrag anteilig auf die Steuersätze der Gruppe.

    Ohne diese Aufteilung wäre ein Rabatt auf eine Gruppe mit gemischten
    Sätzen steuerlich falsch: Der volle Betrag hinge an einem Satz, und die
    MwSt.-Aufschlüsselung auf dem Beleg stimmte nicht mehr.

    Die Rundungsdifferenz trägt der kleinste Satz, damit die Summe der Anteile
    exakt dem Rabattbetrag entspricht.
    """
    if basis <= 0 or not betrag:
        return {}
    anteile, rest = {}, betrag
    saetze = sorted(gruppe_je_satz, reverse=True)
    for i, satz in enumerate(saetze):
        if i == len(saetze) - 1:
            anteile[satz] = rest
        else:
            anteil = (betrag * gruppe_je_satz[satz] / basis).quantize(Decimal("0.01"))
            anteile[satz] = anteil
            rest -= anteil
    return anteile


def rabattbetrag(pos, basis: Decimal) -> Decimal:
    """Rabatt als Prozent der Gruppe oder als fester Betrag; nie mehr als die Gruppe."""
    if pos.discount_pct:
        betrag = (basis * pos.discount_pct / 100).quantize(Decimal("0.01"))
    else:
        betrag = Decimal(str(pos.unit_price or 0)).quantize(Decimal("0.01"))
    return min(betrag, basis) if basis > 0 else betrag


def netto_je_satz(positionen: list, tax_mode: str = "per_position") -> dict:
    """
    Nettobeträge je Steuersatz über den ganzen Beleg — inklusive der anteilig
    verteilten Rabatte. ``None`` als Schlüssel steht für Reverse Charge.

    Setzt voraus, dass ``line_total`` je Position bereits berechnet ist
    (das erledigt ``_calc_totals`` beim Speichern).
    """
    werte = defaultdict(lambda: Decimal("0"))
    if tax_mode == "kleinunternehmer":
        return werte

    gruppe_ab = 0
    for i, pos in enumerate(positionen):
        t = typ(pos)
        if t == "heading":
            gruppe_ab = i + 1
            continue
        if t == "subtotal":
            gruppe_ab = i + 1
            continue
        if t == "text":
            continue
        if t == "discount":
            gruppe = gruppen_netto(positionen, gruppe_ab, i)
            basis = sum(gruppe.values(), Decimal("0"))
            betrag = -(pos.line_total or Decimal("0"))      # line_total ist negativ
            for satz, anteil in rabatt_verteilen(gruppe, basis, betrag).items():
                werte[satz] -= anteil
            continue
        werte[pos.tax_rate] += pos.line_total or Decimal("0")
    return werte
