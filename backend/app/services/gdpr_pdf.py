"""
PDF-Löschbericht für DSGVO-Löschungen
=====================================

Zwei Varianten aus demselben Löschvorgang:

  - "personal":   Löschbescheinigung für die betroffene Person (enthält
                  deren Namen/Daten — wird NUR als Download übergeben und
                  nirgends gespeichert, sonst wäre die Löschung ausgehebelt).
  - "anonymized": Ablage-Version für das Datacenter des Mandanten — ohne
                  Personenbezug (nur Vorgangs-ID, Kategorien, Fristen).
"""
from datetime import datetime
from typing import Optional

from weasyprint import HTML as WeasyprintHTML

CATEGORY_LABELS = {
    "time_entries":         "Zeiteinträge",
    "invoices_total":       "Belege gesamt (Rechnungen, Angebote, …)",
    "invoices_retention":   "davon aufbewahrungspflichtig (Empfänger eingefroren)",
    "invoices_snapshotted": "davon Snapshot beim Löschvorgang nachgezogen",
    "planning_projects":    "Planungsprojekte",
    "planning_tasks":       "Projektaufgaben",
    "checklist_items":      "Checklisten-Zuweisungen",
    "todos":                "Aufgaben (To-dos)",
    "attachments":          "Datacenter-Dateien",
}

FILES_ACTION_LABELS = {
    "deleted": "Zugeordnete Dateien wurden endgültig gelöscht.",
    "none":    "Zugeordnete Dateien wurden beibehalten; der Kontaktbezug wurde anonymisiert.",
}


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def build_erasure_pdf(*, variant: str, report: dict, log_id: str,
                      executed_at: datetime, executed_by: Optional[str],
                      files_action: str, company_name: str,
                      company_lines: Optional[list[str]] = None,
                      note: Optional[str] = None) -> bytes:
    """
    Erzeugt den Löschbericht als PDF.
    variant: "personal" | "anonymized"
    report:  Betroffenheits-Report (gdpr.build_report), VOR der Anonymisierung
             erstellt — nur die personal-Variante nutzt die Personendaten.
    """
    personal = variant == "personal"
    cats = report.get("categories", {})
    retention = report.get("retention", {})
    rec = report.get("record", {})

    rows = ""
    for key, label in CATEGORY_LABELS.items():
        if key in cats:
            rows += f"<tr><td>{label}</td><td class='r'>{cats[key]}</td></tr>"

    # Betroffenen-Block nur in der persönlichen Variante
    person_html = ""
    if personal:
        d = rec.get("data") or {}
        detail_lines = []
        for k in ("ansprechperson", "adresse", "plz", "ort", "land", "email", "telefon", "uid"):
            if d.get(k):
                detail_lines.append(str(d[k]))
        details = "<br>".join(detail_lines)
        person_html = f"""
        <h2>Betroffene Person / Organisation</h2>
        <p><strong>{rec.get('display_name') or '—'}</strong><br>{details}</p>"""

    company_html = "<br>".join(company_lines or [company_name])

    retention_html = ""
    if retention.get("deletable_after"):
        retention_html = f"""
        <p>Aufbewahrungspflichtige Belegdaten (Name und Anschrift auf Rechnungen
        und Gutschriften) bleiben gemäß § 132 BAO bzw. § 147 AO als eingefrorener
        Beleg-Bestandteil erhalten (Aufbewahrungsfrist:
        {retention.get('years', 7)} Jahre) und werden nach Fristablauf
        (<strong>{_fmt_date(retention['deletable_after'])}</strong>) endgültig gelöscht.
        Eine Verwendung für andere Zwecke ist ausgeschlossen
        (Art. 18 DSGVO — Einschränkung der Verarbeitung).</p>"""

    files_html = FILES_ACTION_LABELS.get(files_action, "")
    note_html = f"<p>Anmerkung: {note}</p>" if (note and personal) else ""

    title = ("Löschbescheinigung gemäß Art. 17 DSGVO" if personal
             else "Löschprotokoll (anonymisiert) — Art. 17 DSGVO")

    subject_html = "" if personal else f"""
    <p>Betroffener Datensatz (anonymisiert): <code>{rec.get('id', '—')}</code><br>
    Dieses Protokoll enthält bewusst keine personenbezogenen Daten
    (Rechenschaftspflicht, Art. 5 Abs. 2 DSGVO).</p>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 2.2cm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #222; }}
  h1 {{ font-size: 17px; margin: 0 0 2px 0; }}
  h2 {{ font-size: 12px; margin: 18px 0 4px 0; }}
  p  {{ line-height: 1.5; margin: 6px 0; }}
  .meta {{ color: #666; font-size: 10px; margin-bottom: 18px; }}
  .sender {{ font-size: 10px; color: #444; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 4px 0; }}
  th {{ background: #f3f4f6; text-align: left; padding: 5px 8px;
       border-bottom: 2px solid #d1d5db; font-size: 10px; }}
  td {{ padding: 4px 8px; border-bottom: 1px solid #e5e7eb; }}
  .r {{ text-align: right; }}
  code {{ font-family: monospace; font-size: 10px; }}
  .footer {{ margin-top: 30px; padding-top: 8px; border-top: 1px solid #e5e7eb;
             font-size: 9px; color: #888; }}
</style></head><body>
  <div class="sender">{company_html}</div>
  <h1>{title}</h1>
  <p class="meta">Vorgangs-ID: <code>{log_id}</code> &nbsp;|&nbsp;
     Durchgeführt am {executed_at.strftime('%d.%m.%Y um %H:%M Uhr (UTC)')}
     {('durch ' + executed_by) if executed_by else ''}</p>

  {person_html}
  {subject_html}

  <h2>Durchgeführte Löschung</h2>
  <p>Die personenbezogenen Daten wurden durch vollständige Anonymisierung
  gelöscht (Art. 17 DSGVO). Der Personenbezug wurde in allen Modulen der
  Anwendung entfernt; eine Re-Identifizierung ist ausgeschlossen.</p>
  <table>
    <thead><tr><th>Kategorie</th><th class="r">Anzahl</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p>{files_html}</p>
  {retention_html}
  {note_html}

  <div class="footer">
    Erstellt mit DeineZeit — {company_name}. Dieses Dokument wurde maschinell
    erstellt und ist ohne Unterschrift gültig.
  </div>
</body></html>"""

    return WeasyprintHTML(string=html).write_pdf()
