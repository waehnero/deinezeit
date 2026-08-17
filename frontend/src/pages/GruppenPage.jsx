import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ArrowLeft, Loader2, Lock, Plus, ShieldCheck, Trash2, Users, X,
} from 'lucide-react'
import { groupsApi, usersApi } from '../services/api'
import RechteMatrix from '../components/RechteMatrix'

/**
 * Gruppenverwaltung (Teiletappe 2c).
 *
 * Bis hierher waren Rechte nur über die API oder direkt in der Datenbank
 * vergebbar — die Abstufung nach Ansehen/Ändern/Löschen war gebaut, aber nicht
 * bedienbar.
 *
 * Zwei Dinge sind hier bewusst prominent:
 *
 * * Die **Mitgliederzahl** steht an jeder Gruppe. Wer Rechte ändert, ändert
 *   sie für alle darin — das soll man sehen, bevor man klickt, nicht danach.
 * * **Mitgelieferte Gruppen** sind gekennzeichnet und nicht löschbar. Ohne
 *   diese Sperre kann eine Installation ohne jede Gruppe dastehen, und neu
 *   angelegte Benutzer hätten nichts, dem man sie zuordnen könnte.
 */
export default function GruppenPage() {
  const [gruppen, setGruppen] = useState([])
  const [benutzer, setBenutzer] = useState([])
  const [katalog, setKatalog] = useState([])
  const [laden, setLaden] = useState(true)
  const [auswahl, setAuswahl] = useState(null)   // Gruppe im Bearbeiten-Bereich
  const [entwurf, setEntwurf] = useState(null)   // ungespeicherte Änderungen
  const [speichert, setSpeichert] = useState(false)

  const laden_ = useCallback(async () => {
    setLaden(true)
    try {
      const [g, k, u] = await Promise.all([
        groupsApi.list(), groupsApi.katalog(), usersApi.list(),
      ])
      setGruppen(g.data)
      setKatalog(k.data.module)
      setBenutzer(u.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Gruppen konnten nicht geladen werden')
    } finally {
      setLaden(false)
    }
  }, [])

  useEffect(() => { laden_() }, [laden_])

  const oeffnen = (gruppe) => {
    setAuswahl(gruppe)
    setEntwurf({
      name: gruppe.name,
      beschreibung: gruppe.beschreibung || '',
      rechte: JSON.parse(JSON.stringify(gruppe.rechte || {})),
      user_ids: gruppe.mitglieder.map((m) => m.id),
    })
  }

  const neu = () => {
    setAuswahl({ id: null, ist_system: false, mitglieder: [] })
    setEntwurf({ name: '', beschreibung: '', rechte: {}, user_ids: [] })
  }

  const schliessen = () => { setAuswahl(null); setEntwurf(null) }

  const speichern = async () => {
    if (!entwurf.name.trim()) {
      toast.error('Bitte einen Gruppennamen angeben')
      return
    }
    setSpeichert(true)
    try {
      if (auswahl.id) {
        await groupsApi.update(auswahl.id, entwurf)
        toast.success(`„${entwurf.name}“ gespeichert`)
      } else {
        await groupsApi.create(entwurf)
        toast.success(`„${entwurf.name}“ angelegt`)
      }
      schliessen()
      laden_()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Speichern fehlgeschlagen')
    } finally {
      setSpeichert(false)
    }
  }

  const loeschen = async (gruppe) => {
    if (!window.confirm(`Gruppe „${gruppe.name}“ wirklich löschen?`)) return
    try {
      await groupsApi.delete(gruppe.id)
      toast.success(`„${gruppe.name}“ gelöscht`)
      if (auswahl?.id === gruppe.id) schliessen()
      laden_()
    } catch (err) {
      // Der Server lehnt ab, wenn noch Mitglieder zugeordnet sind — sonst
      // verlören diese Personen ihre Rechte, ohne dass es jemand sieht.
      toast.error(err.response?.data?.detail || 'Löschen fehlgeschlagen', {
        duration: 7000,
      })
    }
  }

  const mitgliedUmschalten = (userId) => {
    setEntwurf((e) => ({
      ...e,
      user_ids: e.user_ids.includes(userId)
        ? e.user_ids.filter((id) => id !== userId)
        : [...e.user_ids, userId],
    }))
  }

  const sortierteBenutzer = useMemo(
    () => [...benutzer].sort((a, b) => (a.full_name || '').localeCompare(b.full_name || '')),
    [benutzer])

  if (laden) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={28} className="animate-spin text-primary-500" />
    </div>
  )

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/users"
                className="text-sm text-neutral-400 hover:text-neutral-600 flex items-center gap-1 mb-1">
            <ArrowLeft size={14} /> Benutzerverwaltung
          </Link>
          <h1 className="text-2xl font-bold text-neutral-900">Rechtegruppen</h1>
          <p className="text-neutral-400 text-sm mt-0.5">
            {gruppen.length} Gruppen — Rechte gelten für alle Mitglieder gemeinsam
          </p>
        </div>
        <button onClick={neu} className="btn-primary">
          <Plus size={16} /> Neue Gruppe
        </button>
      </div>

      {/* ── Liste ──────────────────────────────────────────────────────────── */}
      <div className="card overflow-hidden mb-6">
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-100 bg-neutral-50">
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">Gruppe</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide hidden md:table-cell">Module mit Zugang</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide w-32">Mitglieder</th>
              <th className="px-4 py-3 w-20"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-50">
            {gruppen.map((g) => {
              const module = katalog
                .filter((m) => g.rechte?.[m.modul]?.lesen)
                .map((m) => m.label)
              return (
                <tr key={g.id}
                    className={`hover:bg-neutral-50 cursor-pointer transition-colors ${
                      auswahl?.id === g.id ? 'bg-primary-50' : ''}`}
                    onClick={() => oeffnen(g)}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-neutral-900">{g.name}</span>
                      {g.ist_system && (
                        <span title="Mitgelieferte Gruppe — änderbar, aber nicht löschbar"
                              className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500 flex items-center gap-1">
                          <Lock size={10} /> Standard
                        </span>
                      )}
                    </div>
                    {g.beschreibung && (
                      <p className="text-xs text-neutral-400 mt-0.5 line-clamp-1">{g.beschreibung}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-neutral-500 hidden md:table-cell">
                    {module.length === 0
                      ? <span className="text-neutral-300">kein Zugang</span>
                      : module.length === katalog.length
                        ? 'alle Module'
                        : module.join(', ')}
                  </td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1.5 text-sm text-neutral-600">
                      <Users size={13} className="text-neutral-400" />
                      {g.mitglieder.length}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {!g.ist_system && (
                      <button
                        onClick={(e) => { e.stopPropagation(); loeschen(g) }}
                        className="p-1.5 text-neutral-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                        title="Gruppe löschen"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ── Bearbeiten ─────────────────────────────────────────────────────── */}
      {entwurf && (
        <div className="card p-6 space-y-5">
          <div className="flex items-start justify-between">
            <h2 className="font-semibold text-neutral-900 flex items-center gap-2">
              <ShieldCheck size={18} className="text-neutral-400" />
              {auswahl.id ? `„${auswahl.name}“ bearbeiten` : 'Neue Gruppe'}
            </h2>
            <button onClick={schliessen} className="text-neutral-400 hover:text-neutral-600">
              <X size={18} />
            </button>
          </div>

          {auswahl.id && auswahl.mitglieder.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-900">
              Diese Änderung wirkt sofort für <strong>{auswahl.mitglieder.length}</strong>{' '}
              {auswahl.mitglieder.length === 1 ? 'Person' : 'Personen'}:{' '}
              {auswahl.mitglieder.map((m) => m.full_name).join(', ')}
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="label">Name</label>
              <input value={entwurf.name}
                     onChange={(e) => setEntwurf({ ...entwurf, name: e.target.value })}
                     className="input w-full" placeholder="z.B. Vertrieb" />
            </div>
            <div>
              <label className="label">Beschreibung (optional)</label>
              <input value={entwurf.beschreibung}
                     onChange={(e) => setEntwurf({ ...entwurf, beschreibung: e.target.value })}
                     className="input w-full"
                     placeholder="Wofür ist diese Gruppe gedacht?" />
            </div>
          </div>

          <div>
            <label className="label mb-2 block">Rechte</label>
            <RechteMatrix katalog={katalog} rechte={entwurf.rechte}
                          onChange={(r) => setEntwurf({ ...entwurf, rechte: r })} />
          </div>

          <div>
            <label className="label mb-2 block">
              Mitglieder ({entwurf.user_ids.length})
            </label>
            <div className="border border-neutral-200 rounded-xl divide-y divide-neutral-100 max-h-56 overflow-y-auto">
              {sortierteBenutzer.map((u) => (
                <label key={u.id}
                       className="flex items-center gap-3 px-3 py-2 hover:bg-neutral-50 cursor-pointer">
                  <input type="checkbox"
                         checked={entwurf.user_ids.includes(u.id)}
                         onChange={() => mitgliedUmschalten(u.id)}
                         className="w-4 h-4 rounded border-neutral-300 text-primary-600 focus:ring-primary-500" />
                  <span className="text-sm text-neutral-800">{u.full_name}</span>
                  <span className="text-xs text-neutral-400">{u.email}</span>
                  {u.role === 'admin' && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-600 ml-auto">
                      Administrator
                    </span>
                  )}
                </label>
              ))}
            </div>
            <p className="text-xs text-neutral-400 mt-2">
              Administratoren haben unabhängig von Gruppen immer alle Rechte —
              ohne diesen Notausgang könnte eine Rechteänderung die Anlage
              aussperren.
            </p>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button onClick={speichern} disabled={speichert}
                    className="btn-primary">
              {speichert ? <Loader2 size={16} className="animate-spin" /> : null}
              Speichern
            </button>
            <button onClick={schliessen} className="btn-secondary">Abbrechen</button>
          </div>
        </div>
      )}
    </div>
  )
}
