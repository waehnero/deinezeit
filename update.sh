#!/bin/sh
# DeineZeit – Server-Update-Skript
# Wird in einem separaten docker:cli-Container ausgeführt (außerhalb des Compose-Projekts),
# damit der Neustart der App-Container diesen Prozess nicht unterbricht.
#
# Ablauf:
#   1. Aktuellen Commit als Rollback-Punkt sichern
#   2. git pull
#   3. docker compose build
#   4. docker compose up -d
#   5. Health-Check (max. 2 Minuten)
#   6. Bei Fehler: automatischer Rollback auf Vorgänger-Version

set -e

INSTALL_DIR="${INSTALL_DIR:-/opt/deinezeit}"
LOG_FILE="$INSTALL_DIR/logs/update.log"
COMPOSE="docker compose -f $INSTALL_DIR/docker-compose.yml --project-directory $INSTALL_DIR"

mkdir -p "$INSTALL_DIR/logs"

log() {
    MSG="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$MSG"
    echo "$MSG" >> "$LOG_FILE"
}

rollback() {
    log ""
    log "!!! ROLLBACK wird durchgeführt !!!"
    cd "$INSTALL_DIR"
    # Code auf vorherigen Commit zurücksetzen
    git reset --hard "$ROLLBACK_COMMIT" >> "$LOG_FILE" 2>&1 || true
    # Container mit bisherigen (noch gecachten) Images neu starten
    $COMPOSE up -d >> "$LOG_FILE" 2>&1 || true
    log "Rollback abgeschlossen – Vorgänger-Version läuft wieder."
    log ""
}

log ""
log "========================================"
log "  DeineZeit Update gestartet"
log "========================================"

cd "$INSTALL_DIR"

# ── Rollback-Punkt sichern ────────────────────────────────────────────────────
ROLLBACK_COMMIT=$(git rev-parse HEAD)
log "Rollback-Commit: $ROLLBACK_COMMIT"

# ── 1. Neue Version von GitHub laden ─────────────────────────────────────────
log ""
log "[1/3] Neue Version von GitHub laden..."
if ! git pull origin main >> "$LOG_FILE" 2>&1; then
    log "FEHLER: git pull fehlgeschlagen – keine Änderungen übernommen, kein Rollback nötig."
    exit 1
fi
NEW_COMMIT=$(git rev-parse HEAD)
log "Neuer Commit: $NEW_COMMIT"

if [ "$ROLLBACK_COMMIT" = "$NEW_COMMIT" ]; then
    log "Keine neuen Commits vorhanden – Update übersprungen."
    exit 0
fi

# ── 2. Docker Images bauen ────────────────────────────────────────────────────
log ""
log "[2/3] Docker Images werden gebaut..."
if ! $COMPOSE build >> "$LOG_FILE" 2>&1; then
    log "FEHLER: Build fehlgeschlagen."
    rollback
    exit 1
fi
log "Build erfolgreich."

# ── 3. Container neu starten ──────────────────────────────────────────────────
log ""
log "[3/3] Container werden neu gestartet..."
if ! $COMPOSE up -d >> "$LOG_FILE" 2>&1; then
    log "FEHLER: Container-Start fehlgeschlagen."
    rollback
    exit 1
fi
log "Container gestartet."

# ── Health-Check (max. 2 Minuten) ─────────────────────────────────────────────
log ""
log "Warte auf Backend-Bereitschaft..."
TRIES=0
while [ "$TRIES" -lt 24 ]; do
    sleep 5
    TRIES=$((TRIES + 1))
    if curl -sf "http://localhost/api/health" > /dev/null 2>&1; then
        log "Backend ist bereit! (nach $((TRIES * 5)) Sekunden)"
        log ""
        log "========================================"
        log "  Update erfolgreich abgeschlossen!"
        log "========================================"
        log ""
        exit 0
    fi
    log "  Warten... ($((TRIES * 5))s / 120s)"
done

log "FEHLER: Backend nach 120 Sekunden nicht erreichbar."
rollback
exit 1
