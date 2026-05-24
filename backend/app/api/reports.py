"""
Berichte & PDF-Export
"""
import io
import base64
import os
import math
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

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


def _load_contact_address(db: Session, settings: dict) -> dict:
    """
    Liest Adressdaten aus dem verknüpften Stammdaten-Kontakt.
    Gibt dict mit keys: name, street, zip_city, country zurück.
    Felder werden anhand ihrer Bezeichnung erkannt (sprachunabhängig).
    """
    contact_id = settings.get("company_contact_id", "")
    result = {
        "name":     settings.get("company_name", ""),
        "street":   "",
        "zip_city": "",
        "country":  "",
    }

    if not contact_id:
        return result

    record = db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()
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

    # Rohdaten des Kontakts loggen (für Diagnose)
    logger.info(
        "Kontakt-Rohdaten: id=%r display_name=%r data=%r field_map=%r",
        str(record.id), record.display_name, data, field_map
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

    logger.info(
        "Kontakt-Adresse geladen: name=%r street=%r zip=%r city=%r zip_city=%r",
        result["name"], result["street"], zip_val, city_val, result["zip_city"]
    )
    return result


def _company_address_html(addr: dict) -> str:
    """Baut die Firmenadresse als HTML-Zeilen (rechtsbündig)."""
    lines = []
    if addr.get("name"):
        lines.append(f'<div class="co-name">{addr["name"]}</div>')
    # Straße und PLZ/Ort auf einer Zeile mit Komma getrennt
    street   = addr.get("street", "").strip()
    zip_city = addr.get("zip_city", "").strip()
    if street and zip_city:
        lines.append(f'<div>{street}, {zip_city}</div>')
    elif street:
        lines.append(f'<div>{street}</div>')
    elif zip_city:
        lines.append(f'<div>{zip_city}</div>')
    if addr.get("country"):
        lines.append(f'<div>{addr["country"]}</div>')
    return "\n".join(lines)


def _build_html(
    entries: list,
    group_by: str,           # "aufgabe" | "benutzer"
    settings: dict,
    filters: dict,
    current_user_name: str,
    db: Session = None,
    round_to: int = 0,
    round_dir: str = "up",
) -> str:
    """Baut das vollständige HTML für den Projektzeitbericht (Vorlage-konform)."""

    # ── Daten gruppieren ──────────────────────────────────────────────────────
    groups: dict = defaultdict(list)
    for e in entries:
        if group_by == "benutzer":
            key = getattr(e.user, "full_name", "") or "Unbekannt"
        else:
            key = e.project_name or "(keine Aufgabe)"
        groups[key].append(e)
    groups = dict(sorted(groups.items()))

    # ── Gerundete Dauer ───────────────────────────────────────────────────────
    def dur(e):
        return _round_minutes(e.duration_minutes or 0, round_to, round_dir)

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    summary = []
    total_bill = 0
    total_non  = 0
    for grp_name, grp_entries in groups.items():
        bill = sum(dur(e) for e in grp_entries if e.billable)
        non  = sum(dur(e) for e in grp_entries if not e.billable)
        total_bill += bill
        total_non  += non
        summary.append((grp_name, bill, non, bill + non))

    # ── Firmendaten aus verknüpftem Kontakt ──────────────────────────────────
    logo_src  = _logo_base64(settings)
    addr      = _load_contact_address(db, settings) if db else {"name": settings.get("company_name",""), "street":"", "zip_city":"", "country":""}
    company_addr = _company_address_html(addr)

    if logo_src:
        logo_html = f'<img src="{logo_src}" class="logo" alt="Logo">'
    elif settings.get("company_name"):
        logo_html = f'<span class="logo-text">{settings["company_name"]}</span>'
    else:
        logo_html = ""

    # ── Filterzeilen ─────────────────────────────────────────────────────────
    filter_rows = [
        ("Datum von", filters.get("date_from", "")),
        ("Datum bis", filters.get("date_to",   "")),
    ]
    if filters.get("contact_name"):
        filter_rows.append(("Kontakt / Kunde", filters["contact_name"]))
    if filters.get("project_name"):
        filter_rows.append(("Aufgabe", filters["project_name"]))
    if filters.get("user_name"):
        filter_rows.append(("Benutzer", filters["user_name"]))
    if filters.get("billable_label"):
        filter_rows.append(("Verrechenbar", filters["billable_label"]))

    filter_html = "".join(
        f"<tr><td class='fk'>{k}</td><td class='fv'>{v}</td></tr>"
        for k, v in filter_rows
    )

    # ── Zusammenfassung-Tabelle ───────────────────────────────────────────────
    grp_col = "Benutzer" if group_by == "benutzer" else "Aufgabe"

    summary_rows_html = "".join(
        f"<tr>"
        f"<td class='s-name'>{name}</td>"
        f"<td class='s-num'>{_fmt_minutes(bill)}</td>"
        f"<td class='s-num'>{_fmt_minutes(non)}</td>"
        f"<td class='s-num'>{_fmt_minutes(total)}</td>"
        f"</tr>"
        for name, bill, non, total in summary
    )

    # ── Detail-Abschnitte ─────────────────────────────────────────────────────
    col_header = "Benutzer" if group_by == "aufgabe" else "Aufgabe"

    def entry_rows(grp_entries):
        rows = ""
        for e in sorted(grp_entries, key=lambda x: x.started_at):
            user_or_task = (
                getattr(e.user, "full_name", "") if group_by == "aufgabe"
                else (e.project_name or "(keine Aufgabe)")
            )
            note  = (e.note or "").replace("\n", "<br>")
            pause = _fmt_minutes(e.pause_minutes or 0)
            dauer = _fmt_minutes(dur(e))
            verr  = "Ja" if e.billable else "Nein"
            rows += (
                f"<tr>"
                f"<td class='eu'>{user_or_task}</td>"
                f"<td class='en'>{note}</td>"
                f"<td class='et2'>{_fmt_dt(e.started_at)}</td>"
                f"<td class='et2'>{_fmt_dt(e.ended_at)}</td>"
                f"<td class='ed'>{pause}</td>"
                f"<td class='ed'>{dauer}</td>"
                f"<td class='ev'>{verr}</td>"
                f"</tr>"
            )
        return rows

    sections_html = ""
    for grp_name, grp_entries in groups.items():
        grp_total = sum(dur(e) for e in grp_entries)
        rows      = entry_rows(grp_entries)
        sections_html += f"""
<div class="grp">
  <div class="grp-title">{grp_name}</div>
  <table class="et">
    <thead><tr>
      <th class="eu">{col_header}</th>
      <th class="en">Notiz</th>
      <th class="et2">Startzeit</th>
      <th class="et2">Endzeit</th>
      <th class="ed">Pause</th>
      <th class="ed">Dauer</th>
      <th class="ev">Verr.</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="grp-total">Gesamt: <strong>{_fmt_minutes(grp_total)}</strong></div>
</div>
"""

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    # ── Vollständiges HTML ────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 1.8cm 1.6cm 2.4cm 1.6cm;
    @bottom-left   {{ content: "Ersteller: {current_user_name}"; font-size: 7.5pt; color: #555; font-family: Arial, sans-serif; }}
    @bottom-center {{ content: "Seite " counter(page) " von " counter(pages); font-size: 7.5pt; color: #555; font-family: Arial, sans-serif; }}
    @bottom-right  {{ content: "Erstellt am: {now_str}"; font-size: 7.5pt; color: #555; font-family: Arial, sans-serif; }}
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9pt;
    color: #1a1a1a;
    line-height: 1.45;
  }}

  /* ── Logo oben rechts ───────────────────────────────── */
  .hdr-logo {{ overflow: hidden; margin-bottom: 0.3cm; }}
  .logo {{ float: right; display: block; max-height: 66px; max-width: 330px; object-fit: contain; }}
  .logo-text {{ float: right; font-size: 14pt; font-weight: bold; color: #333; }}

  /* ── Berichtstitel ──────────────────────────────────── */
  h1 {{
    font-size: 18pt;
    font-weight: bold;
    color: #1a1a1a;
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 0.18cm;
    margin-bottom: 0.5cm;
  }}

  /* ── Filterbereich + Adresse ────────────────────────── */
  .info {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 1px solid #999;
    padding-bottom: 0.45cm;
    margin-bottom: 0.55cm;
  }}

  .info-left .ftitle {{ display: none; }}
  table.ft {{ border-collapse: collapse; }}
  table.ft td {{ padding: 1.5px 12px 1.5px 0; font-size: 8.5pt; vertical-align: top; }}
  .fk {{ font-weight: bold; white-space: nowrap; min-width: 80px; }}
  .fv {{ color: #333; }}

  .info-right {{
    text-align: right;
    font-size: 8.5pt;
    color: #333;
    line-height: 1.65;
    white-space: nowrap;
  }}
  .info-right .co-name {{ font-weight: bold; font-size: 9pt; }}

  /* ── Zusammenfassung ────────────────────────────────── */
  .sec-title {{
    font-size: 13pt;
    font-weight: bold;
    margin-bottom: 0.25cm;
  }}

  table.st {{
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
    margin-bottom: 0.75cm;
  }}
  table.st thead tr {{ border-bottom: 1.5px solid #1a1a1a; }}
  table.st th {{
    padding: 3px 0 5px 0;
    font-weight: bold;
    text-align: left;
  }}
  table.st th.r, table.st td.s-num {{ text-align: right; }}
  table.st td {{
    padding: 3px 0;
    border-bottom: 0.5px solid #ddd;
  }}
  table.st td.s-name {{ padding-right: 8px; }}
  table.st tr.tot td {{
    font-weight: bold;
    border-top: 1.5px solid #1a1a1a;
    border-bottom: none;
    padding-top: 5px;
  }}

  /* ── Gruppen-Abschnitte ─────────────────────────────── */
  .grp {{
    margin-bottom: 0.65cm;
    page-break-inside: avoid;
  }}
  .grp-title {{
    font-size: 11.5pt;
    font-weight: bold;
    border-bottom: 1px solid #1a1a1a;
    padding-bottom: 2px;
    margin-bottom: 0.18cm;
  }}

  /* ── Eintrags-Tabelle ───────────────────────────────── */
  table.et {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
  }}
  table.et thead tr {{ border-bottom: 1px solid #666; }}
  table.et th {{
    text-align: left;
    padding: 3px 6px 4px 0;
    font-weight: bold;
    white-space: nowrap;
  }}
  table.et td {{
    padding: 3px 6px 3px 0;
    border-bottom: 0.5px solid #e8e8e8;
    vertical-align: top;
  }}
  table.et tbody tr:last-child td {{ border-bottom: 1px solid #888; }}

  /* Spaltenbreiten */
  .eu  {{ width: 13%; }}
  .en  {{ width: 41%; }}
  .et2 {{ width: 12%; white-space: nowrap; }}
  .ed  {{ width: 6%;  text-align: right; white-space: nowrap; }}
  .ev  {{ width: 5%;  text-align: center; }}

  /* Gesamt-Zeile unter der Tabelle */
  .grp-total {{
    text-align: right;
    padding: 4px 0 0 0;
    font-size: 9pt;
  }}
</style>
</head>
<body>

<!-- Logo oben rechts (float:right ist in WeasyPrint am zuverlässigsten) -->
<div class="hdr-logo">{logo_html}</div>

<!-- Berichtstitel -->
<h1>Projektzeitbericht</h1>

<!-- Filter links / Firmenadresse rechts -->
<div class="info">
  <div class="info-left">
    <div class="ftitle">Filterkriterien</div>
    <table class="ft"><tbody>{filter_html}</tbody></table>
  </div>
  <div class="info-right">{company_addr}</div>
</div>

<!-- Zusammenfassung -->
<div class="sec-title">Zusammenfassung</div>
<table class="st">
  <thead><tr>
    <th>{grp_col}</th>
    <th class="r">Verrechenbar</th>
    <th class="r">Nicht verrechenbar</th>
    <th class="r">Gesamt</th>
  </tr></thead>
  <tbody>
    {summary_rows_html}
    <tr class="tot">
      <td>Gesamt:</td>
      <td class="s-num">{_fmt_minutes(total_bill)}</td>
      <td class="s-num">{_fmt_minutes(total_non)}</td>
      <td class="s-num">{_fmt_minutes(total_bill + total_non)}</td>
    </tr>
  </tbody>
</table>

<!-- Detail-Abschnitte -->
{sections_html}

</body>
</html>"""


# ── Report-Endpoint ───────────────────────────────────────────────────────────

@router.get("/zeiterfassung")
async def report_zeiterfassung(
    date_from:    str           = Query(...,       description="Von-Datum ISO (YYYY-MM-DD)"),
    date_to:      str           = Query(...,       description="Bis-Datum ISO (YYYY-MM-DD)"),
    group_by:     str           = Query("aufgabe", description="aufgabe | benutzer"),
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
        dt_from = datetime.fromisoformat(date_from).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        dt_to   = datetime.fromisoformat(date_to).replace(
            hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Ungültiges Datumsformat (YYYY-MM-DD erwartet)")

    # ── Einträge abfragen ─────────────────────────────────────────────────────
    q = db.query(TimeEntry).filter(
        TimeEntry.started_at >= dt_from,
        TimeEntry.started_at <= dt_to,
        TimeEntry.ended_at.isnot(None),
    )
    if contact_name:
        q = q.filter(TimeEntry.contact_name.ilike(f"%{contact_name}%"))
    if project_name:
        q = q.filter(TimeEntry.project_name.ilike(f"%{project_name}%"))
    if user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if billable == "yes":
        q = q.filter(TimeEntry.billable == True)
    elif billable == "no":
        q = q.filter(TimeEntry.billable == False)

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
        "date_from":     datetime.fromisoformat(date_from).strftime("%d.%m.%Y"),
        "date_to":       datetime.fromisoformat(date_to).strftime("%d.%m.%Y"),
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
        raise HTTPException(500, f"PDF-Generierung fehlgeschlagen: {exc}") from exc

    # ── Dateiname ─────────────────────────────────────────────────────────────
    if filename:
        safe_name    = filename.strip().replace("/", "_").replace("\\", "_")
        out_filename = f"{safe_name}.pdf"
    else:
        cf           = contact_name.replace(" ", "_") if contact_name else "Alle"
        ts           = datetime.now().strftime("%Y-%m-%d")
        out_filename = f"Projektzeitbericht_{cf}_{ts}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{out_filename}"'},
    )


# ── Kontaktliste für Filter-Dropdown ─────────────────────────────────────────

@router.get("/zeiterfassung/contacts")
async def report_contact_list(
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


# ── Aufgabenliste für Filter-Dropdown ────────────────────────────────────────

@router.get("/zeiterfassung/tasks")
async def report_task_list(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import distinct
    rows = (
        db.query(distinct(TimeEntry.project_name))
        .filter(TimeEntry.project_name.isnot(None), TimeEntry.project_name != "")
        .order_by(TimeEntry.project_name)
        .all()
    )
    return {"tasks": [r[0] for r in rows]}
