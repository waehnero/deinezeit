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
# Der Update-Zustand und die Zählung „aktive Benutzer" liegen seit dem Audit
# (02.09.2026, OPS-003) in der Datenbank — die waren der ursprüngliche Grund.
# Was noch EINEN Prozess verlangt: die Hintergrund-Worker (Mail-Scan,
# wiederkehrende Rechnungen, Fälligkeit, Postecke, Backup, SSL) laufen als
# Threads im App-Prozess. Mit zwei Prozessen liefen sie doppelt — doppelte
# Rechnungsentwürfe, doppelte Backups, doppelte E-Mails. Erst wenn die Worker
# einen Prozess-übergreifenden Riegel haben (oder in einen eigenen Container
# wandern), darf der Wert steigen.
WORKERS="${UVICORN_WORKERS:-1}"

if [ "${APP_ENV:-production}" = "development" ]; then
    echo "[DeineZeit] Entwicklungsmodus: Neuladen bei Dateiänderungen aktiv."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "[DeineZeit] Produktionsmodus: ${WORKERS} Arbeitsprozess(e)."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
fi
