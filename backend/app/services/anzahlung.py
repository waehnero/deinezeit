"""
Abrechnung in Stufen: Anzahlung → Teilrechnung → Schlussrechnung (C-10).

Im Projektgeschäft wird nicht einmal am Ende abgerechnet. Vor Baubeginn geht
eine Anzahlungsrechnung hinaus, nach Baufortschritt Teilrechnungen, und am
Ende steht eine Schlussrechnung über die **Gesamtleistung**, von der alles
bereits Fakturierte wieder abgezogen wird.

**Warum abgezogen und nicht einfach weniger fakturiert wird:** Eine
Anzahlungsrechnung ist bereits voll umsatzsteuerpflichtig. Stünde in der
Schlussrechnung nur der Restbetrag, wäre die Leistung dem Kunden gegenüber
nie vollständig abgerechnet — er könnte die Vorsteuer nicht sauber zuordnen,
und aus dem Beleg allein ginge nicht hervor, was insgesamt geschuldet war.
Deshalb: volle Leistung ausweisen, Fakturiertes abziehen.

**Was abgezogen wird — alles Fakturierte, nicht das Bezahlte** (Entscheidung
Oliver): Die Steuer entsteht mit der Rechnung, nicht mit dem Zahlungseingang.
Würde nur Bezahltes abgezogen, wäre die Umsatzsteuer einer offenen
Anzahlungsrechnung zweimal in der UVA. Der unbezahlte Betrag bleibt ein
eigener offener Posten und wird dort gemahnt — er verschwindet nicht.

**Je Steuersatz eine eigene Abzugszeile.** Eine Sammelzeile ginge nur bei
einem einzigen Satz auf. Sobald 20 % und 13 % gemischt sind, muss der Abzug
getrennt ausgewiesen werden, sonst stimmt die MwSt.-Aufschlüsselung auf dem
Beleg nicht mehr.

> Hinweis für die Buchhaltung: Dieses System weist Erlöse je Beleg und
> Steuersatz aus. Die Anzahlungsrechnung bucht damit bereits Erlös, die
> Schlussrechnung nur noch den Rest — in Summe stimmt es. Eine Buchhaltung,
> die mit einem eigenen Konto „erhaltene Anzahlungen" arbeitet, bucht anders.
> Das Muster gehört einmal von der Steuerberatung gegengelesen.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoicePosition
from app.services import positionen as positionen_service


STUFEN = ("anzahlung", "teil", "schluss")

# Stufen, die in der Schlussrechnung abgezogen werden
ABZUGSSTUFEN = ("anzahlung", "teil")

# Belege in diesen Zuständen zählen nicht: Der Entwurf ist noch nicht
# hinausgegangen, der Stornierte ist rückgängig gemacht.
IGNORIERTE_STATUS = ("entwurf", "storniert")


def bezeichnung(stufe: str) -> str:
    """Titel für Beleg und Liste."""
    return {
        "anzahlung": "Anzahlungsrechnung",
        "teil": "Teilrechnung",
        "schluss": "Schlussrechnung",
    }.get(stufe or "", "Rechnung")


# ── Der Strang ────────────────────────────────────────────────────────────────

def strang_kopf(beleg: Invoice) -> str:
    """
    Kennung des Strangs, zu dem ein Beleg gehört.

    Der Kopf zeigt auf sich selbst. Dadurch bleibt „alle Belege des Strangs"
    eine einzige Abfrage — ohne Sonderfall für den ersten Beleg.
    """
    return beleg.chain_id or beleg.id


def strang_anlegen(db: Session, kopf: Invoice) -> None:
    """Macht einen Beleg zum Kopf eines Strangs, falls er noch keinem angehört."""
    if not kopf.chain_id:
        kopf.chain_id = kopf.id
        db.flush()


def strang_belege(db: Session, chain_id) -> list:
    """Alle Belege eines Strangs, älteste zuerst."""
    if not chain_id:
        return []
    return (db.query(Invoice)
            .filter(Invoice.chain_id == chain_id)
            .order_by(Invoice.date, Invoice.created_at)
            .all())


def abzugsfaehige_belege(db: Session, chain_id, ausser_id=None) -> list:
    """
    Die bereits gestellten Anzahlungs- und Teilrechnungen eines Strangs.

    Entwürfe und Stornierte bleiben draußen: Der Entwurf ist beim Kunden nie
    angekommen, der Stornierte wurde rückgängig gemacht — in beiden Fällen gibt
    es keine Steuer, die abzuziehen wäre.
    """
    belege = []
    for b in strang_belege(db, chain_id):
        if ausser_id and b.id == ausser_id:
            continue
        if b.doc_type != "rechnung":
            continue
        if (b.billing_stage or "") not in ABZUGSSTUFEN:
            continue
        if b.status in IGNORIERTE_STATUS:
            continue
        belege.append(b)
    return belege


def hat_schlussrechnung(db: Session, chain_id, ausser_id=None) -> bool:
    """
    Gibt es im Strang schon eine gültige Schlussrechnung?

    Zwei Schlussrechnungen im selben Strang würden dieselben Anzahlungen
    zweimal abziehen. Statt nachzuhalten, welcher Abzug schon verbraucht ist,
    lassen wir nur eine zu — das ist auch fachlich der Normalfall.
    """
    for b in strang_belege(db, chain_id):
        if ausser_id and b.id == ausser_id:
            continue
        if (b.billing_stage or "") == "schluss" and b.status not in IGNORIERTE_STATUS:
            return True
    return False


# ── Der Abzug ─────────────────────────────────────────────────────────────────

def netto_je_satz(beleg: Invoice) -> dict:
    """Nettobeträge eines Belegs je Steuersatz — dieselbe Regel wie überall."""
    return positionen_service.netto_je_satz(list(beleg.positions), beleg.tax_mode)


def erloeskonto(beleg: Invoice) -> str:
    """
    Das Erlöskonto eines Belegs — aber nur, wenn es eindeutig ist.

    Der Abzug muss den Umsatz dort zurücknehmen, wo er gebucht wurde. Steht
    auf allen Wertzeilen dasselbe Konto, ist das eindeutig; verteilt sich der
    Beleg auf mehrere Konten, gibt es kein einzelnes richtiges, und wir geben
    ``None`` zurück — dann greift das Standard-Erlöskonto. Die Summe stimmt in
    beiden Fällen, nur die Aufteilung auf die Konten ist im zweiten Fall
    gröber. Zu raten wäre schlechter als das offen zu lassen.
    """
    konten = {p.account_nr for p in beleg.positions
              if positionen_service.typ(p) not in positionen_service.GLIEDERUNG}
    return konten.pop() if len(konten) == 1 else None


def abzug_gruppen(belege: list) -> dict:
    """
    Summiert die abzuziehenden Nettobeträge je **Steuersatz und Erlöskonto**.

    Rückgabe: ``{(steuersatz, konto): betrag}`` mit **positiven** Beträgen. Das
    Vorzeichen setzt erst die Positionszeile — hier zu rechnen, wie es später
    gedruckt wird, macht die Zwischenschritte schwer lesbar.
    """
    summen: dict = {}
    for b in belege:
        konto = erloeskonto(b)
        for satz, netto in netto_je_satz(b).items():
            if not netto:
                continue
            schluessel = (satz, konto)
            summen[schluessel] = summen.get(schluessel, Decimal("0")) + netto
    return {k: betrag for k, betrag in summen.items() if betrag}


def abzug_je_satz(belege: list) -> dict:
    """
    Dasselbe, nur ohne Kontoaufteilung — für die Anzeige und die Prüfung auf
    Überabzug. Beides interessiert sich für die Steuer, nicht für die Konten.
    """
    summen: dict = {}
    for (satz, _konto), betrag in abzug_gruppen(belege).items():
        summen[satz] = summen.get(satz, Decimal("0")) + betrag
    return summen


def abzugszeilen(belege: list, ab_sortierung: int = 1000) -> list:
    """
    Baut die Abzugspositionen für die Schlussrechnung.

    Je Steuersatz eine Zeile. Der Text nennt die Belegnummern, damit auf dem
    ausgedruckten Beleg nachvollziehbar bleibt, *was* abgezogen wurde — die
    Verknüpfung im Datenbestand hilft dem Kunden mit dem Papier in der Hand
    nicht weiter.
    """
    gruppen = abzug_gruppen(belege)
    if not gruppen:
        return []

    nummern = ", ".join(b.number or "Entwurf" for b in belege)
    mehrere = len(belege) > 1
    einleitung = ("Abzüglich bereits gestellter Rechnungen"
                  if mehrere else "Abzüglich bereits gestellter Rechnung")

    zeilen = []
    # Sortiert, damit die Reihenfolge auf dem Beleg nicht von der
    # Einfügereihenfolge im Wörterbuch abhängt. ``None`` (Reverse Charge)
    # kommt ans Ende.
    reihenfolge = sorted(gruppen, key=lambda k: (k[0] is None, -(k[0] or 0), k[1] or ""))
    for i, (satz, konto) in enumerate(reihenfolge):
        betrag = gruppen[(satz, konto)]
        satz_text = f" ({satz:g} % USt.)" if satz is not None else " (Reverse Charge)"
        zeilen.append({
            "pos_type": positionen_service.ANZAHLUNGSABZUG,
            "description": f"{einleitung}: {nummern}{satz_text}",
            "quantity": Decimal("1"),
            "unit_price": -betrag,
            "tax_rate": satz,
            # Der Abzug bucht auf dasselbe Erlöskonto wie die Anzahlung —
            # sonst stünde der Umsatz auf einem Konto und seine Rücknahme auf
            # einem anderen.
            "account_nr": konto,
            "sort_order": ab_sortierung + i,
        })
    return zeilen


def zeilen_anhaengen(db: Session, schluss: Invoice, belege: list) -> list:
    """Hängt die Abzugszeilen an eine Schlussrechnung an."""
    letzte = max((p.sort_order or 0) for p in schluss.positions) if schluss.positions else 0
    erzeugt = []
    for daten in abzugszeilen(belege, ab_sortierung=letzte + 1):
        pos = InvoicePosition(invoice_id=schluss.id, **daten)
        db.add(pos)
        erzeugt.append(pos)
    return erzeugt


# ── Prüfungen ─────────────────────────────────────────────────────────────────

def pruefe_abzug(schluss: Invoice, abzug: dict) -> list:
    """
    Meldet, wenn mehr abgezogen wird als die Schlussrechnung an Leistung
    ausweist — je Steuersatz geprüft.

    Das passiert echt: Wer die Schlussrechnung mit den Positionen der
    Restleistung statt der Gesamtleistung füllt, bekommt einen negativen
    Beleg. Der Fehler wird gemeldet, nicht stillschweigend korrigiert — was
    hier richtig ist, weiß nur der Mensch.
    """
    hinweise = []
    leistung = {}
    for p in schluss.positions:
        if positionen_service.typ(p) == positionen_service.ANZAHLUNGSABZUG:
            continue
        if positionen_service.typ(p) in positionen_service.GLIEDERUNG:
            continue
        leistung[p.tax_rate] = leistung.get(p.tax_rate, Decimal("0")) + (p.line_total or Decimal("0"))

    for satz, betrag in abzug.items():
        vorhanden = leistung.get(satz, Decimal("0"))
        if betrag > vorhanden:
            satz_text = f"{satz:g} %" if satz is not None else "Reverse Charge"
            hinweise.append(
                f"Zu {satz_text} werden {betrag:.2f} abgezogen, die Schlussrechnung "
                f"weist aber nur {vorhanden:.2f} an Leistung aus. Enthält sie die "
                f"Gesamtleistung oder nur den Rest?")
    return hinweise
