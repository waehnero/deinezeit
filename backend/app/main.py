from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import logging
import os
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.netz import echte_ip
from app.api import auth, users, masterdata, zeiterfassung, reports, datacenter, system, invoice, accounting, projektplan, aufgaben, mailimport, gdpr, postecke, setup, oeffentlich, period, purchase, dashboard, groups
from app.api import settings as settings_api
from app.services import storage_service

# ── Logging ───────────────────────────────────────────────────────────────────
# Uvicorn konfiguriert nur seine eigenen Logger; der Root-Logger bleibt leer.
# Meldungen aus unseren Modulen (logging.getLogger(__name__), also unterhalb
# von "app") liefen dadurch ins Leere, sobald sie unter WARNING lagen — ein
# Grund, warum im Serverlog zu Fehlern oft nur der nackte HTTP-Status stand.
# Wir hängen daher genau EINEN Handler an den Teilbaum "app". Fremdbibliotheken
# (httpx, sqlalchemy, ...) bleiben unberührt, es wird also nicht lauter als nötig.
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _app_logger.addHandler(_handler)
_app_logger.setLevel(getattr(logging, _log_level, logging.INFO))
# propagate bleibt bewusst an: der Root-Logger hat unter Uvicorn keine Handler,
# es gibt also keine doppelten Zeilen — und pytest (caplog) kann mitlesen.

# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Schlüssel ist die echte Absenderadresse (core/netz.echte_ip), NICHT
# ``get_remote_address``: Hinter nginx liefert das immer die Adresse des
# Proxy-Containers, und dann gelten die 200 Anfragen pro Minute für die gesamte
# Installation gemeinsam statt je Benutzer. In einem Betrieb mit zehn Leuten
# heißt das „zu viele Anfragen“ im Alltag, ohne dass jemand etwas falsch macht.
limiter = Limiter(key_func=echte_ip, default_limits=["200/minute"])
# Abschaltbar für Messläufe (Lasttest kommt von einer einzigen Adresse).
# Vorgabe ist an; siehe RATE_LIMIT_AKTIV in .env.example.
limiter.enabled = settings.RATE_LIMIT_AKTIV
if not limiter.enabled:
    _app_logger.warning(
        "Rate-Limiting ist abgeschaltet (RATE_LIMIT_AKTIV=false). "
        "Das gehört in Messläufe, nicht in den Regelbetrieb."
    )

# ── App — API-Docs in Produktion deaktivieren ─────────────────────────────────
_is_dev = os.environ.get("APP_ENV", "production").lower() == "development"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    await startup_event()          # definiert weiter unten
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs"  if _is_dev else None,
    redoc_url="/api/redoc" if _is_dev else None,
    lifespan=_lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Statische Dateien ─────────────────────────────────────────────────────────
# Pfad per Env überschreibbar (Default = /app/static wie im Docker-Container).
# In Umgebungen ohne Schreibrechte auf /app (z.B. CI/Tests) auf ein temporäres
# Verzeichnis ausweichen, statt beim Import abzustürzen.
STATIC_DIR = os.environ.get("STATIC_DIR", "/app/static")
try:
    os.makedirs(STATIC_DIR, exist_ok=True)
except OSError as e:
    import tempfile
    STATIC_DIR = os.path.join(tempfile.gettempdir(), "deinezeit_static")
    os.makedirs(STATIC_DIR, exist_ok=True)
    print(f"[WARN] STATIC_DIR nicht beschreibbar ({e}); nutze {STATIC_DIR}")
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── API-Router ────────────────────────────────────────────────────────────────
# Modulrechte: Router ganzer Module werden hier abgesichert.
#
# Seit Migration 0055 prüft `_rm` nicht mehr nur „Modul freigeschaltet", sondern
# das passende Recht zur HTTP-Methode: GET → Ansehen, POST/PUT/PATCH → Ändern,
# DELETE → Löschen (siehe deps.require_modul_rechte). Ein Mitarbeiter mit
# Leserecht auf Verkauf kann Belege damit ansehen, aber nicht mehr anlegen oder
# stornieren — vorher war beides dasselbe Häkchen.
#
# Bewusst OHNE Modul-Sperre (Querbezüge, siehe core/modules.py):
#   masterdata  → Lesen für alle (Auswahlfelder); Schreiben je Endpunkt gesperrt
#   datacenter  → Anhänge je Datensatz für alle; nur Übersicht je Endpunkt gesperrt
#   reports     → gehört fachlich zur Zeiterfassung
from app.api.deps import require_modul_rechte as _rm
from fastapi import Depends as _Dep

app.include_router(setup.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
# Rechtegruppen: bewusst OHNE Modul-Sperre — wer Rechte verwaltet, ist
# Administrator, das prüfen die Endpunkte selbst (require_admin).
app.include_router(groups.router, prefix="/api")
app.include_router(masterdata.router, prefix="/api")
app.include_router(zeiterfassung.router, prefix="/api",
                   dependencies=[_Dep(_rm("zeiterfassung"))])
app.include_router(reports.router, prefix="/api",
                   dependencies=[_Dep(_rm("zeiterfassung"))])
app.include_router(settings_api.router, prefix="/api")
app.include_router(datacenter.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(invoice.router, prefix="/api",
                   dependencies=[_Dep(_rm("verkauf"))])
app.include_router(accounting.router, prefix="/api",
                   dependencies=[_Dep(_rm("verkauf")), _Dep(_rm("buchhaltung"))])
app.include_router(period.router, prefix="/api",
                   dependencies=[_Dep(_rm("verkauf")), _Dep(_rm("buchhaltung"))])
# Eingangsrechnungen sind Buchhaltung, nicht Verkauf: Wer Belege schreibt,
# muss nicht sehen, was das Unternehmen einkauft.
app.include_router(purchase.router, prefix="/api",
                   dependencies=[_Dep(_rm("buchhaltung"))])
app.include_router(projektplan.router, prefix="/api",
                   dependencies=[_Dep(_rm("projekte"))])
app.include_router(aufgaben.router, prefix="/api",
                   dependencies=[_Dep(_rm("aufgaben"))])
app.include_router(mailimport.router, prefix="/api",
                   dependencies=[_Dep(_rm("aufgaben"))])
app.include_router(gdpr.router, prefix="/api")
# Dashboard-Kennzahlen: sammelt die Werte anderer Module ein. Die Freigabe je
# Baustein prüft der Service selbst (services/dashboard.py) — hier hängt nur
# das Grundrecht aufs Dashboard.
app.include_router(dashboard.router, prefix="/api",
                   dependencies=[_Dep(_rm("dashboard"))])
app.include_router(postecke.router, prefix="/api",
                   dependencies=[_Dep(_rm("postecke"))])
# Öffentlicher, token-gesicherter Medien-Abruf (für Instagram) — bewusst OHNE
# Auth-/Modul-Sperre; der signierte Kurzzeit-Token ist die Berechtigung.
app.include_router(oeffentlich.router, prefix="/api")


# ── Start der Anwendung (lifespan) ────────────────────────────────────────────
# ``@app.on_event("startup")`` ist seit FastAPI 0.93 durch ``lifespan`` ersetzt
# und in Starlette 1.x entfernt (Audit CODE-002, Update K-13). Die
# Startarbeiten stehen weiter in einer eigenen Funktion, damit sie lesbar
# bleiben; der lifespan-Kontext ruft sie einmal beim Start auf.
async def startup_event():
    # In Tests übersprungen — wie die Worker weiter unten (Kennzeichen ist
    # TEST_DATABASE_URL, siehe tests/conftest.py). Der Testclient startet die
    # App für JEDEN Test neu; ohne erreichbares MinIO versucht der Client hier
    # fünfmal mit wachsender Wartezeit, rund sechs Sekunden je Test. Bei 873
    # Tests waren das in der CI (die kein MinIO hat) bis zu 87 Minuten reiner
    # Leerlauf (Audit TEST-002).
    if not os.environ.get("TEST_DATABASE_URL"):
        try:
            storage_service.ensure_bucket()
        except Exception as e:
            print(f"[WARN] MinIO Bucket konnte nicht erstellt werden: {e}")
        # Update-Zustand liegt in der Datenbank (api/system.py) und überlebt
        # damit den Neustart. Nach einem Update (oder einem Abbruch mittendrin)
        # muss er zurück auf „idle", sonst bliebe das Update-Banner stehen.
        try:
            from app.api.system import update_zustand_nach_neustart_zuruecksetzen
            update_zustand_nach_neustart_zuruecksetzen()
        except Exception as e:
            print(f"[WARN] Update-Zustand konnte nicht zurückgesetzt werden: {e}")
    # Auto-Scan für den Mail-Import (Aufgabenmodul); in Tests deaktiviert
    try:
        from app.services.mail_ingest import start_background_scanner
        start_background_scanner()
    except Exception as e:
        print(f"[WARN] Mail-Scanner konnte nicht gestartet werden: {e}")
    # Wiederkehrende Rechnungen automatisch als Entwurf erzeugen; in Tests deaktiviert
    try:
        from app.services.recurring_service import start_recurring_worker
        start_recurring_worker()
    except Exception as e:
        print(f"[WARN] Wiederkehr-Worker konnte nicht gestartet werden: {e}")
    # Fällige, unbeglichene Rechnungen auf "überfällig" setzen; in Tests deaktiviert
    try:
        from app.services.overdue_service import start_overdue_worker
        start_overdue_worker()
    except Exception as e:
        print(f"[WARN] Fälligkeits-Worker konnte nicht gestartet werden: {e}")
    # Postecke: geplante Posts mit Direktanbindung automatisch veröffentlichen
    try:
        from app.services.social_publish import start_postecke_worker
        start_postecke_worker()
    except Exception as e:
        print(f"[WARN] Postecke-Worker konnte nicht gestartet werden: {e}")
    # Serverseitiges OneDrive-Backup (tägliche Automatik); in Tests deaktiviert
    try:
        from app.services.backup_service import start_backup_worker
        start_backup_worker()
    except Exception as e:
        print(f"[WARN] Backup-Worker konnte nicht gestartet werden: {e}")
    # HTTPS-Zertifikat überwachen und die Administratoren rechtzeitig warnen.
    # Dritte Sicherungsebene: certbot erneuert (Container), der systemd-Timer
    # springt bei Ausfall ein — und dieser Worker meldet sich, falls trotzdem
    # etwas durchrutscht. In Tests deaktiviert.
    try:
        from app.services.ssl_service import start_ssl_worker
        start_ssl_worker()
    except Exception as e:
        print(f"[WARN] SSL-Überwachung konnte nicht gestartet werden: {e}")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
