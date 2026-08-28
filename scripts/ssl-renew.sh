#!/bin/bash
# ============================================================================
# DeineZeit – SSL-Zertifikat erneuern (zweiter Sicherheitsgurt)
#
# Wird vom systemd-Timer `deinezeit-ssl.timer` täglich aufgerufen und kann
# jederzeit auch von Hand gestartet werden:
#
#     sudo bash /opt/deinezeit/scripts/ssl-renew.sh
#
# Warum es dieses Skript gibt, obwohl der certbot-Container schon eine eigene
# Erneuerungsschleife hat: die Schleife lebt IM Docker-Verbund. Steht Docker,
# hängt ein Container oder wurde er versehentlich gestoppt, erneuert niemand
# mehr — und das fällt erst auf, wenn das Zertifikat abgelaufen ist. Dieses
# Skript läuft ausserhalb von Docker und startet notfalls alles neu.
#
# Das Skript ist gutmütig: es erneuert nur, wenn Let's Encrypt es für nötig
# hält (ab 30 Tagen Restlaufzeit), und es bricht bei einem Fehlschlag nicht
# den Server ab — es protokolliert und versucht es am nächsten Tag erneut.
# ============================================================================
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${SSL_LOG_FILE:-/var/log/deinezeit-ssl.log}"

log() {
    local zeile="[$(date '+%d.%m.%Y %H:%M:%S')] $*"
    echo "$zeile"
    echo "$zeile" >> "$LOG_FILE" 2>/dev/null || true
}

cd "$INSTALL_DIR" || { log "✗ Verzeichnis $INSTALL_DIR nicht gefunden"; exit 1; }

log "── Zertifikatsprüfung gestartet ──────────────────────────────"

# ── 1. Läuft der Docker-Verbund überhaupt? ───────────────────────────────────
# Ohne laufenden nginx kann Let's Encrypt die Challenge-Datei nicht abholen und
# die Erneuerung scheitert garantiert. Also zuerst hochfahren.
if ! docker compose ps --status running --services 2>/dev/null | grep -qx nginx; then
    log "⚠ nginx läuft nicht — Verbund wird gestartet"
    docker compose up -d >> "$LOG_FILE" 2>&1 || log "✗ 'docker compose up -d' fehlgeschlagen"
    sleep 10
fi

# ── 2. Läuft der certbot-Container (Erneuerungsschleife)? ────────────────────
# Fehlt er, ist die erste Sicherungsebene ausgefallen. Wieder starten und
# protokollieren, damit man es in der Logdatei später sieht.
if ! docker compose ps --status running --services 2>/dev/null | grep -qx certbot; then
    log "⚠ certbot-Container läuft NICHT — wird gestartet (Erneuerungsschleife war ausgefallen)"
    docker compose up -d certbot >> "$LOG_FILE" 2>&1 || log "✗ certbot konnte nicht gestartet werden"

    # Nachfassen: Ein gestarteter Container ist noch kein laufender. Fällt er
    # sofort wieder um, ist meist der entrypoint schuld — das Image hat
    # ENTRYPOINT ["certbot"], und ohne `entrypoint: /bin/sh` in der
    # docker-compose.yml wird die Schleife an certbot durchgereicht statt
    # ausgeführt. Der Container stirbt dann mit Exit-Code 2. Ohne diese
    # Nachkontrolle meldet das Skript fälschlich Erfolg.
    sleep 5
    if ! docker compose ps --status running --services 2>/dev/null | grep -qx certbot; then
        code="$(docker inspect -f '{{.State.ExitCode}}' deinezeit_certbot 2>/dev/null || echo '?')"
        log "✗ certbot ist sofort wieder beendet worden (Exit-Code $code)."
        log "  Die Dauerschleife läuft NICHT. Prüfen mit:  docker compose ps certbot"
        log "  In der Spalte COMMAND muss '/bin/sh' stehen, nicht 'certbot /bin/sh'."
        log "  Steht dort 'certbot /bin/sh', fehlt in docker-compose.yml die Zeile"
        log "  'entrypoint: /bin/sh' beim Dienst certbot."
        log "  Die Erneuerung selbst läuft weiter über diesen täglichen Timer."
    else
        log "✓ certbot-Container läuft wieder"
    fi
fi

# ── 3. Erneuerung anstoßen ───────────────────────────────────────────────────
# `--entrypoint certbot` umgeht die Dauerschleife aus docker-compose.yml und
# führt genau einen Durchlauf aus. certbot erneuert von sich aus nur, was
# fällig ist; ist noch alles gültig, endet es mit "no renewals were attempted".
log "▶ certbot renew"
RENEW_AUSGABE="$(docker compose run --rm --entrypoint certbot certbot \
    renew --webroot --webroot-path /var/www/certbot 2>&1)"
RENEW_CODE=$?
echo "$RENEW_AUSGABE" >> "$LOG_FILE" 2>/dev/null || true

if [ $RENEW_CODE -ne 0 ]; then
    # Häufigster harmloser Fall: der Schleifen-Container erneuert gerade selbst
    # und hält die certbot-Sperre. Dann ist nichts kaputt — morgen klappt es.
    if echo "$RENEW_AUSGABE" | grep -qi "another instance"; then
        log "ℹ certbot läuft bereits (Sperre aktiv) — nächster Versuch morgen"
    else
        log "✗ Erneuerung fehlgeschlagen (Code $RENEW_CODE) — Details in $LOG_FILE"
    fi
else
    log "✓ certbot durchgelaufen"
fi

# ── 4. nginx das Zertifikat neu einlesen lassen ──────────────────────────────
# Der eigentliche Grund, warum das Zertifikat trotz Erneuerung ablaufen kann:
# nginx hält es im Speicher. `nginx -s reload` ist unterbrechungsfrei, laufende
# Anfragen werden zu Ende bedient. Klappt der Reload nicht (z.B. Container neu),
# hilft ein Neustart.
if docker compose exec -T nginx nginx -s reload >> "$LOG_FILE" 2>&1; then
    log "✓ nginx hat das Zertifikat neu eingelesen"
else
    log "⚠ Reload fehlgeschlagen — nginx wird neu gestartet"
    docker compose restart nginx >> "$LOG_FILE" 2>&1 && log "✓ nginx neu gestartet" \
        || log "✗ nginx-Neustart fehlgeschlagen"
fi

# ── 5. Restlaufzeit protokollieren ───────────────────────────────────────────
# Steht in der Logdatei und beantwortet bei Störungen sofort die erste Frage:
# "wie lange ist das Zertifikat noch gültig?"
ABLAUF="$(docker compose run --rm --entrypoint certbot certbot certificates 2>/dev/null \
          | grep -i "Expiry Date" | head -1 | sed 's/^[[:space:]]*//')"
[ -n "$ABLAUF" ] && log "ℹ $ABLAUF"

log "── Zertifikatsprüfung beendet ────────────────────────────────"
exit 0
