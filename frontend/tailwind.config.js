/** @type {import('tailwindcss').Config} */

// Design-Tokens: alle Farben kommen als RGB-Tripel aus CSS-Variablen
// (definiert in src/index.css). Dadurch sind sie zur Laufzeit themebar
// (Whitelabel / Designvorlagen) und Transparenz-Varianten wie
// bg-primary-50/40 funktionieren korrekt.
const scale = (prefix) =>
  Object.fromEntries(
    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((step) => [
      step,
      `rgb(var(--${prefix}-${step}) / <alpha-value>)`,
    ])
  )

// Eine gemeinsame Grau-Skala: "neutral" und "gray" zeigen auf dieselben
// Variablen (--n-*), da im Bestand beide Paletten gemischt verwendet wurden
// und ihre Werte identisch waren.
const grau = scale('n')

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: scale('p'),   // Markenfarbe (--p-*)
        neutral: grau,
        gray:    grau,
        // Semantische Flächen & Text (Design-Verfassung, Regel 6)
        'surface':   'rgb(var(--surface) / <alpha-value>)',
        'surface-2': 'rgb(var(--surface-2) / <alpha-value>)',
        'page':      'rgb(var(--page-bg) / <alpha-value>)',
        'on-accent': 'rgb(var(--on-accent) / <alpha-value>)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
      },
      // Radien über Tokens: Designvorlagen können die Formsprache
      // (eckig ↔ rund) global umstellen, ohne Klassen zu ändern.
      borderRadius: {
        lg:    'var(--radius-s)',
        xl:    'var(--radius)',
        '2xl': 'var(--radius-l)',
      },
      boxShadow: {
        'card':       'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
      },
    },
  },
  plugins: [],
}
