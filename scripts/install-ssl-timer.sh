#!/bin/bash
# ============================================================================
# DeineZeit – Automatische Zertifikatserneuerung am Server einrichten
#
#     sudo bash /opt/deinezeit/scripts/install-ssl-timer.sh
#
# Richtet einen systemd-Timer ein, der `scripts/ssl-renew.sh` täglich ausführt.
# Das Skript ist wiederholbar: mehrfaches Ausführen ändert nichts kaputt.
#
# Warum systemd-Timer statt Cron?
#   • Persistent=true holt einen verpassten Lauf nach, wenn der Server zum
#     geplanten Zeitpunkt aus war. Cron lässt den Termin ersatzlos ausfallen —
#     bei einem wöchentlichen Cron kann so schnell ein Monat verstreichen.
#   • `systemctl status deinezeit-ssl.timer` zeigt jederzeit, wann zuletzt und
#     wann das nächste Mal geprüft wird. Bei Cron sieht man das nirgends.
#   • Die Ausgabe landet im Journal (`journalctl -u deinezeit-ssl`) statt in
#     einer Mail an root, die niemand liest.
# ============================================================================
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"

GRUEN='\033[0;32m'; GELB='\033[1;33m'; ROT='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GRUEN}✓${NC} $*"; }
warn() { echo -e "${GELB}⚠${NC} $*"; }
fehler(){ echo -e "${ROT}✗${NC} $*"; }

if [ "$(id -u)" -ne 0 ]; then
    fehler "Bitte mit sudo ausführen: sudo bash $0"
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemd nicht verfügbar — es wird stattdessen ein täglicher Cron-Job angelegt."
    crontab -l 2>/dev/null | grep -v 'deinezeit.*ssl-renew\|certbot renew' > /tmp/dz-cron || true
    echo "17 3 * * * bash $INSTALL_DIR/scripts/ssl-renew.sh" >> /tmp/dz-cron
    crontab /tmp/dz-cron && rm -f /tmp/dz-cron
    ok "Cron-Job eingerichtet (täglich 03:17 Uhr)"
    exit 0
fi

chmod +x "$INSTALL_DIR/scripts/ssl-renew.sh"

# ── Dienst-Einheit ───────────────────────────────────────────────────────────
cat > /etc/systemd/system/deinezeit-ssl.service <<EOF
[Unit]
Description=DeineZeit – SSL-Zertifikat prüfen und erneuern
Documentation=file://$INSTALL_DIR/scripts/ssl-renew.sh
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=/bin/bash $INSTALL_DIR/scripts/ssl-renew.sh
# Der Lauf darf niemals hängen bleiben und den Timer blockieren.
TimeoutStartSec=900
EOF

# ── Zeitplan ─────────────────────────────────────────────────────────────────
# Täglich um 03:17 Uhr, mit bis zu 45 Minuten Zufallsverzögerung (Let's Encrypt
# bittet ausdrücklich darum, damit nicht alle Server der Welt zur vollen Stunde
# gleichzeitig anfragen). Persistent=true holt einen verpassten Lauf nach.
cat > /etc/systemd/system/deinezeit-ssl.timer <<'EOF'
[Unit]
Description=DeineZeit – tägliche SSL-Zertifikatsprüfung

[Timer]
OnCalendar=*-*-* 03:17:00
RandomizedDelaySec=45min
Persistent=true
Unit=deinezeit-ssl.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now deinezeit-ssl.timer >/dev/null 2>&1
ok "Timer eingerichtet und aktiviert (täglich ca. 03:17 Uhr)"

# ── Alten Cron-Job entfernen ─────────────────────────────────────────────────
# Frühere Installationen legten einen wöchentlichen Cron-Eintrag an. Der darf
# jetzt weg, sonst laufen zwei Mechanismen gegeneinander und behindern sich
# über die certbot-Sperre.
if crontab -l 2>/dev/null | grep -q 'certbot renew'; then
    crontab -l 2>/dev/null | grep -v 'certbot renew' | crontab -
    ok "Alter wöchentlicher Cron-Job entfernt (wird vom Timer ersetzt)"
fi

# ── Logrotation, damit die Logdatei nicht endlos wächst ──────────────────────
cat > /etc/logrotate.d/deinezeit-ssl <<'EOF'
/var/log/deinezeit-ssl.log {
    monthly
    rotate 12
    compress
    missingok
    notifempty
    copytruncate
}
EOF

echo ""
echo "Nächster geplanter Lauf:"
systemctl list-timers deinezeit-ssl.timer --no-pager 2>/dev/null | head -3
echo ""
echo "Sofort einmal testen:   sudo systemctl start deinezeit-ssl.service"
echo "Ergebnis ansehen:       sudo journalctl -u deinezeit-ssl -n 50 --no-pager"
echo "                        sudo tail -n 50 /var/log/deinezeit-ssl.log"
