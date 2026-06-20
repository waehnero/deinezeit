"""
Projekt-Aufzeichnungstool (Projektplanung)
==========================================

Eigenständiges Planungsmodul, ähnlich MS Project / OpenProject,
aber mobile-first für rasche Erfassung am Handy.

Bewusst eigene, harte Tabellen (kein flexibles EntityRecord-JSONB),
weil Gantt, kritischer Pfad und Abhängigkeiten echte Felder und
Joins brauchen.

Lose Kopplung zum bestehenden System:
  - PlanningProject.masterdata_project_id  -> optional auf Stammdaten-Projekt
  - Task.id wird von TimeEntry.task_id referenziert (Zeit -> Aufgabe)

Hierarchie:
  - Task.parent_task_id ist selbstreferenzierend und damit BELIEBIG TIEF.
    Aktuell zeigt das UI nur flache Ebenen, die Datenstruktur unterstützt
    aber von Anfang an unbegrenzte Verschachtelung (Sammelvorgänge).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Date, ForeignKey, Text, Numeric
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


# ── Status- & Prioritäts-Standardwerte ────────────────────────────────────────
# Dies sind nur die DEFAULTS. Status/Prioritäten/Tags sind über die
# Projekt-Einstellungen (Setting-Tabelle) frei konfigurierbar; die API
# validiert daher NICHT mehr hart gegen diese Tupel.
TASK_STATUS = ("offen", "in_arbeit", "blockiert", "erledigt")
TASK_PRIORITY = ("niedrig", "mittel", "hoch", "kritisch")
# Abhängigkeitstypen wie in MS Project:
#   FS = Ende-Anfang, SS = Anfang-Anfang, FF = Ende-Ende, SF = Anfang-Ende
DEPENDENCY_TYPES = ("FS", "SS", "FF", "SF")


class ProjectTaskField(Base):
    """
    Frei definierbares Custom-Feld für Planungsaufgaben.
    Gleiche Logik wie TimeEntryField/FieldDefinition – über die
    Projekt-Einstellungen verwaltbar. Werte landen in Task.data[key].
    """
    __tablename__ = "planning_task_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    key = Column(String(100), nullable=False, unique=True)
    field_type = Column(String(30), nullable=False)   # text, number, date, dropdown, checkbox, textarea, url
    is_required = Column(Boolean, default=False)
    show_in_list = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    col_span = Column(Integer, default=12)
    options = Column(JSONB, nullable=True)            # für Dropdown
    placeholder = Column(String(200), nullable=True)
    default_value = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PlanningProject(Base):
    """
    Ein Planungsprojekt (Kopf). Bündelt Aufgaben, Meilensteine und Termine.
    Optional verknüpft mit einem Stammdaten-Projekt (EntityRecord), damit
    die Zeiterfassung weiterhin bebuchbar bleibt – aber ohne Zwang.
    """
    __tablename__ = "planning_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    # Lose Kopplung zum Stammdaten-Projekt (EntityRecord.id). Bewusst nur ID +
    # denormalisierter Name, keine harte ForeignKey – Stammdaten sind flexibel.
    masterdata_project_id = Column(UUID(as_uuid=True), nullable=True)
    masterdata_project_name = Column(String(300), nullable=True)

    # Auftraggeber / Kontakt (ebenfalls optional, EntityRecord.id)
    contact_id = Column(UUID(as_uuid=True), nullable=True)
    contact_name = Column(String(300), nullable=True)

    status = Column(String(30), default="offen", nullable=False)
    color = Column(String(20), nullable=True)          # z.B. "#3b82f6"

    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Falls dieses Projekt aus einer Aufgabe entstanden ist ("Zu Detailprojekt
    # machen"), verweist diese Spalte auf die auslösende Aufgabe.
    origin_task_id = Column(UUID(as_uuid=True), nullable=True)

    is_archived = Column(Boolean, default=False, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    tasks = relationship(
        "Task", back_populates="project",
        cascade="all, delete-orphan",
        order_by="Task.sort_order",
    )
    milestones = relationship(
        "Milestone", back_populates="project",
        cascade="all, delete-orphan",
        order_by="Milestone.due_date",
    )


class Task(Base):
    """
    Ein Vorgang/eine Aufgabe innerhalb eines Planungsprojekts.

    parent_task_id ist selbstreferenzierend -> beliebig tiefe Hierarchie
    (Sammelvorgänge). Eine Aufgabe ohne parent ist ein Top-Level-Vorgang.
    """
    __tablename__ = "planning_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Selbstreferenz für beliebig tiefe Verschachtelung
    parent_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_tasks.id", ondelete="CASCADE"),
        nullable=True,
    )

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(30), default="offen", nullable=False)
    priority = Column(String(30), default="mittel", nullable=False)

    # Verantwortlicher Benutzer (intern). Optional.
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assignee_name = Column(String(200), nullable=True)  # denormalisiert für schnelle Liste

    # Kontakt (EntityRecord aus Stammdaten, denormalisiert).
    # Default = Kontakt des Projekts; kann je Aufgabe überschrieben werden.
    contact_id = Column(UUID(as_uuid=True), nullable=True)
    contact_name = Column(String(300), nullable=True)

    start_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)

    # Schätzung (Soll) in Minuten. Ist-Stunden kommen aus TimeEntry.task_id.
    estimate_minutes = Column(Integer, nullable=True)

    # Fortschritt 0–100. Bei Sammelvorgängen kann er aus Kindern berechnet werden.
    progress = Column(Integer, default=0, nullable=False)

    # Markiert reine Meilenstein-Aufgaben (Dauer 0)
    is_milestone = Column(Boolean, default=False, nullable=False)

    # Sortierung innerhalb der gleichen Ebene
    sort_order = Column(Integer, default=0, nullable=False)

    # Erweiterbares Custom-Feld-JSON (gleiche Idee wie anderswo im System)
    data = Column(JSONB, nullable=False, default=dict)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("PlanningProject", back_populates="tasks")

    # Eltern/Kind-Beziehung (rekursiv)
    children = relationship(
        "Task",
        backref="parent",
        remote_side=[id],
        cascade="all",
        single_parent=False,
    )

    # Abhängigkeiten, bei denen DIESE Aufgabe der Nachfolger ist
    # (d.h. sie hängt von predecessor_id ab)
    dependencies = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
    )

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


class TaskDependency(Base):
    """
    Abhängigkeit zwischen zwei Aufgaben (für Reihenfolge & kritischen Pfad).
    successor hängt von predecessor ab.
    dep_type: FS (Standard), SS, FF, SF.
    lag_days: positiver oder negativer Versatz in Tagen.
    """
    __tablename__ = "planning_task_dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    predecessor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    successor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    dep_type = Column(String(2), default="FS", nullable=False)
    lag_days = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    successor = relationship(
        "Task",
        foreign_keys=[successor_id],
        back_populates="dependencies",
    )
    predecessor = relationship(
        "Task",
        foreign_keys=[predecessor_id],
    )


class ChecklistItem(Base):
    """
    Ein Checklisten-Element. Gehört wahlweise zu einem Projekt ODER zu einer
    Aufgabe (parent_type + parent_id). Kann optional einem Benutzer oder
    Stammdaten-Kontakt zugewiesen werden (für E-Mail-Benachrichtigung).
    """
    __tablename__ = "planning_checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    parent_type = Column(String(20), nullable=False)   # "project" | "task"
    parent_id = Column(UUID(as_uuid=True), nullable=False)

    text = Column(String(1000), nullable=False)
    is_done = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    # Zuweisung: entweder interner Benutzer ODER Stammdaten-Kontakt
    assignee_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assignee_contact_id = Column(UUID(as_uuid=True), nullable=True)
    assignee_name = Column(String(300), nullable=True)   # denormalisiert für Anzeige

    # Falls aus dem Element eine Aufgabe erzeugt wurde
    linked_task_id = Column(UUID(as_uuid=True), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class Milestone(Base):
    """
    Ein Meilenstein/Etappenziel eines Planungsprojekts.
    Eigene Tabelle (getrennt von Tasks) für die Roadmap-Ansicht.
    """
    __tablename__ = "planning_milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String(300), nullable=False)
    due_date = Column(Date, nullable=True)
    is_reached = Column(Boolean, default=False, nullable=False)
    color = Column(String(20), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("PlanningProject", back_populates="milestones")
