import os
import secrets
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     status)
from sqlalchemy import text
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


def _setup_token() -> str:
    """Einrichtungs-Token aus der Umgebung (SETUP_TOKEN in der .env).

    Bis 03.09.2026 war /setup/init für jeden erreichbar, solange noch kein
    Benutzer existierte: Wer eine frische Installation zwischen Zertifikat und
    Assistent erreichte, wurde Administrator (Audit SEC-006). install.sh legt
    den Token jetzt automatisch an; bei einer Installation von Hand steht er
    in .env.example beschrieben. Ist keiner gesetzt, verhält sich der Endpunkt
    wie bisher — mit einer Warnung im Log."""
    return (os.environ.get("SETUP_TOKEN") or "").strip()


def _save_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.now(timezone.utc)))


@router.get("/status", response_model=SetupStatusResponse)
def setup_status(db: Session = Depends(get_db)):
    """Prueft, ob der Einrichtungsassistent noetig ist (noch kein Benutzer)."""
    count = _user_count(db)
    return SetupStatusResponse(needs_setup=(count == 0), user_count=count,
                               token_required=bool(_setup_token()))


@router.post("/init", response_model=SetupInitResponse)
def setup_init(
    request: Request,
    response: Response,
    body: SetupInitRequest,
    db: Session = Depends(get_db),
):
    """Legt den ersten Administrator (und optional die Firma) an.

    Sicherheits-Riegel: Sobald *irgendein* Benutzer existiert, ist dieser
    Endpunkt gesperrt (HTTP 409). So kann er nach der Ersteinrichtung nicht
    missbraucht werden, um einen weiteren Admin anzulegen.
    """
    # ── Riegel 1: Einrichtungs-Token (falls gesetzt) ─────────────────────────
    erwartet = _setup_token()
    if erwartet:
        if not secrets.compare_digest((body.setup_token or "").strip(), erwartet):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=("Einrichtungs-Token fehlt oder ist falsch. Er steht in der "
                        "Datei .env auf dem Server (SETUP_TOKEN)."))
    else:
        import logging
        logging.getLogger(__name__).warning(
            "Erstinstallation ohne SETUP_TOKEN — der Assistent ist bis zum ersten "
            "Benutzer für jeden erreichbar. Empfehlung: SETUP_TOKEN in der .env setzen.")

    # ── Riegel 2: nur bei komplett leerer Benutzertabelle ────────────────────
    # Die Tabelle wird für die Dauer der Transaktion gesperrt, damit zwei
    # gleichzeitige Aufrufe nicht beide „0 Benutzer" sehen und zwei
    # Administratoren anlegen. create_user() bestätigt die Transaktion und gibt
    # die Sperre damit frei.
    db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
    if _user_count(db) > 0:
        db.rollback()
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
    # Das erste Konto ist der Administrator der gesamten Installation — hier
    # gilt die Richtlinie erst recht (vorher genügten 8 beliebige Zeichen).
    from app.core import passwort as pw_regeln
    pw_regeln.pruefen_oder_fehler(body.admin_password or "", email=email,
                                  name=full_name)

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
    # Der Refresh-Token geht als httpOnly-Cookie mit, nicht im Antworttext —
    # gleicher Weg wie bei /auth/login.
    from app.api.auth import absender_meta, refresh_cookie_setzen
    from app.core import auth_events as EV

    meta = absender_meta(request)
    tokens = auth_service.create_tokens(db, user, meta)
    refresh_cookie_setzen(response, tokens["refresh_token"])
    auth_service.ereignis(db, EV.LOGIN_OK, user=user, meta=meta,
                          detail="Erstinstallation")
    return SetupInitResponse(company_contact_id=company_contact_id,
                             access_token=tokens["access_token"])
