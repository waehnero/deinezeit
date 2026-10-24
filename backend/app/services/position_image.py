"""
Bilder an Belegpositionen.

Das Bild wird **beim Hochladen** auf die gewählte Druckgröße verkleinert und
nur in dieser Fassung gespeichert. Das hält Speicher und PDF klein und macht
die Größe zu einer Eigenschaft der Datei statt zu einer Anzeigeoption, die bei
jedem Rendern neu ausgewertet werden müsste.

Preis dafür: Eine andere Größe bedeutet neu hochladen. Das war die bewusste
Entscheidung — „nach dem Upload fixieren".

Die Pixelbreiten sind auf 200 dpi ausgelegt: Bei dieser Auflösung sieht ein
Bild im PDF-Druck sauber aus, ohne dass die Datei aufgebläht wird.
"""
import io
import logging
import re
import uuid

from fastapi import HTTPException


# Name → (Breite auf dem Beleg in mm, gespeicherte Pixelbreite bei 200 dpi)
GROESSEN = {
    "klein":  (30,  240),
    "mittel": (60,  480),
    "gross":  (100, 800),
}

MAX_UPLOAD = 15 * 1024 * 1024        # 15 MB Rohdatei
ERLAUBTE_TYPEN = ("image/jpeg", "image/png", "image/webp", "image/gif")

logger = logging.getLogger(__name__)

# ── S02: Grenzen und erlaubte Speicherreferenzen ─────────────────────────────
#: Höchstzahl an Bildpunkten, die beim Hochladen überhaupt dekodiert werden
#: (Schutz vor „Dekompressionsbomben": kleine Datei, riesiges Bild).
MAX_PIXEL_UPLOAD = 40_000_000
#: Höchsthöhe des gespeicherten Bildes in Pixeln (Breite ist durch GROESSEN fix)
MAX_HOEHE = 3000
#: Größte Datei, die in ein Dokument eingebettet wird
MAX_EINBETTEN = 4 * 1024 * 1024
#: Speicherreferenz eines Positionsbildes. Vom Server beim Hochladen vergeben
#: (``speicher_schluessel``); der Client schickt sie nur mit. Alles andere —
#: andere Ordner im Objektspeicher, ``..``, Unterordner — wird abgewiesen.
SCHLUESSEL_MUSTER = re.compile(
    r"^belege/positionsbilder/[A-Za-z0-9_-]{1,100}\.(?:jpg|jpeg|png|gif|webp)$")
ERLAUBTE_SPEICHER = ("minio", "onedrive", "webdav", "nextcloud", "seadrive")
_TYP_JE_ENDUNG = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                  "gif": "image/gif", "webp": "image/webp"}


def schluessel_gueltig(schluessel) -> bool:
    """True, wenn ``schluessel`` eine zulässige Positionsbild-Referenz ist."""
    return isinstance(schluessel, str) and bool(SCHLUESSEL_MUSTER.fullmatch(schluessel))


def speicher_gueltig(provider) -> bool:
    """Leer (= aktiver Speicher) oder ein bekannter Speichername."""
    return provider in (None, "") or provider in ERLAUBTE_SPEICHER


def breite_mm(groesse: str) -> int:
    """Druckbreite in Millimetern; unbekannte Angabe fällt auf 'mittel'."""
    return GROESSEN.get(groesse, GROESSEN["mittel"])[0]


def verkleinern(rohdaten: bytes, groesse: str) -> tuple:
    """
    Bringt das Bild auf die Pixelbreite der gewählten Größe.

    Gibt ``(bytes, mimetype, endung)`` zurück. Ausgabe ist immer JPEG oder PNG —
    PNG nur, wenn das Bild durchsichtige Stellen hat, sonst wäre die Datei
    unnötig groß.
    """
    if groesse not in GROESSEN:
        raise HTTPException(400, f"Unbekannte Größe: {groesse}. "
                                 f"Erlaubt: {', '.join(GROESSEN)}")
    try:
        from PIL import Image
    except ImportError as e:                                   # pragma: no cover
        raise HTTPException(500, "Bildverarbeitung steht nicht zur Verfügung") from e

    try:
        bild = Image.open(io.BytesIO(rohdaten))
    except Exception as e:
        raise HTTPException(400, "Die Datei konnte nicht als Bild gelesen werden") from e
    # Abmessungen stehen im Dateikopf — prüfen, BEVOR die Bilddaten dekodiert
    # werden.
    if bild.width * bild.height > MAX_PIXEL_UPLOAD:
        raise HTTPException(400, "Bild hat zu viele Bildpunkte (max. 40 Megapixel)")
    try:
        bild.load()
    except Exception as e:
        raise HTTPException(400, "Die Datei konnte nicht als Bild gelesen werden") from e

    ziel_breite = GROESSEN[groesse][1]
    if bild.width > ziel_breite:
        hoehe = max(1, round(bild.height * ziel_breite / bild.width))
        bild = bild.resize((ziel_breite, hoehe), Image.LANCZOS)
    if bild.height > MAX_HOEHE:
        raise HTTPException(400, "Bild ist für einen Beleg zu hoch "
                                 f"(höchstens {MAX_HOEHE} Pixel bei dieser Breite)")

    transparent = bild.mode in ("RGBA", "LA") or (
        bild.mode == "P" and "transparency" in bild.info)

    puffer = io.BytesIO()
    if transparent:
        bild.convert("RGBA").save(puffer, format="PNG", optimize=True)
        return puffer.getvalue(), "image/png", "png"
    bild.convert("RGB").save(puffer, format="JPEG", quality=82, optimize=True)
    return puffer.getvalue(), "image/jpeg", "jpg"


def speicher_schluessel(endung: str) -> str:
    """
    Ablageort im Objektspeicher.

    Bewusst NICHT unter einem Kontakt: Das Bild entsteht am Positionsentwurf,
    zu dem es noch keinen ausgestellten Beleg und womöglich keinen Kontakt gibt.
    """
    return f"belege/positionsbilder/{uuid.uuid4().hex}.{endung}"


def als_datenurl(db, image_key: str, provider: str = None) -> str | None:
    """
    Lädt das Bild und gibt es als Data-URL zurück.

    Für die PDF-Erzeugung: WeasyPrint müsste eine Datei-URL sonst selbst
    auflösen können — im Container hinter dem Objektspeicher geht das nicht.
    Fehler werden geschluckt, ein fehlendes Bild darf keinen Beleg verhindern.

    ``provider`` ist der Speicher, in dem die Datei liegt. Ohne ihn wird der
    aktive genommen — im Mischbetrieb also womöglich der falsche.
    """
    if not image_key:
        return None
    # S02: Die Referenz kommt mit den Positionsdaten vom Client. Nur Schlüssel
    # aus dem Positionsbild-Ordner werden geladen; der Bildtyp ergibt sich aus
    # der Endung und wird am Inhalt geprüft (nicht aus der Angabe des
    # Speichers übernommen).
    if not schluessel_gueltig(image_key) or not speicher_gueltig(provider):
        logger.warning("Positionsbild mit unzulässiger Referenz abgewiesen")
        return None
    from app.core.dokument_html import bild_datenurl
    from app.services import storage_service
    try:
        daten, _ = storage_service.download_file(image_key, db=db, backend=provider or None)
    except Exception:
        logger.warning("Positionsbild %s nicht ladbar", image_key, exc_info=True)
        return None
    if not daten or len(daten) > MAX_EINBETTEN or not _abmessungen_ok(daten):
        logger.warning("Positionsbild %s überschreitet die Grenzen", image_key)
        return None
    mime = _TYP_JE_ENDUNG[image_key.rsplit(".", 1)[1].lower()]
    return bild_datenurl(daten, mime, MAX_EINBETTEN) or None


def _abmessungen_ok(daten: bytes) -> bool:
    """Liest nur den Bildkopf und prüft die Pixelzahl."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(daten)) as bild:
            return bild.width * bild.height <= MAX_PIXEL_UPLOAD
    except Exception:
        return False
