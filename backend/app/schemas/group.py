"""
Schemas für die Rechtegruppen (Migration 0055).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class GroupBase(BaseModel):
    name: str
    beschreibung: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_pruefen(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Bitte einen Gruppennamen angeben.")
        if len(v) > 100:
            raise ValueError("Der Gruppenname darf höchstens 100 Zeichen lang sein.")
        return v


class GroupCreate(GroupBase):
    """Neue Gruppe.

    ``rechte`` ist schemafrei und wird serverseitig auf das erlaubte Raster
    gezogen (``core/berechtigungen.blatt_bereinigen``). Eine Pydantic-Struktur
    je Modul wäre eine zweite Liste, die mit ``core/modules.py`` auseinander
    läuft, sobald ein Modul dazukommt.
    """
    rechte: Optional[dict] = None
    #: Optional direkt Mitglieder zuweisen.
    user_ids: Optional[list[UUID]] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    beschreibung: Optional[str] = None
    rechte: Optional[dict] = None
    user_ids: Optional[list[UUID]] = None

    @field_validator("name")
    @classmethod
    def name_pruefen(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Bitte einen Gruppennamen angeben.")
        return v[:100]


class GroupMember(BaseModel):
    id: UUID
    full_name: str
    email: str

    class Config:
        from_attributes = True


class GroupResponse(GroupBase):
    id: UUID
    rechte: dict
    ist_system: bool
    sort_order: int
    created_at: datetime
    #: Mitglieder — die Oberfläche zeigt vor jeder Änderung, wen sie betrifft.
    mitglieder: list[GroupMember] = []

    class Config:
        from_attributes = True


class EffektiveRechteResponse(BaseModel):
    """Die maßgeblichen Rechte eines Benutzers samt Herkunft.

    Die Herkunft ist der Grund, warum es diesen Endpunkt gibt: Bei Gruppen plus
    individuellen Ausnahmen kann niemand mehr im Kopf ausrechnen, warum jemand
    etwas darf. Ohne diese Auskunft wird die Rechteverwaltung zur Ratesache —
    und dann wird im Zweifel zu viel vergeben.
    """
    user_id: UUID
    #: Rechteblatt je Modul (lesen/schreiben/loeschen/umfang)
    rechte: dict
    #: Rolle — Administratoren haben ohne Gruppe alles
    role: str
    gruppen: list[str] = []
    #: Individuelle Abweichungen, die auf die Gruppenrechte angewendet wurden
    ausnahmen: Optional[dict] = None
    #: Module mit Lesezugriff (Grundlage für das Menü)
    module: list[str] = []


class UserGroupsUpdate(BaseModel):
    """Gruppenzugehörigkeit eines Benutzers setzen (ersetzt die bisherige)."""
    group_ids: list[UUID]


class PermissionOverridesUpdate(BaseModel):
    """Individuelle Ausnahmen eines Benutzers setzen.

    ``None`` löscht alle Ausnahmen — der Benutzer erhält dann genau die Rechte
    seiner Gruppen.
    """
    overrides: Optional[dict] = None
