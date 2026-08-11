"""
Tests für die E-Rechnung (C-5) — ZUGFeRD 2.5 / Factur-X, Profil EN 16931.

**Was diese Tests leisten und was nicht.** Sie prüfen, dass die Struktur
stimmt, die Beträge aufgehen und nichts geraten wird. Sie können *nicht*
feststellen, ob die Datei einer echten Konformitätsprüfung standhält — das
entscheidet ein Validator gegen Schema und Schematron. Wer sich hier grüne
Tests als „konform" auslegt, täuscht sich.

Der teuerste Fehler wäre eine Datei, die gültig aussieht und falsche Zahlen
trägt. Deshalb der Schwerpunkt auf zwei Fragen:

  * Ergibt Zeilensumme minus Abschläge die Bemessungsgrundlage — und stimmt
    die mit dem gedruckten Beleg überein?
  * Wird irgendwo etwas geraten, wo es nicht bekannt ist (Mengeneinheit,
    Ländercode, UID)?

Schema analog zu test_verkauf_anzahlung.py.
"""
from decimal import Decimal
from xml.etree import ElementTree as ET

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import InvoiceSettings
from app.services.erechnung import einheiten, datensatz as ds, facturx
from app.services.erechnung import beleg as beleg_service


NS = facturx.NS


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _kontakt(db, name, daten):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=name, data=daten)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


VOLLSTAENDIGER_EMPFAENGER = {
    "adresse": "Ringstraße 9", "plz": "1010", "ort": "Wien", "land": "AT",
    "uid": "ATU22222222", "email": "buero@bauherr.at",
}
VOLLSTAENDIGER_ABSENDER = {
    "adresse": "Hauptstraße 1", "plz": "5020", "ort": "Salzburg",
    "land": "Österreich", "uid": "ATU11111111", "email": "office@waehner.at",
    "firmenbuchnummer": "FN 123456a", "firmensitz": "Salzburg",
    "iban": "AT61 1904 3002 3457 3201", "bic": "BKAUATWW",
}


def _firma_einrichten(db):
    """Firmenkontakt anlegen und als Absender hinterlegen."""
    from app.models.settings import Setting
    firma = _kontakt(db, "Waehner Bau GmbH", VOLLSTAENDIGER_ABSENDER)
    eintrag = db.query(Setting).filter_by(key="company_contact_id").first()
    if eintrag:
        eintrag.value = str(firma.id)
    else:
        db.add(Setting(key="company_contact_id", value=str(firma.id)))
    db.commit()
    return firma


def _create(client, contact_id, **extra):
    payload = {
        "doc_type": extra.pop("doc_type", "rechnung"),
        "contact_id": str(contact_id) if contact_id else None,
        "title": "Sanierung Dachgeschoss",
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "reference": extra.pop("reference", "AUFTRAG-42"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Bauleistung", "quantity": "1",
            "unit": "Stk", "unit_price": "1000", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ausstellen(client, invoice_id, status="offen"):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _pruefung(client, invoice_id):
    resp = client.get(f"/api/invoices/{invoice_id}/erechnung/pruefen")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _xml(client, invoice_id, trotz_luecken=False):
    resp = client.get(f"/api/invoices/{invoice_id}/erechnung/xml",
                      params={"trotz_luecken": trotz_luecken})
    assert resp.status_code == 200, resp.text
    return ET.fromstring(resp.content)


def _text(wurzel, pfad):
    treffer = wurzel.find(pfad, NS)
    return treffer.text if treffer is not None else None


# ── Einheiten ─────────────────────────────────────────────────────────────────

def test_gaengige_einheiten_werden_uebersetzt():
    assert einheiten.code("Stk") == "C62"
    assert einheiten.code("h") == "HUR"
    assert einheiten.code("Std.") == "HUR"
    assert einheiten.code("m²") == "MTK"
    assert einheiten.code("lfm") == "MTR"
    assert einheiten.code("kg") == "KGM"


def test_leere_einheit_ist_stueck():
    """„Ohne Einheit" ist eine Angabe, keine Lücke — EN 16931 verlangt einen Code."""
    assert einheiten.code("") == "C62"
    assert einheiten.code(None) == "C62"


def test_unbekannte_einheit_wird_nicht_geraten():
    """
    Der Kern: Ein Rückfall auf „Stück" würde aus 12 Stunden still 12 Stück
    machen. Die Datei wäre formal gültig und inhaltlich falsch.
    """
    assert einheiten.code("Kübel") is None
    assert einheiten.unbekannte(["Stk", "Kübel", "h", "Sack", "Kübel"]) == ["Kübel", "Sack"]


# ── Aufbau des XML ────────────────────────────────────────────────────────────

def test_leitlinie_und_belegart(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    x = _xml(auth_client, rechnung["id"])
    assert _text(x, "rsm:ExchangedDocumentContext/"
                    "ram:GuidelineSpecifiedDocumentContextParameter/ram:ID") \
        == "urn:cen.eu:en16931:2017"
    assert _text(x, "rsm:ExchangedDocument/ram:TypeCode") == "380"
    assert _text(x, "rsm:ExchangedDocument/ram:ID") == rechnung["number"]


def test_gutschrift_bekommt_die_eigene_belegart(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    gs = _ausstellen(auth_client,
                     _create(auth_client, kontakt.id, doc_type="gutschrift")["id"])
    x = _xml(auth_client, gs["id"])
    assert _text(x, "rsm:ExchangedDocument/ram:TypeCode") == "381"


def test_parteien_stehen_vollstaendig_im_xml(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    x = _xml(auth_client, rechnung["id"])
    basis = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement"

    assert _text(x, f"{basis}/ram:SellerTradeParty/ram:Name") == "Waehner Bau GmbH"
    assert _text(x, f"{basis}/ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID") \
        == "ATU11111111"
    assert _text(x, f"{basis}/ram:BuyerTradeParty/ram:Name") == "Bauherr GmbH"
    assert _text(x, f"{basis}/ram:BuyerTradeParty/ram:PostalTradeAddress/ram:CityName") == "Wien"
    assert _text(x, f"{basis}/ram:BuyerReference") == "AUFTRAG-42"


def test_land_wird_in_einen_code_uebersetzt(auth_client, db_session):
    """„Österreich" ist ein Land, kein Ländercode."""
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    x = _xml(auth_client, rechnung["id"])
    assert _text(x, "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/"
                    "ram:SellerTradeParty/ram:PostalTradeAddress/ram:CountryID") == "AT"


def test_zeile_traegt_menge_einheit_und_satz(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Regiestunden", "quantity": "12",
         "unit": "Std.", "unit_price": "85", "tax_rate": "20"},
    ])["id"])

    x = _xml(auth_client, rechnung["id"])
    zeile = x.find("rsm:SupplyChainTradeTransaction/"
                   "ram:IncludedSupplyChainTradeLineItem", NS)
    menge = zeile.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
    assert menge.get("unitCode") == "HUR"
    assert Decimal(menge.text) == Decimal("12")
    assert _text(zeile, "ram:SpecifiedTradeProduct/ram:Name") == "Regiestunden"
    assert Decimal(_text(zeile, "ram:SpecifiedLineTradeSettlement/"
                                "ram:SpecifiedTradeSettlementLineMonetarySummation/"
                                "ram:LineTotalAmount")) == Decimal("1020.00")


def test_gliederungszeilen_werden_nicht_zu_positionen(auth_client, db_session):
    """Überschrift, Freitext und Zwischensumme sind keine Leistung."""
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "heading", "description": "Erdgeschoss", "quantity": "0",
         "unit_price": "0", "tax_rate": None},
        {"pos_type": "item", "description": "Estrich", "quantity": "1",
         "unit": "m²", "unit_price": "500", "tax_rate": "20"},
        {"pos_type": "text", "description": "Materialliste liegt bei", "quantity": "0",
         "unit_price": "0", "tax_rate": None},
        {"pos_type": "subtotal", "description": "Zwischensumme", "quantity": "0",
         "unit_price": "0", "tax_rate": None},
    ])["id"])

    x = _xml(auth_client, rechnung["id"])
    zeilen = x.findall("rsm:SupplyChainTradeTransaction/"
                       "ram:IncludedSupplyChainTradeLineItem", NS)
    assert len(zeilen) == 1
    assert _text(zeilen[0], "ram:SpecifiedTradeProduct/ram:Name") == "Estrich"


# ── Die Summen müssen aufgehen ────────────────────────────────────────────────

def _summen(x):
    pfad = ("rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement/"
            "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    block = x.find(pfad, NS)
    return {kind.tag.split("}")[1]: Decimal(kind.text) for kind in block}


def test_summen_gehen_auf(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Bauleistung", "quantity": "1",
         "unit": "Stk", "unit_price": "8000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung", "quantity": "1",
         "unit": "Stk", "unit_price": "2000", "tax_rate": "13"},
    ])["id"])

    s = _summen(_xml(auth_client, rechnung["id"]))
    assert s["LineTotalAmount"] == Decimal("10000.00")
    assert s["AllowanceTotalAmount"] == Decimal("0.00")
    assert s["TaxBasisTotalAmount"] == Decimal("10000.00")
    assert s["TaxTotalAmount"] == Decimal("1860.00")      # 1600 + 260
    assert s["GrandTotalAmount"] == Decimal("11860.00")
    assert s["DuePayableAmount"] == Decimal("11860.00")
    # Die Probe, auf die es ankommt
    assert s["LineTotalAmount"] - s["AllowanceTotalAmount"] == s["TaxBasisTotalAmount"]
    assert s["TaxBasisTotalAmount"] + s["TaxTotalAmount"] == s["GrandTotalAmount"]


def test_summen_stimmen_mit_dem_beleg_ueberein(auth_client, db_session):
    """
    ZUGFeRD verlangt, dass PDF und XML dasselbe sagen. Die Summen werden
    deshalb vom Beleg übernommen und nicht ein zweites Mal gerechnet.
    """
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Position A", "quantity": "3",
         "unit": "Stk", "unit_price": "33.33", "tax_rate": "20"},
        {"pos_type": "item", "description": "Position B", "quantity": "7",
         "unit": "h", "unit_price": "81.50", "tax_rate": "20"},
    ])["id"])

    s = _summen(_xml(auth_client, rechnung["id"]))
    assert s["TaxBasisTotalAmount"] == Decimal(rechnung["subtotal"])
    assert s["TaxTotalAmount"] == Decimal(rechnung["tax_total"])
    assert s["GrandTotalAmount"] == Decimal(rechnung["total"])


def test_rabatt_wird_zum_abschlag_auf_belegebene(auth_client, db_session):
    """
    Ein Gruppenrabatt verteilt sich anteilig auf die Sätze seiner Gruppe. Als
    eigene Zeile wäre er eine Leistung; als Abschlag mindert er die Grundlage —
    genauso wie auf dem PDF.
    """
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Bauleistung", "quantity": "1",
         "unit": "Stk", "unit_price": "10000", "tax_rate": "20"},
        {"pos_type": "discount", "description": "Nachlass", "quantity": "1",
         "unit_price": "1000", "tax_rate": None},
    ])["id"])

    x = _xml(auth_client, rechnung["id"])
    zeilen = x.findall("rsm:SupplyChainTradeTransaction/"
                       "ram:IncludedSupplyChainTradeLineItem", NS)
    assert len(zeilen) == 1, "Der Rabatt darf keine Leistungszeile sein"

    abschlag = x.find("rsm:SupplyChainTradeTransaction/"
                      "ram:ApplicableHeaderTradeSettlement/"
                      "ram:SpecifiedTradeAllowanceCharge", NS)
    assert _text(abschlag, "ram:ChargeIndicator/udt:Indicator") == "false"
    assert Decimal(_text(abschlag, "ram:ActualAmount")) == Decimal("1000.00")
    assert Decimal(_text(abschlag, "ram:CategoryTradeTax/"
                                   "ram:RateApplicablePercent")) == Decimal("20.00")

    s = _summen(x)
    assert s["LineTotalAmount"] == Decimal("10000.00")
    assert s["AllowanceTotalAmount"] == Decimal("1000.00")
    assert s["TaxBasisTotalAmount"] == Decimal("9000.00")


def test_anzahlungsabzug_mindert_die_grundlage(auth_client, db_session):
    """
    Der Fall, an dem ich mich fast vertan hätte: ``TotalPrepaidAmount`` mindert
    nur den Zahlbetrag, nicht die Grundlage. In DeineZeit mindert der Abzug
    aber die Grundlage — sonst stünde im XML mehr Steuer als auf dem Beleg.
    """
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    angebot = _create(auth_client, kontakt.id, doc_type="angebot", positions=[
        {"pos_type": "item", "description": "Gesamtleistung", "quantity": "1",
         "unit": "Stk", "unit_price": "10000", "tax_rate": "20"}])
    anzahlung = auth_client.post(f"/api/invoices/{angebot['id']}/anzahlung",
                                 json={"percent": "30"}).json()
    _ausstellen(auth_client, anzahlung["id"])
    schluss = auth_client.post(f"/api/invoices/{angebot['id']}/schlussrechnung",
                               json={"from_invoice_id": angebot["id"]}).json()
    schluss = _ausstellen(auth_client, schluss["id"])

    x = _xml(auth_client, schluss["id"])
    s = _summen(x)
    assert s["LineTotalAmount"] == Decimal("10000.00")
    assert s["AllowanceTotalAmount"] == Decimal("3000.00")
    assert s["TaxBasisTotalAmount"] == Decimal("7000.00")
    assert s["TaxTotalAmount"] == Decimal("1400.00")     # NICHT 2000
    assert s["GrandTotalAmount"] == Decimal("8400.00")
    # …und deckungsgleich mit dem gedruckten Beleg
    assert s["GrandTotalAmount"] == Decimal(schluss["total"])


def test_steuer_je_satz_getrennt(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Bauleistung", "quantity": "1",
         "unit": "Stk", "unit_price": "8000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung", "quantity": "1",
         "unit": "Stk", "unit_price": "2000", "tax_rate": "13"},
    ])["id"])

    x = _xml(auth_client, rechnung["id"])
    bloecke = x.findall("rsm:SupplyChainTradeTransaction/"
                        "ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", NS)
    je_satz = {Decimal(_text(b, "ram:RateApplicablePercent")):
               (Decimal(_text(b, "ram:BasisAmount")), Decimal(_text(b, "ram:CalculatedAmount")))
               for b in bloecke}
    assert je_satz[Decimal("20.00")] == (Decimal("8000.00"), Decimal("1600.00"))
    assert je_satz[Decimal("13.00")] == (Decimal("2000.00"), Decimal("260.00"))


def test_kleinunternehmer_ohne_steuer_mit_begruendung(auth_client, db_session):
    """Fehlt die Begründung, ist für den Empfänger nicht erkennbar, warum."""
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id,
                                                tax_mode="kleinunternehmer")["id"])

    x = _xml(auth_client, rechnung["id"])
    block = x.find("rsm:SupplyChainTradeTransaction/"
                   "ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax", NS)
    assert _text(block, "ram:CategoryCode") == "E"
    assert Decimal(_text(block, "ram:CalculatedAmount")) == Decimal("0.00")
    assert "Kleinunternehmer" in _text(block, "ram:ExemptionReason")


def test_bankverbindung_kommt_mit(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    x = _xml(auth_client, rechnung["id"])
    zahlung = x.find("rsm:SupplyChainTradeTransaction/"
                     "ram:ApplicableHeaderTradeSettlement/"
                     "ram:SpecifiedTradeSettlementPaymentMeans", NS)
    assert _text(zahlung, "ram:TypeCode") == "58"
    # Leerzeichen aus der Eingabe dürfen nicht in der IBAN landen
    assert _text(zahlung, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID") \
        == "AT611904300234573201"


# ── Vollständigkeit ───────────────────────────────────────────────────────────

def test_fehlende_angaben_werden_alle_auf_einmal_gemeldet(auth_client, db_session):
    """Wer die Lücken schließt, will die Liste — nicht das erste Problem."""
    kontakt = _kontakt(db_session, "Nackter Kontakt", {})
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    stand = _pruefung(auth_client, rechnung["id"])
    assert stand["moeglich"] is False
    text = " ".join(stand["fehlende_angaben"])
    assert "UID" in text
    assert "Straße" in text
    assert len(stand["fehlende_angaben"]) >= 4


def test_unbekannte_einheit_verhindert_die_erechnung(auth_client, db_session):
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Schotter", "quantity": "3",
         "unit": "Kübel", "unit_price": "50", "tax_rate": "20"}])["id"])

    stand = _pruefung(auth_client, rechnung["id"])
    assert stand["moeglich"] is False
    text = " ".join(stand["fehlende_angaben"])
    assert "Mengeneinheiten" in text and "Kübel" in text


def test_unvollstaendige_erechnung_wird_nicht_ausgeliefert(auth_client, db_session):
    kontakt = _kontakt(db_session, "Nackter Kontakt", {})
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    resp = auth_client.get(f"/api/invoices/{rechnung['id']}/erechnung/xml")
    assert resp.status_code == 409


def test_beim_einrichten_darf_man_trotzdem_hineinsehen(auth_client, db_session):
    """Die halbfertige Datei hilft beim Einrichten — verschicken darf man sie nicht."""
    kontakt = _kontakt(db_session, "Nackter Kontakt", {})
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    resp = auth_client.get(f"/api/invoices/{rechnung['id']}/erechnung/xml",
                           params={"trotz_luecken": True})
    assert resp.status_code == 200
    assert b"CrossIndustryInvoice" in resp.content


def test_angebot_hat_keine_erechnung(auth_client, db_session):
    """
    Ein Angebot als Rechnung zu übermitteln hieße, beim Empfänger eine
    Forderung zu buchen, die es nicht gibt.
    """
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    angebot = _create(auth_client, kontakt.id, doc_type="angebot")

    stand = _pruefung(auth_client, angebot["id"])
    assert stand["moeglich"] is False
    resp = auth_client.get(f"/api/invoices/{angebot['id']}/erechnung/xml")
    assert resp.status_code == 400


# ── Der Schalter ──────────────────────────────────────────────────────────────

def test_erechnung_ist_ab_werk_aus(auth_client, db_session):
    """
    Sie ändert das Dateiformat jedes versendeten Belegs. Das gehört
    eingeschaltet, nicht stillschweigend übernommen.
    """
    assert beleg_service.ist_aktiv(db_session) is False
    daten = auth_client.get("/api/invoices/settings/all").json()
    assert daten["erechnung_aktiv"] is False


def test_schalter_wirkt(auth_client, db_session):
    db_session.add(InvoiceSettings(key=beleg_service.AKTIV_KEY, value=True))
    db_session.commit()
    assert beleg_service.ist_aktiv(db_session) is True


def test_entwurf_bekommt_keine_erechnung(auth_client, db_session):
    """Ein Entwurf hat keine Nummer — ohne Nummer keine Rechnung."""
    _firma_einrichten(db_session)
    db_session.add(InvoiceSettings(key=beleg_service.AKTIV_KEY, value=True))
    db_session.commit()
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    entwurf = _create(auth_client, kontakt.id)

    from app.models.invoice import Invoice
    inv = db_session.query(Invoice).filter(Invoice.id == entwurf["id"]).first()
    assert beleg_service.xml_fuer_pdf(db_session, inv, {}, None, None) is None


# ── Der Datensatz für sich ────────────────────────────────────────────────────

def test_pdf_bleibt_ohne_erechnung_unveraendert(auth_client, db_session):
    """
    Ohne eingeschaltete E-Rechnung entsteht weiter ein gewöhnliches PDF. Ein
    stiller Wechsel aller Ausdrucke des Hauses auf PDF/A wäre eine Änderung,
    die niemand bestellt hat.
    """
    _firma_einrichten(db_session)
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    resp = auth_client.get(f"/api/invoices/{rechnung['id']}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert b"factur-x.xml" not in _pdf_inhalt(resp.content)


def _pdf_inhalt(roh: bytes) -> bytes:
    """
    PDF-Bytes samt entpackter Ströme.

    Nötig, weil WeasyPrint komprimiert schreibt: Ab PDF 1.5 wandern alle
    Objekte, die keine Ströme sind — also auch der Katalog und der
    Dateieintrag —, in einen komprimierten Objektstrom. Wer im Rohtext nach
    ``/AFRelationship`` sucht, findet nichts und schließt daraus fälschlich,
    die Angabe fehle. Genau darauf bin ich beim ersten Anlauf hereingefallen:
    Der Test war rot, obwohl der Code stimmte.
    """
    import re
    import zlib
    teile = [roh]
    for treffer in re.finditer(rb"stream\r?\n", roh):
        start = treffer.end()
        ende = roh.find(b"endstream", start)
        if ende == -1:
            continue
        try:
            teile.append(zlib.decompress(roh[start:ende]))
        except zlib.error:
            pass                      # unkomprimiert oder anders kodiert
    return b"\n".join(teile)


def test_hybrides_pdf_traegt_das_xml(auth_client, db_session):
    """
    Die Probe auf das Ganze: eingeschaltet, vollständig — dann steckt das XML
    im PDF, samt der Kennzeichnung, an der ein Empfänger es findet.
    """
    _firma_einrichten(db_session)
    db_session.add(InvoiceSettings(key=beleg_service.AKTIV_KEY, value=True))
    db_session.commit()
    kontakt = _kontakt(db_session, "Bauherr GmbH", VOLLSTAENDIGER_EMPFAENGER)
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    resp = auth_client.get(f"/api/invoices/{rechnung['id']}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")

    inhalt = _pdf_inhalt(resp.content)
    assert b"factur-x.xml" in inhalt, "Die eingebettete Datei fehlt"
    assert b"CrossIndustryInvoice" in inhalt, "Das XML selbst fehlt"
    assert rechnung["number"].encode() in inhalt, "Die Belegnummer steht nicht im XML"
    assert b"/AFRelationship /Data" in inhalt, "Ohne diese Angabe ist es eine Beilage"
    assert b"Factur-X PDFA Extension Schema" in inhalt, "Erweiterungsschema im XMP fehlt"
    # Die /AF-Liste im Katalog. Bewusst mit Klammer geprüft: „/AF" allein
    # steckt auch in „/AFRelationship" — ein Test darauf wäre wertlos.
    import re
    assert re.search(rb"/AF\s*\[", inhalt), "Die /AF-Liste im Katalog fehlt"
    # PDF/A-3: Ohne die Kennung ist es ein gewöhnliches PDF mit Beilage.
    assert b"pdfaid:part" in inhalt and b"3" in inhalt


def test_unvollstaendiger_beleg_bekommt_ein_gewoehnliches_pdf(auth_client, db_session):
    """
    Der Belegdruck muss immer funktionieren. Fehlt eine Pflichtangabe, geht das
    gewohnte PDF hinaus statt eines Fehlers — sonst legt eine Lücke in den
    Stammdaten den ganzen Verkauf lahm.
    """
    db_session.add(InvoiceSettings(key=beleg_service.AKTIV_KEY, value=True))
    db_session.commit()
    kontakt = _kontakt(db_session, "Nackter Kontakt", {})
    rechnung = _ausstellen(auth_client, _create(auth_client, kontakt.id)["id"])

    resp = auth_client.get(f"/api/invoices/{rechnung['id']}/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert b"factur-x.xml" not in _pdf_inhalt(resp.content)


def test_xml_ist_wohlgeformt_und_deklariert_utf8():
    daten = ds.ERechnung(nummer="RE-1", waehrung="EUR")
    roh = facturx.erzeugen(daten)
    assert roh.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    ET.fromstring(roh)          # wirft, wenn nicht wohlgeformt


def test_dateiname_ist_nicht_frei_waehlbar():
    """Ein Empfänger sucht genau diese Datei."""
    assert facturx.dateiname() == "factur-x.xml"
