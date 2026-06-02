import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { zeiterfassungApi } from '../services/api'
import toast from 'react-hot-toast'
import { ArrowLeft, Plus, Trash2, GripVertical, Loader2, Settings2 } from 'lucide-react'
import { FIELD_TYPES } from '../components/FieldBuilder'

const COL_OPTIONS = [
  { value: 3,  label: '25%' },
  { value: 4,  label: '33%' },
  { value: 6,  label: '50%' },
  { value: 9,  label: '75%' },
  { value: 12, label: '100%' },
]

function makeKey(text) {
  return text.toLowerCase()
    .replace(/[äöüß]/g, c => ({ ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' })[c] || c)
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

export default function ZeiterfassungFelder() {
  const navigate = useNavigate()
  const [fields, setFields] = useState([])
  const [loading, setLoading] = useState(true)

  // Neues Feld Formular
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState('text')
  const [newColSpan, setNewColSpan] = useState(12)
  const [newOptions, setNewOptions] = useState('')
  const [newRequired, setNewRequired] = useState(false)
  const [newShowList, setNewShowList] = useState(true)
  const [saving, setSaving] = useState(false)

  const loadFields = async () => {
    try {
      const res = await zeiterfassungApi.listFields()
      setFields(res.data)
    } catch {
      toast.error('Felder konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadFields() }, [])

  const handleAdd = async () => {
    if (!newName.trim()) return toast.error('Bitte Namen eingeben')
    setSaving(true)
    try {
      await zeiterfassungApi.createField({
        name: newName.trim(),
        key: makeKey(newName),
        field_type: newType,
        col_span: newColSpan,
        is_required: newRequired,
        show_in_list: newShowList,
        options: newType === 'dropdown' && newOptions
          ? newOptions.split('\n').map(s => s.trim()).filter(Boolean)
          : null,
      })
      toast.success('Feld angelegt')
      setNewName(''); setNewType('text'); setNewColSpan(12)
      setNewOptions(''); setNewRequired(false); setNewShowList(true)
      setShowAdd(false)
      loadFields()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Anlegen')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (field) => {
    try {
      await zeiterfassungApi.deleteField(field.id)
      toast.success('Feld gelöscht')
      setFields(fields.filter(f => f.id !== field.id))
    } catch {
      toast.error('Löschen fehlgeschlagen')
    }
  }

  const handleColSpanChange = async (field, colSpan) => {
    const updated = fields.map(f => f.id === field.id ? { ...f, col_span: colSpan } : f)
    setFields(updated)
    try {
      await zeiterfassungApi.updateFieldOrder([{ id: field.id, col_span: colSpan }])
    } catch {
      toast.error('Fehler beim Speichern')
    }
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate('/zeiterfassung')}
          className="flex items-center gap-1 text-gray-400 hover:text-gray-700 transition text-sm">
          <ArrowLeft size={16} /> Zurück
        </button>
        <div className="flex items-center gap-2">
          <Settings2 size={20} className="text-primary-600" />
          <h1 className="text-xl font-bold text-gray-900">Custom-Felder für Zeiterfassung</h1>
        </div>
      </div>

      <p className="text-sm text-gray-500 mb-6 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3">
        Hier kannst du zusätzliche Felder für Zeiteinträge definieren — z.B. „Fahrtkosten", „Kilometer" oder „Tagessatz".
        Diese Felder erscheinen dann im Nachtragen-Dialog und können frei positioniert werden.
      </p>

      {/* Feldliste */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden mb-4">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 size={24} className="animate-spin text-primary-400" />
          </div>
        ) : fields.length === 0 ? (
          <div className="text-center py-10 text-gray-400 text-sm">
            Noch keine Custom-Felder definiert.
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Feld</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Typ</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Breite</th>
                <th className="px-4 py-3 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {fields.map(field => {
                const TypeInfo = FIELD_TYPES.find(t => t.key === field.field_type)
                return (
                  <tr key={field.id} className="hover:bg-gray-50 transition">
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-gray-800">{field.name}</div>
                      <div className="text-xs text-gray-400 font-mono">{field.key}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {TypeInfo ? TypeInfo.label : field.field_type}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={field.col_span}
                        onChange={(e) => handleColSpanChange(field, Number(e.target.value))}
                        className="px-2 py-1 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-primary-500"
                      >
                        {COL_OPTIONS.map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(field)}
                        className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Neues Feld */}
      {showAdd ? (
        <div className="bg-white rounded-2xl border border-primary-200 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Neues Feld</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="z.B. Fahrtkosten"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                autoFocus
              />
              {newName && (
                <p className="text-xs text-gray-400 mt-1 font-mono">Key: {makeKey(newName)}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Feldtyp</label>
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
              >
                {FIELD_TYPES.filter(t => t.key !== 'relation').map(t => (
                  <option key={t.key} value={t.key}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Breite</label>
              <select
                value={newColSpan}
                onChange={(e) => setNewColSpan(Number(e.target.value))}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
              >
                {COL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            {newType === 'dropdown' && (
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Optionen <span className="text-gray-400 font-normal">(eine pro Zeile)</span>
                </label>
                <textarea
                  value={newOptions}
                  onChange={(e) => setNewOptions(e.target.value)}
                  rows={4}
                  placeholder="Option 1&#10;Option 2&#10;Option 3"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none font-mono"
                />
              </div>
            )}
            <div className="flex items-center gap-4 col-span-2">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input type="checkbox" checked={newRequired} onChange={(e) => setNewRequired(e.target.checked)}
                  className="w-4 h-4 rounded accent-primary-600" />
                Pflichtfeld
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input type="checkbox" checked={newShowList} onChange={(e) => setNewShowList(e.target.checked)}
                  className="w-4 h-4 rounded accent-primary-600" />
                In Liste anzeigen
              </label>
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setShowAdd(false)}
              className="px-4 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition">
              Abbrechen
            </button>
            <button onClick={handleAdd} disabled={saving}
              className="px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition flex items-center gap-2">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Feld anlegen
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowAdd(true)}
          className="w-full py-3 border-2 border-dashed border-gray-200 rounded-2xl text-sm text-gray-400 hover:border-primary-300 hover:text-primary-500 transition flex items-center justify-center gap-2"
        >
          <Plus size={16} />
          Neues Custom-Feld hinzufügen
        </button>
      )}
    </div>
  )
}
