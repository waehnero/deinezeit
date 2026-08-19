"""
Stammdaten-Import: prüfen, abgleichen, schreiben
================================================

Der Import läuft in zwei Durchgängen über dieselbe Prüfung: erst als Probelauf
(``dry_run``), dessen Bericht der Assistent anzeigt, dann — nach ausdrücklicher
Bestätigung — als echter Lauf. Beide Durchgänge nutzen bewusst denselben Code:
Ein Bericht, der etwas anderes prüft als der spätere Schreibvorgang, ist
schlimmer als gar keiner, weil man ihm glaubt.

Werte kommen als Text aus CSV oder Excel und werden je Feldtyp gedeutet. Die
Regeln sind auf österreichische Dateien ausgelegt (Datum ``31.12.2026``, Zahl
``1.234,56``), akzeptieren aber auch die maschinenüblichen Schreibweisen.

Was hier ausdrücklich NICHT passiert: raten. Ein unklarer Wert wird zur
beanstandeten Zeile, nicht zu einer stillen Null. Wer 2000 Zeilen importiert,
merkt sonst erst Monate später, dass jedes fehlerhafte Datum zum 01.01.1970
geworden ist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.masterdata import EntityRecord, EntityType, FieldDefinition
from app.services.masterdata_service import masterdata_service

# Datumsformate in der Reihenfolge, in der sie probiert werden. Das deutsche
# Format steht vorn: In einer Datei aus Excel-AT ist „01.02.2026“ der 1. Februar.
DATUMSFORMATE = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y", "%d-%m-%Y")

WAHR = {"ja", "j", "true", "wahr", "x", "1", "yes", "y"}
FALSCH = {"nein", "n", "false", "falsch", "0", "no", ""}

EMAIL_MUSTER = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


@dataclass
class Beanstandung:
    """Eine Zeile, die so nicht geschrieben werden kann."""
    zeile: int              # 1-basiert, wie in der Tabelle gezählt
    feld: Optional[str]     # Feldname (Anzeigename), None = ganze Zeile
    wert: str
    grund: str


@dataclass
class Importbericht:
    geprueft: int = 0
    anlegen: int = 0
    aktualisieren: int = 0
    angelegt: int = 0
    aktualisiert: int = 0
    uebersprungen: int = 0
    beanstandungen: List[Beanstandung] = dc_field(default_factory=list)

    @property
    def sauber(self) -> bool:
        return not self.beanstandungen


# ── Werte deuten ─────────────────────────────────────────────────────────────

class Wertfehler(ValueError):
    """Ein Wert passt nicht zum Feldtyp — mit einer Begründung im Klartext."""


def _zahl(wert: str) -> float:
    """„1.234,56“ und „1234.56“ ergeben beide 1234.56.

    Die Unterscheidung ist nicht raten, sondern eindeutig: Steht ein Komma im
    Text, ist es das Dezimaltrennzeichen und der Punkt trennt Tausender.
    """
    text = wert.strip().replace(" ", "").replace("€", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        raise Wertfehler("keine Zahl")


def _datum(wert: str) -> str:
    text = wert.strip()
    for fmt in DATUMSFORMATE:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise Wertfehler("kein Datum (erwartet z.B. 31.12.2026)")


def _jaNein(wert: str) -> bool:
    text = wert.strip().lower()
    if text in WAHR:
        return True
    if text in FALSCH:
        return False
    raise Wertfehler("kein Ja/Nein-Wert")


def _auswahl(wert: str, feld: FieldDefinition) -> str:
    """Auswahlfeld: Groß-/Kleinschreibung egal, gespeichert wird die Vorgabe.

    Sonst stehen „Kunde“ und „kunde“ nebeneinander in den Filtern.
    """
    text = wert.strip()
    optionen = feld.options or []
    for option in optionen:
        if str(option).strip().lower() == text.lower():
            return str(option)
    raise Wertfehler(f"nicht in der Auswahlliste ({', '.join(map(str, optionen))})")


def _verknuepfung(wert: str, feld: FieldDefinition, db: Session) -> str:
    """Verknüpfung über den Anzeigenamen des Zieldatensatzes auflösen.

    In einer Tabelle steht „Musterbau GmbH“, nicht die UUID. Mehrdeutige Namen
    werden beanstandet statt willkürlich aufgelöst — bei zwei gleichnamigen
    Kunden wäre jede Wahl falsch.
    """
    ziel = masterdata_service.get_entity_type(db, feld.linked_type_slug or "")
    if not ziel:
        raise Wertfehler("Ziel-Typ der Verknüpfung existiert nicht mehr")

    text = wert.strip()
    treffer = (db.query(EntityRecord)
               .filter(EntityRecord.entity_type_id == ziel.id,
                       EntityRecord.archived_at.is_(None),
                       EntityRecord.display_name.ilike(text))
               .limit(2).all())
    if not treffer:
        raise Wertfehler(f"in „{ziel.name}“ nicht gefunden")
    if len(treffer) > 1:
        raise Wertfehler(f"in „{ziel.name}“ mehrfach vorhanden — nicht eindeutig")
    return str(treffer[0].id)


def wert_deuten(wert: Any, feld: FieldDefinition, db: Session) -> Any:
    """Einen Tabellenwert in die Form bringen, in der er gespeichert wird."""
    text = "" if wert is None else str(wert).strip()

    if text == "":
        if feld.is_required:
            raise Wertfehler("Pflichtfeld ist leer")
        return "" if feld.field_type != "checkbox" else False

    if feld.field_type == "number":
        return _zahl(text)
    if feld.field_type == "date":
        return _datum(text)
    if feld.field_type == "checkbox":
        return _jaNein(text)
    if feld.field_type == "dropdown":
        return _auswahl(text, feld)
    if feld.field_type == "relation":
        return _verknuepfung(text, feld, db)
    if feld.field_type == "email":
        if not EMAIL_MUSTER.match(text):
            raise Wertfehler("keine gültige E-Mail-Adresse")
        return text
    if feld.field_type == "url":
        if not text.lower().startswith(("http://", "https://")):
            # Kein stilles Voranstellen: „www.beispiel.at“ und
            # „beispiel.at/pfad“ sind beide plausibel, aber nicht dasselbe.
            raise Wertfehler("Adresse muss mit http:// oder https:// beginnen")
        return text

    # text, textarea, phone: unverändert übernehmen
    return text


# ── Import ───────────────────────────────────────────────────────────────────

class MasterDataImport:

    def _felder(self, entity_type: EntityType) -> Dict[str, FieldDefinition]:
        return {f.key: f for f in entity_type.fields}

    def _vorhandene_suchen(self, db: Session, entity_type: EntityType,
                           feldschluessel: str, wert: Any) -> Optional[EntityRecord]:
        if wert in (None, ""):
            return None
        return (db.query(EntityRecord)
                .filter(EntityRecord.entity_type_id == entity_type.id,
                        EntityRecord.archived_at.is_(None),
                        EntityRecord.data[feldschluessel].astext == str(wert))
                .first())

    def durchfuehren(self, db: Session, entity_type: EntityType,
                     zeilen: List[Dict[str, Any]],
                     benutzer_id: Optional[UUID] = None,
                     abgleichsfeld: Optional[str] = None,
                     probelauf: bool = True,
                     fehlerhafte_ueberspringen: bool = False) -> Importbericht:
        """Zeilen prüfen und — außerhalb des Probelaufs — schreiben.

        ``abgleichsfeld``: Schlüssel eines Feldes. Existiert ein Datensatz mit
        demselben Wert, wird er aktualisiert statt ein zweiter angelegt.

        Geschrieben wird erst, wenn alle Zeilen geprüft sind. Ein Abbruch
        mittendrin hinterlässt sonst einen halb importierten Bestand, den
        niemand mehr auseinandersortieren kann.
        """
        felder = self._felder(entity_type)
        bericht = Importbericht()

        if abgleichsfeld and abgleichsfeld not in felder:
            raise ValueError(f"Abgleichsfeld „{abgleichsfeld}“ gibt es in "
                             f"„{entity_type.name}“ nicht")

        # (geprüfte Daten, vorhandener Datensatz oder None)
        vorgemerkt: List[tuple] = []
        # Doppelte Schlüsselwerte innerhalb der Datei: Ohne diese Prüfung
        # gewinnt beim Abgleich die letzte Zeile, und die vorherigen
        # verschwinden lautlos.
        gesehen: Dict[str, int] = {}

        for nummer, zeile in enumerate(zeilen, start=1):
            bericht.geprueft += 1
            daten: Dict[str, Any] = {}
            zeilenfehler: List[Beanstandung] = []

            for schluessel, rohwert in zeile.items():
                feld = felder.get(schluessel)
                if not feld:
                    continue  # nicht zugeordnete Spalten sind kein Fehler
                try:
                    daten[schluessel] = wert_deuten(rohwert, feld, db)
                except Wertfehler as fehler:
                    zeilenfehler.append(Beanstandung(
                        zeile=nummer, feld=feld.name,
                        wert="" if rohwert is None else str(rohwert),
                        grund=str(fehler)))

            # Pflichtfelder, die in der Datei gar keine Spalte haben
            for schluessel, feld in felder.items():
                if feld.is_required and schluessel not in daten:
                    zeilenfehler.append(Beanstandung(
                        zeile=nummer, feld=feld.name, wert="",
                        grund="Pflichtfeld fehlt in der Datei"))

            vorhanden = None
            if abgleichsfeld and not zeilenfehler:
                schluesselwert = daten.get(abgleichsfeld, "")
                if schluesselwert in (None, ""):
                    zeilenfehler.append(Beanstandung(
                        zeile=nummer, feld=felder[abgleichsfeld].name, wert="",
                        grund="Abgleichsfeld ist leer"))
                else:
                    text = str(schluesselwert)
                    if text in gesehen:
                        zeilenfehler.append(Beanstandung(
                            zeile=nummer, feld=felder[abgleichsfeld].name,
                            wert=text,
                            grund=f"kommt in der Datei schon in Zeile "
                                  f"{gesehen[text]} vor"))
                    else:
                        gesehen[text] = nummer
                        vorhanden = self._vorhandene_suchen(
                            db, entity_type, abgleichsfeld, text)

            if zeilenfehler:
                bericht.beanstandungen.extend(zeilenfehler)
                continue

            if vorhanden is not None:
                bericht.aktualisieren += 1
            else:
                bericht.anlegen += 1
            vorgemerkt.append((daten, vorhanden))

        if probelauf:
            return bericht

        if bericht.beanstandungen and not fehlerhafte_ueberspringen:
            # Der Aufrufer hat den Bericht gesehen und trotzdem nicht
            # entschieden — dann wird nichts geschrieben.
            return bericht

        for daten, vorhanden in vorgemerkt:
            if vorhanden is not None:
                # Nur die zugeordneten Spalten überschreiben: Felder, die in
                # der Datei fehlen, behalten ihren gepflegten Wert.
                zusammengefuehrt = dict(vorhanden.data or {})
                zusammengefuehrt.update(daten)
                vorhanden.data = zusammengefuehrt
                vorhanden.display_name = masterdata_service._extract_display_name(
                    entity_type, zusammengefuehrt)
                vorhanden.updated_by = benutzer_id
                bericht.aktualisiert += 1
            else:
                db.add(EntityRecord(
                    entity_type_id=entity_type.id,
                    data=daten,
                    display_name=masterdata_service._extract_display_name(
                        entity_type, daten),
                    created_by=benutzer_id,
                    updated_by=benutzer_id,
                ))
                bericht.angelegt += 1

        bericht.uebersprungen = len({b.zeile for b in bericht.beanstandungen})
        # Ein einziges Commit für den ganzen Lauf — 2000 Einzel-Commits dauern
        # nicht nur, sie lassen sich auch nicht mehr zurücknehmen.
        db.commit()
        return bericht


masterdata_import = MasterDataImport()
