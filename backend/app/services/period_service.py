"""
Monatsabschluss und Übergabe an die Steuerberatung.

Bisher gab es keinen Zeitpunkt, an dem ein Monat „zu" war: Nach der Übergabe
ließ sich jederzeit noch ein Beleg mit Datum in diesem Monat anlegen oder
ändern. Die übergebenen Zahlen stimmten danach nicht mehr mit dem System
überein, ohne dass irgendetwas gewarnt hätte.

Der Ablauf in vier Schritten:

  1. PRÜFEN        — :func:`pruefliste`: Was steht dem Abschluss im Weg?
  2. ABSCHLIESSEN  — :func:`abschliessen`: Monat sperren, Kennzahlen festhalten
  3. ÜBERGEBEN     — :func:`paket_bauen`: ein ZIP mit allem, was die
                     Steuerberatung braucht, samt Prüfsummen-Protokoll
  4. NACHWEISEN    — jede Übergabe bleibt als :class:`PeriodHandover` erhalten

Wiedereröffnen ist möglich, aber nur mit Begründung und ohne den Vorgang zu
verwischen.
"""
import hashlib
import io
import zipfile
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.period import AccountingPeriod, PeriodHandover


MONATSNAMEN = ["", "Jänner", "Februar", "März", "April", "Mai", "Juni",
               "Juli", "August", "September", "Oktober", "November", "Dezember"]


def monatsgrenzen(jahr: int, monat: int) -> tuple:
    """Erster und letzter Tag des Monats."""
    if not 1 <= monat <= 12:
        raise HTTPException(400, f"Ungültiger Monat: {monat}")
    return date(jahr, monat, 1), date(jahr, monat, monthrange(jahr, monat)[1])


def get_period(db: Session, jahr: int, monat: int):
    return (db.query(AccountingPeriod)
            .filter_by(year=jahr, month=monat).first())


def ist_gesperrt(db: Session, tag: date) -> bool:
    """Liegt dieses Datum in einem abgeschlossenen Monat?"""
    if not tag:
        return False
    p = get_period(db, tag.year, tag.month)
    return bool(p and p.ist_gesperrt)


def pruefe_periode_offen(db: Session, tag: date, vorgang: str = "geändert") -> None:
    """
    Wirft 400, wenn das Datum in einem abgeschlossenen Monat liegt.

    Wird beim Anlegen, Bearbeiten und Finalisieren von Belegen aufgerufen.
    Zahlungen bleiben bewusst außen vor — sie ändern nichts am Belegjournal
    des abgeschlossenen Monats.
    """
    if not ist_gesperrt(db, tag):
        return
    raise HTTPException(
        400,
        f"{MONATSNAMEN[tag.month]} {tag.year} ist abgeschlossen und an die "
        f"Buchhaltung übergeben — Belege aus diesem Monat können nicht mehr "
        f"{vorgang} werden. Ein Admin kann den Monat mit Begründung wieder "
        f"öffnen.",
    )


# ── Schritt 1: Prüfen ─────────────────────────────────────────────────────────

def pruefliste(db: Session, jahr: int, monat: int) -> dict:
    """
    Was steht dem Abschluss im Weg?

    ``blockierend`` verhindert den Abschluss, ``hinweis`` nicht — ein fehlendes
    Erlöskonto ist zwar unschön, aber der Standard greift und die Buchung
    stimmt trotzdem.
    """
    from app.services import tax_rates as tax_rates_service

    von, bis = monatsgrenzen(jahr, monat)
    im_monat = db.query(Invoice).filter(Invoice.date >= von, Invoice.date <= bis,
                                        Invoice.is_recurring_template.is_(False))

    punkte = []

    entwuerfe = im_monat.filter(Invoice.status == "entwurf").all()
    punkte.append({
        "schluessel": "entwuerfe",
        "titel": "Offene Entwürfe",
        "art": "blockierend",
        "erfuellt": not entwuerfe,
        "anzahl": len(entwuerfe),
        "text": ("Keine offenen Entwürfe." if not entwuerfe else
                 f"{len(entwuerfe)} Entwurf/Entwürfe mit Datum in diesem Monat. "
                 "Entweder ausstellen oder löschen — ein Entwurf ist kein Beleg "
                 "und gehört nicht in die Übergabe."),
        "belege": [{"id": str(b.id), "titel": b.title or "(ohne Titel)"} for b in entwuerfe],
    })

    ohne_kontakt = im_monat.filter(Invoice.status != "entwurf",
                                   Invoice.contact_id.is_(None)).all()
    punkte.append({
        "schluessel": "ohne_kontakt",
        "titel": "Belege ohne Kontakt",
        "art": "hinweis",
        "erfuellt": not ohne_kontakt,
        "anzahl": len(ohne_kontakt),
        "text": ("Alle Belege haben einen Kontakt." if not ohne_kontakt else
                 f"{len(ohne_kontakt)} Beleg(e) ohne Kontakt — sie erscheinen im "
                 "Journal ohne Debitor und wurden nicht ins Datacenter archiviert."),
        "belege": [{"id": str(b.id), "titel": b.number or "(ohne Nummer)"} for b in ohne_kontakt],
    })

    # UID des Empfängers ab 10.000 € — Pflichtangabe, aber nicht bei jedem
    # Empfänger vorhanden (Privatpersonen haben keine). Daher Hinweis.
    from app.api.invoice import _uid_fehlt, UID_SCHWELLE
    ohne_uid = [b for b in im_monat.filter(Invoice.status != "entwurf").all()
                if _uid_fehlt(db, b)]
    punkte.append({
        "schluessel": "uid_fehlt",
        "titel": f"UID ab {float(UID_SCHWELLE):.0f} €",
        "art": "hinweis",
        "erfuellt": not ohne_uid,
        "anzahl": len(ohne_uid),
        "text": ("Keine Belege über der Schwelle ohne UID." if not ohne_uid else
                 f"{len(ohne_uid)} Beleg(e) über {float(UID_SCHWELLE):.0f} € ohne "
                 "UID des Empfängers. Bei unternehmerischen Empfängern ist sie "
                 "nach § 11 Abs. 1 Z 2 UStG Pflicht; Privatpersonen haben keine."),
        "belege": [{"id": str(b.id), "titel": b.number or "(ohne Nummer)"} for b in ohne_uid],
    })

    # Kennzahlen, die für die Umsatzsteuer-Aufstellung fehlen
    saetze = tax_rates_service.get_tax_rates(db)
    offene_kz = [s for s in saetze if s["aktiv"] and not s["uva_kz"]]
    punkte.append({
        "schluessel": "uva_kennzahlen",
        "titel": "UVA-Kennzahlen",
        "art": "hinweis",
        "erfuellt": not offene_kz,
        "anzahl": len(offene_kz),
        "text": ("Alle aktiven Steuersätze haben eine Kennzahl." if not offene_kz else
                 "Für " + ", ".join(s["bezeichnung"] for s in offene_kz) +
                 " ist keine UVA-Kennzahl hinterlegt. Die Beträge stimmen, die "
                 "Zuordnung im Formular fehlt."),
        "belege": [],
    })

    periode = get_period(db, jahr, monat)
    blockierer = [p for p in punkte if p["art"] == "blockierend" and not p["erfuellt"]]

    return {
        "jahr": jahr, "monat": monat,
        "monatsname": MONATSNAMEN[monat],
        "status": periode.status if periode else "offen",
        "abschluss_moeglich": not blockierer and (periode is None or not periode.ist_gesperrt),
        "punkte": punkte,
        "summen": _summen(db, jahr, monat),
    }


def _summen(db: Session, jahr: int, monat: int) -> dict:
    """Kennzahlen des Monats — dieselbe Abgrenzung wie im Verkaufsbuch."""
    von, bis = monatsgrenzen(jahr, monat)
    belege = (db.query(Invoice)
              .filter(Invoice.date >= von, Invoice.date <= bis,
                      Invoice.status != "entwurf",
                      Invoice.is_recurring_template.is_(False))
              .all())
    netto = sum((Decimal(str(b.subtotal or 0)) for b in belege), Decimal("0"))
    steuer = sum((Decimal(str(b.tax_total or 0)) for b in belege), Decimal("0"))
    brutto = sum((Decimal(str(b.total or 0)) for b in belege), Decimal("0"))
    return {"anzahl": len(belege), "netto": float(netto),
            "steuer": float(steuer), "brutto": float(brutto)}


# ── Schritt 2: Abschließen und Wiederöffnen ───────────────────────────────────

def abschliessen(db: Session, jahr: int, monat: int, benutzer: str) -> AccountingPeriod:
    liste = pruefliste(db, jahr, monat)
    if not liste["abschluss_moeglich"]:
        blocker = [p["text"] for p in liste["punkte"]
                   if p["art"] == "blockierend" and not p["erfuellt"]]
        raise HTTPException(400, " ".join(blocker) or "Der Monat ist bereits abgeschlossen.")

    periode = get_period(db, jahr, monat)
    if periode is None:
        periode = AccountingPeriod(year=jahr, month=monat)
        db.add(periode)

    periode.status = "abgeschlossen"
    periode.closed_at = datetime.now(timezone.utc)
    periode.closed_by = benutzer
    periode.totals = liste["summen"]
    db.commit()
    db.refresh(periode)
    return periode


def wieder_oeffnen(db: Session, jahr: int, monat: int, benutzer: str,
                   grund: str) -> AccountingPeriod:
    if not (grund or "").strip():
        raise HTTPException(400, "Zum Wiederöffnen ist eine Begründung nötig — "
                                 "sie bleibt am Monat dokumentiert.")
    periode = get_period(db, jahr, monat)
    if periode is None or not periode.ist_gesperrt:
        raise HTTPException(400, "Dieser Monat ist nicht abgeschlossen.")

    periode.status = "wieder_geoeffnet"
    periode.reopened_at = datetime.now(timezone.utc)
    periode.reopened_by = benutzer
    periode.reopen_reason = grund.strip()[:500]
    db.commit()
    db.refresh(periode)
    return periode


# ── Schritt 3: Übergabepaket ──────────────────────────────────────────────────

def _sicherer_name(text: str) -> str:
    return "".join(c for c in (text or "") if c.isalnum() or c in "._- ").strip() or "datei"


async def paket_bauen(db: Session, jahr: int, monat: int, benutzer) -> tuple:
    """
    Baut das Übergabe-ZIP und protokolliert die Übergabe.

    Inhalt:
      * ``buchungsjournal.csv``          — BMD-Buchungssätze (Verkauf)
      * ``buchungsjournal_eingang.csv``  — Buchungssätze der Eingangsrechnungen
      * ``belegjournal.pdf``             — Verkaufsbuch des Monats
      * ``umsatzsteuer.pdf``             — Umsatz- und Vorsteuerseite
      * ``offene_posten.csv``            — Forderungsstand zum Monatsletzten
      * ``belege/…pdf``                  — jeder ausgestellte Beleg als PDF
      * ``UEBERGABE.txt``                — Inhaltsverzeichnis mit SHA-256 je Datei

    Gibt ``(zip_bytes, handover)`` zurück.
    """
    import csv as csv_mod
    from app.api.invoice import (get_book_csv, get_book_pdf, get_uva_pdf,
                                 get_open_items, _load_pdf_context)
    from app.api.accounting import export_bmd, export_bmd_eingang
    from app.services.invoice_pdf import generate_pdf

    von, bis = monatsgrenzen(jahr, monat)
    dateien: dict = {}

    async def _rohdaten(antwort) -> bytes:
        """
        Rohbytes aus einer Antwort holen.

        Nötig, weil die wiederverwendeten Endpunkte zwei verschiedene Typen
        liefern: ``Response`` hat ``.body``, ``StreamingResponse`` (so gibt der
        BMD-Export zurück) dagegen nur einen asynchronen Iterator.
        """
        if hasattr(antwort, "body"):
            return antwort.body
        teile = []
        async for stueck in antwort.body_iterator:
            teile.append(stueck if isinstance(stueck, bytes) else str(stueck).encode("utf-8"))
        return b"".join(teile)

    async def sammle(name: str, aufruf):
        """Antwort eines Endpunkts als Datei aufnehmen; Fehler nicht verschlucken."""
        try:
            dateien[name] = await _rohdaten(await aufruf)
        except Exception as e:
            dateien[name.rsplit(".", 1)[0] + "_FEHLER.txt"] = (
                f"Diese Datei konnte nicht erzeugt werden:\n{e}\n"
            ).encode("utf-8")

    await sammle("buchungsjournal.csv",
                 export_bmd(date_from=von, date_to=bis, doc_type=None, db=db, _=benutzer))
    # Eingangsseite als eigene Datei — im Verkaufsjournal hießen die Spalten
    # „Erlöskonto" und „Debitornummer", was für Aufwand und Kreditoren falsch
    # wäre.
    await sammle("buchungsjournal_eingang.csv",
                 export_bmd_eingang(date_from=von, date_to=bis, db=db, _=benutzer))
    await sammle("belegjournal.pdf",
                 get_book_pdf(date_from=von, date_to=bis, doc_type=None, db=db, _=benutzer))
    await sammle("umsatzsteuer.pdf",
                 get_uva_pdf(date_from=von, date_to=bis, db=db, current_user=benutzer))
    await sammle("verkaufsbuch.csv",
                 get_book_csv(date_from=von, date_to=bis, doc_type=None, db=db, _=benutzer))

    # Offene Posten zum Monatsletzten
    try:
        op = await get_open_items(contact_id=None, stichtag=bis, db=db, _=benutzer)
        puffer = io.StringIO()
        schreiber = csv_mod.writer(puffer, delimiter=";")
        schreiber.writerow(["Nummer", "Datum", "Fällig", "Kontakt", "Gesamt",
                            "Bezahlt", "Offen", "Tage überfällig", "Status"])
        for p in op.items:
            schreiber.writerow([
                p.number or "", p.date.strftime("%d.%m.%Y"),
                p.due_date.strftime("%d.%m.%Y") if p.due_date else "",
                p.contact_name or "", f"{float(p.total):.2f}".replace(".", ","),
                f"{float(p.paid_total):.2f}".replace(".", ","),
                f"{float(p.open_amount):.2f}".replace(".", ","),
                p.days_overdue, p.status,
            ])
        dateien["offene_posten.csv"] = puffer.getvalue().encode("utf-8-sig")
    except Exception as e:
        dateien["offene_posten_FEHLER.txt"] = f"{e}\n".encode("utf-8")

    # Jeder ausgestellte Beleg als PDF
    belege = (db.query(Invoice)
              .filter(Invoice.date >= von, Invoice.date <= bis,
                      Invoice.status != "entwurf",
                      Invoice.is_recurring_template.is_(False))
              .order_by(Invoice.date, Invoice.number).all())
    for beleg in belege:
        name = f"belege/{_sicherer_name(beleg.number or str(beleg.id)[:8])}.pdf"
        try:
            s, i, absender, empfaenger = _load_pdf_context(db, beleg)
            dateien[name] = generate_pdf(beleg, beleg.positions, s, i, absender,
                                         empfaenger, db=db)
        except Exception as e:
            dateien[name.replace(".pdf", "_FEHLER.txt")] = f"{e}\n".encode("utf-8")

    # Inhaltsverzeichnis mit Prüfsummen — damit später nachweisbar ist, was drin war
    zeilen = [
        f"Übergabe an die Buchhaltung",
        f"Zeitraum:   {MONATSNAMEN[monat]} {jahr} ({von:%d.%m.%Y} – {bis:%d.%m.%Y})",
        f"Erstellt:   {datetime.now(timezone.utc):%d.%m.%Y %H:%M} UTC",
        f"Benutzer:   {getattr(benutzer, 'email', '—')}",
        f"Belege:     {len(belege)}",
        "",
        "HINWEIS: Dieses Paket enthält die Verkaufsseite. Eingangsrechnungen und",
        "Vorsteuer werden in DeineZeit nicht erfasst und sind gesondert beizubringen.",
        "",
        "Inhalt (SHA-256 je Datei):",
    ]
    for name in sorted(dateien):
        zeilen.append(f"  {hashlib.sha256(dateien[name]).hexdigest()}  {name}")
    dateien["UEBERGABE.txt"] = ("\n".join(zeilen) + "\n").encode("utf-8")

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(dateien):
            z.writestr(name, dateien[name])
    inhalt = puffer.getvalue()

    handover = PeriodHandover(
        year=jahr, month=monat, created_by=getattr(benutzer, "email", None),
        file_count=len(dateien), byte_size=len(inhalt),
        checksum=hashlib.sha256(inhalt).hexdigest(),
        note=f"{len(belege)} Belege, {MONATSNAMEN[monat]} {jahr}",
    )
    db.add(handover)
    db.commit()
    db.refresh(handover)
    return inhalt, handover
