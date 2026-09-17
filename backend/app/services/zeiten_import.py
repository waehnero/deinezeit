"""
Zeiten-Import: Projektzeiten aus Fremdsystemen prüfen und übernehmen
====================================================================

Gleiche Bauart wie der Stammdaten-Import (``services/masterdata_import.py``):
ein Probelauf, dessen Bericht der Assistent anzeigt, dann — nach ausdrücklicher
Bestätigung — der echte Lauf. Beide Durchgänge laufen durch denselben Code,
geschrieben wird in EINER Transaktion.

Woher die Zeilen kommen, ist dem Server gleich: CSV, Excel, JSON und Kalender
(ICS) liest der Browser, ein PDF macht die KI-Schnittstelle zur Tabelle
(``services/zeiten_pdf.py``). Hier kommen immer fertig zugeordnete Zeilen an —
Schlüssel sind die Zielfelder unten, Werte der Text aus der Datei.

Beschlüsse Oliver (18.09.2026):

* **Wem gehören die Einträge?** Administratoren ordnen eine Spalte den
  Benutzern zu (Name oder E-Mail) ODER wählen einen Benutzer für die ganze
  Datei. Alle anderen importieren ausschließlich für sich selbst.
* **Nur Datum + Dauer wird beanstandet.** Ein Zeiteintrag braucht Beginn und
  Ende. Eine Uhrzeit zu erfinden hieße, Arbeitszeitnachweise zu fälschen.

Wie beim Stammdaten-Import gilt: Es wird nichts geraten. Ein unklarer Wert ist
eine beanstandete Zeile, keine stille Annahme. Das betrifft hier vor allem

* Datumsangaben mit Schrägstrich (``03/04/2026`` — 3. April oder 4. März?),
* ein Ende vor dem Beginn (Tippfehler oder Arbeit über Mitternacht?),
* Zeitprojekte und Benutzer, die es nicht oder mehrfach gibt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import zeitprojekte
from app.core.zeit import ZONE
from app.models.masterdata import EntityRecord
from app.models.user import User
from app.models.zeiterfassung import TimeEntry, TimeEntryField
from app.services.masterdata_import import (
    Beanstandung, Wertfehler, _jaNein, wert_deuten,
)

# Mehr Zeilen in einem Aufruf hält weder der Bericht im Browser noch die eine
# Transaktion sinnvoll aus. Wer mehr hat, teilt die Datei nach Jahren.
MAX_ZEILEN = 5000

# Ein einzelner Eintrag über 24 Stunden ist in aller Regel ein falsch
# gelesenes Datum (Ende im Folgemonat), kein Arbeitstag.
MAX_DAUER = timedelta(hours=24)

# Vorsilbe für frei definierte Felder (``TimeEntryField``). Ohne sie könnte ein
# Custom-Feld mit dem Schlüssel „notiz" das Kernfeld überdecken.
FELD_PRAEFIX = "feld:"

# Kernfelder. ``synonyme`` dienen nur dem Zuordnungsvorschlag im Assistenten —
# kleingeschrieben, so wie Toggl, Clockify, Kimai, Excel-Stundenzettel und der
# Kalender-Leser ihre Spalten nennen. Entschieden wird immer vom Benutzer.
KERNFELDER: List[Dict[str, Any]] = [
    dict(key="benutzer", name="Benutzer (Name oder E-Mail)", nur_admin=True,
         synonyme=["benutzer", "mitarbeiter", "mitarbeiterin", "name", "user",
                   "username", "e-mail", "email", "person", "member"]),
    dict(key="datum", name="Datum",
         synonyme=["datum", "date", "tag", "start date", "startdatum"]),
    dict(key="beginn", name="Beginn (Uhrzeit oder Datum + Uhrzeit)",
         synonyme=["beginn", "start", "von", "anfang", "start time", "startzeit",
                   "kommen", "begin", "timeinterval.start", "dtstart"]),
    dict(key="ende", name="Ende (Uhrzeit oder Datum + Uhrzeit)",
         synonyme=["ende", "end", "stop", "bis", "end time", "endzeit", "gehen",
                   "timeinterval.end", "dtend"]),
    dict(key="pause", name="Pause (Minuten oder 0:30)",
         synonyme=["pause", "pause (min)", "pausen", "break", "pause_minutes"]),
    dict(key="zeitprojekt", name="Zeitprojekt (Name)",
         synonyme=["zeitprojekt", "projekt", "project", "project.name",
                   "projektname", "kunde / projekt"]),
    dict(key="notiz", name="Notiz",
         synonyme=["notiz", "beschreibung", "description", "tätigkeit",
                   "taetigkeit", "bemerkung", "kommentar", "note", "notes",
                   "titel", "summary", "text"]),
    dict(key="verrechenbar", name="Verrechenbar (ja/nein)",
         synonyme=["verrechenbar", "billable", "abrechenbar", "fakturierbar"]),
]


@dataclass
class ZeitenBericht:
    geprueft: int = 0
    anlegen: int = 0
    angelegt: int = 0
    uebersprungen: int = 0
    minuten_gesamt: int = 0          # Netto-Minuten der übernehmbaren Zeilen
    beanstandungen: List[Beanstandung] = dc_field(default_factory=list)


def zielfelder(db: Session, ist_admin: bool) -> List[Dict[str, Any]]:
    """Alle Felder, auf die eine Spalte zugeordnet werden kann."""
    felder = [dict(key=f["key"], name=f["name"], synonyme=f["synonyme"])
              for f in KERNFELDER if ist_admin or not f.get("nur_admin")]
    for feld in (db.query(TimeEntryField)
                 .order_by(TimeEntryField.sort_order).all()):
        felder.append(dict(key=FELD_PRAEFIX + feld.key, name=feld.name,
                           synonyme=[feld.name.lower(), feld.key.lower()]))
    return felder


# ── Werte deuten ─────────────────────────────────────────────────────────────

_PUNKT_DATUM = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d-%m-%Y")
_UHRZEIT = ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p")
_SCHRAEGSTRICH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _datum(text: str) -> date:
    text = text.strip()
    for fmt in _PUNKT_DATUM:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    treffer = _SCHRAEGSTRICH.match(text)
    if treffer:
        a, b, jahr = (int(x) for x in treffer.groups())
        # 25/03/2026 kann nur TT/MM sein, 03/25/2026 nur MM/TT. Bei 03/04/2026
        # ist beides möglich — und ein vertauschter Tag fällt in einem
        # Arbeitszeitnachweis niemandem mehr auf.
        if a > 12 >= b:
            tag, monat = a, b
        elif b > 12 >= a:
            tag, monat = b, a
        else:
            raise Wertfehler("Datum mit Schrägstrich ist nicht eindeutig "
                             "(TT/MM oder MM/TT?) — bitte als 31.12.2026 "
                             "oder 2026-12-31 liefern")
        try:
            return date(jahr, monat, tag)
        except ValueError as e:
            raise Wertfehler("kein gültiges Datum") from e
    raise Wertfehler("kein Datum (erwartet z.B. 31.12.2026)")


def _uhrzeit(text: str) -> Optional[time]:
    roh = re.sub(r"\s*uhr$", "", text.strip(), flags=re.IGNORECASE).upper()
    for fmt in _UHRZEIT:
        try:
            return datetime.strptime(roh, fmt).time()
        except ValueError:
            continue
    return None


def _mit_zone(wert: datetime) -> datetime:
    """Angaben ohne Zeitzone sind Ortszeit der Installation (``TZ``)."""
    return wert if wert.tzinfo else wert.replace(tzinfo=ZONE)


def _zeitpunkt(text: str, tag: Optional[date]) -> datetime:
    """„08:15" (+ Datumsspalte), „31.12.2026 08:15" oder ISO 8601."""
    text = text.strip()

    uhr = _uhrzeit(text)
    if uhr is not None:
        if tag is None:
            raise Wertfehler("Uhrzeit ohne Datum — bitte auch die "
                             "Datumsspalte zuordnen")
        return _mit_zone(datetime.combine(tag, uhr))

    # ISO 8601, auch mit „Z" (Toggl, Clockify, Kalender in UTC)
    try:
        iso = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if isinstance(iso, datetime) and ("T" in text or " " in text):
            return _mit_zone(iso)
    except ValueError:
        pass

    # „31.12.2026 08:15" — Datum und Uhrzeit getrennt deuten, damit dieselben
    # Regeln gelten wie für die einzelnen Spalten.
    teile = text.replace(",", " ").split(None, 1)
    if len(teile) == 2:
        uhr = _uhrzeit(teile[1])
        if uhr is not None:
            return _mit_zone(datetime.combine(_datum(teile[0]), uhr))

    raise Wertfehler("keine Uhrzeit (erwartet z.B. 08:15 oder 31.12.2026 08:15)")


def _pause(text: str) -> int:
    text = text.strip().lower()
    text = re.sub(r"\s*(min\.?|minuten)$", "", text)
    if re.fullmatch(r"\d+", text):
        return int(text)
    treffer = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text)
    if treffer:
        return int(treffer.group(1)) * 60 + int(treffer.group(2))
    raise Wertfehler("Pause in ganzen Minuten oder als 0:30 angeben")


def _text(wert: Any) -> str:
    return "" if wert is None else str(wert).strip()


# ── Import ───────────────────────────────────────────────────────────────────

class ZeitenImport:

    def _benutzer_suchen(self, db: Session, text: str,
                         zwischenspeicher: Dict[str, Any]) -> User:
        schluessel = text.lower()
        if schluessel not in zwischenspeicher:
            zwischenspeicher[schluessel] = (
                db.query(User)
                .filter((func.lower(User.email) == schluessel)
                        | (func.lower(User.full_name) == schluessel))
                .limit(2).all())
        treffer = zwischenspeicher[schluessel]
        if not treffer:
            raise Wertfehler("kein Benutzer mit diesem Namen oder dieser E-Mail")
        if len(treffer) > 1:
            raise Wertfehler("mehrere Benutzer mit diesem Namen — bitte die "
                             "E-Mail-Adresse verwenden")
        return treffer[0]

    def _projekt_suchen(self, db: Session, typ, text: str,
                        zwischenspeicher: Dict[str, Any]) -> Tuple[UUID, str, Optional[str]]:
        if typ is None:
            raise Wertfehler("es gibt noch keine Zeitprojekte")
        schluessel = text.lower()
        if schluessel not in zwischenspeicher:
            zwischenspeicher[schluessel] = (
                db.query(EntityRecord)
                .filter(EntityRecord.entity_type_id == typ.id,
                        EntityRecord.archived_at.is_(None),
                        func.lower(EntityRecord.display_name) == schluessel)
                .limit(2).all())
        treffer = zwischenspeicher[schluessel]
        if not treffer:
            raise Wertfehler("Zeitprojekt nicht gefunden — zuerst unter "
                             "Zeiterfassung → Zeitprojekte anlegen oder importieren")
        if len(treffer) > 1:
            raise Wertfehler("Zeitprojekt mehrfach vorhanden — nicht eindeutig")
        satz = treffer[0]
        kontakt = None
        # Derselbe Weg wie im Erfassungsdialog (ZeitprojektSuche.jsx)
        for feld in ("kontakt", "kunde"):
            wert = (satz.data or {}).get(feld)
            if isinstance(wert, dict) and wert.get("display_name"):
                kontakt = wert["display_name"]
                break
        return satz.id, satz.display_name, kontakt

    def durchfuehren(self, db: Session, zeilen: List[Dict[str, Any]],
                     aktueller_benutzer: User, ist_admin: bool,
                     fixer_benutzer_id: Optional[UUID] = None,
                     probelauf: bool = True,
                     fehlerhafte_ueberspringen: bool = False) -> ZeitenBericht:
        if len(zeilen) > MAX_ZEILEN:
            raise ValueError(f"Höchstens {MAX_ZEILEN} Zeilen je Import — bitte "
                             "die Datei aufteilen (z.B. nach Jahren)")

        hat_benutzerspalte = any("benutzer" in z for z in zeilen)
        if not ist_admin and (hat_benutzerspalte or (
                fixer_benutzer_id and fixer_benutzer_id != aktueller_benutzer.id)):
            raise PermissionError("Zeiten für andere Benutzer darf nur ein "
                                  "Administrator importieren")

        fixer_benutzer = aktueller_benutzer
        if fixer_benutzer_id and fixer_benutzer_id != aktueller_benutzer.id:
            fixer_benutzer = db.query(User).filter(User.id == fixer_benutzer_id).first()
            if not fixer_benutzer:
                raise ValueError("Der gewählte Benutzer existiert nicht")

        felder = {FELD_PRAEFIX + f.key: f for f in db.query(TimeEntryField).all()}
        projekt_typ = zeitprojekte.typ_holen(db)
        benutzer_cache: Dict[str, Any] = {}
        projekt_cache: Dict[str, Any] = {}

        bericht = ZeitenBericht()
        vorgemerkt: List[Tuple[int, Dict[str, Any]]] = []

        for nummer, zeile in enumerate(zeilen, start=1):
            bericht.geprueft += 1
            fehler: List[Beanstandung] = []

            def beanstanden(feld: Optional[str], wert: Any, grund: str) -> None:
                fehler.append(Beanstandung(zeile=nummer, feld=feld,
                                           wert=_text(wert), grund=grund))

            werte: Dict[str, Any] = dict(user_id=fixer_benutzer.id, pause_minutes=0,
                                         billable=True, note=None, data={},
                                         project_id=None, project_name=None,
                                         contact_name=None)

            # Benutzer
            if "benutzer" in zeile:
                name = _text(zeile["benutzer"])
                if not name:
                    beanstanden("Benutzer", "", "Benutzer fehlt")
                else:
                    try:
                        werte["user_id"] = self._benutzer_suchen(
                            db, name, benutzer_cache).id
                    except Wertfehler as e:
                        beanstanden("Benutzer", name, str(e))

            # Datum, Beginn, Ende
            tag: Optional[date] = None
            if _text(zeile.get("datum")):
                try:
                    tag = _datum(_text(zeile["datum"]))
                except Wertfehler as e:
                    beanstanden("Datum", zeile["datum"], str(e))

            beginn_text, ende_text = _text(zeile.get("beginn")), _text(zeile.get("ende"))
            beginn = ende = None
            datum_kaputt = any(b.feld == "Datum" for b in fehler)
            if not beginn_text and not ende_text:
                beanstanden(None, "", "Beginn und Ende fehlen — Einträge nur mit "
                                      "Datum und Dauer werden nicht übernommen")
            elif not beginn_text:
                beanstanden("Beginn", "", "Beginn fehlt")
            elif not ende_text:
                beanstanden("Ende", "", "Ende fehlt — laufende Einträge lassen "
                                        "sich nicht importieren")
            elif not datum_kaputt:      # sonst zweimal dieselbe Ursache melden
                for feldname, text in (("Beginn", beginn_text), ("Ende", ende_text)):
                    try:
                        wert = _zeitpunkt(text, tag)
                    except Wertfehler as e:
                        beanstanden(feldname, text, str(e))
                        continue
                    if feldname == "Beginn":
                        beginn = wert
                    else:
                        ende = wert

            # Pause
            if _text(zeile.get("pause")):
                try:
                    werte["pause_minutes"] = _pause(_text(zeile["pause"]))
                except Wertfehler as e:
                    beanstanden("Pause", zeile["pause"], str(e))

            if beginn and ende:
                if ende <= beginn:
                    beanstanden("Ende", ende_text,
                                "Ende liegt nicht nach dem Beginn — bei Arbeit über "
                                "Mitternacht Beginn und Ende mit Datum liefern")
                elif ende - beginn > MAX_DAUER:
                    beanstanden("Ende", ende_text, "Eintrag dauert länger als 24 Stunden")
                elif werte["pause_minutes"] * 60 >= (ende - beginn).total_seconds():
                    beanstanden("Pause", zeile.get("pause"),
                                "Pause ist so lang wie der ganze Eintrag oder länger")

            # Zeitprojekt
            if _text(zeile.get("zeitprojekt")):
                try:
                    (werte["project_id"], werte["project_name"],
                     werte["contact_name"]) = self._projekt_suchen(
                        db, projekt_typ, _text(zeile["zeitprojekt"]), projekt_cache)
                except Wertfehler as e:
                    beanstanden("Zeitprojekt", zeile["zeitprojekt"], str(e))

            # Notiz, Verrechenbar
            werte["note"] = _text(zeile.get("notiz")) or None
            if _text(zeile.get("verrechenbar")):
                try:
                    werte["billable"] = _jaNein(_text(zeile["verrechenbar"]))
                except Wertfehler as e:
                    beanstanden("Verrechenbar", zeile["verrechenbar"], str(e))

            # Frei definierte Felder
            for schluessel, rohwert in zeile.items():
                feld = felder.get(schluessel)
                if not feld:
                    continue
                try:
                    werte["data"][feld.key] = wert_deuten(rohwert, feld, db)
                except Wertfehler as e:
                    beanstanden(feld.name, rohwert, str(e))

            if fehler:
                bericht.beanstandungen.extend(fehler)
                continue
            werte["started_at"], werte["ended_at"] = beginn, ende
            vorgemerkt.append((nummer, werte))

        # ── Doppelte erkennen ────────────────────────────────────────────────
        # Derselbe Benutzer mit demselben Beginn UND Ende ist derselbe Eintrag:
        # Wer eine Datei versehentlich zweimal einspielt, verdoppelt sonst die
        # Arbeitszeit eines ganzen Jahres, und das fällt erst bei der
        # Abrechnung auf. Der Bestand wird je Benutzer in einer Abfrage geholt.
        bestand: Dict[UUID, set] = {}
        for benutzer_id in {w["user_id"] for _, w in vorgemerkt}:
            eigene = [w for _, w in vorgemerkt if w["user_id"] == benutzer_id]
            von = min(w["started_at"] for w in eigene)
            bis = max(w["started_at"] for w in eigene)
            bestand[benutzer_id] = {
                (s, e) for s, e in db.query(TimeEntry.started_at, TimeEntry.ended_at)
                .filter(TimeEntry.user_id == benutzer_id,
                        TimeEntry.started_at >= von,
                        TimeEntry.started_at <= bis).all()}

        gesehen: Dict[tuple, int] = {}
        uebernehmen: List[Dict[str, Any]] = []
        for nummer, werte in vorgemerkt:
            paar = (werte["started_at"], werte["ended_at"])
            marke = (werte["user_id"],) + paar
            if marke in gesehen:
                bericht.beanstandungen.append(Beanstandung(
                    zeile=nummer, feld=None, wert="",
                    grund=f"derselbe Eintrag steht schon in Zeile {gesehen[marke]}"))
                continue
            gesehen[marke] = nummer
            if paar in bestand[werte["user_id"]]:
                bericht.beanstandungen.append(Beanstandung(
                    zeile=nummer, feld=None, wert="",
                    grund="diesen Eintrag gibt es schon (gleicher Benutzer, "
                          "gleicher Beginn, gleiches Ende)"))
                continue
            bericht.anlegen += 1
            sekunden = (werte["ended_at"] - werte["started_at"]).total_seconds()
            bericht.minuten_gesamt += max(0, int(sekunden // 60) - werte["pause_minutes"])
            uebernehmen.append(werte)

        bericht.beanstandungen.sort(key=lambda b: b.zeile)

        if probelauf:
            return bericht
        if bericht.beanstandungen and not fehlerhafte_ueberspringen:
            # Der Aufrufer hat den Bericht gesehen und nicht entschieden —
            # dann wird nichts geschrieben.
            return bericht

        for werte in uebernehmen:
            db.add(TimeEntry(**werte))
            bericht.angelegt += 1
        bericht.uebersprungen = len({b.zeile for b in bericht.beanstandungen})
        db.commit()
        return bericht


zeiten_import = ZeitenImport()
