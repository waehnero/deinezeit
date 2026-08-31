import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { masterdataApi, accountingApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { Layers, ArrowLeft, Loader2, Plus, Save, Pencil, Trash2, Lock } from 'lucide-react'

/**
 * Artikelgruppen (Warengruppen).
 *
 * Zwei Aufgaben in einer Zeile:
 *
 * 1. **Nummernkreis.** Präfix + Zähler ergeben die Artikelnummer — „DL-0007".
 *    Die Vorschau zeigt, was als Nächstes herauskommt, damit man Präfix und
 *    Zähler nicht im Kopf zusammensetzen muss.
 * 2. **Buchungsvorgabe.** Erlös- und Aufwandskonto gelten für alle Artikel der
 *    Gruppe. Ein Artikel darf abweichen; tut er es nicht, gilt die Gruppe. So
 *    steht das Konto an einer Stelle statt an dreihundert.
 *
 * Ändern darf nur ein Admin — wie beim Kontenplan, aus demselben Grund: Ein
 * verstelltes Erlöskonto wirkt sich auf jede künftige Buchung aus. Sehen darf
 * es jeder, der Stammdaten öffnen kann.
 */
const LEER = {
  nr: '', name: '', beschreibung: '', praefix: '', stellen: 4,
  naechste_nummer: 1, erloes_konto_nr: '', aufwand_konto_nr: '',
  ust_satz: '', artikelart: '', einheit: '', is_active: true, sort_order: 0,
}

const ARTIKELARTEN = [
  { key: '',               label: '— keine Vorgabe —' },
  { key: 'ware',           label: 'Ware' },
  { key: 'dienstleistung', label: 'Dienstleistung' },
]

// Notnagel, falls das Feld „einheit" im Artikelstamm fehlt oder keine
// Auswahlliste hat. Die gepflegte Liste kommt aus der Felddefinition — eine
// zweite fest verdrahtete Liste hier würde unweigerlich auseinanderlaufen:
// Wer im Feld-Editor „m²" ergänzt, findet es sonst in der Gruppe nicht wieder.
const EINHEITEN_NOTNAGEL = ['Stk', 'h', 'Tag', 'Pauschale', 'm', 'm²', 'm³',
                            'lfm', 'kg', 't', 'Liter', 'km']

export default function ArtikelgruppenPage() {
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [gruppen, setGruppen] = useState([])
  const [kontenplan, setKontenplan] = useState([])
  const [einheiten, setEinheiten] = useState(EINHEITEN_NOTNAGEL)
  // Konten je Steuerfall der gerade bearbeiteten Gruppe — nicht zu verwechseln
  // mit dem Kontenplan darüber.
  const [konten, setKonten] = useState([])
  const [loading, setLoading] = useState(true)
  const [editId, setEditId] = useState(null)
  const [formular, setFormular] = useState(LEER)
  const [neu, setNeu] = useState(false)
  const [speichert, setSpeichert] = useState(false)

  async function laden() {
    setLoading(true)
    try {
      const [g, k, typ] = await Promise.all([
        masterdataApi.listArticleGroups(),
        accountingApi.listAccounts({ active_only: true }),
        // Die Einheiten kommen aus der Auswahlliste des Artikelfeldes
        // „einheit". So gibt es genau eine Stelle, an der sie gepflegt werden:
        // den Feld-Editor auf der Artikelseite.
        masterdataApi.getType('artikel').catch(() => null),
      ])
      setGruppen(g.data)
      setKontenplan(k.data)
      const feld = typ?.data?.fields?.find(f => f.key === 'einheit')
      if (feld?.options?.length) setEinheiten(feld.options)
    } catch {
      toast.error('Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { laden() }, [])

  const erloeskonten = kontenplan.filter(k => k.typ === 'ertrag')
  const aufwandskonten = kontenplan.filter(k => k.typ === 'aufwand')

  function bearbeitenStarten(g) {
    setNeu(false)
    setEditId(g.id)
    // Das Backend liefert immer alle vier Steuerfälle, auch die ungepflegten —
    // so muss das Formular keine fehlenden Zeilen erfinden.
    setKonten((g.konten || []).map(k => ({
      steuerfall: k.steuerfall,
      bezeichnung: k.bezeichnung,
      konto_nr: k.konto_nr || '',
      ust_satz: k.ust_satz ?? '',
      ohne_steuer: !!k.ohne_steuer,
    })))
    setFormular({
      nr: g.nr, name: g.name, beschreibung: g.beschreibung || '',
      praefix: g.praefix || '', stellen: g.stellen,
      naechste_nummer: g.naechste_nummer,
      erloes_konto_nr: g.erloes_konto_nr || '',
      aufwand_konto_nr: g.aufwand_konto_nr || '',
      ust_satz: g.ust_satz ?? '', artikelart: g.artikelart || '',
      einheit: g.einheit || '', is_active: g.is_active, sort_order: g.sort_order,
    })
  }

  function abbrechen() {
    setEditId(null); setNeu(false); setFormular(LEER); setKonten([])
  }

  function kontoZeileSetzen(fall, feld, wert) {
    setKonten(l => l.map(k => k.steuerfall !== fall ? k : {
      ...k,
      [feld]: wert,
      // „Kein Steuersatz" und ein Satz schließen einander aus. Reverse Charge
      // hat keinen Satz — auch nicht null; eine Null erschiene in der UVA als
      // steuerfreier Umsatz statt als übergegangene Steuerschuld.
      ...(feld === 'ohne_steuer' && wert ? { ust_satz: '' } : {}),
      ...(feld === 'ust_satz' && wert !== '' ? { ohne_steuer: false } : {}),
    }))
  }

  // Leere Zeichenketten sind „nicht gesetzt", nicht „leerer Wert" — sonst
  // schriebe das Formular ein Erlöskonto "" in die Gruppe, und die Kaskade
  // würde es für eine bewusste Angabe halten.
  function nutzlast() {
    return {
      ...formular,
      praefix: formular.praefix || formular.nr,
      stellen: Number(formular.stellen) || 4,
      naechste_nummer: Number(formular.naechste_nummer) || 1,
      erloes_konto_nr: formular.erloes_konto_nr || null,
      aufwand_konto_nr: formular.aufwand_konto_nr || null,
      ust_satz: formular.ust_satz === '' ? null : Number(formular.ust_satz),
      artikelart: formular.artikelart || null,
      einheit: formular.einheit || null,
      beschreibung: formular.beschreibung || null,
    }
  }

  async function speichern() {
    if (!formular.nr.trim() || !formular.name.trim()) {
      toast.error('Kurzschlüssel und Bezeichnung sind Pflicht')
      return
    }
    setSpeichert(true)
    try {
      if (neu) {
        await masterdataApi.createArticleGroup(nutzlast())
        toast.success(`Artikelgruppe „${formular.name}" angelegt`)
      } else {
        await masterdataApi.updateArticleGroup(editId, nutzlast())
        // Die Konten je Steuerfall werden vollständig ersetzt — das Formular
        // schickt immer alle vier Fälle. Eine teilweise Aktualisierung ließe
        // offen, ob eine fehlende Zeile unverändert bleiben oder verschwinden
        // soll, und im Zweifel bucht eine stehengebliebene Zeile weiter.
        await masterdataApi.setArticleGroupAccounts(editId, konten.map(k => ({
          steuerfall: k.steuerfall,
          konto_nr: k.konto_nr || null,
          ust_satz: k.ust_satz === '' ? null : Number(k.ust_satz),
          ohne_steuer: !!k.ohne_steuer,
        })))
        toast.success('Gespeichert')
      }
      abbrechen()
      laden()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSpeichert(false)
    }
  }

  async function loeschen(g) {
    if (!window.confirm(`Artikelgruppe „${g.name}" wirklich löschen?`)) return
    try {
      await masterdataApi.deleteArticleGroup(g.id)
      toast.success('Gelöscht')
      laden()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Löschen')
    }
  }

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-neutral-400" /></div>
  }

  const imFormular = neu || editId !== null

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/masterdata/artikel')}
          className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={Layers} title="Artikelgruppen"
          subtitle="Nummernkreis und Buchungsvorgabe für das Sortiment" />
      </div>

      {!isAdmin && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600">
          <Lock size={15} className="mt-0.5 shrink-0" />
          <span>Nur zur Ansicht — Gruppen anlegen oder ändern darf ein Administrator.</span>
        </div>
      )}

      <p className="text-xs text-neutral-400 mb-4 max-w-2xl">
        Jede Gruppe führt ihren eigenen Zähler: Aus Präfix und laufender Nummer
        entsteht die Artikelnummer. Erlös- und Aufwandskonto der Gruppe gelten
        für alle ihre Artikel, solange am Artikel selbst nichts anderes steht.
      </p>

      {isAdmin && !imFormular && (
        <button onClick={() => { setNeu(true); setEditId(null); setFormular(LEER) }}
          className="flex items-center gap-1.5 px-3 py-1.5 mb-3 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
          <Plus size={14} /> Artikelgruppe hinzufügen
        </button>
      )}

      {imFormular && (
        <div className="border border-primary-200 bg-primary-50 rounded-xl p-4 mb-4">
          <h3 className="text-sm font-semibold text-primary-900 mb-3">
            {neu ? 'Neue Artikelgruppe' : `Artikelgruppe „${formular.name}" bearbeiten`}
          </h3>
          <div className="grid grid-cols-12 gap-3">
            <Feld label="Kurzschlüssel *" span={2}>
              <input value={formular.nr} onChange={e => setFormular({ ...formular, nr: e.target.value.toUpperCase() })}
                placeholder="DL" maxLength={20} className={INPUT} />
            </Feld>
            <Feld label="Bezeichnung *" span={4}>
              <input value={formular.name} onChange={e => setFormular({ ...formular, name: e.target.value })}
                placeholder="Dienstleistung" className={INPUT} />
            </Feld>
            <Feld label="Präfix" span={2} hinweis="leer = Kurzschlüssel">
              <input value={formular.praefix} onChange={e => setFormular({ ...formular, praefix: e.target.value.toUpperCase() })}
                placeholder={formular.nr || 'DL'} maxLength={10} className={INPUT} />
            </Feld>
            <Feld label="Stellen" span={2}>
              <input type="number" min={1} max={10} value={formular.stellen}
                onChange={e => setFormular({ ...formular, stellen: e.target.value })} className={INPUT} />
            </Feld>
            <Feld label="Nächste Nummer" span={2} hinweis="für Altdaten anpassen">
              <input type="number" min={1} value={formular.naechste_nummer}
                onChange={e => setFormular({ ...formular, naechste_nummer: e.target.value })} className={INPUT} />
            </Feld>

            <Feld label="Erlöskonto" span={4}>
              <select value={formular.erloes_konto_nr}
                onChange={e => setFormular({ ...formular, erloes_konto_nr: e.target.value })} className={INPUT}>
                <option value="">— keine Vorgabe —</option>
                {erloeskonten.map(k => <option key={k.nr} value={k.nr}>{k.nr} — {k.name}</option>)}
              </select>
            </Feld>
            <Feld label="Aufwandskonto" span={4}>
              <select value={formular.aufwand_konto_nr}
                onChange={e => setFormular({ ...formular, aufwand_konto_nr: e.target.value })} className={INPUT}>
                <option value="">— keine Vorgabe —</option>
                {aufwandskonten.map(k => <option key={k.nr} value={k.nr}>{k.nr} — {k.name}</option>)}
              </select>
            </Feld>
            <Feld label="USt-Satz %" span={2}>
              <input type="number" step="0.01" value={formular.ust_satz}
                onChange={e => setFormular({ ...formular, ust_satz: e.target.value })}
                placeholder="20" className={INPUT} />
            </Feld>
            <Feld label="Einheit" span={2} hinweis={
              <button type="button" onClick={() => navigate('/masterdata/artikel')}
                className="text-primary-600 hover:underline">
                Liste pflegen
              </button>
            }>
              <select value={formular.einheit}
                onChange={e => setFormular({ ...formular, einheit: e.target.value })} className={INPUT}>
                <option value="">— keine —</option>
                {/* Eine gespeicherte Einheit, die es in der Liste nicht mehr
                    gibt, darf nicht stillschweigend verschwinden — sonst
                    leert das nächste Speichern das Feld, ohne dass jemand es
                    angefasst hat. */}
                {formular.einheit && !einheiten.includes(formular.einheit) && (
                  <option value={formular.einheit}>{formular.einheit} (nicht in der Liste)</option>
                )}
                {einheiten.map(e2 => <option key={e2} value={e2}>{e2}</option>)}
              </select>
            </Feld>

            <Feld label="Artikelart" span={3}>
              <select value={formular.artikelart}
                onChange={e => setFormular({ ...formular, artikelart: e.target.value })} className={INPUT}>
                {ARTIKELARTEN.map(a => <option key={a.key} value={a.key}>{a.label}</option>)}
              </select>
            </Feld>
            <Feld label="Beschreibung" span={7}>
              <input value={formular.beschreibung}
                onChange={e => setFormular({ ...formular, beschreibung: e.target.value })} className={INPUT} />
            </Feld>
            <div className="col-span-2 flex items-end pb-1.5">
              <label className="flex items-center gap-2 text-sm text-neutral-700 cursor-pointer">
                <input type="checkbox" checked={formular.is_active}
                  onChange={e => setFormular({ ...formular, is_active: e.target.checked })}
                  className="w-4 h-4 accent-primary-600" />
                Aktiv
              </label>
            </div>
          </div>

          {/* Konten je Steuerfall — nur beim Bearbeiten: Die Gruppe muss erst
              gespeichert sein, bevor Zeilen daran hängen können. Nach dem
              Anlegen erscheint der Block beim ersten Bearbeiten. */}
          {!neu && konten.length > 0 && (
            <div className="mt-5 pt-4 border-t border-primary-200">
              <h4 className="text-sm font-semibold text-primary-900 mb-1">
                Erlöskonten je Steuerfall
              </h4>
              <p className="text-xs text-neutral-500 mb-3 max-w-2xl">
                Welches Konto gilt, hängt auch davon ab, an wen verkauft wird.
                Der Steuerfall steht am Kontakt (Register Finanz). Bleibt eine
                Zeile leer, gilt das Erlöskonto der Gruppe von oben.
              </p>

              <div className="space-y-2">
                {konten.map(k => (
                  <div key={k.steuerfall} className="grid grid-cols-12 gap-2 items-center">
                    <div className="col-span-12 sm:col-span-4 text-sm text-neutral-700">
                      {k.bezeichnung}
                    </div>
                    <div className="col-span-7 sm:col-span-5">
                      <select value={k.konto_nr}
                        onChange={e => kontoZeileSetzen(k.steuerfall, 'konto_nr', e.target.value)}
                        className={INPUT}>
                        <option value="">— wie Gruppe —</option>
                        {k.konto_nr && !erloeskonten.some(e2 => e2.nr === k.konto_nr) && (
                          <option value={k.konto_nr}>{k.konto_nr} (nicht im Kontenplan)</option>
                        )}
                        {erloeskonten.map(e2 => (
                          <option key={e2.nr} value={e2.nr}>{e2.nr} — {e2.name}</option>
                        ))}
                      </select>
                    </div>
                    <div className="col-span-5 sm:col-span-2">
                      <input type="number" step="0.01" value={k.ust_satz}
                        disabled={k.ohne_steuer}
                        onChange={e => kontoZeileSetzen(k.steuerfall, 'ust_satz', e.target.value)}
                        placeholder="USt %"
                        className={`${INPUT} disabled:bg-neutral-100 disabled:text-neutral-400`} />
                    </div>
                    <div className="col-span-12 sm:col-span-1">
                      <label className="flex items-center gap-1.5 text-xs text-neutral-600 cursor-pointer whitespace-nowrap"
                        title="Reverse Charge: gar kein Steuersatz — nicht null Prozent">
                        <input type="checkbox" checked={k.ohne_steuer}
                          onChange={e => kontoZeileSetzen(k.steuerfall, 'ohne_steuer', e.target.checked)}
                          className="w-3.5 h-3.5 accent-primary-600" />
                        o. St.
                      </label>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-neutral-400 mt-2 max-w-2xl">
                „o. St." heißt <em>kein</em> Steuersatz (Reverse Charge) und ist
                nicht dasselbe wie 0 %. Innergemeinschaftliche Lieferung und
                Ausfuhr sind steuerfrei mit 0 % und erscheinen in der
                Voranmeldung mit Bemessungsgrundlage; bei Reverse Charge geht
                die Steuerschuld über. Bleibt der Satz leer, gilt der des
                Artikels — das ist der Inlandsfall, wo 20, 13 oder 10 am Artikel
                hängen.
              </p>
            </div>
          )}

          <div className="flex gap-2 mt-4">
            <button onClick={speichern} disabled={speichert}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
              {speichert ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {neu ? 'Anlegen' : 'Speichern'}
            </button>
            <button onClick={abbrechen}
              className="px-3 py-1.5 text-sm border border-neutral-300 rounded-lg hover:bg-surface">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div className="border border-neutral-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm min-w-[820px]">
          <thead><tr className="bg-neutral-50 border-b border-neutral-100">
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">Kürzel</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500">Bezeichnung</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-36">Nächste Nummer</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-28">Erlös</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-28">Aufwand</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">USt</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">Artikel</th>
            <th className="px-3 py-2.5 w-20"></th>
          </tr></thead>
          <tbody className="divide-y divide-neutral-50">
            {gruppen.map(g => (
              <tr key={g.id} className={`hover:bg-neutral-50 ${!g.is_active ? 'opacity-40' : ''}`}>
                <td className="px-3 py-2.5 font-mono font-medium text-neutral-800">{g.nr}</td>
                <td className="px-3 py-2.5 text-neutral-700">
                  {g.name}
                  {g.beschreibung && <span className="block text-xs text-neutral-400">{g.beschreibung}</span>}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-neutral-500">
                  {g.naechste_artikelnummer || '—'}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-neutral-500">{g.erloes_konto_nr || '—'}</td>
                <td className="px-3 py-2.5 font-mono text-xs text-neutral-500">{g.aufwand_konto_nr || '—'}</td>
                <td className="px-3 py-2.5 text-xs text-neutral-500">
                  {g.ust_satz != null ? `${Number(g.ust_satz)} %` : '—'}
                </td>
                <td className="px-3 py-2.5 text-xs text-neutral-500">{g.artikel_anzahl}</td>
                <td className="px-3 py-2.5">
                  {isAdmin && (
                    <div className="flex gap-1 justify-end">
                      <button onClick={() => bearbeitenStarten(g)}
                        className="p-1 text-neutral-400 hover:text-neutral-700" title="Bearbeiten">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => loeschen(g)}
                        className="p-1 text-neutral-400 hover:text-red-500" title="Löschen">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {gruppen.length === 0 && (
          <div className="text-center py-8 text-sm text-neutral-400">
            Noch keine Artikelgruppen angelegt.
          </div>
        )}
      </div>
    </div>
  )
}

const INPUT = "w-full border border-neutral-200 rounded-lg px-2 py-1.5 text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-primary-300"

const SPAN = {
  2: 'col-span-6 sm:col-span-2', 3: 'col-span-6 sm:col-span-3',
  4: 'col-span-12 sm:col-span-4', 7: 'col-span-12 sm:col-span-7',
}

function Feld({ label, span, hinweis, children }) {
  return (
    <div className={SPAN[span] || 'col-span-12'}>
      <label className="block text-xs font-medium text-neutral-600 mb-1">{label}</label>
      {children}
      {hinweis && <p className="text-[11px] text-neutral-400 mt-0.5">{hinweis}</p>}
    </div>
  )
}
