"""
System-Verwaltung: Versionsanzeige, Zertifikatsstatus, angemeldete Sitzungen

Bis 04.09.2026 lag hier auch das In-App-Update (Knopf in den Einstellungen,
das den Server per Docker-Socket neu baute). Es wurde ersatzlos gestrichen
(Audit SEC-002, Korrekturschritt K-21): Der Docker-Socket im Backend-Container
war gleichbedeutend mit root auf dem Server — ein einziger Fehler im Backend
hätte den ganzen Server preisgegeben. Updates kommen seither ausschließlich
über den CI-Deploy (GitHub Actions nach grüner Prüfung auf ``main``).
"""
import os
import re
import time
import httpx
from datetime import datetime, timedelta, timezone
from typing import List
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.api.auth import absender_meta
from app.core import auth_events as EV
from app.models.user import User, UserSession
from app.schemas.user import AdminSessionResponse
from app.services.auth_service import auth_service
from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health():
    """Einfacher Health-Check (Container-Healthcheck, Deploy-Prüfung)."""
    return {"status": "ok"}


# ── Aktive Benutzer ───────────────────────────────────────────────────────────
#
# Wird aus ``user_sessions.last_used_at`` gezählt (bei jedem Zugriff höchstens
# einmal je Minute fortgeschrieben, siehe auth_service.zugriff_vermerken) und
# gilt damit für alle Arbeitsprozesse gleichermaßen (Audit OPS-003).

def get_active_user_count(db: Session, minutes: int = 5) -> int:
    """Anzahl Benutzer mit einer lebenden Sitzung, die zuletzt vor höchstens
    ``minutes`` Minuten benutzt wurde."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return (db.query(UserSession.user_id)
              .filter(UserSession.revoked_at.is_(None),
                      UserSession.last_used_at > cutoff)
              .distinct().count())


# ── Hilfsfunktion: Versionsvergleich ──────────────────────────────────────────
def _version_newer(v1: str, v2: str) -> bool:
    """True wenn v1 neuer als v2 ist."""
    try:
        a = tuple(int(x) for x in v1.split("."))
        b = tuple(int(x) for x in v2.split("."))
        return a > b
    except Exception:
        return False


def _version_from_changelog_text(text: str) -> str:
    """Höchste Versionsnummer aus CHANGELOG.md-Inhalt extrahieren."""
    found = []
    for line in text.splitlines():
        m = re.match(r'^## \[(\d+\.\d+\.\d+)\]', line)
        if m:
            found.append(tuple(int(x) for x in m.group(1).split(".")))
    if not found:
        return ""
    best = max(found)
    return ".".join(str(x) for x in best)


def _is_local_mode() -> bool:
    """True wenn DEPLOY_MODE=local gesetzt ist (docker-compose.local.yml)."""
    return os.environ.get("DEPLOY_MODE", "").lower() == "local"


def _read_local_version() -> str:
    """Installierte Version aus lokaler CHANGELOG.md lesen."""
    # Suche CHANGELOG.md relativ zum Backend-Verzeichnis (zwei Ebenen hoch)
    base = os.path.dirname(os.path.abspath(__file__))
    for candidate in [
        os.path.join(base, "../../../CHANGELOG.md"),   # backend/app/api/ → root
        os.path.join(base, "../../CHANGELOG.md"),
        os.path.join(base, "../CHANGELOG.md"),
        "/opt/deinezeit/CHANGELOG.md",                 # Produktion: Nur-Lese-Mount
    ]:
        path = os.path.normpath(candidate)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    v = _version_from_changelog_text(f.read())
                    if v:
                        return v
            except Exception:
                pass
    return settings.APP_VERSION  # Fallback auf config.py


# ── Versionsanzeige ───────────────────────────────────────────────────────────
#
# Rein informativ: installierte Version und die neueste auf GitHub. Ist die
# GitHub-Version neuer, läuft gerade ein Deploy (oder er ist fehlgeschlagen —
# dann steht es in GitHub Actions). Einen Knopf zum Aktualisieren gibt es
# nicht mehr (K-21).
#
# Bis 02.09.2026 war /system/version ohne Anmeldung erreichbar und löste bei
# jedem Aufruf eine Anfrage an GitHub aus (Audit OPS-004 / PERF-001). Jetzt:
# nur angemeldet, Ergebnis zehn Minuten zwischengespeichert.
_VERSION_CACHE_SEKUNDEN = 600
_version_cache: dict = {"bis": 0.0, "wert": None}
_version_lock = Lock()


async def _version_ermitteln() -> dict:
    current = _read_local_version()
    latest = current
    update_available = False
    github_check_ok = False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://raw.githubusercontent.com/waehnero/deinezeit/main/CHANGELOG.md",
                headers={"Cache-Control": "no-cache"}
            )
            if resp.status_code == 200:
                github_check_ok = True
                v = _version_from_changelog_text(resp.text)
                if v and _version_newer(v, current):
                    latest = v
                    update_available = True
                elif v:
                    latest = v  # GitHub erreichbar, Version gleich oder älter
    except Exception:
        github_check_ok = False

    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "github_check_ok": github_check_ok,
        "local_mode": _is_local_mode(),
    }


@router.get("/version")
async def get_version_info(_: User = Depends(get_current_user)):
    """Aktuelle Version aus lokaler CHANGELOG.md, neueste von GitHub (10 min Cache)."""
    jetzt = time.monotonic()
    with _version_lock:
        if _version_cache["wert"] is not None and jetzt < _version_cache["bis"]:
            return _version_cache["wert"]
    wert = await _version_ermitteln()
    with _version_lock:
        _version_cache["wert"] = wert
        _version_cache["bis"] = time.monotonic() + _VERSION_CACHE_SEKUNDEN
    return wert


@router.get("/changelog")
async def get_changelog(_: User = Depends(get_current_user)):
    """CHANGELOG.md von GitHub laden."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://raw.githubusercontent.com/waehnero/deinezeit/main/CHANGELOG.md",
                headers={"Cache-Control": "no-cache"}
            )
            if resp.status_code == 200:
                return {"content": resp.text}
    except Exception:
        pass
    return {"content": "Changelog konnte nicht geladen werden."}


@router.get("/ssl-status")
def get_ssl_status(admin: User = Depends(require_admin)):
    """Zustand des HTTPS-Zertifikats: Restlaufzeit und ob die Automatik läuft.

    Nur für Administratoren — die Restlaufzeit eines Zertifikats ist zwar
    öffentlich einsehbar, ob die Erneuerungsautomatik ausgefallen ist aber
    nicht: das wäre ein Hinweis darauf, wann der Server angreifbar wird."""
    from app.services.ssl_service import zertifikat_status
    try:
        return zertifikat_status()
    except Exception as e:                                       # noqa: BLE001
        # Die System-Seite darf an einer Zertifikatsprüfung nicht scheitern.
        return {
            "status": "nicht_konfiguriert",
            "domain": None,
            "gueltig_bis": None,
            "tage_verbleibend": None,
            "automatik_laeuft": None,
            "meldung": f"Zertifikatsstatus nicht ermittelbar: {e}",
        }


@router.get("/active-users")
def get_active_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Anzahl aktiver Benutzer (letzte 5 Minuten) — aus ``user_sessions``,
    also unabhängig von der Zahl der Arbeitsprozesse."""
    count = get_active_user_count(db, minutes=5)
    # Eigenen User abziehen
    active_count = max(0, count - 1)
    return {"active_users": active_count, "total_including_me": count}


# ── Angemeldete Sitzungen (Administrator) ─────────────────────────────────────
#
# Beantwortet zwei Fragen, die im Betrieb regelmäßig auftauchen: „Wer arbeitet
# gerade?" (etwa vor einem Deploy oder einem Lasttest) und „Wer hat vergessen,
# sich abzumelden?". Deshalb werden ALLE offenen Sitzungen gezeigt, nicht nur
# die der letzten Minuten — die Vergessenen sind ja gerade die, die still sind.

def _sitzung_darstellen(sitzung: UserSession, jetzt: datetime,
                        aktuelle_id) -> AdminSessionResponse:
    zuletzt = sitzung.last_used_at or sitzung.created_at
    if zuletzt is not None and zuletzt.tzinfo is None:
        zuletzt = zuletzt.replace(tzinfo=timezone.utc)
    untaetig = int((jetzt - zuletzt).total_seconds() // 60) if zuletzt else None

    return AdminSessionResponse(
        id=sitzung.id,
        user_id=sitzung.user_id,
        user_name=sitzung.user.full_name if sitzung.user else "—",
        user_email=sitzung.user.email if sitzung.user else "—",
        device_label=sitzung.device_label,
        ip_address=sitzung.ip_address,
        created_at=sitzung.created_at,
        last_used_at=sitzung.last_used_at,
        expires_at=sitzung.expires_at,
        untaetig_minuten=untaetig,
        is_current=(sitzung.id == aktuelle_id),
    )


@router.get("/sitzungen", response_model=List[AdminSessionResponse])
def sitzungen_liste(request: Request, db: Session = Depends(get_db),
                          _: User = Depends(require_admin)):
    """Alle offenen Sitzungen, zuletzt aktive zuerst."""
    jetzt = datetime.now(timezone.utc)
    sitzungen = (db.query(UserSession)
                 .filter(UserSession.revoked_at.is_(None),
                         UserSession.expires_at > jetzt)
                 .order_by(UserSession.last_used_at.desc().nullslast(),
                           UserSession.created_at.desc())
                 .all())
    aktuelle = getattr(request.state, "session_id", None)
    return [_sitzung_darstellen(s, jetzt, aktuelle) for s in sitzungen]


@router.delete("/sitzungen/{session_id}")
def sitzung_beenden(session_id: UUID, request: Request,
                          db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """Eine einzelne Sitzung beenden — das vergessene Gerät.

    Der Widerruf wirkt sofort: Jeder Zugriff prüft, ob die Sitzung noch lebt
    (Migration 0054). Der Betroffene landet beim nächsten Aufruf auf der
    Anmeldeseite.
    """
    sitzung = auth_service.sitzung_laden(db, session_id)
    if sitzung is None or sitzung.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden")

    betroffener = sitzung.user
    auth_service.sitzung_widerrufen(db, sitzung, "admin")
    # In den Prüfpfad des BETROFFENEN, nicht des Administrators: Wer sich
    # wundert, warum er abgemeldet wurde, sieht es in seiner eigenen Liste.
    auth_service.ereignis(db, EV.SESSION_REVOKED, user=betroffener,
                          meta=absender_meta(request), session_id=session_id,
                          detail=f"durch Administrator {admin.email}")
    return {"message": "Sitzung beendet"}


@router.delete("/sitzungen/benutzer/{user_id}")
def benutzer_abmelden(user_id: UUID, request: Request,
                            db: Session = Depends(get_db),
                            admin: User = Depends(require_admin)):
    """Alle Geräte eines Benutzers abmelden."""
    betroffener = db.query(User).filter(User.id == user_id).first()
    if not betroffener:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Der Dienst kennt den Vorgang bereits (ein Commit für alle Sitzungen)
    anzahl = auth_service.alle_sitzungen_widerrufen(db, betroffener, "admin")

    auth_service.ereignis(db, EV.LOGOUT_ALL, user=betroffener,
                          meta=absender_meta(request),
                          detail=f"durch Administrator {admin.email}")
    return {"message": f"{anzahl} Sitzungen beendet", "anzahl": anzahl}
