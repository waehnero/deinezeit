"""
Social-Publish-Service – Direktanbindung von Social-Media-Kanälen (Etappe 3)
============================================================================

Kanalneutrale Veröffentlichung vorbereiteter Posts. Aktuell angebunden:

  facebook_seite  Facebook-Seiten über die Graph API. Voraussetzung: eigene
                  Meta-App im Entwicklermodus + langlebiger Page-Access-Token
                  (Anleitung: FACEBOOK-SEITE-ANBINDEN.md). Kein App-Review
                  nötig, solange nur selbst verwaltete Seiten bespielt werden.

Weitere Kanäle (LinkedIn, Instagram Business, ...) werden später ergänzt —
einfach eine Publish-Funktion schreiben und in KANAL_PUBLISHER eintragen.
Kanäle ohne Eintrag behalten das assistierte Posten.

Zugangsdaten liegen verschlüsselt in SocialProfil.zugang_enc (Fernet, wie
alle Geheimnisse — services/ki.py). Für Facebook-Seiten als JSON:
  {"page_id": "...", "page_token": "..."}

Der Hintergrund-Worker veröffentlicht fällige geplante Posts automatisch
(gleiches Muster wie der Wiederkehr-Worker der Rechnungen; in Tests
deaktiviert). Fehler landen am Post (publish_error) und sind in der
Oberfläche sichtbar; es wird beim nächsten Lauf erneut versucht.
"""

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.postecke import SocialPost, SocialProfil
from app.services import storage_service
from app.services.ki import decrypt_secret, encrypt_secret  # noqa: F401 (encrypt für API)
from app.services.postecke import bearbeite_foto

GRAPH_API = "https://graph.facebook.com/v25.0"

# Wie oft der Worker nach fälligen Posts schaut (Sekunden)
WORKER_INTERVALL = 120


# ── Öffentliche, kurzlebig signierte Medien-URLs ──────────────────────────────
# Instagram lädt Foto/Video NICHT hoch, sondern holt sie von einer öffentlich
# erreichbaren URL. Da unsere Medien privat liegen, liefert ein auth-freier
# Endpunkt (api/oeffentlich.py) sie über einen signierten, zeitlich begrenzten
# Token aus (HMAC über SECRET_KEY — keine DB-Persistenz nötig).
def _medien_sig(msg: str) -> str:
    roh = hmac.new(settings.SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(roh).decode().rstrip("=")[:32]


def signiere_medien_token(art: str, media_id: str, ttl: int = 3600) -> str:
    """Signierter Token 'art.media_id.exp.sig' (art = 'foto' | 'video')."""
    exp = int(time.time()) + ttl
    msg = f"{art}.{media_id}.{exp}"
    return f"{msg}.{_medien_sig(msg)}"


def pruefe_medien_token(token: str):
    """Liefert (art, media_id) bei gültigem, nicht abgelaufenem Token, sonst None."""
    teile = (token or "").split(".")
    if len(teile) != 4:
        return None
    art, media_id, exp, sig = teile
    if not hmac.compare_digest(sig, _medien_sig(f"{art}.{media_id}.{exp}")):
        return None
    try:
        if int(exp) < int(time.time()):
            return None
    except ValueError:
        return None
    return art, media_id


def oeffentliche_medien_url(art: str, media_id: str, ttl: int = 3600) -> str:
    """Öffentliche Abruf-URL eines Mediums (für Instagram-Server)."""
    token = signiere_medien_token(art, media_id, ttl)
    basis = settings.FRONTEND_URL.rstrip("/")
    return f"{basis}/api/oeffentlich/postecke/medien/{token}"


# ── Zugangsdaten ──────────────────────────────────────────────────────────────
def lade_zugang(profil: SocialProfil) -> Optional[dict]:
    """Entschlüsselt die Zugangsdaten eines Profils (None, wenn keine da)."""
    if not profil or not profil.zugang_enc:
        return None
    try:
        return json.loads(decrypt_secret(profil.zugang_enc))
    except Exception:
        return None


def hat_direktanbindung(profil: Optional[SocialProfil]) -> bool:
    """True, wenn der Kanal angebunden ist UND Zugangsdaten hinterlegt sind."""
    return (profil is not None
            and profil.kanal in KANAL_PUBLISHER
            and bool(profil.zugang_enc))


# ── Facebook-Seite (Graph API) ────────────────────────────────────────────────
def _fb_fehlertext(resp: httpx.Response) -> str:
    try:
        fehler = resp.json().get("error", {})
        text = fehler.get("message") or resp.text[:200]
        if fehler.get("code") == 190:
            text += " — Page-Access-Token abgelaufen/ungültig, bitte im Profil erneuern"
        return f"Facebook: {text}"
    except Exception:
        return f"Facebook: HTTP {resp.status_code}"


def teste_verbindung_fb_seite(zugang: dict) -> dict:
    """Prüft Seiten-ID + Token; liefert {ok, message}."""
    try:
        resp = httpx.get(
            f"{GRAPH_API}/{zugang.get('page_id')}",
            params={"fields": "name", "access_token": zugang.get("page_token")},
            timeout=20,
        )
        if resp.status_code != 200:
            return {"ok": False, "message": _fb_fehlertext(resp)}
        name = resp.json().get("name", "?")
        return {"ok": True, "message": f"Verbunden mit Seite „{name}“"}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"Facebook nicht erreichbar ({e.__class__.__name__})"}


def _publiziere_fb_seite_video(db: Session, post: SocialPost, profil: SocialProfil,
                               page_id: str, token: str) -> str:
    """
    Veröffentlicht ein Video auf einer Facebook-Seite über den /videos-Endpunkt.
    Text + Hashtags werden als Videobeschreibung übertragen. Video wird
    unverändert (kein Filter/Zuschnitt) hochgeladen. Liefert die Beitrags-URL.
    """
    video = post.video
    beschreibung = "\n\n".join(t for t in (post.text, post.hashtags) if t) or ""
    daten, _ct = storage_service.download_file(video.storage_key, db)
    resp = httpx.post(
        f"{GRAPH_API}/{page_id}/videos",
        data={"description": beschreibung, "access_token": token},
        files={"source": (video.filename, daten, video.mimetype or "video/mp4")},
        timeout=600,  # große Uploads brauchen länger
    )
    if resp.status_code != 200:
        raise RuntimeError(_fb_fehlertext(resp))
    video_id = resp.json().get("id", "")
    return f"https://www.facebook.com/{video_id}" if video_id else ""


def _publiziere_fb_seite(db: Session, post: SocialPost, profil: SocialProfil) -> str:
    """
    Veröffentlicht einen Post auf einer Facebook-Seite. Enthält der Post ein
    Video, wird der Video-Weg (/videos) genutzt, sonst der Foto-/Text-Weg
    (kein Misch-Post). Liefert die URL des Facebook-Beitrags.
    """
    zugang = lade_zugang(profil)
    if not zugang or not zugang.get("page_id") or not zugang.get("page_token"):
        raise RuntimeError("Keine Zugangsdaten hinterlegt (Profil bearbeiten -> Seiten-ID/Token)")
    page_id, token = zugang["page_id"], zugang["page_token"]

    # Video-Post: eigener Endpunkt, keine Fotos, kein Filter/Zuschnitt
    if getattr(post, "video", None) is not None:
        return _publiziere_fb_seite_video(db, post, profil, page_id, token)

    text = "\n\n".join(t for t in (post.text, post.hashtags) if t) or ""

    # 1. Fotos einzeln (unveröffentlicht) hochladen -> media_fbids
    media_ids = []
    for foto in (post.fotos or []):
        daten, _ct = storage_service.download_file(foto.storage_key, db)
        try:
            daten, mimetype = bearbeite_foto(
                daten, profil.bild_format or "original", profil.bild_filter or "kein")
        except Exception:
            mimetype = foto.mimetype or "image/jpeg"
        resp = httpx.post(
            f"{GRAPH_API}/{page_id}/photos",
            data={"published": "false", "access_token": token},
            files={"source": (foto.filename, daten, mimetype)},
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(_fb_fehlertext(resp))
        media_ids.append(resp.json()["id"])

    # 2. Beitrag anlegen (mit angehängten Fotos)
    daten_feed = {"message": text, "access_token": token}
    for i, mid in enumerate(media_ids):
        daten_feed[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
    resp = httpx.post(f"{GRAPH_API}/{page_id}/feed", data=daten_feed, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(_fb_fehlertext(resp))

    beitrag_id = resp.json().get("id", "")
    return f"https://www.facebook.com/{beitrag_id}" if beitrag_id else ""


# Kanal -> Publish-Funktion (weitere Kanäle hier ergänzen)
# ── Instagram (Graph API, Content Publishing) ─────────────────────────────────
# Voraussetzung: Instagram-Professionell-Konto (Business/Creator), verknüpft mit
# einer Facebook-Seite; gleiche Meta-App im Entwicklermodus (kein Review, solange
# nur das eigene Konto bespielt wird). Zugang: {ig_user_id, ig_token}.
# Ablauf: Container anlegen (Foto/Reel/Carousel) -> bei Video auf Verarbeitung
# warten -> veröffentlichen. Medien holt Instagram über oeffentliche_medien_url.
IG_POLL_MAX = 30            # max. Statusabfragen bei der Video-Verarbeitung
IG_POLL_INTERVALL = 4      # Sekunden zwischen den Abfragen


def _ig_fehlertext(resp: httpx.Response) -> str:
    try:
        fehler = resp.json().get("error", {})
        text = fehler.get("message") or resp.text[:200]
        if fehler.get("code") == 190:
            text += " — Access-Token abgelaufen/ungültig, bitte im Profil erneuern"
        return f"Instagram: {text}"
    except Exception:
        return f"Instagram: HTTP {resp.status_code}"


def teste_verbindung_instagram(zugang: dict) -> dict:
    """Prüft ig_user_id + Token; liefert {ok, message}."""
    try:
        resp = httpx.get(
            f"{GRAPH_API}/{zugang.get('ig_user_id')}",
            params={"fields": "username", "access_token": zugang.get("ig_token")},
            timeout=20,
        )
        if resp.status_code != 200:
            return {"ok": False, "message": _ig_fehlertext(resp)}
        name = resp.json().get("username", "?")
        return {"ok": True, "message": f"Verbunden mit @{name}"}
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"Instagram nicht erreichbar ({e.__class__.__name__})"}


def _ig_container(ig_user: str, token: str, params: dict) -> str:
    """Legt einen Media-Container an und liefert dessen creation_id."""
    resp = httpx.post(f"{GRAPH_API}/{ig_user}/media",
                      data={**params, "access_token": token}, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(_ig_fehlertext(resp))
    return resp.json()["id"]


def _ig_warte_auf_verarbeitung(creation_id: str, token: str) -> None:
    """Wartet, bis ein (Video-)Container fertig verarbeitet ist."""
    for _ in range(IG_POLL_MAX):
        resp = httpx.get(f"{GRAPH_API}/{creation_id}",
                         params={"fields": "status_code", "access_token": token}, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(_ig_fehlertext(resp))
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError("Instagram: Video-Verarbeitung fehlgeschlagen")
        time.sleep(IG_POLL_INTERVALL)
    raise RuntimeError("Instagram: Zeitüberschreitung bei der Video-Verarbeitung")


def _ig_veroeffentliche(ig_user: str, token: str, creation_id: str) -> str:
    """Veröffentlicht einen fertigen Container; liefert die Permalink-URL."""
    resp = httpx.post(f"{GRAPH_API}/{ig_user}/media_publish",
                      data={"creation_id": creation_id, "access_token": token}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(_ig_fehlertext(resp))
    media_id = resp.json().get("id", "")
    try:
        pl = httpx.get(f"{GRAPH_API}/{media_id}",
                       params={"fields": "permalink", "access_token": token}, timeout=20)
        if pl.status_code == 200:
            return pl.json().get("permalink", "") or ""
    except Exception:
        pass
    return ""


def _publiziere_instagram(db: Session, post: SocialPost, profil: SocialProfil) -> str:
    """
    Veröffentlicht einen Post auf Instagram: Einzel-Foto, Reel (Video) oder
    Carousel (mehrere Fotos). Da ein Post entweder Fotos ODER ein Video hat,
    entsteht kein gemischtes Carousel. Liefert die Permalink-URL.
    """
    zugang = lade_zugang(profil)
    if not zugang or not zugang.get("ig_user_id") or not zugang.get("ig_token"):
        raise RuntimeError("Keine Instagram-Zugangsdaten hinterlegt (Profil bearbeiten -> Konto-ID/Token)")
    ig_user, token = zugang["ig_user_id"], zugang["ig_token"]
    caption = "\n\n".join(t for t in (post.text, post.hashtags) if t) or ""

    # Video -> Reel
    if getattr(post, "video", None) is not None:
        url = oeffentliche_medien_url("video", str(post.video.id))
        creation = _ig_container(ig_user, token,
                                 {"media_type": "REELS", "video_url": url, "caption": caption})
        _ig_warte_auf_verarbeitung(creation, token)
        return _ig_veroeffentliche(ig_user, token, creation)

    fotos = list(post.fotos or [])
    if not fotos:
        raise RuntimeError("Instagram: Der Post hat weder Foto noch Video")

    # Einzel-Foto
    if len(fotos) == 1:
        url = oeffentliche_medien_url("foto", str(fotos[0].id))
        creation = _ig_container(ig_user, token, {"image_url": url, "caption": caption})
        return _ig_veroeffentliche(ig_user, token, creation)

    # Carousel (2–10 Fotos): Kind-Container -> Carousel-Container
    kinder = []
    for foto in fotos[:10]:
        url = oeffentliche_medien_url("foto", str(foto.id))
        kinder.append(_ig_container(ig_user, token,
                                    {"image_url": url, "is_carousel_item": "true"}))
    creation = _ig_container(ig_user, token,
                             {"media_type": "CAROUSEL", "caption": caption,
                              "children": ",".join(kinder)})
    return _ig_veroeffentliche(ig_user, token, creation)


KANAL_PUBLISHER = {
    "facebook_seite": _publiziere_fb_seite,
    "instagram": _publiziere_instagram,
}

KANAL_VERBINDUNGSTEST = {
    "facebook_seite": teste_verbindung_fb_seite,
    "instagram": teste_verbindung_instagram,
}


# ── Veröffentlichen ───────────────────────────────────────────────────────────
def publiziere(db: Session, post: SocialPost, profil: SocialProfil) -> str:
    """
    Veröffentlicht einen Post über die Direktanbindung seines Profils und
    aktualisiert Status/Zeitstempel/extern_url. Wirft RuntimeError mit
    verständlicher Meldung, wenn etwas schiefgeht (Post bleibt unverändert).
    """
    publisher = KANAL_PUBLISHER.get(profil.kanal if profil else "")
    if not publisher:
        raise RuntimeError(f"Kanal {profil.kanal if profil else '?'} hat keine Direktanbindung")

    extern_url = publisher(db, post, profil)
    post.status = "veroeffentlicht"
    post.veroeffentlicht_am = datetime.now(timezone.utc)
    post.extern_url = extern_url or None
    post.publish_error = None
    return extern_url


# ── Hintergrund-Worker für geplante Posts ─────────────────────────────────────
def veroeffentliche_faellige(db: Session) -> int:
    """
    Veröffentlicht alle fälligen geplanten Posts mit Direktanbindung.
    Fehler werden am Post vermerkt (publish_error) — der Post bleibt
    "geplant" und wird beim nächsten Lauf erneut versucht.
    Liefert die Anzahl erfolgreich veröffentlichter Posts.
    """
    jetzt = datetime.now(timezone.utc)
    faellige = (db.query(SocialPost)
                .filter(SocialPost.status == "geplant",
                        SocialPost.geplant_am.isnot(None),
                        SocialPost.geplant_am <= jetzt).all())
    anzahl = 0
    for post in faellige:
        profil = None
        if post.profil_id:
            profil = db.query(SocialProfil).filter(SocialProfil.id == post.profil_id).first()
        if not hat_direktanbindung(profil):
            continue  # assistierte Kanäle: bleibt geplant (Erinnerung folgt in eigener Etappe)
        try:
            publiziere(db, post, profil)
            anzahl += 1
            print(f"[INFO] Postecke: Post {post.id} automatisch veröffentlicht")
        except Exception as e:
            post.publish_error = str(e)[:1000]
            print(f"[WARN] Postecke: Post {post.id} konnte nicht veröffentlicht werden: {e}")
        db.commit()
    return anzahl


_worker_started = False


def _worker_loop():
    from app.db.base import SessionLocal
    while True:
        time.sleep(WORKER_INTERVALL)
        try:
            db = SessionLocal()
            try:
                veroeffentliche_faellige(db)
            finally:
                db.close()
        except Exception as e:
            print(f"[WARN] Postecke-Worker: {e}")


def start_postecke_worker():
    """Startet den Publish-Thread (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_POSTECKE_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="postecke-publish").start()
