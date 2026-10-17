"""
Pydantic-Schemas für den Mail-Import (Aufgabenmodul, Etappe 3).
"""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ── Mail-Konten ───────────────────────────────────────────────────────────────
class MailAccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    protocol: str = Field(pattern="^(imap|graph)$")
    # IMAP
    imap_host: Optional[str] = Field(default=None, max_length=255)
    imap_port: Optional[int] = Field(default=None, ge=1, le=65535)
    # True = TLS direkt (993), False = STARTTLS (143, Pflicht). Unverschlüsselt
    # gibt es nicht mehr (services/mail_sicherheit.py).
    imap_ssl: bool = True
    imap_user: Optional[str] = Field(default=None, max_length=255)
    # Microsoft Graph
    graph_tenant_id: Optional[str] = Field(default=None, max_length=100)
    graph_client_id: Optional[str] = Field(default=None, max_length=100)
    graph_mailbox: Optional[str] = Field(default=None, max_length=255)
    folder: str = Field(default="INBOX", max_length=300)
    # Zugangsdaten aus Einstellungen -> System -> E-Mail verwenden.
    # Nur an globalen Konten (Admin) zulässig — siehe api/mailimport.py.
    use_central_credentials: bool = False
    # Nur Graph: Mail nach Übernahme in Outlook als erledigt kennzeichnen
    flag_erledigt: bool = False
    auto_scan: bool = False
    scan_interval_minutes: int = Field(default=15, ge=5, le=1440)
    is_active: bool = True


class MailAccountCreate(MailAccountBase):
    # Klartext nur beim Anlegen/Ändern — wird sofort verschlüsselt gespeichert
    secret: Optional[str] = None
    # Nur Admin: globales Konto (owner_user_id = NULL)
    is_global: bool = False
    # Nur Admin, nur globale Konten: wer das Konto verwenden darf
    freigabe_alle: bool = False
    freigabe_gruppen: List[UUID] = Field(default_factory=list)


class MailAccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    imap_host: Optional[str] = Field(default=None, max_length=255)
    imap_port: Optional[int] = Field(default=None, ge=1, le=65535)
    imap_ssl: Optional[bool] = None
    imap_user: Optional[str] = Field(default=None, max_length=255)
    graph_tenant_id: Optional[str] = Field(default=None, max_length=100)
    graph_client_id: Optional[str] = Field(default=None, max_length=100)
    graph_mailbox: Optional[str] = Field(default=None, max_length=255)
    folder: Optional[str] = Field(default=None, max_length=300)
    use_central_credentials: Optional[bool] = None
    freigabe_alle: Optional[bool] = None
    freigabe_gruppen: Optional[List[UUID]] = None
    flag_erledigt: Optional[bool] = None
    auto_scan: Optional[bool] = None
    scan_interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    is_active: Optional[bool] = None
    secret: Optional[str] = None   # neues Geheimnis; None = unverändert


class MailAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: Optional[UUID] = None
    name: str
    protocol: str
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_ssl: bool
    imap_user: Optional[str] = None
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_mailbox: Optional[str] = None
    folder: str
    use_central_credentials: bool = False
    flag_erledigt: bool = False
    auto_scan: bool
    scan_interval_minutes: int
    last_scan_at: Optional[datetime] = None
    last_error: Optional[str] = None
    is_active: bool
    has_secret: bool = False       # ob ein Geheimnis hinterlegt ist (nie der Wert selbst)
    # Zentrale Zugangsdaten: None = nutzbar bzw. nicht verwendet, sonst der
    # Grund der Sperre (verständlicher Hinweis für die Oberfläche)
    zentral_sperrgrund: Optional[str] = None
    zentral_bestaetigt_am: Optional[str] = None
    # Freigabe globaler Konten — nur für Admins befüllt
    freigabe_alle: Optional[bool] = None
    freigabe_gruppen: Optional[List[str]] = None


class MailSicherheitResponse(BaseModel):
    """Admin: Vertrauens- und Zielregeln für Mailverbindungen."""
    interne_ziele: List[str] = []
    ca_zertifikate: str = ""


class MailSicherheitUpdate(BaseModel):
    interne_ziele: List[str] = Field(default_factory=list, max_length=100)
    ca_zertifikate: str = Field(default="", max_length=200_000)


# ── Vorschläge ────────────────────────────────────────────────────────────────
class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    account_name: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    received_at: Optional[datetime] = None
    body_preview: Optional[str] = None
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    status: str
    todo_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    # Nur in der accept-Antwort gesetzt: wurde die Ursprungs-Mail in Outlook
    # als erledigt gekennzeichnet? (None = nicht versucht)
    mail_flagged: Optional[bool] = None


class SuggestionAccept(BaseModel):
    """Optionale Übersteuerung der KI-Werte beim Übernehmen."""
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assignee_id: Optional[UUID] = None


class ScanResult(BaseModel):
    account_id: UUID
    neue_vorschlaege: int


# ── KI-Einstellungen ──────────────────────────────────────────────────────────
class KiSettingsResponse(BaseModel):
    provider: str = "anthropic"
    model: Optional[str] = None
    has_api_key: bool = False      # Key selbst wird nie zurückgegeben


class KiSettingsUpdate(BaseModel):
    provider: str = Field(pattern="^(anthropic|openai)$")
    model: Optional[str] = None
    api_key: Optional[str] = None  # None = bestehenden Key behalten
