# Übergabe: PWA für DeineZeit

## Ziel
"DeineZeit" als PWA (Progressive Web App) ausbauen, damit man sie über
"Zum Home-Bildschirm hinzufügen" wie eine native iPhone-App installieren kann
(eigenes Icon, Vollbild ohne Browserleiste, optional offline-fähig).

## Ausgangslage
- React (Vite) Frontend in `C:\Projekte\deinezeit\frontend`
- FastAPI Backend, Docker Compose lokal
- Aktuelle Version: 1.8.5

## Geplante Schritte
1. `vite-plugin-pwa` einrichten (Manifest + Service Worker)
2. Web App Manifest: Name, Icons (verschiedene Größen), Theme-/Hintergrundfarbe,
   `display: standalone`
3. App-Icons erstellen (basierend auf bestehendem Logo/Branding)
4. Service Worker: Caching-Strategie für Offline-Nutzung (zumindest App-Shell)
5. iOS-spezifische Meta-Tags (`apple-touch-icon`, `apple-mobile-web-app-capable` etc.)
6. Test: Installation auf iPhone über Safari → "Zum Home-Bildschirm"
7. Changelog/Version aktualisieren, commit & push (per Memory-Workflow)

## Hinweise
- Kommunikation auf Deutsch
- Nach jeder Änderung: changelog.js, CHANGELOG.md, package.json Version aktualisieren
- Git: `index.lock` kann manchmal stale sein → ggf. vorher löschen
- Repo: github.com/waehnero/deinezeit
