"""
Mahnwesen (C-1).

Der Ablauf ist bewusst **zweistufig**: Der Mahnlauf ermittelt nur, *was* mahnbar
wäre; verschickt wird erst auf Klick. Eine automatisch rausgegangene Mahnung an
einen Kunden, dessen Zahlung bloß noch nicht erfasst war, kostet mehr Vertrauen
als der Vorgang an Zeit spart.

Drei Regeln, die den Rest bestimmen:

1. **Mahngebühr und Verzugszinsen sind kein Umsatz.** Beides ist Schadenersatz
   und nicht umsatzsteuerbar. Sie werden deshalb nie zu Belegpositionen, sondern
   ausschließlich am Mahndatensatz geführt — sonst liefen sie in Erlös, UVA und
   Buchungsjournal und würden die Umsatzsteuer verfälschen.

2. **Die Mahnung ist kein Beleg im Sinne des § 11 UStG.** Sie bekommt daher
   keine Belegnummer aus dem Rechnungsnummernkreis, sondern nur eine Stufe.

3. **Der Zinssatz wird nicht geraten.** Ist der Basiszinssatz nicht gepflegt,
   werden keine Verzugszinsen berechnet und der Mahnlauf sagt das deutlich.
   Ein ausgedachter Satz auf einem Mahnschreiben ist schlimmer als keiner.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.core import zeit


# ── Vorgaben ─────────────────────────────────────────────────────────────────
#
# ``days_after`` ist bei Stufe 1 die Wartezeit **nach Fälligkeit**, ab Stufe 2
# die Wartezeit **nach der vorigen Mahnung**. ``grace_days`` ist die im
# Schreiben gesetzte Nachfrist.
DEFAULT_LEVELS = [
    {"level": 1, "label": "Zahlungserinnerung", "days_after": 7,  "grace_days": 7,
     "fee": "0", "interest": False,
     "text": "Vermutlich ist es Ihrer Aufmerksamkeit entgangen — die unten "
             "angeführte Rechnung ist noch offen. Sollte sich Ihre Zahlung mit "
             "diesem Schreiben überschnitten haben, betrachten Sie es bitte als "
             "gegenstandslos."},
    {"level": 2, "label": "1. Mahnung", "days_after": 14, "grace_days": 7,
     "fee": "5", "interest": True,
     "text": "Auf unsere Zahlungserinnerung haben wir keinen Zahlungseingang "
             "feststellen können. Wir ersuchen Sie, den offenen Betrag binnen "
             "der genannten Frist zu begleichen."},
    {"level": 3, "label": "2. Mahnung", "days_after": 14, "grace_days": 7,
     "fee": "15", "interest": True,
     "text": "Trotz mehrmaliger Aufforderung ist der offene Betrag nicht bei uns "
             "eingegangen. Wir ersuchen Sie letztmalig um Begleichung binnen der "
             "genannten Frist."},
    {"level": 4, "label": "Letzte Mahnung", "days_after": 14, "grace_days": 7,
     "fee": "30", "interest": True,
     "text": "Sie sind mit der Zahlung erheblich in Verzug. Sollte der offene "
             "Betrag nicht fristgerecht eingehen, werden wir die Forderung ohne "
             "weitere Ankündigung an ein Inkassobüro bzw. unsere Rechtsvertretung "
             "übergeben."},
]

# Verzugszinsen. B2B: 9,2 Prozentpunkte über dem Basiszinssatz (§ 456 UGB).
# B2C: 4 % gesetzlich (§ 1000 ABGB) — dort gibt es keinen Aufschlag.
DEFAULT_AUFSCHLAG_B2B = Decimal("9.2")
DEFAULT_ZINS_B2C = Decimal("4.0")

# Der Basiszinssatz wird halbjährlich von der OeNB veröffentlicht und ändert
# sich. Er gehört deshalb in die Einstellungen und NICHT in den Code — ein hier
# fest eingetragener Wert wäre nach spätestens sechs Monaten falsch.
BASISZINSSATZ_KEY = "dunning_base_rate"

CENT = Decimal("0.01")


def _dec(wert, vorgabe="0") -> Decimal:
    try:
        return Decimal(str(wert if wert is not None else vorgabe))
    except Exception:
        return Decimal(vorgabe)


# ── Einstellungen ────────────────────────────────────────────────────────────

def get_levels(db) -> list:
    """
    Mahnstufen aus den Verkaufseinstellungen, sonst die Vorgaben.

    Unvollständige Einträge werden aus der Vorgabe der gleichen Stufe ergänzt,
    damit eine halb ausgefüllte Konfiguration den Mahnlauf nicht kippt.
    """
    from app.models.invoice import InvoiceSettings
    row = db.query(InvoiceSettings).filter_by(key="dunning_levels").first()
    roh = row.value if (row is not None and isinstance(row.value, list)) else None
    if not roh:
        return [dict(s) for s in DEFAULT_LEVELS]

    vorgabe = {s["level"]: s for s in DEFAULT_LEVELS}
    stufen = []
    for i, eintrag in enumerate(roh, start=1):
        if not isinstance(eintrag, dict):
            continue
        stufe = int(eintrag.get("level") or i)
        basis = dict(vorgabe.get(stufe, DEFAULT_LEVELS[-1]))
        basis.update({k: v for k, v in eintrag.items() if v is not None})
        basis["level"] = stufe
        stufen.append(basis)
    stufen.sort(key=lambda s: s["level"])
    return stufen or [dict(s) for s in DEFAULT_LEVELS]


def get_zins_einstellungen(db) -> dict:
    """
    Zinsparameter. ``basiszinssatz`` ist ``None``, solange nichts gepflegt ist —
    dann werden bewusst keine Zinsen berechnet.
    """
    from app.models.invoice import InvoiceSettings
    werte = {r.key: r.value for r in db.query(InvoiceSettings).filter(
        InvoiceSettings.key.in_([BASISZINSSATZ_KEY, "dunning_surcharge_b2b",
                                 "dunning_rate_b2c", "dunning_interest_mode"])).all()}

    basis = werte.get(BASISZINSSATZ_KEY)
    return {
        "basiszinssatz": _dec(basis) if basis not in (None, "") else None,
        "aufschlag_b2b": _dec(werte.get("dunning_surcharge_b2b"), str(DEFAULT_AUFSCHLAG_B2B)),
        "zins_b2c": _dec(werte.get("dunning_rate_b2c"), str(DEFAULT_ZINS_B2C)),
        # auto | b2b | b2c — bei "auto" entscheidet die UID des Kunden
        "modus": (werte.get("dunning_interest_mode") or "auto"),
    }


def jahreszinssatz(zins_conf: dict, ist_unternehmen: bool):
    """
    Anzuwendender Jahreszinssatz in Prozent — oder ``None``, wenn er sich
    mangels gepflegtem Basiszinssatz nicht bestimmen lässt.
    """
    modus = zins_conf.get("modus") or "auto"
    b2b = ist_unternehmen if modus == "auto" else (modus == "b2b")
    if not b2b:
        return zins_conf.get("zins_b2c")          # fixer gesetzlicher Satz
    basis = zins_conf.get("basiszinssatz")
    if basis is None:
        return None
    return basis + zins_conf.get("aufschlag_b2b", DEFAULT_AUFSCHLAG_B2B)


def zinsbetrag(offen: Decimal, von: date, bis: date, jahressatz) -> Decimal:
    """
    Verzugszinsen für den Zeitraum, taggenau nach actual/365.

    Gerechnet wird auf den offenen **Brutto**betrag ab dem Tag nach Fälligkeit.
    Mahngebühren bleiben außen vor — auf Schadenersatz laufen keine Zinsen.
    """
    if jahressatz is None or not von or not bis:
        return Decimal("0.00")
    tage = (bis - von).days
    if tage <= 0 or offen <= 0:
        return Decimal("0.00")
    betrag = offen * _dec(jahressatz) / Decimal("100") * Decimal(tage) / Decimal("365")
    return betrag.quantize(CENT, rounding=ROUND_HALF_UP)


# ── Mahnbarkeit ──────────────────────────────────────────────────────────────

MAHNBARE_STATUS = ("gesendet", "offen", "teilbezahlt", "ueberfaellig")


def naechste_stufe(invoice, stufen: list):
    """Die Stufe, die als nächste dran wäre — oder ``None``, wenn ausgereizt."""
    erreicht = int(invoice.dunning_level or 0)
    for s in stufen:
        if s["level"] > erreicht:
            return s
    return None


def mahnbar_ab(invoice, stufe: dict) -> date:
    """
    Datum, ab dem diese Stufe verschickt werden darf.

    Stufe 1 zählt ab Fälligkeit, jede weitere ab der vorigen Mahnung. Ohne
    Zahlungsziel gibt es keinen Verzug — dann ist der Beleg nicht mahnbar.
    """
    wartezeit = timedelta(days=int(stufe.get("days_after") or 0))
    if int(invoice.dunning_level or 0) == 0:
        if not invoice.due_date:
            return None
        return invoice.due_date + wartezeit
    if not invoice.dunning_last_at:
        # Stufe gesetzt, aber kein Datum: aus einer Datenkorrektur. Lieber ab
        # Fälligkeit rechnen als gar nicht mahnen.
        return (invoice.due_date + wartezeit) if invoice.due_date else None
    return invoice.dunning_last_at + wartezeit


def sperrgrund(invoice, kontakt_gesperrt: bool):
    """Warum dieser Beleg nicht gemahnt wird — oder ``None``."""
    if invoice.dunning_blocked:
        return invoice.dunning_block_reason or "Mahnsperre am Beleg"
    if kontakt_gesperrt:
        return "Mahnsperre beim Kunden"
    return None


def ist_unternehmen(kontakt) -> bool:
    """
    B2B oder B2C? Entschieden wird an der UID des Kunden.

    Eine UID hat nur, wer unternehmerisch tätig ist — das ist das belastbarste
    Merkmal, das in den Stammdaten überhaupt vorliegt. Wer es anders braucht,
    stellt den Zinsmodus in den Einstellungen fest auf b2b oder b2c.
    """
    if kontakt is None:
        return True                      # Rechnungen ohne Kontakt sind Geschäftsfälle
    daten = getattr(kontakt, "data", None) or {}
    return bool(str(daten.get("uid") or "").strip())


def kontakt_gesperrt(kontakt) -> bool:
    daten = (getattr(kontakt, "data", None) or {}) if kontakt is not None else {}
    wert = daten.get("mahnsperre")
    return str(wert).lower() in ("true", "1", "ja", "yes") if wert is not None else False


# ── Mahnlauf ─────────────────────────────────────────────────────────────────

def kandidaten(db, stichtag: date = None, contact_id=None) -> dict:
    """
    Alle überfälligen Belege mit der jeweils nächsten Mahnstufe.

    Zurück kommen bewusst **auch** die nicht mahnbaren (gesperrt, Wartezeit
    noch nicht um, Stufen ausgereizt) — mit Begründung. Eine Liste, die nur
    zeigt, was gerade geht, lässt den Anwender im Unklaren darüber, warum eine
    Rechnung fehlt, die er erwartet hätte.
    """
    from app.models.invoice import Invoice
    from app.models.masterdata import EntityRecord
    from app.api.invoice import _zahlstand

    heute = stichtag or zeit.heute()
    stufen = get_levels(db)
    zins_conf = get_zins_einstellungen(db)

    q = db.query(Invoice).filter(
        Invoice.doc_type == "rechnung",
        Invoice.is_recurring_template.is_(False),
        Invoice.status.in_(MAHNBARE_STATUS),
        Invoice.due_date.isnot(None),
        Invoice.due_date < heute,
    )
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    belege = q.order_by(Invoice.due_date.asc()).all()

    kontakt_map = {}
    ids = list({b.contact_id for b in belege if b.contact_id})
    if ids:
        for r in db.query(EntityRecord).filter(EntityRecord.id.in_(ids)).all():
            kontakt_map[r.id] = r

    zeilen, ohne_zinssatz = [], False
    for b in belege:
        _, offen, _ = _zahlstand(b)
        if abs(offen) < Decimal("0.01") or offen < 0:
            continue                       # beglichen oder überzahlt

        kontakt = kontakt_map.get(b.contact_id)
        stufe = naechste_stufe(b, stufen)
        ab = mahnbar_ab(b, stufe) if stufe else None
        grund = sperrgrund(b, kontakt_gesperrt(kontakt))
        if grund is None and stufe is None:
            grund = "Alle Mahnstufen ausgeschöpft"
        elif grund is None and (ab is None or ab > heute):
            grund = (f"Frühestens ab {ab:%d.%m.%Y}" if ab
                     else "Kein Zahlungsziel hinterlegt")

        satz = jahreszinssatz(zins_conf, ist_unternehmen(kontakt)) if stufe else None
        zinsen = Decimal("0.00")
        if stufe and stufe.get("interest"):
            if satz is None:
                ohne_zinssatz = True
            zinsen = zinsbetrag(offen, b.due_date, heute, satz)

        zeilen.append({
            "invoice_id": b.id, "number": b.number, "date": b.date,
            "due_date": b.due_date, "title": b.title,
            "contact_id": b.contact_id,
            "contact_name": (kontakt.display_name if kontakt else None),
            "total": Decimal(str(b.total or 0)), "open_amount": offen,
            "days_overdue": (heute - b.due_date).days,
            "current_level": int(b.dunning_level or 0),
            "last_dunned_at": b.dunning_last_at,
            "next_level": (stufe or {}).get("level"),
            "next_label": (stufe or {}).get("label"),
            "fee": _dec((stufe or {}).get("fee")) if stufe else Decimal("0.00"),
            "interest": zinsen,
            "interest_rate": satz,
            "dunnable": grund is None,
            "reason": grund,
        })

    return {
        "stichtag": heute,
        "items": zeilen,
        "dunnable_count": sum(1 for z in zeilen if z["dunnable"]),
        "levels": stufen,
        # Sichtbarer Hinweis statt stiller Null: Ohne gepflegten Basiszinssatz
        # stünden auf dem Mahnschreiben 0,00 € Zinsen, ohne dass jemand merkt,
        # warum.
        "interest_hint": ("Der Basiszinssatz ist nicht gepflegt — es werden "
                          "keine Verzugszinsen berechnet. Nachzutragen in den "
                          "Verkaufseinstellungen." if ohne_zinssatz else None),
    }


def mahnung_anlegen(db, invoice, stufe: dict, stichtag: date = None,
                    benutzer: str = None, batch_id=None, kontakt=None):
    """
    Legt den Mahndatensatz an und hebt die Stufe am Beleg.

    Die Zinsen werden **kumuliert ab Fälligkeit** ausgewiesen, nicht nur seit
    der letzten Mahnung: Auf dem Schreiben steht der bis heute aufgelaufene
    Betrag, so wie es der Kunde nachrechnen können muss.
    """
    from app.models.invoice import InvoiceDunning
    from app.api.invoice import _zahlstand

    heute = stichtag or zeit.heute()
    _, offen, _ = _zahlstand(invoice)
    zins_conf = get_zins_einstellungen(db)
    satz = jahreszinssatz(zins_conf, ist_unternehmen(kontakt))
    zinsen = (zinsbetrag(offen, invoice.due_date, heute, satz)
              if stufe.get("interest") else Decimal("0.00"))
    frist = int(stufe.get("grace_days") or 0)

    eintrag = InvoiceDunning(
        invoice_id=invoice.id,
        level=int(stufe["level"]),
        label=stufe.get("label"),
        dunned_at=heute,
        due_date=heute + timedelta(days=frist) if frist else None,
        open_amount=offen,
        fee=_dec(stufe.get("fee")),
        interest=zinsen,
        interest_rate=satz if stufe.get("interest") else None,
        interest_days=((heute - invoice.due_date).days
                       if (stufe.get("interest") and invoice.due_date) else None),
        batch_id=batch_id,
        created_by=benutzer,
    )
    db.add(eintrag)
    invoice.dunning_level = int(stufe["level"])
    invoice.dunning_last_at = heute
    db.flush()
    return eintrag


def gesamtforderung(eintrag) -> Decimal:
    """Offener Betrag plus Gebühr plus Zinsen — der Betrag im Mahnschreiben."""
    return (_dec(eintrag.open_amount) + _dec(eintrag.fee)
            + _dec(eintrag.interest)).quantize(CENT)
