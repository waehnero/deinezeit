#!/bin/bash
# ============================================================
# DeineZeit – Update-Skript (manuell auf dem Server)
# Verwendung: sudo bash scripts/deploy.sh
#
# Dieser Script wird auch vom GitHub Actions Workflow
# automatisch aufgerufen wenn du auf main pushst.
# ============================================================

# Bewusst KEIN 'set -u': im CI-/SSH-Kontext sind manche Variablen leer, das
# soll den Deploy nicht vorzeitig (und unbemerkt) abbrechen.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

# ── CI-Modus ────────────────────────────────────────────────────────────────
# Wird der Deploy aus GitHub Actions per SSH aufgerufen (Env GIT_SHA gesetzt),
# läuft ein schlanker, robuster Pfad: kein git pull (rsync hat den Code schon
# übertragen), No-Cache-Build mit GIT_SHA-Cache-Buster, erzwungenes Recreate
# und eine Verifikation, dass die Container wirklich neu sind. Schlägt etwas
# fehl, endet das Skript mit Exit != 0 -> der GitHub-Step wird ROT.
if [ -n "${GIT_SHA:-}" ]; then
  DEPLOY_PATH="${DEPLOY_PATH:-$INSTALL_DIR}"
  cd "$DEPLOY_PATH"
  export GIT_SHA

  echo "▶ Neue Images bauen (Cache-Buster GIT_SHA=$GIT_SHA)..."
  docker compose build --no-cache --build-arg GIT_SHA="$GIT_SHA"

  echo "▶ Datenbank-Migrationen..."
  docker compose run --rm backend alembic upgrade head

  echo "▶ Dienste neu erstellen (aus neuen Images)..."
  docker compose up -d --force-recreate --remove-orphans

  echo "▶ Alte Images aufräumen..."
  docker image prune -f || true

  echo "▶ Prüfe, dass Container wirklich neu erstellt wurden..."
  for svc in frontend backend; do
    cid="$(docker compose ps -q "$svc")"
    if [ -z "$cid" ]; then
      echo "✗ $svc: kein Container gefunden - Deploy fehlgeschlagen."
      exit 1
    fi
    started="$(docker inspect -f '{{.State.StartedAt}}' "$cid")"
    started_ts="$(date -d "$started" +%s 2>/dev/null || echo 0)"
    age=$(( "$(date +%s)" - started_ts ))
    echo "   $svc: vor ${age}s gestartet"
    if [ "$age" -gt 300 ]; then
      echo "✗ $svc wurde NICHT neu erstellt (zu alt) - Deploy fehlgeschlagen."
      exit 1
    fi
  done

  echo "✓ Deployment abgeschlossen!"
  exit 0
fi
# ── Ende CI-Modus ─────────────────────────────────────────────────────────────

# Farben
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_step() { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }
print_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
print_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }

cd "$INSTALL_DIR"

print_step "DeineZeit Update wird gestartet..."

# Aktuelle Version anzeigen
VERSION=$(grep '"version"' frontend/package.json 2>/dev/null | head -1 | awk -F'"' '{print $4}' || echo "unbekannt")
echo "  Aktuelle Version: $VERSION"

# Neuesten Code von GitHub holen (falls git verfügbar)
if [ -d ".git" ] && command -v git &>/dev/null; then
    print_step "Neuesten Code von GitHub holen..."
    git pull origin main
    NEW_VERSION=$(grep '"version"' frontend/package.json 2>/dev/null | head -1 | awk -F'"' '{print $4}' || echo "unbekannt")
    print_ok "Code aktuell ($VERSION → $NEW_VERSION)"
fi

# Datenbank-Backup vor Update
print_step "Datenbank-Backup vor dem Update..."
mkdir -p backups
source .env 2>/dev/null || true
BACKUP_FILE="backups/pre-update_$(date +%Y%m%d_%H%M%S).sql"
if docker compose exec -T db pg_dump -U "${DB_USER:-deinezeit}" "${DB_NAME:-deinezeit}" > "$BACKUP_FILE" 2>/dev/null; then
    print_ok "Backup gespeichert: $BACKUP_FILE"
else
    print_warn "Backup übersprungen (Datenbank noch nicht gestartet?)"
fi

# Docker-Images neu bauen
print_step "Docker-Images werden gebaut..."
docker compose build
print_ok "Images aktuell"

# Datenbank-Migrationen
print_step "Datenbank-Migrationen werden ausgeführt..."
docker compose run --rm backend alembic upgrade head
print_ok "Datenbank aktuell"

# Container neu starten
print_step "Dienste werden neu gestartet..."
docker compose up -d --remove-orphans
print_ok "Alle Dienste laufen"

# Alte Images aufräumen
docker image prune -f > /dev/null 2>&1 || true

# Gesundheitscheck
print_step "Healthcheck..."
sleep 8
if curl -sf http://localhost/api/health > /dev/null 2>&1; then
    print_ok "Backend erreichbar – Update erfolgreich!"
elif curl -sf https://localhost/api/health --insecure > /dev/null 2>&1; then
    print_ok "Backend erreichbar (HTTPS) – Update erfolgreich!"
else
    print_warn "Backend antwortet noch nicht – bitte kurz warten und prüfen:"
    echo "    docker compose logs --tail=30 backend"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ Update abgeschlossen!${NC}"
echo ""
