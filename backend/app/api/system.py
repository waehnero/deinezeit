"""
System-Verwaltung: Versionsprüfung, Update-Prozess, aktive Benutzer
"""
import asyncio
import subprocess
import os
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

@router.get("/version")
async def get_version_info():
    """Aktuelle Version und neueste Version von GitHub vergleichen."""
    current = settings.APP_VERSION
    latest = current
    update_available = False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://raw.githubusercontent.com/waehnero/deinezeit/main/frontend/package.json",
                headers={"Cache-Control": "no-cache"}
            )
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("version", current)
                update_available = _version_newer(latest, current)
    except Exception:
        pass

    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
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


def _execute_update():
    """Update auf dem Host ausführen (docker socket + git)."""
    install_dir = os.environ.get("INSTALL_DIR", "/opt/deinezeit")

    try:
        # 1. Neuesten Code von GitHub holen
        subprocess.run(
            ["git", "-C", install_dir, "pull", "origin", "main"],
            check=True, capture_output=True, timeout=60
        )

        # 2. Docker-Images neu bauen und Container neu starten
        #    Läuft als detached Prozess — der Backend-Container startet sich selbst neu
        subprocess.Popen(
            [
                "docker", "compose",
                "-f", f"{install_dir}/docker-compose.yml",
                "up", "-d", "--build", "--remove-orphans"
            ],
            cwd=install_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        _set_update_state(
            status="done",
            message="Update erfolgreich! Das System wird neu gestartet.",
        )

    except subprocess.TimeoutExpired:
        _set_update_state(status="failed", message="Update fehlgeschlagen: Zeitüberschreitung beim git pull.")
    except subprocess.CalledProcessError as e:
        _set_update_state(status="failed", message=f"Update fehlgeschlagen: {e.stderr.decode()[:200]}")
    except Exception as e:
        _set_update_state(status="failed", message=f"Update fehlgeschlagen: {str(e)}")
