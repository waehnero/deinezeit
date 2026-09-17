/**
 * Zeiten-Import: die Leser im Browser.
 *
 * Der Server prüft, was er bekommt — aber nicht, ob der Browser die Datei
 * richtig gelesen hat. Eine Excel-Uhrzeit, die um zwei Stunden verschoben
 * ankommt, ist für den Server eine gültige Uhrzeit.
 */
import { describe, it, expect } from 'vitest'
import {
  excelZellwert, ausMatrix, jsonZuTabelle, icsZuTabelle,
  tabelleAlsCsv, zuordnungVorschlagen,
} from './zeitenDatei'

describe('excelZellwert', () => {
  it('liest eine reine Uhrzeit ohne Zeitzonen-Versatz', () => {
    expect(excelZellwert(new Date(Date.UTC(1899, 11, 30, 7, 30)))).toBe('07:30')
  })
  it('liest ein reines Datum ohne Uhrzeit', () => {
    expect(excelZellwert(new Date(Date.UTC(2026, 7, 3)))).toBe('03.08.2026')
  })
  it('liest Datum mit Uhrzeit', () => {
    expect(excelZellwert(new Date(Date.UTC(2026, 7, 3, 16, 5)))).toBe('03.08.2026 16:05')
  })
  it('nimmt bei Formeln das Ergebnis', () => {
    expect(excelZellwert({ formula: 'A1', result: 4.5 })).toBe('4.5')
  })
})

describe('ausMatrix', () => {
  it('macht doppelte und leere Überschriften eindeutig und lässt Leerzeilen weg', () => {
    const t = ausMatrix([['Zeit', 'Zeit', ''], ['07:30', '12:00', 'x'], ['', '', '']])
    expect(t.spalten).toEqual(['Zeit', 'Zeit (2)', 'Spalte 3'])
    expect(t.zeilen).toEqual([{ Zeit: '07:30', 'Zeit (2)': '12:00', 'Spalte 3': 'x' }])
  })
})

describe('jsonZuTabelle', () => {
  it('liest eine Liste und macht verschachtelte Objekte flach (Clockify)', () => {
    const t = jsonZuTabelle(JSON.stringify([
      { description: 'Wartung', billable: true, project: { name: 'Musterbau' },
        timeInterval: { start: '2026-08-03T05:30:00Z', end: '2026-08-03T10:00:00Z' } },
    ]))
    expect(t.spalten).toContain('timeInterval.start')
    expect(t.zeilen[0]['project.name']).toBe('Musterbau')
    expect(t.zeilen[0].billable).toBe('ja')
  })
  it('findet die Liste in einem Umschlag', () => {
    expect(jsonZuTabelle('{"total": 1, "data": [{"start": "x"}]}').zeilen).toHaveLength(1)
  })
  it('rät nicht, wenn mehrere Listen in Frage kommen', () => {
    expect(() => jsonZuTabelle('{"a": [{"x": 1}], "b": [{"y": 2}]}')).toThrow(/mehrere Listen/)
  })
  it('meldet kaputtes JSON verständlich', () => {
    expect(() => jsonZuTabelle('{kaputt')).toThrow(/kein gültiges JSON/)
  })
})

describe('icsZuTabelle', () => {
  const ics = [
    'BEGIN:VCALENDAR',
    'BEGIN:VEVENT',
    'DTSTART;TZID=Europe/Vienna:20260803T073000',
    'DTEND;TZID=Europe/Vienna:20260803T120000',
    'SUMMARY:Wartung\\, Musterbau',
    'DESCRIPTION:Zeile eins',
    '  und weiter',
    'RRULE:FREQ=WEEKLY',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'DTSTART:20260804T053000Z',
    'DTEND:20260804T100000Z',
    'SUMMARY:UTC-Termin',
    'END:VEVENT',
    'BEGIN:VEVENT',
    'DTSTART;VALUE=DATE:20260805',
    'DTEND;VALUE=DATE:20260806',
    'SUMMARY:Urlaub',
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n')

  it('liest Ortszeit, UTC und ganztägige Termine', () => {
    const t = icsZuTabelle(ics)
    expect(t.zeilen[0]).toMatchObject({
      Beginn: '03.08.2026 07:30', Ende: '03.08.2026 12:00',
      Titel: 'Wartung, Musterbau', Beschreibung: 'Zeile eins und weiter' })
    expect(t.zeilen[1].Beginn).toBe('2026-08-04T05:30:00Z')
    // Ganztägig: nur ein Datum — der Server beanstandet das, erfunden wird nichts.
    expect(t.zeilen[2].Beginn).toBe('05.08.2026')
  })
  it('weist auf Serientermine und Zeitzonen hin', () => {
    const { hinweise } = icsZuTabelle(ics)
    expect(hinweise.join(' ')).toMatch(/Serientermin/)
    expect(hinweise.join(' ')).toMatch(/Europe\/Vienna/)
  })
})

describe('tabelleAlsCsv', () => {
  it('schreibt Semikolon-CSV mit BOM', () => {
    const csv = tabelleAlsCsv({ spalten: ['A', 'B'], zeilen: [{ A: '1;2', B: 'x' }] })
    expect(csv.charCodeAt(0)).toBe(0xFEFF)
    expect(csv).toContain('A;B')
    expect(csv).toContain('"1;2";x')
  })
})

describe('zuordnungVorschlagen', () => {
  const felder = [
    { key: 'beginn', name: 'Beginn', synonyme: ['start', 'von'] },
    { key: 'ende', name: 'Ende', synonyme: ['end', 'bis'] },
  ]
  it('schlägt über Synonyme vor und vergibt kein Feld doppelt', () => {
    expect(zuordnungVorschlagen(['Von', 'Start', 'BIS', 'Sonstiges'], felder))
      .toEqual({ Von: 'beginn', BIS: 'ende' })
  })
})
