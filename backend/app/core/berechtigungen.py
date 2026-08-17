"""
Rechtemodell: Gruppen, Rechte je Modul, individuelle Ausnahmen
==============================================================

Ausgangslage (bis Migration 0055)
---------------------------------
Es gab nur ``users.allowed_modules`` — eine JSON-Liste erlaubter Module, rein
an/aus, je Benutzer einzeln gepflegt. Zwei Dinge fehlten dadurch:

* **Kein Unterschied zwischen Ansehen und Ändern.** Wer Rechnungen sehen
  durfte, durfte sie auch stornieren. Die einzige Abhilfe war, das ganze Modul
  zu sperren.
* **Keine Bündelung.** Bei zwölf Mitarbeitern mit gleicher Tätigkeit musste
  dieselbe Kombination zwölfmal geklickt werden — und beim dreizehnten fiel
  niemandem auf, dass ein Häkchen fehlte.

Modell ab Migration 0055 (Beschluss 17.08.2026)
-----------------------------------------------
Je Modul drei Rechte und ein Umfang:

* ``lesen`` — Datensätze ansehen
* ``schreiben`` — anlegen und ändern
* ``loeschen`` — löschen bzw. archivieren
* ``umfang`` — ``eigene`` oder ``alle``

Der **Umfang** ist die Antwort auf den häufigsten Fall im Betrieb: Ein
Mitarbeiter soll seine eigenen Zeiten sehen und ändern, nicht die der Kollegen.
Ohne diese Stufe bräuchte jede solche Regel eigenen Code an jedem Endpunkt.
Er gilt einheitlich für alle drei Rechte eines Moduls — getrennte Umfänge für
Lesen und Löschen wären in der Oberfläche kaum noch erklärbar und ergeben
fachlich wenig ("fremde sehen, aber nur eigene löschen" ist der Normalfall und
folgt schon aus ``loeschen``).

Rechte kommen aus den **Gruppen** eines Benutzers als Vereinigungsmenge; darauf
werden **individuelle Ausnahmen** angewendet, die einzelne Rechte zusätzlich
erlauben oder entziehen. Ein Entzug gewinnt immer — sonst wäre eine Ausnahme
keine.

Die Rolle ``admin`` bleibt als Notausgang bestehen und hat immer alles. Ohne
sie könnte eine unglückliche Gruppenänderung die Installation aussperren, und
niemand käme mehr an die Rechteverwaltung.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.core.modules import MODULE_KEYS, MODULE_LABELS
from app.models.user import User, UserRole

# ── Rechtearten ──────────────────────────────────────────────────────────────
LESEN = "lesen"
SCHREIBEN = "schreiben"
LOESCHEN = "loeschen"
RECHTE = (LESEN, SCHREIBEN, LOESCHEN)

RECHT_LABELS = {
    LESEN: "Ansehen",
    SCHREIBEN: "Anlegen und ändern",
    LOESCHEN: "Löschen",
}

# ── Umfang ───────────────────────────────────────────────────────────────────
UMFANG_EIGENE = "eigene"
UMFANG_ALLE = "alle"
UMFAENGE = (UMFANG_EIGENE, UMFANG_ALLE)

UMFANG_LABELS = {
    UMFANG_EIGENE: "Nur eigene Datensätze",
    UMFANG_ALLE: "Alle Datensätze",
}

#: Module, in denen der Umfang überhaupt eine Wirkung hat — nämlich dort, wo
#: Datensätze einer Person zugeordnet sind. Bei den übrigen wäre der Schalter
#: eine leere Versprechung in der Oberfläche: Ein Kontakt in den Stammdaten
#: „gehört" niemandem, ein Kontenplan schon gar nicht.
UMFANG_RELEVANT = frozenset({"zeiterfassung", "aufgaben", "projekte", "postecke"})

#: Module ohne eigene Datensätze. Hier gibt es nur ``lesen`` („darf die Seite
#: sehen"); Häkchen für Schreiben und Löschen wären sinnlos.
NUR_LESEN = frozenset({"dashboard"})


def rechte_fuer_modul(modul: str) -> tuple[str, ...]:
    """Welche Rechte für dieses Modul überhaupt vergeben werden können."""
    return (LESEN,) if modul in NUR_LESEN else RECHTE


def leeres_rechteblatt() -> dict:
    """Alle Module ohne jedes Recht — Ausgangspunkt für eine neue Gruppe."""
    return {
        modul: {
            **{recht: False for recht in rechte_fuer_modul(modul)},
            "umfang": UMFANG_EIGENE,
        }
        for modul in MODULE_KEYS
    }


def volles_rechteblatt() -> dict:
    """Alle Rechte auf allen Modulen (Vorlage für die Administratorengruppe)."""
    return {
        modul: {
            **{recht: True for recht in rechte_fuer_modul(modul)},
            "umfang": UMFANG_ALLE,
        }
        for modul in MODULE_KEYS
    }


def blatt_bereinigen(rohdaten: Optional[dict]) -> dict:
    """Eingehende Rechteangaben auf das erlaubte Raster zwingen.

    Unbekannte Module und Rechte werden verworfen, fehlende ergänzt. Das ist
    nicht Förmlichkeit: Die Rechte liegen als JSONB in der Datenbank, es gibt
    also keine Spaltenprüfung, die einen Tippfehler auffangen würde. Ein
    ``"loschen": true`` (ohne e) wäre sonst ein Recht, das niemand vergeben hat
    und das niemandem auffällt.
    """
    blatt = leeres_rechteblatt()
    if not isinstance(rohdaten, dict):
        return blatt

    for modul, werte in rohdaten.items():
        if modul not in MODULE_KEYS or not isinstance(werte, dict):
            continue
        for recht in rechte_fuer_modul(modul):
            blatt[modul][recht] = bool(werte.get(recht, False))
        umfang = werte.get("umfang")
        if umfang in UMFAENGE:
            blatt[modul]["umfang"] = umfang
    return blatt


def _leseweg_ergaenzen(blatt: dict) -> dict:
    """Schreiben oder Löschen ohne Lesen gibt es nicht.

    Ein Modul ändern zu dürfen, ohne es zu sehen, ist keine sinnvolle
    Kombination — man käme an kein Formular. Statt das in der Oberfläche zu
    verbieten (und es an anderer Stelle wieder zu vergessen), wird es hier
    zurechtgezogen.
    """
    for modul, werte in blatt.items():
        if werte.get(SCHREIBEN) or werte.get(LOESCHEN):
            werte[LESEN] = True
    return blatt


def blaetter_vereinigen(blaetter: Iterable[dict]) -> dict:
    """Vereinigungsmenge mehrerer Rechteblätter (mehrere Gruppen).

    Rechte addieren sich, und beim Umfang gewinnt die weitere Angabe: Wer über
    eine Gruppe „alle" hat, verliert das nicht dadurch, dass er zusätzlich in
    einer Gruppe mit „nur eigene" ist. Andernfalls würde das Hinzufügen einer
    Gruppe Rechte wegnehmen — für den Administrator nicht nachvollziehbar.
    """
    ergebnis = leeres_rechteblatt()
    for blatt in blaetter:
        sauber = blatt_bereinigen(blatt)
        for modul, werte in sauber.items():
            for recht in rechte_fuer_modul(modul):
                if werte.get(recht):
                    ergebnis[modul][recht] = True
            if werte.get("umfang") == UMFANG_ALLE:
                ergebnis[modul]["umfang"] = UMFANG_ALLE
    return ergebnis


def ausnahmen_anwenden(blatt: dict, ausnahmen: Optional[dict]) -> dict:
    """Individuelle Ausnahmen auf das Gruppenergebnis anwenden.

    Format (nur die abweichenden Angaben, alles andere bleibt unberührt)::

        {"verkauf": {"loeschen": false}, "stammdaten": {"schreiben": true}}

    ``false`` entzieht ein Recht, das die Gruppe gewährt, ``true`` gewährt eines
    zusätzlich. Ein Entzug ist damit stärker als jede Gruppenzugehörigkeit —
    sonst könnte man einem einzelnen Mitarbeiter nichts wegnehmen, ohne ihn aus
    der Gruppe zu werfen und damit alles andere mit zu verlieren.
    """
    if not isinstance(ausnahmen, dict):
        return blatt

    for modul, werte in ausnahmen.items():
        if modul not in blatt or not isinstance(werte, dict):
            continue
        for recht in rechte_fuer_modul(modul):
            if recht in werte:
                blatt[modul][recht] = bool(werte[recht])
        if werte.get("umfang") in UMFAENGE:
            blatt[modul]["umfang"] = werte["umfang"]
    return blatt


def effektive_rechte(user: User) -> dict:
    """Das maßgebliche Rechteblatt eines Benutzers.

    Reihenfolge: Gruppen vereinigen → Ausnahmen anwenden → Leseweg ergänzen.
    Administratoren bekommen ohne Umweg alles.
    """
    if user.role == UserRole.admin:
        return volles_rechteblatt()

    gruppen_blaetter = [g.rechte for g in getattr(user, "groups", []) or []]

    # Rückwärtskompatibilität: Solange ein Benutzer keiner Gruppe angehört,
    # gilt weiter sein altes allowed_modules. Ohne diesen Weg stünde jeder
    # ohne Gruppe unmittelbar nach dem Einspielen der Migration vor einer
    # leeren Anwendung — und zwar genau dann, wenn die Übernahme aus irgendeinem
    # Grund nicht durchgelaufen ist.
    if not gruppen_blaetter:
        gruppen_blaetter = [_aus_allowed_modules(user.allowed_modules)]

    blatt = blaetter_vereinigen(gruppen_blaetter)
    blatt = ausnahmen_anwenden(blatt, getattr(user, "permission_overrides", None))
    return _leseweg_ergaenzen(blatt)


def _aus_allowed_modules(allowed: Optional[list]) -> dict:
    """Altes Format in ein Rechteblatt übersetzen.

    ``NULL`` bedeutete „alle Module erlaubt". Die alten Rechte kannten kein
    Lesen/Schreiben-Gefälle, also werden alle drei Rechte gesetzt: Ein Umstieg
    darf niemandem etwas wegnehmen, was er vorher konnte. Beim Umfang gilt
    dasselbe — vorher gab es keine Einschränkung auf eigene Datensätze.
    """
    if allowed is None:
        return volles_rechteblatt()

    blatt = leeres_rechteblatt()
    for modul in allowed:
        if modul in blatt:
            for recht in rechte_fuer_modul(modul):
                blatt[modul][recht] = True
            blatt[modul]["umfang"] = UMFANG_ALLE
    return blatt


# ── Abfragen für Endpunkte ───────────────────────────────────────────────────

def hat_recht(user: User, modul: str, recht: str = LESEN) -> bool:
    """Darf dieser Benutzer das? Die Frage, die jeder Endpunkt stellt."""
    if user.role == UserRole.admin:
        return True
    blatt = effektive_rechte(user)
    return bool(blatt.get(modul, {}).get(recht, False))


def umfang(user: User, modul: str) -> str:
    """``alle`` oder ``eigene`` — steuert die Filterung der Abfrage."""
    if user.role == UserRole.admin:
        return UMFANG_ALLE
    if modul not in UMFANG_RELEVANT:
        # Wo der Umfang keine Wirkung hat, ist die ehrliche Antwort „alle".
        # Ein „eigene" würde Endpunkte zu einer Filterung verleiten, für die es
        # gar kein Zuordnungsfeld gibt.
        return UMFANG_ALLE
    return effektive_rechte(user).get(modul, {}).get("umfang", UMFANG_EIGENE)


def darf_nur_eigene(user: User, modul: str) -> bool:
    return umfang(user, modul) == UMFANG_EIGENE


def module_mit_zugang(user: User) -> list[str]:
    """Module für das Menü — alles, was der Benutzer mindestens ansehen darf."""
    blatt = effektive_rechte(user)
    return [m for m in MODULE_KEYS if blatt.get(m, {}).get(LESEN)]


def katalog() -> list[dict]:
    """Beschreibung des Rechtemodells für die Oberfläche.

    Damit die Rechtematrix im Frontend nicht dieselbe Liste doppelt pflegen
    muss — die läuft sonst mit der Zeit auseinander, und niemand merkt, dass
    ein neues Modul in der Verwaltung fehlt.
    """
    return [
        {
            "modul": modul,
            "label": MODULE_LABELS.get(modul, modul),
            "rechte": [
                {"key": recht, "label": RECHT_LABELS[recht]}
                for recht in rechte_fuer_modul(modul)
            ],
            "umfang_relevant": modul in UMFANG_RELEVANT,
        }
        for modul in MODULE_KEYS
    ]
