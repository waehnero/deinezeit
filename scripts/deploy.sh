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
# übertragen), Build mit GIT_SHA-Cache-Buster, erzwungenes Recreate und eine
# Verifikation, dass die Container wirklich neu sind. Schlägt etwas fehl, endet
# das Skript mit Exit != 0 -> der GitHub-Step wird ROT.
if [ -n "${GIT_SHA:-}" ]; then
  DEPLOY_PATH="${DEPLOY_PATH:-$INSTALL_DIR}"
  cd "$DEPLOY_PATH"
  export GIT_SHA

  # ── Zeitmessung je Schritt ──────────────────────────────────────────────────
  # Ohne Zahlen ist jede Optimierung geraten. Am Ende des Laufs steht in der
  # GitHub-Action, welcher Schritt wie lange gedauert hat — dort sieht man
  # sofort, wo sich ein Eingriff überhaupt lohnt.
  _T_START=$(date +%s); _T_LETZTER=$_T_START; _SCHRITT=""
  _zeiten=""
  # Zeilenumbruch als Variable: eine Kommando-Ersetzung $( ) verschluckt
  # abschließende Zeilenumbrüche, sonst landet die ganze Tabelle in einer Zeile.
  _NL=$'\n'
  schritt() {
    local jetzt; jetzt=$(date +%s)
    if [ -n "$_SCHRITT" ]; then
      local dauer=$(( jetzt - _T_LETZTER ))
      _zeiten="${_zeiten}$(printf '%6ss  %s' "$dauer" "$_SCHRITT")${_NL}"
    fi
    _SCHRITT="$1"; _T_LETZTER=$jetzt
    echo "▶ $1"
  }
  zeiten_ausgeben() {
    local jetzt; jetzt=$(date +%s)
    if [ -n "$_SCHRITT" ]; then
      _zeiten="${_zeiten}$(printf '%6ss  %s' "$(( jetzt - _T_LETZTER ))" "$_SCHRITT")${_NL}"
    fi
    echo ""
    echo "── Zeitaufwand ────────────────────────────────────"
    printf '%s' "$_zeiten"
    printf '%6ss  GESAMT\n' "$(( jetzt - _T_START ))"
    echo "───────────────────────────────────────────────────"
  }
  trap zeiten_ausgeben EXIT
  schritt "Vorbereitung"

  # ── nginx-Domain in die Config einsetzen ────────────────────────────────────
  # Der rsync überschreibt nginx/conf.d/app.conf bei JEDEM Deploy mit der
  # Repo-Version, in der die Domain nur ein Platzhalter (deine-domain.at) ist.
  # Ohne die echte Domain findet nginx sein SSL-Zertifikat nicht und crasht
  # (genau das hat die Seite schon einmal lahmgelegt). Quelle der echten Domain:
  # bevorzugt die GitHub-Variable DOMAIN, sonst aus dem vorhandenen Let's-Encrypt-
  # Zertifikat abgeleitet (Ordnername unter live/ = Domain) -> auch ohne Variable
  # robust.
  if [ -z "${DOMAIN:-}" ] || [ "${DOMAIN:-}" = "deine-domain.at" ]; then
    DOMAIN="$(docker compose run --rm --entrypoint sh certbot -c \
      'ls /etc/letsencrypt/live 2>/dev/null | grep -v README | head -1' \
      2>/dev/null | tr -d '[:space:]')"
  fi
  if [ -n "$DOMAIN" ]; then
    echo "▶ nginx-Domain setzen: $DOMAIN"
    sed -i "s/deine-domain\.at/$DOMAIN/g" nginx/conf.d/app.conf
  fi
  if grep -q 'deine-domain\.at' nginx/conf.d/app.conf; then
    echo "✗ nginx-Config enthält noch den Platzhalter 'deine-domain.at'."
    echo "  DOMAIN-Variable setzen oder gültiges Zertifikat prüfen. Deploy abgebrochen"
    echo "  (der laufende nginx bleibt unangetastet, die Seite bleibt online)."
    exit 1
  fi

  # ── Images bauen ────────────────────────────────────────────────────────────
  # BEWUSST OHNE --no-cache. Der Cache-Buster GIT_SHA erledigt dasselbe, aber
  # gezielt: Im Frontend-Dockerfile steht `ARG GIT_SHA` vor `COPY . .`, dadurch
  # wird ab dort alles neu gebaut, sobald sich der Commit ändert. Im Backend
  # übernimmt das `COPY . .` von selbst, weil Docker den Dateiinhalt vergleicht.
  #
  # `--no-cache` warf zusätzlich die teuren Schichten weg, die sich fast nie
  # ändern: apt-get (build-essential, ffmpeg, docker-ce-cli, die WeasyPrint-
  # Bibliotheken), `pip install` und `npm install`. Die wurden bei JEDEM Deploy
  # neu gebaut — das war der Löwenanteil der Wartezeit, ohne jeden Gewinn.
  #
  # Ändern sich requirements.txt oder package.json, greift der Cache dort
  # ohnehin nicht mehr und die Pakete werden neu geholt. Genau so soll es sein.
  schritt "Neue Images bauen (Cache-Buster GIT_SHA=$GIT_SHA)"
  docker compose build --build-arg GIT_SHA="$GIT_SHA"

  # nginx-Config VOR dem Neustart validieren. Schlägt der Test fehl (z.B. Domain/
  # Zertifikat passen nicht), bricht der Deploy hier ab - der laufende nginx wird
  # NICHT ersetzt und die Seite bleibt online.
  schritt "nginx-Konfiguration testen (nginx -t)"
  docker compose run --rm --entrypoint nginx nginx -t

  # Läuft bewusst VOR dem Umschalten, obwohl entrypoint.sh die Migrationen beim
  # Start ohnehin ausführt: Schlägt eine Migration fehl, bricht der Deploy hier
  # ab und die laufende Version bleibt unangetastet online. Diese Doppelung
  # kostet ein paar Sekunden und ist es wert.
  schritt "Datenbank-Migrationen"
  docker compose run --rm backend alembic upgrade head

  schritt "Dienste neu erstellen (aus neuen Images)"
  docker compose up -d --force-recreate --remove-orphans

  schritt "Alte Images aufräumen"
  docker image prune -f || true

  schritt "Prüfe, dass Container wirklich neu erstellt wurden"
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

  # nginx muss nach dem Recreate wirklich laufen (nicht crash-loopen).
  schritt "Prüfe nginx-Status"
  sleep 3
  nginx_state="$(docker inspect -f '{{.State.Status}}' "$(docker compose ps -q nginx)" 2>/dev/null || echo unknown)"
  echo "   nginx: $nginx_state"
  if [ "$nginx_state" != "running" ]; then
    echo "✗ nginx läuft nicht (Status: $nginx_state) - Deploy fehlgeschlagen."
    docker compose logs --tail=20 nginx || true
    exit 1
  fi

  # ── Zertifikats-Automatik prüfen ────────────────────────────────────────────
  # Reine Kontrolle, die den Deploy niemals scheitern lässt. Sie beantwortet
  # bei jedem Deploy die Frage "erneuert sich das Zertifikat noch von selbst?".
  # Genau hier hatte es geklemmt: der certbot-Container lief nach einem
  # Server-Neustart nicht mehr, und es fiel monatelang niemandem auf.
  schritt "Prüfe die automatische Zertifikatserneuerung"
  if docker compose ps --status running --services 2>/dev/null | grep -qx certbot; then
    echo "   certbot-Container: läuft"
  else
    echo "   ⚠ certbot-Container läuft NICHT — wird gestartet."
    docker compose up -d certbot || true
  fi
  if systemctl is-enabled deinezeit-ssl.timer >/dev/null 2>&1; then
    echo "   systemd-Timer: aktiv"
  else
    echo "   ⚠ systemd-Timer fehlt. Einmalig einrichten mit:"
    echo "     sudo bash $DEPLOY_PATH/scripts/install-ssl-timer.sh"
  fi

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
#
# Ablage standardmäßig in $INSTALL_DIR/backups. Dieser Ordner ist im
# CI-Deploy (deploy.yml) vom rsync ausgenommen — bis 02.09.2026 war er das
# nicht, und jeder Merge auf main hat die Sicherungen gelöscht (Audit
# DATA-001). Über BACKUP_DIR lässt sich ein Ort außerhalb des Deploy-Pfads
# wählen, z. B. BACKUP_DIR=/var/backups/deinezeit.
print_step "Datenbank-Backup vor dem Update..."
BACKUP_DIR="${BACKUP_DIR:-$INSTALL_DIR/backups}"
mkdir -p "$BACKUP_DIR"
source .env 2>/dev/null || true
BACKUP_FILE="$BACKUP_DIR/pre-update_$(date +%Y%m%d_%H%M%S).sql"
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
