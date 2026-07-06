"""
DSGVO-Löschung (Anonymisierung) von Stammdaten-Kontakten
========================================================

Umsetzung von Art. 17 DSGVO durch Anonymisierung (von DSB Österreich und
BfDI als Löschung anerkannt): Der EntityRecord bleibt als Tombstone-Zeile
erhalten — data geleert, display_name ersetzt, anonymized_at gesetzt.
So verwaisen keine Verweise und alle Module bleiben konsistent.

Aufbewahrungspflichtige Belege (§ 132 BAO / § 147 AO) sind durch den
Empfänger-Snapshot auf der Rechnung (invoices.recipient_snapshot) abgedeckt
und bleiben unverändert reproduzierbar.

Ablauf:
  1. build_report()       — Betroffenheitsanalyse (auch Basis für Art. 15)
  2. check_blockers()     — Firmenkontakt / offene Belege / laufende Projekte
  3. anonymize_contact()  — Snapshot-Backfill, Anonymisierung, Löschprotokoll
"""
import uuid as uuid_mod
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.masterdata import EntityRecord, EntityType
from app.models.zeiterfassung import TimeEntry
from app.models.attachment import Attachment
from app.models.projektplan import PlanningProject, Task, ChecklistItem
from app.models.aufgaben import Todo
from app.models.invoice import Invoice
from app.models.settings import Setting
from app.models.gdpr import GdprDeletionLog
from app.services.invoice_snapshot import ensure_recipient_snapshot

ANONYM_NAME = "Gelöschter Kontakt"

# Nur RECHNUNGEN blockieren die Löschung — und nur solange sie weder bezahlt
# noch storniert sind. Der Status von Angeboten, Auftragsbestätigungen,
# Lieferscheinen sowie von Projekten/Aufgaben ist für die Löschung unerheblich.
INVOICE_DONE_STATUSES = ("bezahlt", "storniert")

# Standard-Aufbewahrungsfrist in Jahren (AT: § 132 BAO). Überschreibbar über
# die Einstellung "gdpr_retention_years" (DE: 10, § 147 AO).
DEFAULT_RETENTION_YEARS = 7


class GdprBlockedError(Exception):
    """Löschung nicht möglich — Blocker vorhanden (Details in .blockers)."""

    def __init__(self, blockers: list[dict]):
        self.blockers = blockers
        super().__init__("; ".join(b["label"] for b in blockers))


# ─────────────────────────────────────────────────────────────────────────────
# Hilfen
# ─────────────────────────────────────────────────────────────────────────────

def get_retention_years(db: Session) -> int:
    s = db.query(Setting).filter(Setting.key == "gdpr_retention_years").first()
    try:
        years = int(str(s.value).strip('"')) if s and s.value else DEFAULT_RETENTION_YEARS
        return years if years > 0 else DEFAULT_RETENTION_YEARS
    except (ValueError, TypeError):
        return DEFAULT_RETENTION_YEARS


def _retention_end(db: Session, record_id) -> Optional[date]:
    """
    Ende der Aufbewahrungsfrist: Die Frist beginnt mit Ende des Kalenderjahres
    des jüngsten finalisierten Belegs (§ 132 BAO) → löschbar ab 1.1. danach.
    """
    newest = db.query(Invoice.date).filter(
        Invoice.contact_id == record_id,
        Invoice.status != "entwurf",
    ).order_by(Invoice.date.desc()).first()
    if not newest or not newest[0]:
        return None
    return date(newest[0].year + get_retention_years(db) + 1, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Betroffenheitsanalyse
# ─────────────────────────────────────────────────────────────────────────────

def count_references(db: Session, record_id) -> dict:
    """Zählt alle Verweise auf den Kontakt (Grundlage für Report + Protokoll)."""
    return {
        "time_entries": db.query(TimeEntry).filter(
            TimeEntry.contact_id == record_id).count(),
        "invoices_total": db.query(Invoice).filter(
            Invoice.contact_id == record_id).count(),
        "invoices_open": db.query(Invoice).filter(
            Invoice.contact_id == record_id,
            Invoice.doc_type == "rechnung",
            Invoice.status.notin_(INVOICE_DONE_STATUSES)).count(),
        "invoices_retention": db.query(Invoice).filter(
            Invoice.contact_id == record_id,
            Invoice.status != "entwurf").count(),
        "planning_projects": db.query(PlanningProject).filter(
            PlanningProject.contact_id == record_id).count(),
        "planning_tasks": db.query(Task).filter(
            Task.contact_id == record_id).count(),
        "checklist_items": db.query(ChecklistItem).filter(
            ChecklistItem.assignee_contact_id == record_id).count(),
        "todos": db.query(Todo).filter(
            Todo.record_id == record_id).count(),
        "attachments": db.query(Attachment).filter(
            Attachment.contact_id == record_id).count(),
    }


def check_blockers(db: Session, record: EntityRecord) -> list[dict]:
    """Prüft, ob der Kontakt aktuell gelöscht (anonymisiert) werden darf."""
    blockers = []

    # 1. Eigener Firmenkontakt (Absender auf Belegen, Einstellungen)
    s = db.query(Setting).filter(Setting.key == "company_contact_id").first()
    if s and s.value and str(s.value).strip('"') == str(record.id):
        blockers.append({
            "code": "company_contact",
            "label": "Kontakt ist als eigener Firmenkontakt in den Einstellungen hinterlegt",
            "count": 1,
        })

    # 2. Nicht abgeschlossene RECHNUNGEN (weder bezahlt noch storniert).
    #    Angebote, Auftragsbestätigungen, Lieferscheine und der Status von
    #    Projekten/Aufgaben blockieren bewusst NICHT.
    open_count = db.query(Invoice).filter(
        Invoice.contact_id == record.id,
        Invoice.doc_type == "rechnung",
        Invoice.status.notin_(INVOICE_DONE_STATUSES),
    ).count()
    if open_count:
        blockers.append({
            "code": "open_invoices",
            "label": f"{open_count} Rechnung(en) weder bezahlt noch storniert — bitte zuerst abschließen",
            "count": open_count,
        })

    return blockers


def build_report(db: Session, record: EntityRecord) -> dict:
    """
    Betroffenheits-Report für einen Kontakt: was wird anonymisiert, was ist
    aufbewahrungspflichtig, was blockiert. Dient zugleich als Vorschau im
    Lösch-Wizard und als Grundlage für die Auskunft nach Art. 15 DSGVO.
    """
    et = db.query(EntityType).filter(EntityType.id == record.entity_type_id).first()
    retention_end = _retention_end(db, record.id)
    return {
        "record": {
            "id": str(record.id),
            "display_name": record.display_name,
            "entity_type_slug": et.slug if et else None,
            "data": dict(record.data or {}),
            "anonymized_at": record.anonymized_at.isoformat() if record.anonymized_at else None,
        },
        "categories": count_references(db, record.id),
        "blockers": check_blockers(db, record),
        "retention": {
            "years": get_retention_years(db),
            "deletable_after": retention_end.isoformat() if retention_end else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Anonymisierung (Kern der DSGVO-Löschung)
# ─────────────────────────────────────────────────────────────────────────────

def anonymize_contact(db: Session, record: EntityRecord,
                      executed_by: Optional[str] = None,
                      files_action: str = "none",
                      note: Optional[str] = None) -> dict:
    """
    Anonymisiert einen Kontakt und alle denormalisierten Kopien seines Namens.
    Wirft GdprBlockedError, wenn Blocker vorhanden sind.

    files_action: none | unlinked | deleted — das tatsächliche Löschen der
    Datacenter-Dateien (MinIO) übernimmt der API-Layer VOR diesem Aufruf;
    hier wird die Entscheidung nur protokolliert und der Kontaktbezug der
    (verbleibenden) Dateien anonymisiert.

    Kein Commit — der Aufrufer committet.
    """
    if record.anonymized_at:
        raise ValueError("Kontakt wurde bereits anonymisiert")

    blockers = check_blockers(db, record)
    if blockers:
        raise GdprBlockedError(blockers)

    categories = count_references(db, record.id)

    # 1. Belegaufbewahrung sichern: fehlende Empfänger-Snapshots nachziehen
    #    (Belege ab Version 1.12.x frieren beim Finalisieren automatisch ein;
    #    das hier fängt etwaigen Altbestand ab)
    snapshotted = 0
    finalized = db.query(Invoice).filter(
        Invoice.contact_id == record.id,
        Invoice.status != "entwurf",
        Invoice.recipient_snapshot.is_(None),
    ).all()
    for inv in finalized:
        ensure_recipient_snapshot(db, inv, source="gdpr_erase")
        if inv.recipient_snapshot:
            snapshotted += 1
    categories["invoices_snapshotted"] = snapshotted

    # 2. Denormalisierte Namen ersetzen (IDs bleiben → nichts verwaist)
    db.query(TimeEntry).filter(TimeEntry.contact_id == record.id).update(
        {TimeEntry.contact_name: ANONYM_NAME}, synchronize_session=False)
    db.query(Attachment).filter(Attachment.contact_id == record.id).update(
        {Attachment.contact_name: ANONYM_NAME}, synchronize_session=False)
    db.query(PlanningProject).filter(PlanningProject.contact_id == record.id).update(
        {PlanningProject.contact_name: ANONYM_NAME}, synchronize_session=False)
    db.query(Task).filter(Task.contact_id == record.id).update(
        {Task.contact_name: ANONYM_NAME}, synchronize_session=False)
    db.query(ChecklistItem).filter(ChecklistItem.assignee_contact_id == record.id).update(
        {ChecklistItem.assignee_name: ANONYM_NAME}, synchronize_session=False)
    db.query(Todo).filter(Todo.record_id == record.id).update(
        {Todo.record_name: ANONYM_NAME}, synchronize_session=False)

    # 3. Tombstone: Datensatz selbst anonymisieren
    record.data = {}
    record.display_name = ANONYM_NAME
    record.anonymized_at = datetime.now(timezone.utc)

    # 4. Löschprotokoll (Art. 5 Abs. 2 — ohne personenbezogene Daten)
    log = GdprDeletionLog(
        id=uuid_mod.uuid4(),
        record_id=record.id,
        executed_by=executed_by,
        executed_at=record.anonymized_at,
        categories=categories,
        files_action=files_action,
        note=note,
    )
    db.add(log)
    db.flush()

    return categories
