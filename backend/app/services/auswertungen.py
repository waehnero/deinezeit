"""
Umsatzauswertungen (C-15).

**Der Stichtag ist das Belegdatum** (Entscheidung Oliver) — dieselbe Abgrenzung
wie in UVA, Verkaufsbuch und Monatsabschluss. Der Grund ist wichtiger als er
klingt: Zwei Auswertungen im selben Haus, die zum selben Monat verschiedene
Zahlen nennen, kosten mehr Zeit als sie sparen. Wer den Zahlungseingang sehen
will, findet ihn in den offenen Posten.

**Was zählt** ist deshalb wortgleich zur UVA abgegrenzt:

  * kein Entwurf — er ist beim Kunden nie angekommen
  * nur Rechnung und Gutschrift — ein Angebot ist kein Umsatz
  * keine wiederkehrende Vorlage — sie ist ein Muster, kein Beleg
  * storniert nur dann, wenn eine Gutschrift dagegensteht; die hebt ihn auf

Gerechnet wird über ``services/positionen.py``, nicht über eine eigene
Schleife. Ein Gruppenrabatt und der Abzug gestellter Anzahlungen mindern damit
genauso wie auf dem PDF und in der UVA. Eine eigene Schleife hier wäre der
vierte Rechenweg für dieselbe Sache — und der erste, der irgendwann abweicht.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoicePosition
from app.models.masterdata import EntityRecord
from app.services import positionen as positionen_service


# Belegarten, die Umsatz tragen
UMSATZARTEN = ("rechnung", "gutschrift")


def _belege(db: Session, von: Optional[date], bis: Optional[date]):
    """Die Belege eines Zeitraums — abgegrenzt wie in der UVA."""
    q = db.query(Invoice).filter(
        Invoice.status != "entwurf",
        Invoice.doc_type.in_(UMSATZARTEN),
        Invoice.is_recurring_template == False,   # noqa: E712
        or_(Invoice.status != "storniert", Invoice.cancel_mode == "with_credit"),
    )
    if von:
        q = q.filter(Invoice.date >= von)
    if bis:
        q = q.filter(Invoice.date <= bis)
    return q.order_by(Invoice.date).all()


def _netto(beleg: Invoice) -> Decimal:
    """
    Nettoumsatz eines Belegs.

    Über den Positionen-Dienst statt über ``beleg.subtotal``: Bei
    Reverse-Charge-Zeilen und Kleinunternehmern ist die gespeicherte Summe zwar
    dieselbe, aber die Aufteilung je Satz braucht ohnehin denselben Weg — und
    ein Rechenweg ist besser als zwei, die zufällig übereinstimmen.
    """
    werte = positionen_service.netto_je_satz(list(beleg.positions), beleg.tax_mode)
    return sum(werte.values(), Decimal("0"))


# ── Umsatz je Monat ───────────────────────────────────────────────────────────

def je_monat(db: Session, jahr: int) -> dict:
    """
    Zwölf Monate des Jahres, dazu dieselben Monate des Vorjahres.

    Alle zwölf werden ausgegeben, auch die leeren. Eine Lücke in der Reihe
    liest sich sonst wie ein fehlender Monat statt wie ein Monat ohne Umsatz.
    """
    def _summen(j: int) -> list:
        werte = [Decimal("0")] * 12
        anzahl = [0] * 12
        for beleg in _belege(db, date(j, 1, 1), date(j, 12, 31)):
            werte[beleg.date.month - 1] += _netto(beleg)
            anzahl[beleg.date.month - 1] += 1
        return werte, anzahl

    heuer, anzahl = _summen(jahr)
    vorjahr, _ = _summen(jahr - 1)

    monate = []
    for i in range(12):
        monate.append({
            "monat": i + 1,
            "netto": heuer[i],
            "vorjahr": vorjahr[i],
            "belege": anzahl[i],
        })
    return {
        "jahr": jahr,
        "monate": monate,
        "netto_gesamt": sum(heuer, Decimal("0")),
        "vorjahr_gesamt": sum(vorjahr, Decimal("0")),
        "belege_gesamt": sum(anzahl),
    }


# ── Umsatz je Kunde ───────────────────────────────────────────────────────────

def je_kunde(db: Session, von: Optional[date], bis: Optional[date],
             limit: int = 0) -> dict:
    """
    Rangliste der Kunden mit Anteil am Gesamtumsatz.

    Der Anteil wird immer am **vollen** Umsatz des Zeitraums gerechnet, auch
    wenn die Liste gekürzt ist. Sonst summierten sich die Anteile der obersten
    zehn auf 100 %, und die Frage „wie abhängig bin ich vom größten Kunden"
    bekäme eine zu große Antwort.
    """
    summen: dict = defaultdict(lambda: {"netto": Decimal("0"), "belege": 0})
    for beleg in _belege(db, von, bis):
        schluessel = beleg.contact_id
        eintrag = summen[schluessel]
        eintrag["netto"] += _netto(beleg)
        eintrag["belege"] += 1

    gesamt = sum(e["netto"] for e in summen.values()) or Decimal("0")
    namen = _namen(db, [k for k in summen if k])

    zeilen = []
    for kontakt_id, eintrag in summen.items():
        zeilen.append({
            "contact_id": kontakt_id,
            # Belege ohne Kontakt gibt es (Barverkauf, Altbestand). Sie
            # verschwinden nicht, sondern werden benannt.
            "name": namen.get(kontakt_id) or ("— ohne Kontakt —" if not kontakt_id
                                              else "— gelöschter Kontakt —"),
            "netto": eintrag["netto"],
            "belege": eintrag["belege"],
            "anteil": (eintrag["netto"] / gesamt * 100).quantize(Decimal("0.1"))
            if gesamt else Decimal("0"),
        })
    zeilen.sort(key=lambda z: z["netto"], reverse=True)
    if limit:
        zeilen = zeilen[:limit]

    return {"zeilen": zeilen, "netto_gesamt": gesamt, "kunden": len(summen)}


def _namen(db: Session, ids: list) -> dict:
    """
    Anzeigenamen zu Stammdaten-Kennungen. Gilt für Kontakte wie für Artikel —
    beide sind ``EntityRecord``, deshalb bewusst nicht „Kontaktnamen".
    """
    if not ids:
        return {}
    return {r.id: r.display_name or ""
            for r in db.query(EntityRecord).filter(EntityRecord.id.in_(ids)).all()}


# ── Umsatz je Artikel ─────────────────────────────────────────────────────────

def je_artikel(db: Session, von: Optional[date], bis: Optional[date],
               limit: int = 0) -> dict:
    """
    Was sich verkauft — soweit die Positionen mit Artikeln verknüpft sind.

    **Die Lücke wird ausgewiesen, nicht versteckt.** Eine frei getippte
    Position hat keine Artikelkennung; sie unter ihrem Text zu gruppieren
    würde „Regiestunden" und „Regiestunde" zu zwei Artikeln machen und eine
    Genauigkeit vortäuschen, die es nicht gibt. Solche Positionen laufen
    deshalb in einer eigenen Zeile zusammen, und der Anteil steht dabei — wer
    sieht, dass 80 % nicht zugeordnet sind, weiß, was die Liste wert ist.
    """
    summen: dict = defaultdict(lambda: {"netto": Decimal("0"), "menge": Decimal("0"),
                                        "belege": set()})
    ohne_artikel = {"netto": Decimal("0"), "belege": set()}

    for beleg in _belege(db, von, bis):
        # Der Faktor bildet Rabatt und Anzahlungsabzug auf die Zeilen ab: Beide
        # mindern den Beleg, hängen aber an keiner einzelnen Position. Ohne
        # ihn wäre die Summe der Artikel größer als der Umsatz des Belegs.
        zeilen = [p for p in beleg.positions
                  if positionen_service.typ(p) in ("item", "time_entry")]
        zeilensumme = sum((p.line_total or Decimal("0") for p in zeilen), Decimal("0"))
        beleg_netto = _netto(beleg)
        faktor = (beleg_netto / zeilensumme) if zeilensumme else Decimal("1")

        for pos in zeilen:
            anteil = (Decimal(str(pos.line_total or 0)) * faktor).quantize(Decimal("0.01"))
            if pos.article_id:
                eintrag = summen[pos.article_id]
                eintrag["netto"] += anteil
                eintrag["menge"] += Decimal(str(pos.quantity or 0))
                eintrag["belege"].add(beleg.id)
            else:
                ohne_artikel["netto"] += anteil
                ohne_artikel["belege"].add(beleg.id)

    namen = _namen(db, list(summen))
    gesamt = sum(e["netto"] for e in summen.values()) + ohne_artikel["netto"]

    zeilen = [{
        "article_id": artikel_id,
        "name": namen.get(artikel_id) or "— gelöschter Artikel —",
        "netto": eintrag["netto"],
        "menge": eintrag["menge"],
        "belege": len(eintrag["belege"]),
    } for artikel_id, eintrag in summen.items()]
    zeilen.sort(key=lambda z: z["netto"], reverse=True)
    if limit:
        zeilen = zeilen[:limit]

    return {
        "zeilen": zeilen,
        "netto_gesamt": gesamt,
        "ohne_artikel_netto": ohne_artikel["netto"],
        "ohne_artikel_belege": len(ohne_artikel["belege"]),
        "ohne_artikel_anteil": (ohne_artikel["netto"] / gesamt * 100).quantize(
            Decimal("0.1")) if gesamt else Decimal("0"),
    }


# ── Angebotsquote ─────────────────────────────────────────────────────────────

# Ein Angebot gilt als gewonnen, wenn es angenommen wurde oder aus ihm ein
# Folgebeleg entstanden ist. „Angenommen" allein reicht nicht: Wer aus einem
# gesendeten Angebot direkt eine Rechnung macht, hat es faktisch gewonnen,
# ohne je auf den Status geklickt zu haben.
GEWONNEN_STATUS = ("angenommen",)
VERLOREN_STATUS = ("abgelehnt",)


def angebotsquote(db: Session, von: Optional[date], bis: Optional[date]) -> dict:
    """
    Wie viele Angebote werden zu Aufträgen.

    Gezählt wird nach dem Datum des **Angebots**, nicht dem der Annahme: Die
    Frage lautet „was ist aus dem geworden, was ich damals hinausgeschickt
    habe", nicht „was kam diesen Monat herein".

    Entwürfe bleiben draußen — ein nicht versendetes Angebot kann man nicht
    verlieren.
    """
    q = db.query(Invoice).filter(
        Invoice.doc_type == "angebot",
        Invoice.status != "entwurf",
        Invoice.is_recurring_template == False,   # noqa: E712
    )
    if von:
        q = q.filter(Invoice.date >= von)
    if bis:
        q = q.filter(Invoice.date <= bis)
    angebote = q.order_by(Invoice.date).all()

    # Aus welchen Angeboten ist ein Folgebeleg entstanden?
    ids = [a.id for a in angebote]
    umgewandelt = set()
    if ids:
        umgewandelt = {
            r[0] for r in db.query(Invoice.related_invoice_id).filter(
                Invoice.related_invoice_id.in_(ids),
                Invoice.doc_type.in_(("rechnung", "auftragsbestaetigung")),
                Invoice.status != "entwurf",
            ).distinct().all()
        }

    gewonnen = {"anzahl": 0, "netto": Decimal("0"), "tage": []}
    verloren = {"anzahl": 0, "netto": Decimal("0")}
    offen = {"anzahl": 0, "netto": Decimal("0")}

    for a in angebote:
        netto = _netto(a)
        if a.status in GEWONNEN_STATUS or a.id in umgewandelt:
            gewonnen["anzahl"] += 1
            gewonnen["netto"] += netto
            # Dauer bis zur Entscheidung, soweit erkennbar. `updated_at` ist
            # eine Näherung — ein genaues Annahmedatum führen wir nicht.
            if a.updated_at and a.date:
                tage = (a.updated_at.date() - a.date).days
                if tage >= 0:
                    gewonnen["tage"].append(tage)
        elif a.status in VERLOREN_STATUS:
            verloren["anzahl"] += 1
            verloren["netto"] += netto
        else:
            offen["anzahl"] += 1
            offen["netto"] += netto

    entschieden = gewonnen["anzahl"] + verloren["anzahl"]
    tage = gewonnen["tage"]
    return {
        "gesamt": len(angebote),
        "gesamt_netto": gewonnen["netto"] + verloren["netto"] + offen["netto"],
        "gewonnen": gewonnen["anzahl"],
        "gewonnen_netto": gewonnen["netto"],
        "verloren": verloren["anzahl"],
        "verloren_netto": verloren["netto"],
        "offen": offen["anzahl"],
        "offen_netto": offen["netto"],
        # Die Quote rechnet auf die ENTSCHIEDENEN Angebote. Offene mitzuzählen
        # würde die Quote drücken, solange noch nichts entschieden ist — und
        # jeden Monat rückwirkend verändern.
        "quote": (Decimal(gewonnen["anzahl"]) / entschieden * 100).quantize(
            Decimal("0.1")) if entschieden else None,
        "tage_bis_entscheidung": round(sum(tage) / len(tage)) if tage else None,
    }
