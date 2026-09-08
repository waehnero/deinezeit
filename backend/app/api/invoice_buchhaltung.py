"""
Verkauf – Belegbuch, UVA, Offene Posten, Auswertungen (Modulrecht Buchhaltung).

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from uuid import UUID
from datetime import date
import logging
import io

from app.db.base import get_db
from app.api.deps import (get_current_user, require_modul_rechte)
from app.models.user import User
from app.models.invoice import Invoice
from app.models.settings import Setting
from app.models.masterdata import EntityRecord
from app.services import positionen as positionen_service
from app.services import skonto as skonto_service
from app.services import auswertungen as auswertungen_service
from app.schemas.invoice import (
    OpenItem, OpenItemsByContact, OpenItemsResponse,
    UvaZeile, UvaResponse,
    UmsatzJahrResponse, UmsatzKundeResponse, UmsatzArtikelResponse,
    AngebotsquoteResponse,
)
from app.core import zeit
from app.core.http import content_disposition

from app.api.invoice_common import (
    _zahlstand,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Belegbuch
# ─────────────────────────────────────────────────────────────────────────────

def _book_query(db: Session, date_from: Optional[date], date_to: Optional[date],
                doc_type: Optional[str]):
    """Gemeinsame Abfragelogik für Belegbuch-Endpoints."""
    q = db.query(Invoice).filter(Invoice.status != "entwurf")
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    return q.order_by(Invoice.date, Invoice.number)


@router.get("/book/list", dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_book_list(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch-Liste mit Summen."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    # Kontaktnamen gesammelt laden (statt einer Abfrage je Beleg) und den
    # gepflegten Anzeigenamen verwenden — die Keys 'name'/'firma' gibt es in
    # den Stammdaten-Feldern nicht, die Spalte blieb dadurch immer leer.
    contact_ids = list({inv.contact_id for inv in invoices if inv.contact_id})
    contact_map: dict = {}
    if contact_ids:
        for r in db.query(EntityRecord).filter(EntityRecord.id.in_(contact_ids)).all():
            contact_map[r.id] = r.display_name or ""

    rows = []
    for inv in invoices:
        contact_name = contact_map.get(inv.contact_id) if inv.contact_id else None
        rows.append({
            "id": str(inv.id),
            "number": inv.number,
            "doc_type": inv.doc_type,
            "date": inv.date.isoformat() if inv.date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "title": inv.title,
            "contact_name": contact_name,
            "subtotal": float(inv.subtotal or 0),
            "tax_total": float(inv.tax_total or 0),
            "total": float(inv.total or 0),
            "status": inv.status,
            "currency": inv.currency,
        })

    return {
        "invoices": rows,
        "summary": {
            "count": len(rows),
            "total_net": float(total_net),
            "total_tax": float(total_tax),
            "total_gross": float(total_gross),
        },
    }


@router.get("/book/csv", dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_book_csv(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als CSV-Download."""
    import csv as csv_mod
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    output = io.StringIO()
    writer = csv_mod.writer(output, delimiter=";")
    writer.writerow(["Nummer", "Typ", "Datum", "Fällig", "Titel", "Netto", "MwSt.", "Brutto", "Status"])

    for inv in invoices:
        writer.writerow([
            inv.number,
            inv.doc_type,
            inv.date.strftime("%d.%m.%Y") if inv.date else "",
            inv.due_date.strftime("%d.%m.%Y") if inv.due_date else "",
            inv.title or "",
            str(inv.subtotal or 0).replace(".", ","),
            str(inv.tax_total or 0).replace(".", ","),
            str(inv.total or 0).replace(".", ","),
            inv.status,
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=belegbuch.csv"},
    )


@router.get("/book/pdf", dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_book_pdf(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als PDF-Download."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    def fmt_date(d):
        return d.strftime("%d.%m.%Y") if d else "—"

    def fmt_eur(n):
        return f"{float(n):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    period_label = ""
    if date_from and date_to:
        period_label = f"{fmt_date(date_from)} – {fmt_date(date_to)}"
    elif date_from:
        period_label = f"ab {fmt_date(date_from)}"
    elif date_to:
        period_label = f"bis {fmt_date(date_to)}"
    else:
        period_label = "Alle Zeiträume"

    rows_html = ""
    for inv in invoices:
        status_map = {
            "offen": "Offen", "bezahlt": "Bezahlt", "ueberfaellig": "Überfällig",
            "storniert": "Storniert", "gesendet": "Gesendet",
            "angenommen": "Angenommen", "abgelehnt": "Abgelehnt",
        }
        rows_html += f"""
        <tr>
          <td>{inv.number}</td>
          <td>{fmt_date(inv.date)}</td>
          <td>{fmt_date(inv.due_date)}</td>
          <td>{inv.title or '—'}</td>
          <td class="r">{fmt_eur(inv.subtotal or 0)}</td>
          <td class="r">{fmt_eur(inv.tax_total or 0)}</td>
          <td class="r"><b>{fmt_eur(inv.total or 0)}</b></td>
          <td>{status_map.get(inv.status, inv.status)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }}
  h1 {{ font-size: 16px; margin-bottom: 4px; }}
  p.sub {{ color: #666; font-size: 10px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #f3f4f6; text-align: left; padding: 6px 8px; border-bottom: 2px solid #d1d5db; font-size: 10px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; }}
  .r {{ text-align: right; }}
  tfoot td {{ font-weight: bold; background: #f9fafb; border-top: 2px solid #d1d5db; }}
</style>
</head><body>
<h1>Belegbuch</h1>
<p class="sub">Zeitraum: {period_label} &nbsp;|&nbsp; {len(invoices)} Dokumente</p>
<table>
  <thead><tr>
    <th>Nummer</th><th>Datum</th><th>Fällig</th><th>Titel</th>
    <th class="r">Netto</th><th class="r">MwSt.</th><th class="r">Brutto</th><th>Status</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
  <tfoot><tr>
    <td colspan="4">Gesamt ({len(invoices)})</td>
    <td class="r">{fmt_eur(total_net)}</td>
    <td class="r">{fmt_eur(total_tax)}</td>
    <td class="r">{fmt_eur(total_gross)}</td>
    <td></td>
  </tr></tfoot>
</table>
</body></html>"""

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    except Exception as e:
        # Kein HTML-Rückfall mehr: Der Browser lud die Datei als
        # „belegbuch.pdf" herunter und bekam HTML — der Fehler fiel erst beim
        # Öffnen auf, und dann sah es nach einer kaputten Datei aus statt nach
        # einem Serverproblem.
        logger.exception("Fehler bei invoice: %s", e)
        raise HTTPException(500, "Das PDF konnte nicht erzeugt werden (Ursache im Serverlog).")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=belegbuch.pdf"},
    )


@router.get("/uva", response_model=UvaResponse,
            dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_uva(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Umsatzsteuer-Auswertung für die Voranmeldung (Formular U30).

    Liefert je Steuersatz die Bemessungsgrundlage und den Steuerbetrag, dazu
    die Kennzahl aus den Verkaufseinstellungen. Belegt sind 022 (20 %),
    029 (10 %) und 006 (13 %); für steuerfreie Umsätze hängt die Kennzahl vom
    Sachverhalt ab (Ausfuhr, innergemeinschaftliche Lieferung, Reverse Charge)
    und wird bewusst nicht geraten — solche Zeilen erscheinen mit dem Vermerk
    „Kennzahl nicht zugeordnet".

    Enthalten sind Rechnungen und Gutschriften, die ausgestellt und nicht
    storniert sind. Gutschriften mindern die Bemessungsgrundlage, weil ihre
    Beträge negativ geführt werden.

    **Das ist eine Aufbereitung, keine Steuerberatung.** Die Zuordnung von
    Sonderfällen gehört geprüft, bevor die Zahlen in die Voranmeldung gehen.
    """
    from decimal import Decimal
    from collections import defaultdict
    from app.services import tax_rates as tax_rates_service

    belege = _book_query(db, date_from, date_to, None).filter(
        Invoice.doc_type.in_(["rechnung", "gutschrift"]),
        Invoice.is_recurring_template == False,
        or_(Invoice.status != "storniert", Invoice.cancel_mode == "with_credit"),
    ).all()

    saetze = tax_rates_service.get_tax_rates(db)
    kz_je_satz = {s["satz"]: (s["uva_kz"], s["bezeichnung"]) for s in saetze}

    netto_je_satz: dict = defaultdict(lambda: Decimal("0"))
    rc_netto = Decimal("0")

    for beleg in belege:
        if beleg.tax_mode == "kleinunternehmer":
            # Unecht steuerbefreit: kein Satz, kein Steuerbetrag. Die
            # Bemessungsgrundlage ist die gespeicherte Nettosumme.
            netto_je_satz[Decimal("0")] += Decimal(str(beleg.subtotal or 0))
            continue
        # Über den Positionen-Dienst statt über eine eigene Schleife: Nur er
        # kennt die Gliederungszeilen und verteilt eine Rabattzeile anteilig
        # auf die Sätze ihrer Gruppe. Die frühere Schleife hier zählte einen
        # Rabatt mangels Steuersatz als Reverse-Charge-Umsatz — die
        # Bemessungsgrundlage war damit auf beiden Seiten falsch.
        for satz, netto in positionen_service.netto_je_satz(
                list(beleg.positions), beleg.tax_mode).items():
            if satz is None:
                rc_netto += netto            # Reverse Charge: kein Satz am Beleg
            else:
                netto_je_satz[Decimal(str(satz))] += netto

    # Skonto mindert das Entgelt im Monat der Zahlung (§ 16 UStG) — nicht im
    # Monat der Rechnung. Deshalb hängt die Korrektur am Zahlungsdatum und
    # kommt hier als eigener Posten dazu, statt den Beleg rückwirkend zu ändern.
    # Der Steuerbetrag wird weiter unten aus der Bemessungsgrundlage gerechnet;
    # die geminderte Grundlage ergibt damit automatisch die berichtigte Steuer.
    korrektur = skonto_service.korrektur_je_satz(db, date_from, date_to)
    skonto_gesamt = Decimal("0")
    for satz, wert in korrektur["netto"].items():
        if satz is None:
            rc_netto += wert
        else:
            netto_je_satz[Decimal(str(satz))] += wert
        skonto_gesamt += wert

    land = tax_rates_service.get_company_country(db)
    land_unterstuetzt = land in tax_rates_service.SUPPORTED_COUNTRIES

    zeilen, hinweise = [], []
    kz_gesamt = Decimal("0")
    steuer_gesamt = Decimal("0")

    if not land_unterstuetzt:
        hinweise.append(
            f"Als Steuerland ist „{land}“ eingestellt. Die Kennzahlen unten "
            f"stammen aus dem österreichischen Formular U30 und passen dann "
            f"nicht — die Beträge je Steuersatz stimmen, die Zuordnung nicht.")

    # Der frühere Vermerk „enthält nur die Umsatzseite" ist mit den
    # Eingangsrechnungen entfallen — die Vorsteuer kommt jetzt weiter unten
    # dazu. Der Vorbehalt bleibt trotzdem: Aufbereitung, keine Steuerberatung.
    hinweise.append(
        "Diese Auswertung ist eine Aufbereitung aus den erfassten Belegen. "
        "Sonderfälle gehören vor der Abgabe mit der Steuerberatung geprüft.")

    if skonto_gesamt:
        hinweise.append(
            f"Enthalten ist eine Entgeltminderung aus gewährten Skonti von "
            f"{float(-skonto_gesamt):.2f} netto (§ 16 UStG). Sie wirkt im "
            f"Monat der Zahlung — die zugehörigen Rechnungen können aus einem "
            f"früheren Zeitraum stammen.")

    for satz in sorted(netto_je_satz, reverse=True):
        netto = netto_je_satz[satz]
        steuer = (netto * satz / 100).quantize(Decimal("0.01"))
        kennzahl, bezeichnung = kz_je_satz.get(satz, ("", f"{satz} %"))
        zeilen.append(UvaZeile(
            kennzahl=kennzahl, bezeichnung=bezeichnung, satz=satz,
            bemessungsgrundlage=netto, steuer=steuer, zugeordnet=bool(kennzahl),
        ))
        kz_gesamt += netto
        steuer_gesamt += steuer
        if not kennzahl:
            hinweise.append(
                f"Für den Steuersatz {bezeichnung} ist keine UVA-Kennzahl "
                f"hinterlegt — bitte in den Verkaufseinstellungen ergänzen.")

    if rc_netto:
        zeilen.append(UvaZeile(
            kennzahl="", bezeichnung="Reverse Charge (Steuerschuld geht über)",
            satz=None, bemessungsgrundlage=rc_netto, steuer=Decimal("0"),
            zugeordnet=False,
        ))
        kz_gesamt += rc_netto
        hinweise.append(
            "Reverse-Charge-Umsätze laufen je nach Sachverhalt über "
            "unterschiedliche Kennzahlen (z.B. innergemeinschaftliche "
            "Lieferung oder Bauleistung). Die Zuordnung gehört mit der "
            "Steuerberatung geklärt.")

    # ── Vorsteuerseite aus den Eingangsrechnungen ────────────────────────────
    #
    # Bis Etappe 7 endete die Auswertung hier, mit dem Vermerk, dass die
    # Vorsteuer fehlt. Reverse Charge und innergemeinschaftlicher Erwerb
    # erzeugen dabei ZWEI Zeilen: die selbst geschuldete Steuer und — bei
    # Abzugsberechtigung — die gleich hohe Vorsteuer.
    from app.services import vorsteuer as vorsteuer_service
    vst = vorsteuer_service.auswertung(db, date_from, date_to)

    for z in vst["zeilen"]:
        zeilen.append(UvaZeile(
            kennzahl=z["kennzahl"], bezeichnung=z["bezeichnung"], satz=None,
            bemessungsgrundlage=z["grundlage"], steuer=z["betrag"],
            zugeordnet=z["zugeordnet"],
        ))
        # Selbst geschuldete Steuer erhöht die Zahllast, Vorsteuer mindert sie.
        # Die Bemessungsgrundlage der Umsatzseite (KZ 000) bleibt unberührt —
        # dort gehören nur eigene Umsätze hinein.
        steuer_gesamt += z["betrag"] if z["art"] == "steuerschuld" else -z["betrag"]

    hinweise.extend(vst["hinweise"])
    if vst["beleg_anzahl"] == 0:
        hinweise.append(
            "Im Zeitraum ist keine Eingangsrechnung erfasst — die Auswertung "
            "enthält damit keine Vorsteuer. Bitte prüfen, ob das stimmt.")

    return UvaResponse(
        date_from=date_from, date_to=date_to,
        country=land, country_supported=land_unterstuetzt, zeilen=zeilen,
        kz_000=kz_gesamt, steuer_gesamt=steuer_gesamt,
        beleg_anzahl=len(belege) + vst["beleg_anzahl"], hinweise=hinweise,
    )


@router.get("/uva/pdf", dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_uva_pdf(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Umsatzsteuer-Auswertung als Ausdruck, Zeile für Zeile nach dem Formular U30.

    Bewusst ein Ausdruck zum Abtippen und **keine** Übermittlung: DeineZeit
    erfasst keine Eingangsrechnungen, damit fehlt die gesamte Vorsteuerseite
    der Voranmeldung. Eine Meldung mit Vorsteuer null würde deutlich zu viel
    Umsatzsteuer ausweisen. Der Ausdruck sagt das an mehreren Stellen deutlich.
    """
    from app.services import tax_rates as tax_rates_service

    daten = get_uva(date_from=date_from, date_to=date_to, db=db, _=current_user)
    settings = {r.key: r.value for r in db.query(Setting).all()}
    firma = settings.get("company_name", "") or "—"
    land = tax_rates_service.SUPPORTED_COUNTRIES.get(daten.country, daten.country)

    def eur(n):
        return f"{float(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def dat(d):
        return d.strftime("%d.%m.%Y") if d else "—"

    zeitraum = (f"{dat(date_from)} – {dat(date_to)}" if (date_from or date_to)
                else "Alle Zeiträume")

    zeilen_html = ""
    for z in daten.zeilen:
        kz = z.kennzahl or '<span class="offen">nicht zugeordnet</span>'
        zeilen_html += f"""
        <tr>
          <td class="kz">{kz}</td>
          <td>{z.bezeichnung}</td>
          <td class="r">{eur(z.bemessungsgrundlage)}</td>
          <td class="r">{eur(z.steuer)}</td>
        </tr>"""

    hinweise_html = "".join(f"<li>{h}</li>" for h in daten.hinweise)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 2cm; }}
      body {{ font-family: Arial, sans-serif; font-size: 10.5pt; color: #222; }}
      h1 {{ font-size: 15pt; margin: 0 0 2px 0; }}
      .sub {{ color: #666; font-size: 9pt; margin-bottom: 18px; }}
      .warn {{ background: #fff4e5; border: 1px solid #f0c48a; border-radius: 4px;
               padding: 10px 12px; margin-bottom: 18px; font-size: 9pt; }}
      .warn b {{ display: block; margin-bottom: 3px; }}
      .warn ul {{ margin: 6px 0 0 16px; padding: 0; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
      th {{ background: #f3f4f6; text-align: left; padding: 6px 8px;
            border-bottom: 2px solid #d1d5db; font-size: 9pt; }}
      td {{ padding: 6px 8px; border-bottom: 1px solid #e5e7eb; }}
      .r {{ text-align: right; }}
      .kz {{ font-family: "Courier New", monospace; font-weight: bold; width: 3.5cm; }}
      .offen {{ color: #b45309; font-weight: normal; font-family: Arial; }}
      tfoot td {{ font-weight: bold; background: #f9fafb; border-top: 2px solid #d1d5db; }}
      .fuss {{ margin-top: 22px; font-size: 8pt; color: #777; line-height: 1.5; }}
    </style></head><body>
      <h1>Umsatzsteuer — Aufstellung der Umsätze</h1>
      <p class="sub">{firma} &nbsp;|&nbsp; Zeitraum: {zeitraum}
         &nbsp;|&nbsp; Steuerland: {land}
         &nbsp;|&nbsp; {daten.beleg_anzahl} Belege
         &nbsp;|&nbsp; erstellt am {zeit.heute():%d.%m.%Y}</p>

      <div class="warn">
        <b>Diese Aufstellung ist keine vollständige Umsatzsteuervoranmeldung.</b>
        Sie enthält ausschließlich die Umsatzseite. Vorsteuer (KZ 060),
        Einfuhrumsatzsteuer (KZ 061) und innergemeinschaftliche Erwerbe
        (KZ 070 ff.) werden in DeineZeit nicht erfasst und sind vor der Abgabe
        zu ergänzen. Die Kennzahlen folgen dem österreichischen Formular U30.
        {"<ul>" + hinweise_html + "</ul>" if hinweise_html else ""}
      </div>

      <table>
        <thead><tr>
          <th>Kennzahl</th><th>Bezeichnung</th>
          <th class="r">Bemessungsgrundlage</th><th class="r">Umsatzsteuer</th>
        </tr></thead>
        <tbody>{zeilen_html or '<tr><td colspan="4">Keine umsatzsteuerrelevanten Belege im Zeitraum.</td></tr>'}</tbody>
        <tfoot><tr>
          <td class="kz">000</td>
          <td>Gesamtbetrag der Bemessungsgrundlage</td>
          <td class="r">{eur(daten.kz_000)}</td>
          <td class="r">{eur(daten.steuer_gesamt)}</td>
        </tr></tfoot>
      </table>

      <p class="fuss">
        Aufbereitung aus den Verkaufsbelegen, keine Steuerberatung. Enthalten sind
        ausgestellte Rechnungen und Gutschriften; Entwürfe, Angebote,
        Auftragsbestätigungen und Lieferscheine bleiben unberücksichtigt.
        Stornierte Belege zählen nur mit, wenn eine Gutschrift dagegensteht.
        Die Zuordnung der Kennzahlen — besonders bei Ausfuhr, innergemeinschaftlichen
        Lieferungen und Reverse Charge — gehört mit der Steuerberatung geprüft.
      </p>
    </body></html>"""

    try:
        import weasyprint
        pdf = weasyprint.HTML(string=html).write_pdf()
    except Exception as e:
        logger.exception("Fehler bei invoice: %s", e)
        raise HTTPException(500, "Das PDF konnte nicht erzeugt werden (Ursache im Serverlog).")

    name = f"umsatzsteuer_{date_from or 'alle'}_{date_to or ''}".rstrip("_")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition("attachment", name + ".pdf")})


# ─────────────────────────────────────────────────────────────────────────────
# Offene Posten
#
# Muss VOR "/{invoice_id}" stehen, sonst schluckt die Detailroute den Pfad.
# ─────────────────────────────────────────────────────────────────────────────

# Fälligkeitsstaffel — die übliche Einteilung in Debitorenauswertungen
BUCKETS = [
    ("nicht_faellig", "Nicht fällig"),
    ("b1_30",         "1–30 Tage"),
    ("b31_60",        "31–60 Tage"),
    ("b61_90",        "61–90 Tage"),
    ("b90_plus",      "über 90 Tage"),
]


def _bucket_fuer(tage: int) -> str:
    if tage <= 0:
        return "nicht_faellig"
    if tage <= 30:
        return "b1_30"
    if tage <= 60:
        return "b31_60"
    if tage <= 90:
        return "b61_90"
    return "b90_plus"


@router.get("/open-items", response_model=OpenItemsResponse, dependencies=[Depends(require_modul_rechte("buchhaltung"))])
def get_open_items(
    contact_id: Optional[UUID] = Query(None),
    stichtag: Optional[date] = Query(None, description="Standard: heute"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Offene-Posten-Liste mit Fälligkeitsstaffel.

    Die Standardauswertung der Debitorenbuchhaltung: Welche ausgestellten
    Belege sind noch nicht (vollständig) beglichen, wie lange schon, und wie
    verteilt sich das auf die Kunden.

    Enthalten sind Rechnungen und Gutschriften, die ausgestellt und nicht
    storniert sind und bei denen noch etwas offen ist. Entwürfe, Angebote,
    Auftragsbestätigungen und Lieferscheine sind keine Forderungen.
    """
    from decimal import Decimal

    heute = stichtag or zeit.heute()

    q = db.query(Invoice).filter(
        Invoice.is_recurring_template == False,
        Invoice.doc_type.in_(["rechnung", "gutschrift"]),
        Invoice.status.notin_(["entwurf", "storniert"]),
    )
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    belege = q.order_by(Invoice.due_date.asc().nullslast(), Invoice.date.asc()).all()

    kontakt_ids = list({b.contact_id for b in belege if b.contact_id})
    kontakt_map = {}
    if kontakt_ids:
        for r in db.query(EntityRecord).filter(EntityRecord.id.in_(kontakt_ids)).all():
            kontakt_map[r.id] = r.display_name or ""

    items, summen_je_kontakt = [], {}
    buckets = {schluessel: Decimal("0") for schluessel, _ in BUCKETS}
    gesamt_offen = Decimal("0")

    for b in belege:
        gezahlt, offen, _ueber = _zahlstand(b)
        if abs(offen) < Decimal("0.01"):
            continue                      # beglichen — kein offener Posten

        tage = (heute - b.due_date).days if b.due_date else 0
        bucket = _bucket_fuer(tage)
        buckets[bucket] += offen
        gesamt_offen += offen

        eintrag = summen_je_kontakt.setdefault(
            b.contact_id, {"contact_id": b.contact_id,
                           "contact_name": kontakt_map.get(b.contact_id),
                           "open_amount": Decimal("0"), "count": 0})
        eintrag["open_amount"] += offen
        eintrag["count"] += 1

        items.append(OpenItem(
            id=b.id, number=b.number, doc_type=b.doc_type, date=b.date,
            due_date=b.due_date, contact_id=b.contact_id,
            contact_name=kontakt_map.get(b.contact_id), title=b.title,
            total=b.total, paid_total=gezahlt, open_amount=offen,
            status=b.status, days_overdue=max(0, tage), bucket=bucket,
        ))

    return OpenItemsResponse(
        items=items,
        by_contact=sorted(
            (OpenItemsByContact(**e) for e in summen_je_kontakt.values()),
            key=lambda e: abs(e.open_amount), reverse=True),
        buckets={k: float(v) for k, v in buckets.items()},
        total_open=gesamt_offen,
        count=len(items),
    )


# ── Auswertungen (C-15) ───────────────────────────────────────────────────────
#
# Alle vier hinter dem Modulrecht `buchhaltung`: Sie zeigen dieselben Zahlen
# wie Verkaufsbuch und UVA, nur anders geschnitten. Ein Recht, das dort greift
# und hier nicht, wäre über die Auswertung umgehbar.

AUSWERTUNG_RECHT = [Depends(require_modul_rechte("buchhaltung"))]


@router.get("/auswertung/umsatz-jahr", response_model=UmsatzJahrResponse,
            dependencies=AUSWERTUNG_RECHT)
def umsatz_je_monat(
    jahr: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Monatsumsatz eines Jahres mit Vorjahresvergleich."""
    return auswertungen_service.je_monat(db, jahr or zeit.jetzt().year)


@router.get("/auswertung/umsatz-kunden", response_model=UmsatzKundeResponse,
            dependencies=AUSWERTUNG_RECHT)
def umsatz_je_kunde(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(0, ge=0, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Rangliste der Kunden. ``limit=0`` gibt alle zurück."""
    return auswertungen_service.je_kunde(db, date_from, date_to, limit)


@router.get("/auswertung/umsatz-artikel", response_model=UmsatzArtikelResponse,
            dependencies=AUSWERTUNG_RECHT)
def umsatz_je_artikel(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(0, ge=0, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Rangliste der Artikel.

    Die Antwort nennt ausdrücklich, wie viel Umsatz sich **keinem** Artikel
    zuordnen ließ — bei überwiegend frei getippten Positionen ist die Liste
    sonst eine Genauigkeit, die es nicht gibt.
    """
    return auswertungen_service.je_artikel(db, date_from, date_to, limit)


@router.get("/auswertung/angebotsquote", response_model=AngebotsquoteResponse,
            dependencies=AUSWERTUNG_RECHT)
def angebotsquote(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Wie viele Angebote zu Aufträgen werden, gezählt nach Angebotsdatum."""
    return auswertungen_service.angebotsquote(db, date_from, date_to)
