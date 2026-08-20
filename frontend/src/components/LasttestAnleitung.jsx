import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  Gauge, Server, Monitor, Copy, Check, AlertTriangle, ExternalLink,
} from 'lucide-react'

/**
 * Anleitung für einen Lasttest mit Locust.
 *
 * Bewusst nur eine Anleitung und kein Knopf: Locust hat keine eigene
 * Anmeldung. Ein Startknopf in der Anwendung wäre eine Einladung, die eigene
 * Installation lahmzulegen — und ein über nginx geöffneter Port wäre eine
 * offene Tür für jeden, der ihn findet. Der Lasttest läuft deshalb dort, wo
 * ohnehin nur Befugte hinkommen: am Server über SSH, lokal über das Terminal.
 *
 * Zwei Varianten, weil sich die Wege unterscheiden. Vorausgewählt wird die,
 * die zur laufenden Installation passt (`local_mode` aus /system/version).
 */

function Befehl({ children, hinweis }) {
  const [kopiert, setKopiert] = useState(false)
  const text = String(children).trim()

  const kopieren = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setKopiert(true)
      setTimeout(() => setKopiert(false), 2000)
    } catch {
      toast.error('Zwischenablage nicht verfügbar')
    }
  }

  return (
    <div className="mt-2">
      <div className="relative group">
        <pre className="bg-neutral-900 text-neutral-100 text-xs px-3 py-2.5 pr-10 rounded-lg overflow-x-auto font-mono whitespace-pre">
{text}
        </pre>
        <button onClick={kopieren}
          className="absolute top-2 right-2 p-1.5 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-700 transition"
          title="Befehl kopieren">
          {kopiert ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
        </button>
      </div>
      {hinweis && <p className="text-xs text-gray-500 mt-1">{hinweis}</p>}
    </div>
  )
}

function Schritt({ nummer, titel, children }) {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-100 text-primary-700 text-xs font-semibold flex items-center justify-center mt-0.5">
        {nummer}
      </div>
      <div className="flex-1 min-w-0 pb-5">
        <p className="text-sm font-medium text-gray-900">{titel}</p>
        <div className="text-sm text-gray-600 mt-1">{children}</div>
      </div>
    </div>
  )
}

export default function LasttestAnleitung({ istLokal = false }) {
  const [variante, setVariante] = useState(istLokal ? 'lokal' : 'server')
  const amServer = variante === 'server'

  const compose = amServer
    ? 'docker compose'
    : 'docker compose -f docker-compose.local.yml'
  const ziel = amServer ? 'https://dz.wwinterface.online' : 'http://localhost'

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <Gauge size={16} className="text-primary-500" />
          Lasttest durchführen
        </h3>
        <p className="text-sm text-gray-500 mt-1">
          Misst, wie sich DeineZeit verhält, wenn mehrere Personen gleichzeitig
          arbeiten. Der Test wird im Terminal gestartet, nicht hier — siehe
          Hinweis unten.
        </p>
      </div>

      {/* Variantenwahl */}
      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg w-fit">
        {[
          { id: 'server', label: 'Server (über SSH)', icon: Server },
          { id: 'lokal',  label: 'Lokal (Terminal)',  icon: Monitor },
        ].map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setVariante(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md transition-all ${
              variante === id
                ? 'bg-surface text-neutral-900 shadow-sm font-medium'
                : 'text-neutral-600 hover:text-neutral-800'}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {amServer && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Am Server nur außerhalb der Arbeitszeit.</p>
            <p className="mt-1">
              Ein Lauf mit 100 Benutzern belegt den Server vollständig — wer
              gerade arbeitet, wartet. Sieh vorher im Reiter „System" nach, wer
              angemeldet ist. Außerdem entstehen echte Prüfdaten in euren
              Stammdaten, die nachher aufgeräumt werden müssen.
            </p>
          </div>
        </div>
      )}

      <div>
        <Schritt nummer={1} titel={amServer ? 'Am Server anmelden' : 'Terminal im Projektordner öffnen'}>
          {amServer ? (
            <>
              <p>Per SSH auf den Server und in das Verzeichnis der Installation wechseln.</p>
              <Befehl hinweis="Benutzername, Adresse und Pfad wie in den Deploy-Einstellungen (SSH_USER, SSH_HOST, DEPLOY_PATH).">
{`ssh BENUTZER@dz.wwinterface.online
cd /pfad/zur/installation`}
              </Befehl>
            </>
          ) : (
            <>
              <p>Terminal öffnen und in den Projektordner wechseln. Docker Desktop muss laufen.</p>
              <Befehl>{`cd ~/Developer/deinezeit`}</Befehl>
            </>
          )}
        </Schritt>

        <Schritt nummer={2} titel="Anfragebremse für den Messlauf abschalten">
          <p>
            Der Lasttest kommt von einer einzigen Adresse. Die Bremse würde nach
            200 Anfragen je Minute abriegeln — gemessen würde dann die Bremse
            und nicht die Anwendung. In der Datei <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">.env</code> setzen:
          </p>
          <Befehl hinweis="Danach das Backend neu starten. Im Log muss die Warnung erscheinen, dass die Bremse aus ist.">
{`RATE_LIMIT_AKTIV=false

${compose} up -d backend
${compose} logs backend | grep -i "Rate-Limiting"`}
          </Befehl>
        </Schritt>

        <Schritt nummer={3} titel="Prüfdaten anlegen">
          <p>
            Ohne Datenbestand misst der Test leere Listen. Das Skript legt 100
            Testbenutzer, 200 Kontakte, 30 Projekte und 50 Belege an — alles mit
            „Lasttest" im Namen.
          </p>
          <Befehl hinweis="Das Passwort wird abgefragt und darf nicht als Argument übergeben werden — ein „!“ darin löst in zsh sonst eine History-Expansion aus.">
{`python3 lasttest/pruefdaten.py --admin DEINE-ADMIN-MAIL`}
          </Befehl>
        </Schritt>

        <Schritt nummer={4} titel="Locust starten">
          <p>Das Messwerkzeug läuft in einem eigenen Container neben der Anwendung.</p>
          <Befehl>{`docker compose -f docker-compose.lasttest.yml up`}</Befehl>
          {amServer ? (
            <p className="text-xs text-gray-500 mt-2">
              Die Oberfläche läuft auf Port 8089 des Servers und ist bewusst
              <strong> nicht </strong> nach außen freigegeben. Leite sie über die
              bestehende SSH-Verbindung auf deinen Rechner um — dann erreichst du
              sie unter <code className="bg-gray-100 px-1 py-0.5 rounded">http://localhost:8089</code>,
              ohne einen Port zu öffnen:
            </p>
          ) : null}
          {amServer && (
            <Befehl hinweis="In einem zweiten Terminal-Fenster ausführen, während Locust läuft.">
{`ssh -L 8089:localhost:8089 BENUTZER@dz.wwinterface.online`}
            </Befehl>
          )}
        </Schritt>

        <Schritt nummer={5} titel="Messen">
          <p>
            Im Browser <a href="http://localhost:8089" target="_blank" rel="noopener noreferrer"
              className="text-primary-600 hover:underline inline-flex items-center gap-1">
              localhost:8089 <ExternalLink size={11} />
            </a> öffnen und eintragen:
          </p>
          <ul className="list-disc list-inside mt-2 space-y-1 text-sm">
            <li><strong>Number of users:</strong> 5, dann 10, 20, 100 — eine Stufe nach der anderen</li>
            <li><strong>Ramp up:</strong> 1 pro Sekunde</li>
            <li><strong>Host:</strong> <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">{ziel}</code></li>
          </ul>
          <p className="mt-2">
            Jede Stufe mindestens drei Minuten laufen lassen und zwischen den
            Stufen neu starten. Die ersten Sekunden sind Aufwärmphase und nicht
            aussagekräftig.
          </p>
        </Schritt>

        <Schritt nummer={6} titel="Ergebnis lesen">
          <p>
            Im Reiter <em>Statistics</em> zählen zwei Zahlen: die Antwortzeit bei
            95 % und die Fehlerquote. Unter 300 ms ist flüssig, über einer Sekunde
            wird es zäh. Fehler wiegen schwerer als Zeiten — eine langsame
            Anwendung ist ärgerlich, eine fehlerhafte kostet Daten.
          </p>
          <p className="mt-2">
            Wenn die grüne Linie im Diagramm unter der roten verschwindet,
            schlagen alle Anfragen fehl. Dann stimmt etwas an der Vorbereitung
            nicht, und die Zahlen bedeuten nichts.
          </p>
        </Schritt>

        <Schritt nummer={7} titel="Aufräumen">
          <p>Nicht vergessen — beides gehört zusammen:</p>
          <Befehl>
{`# 1. Bremse wieder einschalten: RATE_LIMIT_AKTIV=true in .env
${compose} up -d backend

# 2. Locust beenden
docker compose -f docker-compose.lasttest.yml down`}
          </Befehl>
          <p className="text-xs text-gray-500 mt-2">
            Die angelegten Prüfdaten (Suchbegriff „Lasttest") bleiben stehen und
            müssen von Hand entfernt werden — ein automatischer Löschlauf über
            Namensmuster wäre in einer Datenbank mit echten Daten zu gefährlich.
          </p>
        </Schritt>
      </div>

      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs text-gray-600">
        <p className="font-medium text-gray-700 mb-1">Warum es hier keinen Startknopf gibt</p>
        <p>
          Die Locust-Oberfläche hat keine eigene Anmeldung. Wäre sie über die
          Anwendung erreichbar, könnte jeder, der den Weg findet, die
          Installation lahmlegen. Deshalb läuft der Lasttest ausschließlich dort,
          wo ohnehin nur Befugte hinkommen: über SSH oder am eigenen Rechner.
          Ausführliche Fassung dieser Anleitung: <code className="bg-gray-100 px-1 py-0.5 rounded">lasttest/README.md</code>
        </p>
      </div>
    </div>
  )
}
