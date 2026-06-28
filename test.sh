#!/usr/bin/env bash
#
# test.sh – Automatisierte Backend-Tests lokal ausführen (Mac/Docker).
#
# Führt die pytest-Tests im laufenden backend-Container gegen eine separate
# Wegwerf-Test-Datenbank aus. Die normale Entwicklungs-DB wird NICHT angefasst.
#
# Voraussetzung: lokale Umgebung läuft
#   docker compose -f docker-compose.local.yml up -d --build
#
# Nutzung:   ./test.sh            # alle Tests
#            ./test.sh tests/test_auth.py   # gezielt eine Datei/ein Test
#
set -u
cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
COMPOSE="docker compose -f docker-compose.local.yml"

printf "\n${BLUE}DeineZeit – Tests${NC}\n\n"

# ── DB-Zugangsdaten aus .env lesen ────────────────────────────────────────────
if [ ! -f ".env" ]; then
  printf "${RED}Fehler:${NC} keine .env gefunden.\n"; exit 1
fi
DB_USER=$(grep -E "^DB_USER=" .env | cut -d= -f2-)
DB_NAME=$(grep -E "^DB_NAME=" .env | cut -d= -f2-)
TEST_DB="${DB_NAME}_test"

# ── Läuft die lokale Umgebung? ────────────────────────────────────────────────
if ! $COMPOSE ps --status running 2>/dev/null | grep -q deinezeit_backend; then
  printf "${YELLOW}Die lokale Umgebung läuft nicht.${NC} Bitte zuerst starten:\n"
  printf "  docker compose -f docker-compose.local.yml up -d --build\n\n"
  exit 1
fi

# ── Test-Datenbank frisch anlegen ─────────────────────────────────────────────
printf "Test-Datenbank '%s' wird (neu) angelegt …\n" "$TEST_DB"
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${TEST_DB};" \
  -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1 || {
    printf "${RED}Konnte Test-DB nicht anlegen.${NC}\n"; exit 1; }

# ── Test-Abhängigkeiten sicherstellen (pytest) ────────────────────────────────
$COMPOSE exec -T backend sh -c \
  "python -c 'import pytest' 2>/dev/null || pip install -q -r requirements-dev.txt" \
  || { printf "${RED}Konnte pytest nicht installieren.${NC}\n"; exit 1; }

# ── pytest ausführen ──────────────────────────────────────────────────────────
# Die echte DATABASE_URL (inkl. Passwort) steckt bereits als Env im Container.
# Wir leiten daraus TEST_DATABASE_URL ab, indem wir nur den DB-Namen am Ende
# durch die Test-DB ersetzen – das Passwort bleibt unangetastet.
printf "\n${BLUE}== pytest ==${NC}\n"
$COMPOSE exec -T \
  -e PYTHONPATH=/app \
  backend sh -c '
    TEST_DATABASE_URL="$(echo "$DATABASE_URL" | sed -E "s#/[^/]+\$#/'"$TEST_DB"'#")" \
    python -m pytest '"${*:-}"'
  '
RC=$?

# ── Aufräumen ─────────────────────────────────────────────────────────────────
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1

echo ""
if [ $RC -eq 0 ]; then
  printf "${GREEN}✔ Alle Tests grün.${NC}\n\n"
else
  printf "${RED}✗ Tests fehlgeschlagen (Exit %s).${NC}\n\n" "$RC"
fi
exit $RC
