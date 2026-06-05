#!/bin/bash
# ============================================================
# DeineZeit – Update-Skript (manuell auf dem Server)
# Verwendung: sudo bash scripts/deploy.sh
#
# Dieser Script wird auch vom GitHub Actions Workflow
# automatisch aufgerufen wenn du auf main pushst.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

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
