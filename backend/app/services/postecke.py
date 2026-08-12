"""
Postecke-Service: KI-Generierung von Post-Vorschlägen (Etappe 1)
================================================================

Baut aus den Fotos eines Posts, der Nutzerbeschreibung und dem Stil-Prompt
des Zielprofils einen Prompt und ruft den zentral konfigurierten KI-Provider
auf (services/ki.py — Einstellungen -> System -> KI & Mail-Importer).
"""

import json
import logging
import os
import re
import subprocess  # nosec B404 - fester ffmpeg-Aufruf, keine Shell, keine Nutzereingabe
import tempfile
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.postecke import SocialPost, SocialProfil
from app.services import storage_service
from app.services.ki import call_ki, load_ki_settings, KI_DEFAULT_MODELS

logger = logging.getLogger(__name__)

# Diagnose-Präfixe (Gegenstück zu den Präfixen in services/ki.py).
# [KI-PARSE] = Antwort kam an, war aber nicht verwertbar — der Fall, der bisher
# als nacktes 400 endete. [KI-FOTO] = Bild fehlte schon vor dem KI-Aufruf.
LOG_PRAEFIX_PARSE = "[KI-PARSE]"
LOG_PRAEFIX_FOTO = "[KI-FOTO]"

# So viele Zeichen der Rohantwort landen im Log — nur im Fehlerfall.
MAX_LOG_ROHANTWORT = 500

# Maximal so viele Fotos werden der KI übergeben (Kosten-/Kontextbegrenzung)
MAX_FOTOS_FUER_KI = 5

KANAL_NAMEN = {
    "facebook_privat": "Facebook (privates Profil)",
    "facebook_seite": "Facebook-Seite",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "sonstige": "Social Media",
}

_GENERIEREN_PROMPT = """Du bist ein Social-Media-Assistent. Erstelle aus den beigefügten Fotos und
der Beschreibung einen fertigen Post für {kanal}.

{stil_block}Beschreibung des Benutzers:
{beschreibung}

Beachte:
- Sprache: Deutsch (außer der Stil verlangt anderes).
- Erkenne aus den Fotos möglichst viel Kontext (Ort, Anlass, Stimmung,
  Plakattexte wie Veranstaltungsname/Datum).
- Der Text soll natürlich klingen, nicht nach Werbung.
- Passende Hashtags am Ende, zum Kanal passende Anzahl
  (LinkedIn: 3-5 sachlich, Instagram: bis 15, Facebook: 3-8).

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau diesem Format,
ohne weiteren Text:
{{"titel": "interne Kurzbezeichnung (max. 60 Zeichen)",
  "text": "der fertige Posttext OHNE Hashtags",
  "hashtags": "#tag1 #tag2 ...",
  "ort": "erkannter/genannter Ort oder null",
  "gefuehl": "passendes Facebook-Gefühl (z.B. fröhlich, dankbar, stolz) oder null"}}"""


def _parse_ki_json(text: str) -> Optional[dict]:
    """Extrahiert das JSON-Objekt aus der KI-Antwort (tolerant gegen Codeblöcke)."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _lade_fotos(db: Session, post: SocialPost) -> List[Tuple[bytes, str]]:
    """Lädt die Fotos des Posts aus dem Objektspeicher (max. MAX_FOTOS_FUER_KI)."""
    bilder: List[Tuple[bytes, str]] = []
    auswahl = (post.fotos or [])[:MAX_FOTOS_FUER_KI]
    for foto in auswahl:
        try:
            data, _ct = storage_service.download_file(
                foto.storage_key, db, backend=foto.storage_provider)
            bilder.append((data, foto.mimetype or "image/jpeg"))
        except Exception as e:
            # Ein fehlendes Einzelfoto bricht die Generierung nicht ab — bisher
            # aber völlig lautlos. Die KI bekommt dann weniger Bilder als
            # gedacht und antwortet entsprechend dünn.
            logger.warning("%s post=%s Foto %s nicht ladbar (%s: %s) — "
                           "wird übersprungen", LOG_PRAEFIX_FOTO, post.id,
                           foto.id, e.__class__.__name__, e)
    if len(bilder) < len(auswahl):
        logger.warning("%s post=%s: nur %d von %d Fotos an die KI übergeben",
                       LOG_PRAEFIX_FOTO, post.id, len(bilder), len(auswahl))
    return bilder


def generiere_vorschlag(db: Session, post: SocialPost,
                        profil: Optional[SocialProfil],
                        beschreibung: Optional[str] = None) -> dict:
    """
    Erzeugt einen Post-Vorschlag. Liefert dict mit
    titel/text/hashtags/ort/gefuehl/ki_model. Wirft RuntimeError bei
    fehlender KI-Konfiguration oder unbrauchbarer Antwort.
    """
    ki = load_ki_settings(db)

    kanal = KANAL_NAMEN.get(profil.kanal if profil else "", KANAL_NAMEN["sonstige"])
    stil_block = ""
    if profil is not None and (profil.stil_prompt or "").strip():
        stil_block = ("Stil und Redensart dieses Kontos (unbedingt einhalten):\n"
                      f"{profil.stil_prompt.strip()}\n\n")

    text_beschreibung = (beschreibung or post.beschreibung or "").strip() or "-"
    prompt = _GENERIEREN_PROMPT.format(
        kanal=kanal, stil_block=stil_block, beschreibung=text_beschreibung)

    antwort = call_ki(ki, prompt, images=_lade_fotos(db, post), max_tokens=2000,
                      kontext=f"postecke post={post.id}")
    data = _parse_ki_json(antwort)
    if not data or not (data.get("text") or "").strip():
        # Ohne die Rohantwort war hier nur ein nacktes 400 im Log zu sehen.
        # Gekürzt und nur im Fehlerfall — der Text kann Postinhalte enthalten.
        grund = "kein JSON-Objekt gefunden" if not data else "Feld 'text' fehlt oder leer"
        logger.error("%s postecke post=%s: %s | Rohantwort (%d Zeichen, gekürzt): %r",
                     LOG_PRAEFIX_PARSE, post.id, grund, len(antwort or ""),
                     (antwort or "")[:MAX_LOG_ROHANTWORT])
        raise RuntimeError("Die KI-Antwort konnte nicht verarbeitet werden — bitte erneut versuchen")

    provider = ki.get("provider") or "anthropic"
    model = ki.get("model") or KI_DEFAULT_MODELS.get(provider, "")
    return {
        "titel": (data.get("titel") or "").strip()[:300] or None,
        "text": data.get("text").strip(),
        "hashtags": (data.get("hashtags") or "").strip() or None,
        "ort": (data.get("ort") or "").strip()[:300] or None,
        "gefuehl": (data.get("gefuehl") or "").strip()[:100] or None,
        "ki_model": f"{provider}/{model}",
    }


# ── Bild-Ausspielung (Zuschnitt + Filter je Profil) ──────────────────────────
# Die Originalfotos bleiben unverändert im Speicher; Zielformat und Filter des
# Profils werden erst beim Teilen/Herunterladen angewendet. So sieht jeder
# Kanal immer gleich aus, ohne dass Originale verloren gehen.

# Seitenverhältnisse (Breite / Höhe)
_FORMAT_RATIOS = {"1:1": 1.0, "4:5": 4 / 5, "16:9": 16 / 9, "9:16": 9 / 16}

# Maximale Kantenlänge der Ausspielung (ausreichend für alle Kanäle)
MAX_AUSSPIELUNG_KANTE = 2048


def bearbeite_foto(data: bytes, bild_format: str = "original",
                   bild_filter: str = "kein") -> Tuple[bytes, str]:
    """
    Wendet Zielformat (mittiger Zuschnitt) und Filter auf ein Foto an.
    Liefert (JPEG-Bytes, "image/jpeg"). Bei "original"/"kein" wird nur
    dezent verkleinert und nach JPEG gewandelt (einheitliche Ausspielung).

    WICHTIG — Drehung: Handykameras speichern die Pixel so, wie der Sensor
    sitzt, und vermerken die nötige Drehung nur als EXIF-Feld "Orientation".
    Beim Neuspeichern als JPEG geht dieses Feld verloren. Ohne das Aufrichten
    unten kämen solche Fotos beim Empfänger (z.B. im Teilen-Dialog von
    Facebook) um 90 Grad gedreht an — in der App selbst sieht man nichts
    davon, weil dort das unveränderte Original ausgeliefert wird und der
    Browser die EXIF-Angabe berücksichtigt.
    """
    import io
    from PIL import Image, ImageEnhance, ImageOps

    img = Image.open(io.BytesIO(data))
    # Drehung aus dem EXIF in echte Pixel überführen — muss VOR dem Zuschnitt
    # passieren, sonst wird an der falschen Kante beschnitten. Bei Fotos ohne
    # Drehanweisung (Orientation = 1) ist der Aufruf wirkungslos.
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # 1. Zuschnitt auf das Zielformat (mittig)
    ratio = _FORMAT_RATIOS.get(bild_format)
    if ratio:
        b, h = img.size
        ist = b / h
        if ist > ratio:        # zu breit -> links/rechts beschneiden
            neu_b = int(h * ratio)
            x = (b - neu_b) // 2
            img = img.crop((x, 0, x + neu_b, h))
        elif ist < ratio:      # zu hoch -> oben/unten beschneiden
            neu_h = int(b / ratio)
            y = (h - neu_h) // 2
            img = img.crop((0, y, b, y + neu_h))

    # 2. Filter für gleichbleibende Anzeigequalität
    if bild_filter == "brillant":
        img = ImageOps.autocontrast(img, cutoff=1)
        img = ImageEnhance.Color(img).enhance(1.15)
        img = ImageEnhance.Sharpness(img).enhance(1.1)
    elif bild_filter == "warm":
        r, g, b_ = img.convert("RGB").split()
        r = r.point(lambda v: min(255, int(v * 1.06)))
        b_ = b_.point(lambda v: int(v * 0.94))
        img = Image.merge("RGB", (r, g, b_))
        img = ImageEnhance.Color(img).enhance(1.05)
    elif bild_filter == "kuehl":
        r, g, b_ = img.convert("RGB").split()
        r = r.point(lambda v: int(v * 0.94))
        b_ = b_.point(lambda v: min(255, int(v * 1.06)))
        img = Image.merge("RGB", (r, g, b_))
    elif bild_filter == "kontrast":
        img = ImageEnhance.Contrast(img).enhance(1.2)
    elif bild_filter == "sw":
        img = ImageOps.grayscale(img)

    # 3. Größe begrenzen und als JPEG ausgeben
    if max(img.size) > MAX_AUSSPIELUNG_KANTE:
        img.thumbnail((MAX_AUSSPIELUNG_KANTE, MAX_AUSSPIELUNG_KANTE))
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


# ── Video-Standbild (Poster) ──────────────────────────────────────────────────
def erzeuge_video_poster(video_bytes: bytes, dateiendung: str = ".mp4") -> Optional[bytes]:
    """
    Erzeugt mit ffmpeg ein Standbild (erstes Frame) als JPEG. So ist die Vorschau
    unabhängig davon, ob der Browser das Video-Format (z.B. iPhone-.mov/HEVC)
    selbst dekodieren kann. Liefert None bei Fehler (ffmpeg fehlt, Format nicht
    dekodierbar o.ä.) — der Video-Upload läuft dann trotzdem, nur ohne Poster.
    """
    tmp_in = tmp_out = None
    try:
        with tempfile.NamedTemporaryFile(suffix=dateiendung, delete=False) as f_in:
            f_in.write(video_bytes)
            tmp_in = f_in.name
        tmp_out = tmp_in + ".jpg"
        # Erstes Frame, Höhe auf max. 720 px begrenzt (Vorschau reicht)
        subprocess.run(  # nosec B603 - festes Kommando ohne Shell, Pfade selbst erzeugt
            ["ffmpeg", "-y", "-i", tmp_in, "-frames:v", "1",
             "-vf", "scale=-2:720", "-q:v", "3", tmp_out],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, check=True,
        )
        with open(tmp_out, "rb") as f:
            daten = f.read()
        return daten or None
    except Exception:
        return None
    finally:
        for pfad in (tmp_in, tmp_out):
            if pfad and os.path.exists(pfad):
                try:
                    os.remove(pfad)
                except Exception:
                    pass


# ── Datacenter-Ablage (Postecke) ──────────────────────────────────────────────
# Anhänge und Content eines Posts werden laufend ins Datacenter gespiegelt:
#   - ohne Kontakt: globaler Ordner "Postecke" (entity_type "postecke")
#   - mit Kontakt:  Unterordner "Postecke" beim Kontakt
# Gespiegelt werden der Content als Textdatei (Markdown) sowie – je nach Post –
# die Fotos ODER das Video als Kopien (kein Misch-Post). Die Spiegelung wird bei
# jeder Änderung synchronisiert (nur Neues rein, Gelöschtes/Verschobenes raus)
# und bleibt auch nach dem Löschen des Posts als Beleg erhalten.
# Marker in Attachment.description: "postecke:<post_id>#<teil>"
#   Teil = "text" | "foto:<foto_id>" | "video:<video_id>"

POSTECKE_ORDNER = "Postecke"

_ENDUNGEN = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
             "image/heic": ".heic", "image/heif": ".heif",
             "video/mp4": ".mp4", "video/quicktime": ".mov"}


def _safe(s: str) -> str:
    return "".join(c for c in (s or "") if c.isalnum() or c in "._- ").strip()


def _post_marker(post: SocialPost) -> str:
    """Prefix-Marker über alle Spiegelungen eines Posts."""
    return f"postecke:{post.id}"


def _teil_marker(post: SocialPost, teil: str) -> str:
    return f"postecke:{post.id}#{teil}"


def _hat_inhalt(post: SocialPost) -> bool:
    """True, sobald ein Post etwas Spiegelbares hat (kein leerer Entwurf)."""
    return bool(post.fotos or post.video
                or (post.text or "").strip()
                or (post.hashtags or "").strip()
                or (post.beschreibung or "").strip())


def _content_markdown(post: SocialPost, profil: Optional[SocialProfil]) -> str:
    """Content des Posts als lesbares Markdown fürs Datacenter."""
    def z(iso):
        return iso.strftime("%d.%m.%Y %H:%M") if iso else "—"
    zeilen = [
        f"# {post.titel or 'Social-Media-Post'}",
        "",
        f"- Profil: {profil.name if profil else '—'}"
        + (f" ({profil.kanal})" if profil else ""),
        f"- Kontakt: {post.kontakt_name or '—'}",
        f"- Ort: {post.ort or '—'}  ·  Gefühl: {post.gefuehl or '—'}",
        f"- Erstellt: {z(post.created_at)}  ·  Geplant: {z(post.geplant_am)}"
        f"  ·  Veröffentlicht: {z(post.veroeffentlicht_am)}",
        f"- KI-Modell: {post.ki_model or '—'}",
        "",
        "## Posttext",
        "",
        post.text or "—",
        "",
        post.hashtags or "",
    ]
    if (post.beschreibung or "").strip():
        zeilen += ["", "## Ursprüngliche Beschreibung", "", post.beschreibung.strip()]
    return "\n".join(zeilen).strip() + "\n"


def synchronisiere_datacenter(db: Session, post: SocialPost, user_id=None) -> int:
    """
    Hält die Datacenter-Spiegelung eines Posts aktuell (idempotent, beim
    Erstellen/Speichern sowie bei Foto-/Video-Änderungen aufgerufen).

    - Ordner "Postecke" (global) bzw. Kontakt-Unterordner "Postecke".
    - Content als Textdatei (wird bei jeder Änderung neu geschrieben).
    - Fotos/Video als Kopien: nur fehlende werden hochgeladen, verwaiste oder an
      den falschen Ort (Kontaktwechsel) gehörende Spiegelungen werden entfernt.
    - Große Videos werden dadurch NICHT bei jeder Textänderung neu hochgeladen.

    Liefert die Anzahl neu angelegter Anlagen. Die Attachments landen per
    db.flush() in der laufenden Transaktion des Aufrufers (der Aufrufer committet).
    """
    from app.models.attachment import Attachment

    # Leere Entwürfe nicht spiegeln
    if not _hat_inhalt(post):
        return 0

    profil = None
    if post.profil_id:
        profil = db.query(SocialProfil).filter(SocialProfil.id == post.profil_id).first()

    datum = (post.veroeffentlicht_am or post.geplant_am or post.created_at)
    basis = f"{datum.strftime('%Y-%m-%d')}_{_safe(post.titel or 'Post') or 'Post'}"

    if post.kontakt_id:
        _folder = storage_service.folder_name_for(db, post.kontakt_id, post.kontakt_name)
        key_prefix = f"kontakte/{_folder}/{POSTECKE_ORDNER}"
        entity_type, entity_id = "kontakte", post.kontakt_id
    else:
        key_prefix = f"postecke/{POSTECKE_ORDNER}/{post.id}"
        entity_type, entity_id = "postecke", post.id

    _backend = storage_service.current_backend(db)

    # Soll-Zustand: welche Teile soll es geben?
    soll_teile = {"text"}
    for foto in (post.fotos or []):
        soll_teile.add(f"foto:{foto.id}")
    if post.video is not None:
        soll_teile.add(f"video:{post.video.id}")

    # Bestehende Spiegelungen dieses Posts (Prefix-Marker deckt auch Altbestand
    # mit reinem "postecke:<id>" ohne #Teil ab -> wird migriert).
    vorhandene = (db.query(Attachment)
                  .filter(Attachment.description.like(f"{_post_marker(post)}%")).all())

    def _teil_of(a) -> str:
        d = a.description or ""
        return d.split("#", 1)[1] if "#" in d else ""

    vorhandene_teile = set()
    # 1. Verwaiste / falsch platzierte / Text-Spiegelungen entfernen
    for a in vorhandene:
        teil = _teil_of(a)
        falscher_ort = not (a.storage_key or "").startswith(key_prefix + "/")
        # "text" immer neu schreiben (Content kann sich geändert haben)
        if teil == "text" or teil not in soll_teile or falscher_ort:
            try:
                # Aus dem Speicher löschen, in dem die Spiegelung tatsächlich
                # liegt (seit Migration 0039 je Anlage vermerkt) — sonst bleiben
                # nach einem Speicherwechsel Dateileichen zurück.
                storage_service.delete_file(a.storage_key, db,
                                            backend=a.storage_provider)
            except Exception:
                pass
            db.delete(a)
        else:
            vorhandene_teile.add(teil)
    db.flush()

    anzahl = 0

    def _anlage(teil, storage_key, daten, mimetype, filename, anzeige):
        nonlocal anzahl
        storage_service.upload_file(storage_key, daten, mimetype, db=db, backend=_backend)
        db.add(Attachment(
            entity_type=entity_type, entity_id=entity_id,
            type="file", storage_key=storage_key, storage_provider=_backend,
            filename=filename, filesize=len(daten), mimetype=mimetype,
            display_name=anzeige, description=_teil_marker(post, teil),
            contact_id=post.kontakt_id, contact_name=post.kontakt_name,
            folder=POSTECKE_ORDNER, uploaded_by=user_id,
        ))
        anzahl += 1

    # 2. Content immer (neu) schreiben
    md = _content_markdown(post, profil).encode("utf-8")
    _anlage("text", f"{key_prefix}/{basis}.md", md, "text/markdown",
            f"{basis}.md", f"{post.titel or 'Post'} · Text")

    # 3. Fotos — nur fehlende hinzufügen (bereits gespiegelte bleiben)
    for i, foto in enumerate(post.fotos or [], start=1):
        if f"foto:{foto.id}" in vorhandene_teile:
            continue
        try:
            daten, _ct = storage_service.download_file(
                foto.storage_key, db, backend=foto.storage_provider)
        except Exception:
            continue  # fehlendes Einzelfoto bricht die Spiegelung nicht ab
        endung = _ENDUNGEN.get(foto.mimetype, ".jpg")
        fname = f"{basis}_Foto{i}{endung}"
        _anlage(f"foto:{foto.id}", f"{key_prefix}/{fname}", daten,
                foto.mimetype or "image/jpeg", fname, f"{post.titel or 'Post'} · Foto {i}")

    # 4. Video — nur wenn noch nicht gespiegelt (kein Re-Upload bei Textänderung)
    if post.video is not None and f"video:{post.video.id}" not in vorhandene_teile:
        try:
            daten, _ct = storage_service.download_file(
                post.video.storage_key, db, backend=post.video.storage_provider)
            endung = _ENDUNGEN.get(post.video.mimetype, ".mp4")
            fname = f"{basis}_Video{endung}"
            _anlage(f"video:{post.video.id}", f"{key_prefix}/{fname}", daten,
                    post.video.mimetype or "video/mp4", fname, f"{post.titel or 'Post'} · Video")
        except Exception:
            pass  # fehlendes Video bricht die Spiegelung nicht ab

    db.flush()
    return anzahl
