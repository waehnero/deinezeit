"""
Backup-Service – serverseitige Sicherung von Datenbank UND Dateispeicher.

Ein Backup ist seit 03.09.2026 ein ZIP-Archiv (Audit DATA-002):

    datenbank.sql        vollständiger pg_dump
    manifest.json        Version, Zeitpunkt, Migrationsstand, Dateiliste
    dateien/<schlüssel>  jedes Objekt aus dem MinIO-Bucket

Bis dahin wurde nur die Datenbank gesichert. Der Objektspeicher — Anhänge,
Positions- und Stammdatenbilder, Postecke-Medien und vor allem das
automatische **PDF-Archiv der Verkaufsbelege** — hing an einem Docker-Volume
ohne jede Sicherung. Ein Verlust des Volumes hätte die ``attachments``-Zeilen
ohne ihre Dateien zurückgelassen.

Dateien, die in WebDAV oder OneDrive liegen (Mischbetrieb), stehen nur im
Manifest — sie sind bereits extern. Wiederherstellung: docs/WIEDERHERSTELLUNG.md.

Das Archiv kann optional über die Microsoft-Graph-API nach OneDrive /
SharePoint hochgeladen werden (Backup-Ziel ``onedrive``). Die tägliche
Automatik läuft — wie der Wiederkehr-/Mail-Worker — in einem eigenen
Daemon-Thread (in Tests deaktiviert).
"""
import os
import json
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone, timedelta
from app.core import zeit


# ── pg_dump ───────────────────────────────────────────────────────────────────

def _db_zugang() -> dict:
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        parts   = db_url.replace("postgresql://", "").split("@")
        user_pw = parts[0].split(":")
        host_db = parts[1].split("/")
        return {
            "user": user_pw[0],
            "password": user_pw[1] if len(user_pw) > 1 else "",
            "host": host_db[0].split(":")[0],
            "name": host_db[1].split("?")[0],
        }
    except Exception:
        raise RuntimeError("Datenbank-URL konnte nicht geparst werden")


def _timeout_vorgabe(timeout) -> int:
    """Zeitlimit für pg_dump. Vorgabe 600 s statt bisher 60 — eine Datenbank,
    die in 60 s nicht durch ist, scheiterte sonst still bei jedem Backup.
    Überschreibbar über BACKUP_TIMEOUT_SEKUNDEN."""
    if timeout:
        return int(timeout)
    try:
        return int(os.environ.get("BACKUP_TIMEOUT_SEKUNDEN", "600"))
    except ValueError:
        return 600


def pg_dump_in_datei(pfad: str, timeout: int = None) -> None:
    """Schreibt den Dump direkt in eine Datei (nicht in den Arbeitsspeicher)."""
    z = _db_zugang()
    env = os.environ.copy()
    env["PGPASSWORD"] = z["password"]
    try:
        with open(pfad, "wb") as ziel:
            result = subprocess.run(
                ["pg_dump", "-h", z["host"], "-U", z["user"], "-d", z["name"], "--no-owner"],
                stdout=ziel, stderr=subprocess.PIPE, env=env,
                timeout=_timeout_vorgabe(timeout),
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Backup-Timeout nach {_timeout_vorgabe(timeout)} Sekunden")
    except FileNotFoundError:
        raise RuntimeError("pg_dump nicht gefunden — bitte Container neu bauen")
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump Fehler: {result.stderr.decode('utf-8', 'replace')[:200]}")


def create_pg_dump(timeout: int = None) -> bytes:
    """Vollständiger SQL-Dump als Bytes (für Aufrufer, die ihn im Speicher
    brauchen). Wirft RuntimeError bei Parsing-/Ausführungsfehlern."""
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        pfad = tmp.name
    try:
        pg_dump_in_datei(pfad, timeout)
        with open(pfad, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(pfad)
        except OSError:
            pass


# ── Archiv: Datenbank + Dateispeicher ────────────────────────────────────────

def _migrationsstand(db) -> str:
    """Alembic-Stand fürs Manifest. Im Savepoint: Fehlt die Tabelle (Testschema
    aus create_all), bleibt die Sitzung benutzbar."""
    try:
        from sqlalchemy import text
        with db.begin_nested():
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar() or ""
    except Exception:
        return ""


def create_backup_archive(db, timeout: int = None) -> tuple:
    """Erzeugt das ZIP-Archiv in einer temporären Datei.

    Rückgabe ``(pfad, manifest)``. Der Aufrufer löscht die Datei, wenn er sie
    ausgeliefert oder hochgeladen hat. Die Objekte werden einzeln geholt und
    gleich ins Archiv geschrieben — im Speicher liegt immer nur eine Datei.
    """
    from app.services import storage_service
    from app.models.attachment import Attachment
    from app.core.config import settings as app_settings

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_pfad = tmp.name
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        sql_pfad = tmp.name

    try:
        pg_dump_in_datei(sql_pfad, timeout)

        minio = storage_service.MinioProvider()
        try:
            objekte = minio.list_keys()
        except Exception as e:                                       # noqa: BLE001
            raise RuntimeError(f"Dateispeicher (MinIO) nicht erreichbar: {e}")

        # Anhänge in fremden Speichern nur verzeichnen — sie liegen schon extern
        extern = [{"id": str(a.id), "storage_key": a.storage_key,
                   "provider": a.storage_provider, "filename": a.filename}
                  for a in db.query(Attachment).filter(
                      Attachment.type == "file",
                      Attachment.storage_provider.isnot(None),
                      Attachment.storage_provider != "minio").all()]

        manifest = {
            "format": "deinezeit-backup/1",
            "erstellt": datetime.now(timezone.utc).isoformat(),
            "app_version": app_settings.APP_VERSION,
            "migration": _migrationsstand(db),
            "dateien_anzahl": len(objekte),
            "dateien_bytes": sum(o["size"] for o in objekte),
            "dateien": [o["key"] for o in objekte],
            "externe_anhaenge": extern,
            "fehler": [],
        }

        with zipfile.ZipFile(zip_pfad, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(sql_pfad, "datenbank.sql")
            for o in objekte:
                try:
                    daten, _ = minio.download(o["key"])
                    zf.writestr(f"dateien/{o['key']}", daten)
                except Exception as e:                               # noqa: BLE001
                    # Eine unlesbare Datei darf das Backup nicht verhindern —
                    # sie steht im Manifest, damit es nicht unbemerkt bleibt.
                    manifest["fehler"].append({"key": o["key"], "fehler": str(e)[:200]})
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    except Exception:
        try:
            os.remove(zip_pfad)
        except OSError:
            pass
        raise
    finally:
        try:
            os.remove(sql_pfad)
        except OSError:
            pass

    return zip_pfad, manifest


def backup_dateiname(endung: str = "zip") -> str:
    return f"deinezeit_backup_{zeit.jetzt().strftime('%Y-%m-%d_%H-%M')}.{endung}"


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
    """Löscht Backups (.sql/.zip) im Zielordner, die älter als keep_days sind.
    Best-effort; Fehler werden geschluckt. Gibt Anzahl gelöschter Dateien zurück."""
    if keep_days <= 0:
        return 0
    deleted = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        for item in provider.list_children():
            name = item.get("name", "")
            if not name.startswith("deinezeit_backup_") or \
               not (name.endswith(".sql") or name.endswith(".zip")):
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

    zip_pfad, manifest = create_backup_archive(db)
    try:
        with open(zip_pfad, "rb") as f:
            dump = f.read()
    finally:
        try:
            os.remove(zip_pfad)
        except OSError:
            pass
    filename = backup_dateiname("zip")

    provider.upload(filename, dump, "application/zip")

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
            "dateien": manifest["dateien_anzahl"],
            "message": f"Backup '{filename}' ({size_kb} KB, Datenbank + "
                       f"{manifest['dateien_anzahl']} Dateien) hochgeladen"
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
                now = zeit.jetzt()
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
