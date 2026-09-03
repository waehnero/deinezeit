"""
System-Verwaltung: Versionsprüfung, Update-Prozess, angemeldete Sitzungen
"""
import asyncio
import subprocess
import os
import re
import time
import httpx
from starlette.concurrency import run_in_threadpool
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.api.auth import absender_meta
from app.core import auth_events as EV
from app.models.settings import Setting
from app.models.user import User, UserRole, UserSession
from app.db.base import SessionLocal
from app.schemas.user import AdminSessionResponse
from app.services.auth_service import auth_service
from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health():
    """Einfacher Health-Check — wird von update.sh genutzt um zu prüfen ob das Backend läuft."""
    return {"status": "ok"}

# ── Aktive Benutzer und Update-Zustand ───────────────────────────────────────
#
# Beides lag bis 02.09.2026 im Arbeitsspeicher EINES Prozesses (ein Dict für
# die letzte Aktivität je Benutzer, ein Dict für den Update-Vorgang). Das
# zwang UVICORN_WORKERS auf 1: Mit zwei Prozessen hätte der Browser mal den
# einen, mal den anderen gefragt, und die Update-Meldung wäre scheinbar
# zufällig erschienen und verschwunden (Audit OPS-003).
#
# Jetzt: Aktive Benutzer werden aus ``user_sessions.last_used_at`` gezählt
# (wird bei jedem Zugriff höchstens einmal je Minute fortgeschrieben, siehe
# auth_service.zugriff_vermerken). Der Update-Zustand liegt in der Tabelle
# ``settings`` unter ``update_*``-Schlüsseln. Beides gilt damit für alle
# Arbeitsprozesse gleichermaßen.

def get_active_user_count(db: Session, minutes: int = 5) -> int:
    """Anzahl Benutzer mit einer lebenden Sitzung, die zuletzt vor höchstens
    ``minutes`` Minuten benutzt wurde."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return (db.query(UserSession.user_id)
              .filter(UserSession.revoked_at.is_(None),
                      UserSession.last_used_at > cutoff)
              .distinct().count())


_UPDATE_FELDER = ("status", "scheduled_at", "initiated_by", "message")
_UPDATE_VORGABE = {"status": "idle", "scheduled_at": "", "initiated_by": "", "message": ""}


def _update_state_lesen(db: Session) -> dict:
    zeilen = {r.key: r.value for r in db.query(Setting).filter(
        Setting.key.in_([f"update_{k}" for k in _UPDATE_FELDER])).all()}
    state = {k: zeilen.get(f"update_{k}", v) or v for k, v in _UPDATE_VORGABE.items()}
    state["pending"] = state["status"] == "notifying"
    state["countdown_seconds"] = 0
    return state


def _update_state_schreiben(db: Session, **werte) -> None:
    jetzt = datetime.now(timezone.utc)
    for k, v in werte.items():
        assert k in _UPDATE_FELDER, k
        row = db.query(Setting).filter(Setting.key == f"update_{k}").first()
        if row is None:
            db.add(Setting(key=f"update_{k}", value=v or "", updated_at=jetzt))
        else:
            row.value = v or ""
            row.updated_at = jetzt
    db.commit()


# ── Hilfsfunktion: Versionsvergleich ──────────────────────────────────────────
def _version_newer(v1: str, v2: str) -> bool:
    """True wenn v1 neuer als v2 ist."""
    try:
        a = tuple(int(x) for x in v1.split("."))
        b = tuple(int(x) for x in v2.split("."))
        return a > b
    except Exception:
        return False


# ── Endpoints ─────────────────────────────────────────────────────────────────

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
        "/opt/deinezeit/CHANGELOG.md",                 # Produktions-Pfad
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


# ── Versionsprüfung ───────────────────────────────────────────────────────────
#
# Bis 02.09.2026 war /system/version ohne Anmeldung erreichbar und löste bei
# jedem Aufruf eine Anfrage an GitHub und — wenn die scheiterte — ein
# blockierendes ``git fetch`` (bis 15 s) aus. Damit konnte jeder Unbekannte den
# Server für alle anderen anhalten (Audit OPS-004 / PERF-001). Jetzt: nur
# angemeldet, Ergebnis zehn Minuten zwischengespeichert, git im Threadpool.
_VERSION_CACHE_SEKUNDEN = 600
_version_cache: dict = {"bis": 0.0, "wert": None}
_version_lock = Lock()


def _git_ahead_of_origin() -> bool:
    """Blockierend (Subprozess) — nur über run_in_threadpool aufrufen."""
    subprocess.run(["git", "-C", "/opt/deinezeit", "fetch", "origin", "main"],
                   capture_output=True, timeout=10)
    ahead = subprocess.run(
        ["git", "-C", "/opt/deinezeit", "log", "HEAD..origin/main", "--oneline"],
        capture_output=True, timeout=5, text=True)
    return bool(ahead.stdout.strip())


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

    # Fallback: git-basierte Prüfung wenn GitHub nicht per HTTP erreichbar
    if not github_check_ok:
        try:
            if await run_in_threadpool(_git_ahead_of_origin):
                update_available = True
                latest = f"{current}+"   # Neue Commits vorhanden, Versionsnummer unbekannt
        except Exception:
            pass

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
# gerade?" (etwa vor einem Update oder einem Lasttest) und „Wer hat vergessen,
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


@router.get("/update-status")
def get_update_status(db: Session = Depends(get_db)):
    """Update-Status abfragen — alle Benutzer pollen diesen Endpoint."""
    state = _update_state_lesen(db)

    # Countdown berechnen
    if state.get("scheduled_at") and state["status"] == "notifying":
        try:
            scheduled = datetime.fromisoformat(state["scheduled_at"])
            remaining = (scheduled - datetime.now(timezone.utc)).total_seconds()
            state["countdown_seconds"] = max(0, int(remaining))
        except Exception:
            state["countdown_seconds"] = 0

    return state


@router.post("/update/start")
async def start_update(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Update-Prozess starten: Benutzer benachrichtigen, nach 2 Minuten ausführen."""
    if _is_local_mode():
        raise HTTPException(
            status_code=400,
            detail="Updates sind in der lokalen Entwicklungsinstanz nicht verfügbar. "
                   "Bitte 'git pull' im Projektverzeichnis ausführen und die Container neu starten.",
        )

    if _update_state_lesen(db)["status"] not in ("idle", "done", "failed"):
        raise HTTPException(status_code=409, detail="Ein Update-Prozess läuft bereits")

    scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=2)

    _update_state_schreiben(
        db,
        status="notifying",
        scheduled_at=scheduled_at.isoformat(),
        initiated_by=admin.full_name,
        message=f"Update wird in 2 Minuten von {admin.full_name} gestartet. Bitte speichern Sie Ihre Arbeit.",
    )

    # Hintergrund-Task: nach 2 Minuten Update ausführen
    asyncio.create_task(_run_update_after_delay(120))

    return {"ok": True, "scheduled_at": scheduled_at.isoformat()}


@router.post("/update/cancel")
def cancel_update(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Update abbrechen (nur während der Benachrichtigungs-Phase möglich)."""
    if _update_state_lesen(db)["status"] != "notifying":
        raise HTTPException(status_code=409, detail="Update kann jetzt nicht mehr abgebrochen werden")

    _update_state_schreiben(db, status="idle", scheduled_at="",
                            message="Update wurde abgebrochen.")
    return {"ok": True}


# ── Hintergrund-Update ────────────────────────────────────────────────────────

def _mit_db(fn):
    """Kurzlebige Sitzung für den Hintergrund-Task (er hat keine Request-Session)."""
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


async def _run_update_after_delay(delay_seconds: int):
    await asyncio.sleep(delay_seconds)

    # Prüfen ob noch nicht abgebrochen (Zustand liegt in der Datenbank)
    if await run_in_threadpool(_mit_db, lambda db: _update_state_lesen(db)["status"]) != "notifying":
        return

    await run_in_threadpool(_mit_db, lambda db: _update_state_schreiben(
        db, status="updating", message="Update wird ausgeführt…"))

    # In separatem Thread ausführen damit der Event Loop nicht blockiert
    await run_in_threadpool(_execute_update)

    # Watchdog: Wenn das Backend nach dem Update noch läuft (kein Neustart erfolgt),
    # wurde kein neuer Commit gefunden oder der Build schlug vor dem Container-Neustart fehl.
    # Nach 5 Minuten Status zurücksetzen damit Benutzer nicht dauerhaft ausgesperrt bleiben.
    await asyncio.sleep(300)
    await run_in_threadpool(_mit_db, _update_watchdog)


def update_zustand_nach_neustart_zuruecksetzen() -> None:
    """Beim Start: einen liegengebliebenen Update-Zustand beenden."""
    def _reset(db):
        if _update_state_lesen(db)["status"] in ("notifying", "updating"):
            _update_state_schreiben(db, status="idle", scheduled_at="", message="")
    _mit_db(_reset)


def _update_watchdog(db: Session) -> None:
    if _update_state_lesen(db)["status"] == "updating":
        _update_state_schreiben(db, status="idle", scheduled_at="", message="")


def _execute_update():
    """
    Update starten: Einen unabhängigen docker:cli-Container spawnen, der update.sh ausführt.

    Warum separater Container?
    Der Backend-Container wird beim Update selbst neu gestartet. Würde das Update-Skript
    direkt im Backend-Container laufen, würde der Prozess beim Neustart des Containers
    abrupt beendet — docker compose bliebe in einem halbfertigen Zustand.
    Der docker:cli-Container ist NICHT Teil des Compose-Projekts und läuft unabhängig
    weiter, bis update.sh (inkl. Health-Check) abgeschlossen ist.
    """
    install_dir = os.environ.get("INSTALL_DIR", "/opt/deinezeit")

    try:
        # Evtl. noch laufenden Updater aus einem früheren (fehlgeschlagenen) Versuch entfernen
        subprocess.run(
            ["docker", "rm", "-f", "deinezeit_updater"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Separaten Updater-Container starten
        # --network host: damit curl http://localhost/api/health den nginx auf Port 80 erreicht
        subprocess.Popen(
            [
                "docker", "run", "--rm",
                "--name", "deinezeit_updater",
                "--network", "host",
                "-v", "/var/run/docker.sock:/var/run/docker.sock",
                "-v", f"{install_dir}:{install_dir}",
                "-e", f"INSTALL_DIR={install_dir}",
                "-w", install_dir,
                "docker:cli",
                "sh", "-c", "apk add --quiet --no-progress git curl && sh update.sh",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Status bleibt "updating". Er liegt jetzt in der Datenbank und überlebt
        # den Neustart — deshalb setzt ihn der Start (startup_event in main.py)
        # zurück, sonst bliebe die Update-Meldung nach einem erfolgreichen
        # Update stehen. Das Frontend zeigt die Wartungsseite bis nginx wieder antwortet.

    except Exception as e:
        fehler = f"Update konnte nicht gestartet werden: {e}"
        _mit_db(lambda db: _update_state_schreiben(db, status="failed", message=fehler))
