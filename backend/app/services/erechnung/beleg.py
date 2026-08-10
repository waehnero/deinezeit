"""
Der Weg vom gespeicherten Beleg zur E-Rechnung.

Diese Schicht kennt als einzige die Datenbank. ``datensatz``, ``facturx`` und
``pdf_anhang`` arbeiten mit reinen Werten und lassen sich deshalb ohne
Datenbank prüfen — was die Tests deutlich schärfer macht.
"""
import json

from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceSettings
from app.services.erechnung import datensatz as datensatz_service
from app.services.erechnung import facturx


# Einstellung: Ist die E-Rechnung eingeschaltet?
AKTIV_KEY = "erechnung_aktiv"

# Belegarten, für die eine E-Rechnung überhaupt Sinn ergibt. Ein Angebot ist
# keine Rechnung — ein Empfänger, der es als solche verarbeitet, verbucht eine
# Forderung, die es nicht gibt.
BELEGARTEN = ("rechnung", "gutschrift")


def ist_aktiv(db: Session) -> bool:
    """
    Vorgabe ist **aus**. Eine E-Rechnung ändert das Dateiformat jedes
    versendeten Belegs; das gehört bewusst eingeschaltet und nicht
    stillschweigend übernommen.
    """
    eintrag = db.query(InvoiceSettings).filter_by(key=AKTIV_KEY).first()
    if not eintrag or eintrag.value in (None, ""):
        return False
    wert = eintrag.value
    if isinstance(wert, str):
        try:
            wert = json.loads(wert)
        except Exception:
            return wert.strip().lower() in ("true", "1", "ja")
    return bool(wert)


def _bank(inv_settings: dict, verkaeufer_kontakt) -> dict:
    """
    Bankverbindung — bevorzugt aus dem Firmenkontakt, sonst aus den
    Belegeinstellungen. Dieselbe Reihenfolge wie in der PDF-Fußzeile, damit
    auf Beleg und im XML dieselbe IBAN steht.
    """
    daten = (getattr(verkaeufer_kontakt, "data", None) or {}) if verkaeufer_kontakt else {}
    treffer = {}
    for schluessel, wert in daten.items():
        k = str(schluessel).lower()
        text = str(wert or "").strip()
        if not text:
            continue
        if "iban" in k:
            treffer.setdefault("iban", text)
        elif "bic" in k or "swift" in k:
            treffer.setdefault("bic", text)
        elif "bank" in k:
            treffer.setdefault("bank", text)

    aus_einstellungen = inv_settings.get("bank", {})
    if isinstance(aus_einstellungen, str):
        try:
            aus_einstellungen = json.loads(aus_einstellungen)
        except Exception:
            aus_einstellungen = {}
    for feld in ("iban", "bic", "bank"):
        if not treffer.get(feld) and aus_einstellungen.get(feld):
            treffer[feld] = str(aus_einstellungen[feld]).strip()
    return treffer


def aufbereiten(invoice: Invoice, inv_settings: dict,
                verkaeufer_kontakt, empfaenger_kontakt):
    """Gibt ``(datensatz, fehlende_angaben)`` zurück."""
    daten = datensatz_service.aus_beleg(
        invoice, verkaeufer_kontakt, empfaenger_kontakt,
        bank=_bank(inv_settings, verkaeufer_kontakt))
    return daten, datensatz_service.pruefen(daten, invoice)


def pruefen(invoice: Invoice, inv_settings: dict,
            verkaeufer_kontakt, empfaenger_kontakt) -> list:
    """Nur die Liste der fehlenden Angaben."""
    if invoice.doc_type not in BELEGARTEN:
        return [f"Für diese Belegart gibt es keine E-Rechnung — nur "
                f"Rechnungen und Gutschriften werden elektronisch übermittelt."]
    _, fehlt = aufbereiten(invoice, inv_settings, verkaeufer_kontakt, empfaenger_kontakt)
    return fehlt


def xml_erzeugen(invoice: Invoice, inv_settings: dict,
                 verkaeufer_kontakt, empfaenger_kontakt,
                 trotz_luecken: bool = False):
    """
    Gibt ``(xml_bytes, fehlende_angaben)`` zurück.

    Fehlt etwas, ist ``xml_bytes`` ``None`` — es sei denn, der Aufrufer will
    die Datei ausdrücklich trotzdem sehen. Genau dafür gibt es
    ``trotz_luecken``: Beim Einrichten hilft es sehr, die halbfertige Datei
    anzuschauen; verschicken darf man sie nicht.
    """
    daten, fehlt = aufbereiten(invoice, inv_settings, verkaeufer_kontakt,
                               empfaenger_kontakt)
    if fehlt and not trotz_luecken:
        return None, fehlt
    return facturx.erzeugen(daten), fehlt


def xml_fuer_pdf(db: Session, invoice: Invoice, inv_settings: dict,
                 verkaeufer_kontakt, empfaenger_kontakt):
    """
    Das XML zum Einbetten — oder ``None``, wenn es hier nichts einzubetten gibt.

    Bewusst still: Ist die E-Rechnung aus, der Beleg ein Angebot oder fehlt
    eine Pflichtangabe, entsteht einfach das gewohnte PDF. Ein Fehler an dieser
    Stelle würde den Belegdruck lahmlegen — und ein Ausdruck muss immer
    funktionieren, auch wenn die Stammdaten unvollständig sind.
    """
    if not ist_aktiv(db):
        return None
    if invoice.doc_type not in BELEGARTEN:
        return None
    if not invoice.number:
        return None                      # Entwurf: noch keine Rechnung
    try:
        xml, fehlt = xml_erzeugen(invoice, inv_settings, verkaeufer_kontakt,
                                  empfaenger_kontakt)
        return None if fehlt else xml
    except Exception as e:                                   # pragma: no cover
        print(f"[WARN] E-Rechnung für {invoice.number} nicht erzeugbar: {e}")
        return None
