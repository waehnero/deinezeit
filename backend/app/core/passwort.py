"""
Passwort-Richtlinie
===================

Bisher gab es keine: ``"a"`` war ein zulässiges Passwort — beim Anlegen eines
Benutzers, beim Erstinstallations-Assistenten und beim Ändern im Profil.

Die Regeln folgen der heute üblichen Empfehlung (NIST SP 800-63B) und
verzichten bewusst auf die klassische Pflicht „Groß, klein, Zahl,
Sonderzeichen". Diese Vorgabe erzeugt in der Praxis Passwörter wie
``Sommer2026!`` — sie erfüllt jede Prüfung und steht in jeder Angriffsliste.
Wirksam sind Länge und die Abwesenheit bekannter Muster, deshalb prüfen wir
das.

Konkret:

* mindestens 10 Zeichen (Empfehlung im Text: eine Wortfolge)
* höchstens 128 Zeichen — begrenzt, weil bcrypt ohnehin nach 72 Byte
  abschneidet und ein 1-MB-Passwort nur Rechenzeit kostet
* nicht in der Liste offensichtlicher Passwörter
* nicht die eigene E-Mail-Adresse oder der eigene Name
* nicht aus einem einzigen wiederholten Zeichen und keine reine Tastaturreihe

Anpassen ist Absicht: ``MIN_LAENGE`` und ``VERBOTEN`` sind bewusst hier
zentral, damit die Regel an einer Stelle steht und nicht in fünf Formularen.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

MIN_LAENGE = 10
MAX_LAENGE = 128

#: Kleine, gezielte Liste. Eine vollständige Prüfung gegen geleakte Passwörter
#: (z. B. „Have I Been Pwned") wäre wirksamer, würde aber jede
#: Passwortänderung von einem fremden Dienst abhängig machen — für eine
#: selbst-gehostete Installation, die auch ohne Internetzugang funktionieren
#: muss, ein schlechter Tausch. Die Liste deckt ab, was Menschen tatsächlich
#: eintippen, wenn sie schnell fertig werden wollen.
VERBOTEN = frozenset({
    "passwort", "password", "passwort1", "geheim", "kennwort",
    "12345678", "123456789", "1234567890", "qwertzuiop", "qwertyuiop",
    "asdfghjkl", "sommer2026", "winter2026", "willkommen", "welcome",
    "deinezeit", "deinezeit1", "administrator", "admin1234",
    "letmein", "iloveyou", "monkey123", "dragon123", "zeiterfassung",
})

#: Tastaturreihen, die als Passwort nichts taugen.
_REIHEN = ("qwertzuiop", "qwertyuiop", "asdfghjkl", "yxcvbnm", "zxcvbnm",
           "1234567890", "abcdefghij")


#: Verbreitete Zeichenersetzungen („Leetspeak"). Jede Angriffsliste probiert
#: sie ohnehin mit, also dürfen sie ein bekanntes Passwort nicht retten.
_ERSETZUNGEN = (("@", "a"), ("0", "o"), ("3", "e"), ("4", "a"),
                ("5", "s"), ("7", "t"), ("$", "s"))

#: Die Ziffer 1 wird sowohl für „l" als auch für „i" verwendet, und manchmal
#: ist sie einfach eine angehängte Zahl. Alle drei Deutungen werden geprüft —
#: eine feste Wahl würde je nach Passwort das falsche Ergebnis liefern.
_EINSEN = ("", "l", "i")


def _normalisieren(wert: str) -> str:
    """Für Vergleiche: Kleinschreibung, Umlaute zerlegt, nur a–z und 0–9."""
    wert = unicodedata.normalize("NFKD", wert).lower()
    return re.sub(r"[^a-z0-9]", "", wert)


def _varianten(wert: str) -> set[str]:
    """Schreibweisen, unter denen dasselbe Passwort gemeint sein kann.

    Mehrere Varianten statt einer, weil jede einzelne Regel woanders daneben
    trifft. Zwei Punkte, die dabei leicht schiefgehen:

    * Die Zeichenersetzung muss **nach** dem Abtrennen angehängter Ziffern
      laufen. Sonst wird aus ``P@ssw0rt123`` die Folge ``passwort12e`` — die
      Regel für „3 steht für e" verstümmelt die Jahreszahl, und das bekannte
      Wort ist nicht mehr zu erkennen.
    * ``@`` und ``$`` dürfen beim Filtern zunächst stehen bleiben, sonst ist
      die Ersetzung wirkungslos.
    """
    grund = unicodedata.normalize("NFKD", wert).lower()
    grund = re.sub(r"[^a-z0-9@$]", "", grund)

    # Sowohl das ganze Passwort als auch der Teil vor angehängten Ziffern:
    # „Sommer2026" und „Sommer" sollen beide gegen die Verbotsliste laufen.
    kandidaten = {grund, re.sub(r"\d+$", "", grund)}

    ergebnis: set[str] = set()
    for kandidat in kandidaten:
        ergebnis.add(re.sub(r"[^a-z0-9]", "", kandidat))
        leet = kandidat
        for zeichen, ersatz in _ERSETZUNGEN:
            leet = leet.replace(zeichen, ersatz)
        for eins in _EINSEN:
            ergebnis.add(re.sub(r"[^a-z0-9]", "", leet.replace("1", eins)))
    return {v for v in ergebnis if v}


def pruefen(passwort: str, *, email: Optional[str] = None,
            name: Optional[str] = None) -> Optional[str]:
    """Passwort prüfen.

    Rückgabe: ``None`` = in Ordnung, sonst ein fertiger deutscher Hinweistext
    für die Oberfläche. Die Meldung sagt, *was* zu tun ist — „Passwort
    ungültig" hilft niemandem weiter.
    """
    if not passwort:
        return "Bitte ein Passwort eingeben."

    if len(passwort) < MIN_LAENGE:
        return (f"Das Passwort muss mindestens {MIN_LAENGE} Zeichen lang sein. "
                "Am einfachsten ist eine Wortfolge, die Sie sich merken können, "
                "zum Beispiel „gelberstuhlamfenster“.")

    if len(passwort) > MAX_LAENGE:
        return f"Das Passwort darf höchstens {MAX_LAENGE} Zeichen lang sein."

    if passwort.strip() != passwort:
        return ("Das Passwort darf nicht mit einem Leerzeichen beginnen oder "
                "enden — das führt beim Anmelden zu Fehlern, die niemand "
                "sieht.")

    normal = _normalisieren(passwort)
    varianten = _varianten(passwort)

    if len(set(passwort)) <= 2:
        return ("Das Passwort besteht aus zu wenig verschiedenen Zeichen. "
                "Bitte wählen Sie eine Wortfolge.")

    # Der Klassiker „bekanntes Wort plus angehängte Ziffern" fällt mit durch:
    # „Passwort123" ist für einen Angriff nicht schwerer als „Passwort", weil
    # jede Liste die Zahlenanhänge automatisch mitprobiert. Die Stamm-Variante
    # dazu liefert bereits _varianten().
    if varianten & VERBOTEN:
        return ("Dieses Passwort ist zu bekannt und steht in jeder "
                "Angriffsliste. Bitte wählen Sie ein anderes.")

    for variante in varianten:
        if len(variante) < 6:
            continue
        for reihe in _REIHEN:
            if variante in reihe or reihe.startswith(variante):
                return ("Das Passwort ist eine Tastatur- oder Zahlenreihe. "
                        "Bitte wählen Sie eine Wortfolge.")

    if email:
        # Der Teil vor dem @ ist der aussagekräftige; „oliver" als Passwort bei
        # oliver@… ist genauso schwach wie die ganze Adresse.
        ortsteil = _normalisieren(email.split("@")[0])
        if ortsteil and len(ortsteil) >= 4 and ortsteil in normal:
            return ("Das Passwort darf nicht Ihre E-Mail-Adresse enthalten — "
                    "sie ist bei einem Angriff das Erste, was ausprobiert wird.")

    if name:
        for teil in re.split(r"\s+", name.strip()):
            teil_normal = _normalisieren(teil)
            if len(teil_normal) >= 4 and teil_normal in normal:
                return ("Das Passwort darf nicht Ihren Namen enthalten — "
                        "er ist zu leicht zu erraten.")

    return None


def pruefen_oder_fehler(passwort: str, *, email: Optional[str] = None,
                        name: Optional[str] = None) -> None:
    """Wie ``pruefen``, wirft aber direkt HTTP 400 mit dem Hinweistext."""
    from fastapi import HTTPException
    meldung = pruefen(passwort, email=email, name=name)
    if meldung:
        raise HTTPException(status_code=400, detail=meldung)
