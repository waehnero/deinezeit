import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import PageHeader from '../components/PageHeader'
import {
  Calculator, Wallet, Bell, Book, CalendarCheck, BookText, RefreshCw,
} from 'lucide-react'

function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

/**
 * Bereich Buchhaltung — Einstieg in alles, was nach dem Beleg kommt.
 *
 * Bisher hingen diese Funktionen als Knopfreihe im Kopf der Belegliste. Das
 * Modulrecht „buchhaltung" gab es schon, nur keinen Ort dafür: Es war das
 * einzige Recht ohne eigenen Menüpunkt. Verkauf behält die Belegarbeit,
 * hier steht das Auswerten, Eintreiben und Übergeben.
 *
 * Die Kennzahlen oben sind bewusst nur drei — sie beantworten die Fragen,
 * die man beim Reinschauen wirklich hat: Wie viel steht aus, wie viel davon
 * ist zu spät, und muss ich mahnen?
 */
const KACHELN = [
  {
    to: '/buchhaltung/offene-posten', icon: Wallet, titel: 'Offene Posten',
    text: 'Ausgestellte Belege, die noch nicht beglichen sind — mit Fälligkeitsstaffel und Summen je Kunde.',
  },
  {
    to: '/buchhaltung/mahnlauf', icon: Bell, titel: 'Mahnlauf',
    text: 'Überfällige Rechnungen prüfen, Mahnstufen setzen, Sammelmahnungen erstellen.',
  },
  {
    // Die Umsatzsteuer-Auswertung sitzt auf derselben Seite — sie liest
    // denselben Zeitraum. Eine eigene Kachel würde nur zweimal dorthin führen.
    to: '/buchhaltung/verkaufsbuch', icon: Book, titel: 'Verkaufsbuch & Umsatzsteuer',
    text: 'Belegjournal des Zeitraums, Auswertung je Steuersatz für die Voranmeldung und der Buchungsexport für die Kanzlei.',
  },
  {
    to: '/buchhaltung/abschluss', icon: CalendarCheck, titel: 'Monatsabschluss',
    text: 'Prüfen, festschreiben und als Paket an die Steuerberatung übergeben.',
  },
  {
    to: '/buchhaltung/konten', icon: BookText, titel: 'Kontenplan',
    text: 'Erlöskonten und USt-Codes. Ändern darf nur ein Administrator.',
  },
]

export default function BuchhaltungPage() {
  const navigate = useNavigate()
  const [op, setOp] = useState(null)
  const [mahnbar, setMahnbar] = useState(null)
  const [laden, setLaden] = useState(true)

  useEffect(() => {
    let abgebrochen = false
    // Beide Zahlen sind Beiwerk: Schlägt eine fehl, bleibt die Kachelwand
    // trotzdem benutzbar. Deshalb kein Fehler-Toast, nur ein leerer Wert.
    Promise.allSettled([invoiceApi.openItems({}), invoiceApi.dunningRun({})])
      .then(([o, m]) => {
        if (abgebrochen) return
        if (o.status === 'fulfilled') setOp(o.value.data)
        if (m.status === 'fulfilled') setMahnbar(m.value.data.dunnable_count)
        setLaden(false)
      })
    return () => { abgebrochen = true }
  }, [])

  const ueberfaellig = op
    ? ['b1_30', 'b31_60', 'b61_90', 'b90_plus'].reduce((s, k) => s + Number(op.buckets?.[k] || 0), 0)
    : 0

  return (
    <div>
      <PageHeader icon={Calculator} title="Buchhaltung"
        subtitle="Auswerten, eintreiben und an die Steuerberatung übergeben" />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-6 mb-8">
        <button onClick={() => navigate('/buchhaltung/offene-posten')}
          className="text-left rounded-xl border border-neutral-200 bg-surface p-4 hover:border-neutral-300">
          <p className="text-xs font-medium text-neutral-500">Offen gesamt</p>
          <p className="text-2xl font-semibold text-neutral-900 mt-1">
            {laden ? '—' : fmtEuro(op?.total_open)}
          </p>
          <p className="text-xs text-neutral-400 mt-0.5">{op?.count || 0} Belege</p>
        </button>
        <button onClick={() => navigate('/buchhaltung/offene-posten')}
          className="text-left rounded-xl border border-neutral-200 bg-surface p-4 hover:border-neutral-300">
          <p className="text-xs font-medium text-neutral-500">Davon überfällig</p>
          <p className={`text-2xl font-semibold mt-1 ${ueberfaellig > 0 ? 'text-red-600' : 'text-neutral-900'}`}>
            {laden ? '—' : fmtEuro(ueberfaellig)}
          </p>
          <p className="text-xs text-neutral-400 mt-0.5">Zahlungsziel überschritten</p>
        </button>
        <button onClick={() => navigate('/buchhaltung/mahnlauf')}
          className="text-left rounded-xl border border-neutral-200 bg-surface p-4 hover:border-neutral-300">
          <p className="text-xs font-medium text-neutral-500">Mahnbar</p>
          <p className={`text-2xl font-semibold mt-1 ${mahnbar > 0 ? 'text-amber-600' : 'text-neutral-900'}`}>
            {laden ? '—' : (mahnbar ?? 0)}
          </p>
          <p className="text-xs text-neutral-400 mt-0.5">
            {mahnbar === 1 ? 'Beleg wartet auf eine Mahnung' : 'Belege warten auf eine Mahnung'}
          </p>
        </button>
      </div>

      {laden && (
        <div className="flex justify-center py-2 mb-4">
          <RefreshCw size={16} className="animate-spin text-neutral-300" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {KACHELN.map(k => (
          <button key={k.to} onClick={() => navigate(k.to)}
            className="text-left rounded-xl border border-neutral-200 bg-surface p-5 hover:border-primary-300 hover:shadow-sm transition-all">
            <k.icon size={20} className="text-primary-600 mb-3" />
            <p className="font-semibold text-neutral-800">{k.titel}</p>
            <p className="text-sm text-neutral-500 mt-1 leading-snug">{k.text}</p>
          </button>
        ))}
      </div>
    </div>
  )
}
