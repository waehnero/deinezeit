import pyotp
import qrcode
import qrcode.image.svg
import base64
import io
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.user import User, UserSession, WebAuthnCredential
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from app.core.config import settings


class AuthService:

    # ─── Passwort-Login ───────────────────────────────────────────────────────

    def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.email == email, User.is_active == True).first()
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    def create_tokens(self, db: Session, user: User, request_meta: dict) -> dict:
        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        # Session speichern
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
            user_agent=request_meta.get("user_agent"),
            ip_address=request_meta.get("ip_address"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        db.add(session)
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    # ─── TOTP (Google Authenticator) ──────────────────────────────────────────

    def generate_totp_secret(self) -> str:
        return pyotp.random_base32()

    def get_totp_qr(self, user: User, secret: str) -> str:
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)

        qr = qrcode.make(uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        return "data:image/png;base64," + base64.b64encode(buffer.read()).decode()

    def verify_totp(self, user: User, code: str) -> bool:
        if not user.totp_secret:
            return False
        totp = pyotp.TOTP(user.totp_secret)
        return totp.verify(code, valid_window=1)

    def enable_totp(self, db: Session, user: User, secret: str, code: str) -> bool:
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return False
        user.totp_secret = secret
        user.totp_enabled = True
        db.commit()
        return True

    def disable_totp(self, db: Session, user: User) -> None:
        user.totp_secret = None
        user.totp_enabled = False
        db.commit()

    # ─── Benutzerverwaltung ───────────────────────────────────────────────────

    def create_user(self, db: Session, email: str, full_name: str, password: str, role: str = "employee", language: str = "de") -> User:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(password),
            role=role,
            language=language,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, db: Session, user_id: UUID) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()


auth_service = AuthService()
