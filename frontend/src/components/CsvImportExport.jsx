import { useState, useRef } from 'react'
import { masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import Papa from 'papaparse'
import { Download, Upload, X, Check, Loader2, AlertCircle, FileText } from 'lucide-react'

// ── CSV Export ────────────────────────────────────────────────────────────────
export function CsvExportButton({ slug, entityName }) {
  const [loading, setLoading] = useState(false)

  const handleExport = async () => {
    setLoading(true)
    try {
      const res = await masterdataApi.exportCsv(slug)
      const bom = '﻿'  // BOM für Excel-Kompatibilität
      const blob = new Blob([bom + res.data], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${slug}_export_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`${entityName} als CSV exportiert`)
    } catch {
      toast.error('Export fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
      title="Als CSV exportieren"
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
      Export
    </button>
  )
}

// ── CSV Import ────────────────────────────────────────────────────────────────
export function CsvImportButton({ slug, entityType, onImported }) {
  const [showModal, setShowModal] = useState(false)

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 transition"
        title="Aus CSV importieren"
      >
        <Upload size={15} />
        Import
      </button>

      {showModal && (
        <CsvImportModal
          slug={slug}
          entityType={entityType}
          onClose={() => setShowModal(false)}
          onImported={(count) => {
            setShowModal(false)
            onImported?.(count)
          }}
        />
      )}
    </>
  )
}

// ── Import-Modal ──────────────────────────────────────────────────────────────
function CsvImportModal({ slug, entityType, onClose, onImported }) {
  const fileRef = useRef()
  const [step, setStep] = useState('upload')  // upload | preview | importing | done
  const [rows, setRows] = useState([])
  const [headers, setHeaders] = useState([])
  const [mapping, setMapping] = useState({})  // csvHeader → fieldKey
  const [loading, setLoading] = useState(false)
  const [importedCount, setImportedCount] = useState(0)

  const fields = entityType.fields.sort((a, b) => a.sort_order - b.sort_order)

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      delimiter: '',          // auto-detect ; or ,
      complete: (result) => {
        if (!result.data?.length) {
          toast.error('Datei ist leer oder konnte nicht gelesen werden')
          return
        }
        const csvHeaders = result.meta.fields || []
        setHeaders(csvHeaders)
        setRows(result.data)

        // Automatisches Mapping: CSV-Spalte → Feld (nach Name)
        const autoMap = {}
        csvHeaders.forEach(h => {
          const match = fields.find(f =>
            f.name.toLowerCase() === h.toLowerCase() ||
            f.key.toLowerCase() === h.toLowerCase()
          )
          if (match) autoMap[h] = match.key
        })
        setMapping(autoMap)
        setStep('preview')
      },
      error: () => toast.error('Datei konnte nicht gelesen werden'),
    })
  }

  const handleImport = async () => {
    const mappedRows = rows.map(row => {
      const data = {}
      Object.entries(mapping).forEach(([csvCol, fieldKey]) => {
        if (fieldKey && fieldKey !== '__ignore__') {
          data[fieldKey] = row[csvCol] || ''
        }
      })
      return data
    })

    setLoading(true)
    setStep('importing')
    try {
      const res = await masterdataApi.importCsv(slug, mappedRows)
      setImportedCount(res.data.count)
      setStep('done')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import fehlgeschlagen')
      setStep('preview')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100 flex-shrink-0">
          <h2 className="text-lg font-bold text-gray-900">CSV Import — {entityType.name}</h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">

          {/* Schritt 1: Datei hochladen */}
          {step === 'upload' && (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
                <p className="font-medium mb-1">Hinweise zum CSV-Format:</p>
                <ul className="list-disc list-inside space-y-1 text-blue-700">
                  <li>Erste Zeile muss die Spaltenüberschriften enthalten</li>
                  <li>Trennzeichen: Semikolon (;) oder Komma (,) — wird automatisch erkannt</li>
                  <li>Zeichensatz: UTF-8 (empfohlen) oder ANSI</li>
                  <li>Maximale Dateigröße: 10 MB</li>
                </ul>
              </div>

              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-primary-400 hover:bg-primary-50 rounded-xl p-10 text-center cursor-pointer transition"
              >
                <FileText size={40} className="mx-auto mb-3 text-gray-300" />
                <p className="font-medium text-gray-600">CSV-Datei auswählen</p>
                <p className="text-sm text-gray-400 mt-1">oder hierher ziehen</p>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,.txt"
                  className="hidden"
                  onChange={handleFile}
                />
              </div>
            </div>
          )}

          {/* Schritt 2: Spaltenzuordnung */}
          {step === 'preview' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 rounded-xl p-3">
                <Check size={16} className="text-green-500" />
                <span>{rows.length} Zeilen erkannt · {headers.length} Spalten</span>
              </div>

              <div>
                <p className="text-sm font-semibold text-gray-800 mb-2">Spaltenzuordnung</p>
                <p className="text-xs text-gray-500 mb-3">
                  Ordnen Sie jede CSV-Spalte einem Feld zu. Nicht benötigte Spalten auf „Ignorieren" setzen.
                </p>
                <div className="space-y-2">
                  {headers.map(h => (
                    <div key={h} className="flex items-center gap-3 text-sm">
                      <div className="w-1/2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 font-mono text-xs truncate">
                        {h}
                      </div>
                      <span className="text-gray-400">→</span>
                      <select
                        value={mapping[h] || '__ignore__'}
                        onChange={e => setMapping({ ...mapping, [h]: e.target.value })}
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"
                      >
                        <option value="__ignore__">— Ignorieren —</option>
                        {fields.map(f => (
                          <option key={f.key} value={f.key}>{f.name}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>

              {/* Vorschau erste 3 Zeilen */}
              {rows.slice(0, 3).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Vorschau (erste {Math.min(3, rows.length)} von {rows.length} Zeilen)
                  </p>
                  <div className="overflow-x-auto border border-gray-200 rounded-xl">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr>
                          {headers.map(h => (
                            <th key={h} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.slice(0, 3).map((row, i) => (
                          <tr key={i} className="border-t border-gray-100">
                            {headers.map(h => (
                              <td key={h} className="px-3 py-2 text-gray-600 max-w-[150px] truncate">
                                {row[h]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Schritt 3: Importieren */}
          {step === 'importing' && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <Loader2 size={40} className="animate-spin text-primary-500" />
              <p className="text-gray-600 font-medium">Importiere {rows.length} Datensätze …</p>
            </div>
          )}

          {/* Schritt 4: Fertig */}
          {step === 'done' && (
            <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                <Check size={32} className="text-green-600" />
              </div>
              <div>
                <p className="text-xl font-bold text-gray-900">{importedCount} Datensätze importiert</p>
                <p className="text-gray-500 mt-1">Alle Einträge wurden erfolgreich angelegt.</p>
              </div>
              <button
                onClick={() => onImported(importedCount)}
                className="px-6 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition"
              >
                Fertig
              </button>
            </div>
          )}
        </div>

        {/* Footer-Buttons */}
        {(step === 'upload' || step === 'preview') && (
          <div className="flex gap-3 p-5 border-t border-gray-100 flex-shrink-0">
            <button onClick={onClose}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
              Abbrechen
            </button>
            {step === 'preview' && (
              <button
                onClick={handleImport}
                disabled={loading || !Object.values(mapping).some(v => v && v !== '__ignore__')}
                className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2"
              >
                <Upload size={16} />
                {rows.length} Datensätze importieren
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
