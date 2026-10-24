import { describe, it, expect, vi, afterEach } from 'vitest'
import { vorschauSeite, oeffneHtmlVorschau } from './htmlVorschau'

// Harmlose Marker statt echter Angriffe: geprüft wird nur, ob etwas
// ausführbar/strukturwirksam in der Hülle landet.
const NUTZLAST = '<p>Beleg &amp; Co</p>"><script>window.__S02_MARKER__=1</script>' +
  '<img src=x onerror="window.__S02_MARKER__=2"><iframe src="https://example.invalid/"></iframe>'

function parse(text) {
  return new DOMParser().parseFromString(text, 'text/html')
}

describe('vorschauSeite', () => {
  it('legt das Dokument unverändert in ein sandbox-iframe', () => {
    const doc = parse(vorschauSeite(NUTZLAST, 'Vorschau Beleg'))
    const rahmen = doc.querySelectorAll('iframe')
    expect(rahmen).toHaveLength(1)
    expect(rahmen[0].getAttribute('sandbox')).toBe('')
    expect(rahmen[0].getAttribute('srcdoc')).toBe(NUTZLAST)
    expect(doc.title).toBe('Vorschau Beleg')
  })

  it('erzeugt in der Hülle selbst keine Skripte, Bilder oder weiteren Rahmen', () => {
    const doc = parse(vorschauSeite(NUTZLAST))
    expect(doc.querySelectorAll('script')).toHaveLength(0)
    expect(doc.querySelectorAll('img')).toHaveLength(0)
    expect(doc.querySelectorAll('iframe')).toHaveLength(1)
    expect(doc.querySelectorAll('[onerror]')).toHaveLength(0)
  })

  it('übersteht Anführungszeichen und Umlaute im Titel', () => {
    const doc = parse(vorschauSeite('<p>x</p>', 'Bericht "Grüße" <b>'))
    expect(doc.title).toBe('Bericht "Grüße" <b>')
    expect(doc.querySelectorAll('b')).toHaveLength(0)
  })

  it('kommt mit leerem Inhalt zurecht', () => {
    const doc = parse(vorschauSeite(undefined))
    expect(doc.querySelector('iframe').getAttribute('srcdoc')).toBe('')
  })
})

describe('oeffneHtmlVorschau', () => {
  afterEach(() => vi.restoreAllMocks())

  it('öffnet eine Blob-URL mit der Hülle, nicht das Rohdokument', async () => {
    let erzeugt = null
    globalThis.URL.createObjectURL = vi.fn(b => { erzeugt = b; return 'blob:test' })
    globalThis.URL.revokeObjectURL = vi.fn()
    const offen = vi.spyOn(window, 'open').mockImplementation(() => null)
    oeffneHtmlVorschau(NUTZLAST, 'T')
    expect(offen).toHaveBeenCalledWith('blob:test', '_blank', 'noopener')
    const text = await erzeugt.text()
    const doc = parse(text)
    expect(doc.querySelectorAll('script')).toHaveLength(0)
    expect(doc.querySelector('iframe').getAttribute('sandbox')).toBe('')
  })
})
