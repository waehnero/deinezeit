"""
Mail-Import (Aufgabenmodul, Etappe 3)
=====================================

Anbindung von Mailbox-Ordnern (IMAP oder Microsoft Graph), aus deren
Nachrichten ein KI-Assistent Aufgabenvorschläge extrahiert. Vorschläge
werden erst nach Bestätigung als Todo übernommen (source="email").

Konten:
  - owner_user_id gesetzt  -> persönliches Konto (nur der Besitzer)
  - owner_user_id = NULL   -> globales Konto (verwaltet der Admin,
                              Vorschläge sehen alle Benutzer)

Zugangsdaten (IMAP-Passwort bzw. Graph-Client-Secret) werden NIE im
Klartext gespeichert, sondern mit einem aus SECRET_KEY abgeleiteten
Fernet-Schlüssel verschlüsselt (services/mail_ingest.py).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, ForeignKey, Text, Date
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base

MAIL_PROTOCOLS = ("imap", "graph")
SUGGESTION_STATUS = ("offen", "uebernommen", "verworfen")


class MailAccount(Base):
    """Eine angebundene Mailbox (ein Ordner wird gescannt)."""

    __tablename__ = "mail_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # NULL = globales Konto (Admin), sonst persönliches Konto
    owner_user_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    name = Column(String(200), nullable=False)          # Anzeigename, z.B. "Office-Postfach"
    protocol = Column(String(10), nullable=False)       # imap | graph

    # ── IMAP (unkritische Felder im Klartext) ─────────────────────────────────
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, nullable=True)          # Default 993 (SSL)
    imap_ssl = Column(Boolean, default=True, nullable=False)
    imap_user = Column(String(255), nullable=True)

    # ── Microsoft Graph (Client-Credentials-Flow) ─────────────────────────────
    graph_tenant_id = Column(String(100), nullable=True)
    graph_client_id = Column(String(100), nullable=True)
    graph_mailbox = Column(String(255), nullable=True)  # z.B. office@firma.at

    # Verschlüsseltes Geheimnis (IMAP-Passwort bzw. Graph-Client-Secret)
    secret_enc = Column(Text, nullable=True)

    # Zugangsdaten aus der zentralen E-Mail-Konfiguration verwenden
    # (Einstellungen -> System -> E-Mail: ms_tenant_id/ms_client_id/
    #  ms_client_secret bzw. smtp_user/smtp_password). Dann sind die
    #  kontoeigenen Zugangsdaten/secret_enc nicht nötig.
    use_central_credentials = Column(Boolean, default=False, nullable=False)

    # Zu scannender Ordner (IMAP-Ordnername bzw. Graph-Ordnername/-ID)
    folder = Column(String(300), nullable=False, default="INBOX")

    # ── Auto-Scan ─────────────────────────────────────────────────────────────
    auto_scan = Column(Boolean, default=False, nullable=False)
    scan_interval_minutes = Column(Integer, default=15, nullable=False)
    last_scan_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class MailTaskSuggestion(Base):
    """
    Ein KI-Aufgabenvorschlag aus einer E-Mail. Pro Mail können mehrere
    Vorschläge entstehen (eine Zeile je Vorschlag). Die Kombination
    (account_id, message_id) verhindert doppelte Verarbeitung über
    den Unique-Index in der Migration NICHT — Duplikate werden über
    message_id-Prüfung vor der KI-Analyse vermieden (mehrere Vorschläge
    je Mail sind ja erlaubt).
    """

    __tablename__ = "mail_task_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    account_id = Column(UUID(as_uuid=True),
                        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False)

    # Herkunft (Mail-Metadaten)
    message_id = Column(String(500), nullable=False)   # Message-ID bzw. Graph-ID
    subject = Column(String(1000), nullable=True)
    sender = Column(String(500), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    body_preview = Column(Text, nullable=True)         # gekürzter Klartext für die Anzeige

    # ── KI-Vorschlag ──────────────────────────────────────────────────────────
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    priority = Column(String(30), nullable=True)

    status = Column(String(20), default="offen", nullable=False)  # offen|uebernommen|verworfen
    todo_id = Column(UUID(as_uuid=True), nullable=True)           # nach Übernahme

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
