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
# UVICORN_WORKERS darf seit 04.09.2026 größer als 1 sein.
# ---------------------------------------------------------------------
# Was früher EINEN Prozess verlangte, ist erledigt: Update-Zustand und Zählung
# „aktive Benutzer" liegen in der Datenbank (OPS-003), und die Hintergrund-
# Worker (Mail-Scan, wiederkehrende Rechnungen, Fälligkeit, Postecke, Backup,
# SSL) startet nur noch der Prozess, der den Riegel in der Datenbank hält
# (app/core/worker_sperre.py, K-21). Vorgabe bleibt 1 — auf einem kleinen
# Server reicht das; 2 lohnt sich erst, wenn PDF-Erzeugung und Berichte
# spürbar aufeinander warten. Richtwert: höchstens Anzahl CPU-Kerne.
WORKERS="${UVICORN_WORKERS:-1}"

if [ "${APP_ENV:-production}" = "development" ]; then
    echo "[DeineZeit] Entwicklungsmodus: Neuladen bei Dateiänderungen aktiv."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "[DeineZeit] Produktionsmodus: ${WORKERS} Arbeitsprozess(e)."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WORKERS}"
fi
