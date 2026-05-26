#!/bin/bash
# ╔══════════════════════════════════════════════════════════════╗
# ║           DeineZeit – Automatischer Installer               ║
# ║                    Version 0.8.1                            ║
# ╚══════════════════════════════════════════════════════════════╝
#
# Verwendung (direkt von GitHub):
#   curl -fsSL https://raw.githubusercontent.com/waehnero/deinezeit/main/install.sh | sudo bash
#
# Oder lokal (wenn Skript bereits heruntergeladen):
#   sudo bash install.sh

set -euo pipefail

# ── Farben für die Ausgabe ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
print_header() {
    echo ""
    echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}${BOLD}║           DeineZeit – Automatischer Installer               ║${NC}"
    echo -e "${BLUE}${BOLD}║                    Version 0.8.1                            ║${NC}"
    echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo ""
    echo -e "${CYAN}${BOLD}▶ $1${NC}"
}

print_ok() {
    echo -e "${GREEN}  ✓ $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✗ FEHLER: $1${NC}"
    exit 1
}

ask() {
    # ask "Frage" "Standardwert" → gibt Eingabe zurück
    # Prompt auf stderr damit $() die Ausgabe nicht einfängt
    local prompt="$1"
    local default="${2:-}"
    local answer

    if [ -n "$default" ]; then
        echo -ne "${BOLD}  $prompt ${NC}[${default}]: " >&2
    else
        echo -ne "${BOLD}  $prompt: ${NC}" >&2
    fi

    read -r answer
    echo "${answer:-$default}"
}

ask_password() {
    local prompt="$1"
    local password
    local password2

    while true; do
        echo -ne "${BOLD}  $prompt: ${NC}" >&2
        read -rs password
        echo "" >&2
        echo -ne "${BOLD}  Passwort bestätigen: ${NC}" >&2
        read -rs password2
        echo "" >&2

        if [ "$password" = "$password2" ]; then
            if [ ${#password} -lt 8 ]; then
                print_warn "Passwort muss mindestens 8 Zeichen lang sein."
            else
                echo "$password"
                return
            fi
        else
            print_warn "Passwörter stimmen nicht überein. Bitte erneut versuchen."
        fi
    done
}

generate_secret() {
    # Zufälligen 64-Zeichen Schlüssel generieren
    cat /dev/urandom | tr -dc 'a-zA-Z0-9!@#$%^&*' | fold -w 64 | head -n 1
}

# ── Überprüfungen ─────────────────────────────────────────────────────────────
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Dieses Skript muss als root ausgeführt werden.\nBitte mit 'sudo bash install.sh' starten."
    fi
}

check_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        print_error "Betriebssystem konnte nicht erkannt werden. Unterstützt: Ubuntu, Debian."
    fi

    case "$OS" in
        ubuntu|debian)
            print_ok "Betriebssystem: $PRETTY_NAME"
            ;;
        *)
            print_warn "Nicht offiziell getestetes Betriebssystem: $PRETTY_NAME"
            print_warn "Fahre trotzdem fort..."
            ;;
    esac
}

# ── Eingaben vom Benutzer ─────────────────────────────────────────────────────
collect_inputs() {
    echo ""
    echo -e "${BOLD}Bitte beantworten Sie die folgenden Fragen zur Einrichtung:${NC}"
    echo -e "${YELLOW}  (Drücken Sie ENTER um den Standardwert zu übernehmen)${NC}"
    echo ""

    # Domain
    echo -e "${CYAN}── Ihre Domain ─────────────────────────────────────────────────${NC}"
    echo "   Beispiel: firma.at  oder  meinprogramm.firma.at"
    echo "   Wichtig: Die Domain muss bereits auf diesen Server zeigen!"
    echo ""
    DOMAIN=$(ask "Domain (ohne https://)")
    while [[ -z "$DOMAIN" || "$DOMAIN" == *"/"* || "$DOMAIN" == *" "* ]]; do
        print_warn "Bitte eine gültige Domain eingeben (ohne https:// und ohne Leerzeichen)"
        DOMAIN=$(ask "Domain (ohne https://)")
    done

    # E-Mail für Let's Encrypt
    echo ""
    echo -e "${CYAN}── E-Mail-Adresse ──────────────────────────────────────────────${NC}"
    echo "   Wird für das SSL-Zertifikat (Let's Encrypt) benötigt."
    echo "   Sie erhalten dort Benachrichtigungen falls das Zertifikat abläuft."
    echo ""
    ADMIN_EMAIL=$(ask "Ihre E-Mail-Adresse")
    while [[ -z "$ADMIN_EMAIL" || "$ADMIN_EMAIL" != *"@"* ]]; do
        print_warn "Bitte eine gültige E-Mail-Adresse eingeben"
        ADMIN_EMAIL=$(ask "Ihre E-Mail-Adresse")
    done

    # Admin-Benutzerdaten
    echo ""
    echo -e "${CYAN}── Administrator-Konto ─────────────────────────────────────────${NC}"
    echo "   Dies wird der erste Benutzer mit vollen Administratorrechten."
    echo ""
    ADMIN_NAME=$(ask "Vollständiger Name des Administrators" "Administrator")
    ADMIN_LOGIN_EMAIL=$(ask "E-Mail-Adresse für den Login" "$ADMIN_EMAIL")
    echo ""
    ADMIN_PASSWORD=$(ask_password "Passwort für den Administrator")

    # Installationsverzeichnis
    echo ""
    echo -e "${CYAN}── Installationsverzeichnis ────────────────────────────────────${NC}"
    INSTALL_DIR=$(ask "Installationspfad" "/opt/deinezeit")

    # Zusammenfassung
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║                 Zusammenfassung                             ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Domain:${NC}          https://$DOMAIN"
    echo -e "  ${BOLD}E-Mail:${NC}          $ADMIN_EMAIL"
    echo -e "  ${BOLD}Admin-Name:${NC}      $ADMIN_NAME"
    echo -e "  ${BOLD}Admin-Login:${NC}     $ADMIN_LOGIN_EMAIL"
    echo -e "  ${BOLD}Installiert in:${NC}  $INSTALL_DIR"
    echo ""

    echo -ne "${BOLD}  Alles korrekt? Installation starten? [J/n]: ${NC}"
    read -r CONFIRM
    CONFIRM=${CONFIRM:-J}
    if [[ ! "$CONFIRM" =~ ^[JjYy]$ ]]; then
        echo ""
        echo "Installation abgebrochen."
        exit 0
    fi
}

# ── Docker installieren ───────────────────────────────────────────────────────
install_docker() {
    print_step "Docker wird installiert..."

    if command -v docker &>/dev/null; then
        print_ok "Docker ist bereits installiert ($(docker --version | awk '{print $3}' | tr -d ','))"
        return
    fi

    apt-get update -qq
    apt-get install -y -qq \
        ca-certificates curl gnupg lsb-release apt-transport-https

    # Docker GPG-Schlüssel
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$OS/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Docker Repository hinzufügen
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/$OS \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    print_ok "Docker erfolgreich installiert"
}

# ── Hilfsprogramme installieren ───────────────────────────────────────────────
install_dependencies() {
    print_step "Hilfsprogramme werden geprüft..."
    apt-get update -qq
    apt-get install -y -qq git curl openssl ufw
    print_ok "Hilfsprogramme bereit"
}

# ── Firewall konfigurieren ────────────────────────────────────────────────────
configure_firewall() {
    print_step "Firewall wird konfiguriert..."

    if command -v ufw &>/dev/null; then
        ufw allow 22/tcp  > /dev/null 2>&1 || true   # SSH immer offen lassen!
        ufw allow 80/tcp  > /dev/null 2>&1 || true   # HTTP
        ufw allow 443/tcp > /dev/null 2>&1 || true   # HTTPS
        ufw --force enable > /dev/null 2>&1 || true
        print_ok "Firewall: Port 22 (SSH), 80 (HTTP), 443 (HTTPS) geöffnet"
    else
        print_warn "ufw nicht gefunden – Firewall wird übersprungen"
    fi
}

# ── Programm herunterladen ────────────────────────────────────────────────────
setup_application() {
    print_step "DeineZeit wird eingerichtet..."

    # Verzeichnis anlegen
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/backups"

    # Programmcode kopieren (bei lokalem Aufruf) oder herunterladen
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
        # Lokale Installation (Skript liegt im Projektordner)
        print_ok "Programmcode gefunden (lokale Installation)"
        if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
            cp -r "$SCRIPT_DIR/." "$INSTALL_DIR/"
        fi
    else
        # Download von GitHub
        GITHUB_REPO="https://github.com/waehnero/deinezeit"
        print_step "Lade DeineZeit von GitHub herunter..."
        if ! command -v git &>/dev/null; then
            apt-get install -y -qq git
        fi
        if [ -d "$INSTALL_DIR/.git" ]; then
            print_ok "Repository bereits vorhanden – aktualisiere auf neuesten Stand..."
            git -C "$INSTALL_DIR" pull origin main
        else
            git clone "$GITHUB_REPO" "$INSTALL_DIR"
            print_ok "Programmcode von GitHub geladen"
        fi
    fi

    print_ok "Programmcode bereit in $INSTALL_DIR"
}

# ── Konfiguration schreiben ───────────────────────────────────────────────────
write_config() {
    print_step "Konfiguration wird erstellt..."

    SECRET_KEY=$(generate_secret)
    DB_PASSWORD=$(generate_secret | tr -dc 'a-zA-Z0-9' | head -c 32)
    MINIO_PASSWORD=$(generate_secret | tr -dc 'a-zA-Z0-9' | head -c 32)

    cat > "$INSTALL_DIR/.env" <<EOF
# DeineZeit Konfiguration
# Erstellt am: $(date '+%Y-%m-%d %H:%M:%S')
# ACHTUNG: Diese Datei enthält sensible Daten – niemals veröffentlichen!

# Datenbank
DB_USER=deinezeit
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=deinezeit

# Backend-Sicherheit
SECRET_KEY=${SECRET_KEY}
FRONTEND_URL=https://${DOMAIN}

# WebAuthn (Face ID / Passkeys)
WEBAUTHN_RP_ID=${DOMAIN}
WEBAUTHN_RP_NAME=DeineZeit

# MinIO (Datei-Speicher)
MINIO_ROOT_USER=deinezeit
MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}

# Domain
DOMAIN=${DOMAIN}
ADMIN_EMAIL=${ADMIN_EMAIL}
EOF

    chmod 600 "$INSTALL_DIR/.env"
    print_ok "Konfiguration erstellt (.env)"

    # nginx Domain anpassen
    sed -i "s/deine-domain.at/${DOMAIN}/g" "$INSTALL_DIR/nginx/conf.d/app.conf"
    print_ok "nginx für Domain $DOMAIN konfiguriert"
}

# ── SSL-Zertifikat holen ──────────────────────────────────────────────────────
setup_ssl() {
    print_step "SSL-Zertifikat wird beantragt (Let's Encrypt)..."
    echo "   Domain: $DOMAIN"
    echo "   E-Mail: $ADMIN_EMAIL"
    echo ""
    print_warn "Bitte stellen Sie sicher, dass $DOMAIN bereits auf diesen Server zeigt!"
    echo -ne "${BOLD}  DNS bereits konfiguriert? Weiter? [J/n]: ${NC}"
    read -r DNS_READY
    DNS_READY=${DNS_READY:-J}

    if [[ ! "$DNS_READY" =~ ^[JjYy]$ ]]; then
        print_warn "SSL-Zertifikat übersprungen. Später manuell holen mit:"
        echo "    cd $INSTALL_DIR && bash scripts/renew-ssl.sh"
        SSL_SKIPPED=true
        return
    fi

    cd "$INSTALL_DIR"

    # Kurz nginx für die Challenge starten
    docker compose up -d nginx certbot 2>/dev/null || true
    sleep 3

    # Zertifikat beantragen
    if docker compose run --rm certbot certonly \
        --webroot \
        --webroot-path /var/www/certbot \
        --email "$ADMIN_EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        -d "$DOMAIN"; then
        print_ok "SSL-Zertifikat erfolgreich ausgestellt!"
        SSL_SKIPPED=false
    else
        print_warn "Zertifikat konnte nicht ausgestellt werden."
        print_warn "Mögliche Ursache: DNS zeigt noch nicht auf diesen Server."
        print_warn "SSL kann später nachgeholt werden: bash scripts/renew-ssl.sh"
        SSL_SKIPPED=true
    fi
}

# ── Anwendung starten ─────────────────────────────────────────────────────────
start_application() {
    print_step "Anwendung wird gestartet..."

    cd "$INSTALL_DIR"

    if [ "${SSL_SKIPPED:-false}" = true ]; then
        # Ohne SSL starten (HTTP only, für späteres SSL-Setup)
        print_warn "Starte vorerst ohne HTTPS..."
        # Temporäre nginx-Konfiguration ohne SSL
        create_http_only_config
    fi

    docker compose up -d
    print_ok "Docker-Container gestartet"

    # Warten bis Datenbank bereit ist
    print_step "Warte auf Datenbank..."
    local TRIES=0
    until docker compose exec -T db pg_isready -U deinezeit > /dev/null 2>&1; do
        TRIES=$((TRIES + 1))
        if [ $TRIES -gt 30 ]; then
            print_error "Datenbank startet nicht. Logs prüfen: docker compose logs db"
        fi
        sleep 2
        echo -n "."
    done
    echo ""
    print_ok "Datenbank bereit"
}

# ── Temporäre HTTP-Konfiguration (falls SSL noch fehlt) ───────────────────────
create_http_only_config() {
    cat > "$INSTALL_DIR/nginx/conf.d/app.conf" <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
    print_warn "Temporäre HTTP-Konfiguration aktiv. HTTPS später aktivieren."
}

# ── Datenbank-Migrationen ─────────────────────────────────────────────────────
run_migrations() {
    print_step "Datenbank wird eingerichtet..."

    cd "$INSTALL_DIR"
    docker compose exec -T backend alembic upgrade head
    print_ok "Datenbanktabellen angelegt"
}

# ── Ersten Admin anlegen ──────────────────────────────────────────────────────
create_admin() {
    print_step "Administrator-Konto wird angelegt..."

    cd "$INSTALL_DIR"
    docker compose exec -T backend python3 -c "
import sys
sys.path.insert(0, '/app')
from app.db.base import SessionLocal
from app.services.auth_service import auth_service
from app.models.user import UserRole

db = SessionLocal()
existing = auth_service.get_user_by_email(db, '${ADMIN_LOGIN_EMAIL}')
if existing:
    print('BEREITS_VORHANDEN')
else:
    user = auth_service.create_user(
        db,
        email='${ADMIN_LOGIN_EMAIL}',
        full_name='${ADMIN_NAME}',
        password='${ADMIN_PASSWORD}',
        role='admin',
        language='de'
    )
    print('ERSTELLT:' + str(user.id))
db.close()
"
    print_ok "Administrator-Konto bereit"
}

# ── SSL nachträglich aktivieren ───────────────────────────────────────────────
write_ssl_script() {
    cat > "$INSTALL_DIR/scripts/renew-ssl.sh" <<'EOF'
#!/bin/bash
# SSL-Zertifikat beantragen (falls bei der Installation übersprungen)
set -e
source "$(dirname "$0")/../.env"

cd "$(dirname "$0")/.."

echo "▶ Beantrage SSL-Zertifikat für $DOMAIN..."
docker compose run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$ADMIN_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    -d "$DOMAIN"

echo "▶ Vollständige nginx-Konfiguration wird aktiviert..."
# Vollständige SSL-Konfiguration wiederherstellen
docker compose restart nginx

echo "✓ HTTPS ist jetzt aktiv! Erreichbar unter: https://$DOMAIN"
EOF
    chmod +x "$INSTALL_DIR/scripts/renew-ssl.sh"
    chmod +x "$INSTALL_DIR/scripts/deploy.sh"
}

# ── Automatische Zertifikatserneuerung ────────────────────────────────────────
setup_cron() {
    print_step "Automatische Zertifikatserneuerung wird eingerichtet..."

    # Cron-Job: Jeden Montag um 3:30 Uhr Zertifikat prüfen und ggf. erneuern
    (crontab -l 2>/dev/null; echo "30 3 * * 1 cd $INSTALL_DIR && docker compose run --rm certbot renew --quiet && docker compose restart nginx") | crontab -
    print_ok "Automatische Erneuerung eingerichtet (jeden Montag, 03:30 Uhr)"
}

# ── Abschlussmeldung ──────────────────────────────────────────────────────────
print_success() {
    local PROTOCOL="https"
    [ "${SSL_SKIPPED:-false}" = true ] && PROTOCOL="http"

    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║          ✓  Installation erfolgreich abgeschlossen!          ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}🌐 Ihre App ist erreichbar unter:${NC}"
    echo -e "     ${CYAN}${BOLD}${PROTOCOL}://${DOMAIN}${NC}"
    echo ""
    echo -e "  ${BOLD}🔐 Login-Daten:${NC}"
    echo -e "     E-Mail:    ${ADMIN_LOGIN_EMAIL}"
    echo -e "     Passwort:  (das von Ihnen gewählte)"
    echo ""

    if [ "${SSL_SKIPPED:-false}" = true ]; then
        echo -e "  ${YELLOW}${BOLD}⚠  HTTPS noch nicht aktiv!${NC}"
        echo -e "  Sobald DNS konfiguriert ist:"
        echo -e "  ${CYAN}bash $INSTALL_DIR/scripts/renew-ssl.sh${NC}"
        echo ""
    fi

    echo -e "  ${BOLD}📁 Installiert in:${NC} $INSTALL_DIR"
    echo ""
    echo -e "  ${BOLD}🔧 Nützliche Befehle:${NC}"
    echo -e "     Status:    ${CYAN}cd $INSTALL_DIR && docker compose ps${NC}"
    echo -e "     Logs:      ${CYAN}cd $INSTALL_DIR && docker compose logs -f${NC}"
    echo -e "     Update:    ${CYAN}cd $INSTALL_DIR && bash scripts/deploy.sh${NC}"
    echo -e "     Stoppen:   ${CYAN}cd $INSTALL_DIR && docker compose down${NC}"
    echo ""
    echo -e "  ${BOLD}💡 Tipp:${NC} Die Konfigurationsdatei finden Sie unter:"
    echo -e "     ${CYAN}$INSTALL_DIR/.env${NC}"
    echo ""
}

# ── Hauptprogramm ─────────────────────────────────────────────────────────────
main() {
    print_header
    check_root
    check_os
    collect_inputs

    install_dependencies
    install_docker
    configure_firewall
    setup_application
    write_config
    setup_ssl
    write_ssl_script
    start_application
    run_migrations
    create_admin
    setup_cron

    print_success
}

main "$@"
