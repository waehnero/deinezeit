from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import os
from app.core.config import settings
from app.api import auth, users, masterdata, zeiterfassung, reports, datacenter, system, invoice, accounting, projektplan, aufgaben, mailimport, gdpr, postecke, setup
from app.api import settings as settings_api
from app.services import storage_service
from app.api.system import record_activity

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── App — API-Docs in Produktion deaktivieren ─────────────────────────────────
_is_dev = os.environ.get("APP_ENV", "production").lower() == "development"

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs"  if _is_dev else None,
    redoc_url="/api/redoc" if _is_dev else None,
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
# Modulrechte: Router ganzer Module werden hier mit require_module(<key>)
# abgesichert (Admin hat immer alles; allowed_modules=NULL = alle erlaubt).
# Bewusst OHNE Modul-Sperre (Querbezüge, siehe core/modules.py):
#   masterdata  → Lesen für alle (Auswahlfelder); Schreiben je Endpunkt gesperrt
#   datacenter  → Anhänge je Datensatz für alle; nur Übersicht je Endpunkt gesperrt
#   reports     → gehört fachlich zur Zeiterfassung
from app.api.deps import require_module as _rm
from fastapi import Depends as _Dep

app.include_router(setup.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
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
                   dependencies=[_Dep(_rm("verkauf"))])
app.include_router(projektplan.router, prefix="/api",
                   dependencies=[_Dep(_rm("projekte"))])
app.include_router(aufgaben.router, prefix="/api",
                   dependencies=[_Dep(_rm("aufgaben"))])
app.include_router(mailimport.router, prefix="/api",
                   dependencies=[_Dep(_rm("aufgaben"))])
app.include_router(gdpr.router, prefix="/api")
app.include_router(postecke.router, prefix="/api",
                   dependencies=[_Dep(_rm("postecke"))])


# ── Aktivitäts-Middleware: letzte Aktivität pro Benutzer tracken ──────────────
@app.middleware("http")
async def track_activity(request: Request, call_next):
    response = await call_next(request)
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            from app.core.security import decode_token
            payload = decode_token(token)
            if payload and payload.get("sub") and payload.get("type") == "access":
                record_activity(payload["sub"])
    except Exception:
        pass
    return response

# ── MinIO Bucket beim Start sicherstellen ─────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    try:
        storage_service.ensure_bucket()
    except Exception as e:
        print(f"[WARN] MinIO Bucket konnte nicht erstellt werden: {e}")
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
    # Postecke: geplante Posts mit Direktanbindung automatisch veröffentlichen
    try:
        from app.services.social_publish import start_postecke_worker
        start_postecke_worker()
    except Exception as e:
        print(f"[WARN] Postecke-Worker konnte nicht gestartet werden: {e}")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
