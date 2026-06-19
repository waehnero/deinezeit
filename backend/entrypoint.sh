#!/bin/bash
set -e

echo "[DeineZeit] Datenbank-Migrationen werden ausgeführt..."
alembic upgrade head
echo "[DeineZeit] Migrationen abgeschlossen. Server wird gestartet..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
