import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  // Frontend-Tests (Vitest, seit 04.09.2026 — Audit TEST-003, K-22):
  //   npm test            einmal durchlaufen
  //   npm run test:watch  bei Änderungen erneut
  // Läuft in jsdom (kein Browser nötig). Testdateien liegen neben dem Code
  // als *.test.js / *.test.jsx.
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
    setupFiles: ['src/test-setup.js'],
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Service Worker bewusst deaktiviert: Der PWA-Cache hat wiederholt alten
      // JS-Code festgehalten, sodass Updates (z.B. Upload-Fix) nicht griffen.
      // selfDestroying erzeugt einen einmaligen SW, der bei jedem Nutzer alle
      // alten Service Worker + Caches entfernt und sich dann selbst abschaltet.
      // Updates greifen danach immer sofort. (Kein Offline-Modus / keine
      // Homescreen-Installation mehr – für eine interne Web-App akzeptabel.)
      selfDestroying: true,
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'DeineZeit',
        short_name: 'DeineZeit',
        description: 'DeineZeit – Zeiterfassung, Projektverwaltung und Stammdaten',
        lang: 'de',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#f97316',
        icons: [
          {
            src: '/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/maskable-icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // Alten Service Worker beim Update sofort ablösen und alte Caches löschen,
        // damit kein veralteter SW mehr API-Requests abfängt.
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        navigateFallback: '/index.html',
        // App-Shell + Assets fürs Offline-Caching, API-Aufrufe NIE cachen.
        // navigateFallbackDenylist verhindert, dass /api-Pfade die index.html bekommen.
        navigateFallbackDenylist: [/^\/api/],
        // GET-API-Aufrufe immer direkt ans Netzwerk. Nicht-GET (POST/PUT/DELETE/PATCH)
        // werden von Workbox ohnehin nicht abgefangen – Uploads laufen damit direkt durch.
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
            handler: 'NetworkOnly',
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  build: {
    // Die einzige Datei über 500 kB ist exceljs (930 kB), die nur beim
    // Excel-Import/-Export per import() nachgeladen wird. Die Warnung soll bei
    // echten Ausreißern im Hauptbundle wieder anschlagen, nicht bei dieser.
    chunkSizeWarningLimit: 1000,
    rolldownOptions: {
      output: {
        // Seiten werden per React.lazy nachgeladen (K-26b). Ohne diese Gruppen
        // legt Rolldown für jedes lucide-Icon, das mehrere Seiten teilen, eine
        // eigene 200-Byte-Datei an — über 50 Stück, jede ein eigener Request.
        // Deshalb: alle Icons in eine Datei, React-Kern in eine zweite.
        codeSplitting: {
          groups: [
            { name: 'icons', test: /node_modules[\\/]lucide-react[\\/]/ },
            { name: 'react', test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/ },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
