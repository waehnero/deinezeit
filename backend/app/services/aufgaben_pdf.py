"""
Aufgaben-Laufzettel als PDF (A4 hoch)
=====================================

Aufbau:
  - Obere Hälfte (A5 quer im A4-Hochformat): Laufzettel mit allen
    Aufgabeninformationen + QR-Code (kodiert die Aufgaben-URL inkl. ID —
    ein späteres Belegmodul kann Scans darüber automatisch der Aufgabe
    zuordnen).
  - Untere Hälfte: 5-mm-Rasterfläche für handschriftliche Notizen.

Erzeugt mit WeasyPrint (wie die Rechnungs-PDFs) und qrcode (bereits für
2FA im Stack).
"""
import base64
import io
from datetime import datetime

import qrcode
from weasyprint import HTML as WeasyprintHTML


def _qr_data_uri(payload: str) -> str:
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _esc(text) -> str:
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _datum(d) -> str:
    if not d:
        return "—"
    try:
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)


def generate_todo_pdf(todo: dict, qr_payload: str, statuses: list, priorities: list,
                      company_name: str = "DeineZeit", anhaenge: int = 0) -> bytes:
    """
    todo: Dict mit den Feldern des TodoResponse-Schemas.
    qr_payload: Inhalt des QR-Codes (Aufgaben-URL mit ID).
    statuses/priorities: [{value,label,color}] für die Beschriftung.
    company_name: Firmenname aus Einstellungen -> Allgemein.
    anhaenge: Anzahl der Anhänge der Aufgabe.
    """
    def _label(options, value):
        for o in options:
            if o.get("value") == value:
                return o.get("label") or value
        return value or "—"

    def _color(options, value, fallback="#6b7280"):
        for o in options:
            if o.get("value") == value:
                return o.get("color") or fallback
        return fallback

    status_label = _label(statuses, todo.get("status"))
    status_color = _color(statuses, todo.get("status"))
    prio_label = _label(priorities, todo.get("priority"))
    prio_color = _color(priorities, todo.get("priority"))

    faellig = _datum(todo.get("due_date"))
    if todo.get("due_time"):
        faellig += f", {str(todo['due_time'])[:5]} Uhr"

    verknuepfungen = []
    if todo.get("planning_project_name"):
        v = todo["planning_project_name"]
        if todo.get("planning_task_title"):
            v += f" › {todo['planning_task_title']}"
        verknuepfungen.append(("Projekt", v))
    if todo.get("record_name"):
        typ = f" ({todo['record_type_slug']})" if todo.get("record_type_slug") else ""
        verknuepfungen.append(("Stammdaten", f"{todo['record_name']}{typ}"))
    if todo.get("source") == "email" and todo.get("source_meta"):
        sm = todo["source_meta"]
        verknuepfungen.append(("Aus E-Mail", f"{sm.get('sender') or ''} — „{sm.get('subject') or ''}\""))
    elif todo.get("source") == "projektplan":
        verknuepfungen.append(("Quelle", "Projektmodul"))

    verkn_html = "".join(
        f'<tr><td class="k">{_esc(k)}</td><td>{_esc(v)}</td></tr>'
        for k, v in verknuepfungen
    )

    beschreibung = _esc(todo.get("description") or "").replace("\n", "<br>")

    html = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8">
<style>
  @page {{ size: A4 portrait; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Helvetica, Arial, sans-serif; color: #1f2937; }}

  /* ── Obere Hälfte: Laufzettel (A5) ─────────────────────────────── */
  .laufzettel {{
    height: 148.5mm; padding: 12mm 14mm 8mm 14mm;
    border-bottom: 0.5pt dashed #9ca3af;   /* Schnitt-/Falzlinie */
    position: relative; overflow: hidden;
  }}
  .qr {{ position: absolute; top: 10mm; right: 14mm; width: 30mm; height: 30mm; }}
  .qr img {{ width: 100%; height: 100%; }}
  .qr-id {{ position: absolute; top: 40.5mm; right: 14mm; width: 30mm;
            font-size: 5.5pt; color: #9ca3af; text-align: center; }}
  .modul {{ font-size: 8pt; letter-spacing: 2pt; color: #9ca3af;
            text-transform: uppercase; margin: 0 0 3mm 0; }}
  h1 {{ font-size: 16pt; margin: 0 38mm 4mm 0; line-height: 1.25; }}
  .badges {{ margin-bottom: 5mm; }}
  .badge {{ display: inline-block; font-size: 8.5pt; padding: 1mm 3mm;
            border-radius: 2mm; margin-right: 2mm; color: #fff; }}
  table.meta {{ border-collapse: collapse; width: 100%; font-size: 9.5pt; }}
  table.meta td {{ padding: 1.2mm 0; vertical-align: top; }}
  table.meta td.k {{ width: 32mm; color: #6b7280; }}
  .beschreibung {{ margin-top: 4mm; font-size: 9.5pt; line-height: 1.45;
                   border-top: 0.4pt solid #e5e7eb; padding-top: 3mm; }}
  .beschreibung .k {{ color: #6b7280; font-size: 8pt; text-transform: uppercase;
                      letter-spacing: 1pt; display: block; margin-bottom: 1.5mm; }}
  .fuss {{ position: absolute; bottom: 5mm; left: 14mm; right: 14mm;
           font-size: 7pt; color: #9ca3af; }}

  /* ── Untere Hälfte: Notizraster (A5 quer) ──────────────────────── */
  .notizen {{ height: 148.5mm; padding: 8mm 14mm 12mm 14mm; }}
  .notizen .k {{ color: #9ca3af; font-size: 8pt; text-transform: uppercase;
                 letter-spacing: 1pt; margin-bottom: 2mm; }}
  .raster {{
    height: 123mm; border: 0.4pt solid #d1d5db;
    background-image:
      linear-gradient(to right, #dbe0e5 0.35pt, transparent 0.35pt),
      linear-gradient(to bottom, #dbe0e5 0.35pt, transparent 0.35pt);
    background-size: 5mm 5mm;
  }}
</style></head>
<body>

  <div class="laufzettel">
    <div class="qr"><img src="{_qr_data_uri(qr_payload)}" alt="QR"></div>
    <div class="qr-id">{_esc(str(todo.get('id', ''))[:8])}</div>

    <p class="modul">{_esc(company_name or 'DeineZeit')} · Aufgabe</p>
    <h1>{_esc(todo.get('title'))}</h1>

    <div class="badges">
      <span class="badge" style="background:{status_color}">{_esc(status_label)}</span>
      <span class="badge" style="background:{prio_color}">{_esc(prio_label)}</span>
    </div>

    <table class="meta">
      <tr><td class="k">Fällig am</td><td><strong>{_esc(faellig)}</strong></td></tr>
      <tr><td class="k">Start</td><td>{_esc(_datum(todo.get('start_date')))}</td></tr>
      <tr><td class="k">Zugewiesen an</td><td>{_esc(todo.get('assignee_name') or '—')}</td></tr>
      <tr><td class="k">Erstellt von</td><td>{_esc(todo.get('created_by_name') or '—')}</td></tr>
      <tr><td class="k">Anhänge</td><td>{int(anhaenge)}</td></tr>
      {verkn_html}
    </table>

    {f'<div class="beschreibung"><span class="k">Beschreibung</span>{beschreibung}</div>' if beschreibung else ''}

    <div class="fuss">
      Gedruckt am {datetime.now().strftime('%d.%m.%Y, %H:%M')} Uhr ·
      Aufgaben-ID: {_esc(todo.get('id'))}
    </div>
  </div>

  <div class="notizen">
    <p class="k">Notizen</p>
    <div class="raster"></div>
  </div>

</body></html>"""

    return WeasyprintHTML(string=html).write_pdf()
