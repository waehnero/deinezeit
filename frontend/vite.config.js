import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
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
  server: {
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
