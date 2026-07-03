"""
Aufgabenmodul (umfassende To-do-Liste)
======================================

Zentrale, projektunabhängige Aufgabenverwaltung mit losen Verknüpfungen
in alle bestehenden Domänen (gleiche Philosophie wie Projektplan):

  - Todo.planning_project_id / planning_task_id  -> Projektplan (optional)
  - Todo.time_entry_id                           -> Zeiterfassung (optional)
  - Todo.record_id (+ record_type_slug)          -> Stammdaten-Datensatz
                                                    (Kontakt, Artikel, Projekt …)

Verknüpfungen sind bewusst OHNE harte ForeignKeys umgesetzt (nur UUID +
denormalisierter Anzeigename), damit die Domänen entkoppelt bleiben —
identisch zu PlanningProject.masterdata_project_id.

Für Etappe 3 (Mail-Ingest per KI) sind `source` und `source_meta` bereits
vorgesehen: Aufgaben aus E-Mails tragen source="email" und im JSONB die
Herkunftsdaten (Mailbox, Message-ID, Betreff, …).

Status/Prioritäten sind wie beim Projektplan NUR Defaults — über die
Einstellungen (Setting-Key "aufgaben_settings") frei konfigurierbar,
die API validiert daher nicht hart gegen diese Tupel.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Date, Time, ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


# ── Standardwerte (Defaults, konfigurierbar über Einstellungen) ──────────────
TODO_STATUS = ("offen", "in_arbeit", "wartet", "erledigt")
TODO_PRIORITY = ("niedrig", "mittel", "hoch", "kritisch")

# Herkunft einer Aufgabe (Etappe 3: "email" = per KI aus Mailbox übernommen)
TODO_SOURCES = ("manuell", "email")


class Todo(Base):
    """Eine Aufgabe der zentralen To-do-Liste."""

    __tablename__ = "todos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(30), default="offen", nullable=False)
    priority = Column(String(30), default="mittel", nullable=False)

    # Terminierung. due_time optional (für Kalender-Wochenansichten).
    start_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    due_time = Column(Time, nullable=True)

    # Zeitpunkt der Erledigung (gesetzt, wenn Status auf "erledigt" wechselt)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Zuweisung an internen Benutzer (optional)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assignee_name = Column(String(200), nullable=True)  # denormalisiert für Listen

    # ── Lose Verknüpfungen (UUID + denormalisierter Name, keine FKs) ──────────
    # Projektplan
    planning_project_id = Column(UUID(as_uuid=True), nullable=True)
    planning_project_name = Column(String(300), nullable=True)
    planning_task_id = Column(UUID(as_uuid=True), nullable=True)
    planning_task_title = Column(String(500), nullable=True)

    # Zeiterfassung
    time_entry_id = Column(UUID(as_uuid=True), nullable=True)

    # Stammdaten-Datensatz (EntityRecord: Kontakt, Artikel, Projekt, …)
    record_id = Column(UUID(as_uuid=True), nullable=True)
    record_name = Column(String(300), nullable=True)
    record_type_slug = Column(String(100), nullable=True)  # z.B. "kontakte", "artikel"

    # ── Herkunft (Etappe 3: Mail-Ingest) ──────────────────────────────────────
    source = Column(String(30), default="manuell", nullable=False)
    source_meta = Column(JSONB, nullable=True)  # z.B. {mailbox, message_id, subject}

    # Sortierung (Kanban-Spalten / manuelle Reihung in der Liste)
    sort_order = Column(Integer, default=0, nullable=False)

    # Erweiterbares JSON für spätere Custom-Felder (gleiche Idee wie anderswo)
    data = Column(JSONB, nullable=False, default=dict)

    is_archived = Column(Boolean, default=False, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_name = Column(String(200), nullable=True)  # denormalisiert
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
