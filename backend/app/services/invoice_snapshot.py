"""
Empfänger-Snapshot für Belege (DSGVO / Belegaufbewahrung)
=========================================================

Belege unterliegen der Aufbewahrungspflicht (§ 132 BAO / § 147 AO) und
müssen unverändert reproduzierbar bleiben. Deshalb werden die Empfänger-
daten beim Finalisieren eines Belegs (Status verlässt 'entwurf') aus dem
Stammdaten-Kontakt (EntityRecord) in `invoices.recipient_snapshot`
eingefroren.

Ab dann rendern PDF und HTML-Vorschau aus dem Snapshot — spätere
Kontakt-Änderungen oder eine DSGVO-Anonymisierung des Kontakts verändern
den Beleg nicht mehr.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from app.models.invoice import Invoice
from app.models.masterdata import EntityRecord


def build_recipient_snapshot(record: EntityRecord, source: str = "finalize") -> dict:
    """Erzeugt das Snapshot-Dict aus einem Stammdaten-Kontakt."""
    return {
        "display_name": record.display_name or "",
        "data": dict(record.data or {}),
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
    }


def snapshot_as_contact(snapshot: Optional[dict]):
    """
    Macht aus dem Snapshot-Dict ein Objekt mit .display_name und .data —
    dieselbe Schnittstelle wie EntityRecord, damit invoice_pdf.py und
    E-Mail-Platzhalter unverändert funktionieren.
    """
    if not snapshot:
        return None
    return SimpleNamespace(
        display_name=snapshot.get("display_name") or "",
        data=snapshot.get("data") or {},
    )


def ensure_recipient_snapshot(db: Session, invoice: Invoice,
                              force: bool = False, source: str = "finalize") -> None:
    """
    Friert die Empfängerdaten auf dem Beleg ein, falls noch kein Snapshot
    existiert (oder force=True, z.B. wenn auf einem finalisierten Beleg der
    Kontakt getauscht wurde). Kein Commit — der Aufrufer committet.
    """
    if invoice.recipient_snapshot and not force:
        return
    if not invoice.contact_id:
        return
    record = db.query(EntityRecord).filter(
        EntityRecord.id == invoice.contact_id
    ).first()
    if not record:
        return
    invoice.recipient_snapshot = build_recipient_snapshot(record, source=source)
