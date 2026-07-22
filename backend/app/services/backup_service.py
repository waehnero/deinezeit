"""
Backup-Service – serverseitige Datenbank-Sicherung.

Erzeugt per ``pg_dump`` einen vollständigen SQL-Dump der Datenbank und kann ihn
optional über die Microsoft-Graph-API nach OneDrive / SharePoint hochladen
(Backup-Ziel ``onedrive``). Die Credentials-Logik ist identisch zum
Speicher-Provider (``storage_service``): entweder werden die Graph-Zugangsdaten
aus dem E-Mail-Modul (``ms_*``) wiederverwendet oder eigene ``backup_onedrive_*``
Zugangsdaten genutzt. Das Zielverzeichnis in OneDrive ist frei wählbar.

Die tägliche Automatik läuft – wie der Wiederkehr-/Mail-Worker – in einem
eigenen Daemon-Thread (in Tests deaktiviert).
"""
import os
import json
import subprocess
import threading
import time
from datetime import datetime, timezone, date, timedelta


# ── pg_dump ───────────────────────────────────────────────────────────────────

def create_pg_dump(timeout: int = 60) -> bytes:
    """Erzeugt einen vollständigen SQL-Dump der Datenbank als Bytes.

    Wirft RuntimeError bei Parsing-/Ausführungsfehlern (aufrufer-freundlich, damit
    API-Endpunkt sauber HTTP 500 mit Klartext liefern kann)."""
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        parts   = db_url.replace("postgresql://", "").split("@")
        user_pw = parts[0].split(":")
        host_db = parts[1].split("/")
        db_user = user_pw[0]
        db_pass = user_pw[1] if len(user_pw) > 1 else ""
        db_host = host_db[0].split(":")[0]
        db_name = host_db[1]
    except Exception:
        raise RuntimeError("Datenbank-URL konnte nicht geparst werden")

    env = os.environ.copy()
    env["PGPASSWORD"] = db_pass
    try:
        result = subprocess.run(
            ["pg_dump", "-h", db_host, "-U", db_user, "-d", db_name, "--no-owner"],
            capture_output=True, text=True, env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Backup-Timeout nach {timeout} Sekunden")
    except FileNotFoundError:
        raise RuntimeError("pg_dump nicht gefunden — bitte Container neu bauen")
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump Fehler: {result.stderr[:200]}")
    return result.stdout.encode("utf-8")


# ── OneDrive-Provider fürs Backup ─────────────────────────────────────────────

_BACKUP_OD_KEYS = [
    "backup_onedrive_use_graph_creds", "backup_onedrive_tenant_id",
    "backup_onedrive_client_id", "backup_onedrive_client_secret",
    "backup_onedrive_drive_type", "backup_onedrive_site_id",
    "backup_onedrive_user", "backup_onedrive_folder",
    "ms_tenant_id", "ms_client_id", "ms_client_secret",
]


def _load_backup_settings(db) -> dict:
    from app.models.settings import Setting
    keys = _BACKUP_OD_KEYS + ["backup_keep_days", "backup_schedule_time",
                              "backup_target", "backup_last_at"]
    rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
    return {r.key: r.value for r in rows}


def build_backup_onedrive_provider(settings: dict):
    """Baut den OneDrive-Provider fürs Backup aus den (bereits geladenen) Settings.

    Zielordner = ``backup_onedrive_folder`` (eigenes Verzeichnis, unabhängig vom
    Speicher-Provider)."""
    from app.services.storage_service import OneDriveProvider
    use_graph = settings.get("backup_onedrive_use_graph_creds", "false") == "true"
    return OneDriveProvider(
        tenant_id     = settings.get("ms_tenant_id" if use_graph else "backup_onedrive_tenant_id", ""),
        client_id     = settings.get("ms_client_id" if use_graph else "backup_onedrive_client_id", ""),
        client_secret = settings.get("ms_client_secret" if use_graph else "backup_onedrive_client_secret", ""),
        drive_type    = settings.get("backup_onedrive_drive_type", "personal"),
        site_id       = settings.get("backup_onedrive_site_id", ""),
        user          = settings.get("backup_onedrive_user", ""),
        root_folder   = settings.get("backup_onedrive_folder", "DeineZeit-Backups"),
    )


def _apply_retention(provider, keep_days: int) -> int:
    """Löscht .sql-Backups im Zielordner, die älter als keep_days sind.
    Best-effort; Fehler werden geschluckt. Gibt Anzahl gelöschter Dateien zurück."""
    if keep_days <= 0:
        return 0
    deleted = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        for item in provider.list_children():
            name = item.get("name", "")
            if not name.startswith("deinezeit_backup_") or not name.endswith(".sql"):
                continue
            mod_raw = item.get("lastModifiedDateTime", "")
            try:
                mod = datetime.fromisoformat(mod_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            if mod < cutoff:
                provider.delete(name)
                deleted += 1
    except Exception:
        pass
    return deleted


def run_onedrive_backup(db) -> dict:
    """Erzeugt einen DB-Dump und lädt ihn nach OneDrive/SharePoint hoch.
    Aktualisiert backup_last_at + backup_history. Gibt {ok, message, filename} zurück."""
    from app.api.settings import _save  # zentrale Save-Logik wiederverwenden

    settings = _load_backup_settings(db)
    provider = build_backup_onedrive_provider(settings)

    dump = create_pg_dump()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename  = f"deinezeit_backup_{timestamp}.sql"

    provider.upload(filename, dump, "application/sql")

    # Verifizieren, dass die Datei wirklich am Ziel liegt (Metadaten holen)
    meta = None
    try:
        meta = provider.item_meta(filename)
    except Exception:
        meta = None
    if not meta:
        raise RuntimeError(
            f"Upload gemeldet, aber Datei '{filename}' im Ziel nicht auffindbar – "
            "bitte Benutzer/Zielverzeichnis prüfen")
    web_url    = meta.get("webUrl", "")
    drive_name = ((meta.get("parentReference") or {}).get("driveType") or "OneDrive")

    try:
        keep_days = int(settings.get("backup_keep_days", "30") or "30")
    except ValueError:
        keep_days = 30
    _apply_retention(provider, keep_days)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        from app.models.settings import Setting
        hr = db.query(Setting).filter(Setting.key == "backup_history").first()
        history = json.loads(hr.value) if hr and hr.value else []
    except Exception:
        history = []
    history.insert(0, now_iso)
    history = history[:3]
    _save(db, "backup_last_at", now_iso)
    _save(db, "backup_history", json.dumps(history))

    size_kb = round(len(dump) / 1024, 1)
    return {"ok": True, "filename": filename, "web_url": web_url,
            "message": f"Backup '{filename}' ({size_kb} KB) hochgeladen"
                       + (f" – {web_url}" if web_url else "")}


# ── Hintergrund-Worker (tägliche Automatik) ───────────────────────────────────
_worker_started = False


def _parse_hhmm(value: str) -> tuple:
    try:
        h, m = value.strip().split(":")
        return int(h), int(m)
    except Exception:
        return 2, 0


def _worker_loop():
    from app.db.base import SessionLocal
    last_run_day = None
    while True:
        time.sleep(300)  # alle 5 Minuten prüfen
        try:
            db = SessionLocal()
            try:
                settings = _load_backup_settings(db)
                if settings.get("backup_target") != "onedrive":
                    continue
                now = datetime.now()
                heute = now.date()
                if last_run_day == heute:
                    continue
                sh, sm = _parse_hhmm(settings.get("backup_schedule_time", "02:00"))
                if (now.hour, now.minute) < (sh, sm):
                    continue
                # Am selben Tag nicht doppelt: prüfe backup_last_at
                last_at = settings.get("backup_last_at", "")
                try:
                    if last_at and datetime.fromisoformat(last_at).date() == heute:
                        last_run_day = heute
                        continue
                except Exception:
                    pass
                res = run_onedrive_backup(db)
                last_run_day = heute
                print(f"[INFO] Backup: {res.get('message')}")
            finally:
                db.close()
        except Exception as e:
            print(f"[WARN] Backup-Worker: {e}")


def start_backup_worker():
    """Startet den Backup-Thread (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_BACKUP_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="backup-onedrive").start()
