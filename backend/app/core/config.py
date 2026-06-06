from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DeineZeit"
    APP_VERSION: str = "1.6.1"
    DEBUG: bool = False

    # Datenbank
    DATABASE_URL: str

    # Sicherheit
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # WebAuthn
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "DeineZeit"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
