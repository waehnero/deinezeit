"""
Steuersätze — zentral gepflegt statt an drei Stellen hartkodiert.

Bisher steckten die Sätze fest verdrahtet
  * im Positions-Dropdown des Belegformulars (20 / 10 / 0 / RC),
  * in der USt-Code-Tabelle des BMD-Exports und
  * implizit in der MwSt.-Aufschlüsselung des PDF.

Ein Umsatz zu **13 %** (Beherbergung, Kultur, Ab-Hof-Verkauf, lebende Tiere)
ließ sich dadurch gar nicht erfassen — und wäre im Export still als 20 %
gebucht worden, weil die Code-Tabelle auf ``U20`` zurückfiel.

Gespeichert wird unter dem InvoiceSettings-Schlüssel ``tax_rates`` als Liste:

    [{"satz": 20, "bezeichnung": "Normalsatz", "ust_code": "U20",
      "aktiv": True, "standard": True}, ...]

Der USt-Code ist bewusst mitpflegbar: BMD-Codes sind kanzleiabhängig, ein fest
verdrahtetes ``U13`` wäre bei der nächsten Kanzlei wieder falsch.

**Reverse Charge ist kein Steuersatz**, sondern das Fehlen eines Satzes
(``tax_rate = NULL``) und daher nicht Teil dieser Liste — der Code dafür steht
in :data:`REVERSE_CHARGE_CODE`.
"""
from decimal import Decimal, InvalidOperation


# Österreichische Sätze als Vorgabe (§ 10 UStG).
#
# uva_kz = Kennzahl im Formular U30 (Umsatzsteuervoranmeldung). Belegt sind
# 022 (20 %), 029 (10 %) und 006 (13 %). Für steuerfreie Umsätze hängt die
# Kennzahl vom Sachverhalt ab — Ausfuhr, innergemeinschaftliche Lieferung und
# Reverse Charge laufen über verschiedene Kennzahlen. Das wird bewusst NICHT
# geraten, sondern bleibt leer und wird in der Auswertung als „nicht
# zugeordnet" ausgewiesen, bis die Steuerberatung es einträgt.
DEFAULT_TAX_RATES = [
    {"satz": 20, "bezeichnung": "Normalsatz",           "ust_code": "U20",
     "uva_kz": "022", "aktiv": True,  "standard": True},
    {"satz": 13, "bezeichnung": "Ermäßigt (13 %)",      "ust_code": "U13",
     "uva_kz": "006", "aktiv": True,  "standard": False},
    {"satz": 10, "bezeichnung": "Ermäßigt (10 %)",      "ust_code": "U10",
     "uva_kz": "029", "aktiv": True,  "standard": False},
    {"satz": 0,  "bezeichnung": "Steuerfrei",           "ust_code": "U00",
     "uva_kz": "",    "aktiv": True,  "standard": False},
]

# Kennzahl für den Gesamtbetrag der Bemessungsgrundlage im Formular U30
UVA_KZ_GESAMT = "000"

# Steuerland der Firma (Settings-Schlüssel ``company_country``).
#
# Ausgebaut ist derzeit ausschließlich Österreich. Das Kennzeichen steht
# trotzdem schon da, damit die Meldelogik von Anfang an daran hängt statt an
# einer stillen Annahme — ein zweites Land wäre sonst ein Umbau quer durch das
# Modul. Andere Meldungen bedeuten andere Formulare, Kennzahlen, Fristen und
# Übermittlungswege (Deutschland z.B. ELSTER/ERiC mit Zertifikat).
DEFAULT_COUNTRY = "AT"
SUPPORTED_COUNTRIES = {"AT": "Österreich"}


def get_company_country(db) -> str:
    """Steuerland der Firma; Vorgabe Österreich."""
    from app.models.settings import Setting
    row = db.query(Setting).filter_by(key="company_country").first()
    wert = (row.value or "").strip().upper() if row else ""
    return wert or DEFAULT_COUNTRY

REVERSE_CHARGE_CODE = "URC"

SETTINGS_KEY = "tax_rates"


def _normalisieren(eintrag) -> dict | None:
    """
    Macht aus einem gespeicherten Eintrag einen brauchbaren Satz — oder None.

    Der Schlüssel ``tax_rates`` lag in Bestandsinstallationen bereits in der
    Datenbank, ohne dass ihn je Code gelesen hätte. Sein Inhalt ist damit
    unbekannt, deshalb wird hier defensiv geprüft statt vertraut.
    """
    if not isinstance(eintrag, dict):
        return None
    try:
        satz = Decimal(str(eintrag.get("satz")))
    except (InvalidOperation, TypeError):
        return None
    if satz < 0 or satz > 100:
        return None

    satz_text = str(int(satz)) if satz == int(satz) else str(satz)
    # uva_kz bewusst OHNE Rückfall: Eine geratene Kennzahl wäre schlimmer als
    # keine — sie landet ungeprüft in der Voranmeldung.
    return {
        "satz": satz,
        "bezeichnung": str(eintrag.get("bezeichnung") or f"{satz_text} %"),
        "ust_code": str(eintrag.get("ust_code") or f"U{satz_text.zfill(2)}"),
        "uva_kz": str(eintrag.get("uva_kz") or ""),
        "aktiv": bool(eintrag.get("aktiv", True)),
        "standard": bool(eintrag.get("standard", False)),
    }


def _mit_decimal(liste: list) -> list:
    """Vorgabewerte in dieselbe Form bringen wie gespeicherte Sätze."""
    return [_normalisieren(e) for e in liste]


def get_tax_rates(db, nur_aktive: bool = False) -> list:
    """
    Liefert die gepflegten Steuersätze, absteigend nach Prozentwert.

    Ist nichts hinterlegt oder ist der gespeicherte Wert unbrauchbar, gelten
    die Vorgabewerte. Es wird bewusst nichts geschrieben — die Einstellung
    entsteht erst, wenn sie jemand bewusst speichert.
    """
    from app.models.invoice import InvoiceSettings

    row = db.query(InvoiceSettings).filter_by(key=SETTINGS_KEY).first()
    saetze = []
    if row is not None and isinstance(row.value, list):
        saetze = [s for s in (_normalisieren(e) for e in row.value) if s]

    if not saetze:
        saetze = _mit_decimal(DEFAULT_TAX_RATES)

    if nur_aktive:
        saetze = [s for s in saetze if s["aktiv"]]
    return sorted(saetze, key=lambda s: s["satz"], reverse=True)


def as_json(saetze: list) -> list:
    """Decimal → Zahl, damit die Liste über die API gehen kann."""
    return [
        {**s, "satz": float(s["satz"]) if s["satz"] % 1 else int(s["satz"])}
        for s in saetze
    ]


def ust_code_for(saetze: list, rate) -> str:
    """
    USt-Code zu einem Steuersatz. ``rate = None`` bedeutet Reverse Charge.

    Ist der Satz nicht gepflegt, wird der Code aus dem Prozentwert gebildet
    (z.B. 7 % → ``U07``) statt auf den Normalsatz zurückzufallen. Ein falscher
    Code fällt beim Steuerberater auf — ein still auf 20 % gebuchter Umsatz
    nicht.
    """
    if rate is None:
        return REVERSE_CHARGE_CODE
    try:
        wert = Decimal(str(rate))
    except (InvalidOperation, TypeError):
        return REVERSE_CHARGE_CODE
    for s in saetze:
        if s["satz"] == wert:
            return s["ust_code"]
    text = str(int(wert)) if wert == int(wert) else str(wert)
    return f"U{text.zfill(2)}"


def standard_satz(saetze: list):
    """Der als Standard markierte Satz (oder der höchste aktive)."""
    aktive = [s for s in saetze if s["aktiv"]]
    if not aktive:
        return None
    for s in aktive:
        if s["standard"]:
            return s["satz"]
    return aktive[0]["satz"]
