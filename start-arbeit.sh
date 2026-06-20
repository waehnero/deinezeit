#!/usr/bin/env bash
#
# start-arbeit.sh – Vor jeder neuen Aufgabe ausführen.
#
# Holt sicher den neuesten Stand vom Server (GitHub), ABER nur wenn keine
# uncommitteten Änderungen rumliegen. So starten wir nie auf einem veralteten
# oder vermischten Stand.
#
# Nutzung (im Terminal):   ./start-arbeit.sh

set -u
cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

printf "\n${BLUE}DeineZeit – Arbeit starten${NC}\n\n"

# Richtiger Ordner?
if [ ! -f "docker-compose.local.yml" ] || [ ! -d ".git" ]; then
  printf "${RED}Fehler:${NC} Das ist nicht der Projektordner. Bitte ins DeineZeit-Verzeichnis wechseln.\n\n"
  exit 1
fi

# Uncommittete Änderungen? -> nicht ziehen, warnen.
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  printf "${YELLOW}Achtung:${NC} Es gibt noch uncommittete Änderungen:\n\n"
  git status --short | sed 's/^/    /'
  printf "\nIch ziehe NICHTS, um deine Arbeit nicht zu gefährden.\n"
  printf "Bitte zuerst testen und (nach Freigabe) committen/pushen –\n"
  printf "oder die Änderungen verwerfen, falls sie nicht gebraucht werden.\n\n"
  exit 0
fi

# Sauber -> neuesten Stand holen
printf "Hole den neuesten Stand vom Server …\n"
if git pull origin main; then
  printf "\n${GREEN}✔ Aktuell.${NC} Du arbeitest jetzt auf dem neuesten Stand.\n\n"
  printf "Nächster Schritt: lokal entwickeln & testen mit\n"
  printf "  docker compose -f docker-compose.local.yml up -d --build\n\n"
else
  printf "\n${RED}Der Abgleich ist nicht glatt durchgelaufen.${NC}\n"
  printf "Bitte die Ausgabe oben kopieren und melden – dann lösen wir es gemeinsam.\n\n"
  exit 1
fi
