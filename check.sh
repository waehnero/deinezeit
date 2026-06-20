#!/usr/bin/env bash
#
# check.sh – "Bin ich richtig?"-Kontrolle für DeineZeit
#
# Startet eine reine LESE-Prüfung (ändert nichts!) und zeigt auf einen Blick:
#   - richtiger Ordner / Branch
#   - uncommittete Änderungen?
#   - synchron mit GitHub (Server-Quelle)?
#   - Versionsnummern konsistent?
#
# Nutzung (im Terminal):   ./check.sh
# (einmalig ausführbar machen:  chmod +x check.sh)

set -u
cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "  ${GREEN}✔${NC} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${NC} %s\n" "$1"; }
err()  { printf "  ${RED}x${NC} %s\n" "$1"; }
head() { printf "\n${BLUE}== %s ==${NC}\n" "$1"; }

printf "\n${BLUE}DeineZeit – Statuscheck${NC}\n"

# ── 1. Richtiger Ordner? ──────────────────────────────────────────────────────
head "Projektordner"
if [ -f "docker-compose.local.yml" ] && [ -d ".git" ]; then
  ok "Du bist im richtigen Projektordner ($(pwd))"
else
  err "Das sieht NICHT nach dem Projektordner aus. Bitte ins DeineZeit-Verzeichnis wechseln."
  exit 1
fi

# ── 2. Branch ─────────────────────────────────────────────────────────────────
head "Branch"
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ "$BRANCH" = "main" ]; then
  ok "Auf Branch 'main'"
else
  warn "Du bist auf Branch '$BRANCH' (normal wäre 'main')"
fi

# ── 3. Lokale Änderungen? ─────────────────────────────────────────────────────
head "Lokale Änderungen"
CHANGES=$(git status --porcelain 2>/dev/null)
if [ -z "$CHANGES" ]; then
  ok "Keine uncommitteten Änderungen – Arbeitsverzeichnis sauber"
else
  warn "Es gibt uncommittete Änderungen:"
  echo "$CHANGES" | sed 's/^/      /'
  printf "    ${YELLOW}→ Erst testen, dann (nach Freigabe) committen & pushen.${NC}\n"
fi

# ── 4. Sync mit GitHub (Server-Quelle) ────────────────────────────────────────
head "Abgleich mit GitHub"
SYNC="unknown"   # gleichauf | hinten | vorne | divergiert | offline
if git fetch origin --quiet 2>/dev/null; then
  LOCAL=$(git rev-parse HEAD 2>/dev/null)
  REMOTE=$(git rev-parse origin/main 2>/dev/null)
  BASE=$(git merge-base HEAD origin/main 2>/dev/null)
  if [ "$LOCAL" = "$REMOTE" ]; then
    ok "Lokal und GitHub sind auf demselben Stand"; SYNC="gleichauf"
  elif [ "$LOCAL" = "$BASE" ]; then
    warn "GitHub ist VORAUS – du hinkst hinterher."; SYNC="hinten"
    printf "    ${YELLOW}→ Hole den neuen Stand:  git pull origin main${NC}\n"
  elif [ "$REMOTE" = "$BASE" ]; then
    warn "Du bist VORAUS – es gibt ungepushte Commits."; SYNC="vorne"
    printf "    ${YELLOW}→ Nach Freigabe pushen:  git push origin main${NC}\n"
  else
    err "Lokal und GitHub sind AUSEINANDERGELAUFEN (beide haben eigene Commits)."; SYNC="divergiert"
    printf "    ${RED}→ Bitte melden, dann zusammen lösen (git pull --rebase o.ä.).${NC}\n"
  fi
else
  warn "Konnte GitHub nicht erreichen (offline?) – Abgleich übersprungen"; SYNC="offline"
fi

# ── 5. Versionskonsistenz ─────────────────────────────────────────────────────
head "Versionsnummern"
V_PKG=$(grep -m1 '"version"' frontend/package.json | sed -E 's/.*"version": *"([^"]+)".*/\1/')
V_CFG=$(grep -m1 'APP_VERSION: str' backend/app/core/config.py | sed -E 's/.*"([^"]+)".*/\1/')
V_CL=$(grep -m1 'APP_VERSION:-' docker-compose.local.yml | sed -E 's/.*:-([0-9.]+).*/\1/')
printf "  package.json:        %s\n" "${V_PKG:-?}"
printf "  config.py:           %s\n" "${V_CFG:-?}"
printf "  docker-compose.local:%s\n" "${V_CL:-?}"
if [ -n "$V_PKG" ] && [ "$V_PKG" = "$V_CFG" ] && [ "$V_PKG" = "$V_CL" ]; then
  ok "Alle Versionsnummern stimmen überein ($V_PKG)"
else
  warn "Versionsnummern weichen ab – vor einem Release angleichen"
fi

# ── 6. Optional: uncommittete Änderungen committen & pushen ───────────────────
if [ -n "$CHANGES" ]; then
  head "Änderungen übergeben?"

  # Sicherheits-Stopp: bei divergiertem Stand NICHT pushen
  if [ "$SYNC" = "divergiert" ]; then
    err "Lokal und GitHub sind auseinandergelaufen – jetzt NICHT pushen."
    printf "    ${RED}→ Erst gemeinsam zusammenführen, dann erneut versuchen.${NC}\n\n"
    printf "${BLUE}Fertig.${NC}\n\n"
    exit 0
  fi
  if [ "$SYNC" = "hinten" ]; then
    warn "GitHub ist voraus. Bitte zuerst 'git pull origin main', dann committen."
    printf "\n${BLUE}Fertig.${NC}\n\n"
    exit 0
  fi

  printf "Möchtest du diese Änderungen jetzt committen und nach GitHub pushen?\n"
  printf "(Danach kann der Server das Update ziehen.)\n"
  printf "  [j] Ja, committen & pushen\n"
  printf "  [n] Nein, nichts tun (Standard)\n"
  printf "Auswahl [j/N]: "
  read -r ANSWORT
  case "$ANSWORT" in
    j|J|y|Y)
      printf "\nKurze Beschreibung der Änderung (Commit-Nachricht):\n> "
      read -r MSG
      if [ -z "$MSG" ]; then
        MSG="update $(date '+%Y-%m-%d %H:%M')"
        printf "${YELLOW}Keine Nachricht eingegeben – verwende: \"$MSG\"${NC}\n"
      fi
      printf "\n"
      git add -A && git commit -m "$MSG" && git push origin main
      if [ $? -eq 0 ]; then
        printf "\n${GREEN}✔ Erledigt.${NC} Änderungen sind auf GitHub. Der Server kann jetzt updaten.\n\n"
      else
        printf "\n${RED}Es gab ein Problem beim Commit/Push.${NC} Bitte Ausgabe oben prüfen/melden.\n\n"
      fi
      ;;
    *)
      printf "\n${BLUE}Okay, nichts geändert.${NC} Die Änderungen bleiben lokal liegen.\n\n"
      ;;
  esac
else
  printf "\n${BLUE}Fertig.${NC} Alles sauber – nichts zu übergeben.\n\n"
fi
