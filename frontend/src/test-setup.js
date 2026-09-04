// Gemeinsame Vorbereitung für alle Vitest-Läufe (siehe vite.config.js).
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Nach jedem Test das gerenderte DOM abbauen — sonst sehen spätere Tests
// die Überreste der vorherigen.
afterEach(() => cleanup())
