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
    except ImportError:                                   # pragma: no cover
        raise HTTPException(500, "Bildverarbeitung steht nicht zur Verfügung")

    try:
        bild = Image.open(io.BytesIO(rohdaten))
        bild.load()
    except Exception:
        raise HTTPException(400, "Die Datei konnte nicht als Bild gelesen werden")

    ziel_breite = GROESSEN[groesse][1]
    if bild.width > ziel_breite:
        hoehe = max(1, round(bild.height * ziel_breite / bild.width))
        bild = bild.resize((ziel_breite, hoehe), Image.LANCZOS)

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


def als_datenurl(db, image_key: str) -> str | None:
    """
    Lädt das Bild und gibt es als Data-URL zurück.

    Für die PDF-Erzeugung: WeasyPrint müsste eine Datei-URL sonst selbst
    auflösen können — im Container hinter dem Objektspeicher geht das nicht.
    Fehler werden geschluckt, ein fehlendes Bild darf keinen Beleg verhindern.
    """
    if not image_key:
        return None
    import base64
    from app.services import storage_service
    try:
        daten, mime = storage_service.download_file(image_key, db=db)
        b64 = base64.b64encode(daten).decode("ascii")
        return f"data:{mime or 'image/jpeg'};base64,{b64}"
    except Exception as e:
        print(f"[WARN] Positionsbild {image_key} nicht ladbar: {e}")
        return None
