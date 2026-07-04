from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.db.base import get_db
from app.schemas.user import (
    UserCreate, UserResponse, UserUpdate, AdminUserUpdate, DashboardConfigPayload,
)
from app.services.auth_service import auth_service
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.core.security import get_password_hash

router = APIRouter(prefix="/users", tags=["Benutzerverwaltung"])


@router.get("/", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Benutzer anzeigen (alle eingeloggten Benutzer; Bearbeitung bleibt Admin vorbehalten)."""
    return db.query(User).all()


@router.post("/", response_model=UserResponse)
async def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neuen Benutzer anlegen (nur Admin)."""
    existing = auth_service.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="E-Mail bereits vergeben")
    return auth_service.create_user(db, body.email, body.full_name, body.password, body.role, body.language)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eigenes Profil aktualisieren (Sprache, Name, Passwort)."""
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.language is not None:
        current_user.language = body.language
    if body.password is not None:
        current_user.hashed_password = get_password_hash(body.password)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/dashboard", response_model=DashboardConfigPayload)
async def get_my_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Persönliche Dashboard-Konfiguration abrufen (None = Standard)."""
    return DashboardConfigPayload(config=current_user.dashboard_config)


@router.put("/me/dashboard", response_model=DashboardConfigPayload)
async def save_my_dashboard(
    body: DashboardConfigPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persönliche Dashboard-Konfiguration speichern.

    config = None setzt auf das Standard-Dashboard zurück.
    """
    current_user.dashboard_config = body.config
    db.commit()
    db.refresh(current_user)
    return DashboardConfigPayload(config=current_user.dashboard_config)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_by_admin(
    user_id: UUID,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Benutzer bearbeiten (nur Admin): Name, Passwort, Rolle, 2FA deaktivieren."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password is not None:
        user.hashed_password = get_password_hash(body.password)
    if body.role is not None:
        user.role = body.role
    if body.language is not None:
        user.language = body.language
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.disable_totp:
        user.totp_secret = None
        user.totp_enabled = False
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Benutzer endgültig löschen (nur Admin)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Den eigenen Account kann man nicht löschen")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    db.delete(user)
    db.commit()
    return {"message": "Benutzer gelöscht"}
