"""
Berichte & PDF-Export
"""
import io
import base64
import os
import math
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session
from weasyprint import HTML as WeasyprintHTML

logger = logging.getLogger(__name__)

from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.zeiterfassung import TimeEntry
from app.models.settings import Setting
from app.models.masterdata import EntityRecord, FieldDefinition
from app.api.berichtsvorlage import bericht_html
from app.core import zeit
from app.core.http import content_disposition

router = APIRouter(prefix="/reports", tags=["Berichte"])

STATIC_DIR = "/app/static"


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _fmt_minutes(total_minutes: int) -> str:
    """Formatiert Minuten als H:MM — z.B. 90 → '1:30'"""
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}:{m:02d}"


def _round_minutes(minutes: int, round_to: int, direction: str) -> int:
    """Rundet Minuten auf das nächste Vielfache von round_to."""
    if round_to <= 0 or minutes <= 0:
        return minutes
    if direction == "up":
        return math.ceil(minutes / round_to) * round_to
    else:
        return math.floor(minutes / round_to) * round_to


def _zeitgrenze(text: str, ende: bool = False) -> datetime:
    """Eine Zeitraumgrenze aus dem Bericht einlesen.

    Angenommen werden zwei Formen:

      ``2026-08-01``                  reines Datum  → Tagesgrenze in UTC
      ``2026-08-01T00:00:00+02:00``   Zeitstempel   → genau so übernommen

    Die zweite Form schickt die Oberfläche, seit aufgefallen ist, dass der
    Bericht für August einen Eintrag vom 1. September enthielt: Ein Eintrag,
    der um 01:15 Ortszeit beginnt, liegt in UTC noch im Vormonat. Wird die
    Grenze als UTC-Mitternacht gelesen, verschiebt sich der ganze Zeitraum um
    die Zeitzone — vorne fehlen Einträge, hinten kommen fremde dazu.

    Das reine Datum bleibt zulässig, damit ältere Lesezeichen und direkte
    Aufrufe der Schnittstelle weiter funktionieren.
    """
    wert = datetime.fromisoformat(text)          # wirft ValueError bei Unsinn
    if len(text.strip()) == 10:                  # nur Datum → Tagesgrenze
        wert = (wert.replace(hour=23, minute=59, second=59, microsecond=999999)
                if ende else
                wert.replace(hour=0, minute=0, second=0, microsecond=0))
    if wert.tzinfo is None:
        wert = wert.replace(tzinfo=timezone.utc)
    return wert


def _fmt_dt(dt: datetime) -> str:
    """Formatiert datetime als DD.MM.YYYY HH:MM"""
    if not dt:
        return ""
    local = dt.astimezone()
    return local.strftime("%d.%m.%Y %H:%M")


def _load_settings(db: Session) -> dict:
    rows = db.query(Setting).all()
    return {r.key: r.value for r in rows}


def _logo_base64(settings: dict) -> str:
    """Lädt das Header-Logo als base64 für den PDF-Einbau."""
    logo_url = settings.get("logo_header_url") or settings.get("logo_url") or ""
    if not logo_url:
        return ""
    path = logo_url.replace("/api/static", STATIC_DIR)
    if not os.path.exists(path):
        return ""
    ext  = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "svg": "image/svg+xml", "webp": "image/webp"}.get(ext, "image/png")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _adresse_aus_record(db: Session, record, vorgabe_name: str = "") -> dict:
    """Adressfelder eines Kontakt-Datensatzes erkennen.

    Die Felder der Kontakte sind frei konfigurierbar — es gibt keine feste
    Spalte „Straße". Erkannt wird deshalb über Feldbezeichnung *und*
    Feldschlüssel; das überlebt Umbenennungen und andere Sprachen.

    Genutzt für den Absender (eigene Firma) und seit 01.09.2026 auch für den
    Empfänger (Kunde im Kopf des Berichts) — beide brauchen dieselbe Erkennung,
    und zwei Kopien davon würden bei der nächsten Feldumbenennung auseinander
    laufen.
    """
    result = {"name": vorgabe_name, "street": "", "zip_city": "", "country": ""}
    if not record or not record.data:
        return result

    # Feldbezeichnungen laden
    fields = db.query(FieldDefinition).filter(
        FieldDefinition.entity_type_id == record.entity_type_id
    ).all()
    field_map = {f.key: f.name.lower() for f in fields}

    data = record.data or {}

    # Display-Name des Kontakts als Firmenname verwenden
    if record.display_name:
        result["name"] = record.display_name

    # Schlüsselwörter für die Felderkennung
    street_kw  = ("straße", "strasse", "street", "adresse", "address", "anschrift")
    zip_kw     = ("plz", "postleitzahl", "zip", "postal")
    city_kw    = ("ort", "stadt", "city", "gemeinde", "place")
    country_kw = ("land", "country", "staat")

    zip_val  = ""
    city_val = ""

    # Diagnose-Ausgabe: bewusst DEBUG und ohne die Feldinhalte. Auf INFO
    # schrieb jeder erzeugte Bericht Adresse, E-Mail und Telefon des Kontakts
    # ins Container-Log — personenbezogene Daten, die dort dauerhaft liegen
    # bleiben und in keinem Löschkonzept auftauchen.
    logger.debug(
        "Kontakt-Adressfelder: id=%r felder=%r",
        str(record.id), sorted(field_map.keys())
    )

    for key, label in field_map.items():
        val = str(data.get(key, "") or "").strip()
        if not val:
            continue
        key_lower = key.lower()
        # Prüfe sowohl Feldbezeichnung als auch Feldschlüssel
        is_street  = any(kw in label for kw in street_kw)  or any(kw in key_lower for kw in street_kw)
        is_zip     = any(kw in label for kw in zip_kw)     or any(kw in key_lower for kw in zip_kw)
        is_city    = any(kw in label for kw in city_kw)    or any(kw in key_lower for kw in city_kw)
        is_country = any(kw in label for kw in country_kw) or any(kw in key_lower for kw in country_kw)

        if is_street:
            result["street"] = val
        elif is_zip:
            zip_val = val
        elif is_city:
            city_val = val
        elif is_country:
            result["country"] = val

    zip_city = " ".join(filter(None, [zip_val, city_val]))
    if zip_city:
        result["zip_city"] = zip_city

    logger.debug("Kontakt-Adresse erkannt: %s Zeilen gefüllt",
                 sum(1 for v in result.values() if v))
    return result


def _kunde_adresse(db: Session, name: str) -> dict:
    """Empfängeradresse: Kontakt-Stammsatz zum Namen aus den Zeiteinträgen.

    Die Zeiteinträge führen den Kontakt denormalisiert als Text mit — für den
    Empfängerblock wird daraus der Stammsatz gesucht. Findet sich keiner
    (Kontakt gelöscht, Name von Hand getippt), bleibt der Name ohne Adresse
    stehen: Ein Bericht ohne Anschrift ist brauchbar, ein Bericht mit falscher
    Anschrift nicht.
    """
    if not db or not name:
        return {"name": name or "", "street": "", "zip_city": "", "country": ""}
    record = (
        db.query(EntityRecord)
        .filter(EntityRecord.display_name.ilike(name.strip()),
                EntityRecord.anonymized_at.is_(None))
        .first()
    )
    return _adresse_aus_record(db, record, name)


def _build_html(
    entries: list,
    group_by: str,           # "aufgabe" (= Zeitprojekt) | "benutzer"
    settings: dict,
    filters: dict,
    current_user_name: str,
    db: Session = None,
    round_to: int = 0,
    round_dir: str = "up",
) -> str:
    """HTML des Projektzeitberichts — für die Vorschau und für das PDF.

    Die Gestaltung liegt in ``berichtsvorlage.py``; hier werden nur die Daten
    zusammengetragen (Firmenkopf, Logo) und die Formatier-/Rundungsfunktionen
    hineingereicht. So rechnet der Bericht nachweislich wie die Auswertung:
    dieselbe ``_round_minutes``, dieselbe ``_fmt_minutes``.
    """
    logo_src = _logo_base64(settings)

    # Ohne hinterlegtes Logo bleibt der Firmenname als Text stehen — sonst wäre
    # der Kopf links leer und der Bericht ohne Absenderhinweis.
    # Kein Logo im Bericht? Dann fehlt in Einstellungen → Allgemein das
    # Kopf-Logo (600×120), oder die hinterlegte Datei liegt nicht mehr im
    # static-Verzeichnis (siehe _logo_base64).
    if logo_src:
        logo_html = f'<img src="{logo_src}" class="logo" alt="Logo">'
    elif settings.get("company_name"):
        logo_html = f'<span class="logo-text">{settings["company_name"]}</span>'
    else:
        logo_html = ""

    # ── Empfänger (Kunde) ────────────────────────────────────────────────────
    # Der Bericht geht in aller Regel an genau einen Kunden. Enthalten die
    # Einträge nur einen Kontakt — sei es durch den Filter oder weil im
    # Zeitraum nur für ihn gearbeitet wurde —, steht er als Anschriftfeld im
    # Kopf. Bei mehreren Kunden entfällt der Block: Eine willkürlich gewählte
    # Anschrift wäre schlimmer als gar keine.
    kontakte = {(e.contact_name or "").strip() for e in entries}
    kontakte.discard("")
    empfaenger_html = ""
    if len(kontakte) == 1:
        adresse = _kunde_adresse(db, next(iter(kontakte)))
        zeilen = [f'<div class="empf-name">{adresse["name"]}</div>']
        if adresse["street"]:
            zeilen.append(f'<div>{adresse["street"]}</div>')
        if adresse["zip_city"]:
            zeilen.append(f'<div>{adresse["zip_city"]}</div>')
        if adresse["country"]:
            zeilen.append(f'<div>{adresse["country"]}</div>')
        empfaenger_html = "\n".join(zeilen)

    # Rundung gehört in den Kopf des Berichts: Wer die Stunden nachrechnet,
    # muss sehen, dass gerundet wurde — sonst gilt der Bericht als falsch.
    if round_to > 0:
        richtung = "aufgerundet" if round_dir == "up" else "abgerundet"
        filters = {**filters,
                   "rounding_label": f" · je Eintrag auf {round_to} min {richtung}"}

    return bericht_html(
        entries=entries,
        group_by=group_by,
        settings=settings,
        filters=filters,
        current_user_name=current_user_name,
        logo_html=logo_html,
        empfaenger_html=empfaenger_html,
        fmt_minutes=_fmt_minutes,
        fmt_dt=_fmt_dt,
        runde=lambda e: _round_minutes(e.duration_minutes or 0, round_to, round_dir),
    )


# ── Report-Endpoint ───────────────────────────────────────────────────────────

@router.get("/zeiterfassung")
def report_zeiterfassung(
    date_from:    str           = Query(...,       description="Von-Datum ISO (YYYY-MM-DD)"),
    date_to:      str           = Query(...,       description="Bis-Datum ISO (YYYY-MM-DD)"),
    group_by:     str           = Query("aufgabe", description="aufgabe (= Zeitprojekt) | benutzer | kontakt"),
    contact_name: Optional[str] = Query(None,      description="Filter: Kontakt/Kunde"),
    project_name: Optional[str] = Query(None,      description="Filter: Aufgabe/Projektname"),
    user_id:      Optional[str] = Query(None,      description="Filter: Benutzer-UUID"),
    billable:     Optional[str] = Query(None,      description="all | yes | no"),
    format:       str           = Query("pdf",     description="pdf | html"),
    filename:     Optional[str] = Query(None,      description="Gewünschter Dateiname (ohne .pdf)"),
    round_to:     int           = Query(0,         description="Auf X Minuten runden (0 = keine Rundung)"),
    round_dir:    str           = Query("up",      description="up | down"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Projektzeitbericht als PDF oder HTML-Vorschau."""

    # ── Datum parsen ──────────────────────────────────────────────────────────
    try:
        dt_from = _zeitgrenze(date_from)
        dt_to   = _zeitgrenze(date_to, ende=True)
    except ValueError:
        raise HTTPException(400, "Ungültiges Datumsformat (YYYY-MM-DD erwartet)")

    # ── Einträge abfragen ─────────────────────────────────────────────────────
    # Gemeinsame Abfrage mit der Auswertung (``_entry_query``) — inklusive der
    # Beschränkung auf eigene Einträge beim Umfang „nur eigene".
    q = _entry_query(db, current_user, dt_from, dt_to, contact_name,
                     project_name, user_id, billable)

    entries = q.order_by(TimeEntry.started_at).all()

    if not entries:
        raise HTTPException(404, "Keine Zeiteinträge für die gewählten Filter gefunden")

    # ── Benutzername für Filteranzeige ────────────────────────────────────────
    user_name_filter = ""
    if user_id:
        from app.models.user import User as UserModel
        u = db.query(UserModel).filter(UserModel.id == user_id).first()
        user_name_filter = u.full_name if u else ""

    # ── HTML generieren ───────────────────────────────────────────────────────
    settings       = _load_settings(db)
    billable_label = {"yes": "Ja", "no": "Nein"}.get(billable or "all", "Alle")

    filters = {
        # aus den bereits gelesenen Grenzen, nicht erneut aus dem Text —
        # sonst steht im Kopf des Berichts ein anderes Datum, als abgefragt wurde
        "date_from":     dt_from.strftime("%d.%m.%Y"),
        "date_to":       dt_to.strftime("%d.%m.%Y"),
        "contact_name":  contact_name or "",
        "project_name":  project_name or "",
        "user_name":     user_name_filter,
        "billable_label": billable_label if billable and billable != "all" else "",
    }

    html_content = _build_html(
        entries=entries,
        group_by=group_by,
        settings=settings,
        filters=filters,
        current_user_name=current_user.full_name,
        db=db,
        round_to=round_to,
        round_dir=round_dir,
    )

    # ── HTML-Vorschau ─────────────────────────────────────────────────────────
    if format == "html":
        return HTMLResponse(content=html_content)

    # ── PDF generieren ────────────────────────────────────────────────────────
    try:
        pdf_bytes = WeasyprintHTML(string=html_content).write_pdf()
    except Exception as exc:
        logger.exception("WeasyPrint Fehler beim PDF-Generieren")
        logger.exception("Fehler bei reports: %s", exc)
        raise HTTPException(500, "Das PDF konnte nicht erzeugt werden (Ursache im Serverlog).")

    # ── Dateiname ─────────────────────────────────────────────────────────────
    if filename:
        safe_name    = filename.strip().replace("/", "_").replace("\\", "_")
        out_filename = f"{safe_name}.pdf"
    else:
        cf           = contact_name.replace(" ", "_") if contact_name else "Alle"
        ts           = zeit.jetzt().strftime("%Y-%m-%d")
        out_filename = f"Projektzeitbericht_{cf}_{ts}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition("attachment", out_filename)},
    )


# ── Kontaktliste für Filter-Dropdown ─────────────────────────────────────────

@router.get("/zeiterfassung/contacts")
def report_contact_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import distinct
    rows = (
        db.query(distinct(TimeEntry.contact_name))
        .filter(TimeEntry.contact_name.isnot(None), TimeEntry.contact_name != "")
        .order_by(TimeEntry.contact_name)
        .all()
    )
    return {"contacts": [r[0] for r in rows]}


# ── Zeitprojekt-Liste für Filter-Dropdown ────────────────────────────────────

@router.get("/zeiterfassung/tasks")
def report_task_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Namen aller Zeitprojekte, auf die gebucht wurde (Filter-Auswahl).

    Bewusst aus den Zeiteinträgen und nicht aus den Stammdaten: Gefiltert
    werden soll, was tatsächlich vorkommt — auch Buchungen auf inzwischen
    archivierte Zeitprojekte.
    """
    from sqlalchemy import distinct
    rows = (
        db.query(distinct(TimeEntry.project_name))
        .filter(TimeEntry.project_name.isnot(None), TimeEntry.project_name != "")
        .order_by(TimeEntry.project_name)
        .all()
    )
    return {"tasks": [r[0] for r in rows]}


# ── Auswertung: Summen je Benutzer / Zeitprojekt / Kontakt ───────────────────

def _entry_query(db: Session, current_user: User, dt_from: datetime, dt_to: datetime,
                 contact_name: Optional[str], project_name: Optional[str],
                 user_id: Optional[str], billable: Optional[str]):
    """Grundabfrage für abgeschlossene Zeiteinträge im Zeitraum.

    Dieselben Filter wie im PDF-Bericht — absichtlich in einer Funktion, damit
    Auswertung und Bericht nicht auseinanderlaufen. Zwei Stellen, die dieselbe
    Frage verschieden beantworten, sind schlimmer als eine unbequeme.

    Der Umfang „nur eigene" (Rechtemodell seit Migration 0055) hat Vorrang vor
    jedem Filter: Sonst wäre der Bericht der bequemste Weg, an die
    Arbeitszeiten des ganzen Betriebs zu kommen — die Einträge-Liste im Modul
    schränkt seit 0055 ein, die Auswertung tat es bis 01.09.2026 nicht.
    """
    from app.core.berechtigungen import darf_nur_eigene

    q = db.query(TimeEntry).filter(
        TimeEntry.started_at >= dt_from,
        TimeEntry.started_at <= dt_to,
        TimeEntry.ended_at.isnot(None),
    )
    if darf_nur_eigene(current_user, "zeiterfassung"):
        q = q.filter(TimeEntry.user_id == current_user.id)
    elif user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if contact_name:
        q = q.filter(TimeEntry.contact_name.ilike(f"%{contact_name}%"))
    if project_name:
        q = q.filter(TimeEntry.project_name.ilike(f"%{project_name}%"))
    if billable == "yes":
        q = q.filter(TimeEntry.billable == True)   # noqa: E712
    elif billable == "no":
        q = q.filter(TimeEntry.billable == False)  # noqa: E712
    return q


@router.get("/zeiterfassung/uebersicht")
def report_uebersicht(
    date_from:    str           = Query(...,         description="Von-Datum ISO (YYYY-MM-DD)"),
    date_to:      str           = Query(...,         description="Bis-Datum ISO (YYYY-MM-DD)"),
    group_by:     str           = Query("benutzer",  description="benutzer | zeitprojekt | kontakt"),
    contact_name: Optional[str] = Query(None,        description="Filter: Kontakt"),
    project_name: Optional[str] = Query(None,        description="Filter: Zeitprojekt"),
    user_id:      Optional[str] = Query(None,        description="Filter: Benutzer-UUID"),
    billable:     Optional[str] = Query(None,        description="all | yes | no"),
    round_to:     int           = Query(0,           description="Auf X Minuten runden (0 = keine)"),
    round_dir:    str           = Query("up",        description="up | down"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summen je Benutzer, Zeitprojekt oder Kontakt für einen Zeitraum.

    Grundlage der Auswertungsseiten unter Zeiterfassung → Berichte. Anders als
    ``/zeiterfassung`` (PDF) liefert dieser Endpunkt Zahlen statt Papier: die
    Antwort trägt je Zeile Gesamt, verrechenbar und nicht verrechenbar sowie
    — bei Gruppierung nach Zeitprojekt — den Stand des Stundenkontos.

    Gruppiert wird nach Kennung, nicht nach Namen: Wird ein Zeitprojekt
    umbenannt, bleiben alte Buchungen unter ihrem damaligen Namen gespeichert
    (denormalisiert) und würden sonst als zweite Zeile erscheinen. Nur wo
    keine Kennung mitgeschrieben wurde (Altbestand), dient der Name als
    Rückfall.
    """
    if group_by not in ("benutzer", "zeitprojekt", "kontakt"):
        raise HTTPException(400, "group_by muss benutzer, zeitprojekt oder kontakt sein")

    try:
        dt_from = _zeitgrenze(date_from)
        dt_to   = _zeitgrenze(date_to, ende=True)
    except ValueError:
        raise HTTPException(400, "Ungültiges Datumsformat (YYYY-MM-DD erwartet)")

    entries = _entry_query(db, current_user, dt_from, dt_to, contact_name,
                           project_name, user_id, billable).all()

    # ── Gruppieren ────────────────────────────────────────────────────────────
    zeilen: dict = {}
    for e in entries:
        if group_by == "benutzer":
            schluessel = str(e.user_id)
            name = getattr(e.user, "full_name", "") or "Unbekannt"
            zusatz = ""
        elif group_by == "zeitprojekt":
            schluessel = str(e.project_id) if e.project_id else f"name:{e.project_name or ''}"
            name = e.project_name or "(ohne Zeitprojekt)"
            zusatz = e.contact_name or ""
        else:
            schluessel = str(e.contact_id) if e.contact_id else f"name:{e.contact_name or ''}"
            name = e.contact_name or "(ohne Kontakt)"
            zusatz = ""

        zeile = zeilen.setdefault(schluessel, {
            "schluessel": schluessel,
            "name": name,
            "zusatz": zusatz,
            "project_id": str(e.project_id) if (group_by == "zeitprojekt" and e.project_id) else None,
            "eintraege": 0,
            "minuten": 0,
            "verrechenbar_minuten": 0,
            "nicht_verrechenbar_minuten": 0,
        })
        # Neuester Name gewinnt: Nach einer Umbenennung soll die Zeile so
        # heißen, wie das Zeitprojekt heute heißt.
        zeile["name"] = name or zeile["name"]
        if zusatz:
            zeile["zusatz"] = zusatz

        minuten = _round_minutes(e.duration_minutes or 0, round_to, round_dir)
        zeile["eintraege"] += 1
        zeile["minuten"] += minuten
        if e.billable:
            zeile["verrechenbar_minuten"] += minuten
        else:
            zeile["nicht_verrechenbar_minuten"] += minuten

    # ── Stundenkonto je Zeitprojekt ergänzen ─────────────────────────────────
    if group_by == "zeitprojekt":
        from app.api.zeiterfassung import _compute_budget
        for zeile in zeilen.values():
            if not zeile["project_id"]:
                zeile["budget"] = None
                continue
            budget = _compute_budget(db, UUID(zeile["project_id"]))
            zeile["budget"] = {
                "has_budget": budget.has_budget,
                "budget_minutes": budget.budget_minutes,
                "consumed_minutes": budget.consumed_minutes,
                "remaining_minutes": budget.remaining_minutes,
                "exhausted": budget.exhausted,
            }

    # Größte Summe zuerst — die Auswertung soll zeigen, wo die Zeit hingeht.
    liste = sorted(zeilen.values(), key=lambda z: (-z["minuten"], z["name"].lower()))
    for zeile in liste:
        zeile["anteil_verrechenbar"] = (
            round(zeile["verrechenbar_minuten"] * 100 / zeile["minuten"])
            if zeile["minuten"] else 0
        )
        zeile["dauer"] = _fmt_minutes(zeile["minuten"])

    summe_minuten = sum(z["minuten"] for z in liste)
    summe_bill    = sum(z["verrechenbar_minuten"] for z in liste)

    # ── Jetzt aktiv (laufende Timer) ─────────────────────────────────────────
    from app.core.berechtigungen import darf_nur_eigene

    jetzt = datetime.now(timezone.utc)
    laufend_q = db.query(TimeEntry).filter(TimeEntry.ended_at.is_(None))
    if darf_nur_eigene(current_user, "zeiterfassung"):
        laufend_q = laufend_q.filter(TimeEntry.user_id == current_user.id)
    laufend = []
    for e in laufend_q.all():
        laufend.append({
            "id": str(e.id),
            "benutzer": getattr(e.user, "full_name", "") or "Unbekannt",
            "zeitprojekt": e.project_name or "",
            "kontakt": e.contact_name or "",
            "notiz": e.note or "",
            "startzeit": e.started_at.isoformat(),
            "dauer_minuten": max(0, int((jetzt - e.started_at).total_seconds() // 60)
                                 - (e.pause_minutes or 0)),
        })
    laufend.sort(key=lambda x: x["startzeit"])

    return {
        "von": date_from,
        "bis": date_to,
        "group_by": group_by,
        "zeilen": liste,
        "summe": {
            "eintraege": sum(z["eintraege"] for z in liste),
            "minuten": summe_minuten,
            "dauer": _fmt_minutes(summe_minuten),
            "verrechenbar_minuten": summe_bill,
            "nicht_verrechenbar_minuten": summe_minuten - summe_bill,
            "anteil_verrechenbar": (round(summe_bill * 100 / summe_minuten)
                                    if summe_minuten else 0),
        },
        "laufend": laufend,
    }
