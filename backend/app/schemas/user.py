from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.user import UserRole


class UserBase(BaseModel):
    email: str
    full_name: str
    role: UserRole = UserRole.employee
    language: str = "de"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    language: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    totp_enabled: bool
    created_at: datetime
    # Anmeldeschutz — die Benutzerverwaltung zeigt an, wenn ein Konto wegen
    # Fehlversuchen gesperrt ist, damit ein Administrator auf „Sperre aufheben"
    # nicht erst durch Nachfragen kommt.
    is_locked: bool = False
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    # Altes Rechteformat, seit Migration 0055 nur noch Rückfall und Nachweis
    # der Übernahme (None = alle Module erlaubt). Wird nicht mehr gesetzt.
    allowed_modules: Optional[list[str]] = None
    # Module mit Lesezugriff — Pydantic liest sie über das @property
    # User.modules (from_attributes). Grundlage für das Menü im Frontend.
    modules: Optional[list[str]] = None
    # Rechtegruppen, in denen der Benutzer ist (Namen für die Liste)
    gruppen_namen: list[str] = []
    # Gesetzt, wenn individuelle Abweichungen bestehen — die Benutzerliste
    # kennzeichnet solche Konten, damit sie bei einer Gruppenänderung nicht
    # übersehen werden.
    permission_overrides: Optional[dict] = None

    class Config:
        from_attributes = True


# Grenzen für die Dashboard-Konfiguration. Sie halten die JSONB-Spalte klein
# und spiegeln die Vorgaben des Frontends (utils/dashboardConfig.js).
DASHBOARD_MAX_LAYOUTS = 5
DASHBOARD_MAX_WIDGETS = 60
DASHBOARD_MAX_NAME = 30
DASHBOARD_MAX_TITEL = 40


class DashboardConfigPayload(BaseModel):
    """Persönliche Dashboard-Konfiguration je Benutzer (JSONB, schemafrei).

    config = None bedeutet: Standard-Dashboard verwenden.

    Format v2 (aktuell) — mehrere Ansichten je Benutzer::

        {"version": 2,
         "aktivesLayout": "standard",
         "bekannt": {"typen": [...], "slugs": [...]},
         "layouts": [{"id": "standard", "name": "Standard",
                      "widgets": [{"id": "w_zeit_ab12", "type": "zeiterfassung",
                                   "size": 2, "titel": "Meine Zeiten"}]}]}

    Format v1 (Vorgänger) wird weiterhin angenommen, damit ein Client mit
    altem Stand (z. B. zwischengespeicherte PWA) nichts kaputt schreibt::

        {"widgets": [{"id": "widget_zeit", "type": "zeiterfassung",
                      "size": 2, "hidden": false}]}

    Absichtlich NICHT geprüft wird, ob ein Widget-Typ existiert oder ob der
    Benutzer das zugehörige Modul freigeschaltet hat: der Katalog lebt im
    Frontend (data/dashboardWidgets.js) und würde hier nur doppelt gepflegt und
    mit der Zeit auseinanderlaufen. Das Frontend wirft unbekannte und nicht
    freigegebene Bausteine beim Laden weg. Sicherheitsrelevant ist das nicht —
    die Daten hinter den Bausteinen holen sich die Widgets über eigene,
    einzeln rechtegeprüfte Endpunkte.
    """
    config: Optional[dict] = None

    @field_validator("config")
    @classmethod
    def config_pruefen(cls, v: Optional[dict]) -> Optional[dict]:
        if v is None:
            return v

        def widgets_pruefen(widgets, wo: str):
            if not isinstance(widgets, list):
                raise ValueError(f"{wo}: 'widgets' muss eine Liste sein")
            if len(widgets) > DASHBOARD_MAX_WIDGETS:
                raise ValueError(f"{wo}: höchstens {DASHBOARD_MAX_WIDGETS} Bausteine")
            for w in widgets:
                if not isinstance(w, dict) or not isinstance(w.get("type"), str):
                    raise ValueError(f"{wo}: jeder Baustein braucht ein 'type'")
                if "size" in w and w["size"] not in (1, 2, 3, 4):
                    raise ValueError(f"{wo}: 'size' muss zwischen 1 und 4 liegen")
                titel = w.get("titel")
                if titel is not None and (not isinstance(titel, str)
                                          or len(titel) > DASHBOARD_MAX_TITEL):
                    raise ValueError(f"{wo}: 'titel' höchstens {DASHBOARD_MAX_TITEL} Zeichen")

        # ── Format v2 ─────────────────────────────────────────────────────────
        if v.get("version") == 2:
            layouts = v.get("layouts")
            if not isinstance(layouts, list) or not layouts:
                raise ValueError("v2 braucht mindestens eine Ansicht in 'layouts'")
            if len(layouts) > DASHBOARD_MAX_LAYOUTS:
                raise ValueError(f"höchstens {DASHBOARD_MAX_LAYOUTS} Ansichten")
            for l in layouts:
                if not isinstance(l, dict) or not isinstance(l.get("id"), str) or not l["id"]:
                    raise ValueError("jede Ansicht braucht eine 'id'")
                name = l.get("name")
                if name is not None and (not isinstance(name, str)
                                         or len(name) > DASHBOARD_MAX_NAME):
                    raise ValueError(f"Ansichtsname höchstens {DASHBOARD_MAX_NAME} Zeichen")
                widgets_pruefen(l.get("widgets", []), f"Ansicht '{l['id']}'")

            aktiv = v.get("aktivesLayout")
            if aktiv is not None and aktiv not in [l["id"] for l in layouts]:
                raise ValueError("'aktivesLayout' zeigt auf keine vorhandene Ansicht")
            return v

        # ── Format v1 ─────────────────────────────────────────────────────────
        if "widgets" in v:
            widgets_pruefen(v["widgets"], "Dashboard")
            return v

        raise ValueError("Unbekanntes Format: erwartet wird 'version': 2 oder 'widgets'")


class LoginRequest(BaseModel):
    email: str
    password: str
    totp_code: Optional[str] = None
    # Notausgang, wenn das Authenticator-Gerät fehlt: einer der Einmal-Codes
    # aus den Sicherheitseinstellungen — anstelle des 2FA-Codes.
    recovery_code: Optional[str] = None


class TokenResponse(BaseModel):
    """Antwort auf eine erfolgreiche Anmeldung.

    ``refresh_token`` bleibt **leer**: Der langlebige Token wird seit der
    Sicherheits-Etappe als ``httpOnly``-Cookie gesetzt und ist für JavaScript
    nicht lesbar. Eine XSS-Lücke im Frontend kann damit nicht mehr eine
    dauerhaft gültige Sitzung abgreifen, sondern höchstens den Access-Token —
    und der lebt 30 Minuten.

    Das Feld bleibt aus einem praktischen Grund im Schema: Eine als PWA
    installierte Oberfläche kann eine zwischengespeicherte, ältere Version
    sein, die das Feld noch ausliest. Es fehlt dann nicht, sondern ist leer,
    und der Anmeldefluss läuft über den Cookie weiter.
    """
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    requires_totp: bool = False
    requires_webauthn: bool = False
    #: Anzahl noch nicht verbrauchter Einmal-Codes — die Oberfläche warnt,
    #: wenn kaum noch welche übrig sind.
    recovery_codes_left: Optional[int] = None


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None
    disable_totp: Optional[bool] = None  # True = 2FA deaktivieren
    # Modulrechte: Liste erlaubter Module; None = Feld nicht ändern
    allowed_modules: Optional[list[str]] = None


class TOTPSetupResponse(BaseModel):
    """QR-Code und Secret für die Einrichtung.

    Das Secret steht weiterhin in der Antwort — der Benutzer muss es abtippen
    können, wenn die Kamera den QR-Code nicht liest. Neu ist, dass der Client
    es beim Aktivieren **nicht** zurückschickt: der Server hat es vorgemerkt
    (``users.totp_secret_pending``). Vorher lief es als Query-Parameter zurück
    und landete damit in Zugriffslogs und im Browserverlauf.
    """
    secret: str
    qr_code_url: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str


class WebAuthnCredentialResponse(BaseModel):
    id: UUID
    device_name: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True


# ─── Sitzungen ────────────────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    """Eine angemeldete Sitzung für die Übersicht „Hier bist du angemeldet"."""
    id: UUID
    device_label: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: datetime
    #: True für die Sitzung, aus der die Anfrage gerade kommt — die Oberfläche
    #: markiert sie als „dieses Gerät" und bietet dort kein „beenden" an.
    is_current: bool = False

    class Config:
        from_attributes = True


class RefreshResponse(BaseModel):
    """Antwort auf ``/auth/refresh``. Der neue Refresh-Token steckt im Cookie."""
    access_token: str
    token_type: str = "bearer"


# ─── Passwort ─────────────────────────────────────────────────────────────────

class PasswordForgotRequest(BaseModel):
    email: str


class PasswordResetRequest(BaseModel):
    token: str
    new_password: str


class PasswordChangeRequest(BaseModel):
    """Passwortwechsel im Profil.

    Das aktuelle Passwort ist Pflicht: Ohne diese Rückfrage kann jemand, der
    ein offenes Gerät vorfindet oder einen Access-Token abgegriffen hat, das
    Passwort ändern und den rechtmäßigen Benutzer aussperren.
    """
    current_password: str
    new_password: str
    #: True = zusätzlich alle anderen Geräte abmelden (Standard).
    logout_other_devices: bool = True


# ─── Einmal-Codes ─────────────────────────────────────────────────────────────

class RecoveryCodesResponse(BaseModel):
    """Die Codes im Klartext — einmalig bei der Erzeugung."""
    codes: list[str]
    hinweis: str = ("Bitte jetzt ausdrucken oder in einem Passwort-Manager "
                    "speichern. Nach dem Schließen sind die Codes nicht mehr "
                    "abrufbar. Jeder Code funktioniert genau einmal.")


class RecoveryStatusResponse(BaseModel):
    codes_left: int
    total: int


# ─── Prüfpfad ─────────────────────────────────────────────────────────────────

class AuthEventResponse(BaseModel):
    id: UUID
    event: str
    #: Deutscher Text zur Ereignisart (siehe core/auth_events.py)
    label: Optional[str] = None
    email_attempted: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime
    suspicious: bool = False

    class Config:
        from_attributes = True


# ─── WebAuthn (bisher ungetypte dicts) ────────────────────────────────────────

class WebAuthnRegisterComplete(BaseModel):
    credential: dict
    device_name: str = "Mein Gerät"


class WebAuthnLoginBegin(BaseModel):
    email: str


class WebAuthnLoginComplete(BaseModel):
    email: str
    credential: dict
