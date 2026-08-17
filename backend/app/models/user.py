import uuid
from datetime import datetime, timezone
from sqlalchemy import (Column, String, Boolean, DateTime, Enum, ForeignKey,
                        Text, LargeBinary, Integer, Index, Table)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    employee = "employee"


#: Zuordnung Benutzer ↔ Gruppe (Migration 0055).
#: Eine eigene Zwischentabelle statt einer Liste am Benutzer, weil beide
#: Richtungen gebraucht werden: „welche Rechte hat dieser Mitarbeiter" und
#: „wer ist in dieser Gruppe" — Letzteres, bevor man eine Gruppe ändert.
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True),
           ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", UUID(as_uuid=True),
           ForeignKey("permission_groups.id", ondelete="CASCADE"),
           primary_key=True),
    Column("created_at", DateTime(timezone=True),
           default=lambda: datetime.now(timezone.utc)),
)


class PermissionGroup(Base):
    """Eine Rechtegruppe, z. B. „Buchhaltung" (Migration 0055).

    Die Rechte liegen als JSONB (``rechte``) und nicht in einer Tabelle mit
    einer Zeile je Modul und Recht. Begründung: Der Modulkatalog lebt im Code
    (``core/modules.py``), ein neues Modul soll keine Migration und keine
    Datenpflege auslösen. Das Format prüft
    ``core/berechtigungen.blatt_bereinigen()`` beim Schreiben — bei JSONB gibt
    es keine Spaltenprüfung, die einen Tippfehler abfängt.

    Aufbau::

        {"verkauf": {"lesen": true, "schreiben": true,
                     "loeschen": false, "umfang": "alle"}, …}
    """
    __tablename__ = "permission_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    beschreibung = Column(String(500), nullable=True)
    rechte = Column(JSONB, nullable=False, default=dict)
    # Mitgelieferte Gruppen: umbenennen und in den Rechten ändern ist erlaubt,
    # löschen nicht. Sonst kann eine Installation ohne jede Gruppe dastehen,
    # und neu angelegte Benutzer hätten nichts, dem man sie zuordnen könnte.
    ist_system = Column(Boolean, nullable=False, default=False,
                        server_default="false")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    users = relationship("User", secondary=user_groups, back_populates="groups")

    @property
    def benutzer_anzahl(self) -> int:
        """Für die Rückfrage „diese Gruppe betrifft 7 Personen"."""
        return len(self.users)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.employee)
    language = Column(String(10), nullable=False, default="de")
    # Persönliche Dashboard-Konfiguration (Widgets, Reihenfolge, Größen); NULL = Standard
    dashboard_config = Column(JSONB, nullable=True)
    # Modulrechte, altes Format: JSON-Liste erlaubter Module, rein an/aus.
    # NULL = alle Module erlaubt.
    #
    # Ab Migration 0055 durch Gruppen ersetzt (siehe core/berechtigungen.py).
    # Die Spalte bleibt bewusst erhalten: Sie ist der Rückfall für Benutzer
    # ohne Gruppenzugehörigkeit und macht die Übernahme nachprüfbar. Neu
    # gesetzt wird sie nicht mehr.
    allowed_modules = Column(JSONB, nullable=True)
    # Individuelle Abweichungen von den Gruppenrechten — nur die abweichenden
    # Angaben, z. B. {"verkauf": {"loeschen": false}}. Ein Entzug hier gewinnt
    # gegen jede Gruppe.
    permission_overrides = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)

    groups = relationship("PermissionGroup", secondary=user_groups,
                          back_populates="users", lazy="selectin")

    @property
    def modules(self) -> list:
        """Module mit Lesezugriff (Admin: immer alle) — für API-Antworten.

        Das Frontend baut daraus das Menü. Der Name bleibt ``modules``, damit
        eine zwischengespeicherte, ältere Oberfläche weiterläuft.
        """
        from app.core.berechtigungen import module_mit_zugang
        return module_mit_zugang(self)

    @property
    def rechte(self) -> dict:
        """Das effektive Rechteblatt — für die Oberfläche und Prüfungen."""
        from app.core.berechtigungen import effektive_rechte
        return effektive_rechte(self)

    @property
    def gruppen_namen(self) -> list[str]:
        return [g.name for g in self.groups or []]
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 2FA (TOTP)
    # Der Inhalt ist ab Migration 0054 verschlüsselt (siehe core/crypto.py);
    # deshalb Text statt String(64) — ein Fernet-Token ist deutlich länger als
    # das Base32-Secret. Bestandswerte im Klartext werden weiterhin gelesen und
    # beim nächsten Schreiben verschlüsselt. Nie direkt zugreifen, sondern über
    # AuthService.totp_secret_lesen()/totp_secret_setzen().
    totp_secret = Column(Text, nullable=True)
    totp_enabled = Column(Boolean, default=False)
    # Secret aus einem laufenden 2FA-Einrichtungsvorgang. Liegt bewusst hier und
    # nicht mehr beim Client: vorher schickte das Frontend das Secret als
    # Query-Parameter an /auth/totp/enable zurück und es landete in Zugriffslogs
    # und im Browserverlauf.
    totp_secret_pending = Column(Text, nullable=True)
    totp_pending_at = Column(DateTime(timezone=True), nullable=True)

    # ── Anmeldeschutz (Etappe „Sicherheit & Anmeldung") ───────────────────────
    # Zähler der aufeinanderfolgenden Fehlversuche; wird bei Erfolg genullt.
    failed_login_count = Column(Integer, nullable=False, default=0,
                                server_default="0")
    # Gesetzt = Konto ist bis zu diesem Zeitpunkt gesperrt (läuft von selbst ab).
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    # Zeitpunkt der letzten Passwortänderung. Dient als Stichtag: alle Sitzungen
    # und Reset-Token, die davor entstanden sind, gelten als entwertet.
    password_changed_at = Column(DateTime(timezone=True), nullable=True)

    # WebAuthn / Passkey
    webauthn_credentials = relationship("WebAuthnCredential", back_populates="user", cascade="all, delete-orphan")

    # Sessions
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    recovery_codes = relationship("TotpRecoveryCode", back_populates="user",
                                  cascade="all, delete-orphan")

    # ── Abgeleitete Angaben ───────────────────────────────────────────────────

    @property
    def is_locked(self) -> bool:
        """True, solange die Sperre aus Fehlversuchen noch läuft."""
        if not self.locked_until:
            return False
        gesperrt_bis = self.locked_until
        if gesperrt_bis.tzinfo is None:          # SQLite in Tests liefert naiv
            gesperrt_bis = gesperrt_bis.replace(tzinfo=timezone.utc)
        return gesperrt_bis > datetime.now(timezone.utc)


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    credential_id = Column(Text, unique=True, nullable=False)
    public_key = Column(Text, nullable=False)
    sign_count = Column(String(20), default="0")
    device_name = Column(String(100), nullable=True)  # z.B. "iPhone von Oliver"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="webauthn_credentials")


class UserSession(Base):
    """Eine angemeldete Sitzung (ein Gerät, ein Browser).

    Die Tabelle gab es schon vorher, sie wurde aber nur beschrieben und nie
    gelesen: es existierte kein Endpunkt zum Erneuern oder Abmelden, also war
    keine Sitzung widerrufbar. Ab Migration 0054 ist sie die
    Wahrheitsinstanz — jeder Zugriff prüft, dass die Sitzung noch lebt
    (``id`` steckt als ``sid`` im Access-Token).
    """
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
                     index=True)
    # SHA-256 des Refresh-Tokens — der Token selbst wird nie gespeichert.
    refresh_token_hash = Column(String(255), nullable=False, index=True)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── Ab Migration 0054 ─────────────────────────────────────────────────────
    # Letzter gesehener Zugriff — Grundlage für „Hier bist du angemeldet".
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    # Gesetzt = Sitzung ist entwertet und wird nicht mehr akzeptiert.
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    # Warum sie entwertet wurde: logout, logout_all, rotation, password_change,
    # admin, reuse_detected. Rein informativ, für die Übersicht und das Log.
    revoked_reason = Column(String(30), nullable=True)
    # Bei Rotation: die Nachfolge-Sitzung. Wird ein bereits rotierter
    # Refresh-Token ein zweites Mal eingelöst, ist das ein Hinweis auf einen
    # gestohlenen Token — dann fliegt die ganze Kette raus (reuse_detected).
    replaced_by_id = Column(UUID(as_uuid=True),
                            ForeignKey("user_sessions.id", ondelete="SET NULL"),
                            nullable=True)
    # Frei wählbarer Gerätename, damit der Nutzer seine Sitzungen wiedererkennt.
    device_label = Column(String(100), nullable=True)

    user = relationship("User", back_populates="sessions")

    @property
    def is_active(self) -> bool:
        """True, wenn die Sitzung weder widerrufen noch abgelaufen ist."""
        if self.revoked_at is not None:
            return False
        ablauf = self.expires_at
        if ablauf is not None and ablauf.tzinfo is None:
            ablauf = ablauf.replace(tzinfo=timezone.utc)
        return ablauf is None or ablauf > datetime.now(timezone.utc)


class AuthEvent(Base):
    """Nachvollziehbarkeit rund um die Anmeldung (Migration 0054).

    Bewusst eine eigene Tabelle und kein Textlog: die Einträge werden in der
    Oberfläche gezeigt („letzte Anmeldungen"), dienen der Sperr-Logik als
    Grundlage und müssen eine Kontoübernahme auch dann noch belegen können,
    wenn Serverlogs längst rotiert sind.

    ``user_id`` ist absichtlich NULL-bar: Fehlversuche auf unbekannte
    Adressen sollen ebenfalls sichtbar sein. Dafür steht in ``email_attempted``
    die eingegebene Adresse. Beim Löschen eines Benutzers bleibt der Eintrag
    erhalten (``SET NULL``) — ein Prüfpfad, der beim Aufräumen verschwindet,
    ist keiner.
    """
    __tablename__ = "auth_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Siehe AUTH_EVENTS in app/core/auth_events.py (z. B. login_ok, login_fail)
    event = Column(String(40), nullable=False)
    email_attempted = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    # Kurze Zusatzangabe, z. B. „2FA-Code falsch" oder der Gerätename.
    detail = Column(String(200), nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_auth_events_user_created", "user_id", "created_at"),
        Index("ix_auth_events_event_created", "event", "created_at"),
    )


class WebAuthnChallenge(Base):
    """Zwischenspeicher für WebAuthn-Challenges (Migration 0054).

    Vorher lagen die Challenges in einem Dict im Arbeitsspeicher des Prozesses.
    Das funktioniert nur mit genau einem Worker und überlebt keinen Neustart:
    mit mehreren Uvicorn-Workern landet der zweite Aufruf mit hoher
    Wahrscheinlichkeit im falschen Prozess und die Anmeldung scheitert mit
    „Challenge abgelaufen", obwohl nichts abgelaufen ist.
    """
    __tablename__ = "webauthn_challenges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # z. B. "reg:<user-id>" oder "auth:<e-mail>"
    scope = Column(String(320), nullable=False, unique=True, index=True)
    challenge = Column(LargeBinary, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))


class TotpRecoveryCode(Base):
    """Einmal-Codes als Notausgang, wenn das Authenticator-Gerät fehlt.

    Ohne diese Codes sperrt sich ein Benutzer mit aktivem 2FA beim Verlust
    seines Handys endgültig aus und braucht zwingend einen Administrator.
    Gespeichert wird nur der Hash, angezeigt wird der Code genau einmal —
    bei der Erzeugung.
    """
    __tablename__ = "totp_recovery_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="recovery_codes")


class PasswordResetToken(Base):
    """Einmal-Token für „Passwort vergessen" (Migration 0054).

    Gespeichert wird nur der SHA-256-Hash: wer die Datenbank liest, kann damit
    kein Passwort zurücksetzen. Ein Token ist kurz gültig, genau einmal
    verwendbar und wird von einer Passwortänderung entwertet.
    """
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc))
