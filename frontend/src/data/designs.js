// Designvorlagen (Layout-Redesign Etappe 2)
// Die eigentlichen Token-Presets liegen in src/index.css ([data-design="…"]).
// Hier stehen nur Metadaten + Vorschaufarben für die Galerie in den
// Einstellungen. IDs müssen mit den CSS-Presets und dem Backend
// (design_template) übereinstimmen.

export const DESIGN_TEMPLATES = [
  {
    id: 'standard',
    label: 'Standard',
    stil: 'Bewährt',
    desc: 'Das bisherige DeineZeit-Design — neutral und vertraut.',
    preview: { page: '#f9fafb', surface: '#ffffff', sidebar: '#ffffff', text: '#111827', border: '#e5e7eb', radius: 6 },
  },
  {
    id: 'aurora',
    label: 'Aurora Glas',
    stil: 'Modern',
    desc: 'Transluzente Flächen mit sanften Farbverläufen — leicht und hochwertig.',
    preview: { page: 'linear-gradient(135deg,#e0e7ff 0%,#f8fafc 55%,#fce7f3 100%)', surface: 'rgba(255,255,255,0.72)', sidebar: 'rgba(255,255,255,0.6)', text: '#111827', border: 'rgba(255,255,255,0.8)', radius: 10 },
  },
  {
    id: 'bento',
    label: 'Bento Studio',
    stil: 'Modern',
    desc: 'Große Radien und weiche Kachel-Schatten im Stil aktueller SaaS-Apps.',
    preview: { page: '#f6f7fb', surface: '#ffffff', sidebar: '#ffffff', text: '#111827', border: '#eceef4', radius: 12 },
  },
  {
    id: 'business',
    label: 'Business Line',
    stil: 'Klassisch',
    desc: 'Dichtes ERP-Design mit dunkler Marine-Sidebar — maximale Übersicht.',
    preview: { page: '#eef1f5', surface: '#ffffff', sidebar: '#0f2b46', text: '#111827', border: '#dde3ea', radius: 4 },
  },
  {
    id: 'kontor',
    label: 'Kontor',
    stil: 'Klassisch',
    desc: 'Warme Papiertöne mit Serifen-Überschriften — Kanzlei-Charakter.',
    preview: { page: '#f7f4ee', surface: '#fffdf9', sidebar: '#2e2924', text: '#292521', border: '#e7e0d2', radius: 6 },
  },
  {
    id: 'nordic',
    label: 'Nordic Ruhe',
    stil: 'Zeitlos',
    desc: 'Skandinavisch ruhig: feine Linien, kein Schatten, viel Weißraum.',
    preview: { page: '#fbfbfa', surface: '#ffffff', sidebar: '#f4f4f2', text: '#2b2f33', border: '#ececea', radius: 7 },
  },
  {
    id: 'midnight',
    label: 'Midnight Pro',
    stil: 'Dark Mode',
    desc: 'Dunkles Design — augenschonend bei langen Sitzungen.',
    preview: { page: '#0b1220', surface: '#121b2e', sidebar: '#0e1626', text: '#e2e8f0', border: '#334155', radius: 8 },
  },
  {
    id: 'kontrast',
    label: 'Kontrast Plus',
    stil: 'Barrierefrei',
    desc: 'WCAG 2.2: maximaler Kontrast, große Schrift, deutliche Fokus-Ringe.',
    preview: { page: '#ffffff', surface: '#ffffff', sidebar: '#ffffff', text: '#000000', border: '#000000', radius: 3 },
  },
]
