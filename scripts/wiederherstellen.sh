#!/bin/bash
# ============================================================
# DeineZeit – Wiederherstellung aus einem Backup-Archiv (am Server)
#
# Verwendung:  sudo bash scripts/wiederherstellen.sh /pfad/deinezeit_backup_JJJJ-MM-TT_HH-MM.zip
#
# Spielt die Datenbank (datenbank.sql) und alle Dateien des Objektspeichers
# (dateien/…) aus dem Archiv zurück, das „Backup herunterladen" bzw. das
# OneDrive-Backup erzeugt (Audit DATA-002, Anleitung: docs/WIEDERHERSTELLUNG.md).
#
# ACHTUNG: Ersetzt den kompletten Datenbestand. Vorher wird der aktuelle
# Stand gesichert (backups/vor-wiederherstellung_*.sql), aber Dateien im
# Objektspeicher, die im Archiv fehlen, bleiben liegen (sie werden nicht gelöscht).
# ============================================================
set -eo pipefail

ARCHIV="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
cd "$INSTALL_DIR"

if [ -z "$ARCHIV" ] || [ ! -f "$ARCHIV" ]; then
    echo "Verwendung: $0 /pfad/zum/deinezeit_backup_….zip"; exit 1
fi
if ! command -v unzip >/dev/null; then
    echo "✗ 'unzip' fehlt (apt-get install unzip)"; exit 1
fi
if ! docker compose ps --status running --services 2>/dev/null | grep -qx db; then
    echo "✗ Der Datenbank-Container läuft nicht (docker compose up -d db minio)"; exit 1
fi

source .env 2>/dev/null || true
DB_USER="${DB_USER:-deinezeit}"; DB_NAME="${DB_NAME:-deinezeit}"

ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT
unzip -q "$ARCHIV" -d "$ARBEIT"
if [ ! -f "$ARBEIT/datenbank.sql" ] || [ ! -f "$ARBEIT/manifest.json" ]; then
    echo "✗ Kein DeineZeit-Backup-Archiv (datenbank.sql / manifest.json fehlen)"; exit 1
fi
ANZAHL=$(find "$ARBEIT/dateien" -type f 2>/dev/null | wc -l)
echo "Archiv:      $ARCHIV"
echo "Erstellt:    $(grep -o '"erstellt": *"[^"]*"' "$ARBEIT/manifest.json" | cut -d'"' -f4)"
echo "Version:     $(grep -o '"app_version": *"[^"]*"' "$ARBEIT/manifest.json" | cut -d'"' -f4)"
echo "Migration:   $(grep -o '"migration": *"[^"]*"' "$ARBEIT/manifest.json" | cut -d'"' -f4)"
echo "Dateien:     $ANZAHL"
echo ""
echo "!!! Die Datenbank '$DB_NAME' wird KOMPLETT durch das Archiv ersetzt. !!!"
read -r -p "Fortfahren? (ja/nein) " ANTWORT
[ "$ANTWORT" = "ja" ] || { echo "Abgebrochen."; exit 1; }

# ── 1. Aktuellen Stand sichern ────────────────────────────────────────────────
mkdir -p backups
SICHERUNG="backups/vor-wiederherstellung_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T db pg_dump -U "$DB_USER" "$DB_NAME" > "$SICHERUNG"
echo "✓ Aktueller Stand gesichert: $SICHERUNG"

# ── 2. Anwendung anhalten (nginx bleibt: Wartungsseite) ──────────────────────
docker compose stop backend >/dev/null
echo "✓ Backend angehalten"

# ── 3. Datenbank ersetzen ─────────────────────────────────────────────────────
docker compose exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -q \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" \
    -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" \
    -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" >/dev/null
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q < "$ARBEIT/datenbank.sql"
echo "✓ Datenbank eingespielt"

# ── 4. Dateien in den Objektspeicher ─────────────────────────────────────────
if [ "$ANZAHL" -gt 0 ]; then
    docker compose run --rm -T -v "$ARBEIT/dateien:/wiederherstellung:ro" backend python3 - <<'PY'
import mimetypes, os
from app.services.storage_service import MinioProvider
p = MinioProvider()
n = 0
for wurzel, _, dateien in os.walk("/wiederherstellung"):
    for name in dateien:
        pfad = os.path.join(wurzel, name)
        key = os.path.relpath(pfad, "/wiederherstellung")
        with open(pfad, "rb") as f:
            p.upload(key, f.read(), mimetypes.guess_type(name)[0] or "application/octet-stream")
        n += 1
print(f"✓ {n} Datei(en) in den Objektspeicher geschrieben")
PY
fi

# ── 5. Migrationen nachziehen (falls das Archiv älter ist als der Code) ──────
docker compose run --rm backend alembic upgrade head >/dev/null
echo "✓ Migrationsstand aktuell"

# ── 6. Anwendung starten ──────────────────────────────────────────────────────
docker compose up -d backend >/dev/null
echo "✓ Backend gestartet"
echo ""
echo "Wiederherstellung abgeschlossen. Bitte anmelden und stichprobenartig prüfen"
echo "(Belege, Anhänge öffnen). Alle Benutzer müssen sich neu anmelden."
