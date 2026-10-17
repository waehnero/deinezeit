"""
Sichere Bausteine für Dokument-HTML (PDF-Erzeugung und HTML-Vorschau) — S02
==========================================================================

Alle Belege, Mahnungen, Berichte und Protokolle entstehen als HTML-Text, aus
dem WeasyPrint ein PDF macht; dasselbe HTML dient als Vorschau im Browser.
Feldinhalte (Positionstexte, Adressen, Filterwerte …) stammen von Benutzern,
aus Importen oder aus Altbeständen — sie sind **nicht vertrauenswürdig** und
dürfen das Dokument nicht verändern: keine neuen Tags, Attribute, Styles oder
Ressourcenverweise.

Darum gibt es genau drei Wege, einen Feldinhalt in Dokument-HTML zu bringen:

``text(wert)``
    **Gewöhnlicher Text** (Namen, Adressen, Nummern, Einheiten, Filterwerte,
    Benutzernamen …). Wird vollständig maskiert; ``<b>`` erscheint als
    sichtbarer Text, nicht als Fettdruck.

``rich_text(wert)``
    **Ausdrücklich erlaubter Rich Text** (Positionsbeschreibung und
    Zusatztext, Einleitung/Schluss, Hinweistexte, Mahntexte). Parserbasiert
    (nh3/ammonia, kein selbstgebauter Regex) auf eine enge Positivliste
    reduziert:

    * Elemente: ``b strong i em u s br p ul ol li span small sub sup``
    * Attribute: nur ``style`` an ``p``/``li``/``span`` und davon nur
      ``text-align: left|center|right|justify`` (das liefert der TipTap-Editor)
    * alles andere — ``script``/``style`` samt Inhalt, ``img``, ``link``,
      ``a``, ``svg``, ``iframe``, ``object``, Eventhandler, Kommentare,
      Ressourcen-URLs — entfällt.

    Reiner Text geht unverändert durch (``&`` und ``<`` werden korrekt
    maskiert, bereits maskierte Entitäten wie ``&amp;`` nicht doppelt), und
    Altbestände mit einfachen Formatierungen zeigen keine sichtbaren Tags.

``farbe(wert, vorgabe)`` / ``css_block(wert)``
    Für Werte, die in ``<style>``- oder ``style="…"``-Kontexte gehen:
    Farben nur als Hex-Wert, frei gepflegtes CSS (Belegeinstellungen,
    nur Administratoren) ohne ``<`` und ohne ``@import``. Ressourcen im CSS
    (``url(…)``) verhindert zusätzlich der Ressourcenfilter des Renderers
    (``services/pdf_render.py``) bzw. die CSP der Vorschau.

Wer neue Felder in ein Dokument bringt, nimmt einen dieser Wege. Ein
f-String mit einem Rohwert ist ein Fehler, auch wenn der Wert heute
harmlos aussieht.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any

import nh3

# ── Rich Text: Positivliste ──────────────────────────────────────────────────

RICH_TEXT_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "s", "br", "p", "ul", "ol", "li",
    "span", "small", "sub", "sup",
})
_STYLE_TRAEGER = ("p", "li", "span")
_RICH_TEXT_ATTRIBUTE = {tag: {"style"} for tag in _STYLE_TRAEGER}
_TEXT_ALIGN = re.compile(r"^\s*text-align\s*:\s*(left|center|right|justify)\s*$", re.I)


def _attribut_filter(tag: str, attribut: str, wert: str):
    """Lässt von ``style`` nur eine gültige Textausrichtung übrig.

    Jede Deklaration wird einzeln geprüft; alles außer ``text-align`` mit
    einem der vier Schlüsselwörter entfällt (also auch ``url(…)``).
    """
    if attribut != "style":
        return None
    for deklaration in (wert or "").split(";"):
        treffer = _TEXT_ALIGN.match(deklaration)
        if treffer:
            return f"text-align: {treffer.group(1).lower()}"
    return None


def text(wert: Any) -> str:
    """Gewöhnlicher Text → vollständig maskiert. ``None`` wird zu ``""``."""
    if wert is None:
        return ""
    return _html.escape(str(wert), quote=True)


def rich_text(wert: Any) -> str:
    """Erlaubter Rich Text → auf die Positivliste reduziertes HTML."""
    if wert is None:
        return ""
    return nh3.clean(
        str(wert),
        tags=set(RICH_TEXT_TAGS),
        attributes={k: set(v) for k, v in _RICH_TEXT_ATTRIBUTE.items()},
        attribute_filter=_attribut_filter,
        clean_content_tags={"script", "style"},
        strip_comments=True,
        link_rel=None,
        url_schemes=set(),
    )


def nur_text(wert: Any) -> str:
    """Rich Text → reiner Text (Tags entfernt), unmaskiert.

    Für Stellen, die eine einzeilige Kurzfassung brauchen (z. B. die
    Rücksendezeile aus den Absenderzeilen). Ergebnis wieder mit ``text()``
    ausgeben.
    """
    if wert is None:
        return ""
    ohne_tags = nh3.clean(str(wert), tags=set(), clean_content_tags={"script", "style"})
    return _html.unescape(ohne_tags)


# ── CSS-Kontexte ─────────────────────────────────────────────────────────────

_HEXFARBE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def farbe(wert: Any, vorgabe: str) -> str:
    """Nur Hex-Farben (``#rgb``, ``#rrggbb`` …); alles andere → ``vorgabe``."""
    s = str(wert or "").strip()
    return s if _HEXFARBE.match(s) else vorgabe


_CSS_IMPORT = re.compile(r"@import\b[^;]*;?", re.I)


def css_block(wert: Any) -> str:
    """Frei gepflegtes CSS für einen ``<style>``-Block entschärfen.

    * ``<`` entfällt — damit kann der Wert den ``<style>``-Block nicht
      verlassen (``</style><script>…``).
    * ``@import`` entfällt — nachgeladene Stylesheets gibt es nicht.
    * ``url(…)`` bleibt syntaktisch stehen, wird aber vom Ressourcenfilter des
      Renderers nur für ``data:``-Bilder aufgelöst und in der Vorschau von der
      CSP blockiert.
    """
    s = str(wert or "")
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    s = s.replace("<", "")
    return _CSS_IMPORT.sub("", s)


# ── HTML-Vorschau ────────────────────────────────────────────────────────────

#: CSP für alle HTML-Vorschauen von Dokumenten. Keine Skripte, keine
#: Nachladungen außer eingebetteten ``data:``-Bildern; ``sandbox`` gibt der
#: direkt geöffneten Antwort zusätzlich einen undurchsichtigen Ursprung.
VORSCHAU_CSP = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
                "font-src data:; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'self'; sandbox")
#: Dieselbe Regel als <meta>-Element. Wirkt auch dann, wenn das Frontend die
#: Antwort als Blob öffnet (dann gelten die HTTP-Header nicht mehr).
#: ``sandbox`` und ``frame-ancestors`` sind per <meta> nicht erlaubt.
_VORSCHAU_CSP_META = ('<meta http-equiv="Content-Security-Policy" content="'
                      "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
                      "font-src data:; base-uri 'none'; form-action 'none'\">")

VORSCHAU_KOPF = {
    "Content-Security-Policy": VORSCHAU_CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def vorschau_absichern(dokument: str) -> str:
    """Setzt die CSP als erstes Element in den ``<head>`` des Dokuments."""
    if "<head>" in dokument:
        return dokument.replace("<head>", "<head>" + _VORSCHAU_CSP_META, 1)
    return _VORSCHAU_CSP_META + dokument


def vorschau_antwort(dokument: str):
    """``HTMLResponse`` für eine Dokument-Vorschau mit allen Schutz-Headern."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=vorschau_absichern(dokument), headers=dict(VORSCHAU_KOPF))


# ── Bilder aus dem static-Verzeichnis (Logos) ────────────────────────────────

#: Bildtypen, die als Logo in Dokumente eingebettet werden
LOGO_TYPEN = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "svg": "image/svg+xml", "webp": "image/webp", "gif": "image/gif"}
LOGO_MAX_BYTES = 2 * 1024 * 1024


def static_bild_datenurl(url: Any, static_dir: str, url_praefix: str = "/api/static",
                         max_bytes: int = LOGO_MAX_BYTES) -> str:
    """Logo-URL aus den Einstellungen → ``data:``-URL, oder ``""``.

    Serverseitig bestimmt und eng begrenzt: nur Dateien **innerhalb** von
    ``static_dir`` (kein ``..``, keine Symlinks hinaus), nur Bildendungen,
    höchstens ``max_bytes``, und der Inhalt muss zum Bildtyp passen. Früher
    wurde der Pfad per ``replace`` gebildet und ohne weitere Prüfung gelesen —
    ``/api/static/../../etc/…`` hätte jede für das Backend lesbare Datei als
    „Logo" in Vorschau und PDF gebracht.
    """
    import os

    s = str(url or "").strip()
    if not s.startswith(url_praefix.rstrip("/") + "/"):
        return ""
    relativ = s[len(url_praefix.rstrip("/")) + 1:].split("?", 1)[0].split("#", 1)[0]
    wurzel = os.path.realpath(static_dir)
    pfad = os.path.realpath(os.path.join(wurzel, relativ))
    if not pfad.startswith(wurzel + os.sep):
        return ""
    endung = os.path.splitext(pfad)[1].lower().lstrip(".")
    mime = LOGO_TYPEN.get(endung)
    if not mime or not os.path.isfile(pfad) or os.path.getsize(pfad) > max_bytes:
        return ""
    with open(pfad, "rb") as f:
        daten = f.read(max_bytes + 1)
    return bild_datenurl(daten, mime, max_bytes)


def bild_datenurl(daten: bytes, mime: str, max_bytes: int) -> str:
    """Bilddaten → ``data:``-URL, wenn Typ, Inhalt und Größe stimmen, sonst ``""``.

    Dieselbe Prüfung wie der Ressourcenfilter im Renderprozess — was hier
    durchgeht, wird dort auch angenommen; die Vorschau im Browser bekommt
    nichts anderes als das PDF.
    """
    import base64
    from app.services.pdf_render_worker import RessourceGesperrt, ressource_holen

    if not daten or len(daten) > max_bytes:
        return ""
    url = f"data:{mime};base64,{base64.b64encode(daten).decode('ascii')}"
    try:
        ressource_holen(url, max_bytes)
    except RessourceGesperrt:
        return ""
    return url


def css_zeichenkette(wert: Any) -> str:
    """Wert für eine CSS-Zeichenkette (``content: "…"``), ohne Anführungszeichen.

    Buchstaben, Ziffern und einfache Satzzeichen bleiben stehen; alles andere
    (``"``, ``\\``, ``<``, Zeilenumbrüche, ``;`` …) wird als CSS-Hex-Escape
    geschrieben und kann die Zeichenkette damit nicht verlassen.
    """
    return "".join(
        z if (z.isalnum() or z in " .,-_@:/()") else f"\\{ord(z):x} "
        for z in str(wert or "")
    )
