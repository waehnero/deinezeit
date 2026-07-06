from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DeineZeit"
    APP_VERSION: str = "1.12.16"
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

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin123"
    MINIO_BUCKET: str = "deinezeit-files"
    MINIO_PUBLIC_URL: str = "http://localhost"

    # Deploy-Modus
    DEPLOY_MODE: str = "production"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
