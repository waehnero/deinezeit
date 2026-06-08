#!/bin/sh
# DeineZeit – Server-Update-Skript
# Wird in einem separaten docker:cli-Container ausgeführt (außerhalb des Compose-Projekts),
# damit der Neustart der App-Container diesen Prozess nicht unterbricht.
#
# Ablauf:
#   1. Rollback-Punkt sichern (aktueller Git-Commit)
#   2. nginx/conf.d/app.conf sichern (hat echten Domain-Namen, würde git pull blockieren)
#   3. app.conf auf Repo-Platzhalter zurücksetzen → git pull funktioniert
#   4. docker compose build
#   5. docker compose up -d
#   6. Health-Check (max. 2 Minuten)
#   7. app.conf mit echtem Domain-Namen neu generieren + nginx neu laden
#   8. Bei Fehler: automatischer Rollback auf Vorgänger-Version

INSTALL_DIR="${INSTALL_DIR:-/opt/deinezeit}"
LOG_FILE="$INSTALL_DIR/logs/update.log"
COMPOSE="docker compose -f $INSTALL_DIR/docker-compose.yml --project-directory $INSTALL_DIR"
APPCONF="$INSTALL_DIR/nginx/conf.d/app.conf"

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
    git reset --hard "$ROLLBACK_COMMIT" >> "$LOG_FILE" 2>&1 || true
    # Falls app.conf durch den Reset den Platzhalter enthält, Domain wiederherstellen
    if [ -n "$DOMAIN" ]; then
        sed "s/deine-domain.at/$DOMAIN/g" "$APPCONF" > /tmp/appconf.tmp && mv /tmp/appconf.tmp "$APPCONF"
    fi
    # Gesicherte Images wiederherstellen (damit wirklich der alte Code läuft)
    if docker image inspect deinezeit-backend:rollback > /dev/null 2>&1; then
        docker tag deinezeit-backend:rollback deinezeit-backend:latest >> "$LOG_FILE" 2>&1 || true
        log "Backend-Image auf Backup-Version zurückgesetzt."
    fi
    if docker image inspect deinezeit-frontend:rollback > /dev/null 2>&1; then
        docker tag deinezeit-frontend:rollback deinezeit-frontend:latest >> "$LOG_FILE" 2>&1 || true
        log "Frontend-Image auf Backup-Version zurückgesetzt."
    fi
    $COMPOSE up -d --force-recreate >> "$LOG_FILE" 2>&1 || true
    sleep 3
    docker exec deinezeit_nginx nginx -s reload >> "$LOG_FILE" 2>&1 || true
    log "Rollback abgeschlossen – Vorgänger-Version läuft wieder."
    log ""
}

log ""
log "========================================"
log "  DeineZeit Update gestartet"
log "========================================"

cd "$INSTALL_DIR"

# Fix: nginx.conf darf kein Verzeichnis sein (Docker erstellt Verzeichnis wenn Quelldatei fehlt)
if [ -d "$INSTALL_DIR/nginx/nginx.conf" ]; then
    log "WARNUNG: nginx/nginx.conf ist ein Verzeichnis — wird entfernt"
    rm -rf "$INSTALL_DIR/nginx/nginx.conf"
fi

# ── Rollback-Punkt sichern ────────────────────────────────────────────────────
ROLLBACK_COMMIT=$(git rev-parse HEAD)
log "Rollback-Commit: $ROLLBACK_COMMIT"

# ── Domain aus lokaler app.conf lesen (echte Domain, z.B. dz.meinserver.at) ──
# Die Server-Version enthält den echten Domain-Namen, den git nicht kennt.
DOMAIN=""
if [ -f "$APPCONF" ]; then
    DOMAIN=$(grep -oE 'server_name\s+[^;_]+;' "$APPCONF" | awk '{print $2}' | tr -d ';' | head -1)
    log "Erkannte Domain: ${DOMAIN:-unbekannt}"
fi
# Fallback: aus WEBAUTHN_RP_ID in .env
if [ -z "$DOMAIN" ] && [ -f "$INSTALL_DIR/.env" ]; then
    DOMAIN=$(grep '^WEBAUTHN_RP_ID=' "$INSTALL_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
    [ -n "$DOMAIN" ] && log "Domain aus .env gelesen: $DOMAIN"
fi

# ── app.conf auf Repo-Platzhalter zurücksetzen (damit git pull nicht abbricht) ─
git checkout -- nginx/conf.d/app.conf 2>/dev/null || true
log "nginx/conf.d/app.conf auf Repo-Version zurückgesetzt"

# ── 1. Neue Version von GitHub laden ─────────────────────────────────────────
log ""
log "[1/3] Neue Version von GitHub laden..."
if ! git fetch origin main >> "$LOG_FILE" 2>&1; then
    log "FEHLER: git fetch fehlgeschlagen – keine Änderungen übernommen, kein Rollback nötig."
    # Domain in app.conf wiederherstellen
    [ -n "$DOMAIN" ] && sed -i "s/deine-domain.at/$DOMAIN/g" "$APPCONF"
    exit 1
fi
if ! git reset --hard origin/main >> "$LOG_FILE" 2>&1; then
    log "FEHLER: git reset fehlgeschlagen – keine Änderungen übernommen, kein Rollback nötig."
    [ -n "$DOMAIN" ] && sed -i "s/deine-domain.at/$DOMAIN/g" "$APPCONF"
    exit 1
fi
NEW_COMMIT=$(git rev-parse HEAD)
log "Neuer Commit: $NEW_COMMIT"

if [ "$ROLLBACK_COMMIT" = "$NEW_COMMIT" ]; then
    log "Keine neuen Commits vorhanden – Update übersprungen."
    [ -n "$DOMAIN" ] && sed -i "s/deine-domain.at/$DOMAIN/g" "$APPCONF"
    exit 0
fi

# ── Domain in frisch gepullter app.conf einsetzen ─────────────────────────────
if [ -n "$DOMAIN" ]; then
    sed -i "s/deine-domain.at/$DOMAIN/g" "$APPCONF"
    log "nginx/conf.d/app.conf: Domain '$DOMAIN' eingesetzt"
fi

# ── Version aus package.json lesen und exportieren ────────────────────────────
# Wird als Umgebungsvariable an docker compose übergeben und überschreibt
# den Default in config.py — unabhängig vom Docker-Layer-Cache.
if [ -f "$INSTALL_DIR/frontend/package.json" ]; then
    APP_VERSION=$(grep '"version"' "$INSTALL_DIR/frontend/package.json" | head -1 | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    export APP_VERSION
    log "Version: $APP_VERSION"
fi

# ── 2. Docker Images bauen ────────────────────────────────────────────────────
log ""
log "[2/3] Docker Images werden gebaut..."
# Aktuelle Images als Rollback-Sicherung taggen
docker tag deinezeit-backend:latest deinezeit-backend:rollback >> "$LOG_FILE" 2>&1 || true
docker tag deinezeit-frontend:latest deinezeit-frontend:rollback >> "$LOG_FILE" 2>&1 || true
log "Aktuelle Images als Rollback-Backup gesichert."
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

# nginx force-recreate: stellt sicher dass Bind Mounts (nginx.conf, conf.d) frisch eingehängt werden
$COMPOSE up -d --force-recreate nginx >> "$LOG_FILE" 2>&1 || true
log "nginx neu erstellt (Bind Mounts aktualisiert)."

# ── Health-Check (max. 2 Minuten) ─────────────────────────────────────────────
log ""
log "Warte auf Backend-Bereitschaft..."
TRIES=0
while [ "$TRIES" -lt 24 ]; do
    sleep 5
    TRIES=$((TRIES + 1))
    if curl -sfk "https://localhost/api/health" > /dev/null 2>&1; then
        log "Backend ist bereit! (nach $((TRIES * 5)) Sekunden)"
        # nginx neu laden damit neue app.conf (mit error_page + Wartungsseite) aktiv wird
        docker exec deinezeit_nginx nginx -s reload >> "$LOG_FILE" 2>&1 || true
        log "nginx neu geladen."
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
