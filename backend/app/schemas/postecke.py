"""Pydantic-Schemas für das Modul Postecke (Social Media)."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.postecke import KANAELE, POST_STATUS, BILD_FORMATE, BILD_FILTER


# ── Profile ───────────────────────────────────────────────────────────────────
class ProfilBase(BaseModel):
    name: str
    kanal: str
    stil_prompt: Optional[str] = None
    bild_format: str = "original"
    bild_filter: str = "kein"
    is_active: bool = True

    @field_validator("kanal")
    @classmethod
    def kanal_gueltig(cls, v: str) -> str:
        if v not in KANAELE:
            raise ValueError(f"Ungültiger Kanal (erlaubt: {', '.join(KANAELE)})")
        return v

    @field_validator("bild_format")
    @classmethod
    def format_gueltig(cls, v: str) -> str:
        if v not in BILD_FORMATE:
            raise ValueError(f"Ungültiges Bildformat (erlaubt: {', '.join(BILD_FORMATE)})")
        return v

    @field_validator("bild_filter")
    @classmethod
    def filter_gueltig(cls, v: str) -> str:
        if v not in BILD_FILTER:
            raise ValueError(f"Ungültiger Filter (erlaubt: {', '.join(BILD_FILTER)})")
        return v


class ProfilZugang(BaseModel):
    """Zugangsdaten für die Direktanbindung (aktuell: Facebook-Seite)."""
    page_id: str
    page_token: str


class ProfilCreate(ProfilBase):
    # Optional: Zugangsdaten für die Direktanbindung (werden verschlüsselt)
    zugang: Optional[ProfilZugang] = None


class ProfilUpdate(BaseModel):
    name: Optional[str] = None
    kanal: Optional[str] = None
    stil_prompt: Optional[str] = None
    bild_format: Optional[str] = None
    bild_filter: Optional[str] = None
    is_active: Optional[bool] = None
    # Zugangsdaten nur bei Änderung mitschicken; None = unverändert lassen
    zugang: Optional[ProfilZugang] = None

    @field_validator("kanal")
    @classmethod
    def kanal_gueltig(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in KANAELE:
            raise ValueError(f"Ungültiger Kanal (erlaubt: {', '.join(KANAELE)})")
        return v

    @field_validator("bild_format")
    @classmethod
    def format_gueltig(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in BILD_FORMATE:
            raise ValueError(f"Ungültiges Bildformat (erlaubt: {', '.join(BILD_FORMATE)})")
        return v

    @field_validator("bild_filter")
    @classmethod
    def filter_gueltig(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in BILD_FILTER:
            raise ValueError(f"Ungültiger Filter (erlaubt: {', '.join(BILD_FILTER)})")
        return v


class ProfilResponse(ProfilBase):
    id: UUID
    # Zugangsdaten hinterlegt? (die Daten selbst verlassen den Server nie)
    has_zugang: bool = False
    # Kanal direkt angebunden UND Zugangsdaten da -> automatisches Posten möglich
    direktanbindung: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Fotos ─────────────────────────────────────────────────────────────────────
class FotoResponse(BaseModel):
    id: UUID
    filename: str
    mimetype: str
    size_bytes: Optional[int] = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


# ── Posts ─────────────────────────────────────────────────────────────────────
class PostCreate(BaseModel):
    profil_id: Optional[UUID] = None
    titel: Optional[str] = None
    beschreibung: Optional[str] = None
    kontakt_id: Optional[UUID] = None
    kontakt_name: Optional[str] = None


class PostUpdate(BaseModel):
    profil_id: Optional[UUID] = None
    titel: Optional[str] = None
    beschreibung: Optional[str] = None
    text: Optional[str] = None
    hashtags: Optional[str] = None
    ort: Optional[str] = None
    gefuehl: Optional[str] = None
    kontakt_id: Optional[UUID] = None
    kontakt_name: Optional[str] = None


class PostStatusUpdate(BaseModel):
    status: str
    geplant_am: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def status_gueltig(cls, v: str) -> str:
        if v not in POST_STATUS:
            raise ValueError(f"Ungültiger Status (erlaubt: {', '.join(POST_STATUS)})")
        return v


class PostResponse(BaseModel):
    id: UUID
    profil_id: Optional[UUID] = None
    titel: Optional[str] = None
    beschreibung: Optional[str] = None
    text: Optional[str] = None
    hashtags: Optional[str] = None
    ort: Optional[str] = None
    gefuehl: Optional[str] = None
    kontakt_id: Optional[UUID] = None
    kontakt_name: Optional[str] = None
    status: str
    geplant_am: Optional[datetime] = None
    veroeffentlicht_am: Optional[datetime] = None
    ki_model: Optional[str] = None
    extern_url: Optional[str] = None
    publish_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    fotos: List[FotoResponse] = []

    model_config = ConfigDict(from_attributes=True)


# ── KI-Generierung ────────────────────────────────────────────────────────────
class GenerierenRequest(BaseModel):
    # Optional: abweichende Beschreibung nur für diesen Aufruf
    beschreibung: Optional[str] = None


class GenerierenResponse(BaseModel):
    text: str
    hashtags: Optional[str] = None
    ort: Optional[str] = None
    gefuehl: Optional[str] = None
    titel: Optional[str] = None
    ki_model: Optional[str] = None
