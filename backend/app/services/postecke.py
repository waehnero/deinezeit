"""
Postecke-Service: KI-Generierung von Post-Vorschlägen (Etappe 1)
================================================================

Baut aus den Fotos eines Posts, der Nutzerbeschreibung und dem Stil-Prompt
des Zielprofils einen Prompt und ruft den zentral konfigurierten KI-Provider
auf (services/ki.py — Einstellungen -> System -> KI & Mail-Importer).
"""

import json
import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.postecke import SocialPost, SocialProfil
from app.services import storage_service
from app.services.ki import call_ki, load_ki_settings, KI_DEFAULT_MODELS

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
    for foto in (post.fotos or [])[:MAX_FOTOS_FUER_KI]:
        try:
            data, _ct = storage_service.download_file(foto.storage_key, db)
            bilder.append((data, foto.mimetype or "image/jpeg"))
        except Exception:
            continue  # fehlendes Einzelfoto bricht die Generierung nicht ab
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

    antwort = call_ki(ki, prompt, images=_lade_fotos(db, post), max_tokens=2000)
    data = _parse_ki_json(antwort)
    if not data or not (data.get("text") or "").strip():
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


# ── Datacenter-Postsarchiv ────────────────────────────────────────────────────
# Beim Archivieren wird der Post (Content als Markdown + alle Fotos als Kopien)
# ins Datacenter gespiegelt: mit Kontakt unter dem Kontakt-Ordner, sonst global —
# jeweils im Unterordner "Postsarchiv" (analog zum Beleg-Archiv des Verkaufs).
# Der Marker in Attachment.description ("postecke:<id>") verknüpft die Spiegelung
# mit dem Post, damit die Wiederherstellung sie wieder entfernen kann.

ARCHIV_ORDNER = "Postsarchiv"

_ENDUNGEN = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
             "image/heic": ".heic", "image/heif": ".heif"}


def _safe(s: str) -> str:
    return "".join(c for c in (s or "") if c.isalnum() or c in "._- ").strip()


def _archiv_marker(post: SocialPost) -> str:
    return f"postecke:{post.id}"


def _archiv_markdown(post: SocialPost, profil: Optional[SocialProfil]) -> str:
    """Content des Posts als lesbares Markdown fürs Archiv."""
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


def archiviere_ins_datacenter(db: Session, post: SocialPost,
                              user_id=None) -> int:
    """
    Spiegelt einen Post ins Datacenter (Markdown + Foto-Kopien).
    Liefert die Anzahl angelegter Anlagen (0, wenn schon vorhanden).
    Die Attachments werden per db.flush() in die laufende Transaktion des
    Aufrufers eingefügt (der Aufrufer committet).
    """
    from app.models.attachment import Attachment

    marker = _archiv_marker(post)
    if db.query(Attachment).filter(Attachment.description == marker).first():
        return 0  # bereits gespiegelt

    profil = None
    if post.profil_id:
        profil = db.query(SocialProfil).filter(SocialProfil.id == post.profil_id).first()

    datum = (post.veroeffentlicht_am or post.geplant_am or post.created_at)
    basis = f"{datum.strftime('%Y-%m-%d')}_{_safe(post.titel or 'Post') or 'Post'}"

    if post.kontakt_id:
        key_prefix = f"kontakte/{post.kontakt_id}/{ARCHIV_ORDNER}"
        entity_type, entity_id = "kontakte", post.kontakt_id
    else:
        key_prefix = f"postecke-archiv/{post.id}"
        entity_type, entity_id = "postecke", post.id

    def _anlage(storage_key, daten, mimetype, filename, anzeige):
        storage_service.upload_file(storage_key, daten, mimetype, db=db)
        db.add(Attachment(
            entity_type=entity_type, entity_id=entity_id,
            type="file", storage_key=storage_key,
            filename=filename, filesize=len(daten), mimetype=mimetype,
            display_name=anzeige, description=marker,
            contact_id=post.kontakt_id, contact_name=post.kontakt_name,
            folder=ARCHIV_ORDNER, uploaded_by=user_id,
        ))

    anzahl = 0
    # 1. Content als Markdown
    md = _archiv_markdown(post, profil).encode("utf-8")
    _anlage(f"{key_prefix}/{basis}.md", md, "text/markdown",
            f"{basis}.md", f"{post.titel or 'Post'} · Text")
    anzahl += 1

    # 2. Fotos als Kopien (unabhängig vom Post-Speicher, Archiv bleibt
    #    auch nach endgültigem Löschen des Posts erhalten)
    for i, foto in enumerate(post.fotos or [], start=1):
        try:
            daten, _ct = storage_service.download_file(foto.storage_key, db)
        except Exception:
            continue  # fehlendes Einzelfoto bricht das Archiv nicht ab
        endung = _ENDUNGEN.get(foto.mimetype, ".jpg")
        fname = f"{basis}_Foto{i}{endung}"
        _anlage(f"{key_prefix}/{fname}", daten, foto.mimetype or "image/jpeg",
                fname, f"{post.titel or 'Post'} · Foto {i}")
        anzahl += 1

    db.flush()
    return anzahl


def entferne_datacenter_archiv(db: Session, post: SocialPost) -> int:
    """Entfernt die Datacenter-Spiegelung eines Posts (bei Wiederherstellung)."""
    from app.models.attachment import Attachment

    anlagen = (db.query(Attachment)
               .filter(Attachment.description == _archiv_marker(post)).all())
    for a in anlagen:
        try:
            storage_service.delete_file(a.storage_key, db)
        except Exception:
            pass
        db.delete(a)
    db.flush()
    return len(anlagen)
