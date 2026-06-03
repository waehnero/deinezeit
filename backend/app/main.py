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
from app.api import auth, users, masterdata, zeiterfassung, reports, datacenter, system, invoice
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
STATIC_DIR = "/app/static"
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── API-Router ────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(masterdata.router, prefix="/api")
app.include_router(zeiterfassung.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(datacenter.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(invoice.router, prefix="/api")


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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
