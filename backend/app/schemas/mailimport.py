"""
Pydantic-Schemas für den Mail-Import (Aufgabenmodul, Etappe 3).
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ── Mail-Konten ───────────────────────────────────────────────────────────────
class MailAccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    protocol: str = Field(pattern="^(imap|graph)$")
    # IMAP
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_ssl: bool = True
    imap_user: Optional[str] = None
    # Microsoft Graph
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_mailbox: Optional[str] = None
    folder: str = "INBOX"
    # Zugangsdaten aus Einstellungen -> System -> E-Mail verwenden
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


class MailAccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_ssl: Optional[bool] = None
    imap_user: Optional[str] = None
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_mailbox: Optional[str] = None
    folder: Optional[str] = None
    use_central_credentials: Optional[bool] = None
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
