from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
from app.db.base import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges oder abgelaufenes Token",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == UUID(user_id), User.is_active == True).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administratorrechte erforderlich",
        )
    return current_user


def require_module(module: str):
    """Dependency-Factory: Zugriff nur mit freigeschaltetem Modul.

    Admins haben immer alle Module; allowed_modules=NULL bedeutet
    "alle erlaubt" (Standard). Verwendung in main.py beim Einbinden
    der Router oder je Endpunkt:

        app.include_router(r, dependencies=[Depends(require_module("verkauf"))])
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        from app.core.modules import user_has_module, MODULE_LABELS
        if not user_has_module(current_user, module):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Kein Zugriff — das Modul "
                       f"„{MODULE_LABELS.get(module, module)}“ ist für diesen "
                       "Benutzer nicht freigeschaltet",
            )
        return current_user
    return _check
