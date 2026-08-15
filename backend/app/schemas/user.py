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
    # Gespeicherte Modulrechte (None = alle Module erlaubt)
    allowed_modules: Optional[list[str]] = None
    # Effektive Modul-Liste (Admin: immer alle) — Pydantic liest sie über
    # das @property User.modules (from_attributes)
    modules: Optional[list[str]] = None

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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_totp: bool = False
    requires_webauthn: bool = False


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
