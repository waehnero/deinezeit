from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.user import User, UserRole
from app.models.settings import Setting
from app.models.masterdata import EntityType
from app.schemas.setup import (
    SetupStatusResponse, SetupInitRequest, SetupInitResponse,
)
from app.services.auth_service import auth_service
from app.services.masterdata_service import masterdata_service

router = APIRouter(prefix="/setup", tags=["Erstinstallation"])


def _user_count(db: Session) -> int:
    return db.query(User).count()


def _save_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.now(timezone.utc)))


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: Session = Depends(get_db)):
    """Prueft, ob der Einrichtungsassistent noetig ist (noch kein Benutzer)."""
    count = _user_count(db)
    return SetupStatusResponse(needs_setup=(count == 0), user_count=count)


@router.post("/init", response_model=SetupInitResponse)
async def setup_init(
    request: Request,
    body: SetupInitRequest,
    db: Session = Depends(get_db),
):
    """Legt den ersten Administrator (und optional die Firma) an.

    Sicherheits-Riegel: Sobald *irgendein* Benutzer existiert, ist dieser
    Endpunkt gesperrt (HTTP 409). So kann er nach der Ersteinrichtung nicht
    missbraucht werden, um einen weiteren Admin anzulegen.
    """
    # ── Riegel: nur bei komplett leerer Benutzertabelle ──────────────────────
    if _user_count(db) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Einrichtung bereits abgeschlossen — Anmeldung erforderlich.",
        )

    # ── Eingaben pruefen ─────────────────────────────────────────────────────
    email = (body.admin_email or "").strip().lower()
    full_name = (body.admin_full_name or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Bitte eine gueltige E-Mail-Adresse angeben.")
    if not full_name:
        raise HTTPException(status_code=400, detail="Bitte einen Namen angeben.")
    if len(body.admin_password or "") < 8:
        raise HTTPException(status_code=400, detail="Das Passwort muss mindestens 8 Zeichen lang sein.")

    # ── Ersten Admin anlegen ─────────────────────────────────────────────────
    user = auth_service.create_user(
        db, email=email, full_name=full_name,
        password=body.admin_password, role=UserRole.admin, language=body.language,
    )

    # ── Optional: Firma als Kontakt anlegen und als Briefkopf verknuepfen ────
    company_contact_id = None
    if body.company and (body.company.firmenname or "").strip():
        c = body.company
        # Firmenname zugleich als Anzeigename der App (Einstellungen/Allgemein)
        _save_setting(db, "company_name", c.firmenname.strip())

        kontakte = db.query(EntityType).filter(EntityType.slug == "kontakte").first()
        if kontakte:
            data = {
                k: v for k, v in {
                    "firmenname":     (c.firmenname or "").strip(),
                    "ansprechperson": (c.ansprechperson or "").strip(),
                    "email":          (c.email or "").strip(),
                    "telefon":        (c.telefon or "").strip(),
                    "adresse":        (c.adresse or "").strip(),
                    "plz":            (c.plz or "").strip(),
                    "ort":            (c.ort or "").strip(),
                    "land":           (c.land or "").strip(),
                    "uid":            (c.uid or "").strip(),
                    "iban":           (c.iban or "").strip(),
                    "bic":            (c.bic or "").strip(),
                    "bankname":       (c.bankname or "").strip(),
                }.items() if v
            }
            record = masterdata_service.create_record(db, kontakte, data, user_id=user.id)
            company_contact_id = str(record.id)
            _save_setting(db, "company_contact_id", company_contact_id)
            _save_setting(db, "company_contact_type", kontakte.slug)
        db.commit()

    # ── Direkt einloggen (Assistent geht nahtlos ins Dashboard) ──────────────
    meta = {
        "user_agent": request.headers.get("user-agent"),
        "ip_address": request.client.host if request.client else None,
    }
    tokens = auth_service.create_tokens(db, user, meta)
    return SetupInitResponse(company_contact_id=company_contact_id, **tokens)
