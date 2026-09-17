"""
Zeiten-Import: PDF über die KI-Schnittstelle in eine Tabelle überführen
======================================================================

Ein Stundenzettel als PDF hat keine Spalten, die ein Programm lesen könnte —
oft ist er sogar nur ein Scan. Die KI liest ihn und liefert eine Tabelle. Mehr
nicht: Die Tabelle geht denselben Weg wie eine CSV-Datei (Spalten zuordnen →
Probelauf → Bericht → bewusst importieren), und der Benutzer kann sie vorher
als CSV herunterladen und korrigieren.

Beschluss Oliver (18.09.2026): Das PDF geht DIREKT an den KI-Provider. Beide
Provider lesen PDFs selbst, auch gescannte; das Backend braucht keine
PDF-Bibliothek. Dafür verlässt die Datei den Server — der Assistent weist vor
dem Hochladen darauf hin.

Die KI wird hier bewusst klein gehalten: abschreiben, nicht rechnen, nichts
ergänzen. Ob „7,5" eine Dauer oder eine Pause ist, ob eine Uhrzeit plausibel
ist — das entscheidet danach dieselbe Prüfung wie bei jeder anderen Datei.
Eine KI, die verliest, ist damit ein Tippfehler in der Quelle und fällt im
Prüfbericht oder beim Vergleich der Stundensumme auf, nicht erst Monate später.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.services.ki import call_ki

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024
# Rund 250–300 Tabellenzeilen. Mehr gäbe das Zeitfenster nicht her: Die Antwort
# muss unter dem proxy_read_timeout von nginx (180 s) fertig sein.
MAX_TOKENS = 10000
ZEITLIMIT_SEKUNDEN = 170
MAX_SPALTEN = 40

PROMPT = """Du liest einen Arbeitszeitnachweis (Stundenzettel, Zeiterfassungs-Export) \
und gibst ihn als Tabelle zurück.

Regeln:
1. Jede erfasste Arbeitszeit wird eine Zeile. Summen-, Zwischensummen-, Saldo- \
und Überschriftenzeilen werden NICHT übernommen.
2. Schreibe die Werte so ab, wie sie im Dokument stehen (z.B. "07:30", "0,5", \
"31.12.2026"). Nichts umrechnen, nichts berechnen, nichts ergänzen. Ist ein Wert \
nicht lesbar oder fehlt er, bleibt die Zelle leer ("").
3. Nimm die Spaltenüberschriften des Dokuments. Hat eine Spalte keine, vergib \
eine kurze deutsche (z.B. "Beginn", "Ende", "Pause", "Tätigkeit").
4. Steht der Name der Person nur im Kopf des Dokuments, füge eine Spalte \
"Mitarbeiter" hinzu und trage ihn in jede Zeile ein. Gleiches gilt für ein \
Projekt oder einen Kunden, der nur im Kopf steht (Spalte "Projekt").
5. Steht in den Zeilen nur der Tag (z.B. "Mo 03.") und Monat/Jahr nur im Kopf, \
schreibe das vollständige Datum als TT.MM.JJJJ in die Spalte "Datum" und \
vermerke das unter "hinweise".
6. Unter "hinweise" nennst du alles, was ein Mensch prüfen sollte: unleserliche \
Stellen, handschriftliche Korrekturen, Zeilen ohne Beginn/Ende, mehrere \
Personen im Dokument.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne Erklärung und ohne \
Markdown-Codeblock, in genau dieser Form:
{"spalten": ["Datum", "Beginn", "..."],
 "zeilen": [["03.08.2026", "07:30", "..."], ["..."]],
 "hinweise": ["..."]}
Jede Zeile hat genau so viele Werte wie "spalten". Alle Werte sind Zeichenketten. \
Enthält das Dokument keine Arbeitszeiten, ist "zeilen" leer und "hinweise" sagt, \
was das Dokument stattdessen ist."""


class PdfLesefehler(RuntimeError):
    """Das PDF ließ sich nicht in eine Tabelle überführen — Text ist für den Benutzer."""


def _json_aus_antwort(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        treffer = re.search(r"\{.*\}", text, re.DOTALL)
        if treffer:
            try:
                return json.loads(treffer.group(0))
            except ValueError:
                pass
    raise PdfLesefehler("Die KI-Antwort konnte nicht ausgewertet werden — "
                        "bitte noch einmal versuchen")


def pdf_zu_tabelle(ki: dict, pdf: bytes, dateiname: str) -> Dict[str, Any]:
    """Liefert ``{"spalten": [...], "zeilen": [{spalte: wert}], "hinweise": [...]}``.

    ``zeilen`` hat dieselbe Form wie das, was der Browser aus einer CSV-Datei
    liest — der Assistent behandelt beides gleich.
    """
    if not pdf.startswith(b"%PDF"):
        raise PdfLesefehler("Das ist keine PDF-Datei")
    if len(pdf) > MAX_PDF_BYTES:
        raise PdfLesefehler("Das PDF ist größer als 10 MB — bitte aufteilen")

    meta: Dict[str, Any] = {}
    try:
        antwort = call_ki(ki, PROMPT, dokumente=[(pdf, dateiname)],
                          max_tokens=MAX_TOKENS, kontext="zeiten-import",
                          timeout=ZEITLIMIT_SEKUNDEN, meta=meta)
    except RuntimeError as e:
        raise PdfLesefehler(str(e)) from e

    if meta.get("abgeschnitten"):
        # Eine abgerissene Tabelle still zu übernehmen wäre das Schlimmste:
        # Die letzten Wochen fehlten, und nichts wiese darauf hin.
        raise PdfLesefehler("Das PDF enthält mehr Zeilen, als sich in einem "
                            "Durchgang lesen lassen — bitte in kleinere Teile "
                            "(z.B. je Monat) aufteilen")

    daten = _json_aus_antwort(antwort)
    spalten_roh = daten.get("spalten")
    zeilen_roh = daten.get("zeilen")
    if not isinstance(spalten_roh, list) or not isinstance(zeilen_roh, list):
        raise PdfLesefehler("Die KI hat keine Tabelle geliefert — bitte noch "
                            "einmal versuchen")

    # Spaltennamen eindeutig machen: Zwei Spalten „Zeit" würden sich beim
    # Umbau in Wörterbücher gegenseitig überschreiben.
    spalten: List[str] = []
    for i, name in enumerate(spalten_roh[:MAX_SPALTEN], start=1):
        name = str(name or "").strip() or f"Spalte {i}"
        basis, n = name, 2
        while name in spalten:
            name = f"{basis} ({n})"
            n += 1
        spalten.append(name)

    zeilen: List[Dict[str, str]] = []
    hinweise = [str(h) for h in (daten.get("hinweise") or []) if str(h).strip()]
    schief = 0
    for roh in zeilen_roh:
        if not isinstance(roh, list):
            schief += 1
            continue
        if len(roh) != len(spalten_roh):
            schief += 1
        werte = ["" if w is None else str(w).strip() for w in roh]
        werte = (werte + [""] * len(spalten))[:len(spalten)]
        if any(werte):
            zeilen.append(dict(zip(spalten, werte)))
    if schief:
        hinweise.append(f"{schief} Zeile(n) hatten nicht die erwartete Spaltenzahl "
                        "— bitte diese Zeilen mit dem PDF vergleichen")

    return {"spalten": spalten, "zeilen": zeilen, "hinweise": hinweise}
