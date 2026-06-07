"""
System-Verwaltung: Versionsprüfung, Update-Prozess, aktive Benutzer
"""
import asyncio
import subprocess
import os
import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User, UserRole
from app.core.config import settings

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health():
    """Einfacher Health-Check — wird von update.sh genutzt um zu prüfen ob das Backend läuft."""
    return {"status": "ok"}

# ── Aktive Sessions (in-memory) ───────────────────────────────────────────────
# { user_id: last_active_datetime }
_active_sessions: dict = {}
_sessions_lock = Lock()

def record_activity(user_id: str):
    """Letzte Aktivität eines Benutzers aktualisieren."""
    with _sessions_lock:
        _active_sessions[user_id] = datetime.now(timezone.utc)

def get_active_user_count(minutes: int = 5) -> int:
    """Anzahl Benutzer die in den letzten N Minuten aktiv waren."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with _sessions_lock:
        return sum(1 for ts in _active_sessions.values() if ts > cutoff)

def get_active_user_ids(minutes: int = 5) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with _sessions_lock:
        return [uid for uid, ts in _active_sessions.items() if ts > cutoff]

# ── Update-Status (in-memory) ─────────────────────────────────────────────────
_update_state = {
    "status": "idle",          # idle | notifying | updating | done | failed
    "pending": False,
    "scheduled_at": None,      # ISO-String wann Update ausgeführt wird
    "countdown_seconds": 0,
    "initiated_by": None,
    "message": "",
}
_update_lock = Lock()

def _set_update_state(**kwargs):
    with _update_lock:
        _update_state.update(kwargs)

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
    """Erste Versionsnummer aus CHANGELOG.md-Inhalt extrahieren."""
    for line in text.splitlines():
        m = re.match(r'^## \[(\d+\.\d+\.\d+)\]', line)
        if m:
            return m.group(1)
    return ""


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


@router.get("/version")
async def get_version_info():
    """Aktuelle Version aus lokaler CHANGELOG.md, neueste von GitHub."""
    current = _read_local_version()
    latest = current
    update_available = False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://raw.githubusercontent.com/waehnero/deinezeit/main/CHANGELOG.md",
                headers={"Cache-Control": "no-cache"}
            )
            if resp.status_code == 200:
                v = _version_from_changelog_text(resp.text)
                if v and _version_newer(v, current):
                    # GitHub hat eine neuere Version als die installierte
                    latest = v
                    update_available = True
                # Wenn GitHub-Version älter/gleich ist → latest bleibt = current
    except Exception:
        pass

    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "local_mode": _is_local_mode(),
    }


@router.get("/changelog")
async def get_changelog():
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


@router.get("/active-users")
async def get_active_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Anzahl aktiver Benutzer (letzte 5 Minuten)."""
    count = get_active_user_count(minutes=5)
    # Eigenen User abziehen
    active_count = max(0, count - 1)
    return {"active_users": active_count, "total_including_me": count}


@router.get("/update-status")
async def get_update_status():
    """Update-Status abfragen — alle Benutzer pollen diesen Endpoint."""
    with _update_lock:
        state = dict(_update_state)

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

    with _update_lock:
        if _update_state["status"] not in ("idle", "done", "failed"):
            raise HTTPException(status_code=409, detail="Ein Update-Prozess läuft bereits")

    scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=2)

    _set_update_state(
        status="notifying",
        pending=True,
        scheduled_at=scheduled_at.isoformat(),
        initiated_by=admin.full_name,
        message=f"Update wird in 2 Minuten von {admin.full_name} gestartet. Bitte speichern Sie Ihre Arbeit.",
        countdown_seconds=120,
    )

    # Hintergrund-Task: nach 2 Minuten Update ausführen
    asyncio.create_task(_run_update_after_delay(120))

    return {"ok": True, "scheduled_at": scheduled_at.isoformat()}


@router.post("/update/cancel")
async def cancel_update(admin: User = Depends(require_admin)):
    """Update abbrechen (nur während der Benachrichtigungs-Phase möglich)."""
    with _update_lock:
        if _update_state["status"] != "notifying":
            raise HTTPException(status_code=409, detail="Update kann jetzt nicht mehr abgebrochen werden")

    _set_update_state(
        status="idle",
        pending=False,
        scheduled_at=None,
        message="Update wurde abgebrochen.",
    )
    return {"ok": True}


# ── Hintergrund-Update ────────────────────────────────────────────────────────

async def _run_update_after_delay(delay_seconds: int):
    await asyncio.sleep(delay_seconds)

    # Prüfen ob noch nicht abgebrochen
    with _update_lock:
        if _update_state["status"] != "notifying":
            return

    _set_update_state(status="updating", pending=False, message="Update wird ausgeführt…")

    # In separatem Thread ausführen damit der Event Loop nicht blockiert
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _execute_update)

    # Watchdog: Wenn das Backend nach dem Update noch läuft (kein Neustart erfolgt),
    # wurde kein neuer Commit gefunden oder der Build schlug vor dem Container-Neustart fehl.
    # Nach 5 Minuten Status zurücksetzen damit Benutzer nicht dauerhaft ausgesperrt bleiben.
    await asyncio.sleep(300)
    with _update_lock:
        if _update_state["status"] == "updating":
            _set_update_state(status="idle", pending=False, message="")


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

        # Status bleibt "updating" — nach dem Neustart der Container resettet sich der
        # In-Memory-State ohnehin. Das Frontend zeigt die Wartungsseite bis nginx wieder antwortet.

    except Exception as e:
        _set_update_state(status="failed", message=f"Update konnte nicht gestartet werden: {str(e)}")
