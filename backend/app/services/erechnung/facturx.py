"""
Factur-X / ZUGFeRD 2.5 — Cross Industry Invoice (CII), Profil EN 16931.

Serialisiert den formatneutralen Datensatz nach UN/CEFACT CII. Das Profil
``urn:cen.eu:en16931:2017`` ist die Stufe, die eine vollwertige Rechnung mit
Positionen abbildet — darunter (BASIC, MINIMUM) fehlen Zeilen oder Adressen.

**Die Reihenfolge der Elemente ist Teil des Schemas.** CII ist eine Sequenz,
kein Beutel: Steht ``ram:Name`` nach ``ram:PostalTradeAddress``, ist die Datei
ungültig, auch wenn alle Werte stimmen. Deshalb wird hier streng von oben nach
unten gebaut und nicht nach Bequemlichkeit sortiert.

**Beträge immer mit zwei Nachkommastellen**, auch wenn sie glatt sind: ``100``
und ``100.00`` sind für einen Prüfer nicht dasselbe.

> Diese Datei erzeugt XML. Ob es konform ist, entscheidet ein Validator — vor
> dem produktiven Einsatz gehört eine erzeugte Rechnung extern geprüft.
"""
from decimal import Decimal
from xml.etree import ElementTree as ET

from app.services.erechnung.datensatz import (
    ERechnung, KATEGORIE_REVERSE_CHARGE, KATEGORIE_BEFREIT,
)


NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:"
           "ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}

PROFIL = "urn:cen.eu:en16931:2017"

# Datumsformat 102 = JJJJMMTT (UNTDID 2379)
DATUMSFORMAT = "102"

# Zahlungsart 58 = SEPA-Überweisung, 1 = unbestimmt (UNTDID 4461)
ZAHLUNGSART_UEBERWEISUNG = "58"
ZAHLUNGSART_UNBESTIMMT = "1"

# Begründungen für nicht ausgewiesene Steuer. Sie sind Pflicht, sobald die
# Kategorie nicht der Regelsatz ist — ohne Begründung wäre für den Empfänger
# nicht erkennbar, warum keine Steuer anfällt.
BEFREIUNGSGRUND = {
    KATEGORIE_REVERSE_CHARGE: "Steuerschuld geht auf den Leistungsempfänger "
                              "über (Reverse Charge)",
    KATEGORIE_BEFREIT: "Kleinunternehmer gemäß § 6 Abs. 1 Z 27 UStG",
}


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _sub(eltern, prefix: str, name: str, text=None, **attrib):
    kind = ET.SubElement(eltern, _q(prefix, name), attrib)
    if text is not None:
        kind.text = str(text)
    return kind


def _betrag(wert) -> str:
    """Zwei Nachkommastellen, Punkt als Trenner — so verlangt es das Schema."""
    return f"{Decimal(str(wert or 0)).quantize(Decimal('0.01')):f}"


def _menge(wert) -> str:
    """Menge mit bis zu vier Nachkommastellen, ohne überflüssige Nullen."""
    d = Decimal(str(wert or 0)).quantize(Decimal("0.0001")).normalize()
    return f"{d:f}"


def _prozent(wert) -> str:
    return f"{Decimal(str(wert or 0)).quantize(Decimal('0.01')):f}"


def _datum(eltern, prefix_name: tuple, wert):
    """Ein Datumselement im Format 102 (JJJJMMTT)."""
    if not wert:
        return None
    huelle = _sub(eltern, *prefix_name)
    _sub(huelle, "udt", "DateTimeString", wert.strftime("%Y%m%d"),
         format=DATUMSFORMAT)
    return huelle


# ── Parteien ──────────────────────────────────────────────────────────────────

def _partei(eltern, tag: str, partei, mit_rechtsform: bool = False):
    """
    Eine Handelspartei. Die Reihenfolge ist vom Schema vorgegeben:
    Name → Rechtsform → Kontakt → Adresse → Kommunikation → Steuernummer.
    """
    p = _sub(eltern, "ram", tag)
    _sub(p, "ram", "Name", partei.name or "")

    if mit_rechtsform and (partei.firmenbuchnummer or partei.firmensitz):
        org = _sub(p, "ram", "SpecifiedLegalOrganization")
        if partei.firmenbuchnummer:
            # schemeID 0195 wäre eine Kennung aus einem Register; ohne
            # gesicherte Zuordnung wird sie bewusst weggelassen statt geraten.
            _sub(org, "ram", "ID", partei.firmenbuchnummer)

    if partei.email:
        kontakt = _sub(p, "ram", "DefinedTradeContact")
        komm = _sub(kontakt, "ram", "EmailURIUniversalCommunication")
        _sub(komm, "ram", "URIID", partei.email, schemeID="SMTP")

    adresse = _sub(p, "ram", "PostalTradeAddress")
    if partei.plz:
        _sub(adresse, "ram", "PostcodeCode", partei.plz)
    if partei.strasse:
        _sub(adresse, "ram", "LineOne", partei.strasse)
    if partei.ort:
        _sub(adresse, "ram", "CityName", partei.ort)
    _sub(adresse, "ram", "CountryID", partei.land or "")

    if partei.email:
        komm = _sub(p, "ram", "URIUniversalCommunication")
        _sub(komm, "ram", "URIID", partei.email, schemeID="EM")

    if partei.uid:
        reg = _sub(p, "ram", "SpecifiedTaxRegistration")
        _sub(reg, "ram", "ID", partei.uid, schemeID="VA")
    return p


# ── Zeilen ────────────────────────────────────────────────────────────────────

def _zeile(eltern, zeile, kleinunternehmer: bool):
    pos = _sub(eltern, "ram", "IncludedSupplyChainTradeLineItem")

    dok = _sub(pos, "ram", "AssociatedDocumentLineDocument")
    _sub(dok, "ram", "LineID", zeile.nummer)

    produkt = _sub(pos, "ram", "SpecifiedTradeProduct")
    _sub(produkt, "ram", "Name", zeile.bezeichnung)
    if zeile.beschreibung:
        _sub(produkt, "ram", "Description", zeile.beschreibung)

    vereinbarung = _sub(pos, "ram", "SpecifiedLineTradeAgreement")
    preis = _sub(vereinbarung, "ram", "NetPriceProductTradePrice")
    _sub(preis, "ram", "ChargeAmount", _betrag(zeile.einzelpreis))

    lieferung = _sub(pos, "ram", "SpecifiedLineTradeDelivery")
    _sub(lieferung, "ram", "BilledQuantity", _menge(zeile.menge),
         unitCode=zeile.einheit_code or "C62")

    abrechnung = _sub(pos, "ram", "SpecifiedLineTradeSettlement")
    steuer = _sub(abrechnung, "ram", "ApplicableTradeTax")
    _sub(steuer, "ram", "TypeCode", "VAT")
    if kleinunternehmer:
        _sub(steuer, "ram", "CategoryCode", KATEGORIE_BEFREIT)
        _sub(steuer, "ram", "RateApplicablePercent", _prozent(0))
    elif zeile.steuersatz is None:
        _sub(steuer, "ram", "CategoryCode", KATEGORIE_REVERSE_CHARGE)
        _sub(steuer, "ram", "RateApplicablePercent", _prozent(0))
    else:
        _sub(steuer, "ram", "CategoryCode", "S")
        _sub(steuer, "ram", "RateApplicablePercent", _prozent(zeile.steuersatz))

    summe = _sub(abrechnung, "ram", "SpecifiedTradeSettlementLineMonetarySummation")
    _sub(summe, "ram", "LineTotalAmount", _betrag(zeile.netto))


# ── Ganzes Dokument ───────────────────────────────────────────────────────────

def erzeugen(daten: ERechnung) -> bytes:
    """Baut das CII-XML und gibt es als UTF-8-Bytes zurück."""
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)

    wurzel = ET.Element(_q("rsm", "CrossIndustryInvoice"))

    # ── Kontext: Nach welcher Leitlinie ist das hier gebaut? ─────────────────
    kontext = _sub(wurzel, "rsm", "ExchangedDocumentContext")
    leitlinie = _sub(kontext, "ram", "GuidelineSpecifiedDocumentContextParameter")
    _sub(leitlinie, "ram", "ID", PROFIL)

    # ── Kopf ────────────────────────────────────────────────────────────────
    kopf = _sub(wurzel, "rsm", "ExchangedDocument")
    _sub(kopf, "ram", "ID", daten.nummer)
    _sub(kopf, "ram", "TypeCode", daten.typ_code)
    _datum(kopf, ("ram", "IssueDateTime"), daten.datum)
    if daten.hinweis:
        notiz = _sub(kopf, "ram", "IncludedNote")
        _sub(notiz, "ram", "Content", daten.hinweis)

    transaktion = _sub(wurzel, "rsm", "SupplyChainTradeTransaction")

    kleinunternehmer = any(s.kategorie == KATEGORIE_BEFREIT for s in daten.steuern)
    for zeile in daten.zeilen:
        _zeile(transaktion, zeile, kleinunternehmer)

    # ── Vereinbarung: wer mit wem ───────────────────────────────────────────
    vereinbarung = _sub(transaktion, "ram", "ApplicableHeaderTradeAgreement")
    if daten.referenz:
        _sub(vereinbarung, "ram", "BuyerReference", daten.referenz)
    _partei(vereinbarung, "SellerTradeParty", daten.verkaeufer, mit_rechtsform=True)
    _partei(vereinbarung, "BuyerTradeParty", daten.empfaenger)

    # ── Lieferung ───────────────────────────────────────────────────────────
    lieferung = _sub(transaktion, "ram", "ApplicableHeaderTradeDelivery")
    if daten.leistungsdatum:
        ereignis = _sub(lieferung, "ram", "ActualDeliverySupplyChainEvent")
        _datum(ereignis, ("ram", "OccurrenceDateTime"), daten.leistungsdatum)

    # ── Abrechnung ──────────────────────────────────────────────────────────
    abrechnung = _sub(transaktion, "ram", "ApplicableHeaderTradeSettlement")
    _sub(abrechnung, "ram", "InvoiceCurrencyCode", daten.waehrung)

    zahlung = _sub(abrechnung, "ram", "SpecifiedTradeSettlementPaymentMeans")
    _sub(zahlung, "ram", "TypeCode",
         ZAHLUNGSART_UEBERWEISUNG if daten.zahlung.iban else ZAHLUNGSART_UNBESTIMMT)
    if daten.zahlung.iban:
        konto = _sub(zahlung, "ram", "PayeePartyCreditorFinancialAccount")
        _sub(konto, "ram", "IBANID", daten.zahlung.iban)
        if daten.zahlung.kontoinhaber:
            _sub(konto, "ram", "AccountName", daten.zahlung.kontoinhaber)
        if daten.zahlung.bic:
            institut = _sub(zahlung, "ram", "PayeeSpecifiedCreditorFinancialInstitution")
            _sub(institut, "ram", "BICID", daten.zahlung.bic)

    # Steuer je Satz. Reihenfolge innerhalb des Blocks ist vorgegeben:
    # Betrag → Art → Begründung → Grundlage → Kategorie → Satz.
    for s in daten.steuern:
        st = _sub(abrechnung, "ram", "ApplicableTradeTax")
        _sub(st, "ram", "CalculatedAmount", _betrag(s.steuer))
        _sub(st, "ram", "TypeCode", "VAT")
        grund = BEFREIUNGSGRUND.get(s.kategorie)
        if grund:
            _sub(st, "ram", "ExemptionReason", grund)
        _sub(st, "ram", "BasisAmount", _betrag(s.netto))
        _sub(st, "ram", "CategoryCode", s.kategorie)
        _sub(st, "ram", "RateApplicablePercent", _prozent(s.satz))

    # Abschläge auf Belegebene (Rabatt, Abzug gestellter Anzahlungen)
    for a in daten.abschlaege:
        ab = _sub(abrechnung, "ram", "SpecifiedTradeAllowanceCharge")
        anzeiger = _sub(ab, "ram", "ChargeIndicator")
        _sub(anzeiger, "udt", "Indicator", "false")     # false = Abschlag
        _sub(ab, "ram", "ActualAmount", _betrag(a.betrag))
        if a.grund:
            _sub(ab, "ram", "Reason", a.grund)
        kat = _sub(ab, "ram", "CategoryTradeTax")
        _sub(kat, "ram", "TypeCode", "VAT")
        _sub(kat, "ram", "CategoryCode", a.kategorie)
        _sub(kat, "ram", "RateApplicablePercent", _prozent(a.steuersatz))

    # Zahlungsbedingungen
    if daten.zahlung.faellig or daten.zahlung.skonto_prozent:
        bedingungen = _sub(abrechnung, "ram", "SpecifiedTradePaymentTerms")
        if daten.zahlung.skonto_prozent and daten.zahlung.skonto_tage:
            _sub(bedingungen, "ram", "Description",
                 f"{_prozent(daten.zahlung.skonto_prozent)} % Skonto bei Zahlung "
                 f"binnen {daten.zahlung.skonto_tage} Tagen")
        _datum(bedingungen, ("ram", "DueDateDateTime"), daten.zahlung.faellig)

    # Summen. Die Reihenfolge ist ebenfalls vorgegeben.
    summe = _sub(abrechnung, "ram",
                 "SpecifiedTradeSettlementHeaderMonetarySummation")
    _sub(summe, "ram", "LineTotalAmount", _betrag(daten.zeilen_gesamt))
    _sub(summe, "ram", "ChargeTotalAmount", _betrag(0))
    _sub(summe, "ram", "AllowanceTotalAmount", _betrag(daten.abschlag_gesamt))
    _sub(summe, "ram", "TaxBasisTotalAmount", _betrag(daten.netto_gesamt))
    _sub(summe, "ram", "TaxTotalAmount", _betrag(daten.steuer_gesamt),
         currencyID=daten.waehrung)
    _sub(summe, "ram", "GrandTotalAmount", _betrag(daten.brutto_gesamt))
    _sub(summe, "ram", "DuePayableAmount", _betrag(daten.zahlbetrag))

    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        wurzel, encoding="utf-8", xml_declaration=False)


def dateiname() -> str:
    """
    Der Name, unter dem das XML im PDF liegen muss.

    Nicht frei wählbar: Ein Empfänger sucht genau diese Datei. ZUGFeRD 2.x und
    Factur-X verwenden beide ``factur-x.xml``.
    """
    return "factur-x.xml"
