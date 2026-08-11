"""
Formatneutraler Datensatz einer E-Rechnung.

Hier steckt die inhaltliche Arbeit: Adressen zusammensuchen, Steuer je Satz
aufteilen, Einheiten in Normcodes übersetzen, Pflichtangaben prüfen. Die
Formate darüber (Factur-X heute, ebInterface später) unterscheiden sich nur
noch darin, wie sie dieselben Werte hinschreiben.

Diese Trennung ist nicht Selbstzweck. Würde man das XML direkt aus dem Beleg
erzeugen, stünde die Steueraufteilung beim zweiten Format ein zweites Mal da —
und wäre irgendwann einmal richtig und einmal falsch. Dieselbe Überlegung wie
bei ``services/positionen.py``.

**Was fehlt, wird gemeldet, nicht ersetzt.** Eine E-Rechnung ohne UID des
Verkäufers oder mit geratener Mengeneinheit ist schlimmer als gar keine: Sie
sieht gültig aus. Deshalb sammelt ``pruefen()`` alle Lücken auf einmal ein,
statt bei der ersten abzubrechen — wer sie schließt, will sie vollständig
kennen.
"""
from dataclasses import dataclass, field
from datetime import date as Datum
from decimal import Decimal
from typing import Optional, List

from app.services import positionen as positionen_service
from app.services.erechnung import einheiten as einheiten_service


# ── Bausteine ─────────────────────────────────────────────────────────────────

@dataclass
class Partei:
    """Verkäufer oder Empfänger."""
    name: str = ""
    strasse: str = ""
    plz: str = ""
    ort: str = ""
    land: str = "AT"                 # ISO 3166-1 alpha-2
    uid: str = ""                    # USt-Identifikationsnummer
    email: str = ""
    # Nur für den Verkäufer, nach § 14 UGB auf dem Beleg verlangt
    firmensitz: str = ""
    firmenbuchnummer: str = ""
    firmenbuchgericht: str = ""


@dataclass
class Zeile:
    """Eine Rechnungszeile. Gliederungszeilen kommen hier nicht an."""
    nummer: str
    bezeichnung: str
    menge: Decimal
    einheit_code: str
    einzelpreis: Decimal
    netto: Decimal
    steuersatz: Optional[Decimal]    # None = Reverse Charge
    beschreibung: str = ""


@dataclass
class Steuerzeile:
    """Bemessungsgrundlage und Steuer zu einem Satz."""
    satz: Optional[Decimal]
    netto: Decimal
    steuer: Decimal
    kategorie: str                   # S | AE | E — siehe KATEGORIE


@dataclass
class Abschlag:
    """
    Ein Abzug auf Belegebene, je Steuersatz.

    Hier landen Gruppenrabatte und der Abzug bereits gestellter Anzahlungen.
    Beide mindern in DeineZeit die Bemessungsgrundlage — auf dem PDF wie in der
    UVA. EN 16931 bildet genau das als „document level allowance" ab (BT-92 ff.)
    mit eigener Steuerkategorie und eigenem Satz.
    """
    betrag: Decimal                  # positiv; das Vorzeichen macht die Rolle
    steuersatz: Optional[Decimal]
    kategorie: str
    grund: str = ""


@dataclass
class Zahlung:
    iban: str = ""
    bic: str = ""
    kontoinhaber: str = ""
    faellig: Optional[Datum] = None
    skonto_prozent: Optional[Decimal] = None
    skonto_tage: Optional[int] = None


@dataclass
class ERechnung:
    """Der vollständige Datensatz eines Belegs."""
    nummer: str = ""
    datum: Optional[Datum] = None
    typ_code: str = "380"            # 380 Rechnung, 381 Gutschrift
    waehrung: str = "EUR"
    referenz: str = ""               # Auftragsreferenz des Empfängers
    leistungsdatum: Optional[Datum] = None
    verkaeufer: Partei = field(default_factory=Partei)
    empfaenger: Partei = field(default_factory=Partei)
    zeilen: List[Zeile] = field(default_factory=list)
    steuern: List[Steuerzeile] = field(default_factory=list)
    zahlung: Zahlung = field(default_factory=Zahlung)
    abschlaege: List[Abschlag] = field(default_factory=list)
    # Summe der Zeilen VOR Abschlägen (BT-106)
    zeilen_gesamt: Decimal = Decimal("0")
    # Summe der Abschläge (BT-107)
    abschlag_gesamt: Decimal = Decimal("0")
    # Bemessungsgrundlage = zeilen_gesamt - abschlag_gesamt (BT-109)
    netto_gesamt: Decimal = Decimal("0")
    steuer_gesamt: Decimal = Decimal("0")
    brutto_gesamt: Decimal = Decimal("0")
    zahlbetrag: Decimal = Decimal("0")
    hinweis: str = ""                # Kleinunternehmer, Reverse Charge …


# UNTDID-5305-Kategorien: Was für eine Art von Umsatz die Zeile ist.
#   S  Regelsatz
#   AE Reverse Charge (Steuerschuld beim Empfänger)
#   E  steuerbefreit
KATEGORIE_NORMAL = "S"
KATEGORIE_REVERSE_CHARGE = "AE"
KATEGORIE_BEFREIT = "E"

# Belegarten nach UNTDID 1001
TYP_RECHNUNG = "380"
TYP_GUTSCHRIFT = "381"


# ── Aus einem Beleg bauen ─────────────────────────────────────────────────────

def _feld(daten: dict, *namen) -> str:
    """
    Sucht ein Stammdatenfeld über Teilstücke seines Namens.

    Die Stammdatenfelder sind frei benennbar; „UID", „uid_nummer" und
    „USt-IdNr." meinen dasselbe. Dieselbe Heuristik verwendet schon die
    PDF-Fußzeile — für das XML zusätzlich wichtig, weil ein leeres Pflichtfeld
    hier nicht bloß hässlich aussieht, sondern die Datei unbrauchbar macht.
    """
    if not daten:
        return ""
    for name in namen:
        for schluessel, wert in daten.items():
            if name in str(schluessel).lower() and str(wert or "").strip():
                return str(wert).strip()
    return ""


def _partei_aus_kontakt(kontakt, ist_verkaeufer: bool = False) -> Partei:
    if kontakt is None:
        return Partei()
    daten = getattr(kontakt, "data", None) or {}
    p = Partei(
        name=getattr(kontakt, "display_name", "") or "",
        strasse=_feld(daten, "adresse", "strasse", "straße"),
        plz=_feld(daten, "plz", "postleitzahl"),
        ort=_feld(daten, "ort", "stadt"),
        land=(_feld(daten, "land", "country") or "AT"),
        uid=_feld(daten, "uid", "ustid", "ust-id", "atu"),
        email=_feld(daten, "email", "mail"),
    )
    # Zweibuchstabiger Ländercode. „Österreich" ist ein Land, kein Code.
    p.land = _laendercode(p.land)
    if ist_verkaeufer:
        p.firmensitz = _feld(daten, "firmensitz", "sitz")
        p.firmenbuchnummer = _feld(daten, "firmenbuch")
        p.firmenbuchgericht = _feld(daten, "gericht")
    return p


_LAENDER = {
    "österreich": "AT", "oesterreich": "AT", "austria": "AT", "at": "AT",
    "deutschland": "DE", "germany": "DE", "de": "DE",
    "schweiz": "CH", "switzerland": "CH", "ch": "CH",
    "italien": "IT", "italy": "IT", "it": "IT",
    "slowenien": "SI", "si": "SI",
    "ungarn": "HU", "hu": "HU",
    "tschechien": "CZ", "cz": "CZ",
    "slowakei": "SK", "sk": "SK",
    "liechtenstein": "LI", "li": "LI",
}


def _laendercode(wert: str) -> str:
    """
    Zweibuchstabiger Ländercode. Unbekanntes bleibt stehen, damit die Prüfung
    es meldet — ein stiller Rückfall auf „AT" würde eine Auslandsrechnung
    unbemerkt zur Inlandsrechnung machen.
    """
    schluessel = str(wert or "").strip().lower()
    if not schluessel:
        return ""
    return _LAENDER.get(schluessel, wert.strip().upper()[:2] if len(wert.strip()) == 2 else wert.strip())


def _kategorie(satz, tax_mode: str) -> str:
    if tax_mode == "kleinunternehmer":
        return KATEGORIE_BEFREIT
    if satz is None:
        return KATEGORIE_REVERSE_CHARGE
    return KATEGORIE_NORMAL


def aus_beleg(invoice, verkaeufer_kontakt, empfaenger_kontakt,
              bank: dict = None) -> ERechnung:
    """
    Baut den Datensatz aus einem Beleg.

    Anzahlungsabzug und Gruppenrabatt werden als **Abschläge auf Belegebene**
    geführt, nicht als Zeilen und nicht als ``TotalPrepaidAmount``.

    Das war ein Umweg wert: ``TotalPrepaidAmount`` mindert in EN 16931 nur den
    Zahlbetrag, **nicht** die Bemessungsgrundlage. In DeineZeit mindert der
    Anzahlungsabzug aber sehr wohl die Grundlage — auf dem PDF und in der UVA.
    Beides zugleich hieße, denselben Betrag zweimal abzuziehen. Und ZUGFeRD
    verlangt, dass PDF und XML dasselbe sagen; das PDF ist hier die Vorgabe.
    """
    bank = bank or {}
    daten = ERechnung(
        nummer=invoice.number or "",
        datum=invoice.date,
        typ_code=TYP_GUTSCHRIFT if invoice.doc_type == "gutschrift" else TYP_RECHNUNG,
        waehrung=invoice.currency or "EUR",
        referenz=invoice.reference or "",
        leistungsdatum=invoice.delivery_date or invoice.date,
        verkaeufer=_partei_aus_kontakt(verkaeufer_kontakt, ist_verkaeufer=True),
        empfaenger=_partei_aus_kontakt(empfaenger_kontakt),
    )

    positionen = list(invoice.positions)
    kleinunternehmer = invoice.tax_mode == "kleinunternehmer"

    # ── Zeilen ────────────────────────────────────────────────────────────────
    nummer = 0
    for pos in positionen:
        typ = positionen_service.typ(pos)
        if typ in positionen_service.GLIEDERUNG:
            continue
        if typ in (positionen_service.ANZAHLUNGSABZUG, "discount"):
            # Beide mindern die Grundlage, aber nicht zeilenweise: Ein
            # Gruppenrabatt verteilt sich anteilig auf die Sätze seiner Gruppe.
            # Sie werden weiter unten aus der Differenz zwischen Zeilensumme
            # und maßgeblicher Nettosumme je Satz abgeleitet — so kann die
            # Verteilung gar nicht von der auf dem PDF abweichen.
            continue
        nummer += 1
        daten.zeilen.append(Zeile(
            nummer=str(nummer),
            bezeichnung=(pos.description or "").strip() or "Position",
            menge=Decimal(str(pos.quantity or 0)),
            einheit_code=einheiten_service.code(pos.unit) or "",
            einzelpreis=Decimal(str(pos.unit_price or 0)),
            netto=Decimal(str(pos.line_total or 0)),
            steuersatz=None if kleinunternehmer else pos.tax_rate,
            beschreibung=(pos.detail or "").strip(),
        ))

    # ── Steuer je Satz ────────────────────────────────────────────────────────
    # Über den Positionen-Dienst, damit ein Gruppenrabatt genauso anteilig
    # verteilt wird wie auf dem PDF und in der UVA.
    je_satz = positionen_service.netto_je_satz(positionen, invoice.tax_mode)
    if kleinunternehmer:
        daten.steuern.append(Steuerzeile(
            satz=Decimal("0"),
            netto=Decimal(str(invoice.subtotal or 0)),
            steuer=Decimal("0"),
            kategorie=KATEGORIE_BEFREIT,
        ))
    else:
        for satz in sorted(je_satz, key=lambda s: (s is None, -(s or 0))):
            netto = je_satz[satz]
            if not netto:
                continue
            steuer = (netto * satz / 100).quantize(Decimal("0.01")) if satz is not None \
                else Decimal("0")
            daten.steuern.append(Steuerzeile(
                satz=satz if satz is not None else Decimal("0"),
                netto=netto,
                steuer=steuer,
                kategorie=_kategorie(satz, invoice.tax_mode),
            ))

    # ── Abschläge je Satz ─────────────────────────────────────────────────────
    # Abgeleitet statt nachgerechnet: Der Abschlag ist genau die Differenz
    # zwischen dem, was die Zeilen ergeben, und dem, was je Satz maßgeblich
    # ist. Damit kann er von der Aufteilung auf dem PDF nicht abweichen — und
    # die Rabattverteilung steht weiterhin nur an einer Stelle im Code.
    if not kleinunternehmer:
        zeilen_je_satz: dict = {}
        for z in daten.zeilen:
            zeilen_je_satz[z.steuersatz] = zeilen_je_satz.get(
                z.steuersatz, Decimal("0")) + z.netto
        for satz, zeilensumme in zeilen_je_satz.items():
            massgeblich = je_satz.get(satz, Decimal("0"))
            abzug = zeilensumme - massgeblich
            if abzug > 0:
                daten.abschlaege.append(Abschlag(
                    betrag=abzug,
                    steuersatz=satz if satz is not None else Decimal("0"),
                    kategorie=_kategorie(satz, invoice.tax_mode),
                    grund="Rabatt und bereits gestellte Rechnungen",
                ))

    # ── Summen ────────────────────────────────────────────────────────────────
    # Aus dem Beleg übernommen, nicht neu gerechnet: Was auf dem PDF steht und
    # was im XML steht, muss auf den Cent dasselbe sein. Zwei Rechenwege sind
    # zwei Gelegenheiten, sich zu unterscheiden.
    daten.zeilen_gesamt = sum((z.netto for z in daten.zeilen), Decimal("0"))
    daten.abschlag_gesamt = sum((a.betrag for a in daten.abschlaege), Decimal("0"))
    daten.netto_gesamt = Decimal(str(invoice.subtotal or 0))
    daten.steuer_gesamt = Decimal(str(invoice.tax_total or 0))
    daten.brutto_gesamt = Decimal(str(invoice.total or 0))
    daten.zahlbetrag = daten.brutto_gesamt

    # ── Zahlung ───────────────────────────────────────────────────────────────
    daten.zahlung = Zahlung(
        iban=str(bank.get("iban", "") or "").replace(" ", ""),
        bic=str(bank.get("bic", "") or "").strip(),
        kontoinhaber=str(bank.get("bank", "") or "").strip() or daten.verkaeufer.name,
        faellig=invoice.due_date,
        skonto_prozent=invoice.skonto_percent,
        skonto_tage=invoice.skonto_days,
    )

    if kleinunternehmer:
        daten.hinweis = ("Kleinunternehmer gemäß § 6 Abs. 1 Z 27 UStG — "
                         "es wird keine Umsatzsteuer ausgewiesen.")
    elif any(z.kategorie == KATEGORIE_REVERSE_CHARGE for z in daten.steuern):
        daten.hinweis = "Steuerschuld geht auf den Leistungsempfänger über (Reverse Charge)."

    return daten


# ── Vollständigkeit ───────────────────────────────────────────────────────────

def pruefen(daten: ERechnung, invoice=None) -> List[str]:
    """
    Sammelt alle fehlenden Pflichtangaben auf einmal ein.

    Absichtlich keine Ausnahme beim ersten Fund: Wer eine E-Rechnung
    einrichtet, will die Liste, nicht das erste Problem.
    """
    fehlt = []

    v, e = daten.verkaeufer, daten.empfaenger
    if not daten.nummer:
        fehlt.append("Der Beleg hat noch keine Nummer — er ist ein Entwurf.")
    if not daten.datum:
        fehlt.append("Das Belegdatum fehlt.")

    for bezeichnung, partei in (("Absender", v), ("Empfänger", e)):
        if not partei.name:
            fehlt.append(f"{bezeichnung}: Name fehlt.")
        if not partei.strasse:
            fehlt.append(f"{bezeichnung}: Straße fehlt.")
        if not partei.plz or not partei.ort:
            fehlt.append(f"{bezeichnung}: Postleitzahl oder Ort fehlt.")
        if len(partei.land or "") != 2:
            fehlt.append(f"{bezeichnung}: Ländercode fehlt oder ist keine "
                         f"zweibuchstabige Kennung (aktuell \u201e{partei.land}\u201c).")

    if not v.uid:
        fehlt.append("Die UID des Absenders fehlt. Ohne sie ist keine "
                     "E-Rechnung möglich — sie steht in den Stammdaten des "
                     "Firmenkontakts.")
    if not v.email:
        fehlt.append("Eine E-Mail-Adresse des Absenders fehlt.")

    # Reverse Charge geht nur mit UID des Empfängers — sonst ist der Übergang
    # der Steuerschuld nicht belegbar.
    if any(s.kategorie == KATEGORIE_REVERSE_CHARGE for s in daten.steuern) and not e.uid:
        fehlt.append("Bei Reverse Charge ist die UID des Empfängers Pflicht.")

    if not daten.zeilen:
        fehlt.append("Der Beleg hat keine Positionen mit Betrag.")

    ohne_code = [z.bezeichnung for z in daten.zeilen if not z.einheit_code]
    if ohne_code:
        offen = einheiten_service.unbekannte(
            p.unit for p in (invoice.positions if invoice else [])
        ) if invoice else []
        liste = ", ".join(f"\u201e{x}\u201c" for x in offen) if offen else ""
        fehlt.append(
            "Mengeneinheiten ohne Normcode" + (f" ({liste})" if liste else "") +
            f": {', '.join(ohne_code[:3])}"
            f"{' …' if len(ohne_code) > 3 else ''}. "
            "Eine E-Rechnung braucht eine genormte Einheit; geraten wird sie "
            "nicht, weil aus Stunden sonst still Stück würden.")

    if not daten.zahlung.iban and daten.typ_code == TYP_RECHNUNG:
        fehlt.append("Die IBAN fehlt — sie steht in den Belegeinstellungen "
                     "oder beim Firmenkontakt.")

    return fehlt
