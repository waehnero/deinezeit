from pydantic import BaseModel, EmailStr
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

    class Config:
        from_attributes = True


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
