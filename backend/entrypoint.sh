#!/bin/bash
set -e

echo "[DeineZeit] Datenbank-Migrationen werden ausgeführt..."
alembic upgrade head
echo "[DeineZeit] Migrationen abgeschlossen. Server wird gestartet..."

# ── Startmodus ────────────────────────────────────────────────────────────────
#
# `--reload` ist der ENTWICKLUNGSMODUS: uvicorn startet zusätzlich einen
# Datei-Watcher und lädt bei jeder Änderung neu. In Produktion kostet das
# Arbeitsspeicher und Zeit, ohne irgendeinen Nutzen — bis 20.08.2026 lief der
# Server so, weil der Schalter fest in der Startzeile stand.
#
# UVICORN_WORKERS steht bewusst auf 1.
# ---------------------------------------------------------------------
# Mehr Arbeitsprozesse würden mehrere Kerne nutzen, ABER: Zwei Dinge liegen
# derzeit im Arbeitsspeicher EINES Prozesses (app/api/system.py):
#
#   * `_update_state` — der laufende Update-Vorgang samt Countdown. Bei
#     mehreren Prozessen fragt der Browser mal den einen, mal den anderen;
#     die Update-Meldung erschiene und verschwände scheinbar zufällig.
#   * `_active_sessions` — die Zählung „aktive Benutzer".
#
# Beides gehört in die Datenbank, bevor der Wert erhöht wird. Bis dahin ist
# 1 der einzig richtige Wert — ein höherer sähe schneller aus und würde das
# Update-Fenster kaputtmachen.
WORKERS="${UVICORN_WORKERS:-1}"

if [ "${APP_ENV:-production}" = "development" ]; then
    echo "[DeineZeit] Entwicklungsmodus: Neuladen bei Dateiänderungen aktiv."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "[DeineZeit] Produktionsmodus: ${WORKERS} Arbeitsprozess(e)."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
fi
