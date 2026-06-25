#!/usr/bin/env bash
# Baut das Frontend lokal komplett neu (ohne Cache) und startet es.
# Nötig, wenn Service-Worker-/Cache-Änderungen greifen sollen.
set -e
cd "$(dirname "$0")"

echo "==> Frontend wird ohne Cache neu gebaut (dauert 1-2 Minuten) ..."
docker compose -f docker-compose.local.yml build --no-cache frontend

echo "==> Frontend-Container wird neu gestartet ..."
docker compose -f docker-compose.local.yml up -d frontend

echo "==> nginx neu starten (frische Container-IP) ..."
docker compose -f docker-compose.local.yml restart nginx

echo ""
echo "==> Pruefung: Liegt der neue Service Worker im Container?"
docker compose -f docker-compose.local.yml exec -T frontend sh -c \
  'echo "  sw.js Datum:"; ls -la /usr/share/nginx/html/sw.js | awk "{print \$6, \$7, \$8}"; \
   echo -n "  skipWaiting im SW: "; grep -c "skipWaiting\|clientsClaim" /usr/share/nginx/html/sw.js || echo 0'

echo ""
echo "FERTIG. Jetzt im Browser den alten Service Worker entfernen:"
echo "  -> http://localhost/sw-reset.html  aufrufen (loescht SW + Cache automatisch)"
