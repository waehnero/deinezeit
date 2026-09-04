from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DeineZeit"
    APP_VERSION: str = "1.12.81"
    DEBUG: bool = False

    # Datenbank
    DATABASE_URL: str
    # Verbindungspool (siehe db/base.py). Die SQLAlchemy-Vorgabe von 5+10 ist
    # für eine WebApp mit mehreren gleichzeitigen Benutzern knapp; PostgreSQL
    # verträgt in der Standardkonfiguration 100 Verbindungen insgesamt.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Sicherheit
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate-Limiting. Vorgabe an — abschalten ist ausschließlich für Messläufe
    # gedacht (ein Lasttest kommt von einer einzigen Adresse und liefe sonst
    # nur gegen die Bremse). Im Regelbetrieb bleibt das an, sonst steht die
    # Anmeldung offen für Rateversuche.
    RATE_LIMIT_AKTIV: bool = True

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

    # Zeitzone der Installation (Kalenderdaten, Berichte, Worker-Zeiten).
    # Kommt aus docker-compose.yml (TZ=…); siehe core/zeit.py.
    TZ: str = "Europe/Vienna"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Prozess-Zeitzone setzen, damit auch date.today()/datetime.now() in
# Bibliotheken und an übersehenen Stellen die Ortszeit liefern (Audit BUG-002).
# tzset gibt es nur auf Unix — im Container immer, unter Windows nie nötig.
import os as _os
import time as _time
_os.environ["TZ"] = settings.TZ
if hasattr(_time, "tzset"):
    _time.tzset()
