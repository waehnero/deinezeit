/**
 * Zeitprojekte – Stammsätze, auf die Projektzeiten gebucht werden.
 *
 * Die Seite liegt im Menü der Zeiterfassung, zeigt aber weiterhin den
 * Stammdaten-Baukasten (eigene Felder, Import/Export, Anhänge, Stundenkonten).
 * Deshalb rendert sie ``MasterDataDetail`` mit festem Slug, statt den Aufbau
 * ein zweites Mal nachzubauen — zwei Listen für dieselben Datensätze würden
 * mit jeder Änderung weiter auseinanderlaufen.
 */
import MasterDataDetail from './MasterDataDetail'
import { ZEITPROJEKTE_SLUG } from '../utils/zeitprojekte'

export default function ZeitprojektePage() {
  return <MasterDataDetail festerSlug={ZEITPROJEKTE_SLUG} zurueckZu="/zeiterfassung" />
}
