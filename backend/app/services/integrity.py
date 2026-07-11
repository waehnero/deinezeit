"""
Datenintegrität: zentrale Referenzprüfung für Stammdaten
========================================================

Stammdaten (EntityRecords: Kontakte, Projektzeiten, Artikel, …) werden aus
vielen Modulen heraus referenziert — bewusst ohne harte Foreign Keys, damit
die Stammdaten flexibel bleiben. Die Kehrseite: Die Datenbank verhindert
verwaiste Verweise nicht selbst.

Dieser Service ist die EINE Stelle, die alle bekannten Verweise kennt.
Regelwerk (Beschluss 2026-07-11):

  - Löschen von Stammdaten: nur Admin, und nur wenn KEINE Verweise existieren.
  - Mit Verweisen wird stattdessen ARCHIVIERT (entity_records.archived_at).
    Archivierte Datensätze verschwinden aus Listen/Auswahlfeldern, bleiben
    für die Historie erhalten und sind vom Admin wiederherstellbar.
  - Kontakte mit Belegen: endgültige Löschung ausschließlich über das
    DSGVO-Modul (Anonymisierung nach Aufbewahrungsfrist, services/gdpr.py).

WICHTIG für neue Module: Referenziert ein neues Modul entity_records,
muss hier ein Eintrag in REFERENCE_CHECKS ergänzt werden.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.zeiterfassung import TimeEntry, Stundenkonto
from app.models.invoice import Invoice, InvoicePosition
from app.models.projektplan import PlanningProject, Task, ChecklistItem
from app.models.aufgaben import Todo
from app.models.attachment import Attachment
from app.models.postecke import SocialPost


# key → (Anzeigename für Fehlermeldungen/UI, Zähl-Funktion)
REFERENCE_CHECKS = {
    "zeiteintraege": (
        "Zeiteinträge",
        lambda db, rid: db.query(TimeEntry).filter(
            or_(TimeEntry.project_id == rid, TimeEntry.contact_id == rid)
        ).count(),
    ),
    "stundenkonten": (
        "Stundenkonten",
        lambda db, rid: db.query(Stundenkonto).filter(
            Stundenkonto.project_id == rid).count(),
    ),
    "belege": (
        "Verkaufsbelege",
        lambda db, rid: db.query(Invoice).filter(
            or_(Invoice.contact_id == rid, Invoice.project_id == rid)
        ).count(),
    ),
    "belegpositionen": (
        "Belegpositionen (Artikel)",
        lambda db, rid: db.query(InvoicePosition).filter(
            InvoicePosition.article_id == rid).count(),
    ),
    "planungsprojekte": (
        "Projektplanungen",
        lambda db, rid: db.query(PlanningProject).filter(
            or_(PlanningProject.contact_id == rid,
                PlanningProject.masterdata_project_id == rid)
        ).count(),
    ),
    "planungsaufgaben": (
        "Planungsaufgaben",
        lambda db, rid: db.query(Task).filter(Task.contact_id == rid).count(),
    ),
    "checklistpunkte": (
        "Checklisten-Punkte",
        lambda db, rid: db.query(ChecklistItem).filter(
            ChecklistItem.assignee_contact_id == rid).count(),
    ),
    "aufgaben": (
        "Aufgaben",
        lambda db, rid: db.query(Todo).filter(Todo.record_id == rid).count(),
    ),
    "dateien": (
        "Dateien im Datacenter",
        lambda db, rid: db.query(Attachment).filter(
            Attachment.contact_id == rid).count(),
    ),
    "posts": (
        "Postecke-Posts",
        lambda db, rid: db.query(SocialPost).filter(
            SocialPost.kontakt_id == rid).count(),
    ),
}


def count_references(db: Session, record_id) -> dict:
    """Alle Verweise auf einen Stammdaten-Datensatz zählen.

    Rückgabe: {key: {"label": str, "count": int}} — nur Einträge mit count > 0.
    """
    result = {}
    for key, (label, fn) in REFERENCE_CHECKS.items():
        n = fn(db, record_id)
        if n:
            result[key] = {"label": label, "count": n}
    return result


def has_references(db: Session, record_id) -> bool:
    """True, sobald irgendein Modul auf den Datensatz verweist."""
    for _, fn in REFERENCE_CHECKS.values():
        if fn(db, record_id):
            return True
    return False


def references_summary(refs: dict) -> str:
    """'12 Zeiteinträge, 3 Verkaufsbelege, 2 Dateien im Datacenter'"""
    return ", ".join(f"{v['count']} {v['label']}" for v in refs.values())
