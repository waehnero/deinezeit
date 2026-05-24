from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.schemas.user import (
    LoginRequest, TokenResponse, TOTPSetupResponse,
    TOTPVerifyRequest, UserResponse, UserCreate
)
from app.services.auth_service import auth_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentifizierung"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # Brute-Force-Schutz
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Passwort-Login. Wenn 2FA aktiv, wird ein TOTP-Code benötigt."""
    user = auth_service.authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-Mail oder Passwort falsch")

    # 2FA prüfen
    if user.totp_enabled:
        if not body.totp_code:
            return TokenResponse(
                access_token="",
                refresh_token="",
                requires_totp=True,
            )
        if not auth_service.verify_totp(user, body.totp_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiger 2FA-Code")

    meta = {
        "user_agent": request.headers.get("user-agent"),
        "ip_address": request.client.host if request.client else None,
    }
    tokens = auth_service.create_tokens(db, user, meta)
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Aktuell eingeloggten Benutzer abrufen."""
    return current_user


# ─── TOTP / 2FA ──────────────────────────────────────────────────────────────

@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(current_user: User = Depends(get_current_user)):
    """TOTP-Secret und QR-Code für die Authenticator-App generieren."""
    secret = auth_service.generate_totp_secret()
    qr_code = auth_service.get_totp_qr(current_user, secret)
    import pyotp
    uri = pyotp.TOTP(secret).provisioning_uri(current_user.email, issuer_name="DeineZeit")
    return TOTPSetupResponse(secret=secret, qr_code_url=qr_code, provisioning_uri=uri)


@router.post("/totp/enable")
async def enable_totp(
    body: TOTPVerifyRequest,
    secret: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """2FA aktivieren (nach QR-Code-Scan und Code-Bestätigung)."""
    success = auth_service.enable_totp(db, current_user, secret, body.code)
    if not success:
        raise HTTPException(status_code=400, detail="Ungültiger Code. Bitte erneut versuchen.")
    return {"message": "2FA erfolgreich aktiviert"}


@router.post("/totp/disable")
async def disable_totp(
    body: TOTPVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """2FA deaktivieren."""
    if not auth_service.verify_totp(current_user, body.code):
        raise HTTPException(status_code=400, detail="Ungültiger 2FA-Code")
    auth_service.disable_totp(db, current_user)
    return {"message": "2FA wurde deaktiviert"}


# ─── WebAuthn / Passkeys (Face ID) ───────────────────────────────────────────

@router.post("/webauthn/register/begin")
async def webauthn_register_begin(current_user: User = Depends(get_current_user)):
    """Registrierung eines neuen Passkeys starten (z.B. Face ID)."""
    # WebAuthn-Challenge wird im Frontend weiterverarbeitet
    import webauthn
    from app.core.config import settings

    options = webauthn.generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.email,
        user_display_name=current_user.full_name,
    )
    import webauthn.helpers.structs as structs
    return webauthn.options_to_json(options)


@router.post("/webauthn/register/complete")
async def webauthn_register_complete(
    credential: dict,
    device_name: str = "Mein Gerät",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Passkey-Registrierung abschließen."""
    import webauthn
    from app.core.config import settings
    from app.models.user import WebAuthnCredential

    try:
        verification = webauthn.verify_registration_response(
            credential=credential,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.FRONTEND_URL,
            require_user_verification=True,
        )
        cred = WebAuthnCredential(
            user_id=current_user.id,
            credential_id=verification.credential_id.hex(),
            public_key=verification.credential_public_key.hex(),
            sign_count=str(verification.sign_count),
            device_name=device_name,
        )
        db.add(cred)
        db.commit()
        return {"message": f"'{device_name}' erfolgreich registriert"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registrierung fehlgeschlagen: {str(e)}")


@router.post("/webauthn/login/begin")
async def webauthn_login_begin(email: str, db: Session = Depends(get_db)):
    """Passkey-Login starten."""
    import webauthn
    from app.core.config import settings

    user = auth_service.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    from app.models.user import WebAuthnCredential
    credentials = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).all()

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=bytes.fromhex(c.credential_id))
            for c in credentials
        ],
    )
    return webauthn.options_to_json(options)
