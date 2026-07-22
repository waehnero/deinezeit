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

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.postecke import SocialPost, SocialProfil
from app.services import storage_service
from app.services.ki import decrypt_secret, encrypt_secret  # noqa: F401 (encrypt für API)
from app.services.postecke import bearbeite_foto

GRAPH_API = "https://graph.facebook.com/v25.0"

# Wie oft der Worker nach fälligen Posts schaut (Sekunden)
WORKER_INTERVALL = 120


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


def _publiziere_fb_seite(db: Session, post: SocialPost, profil: SocialProfil) -> str:
    """
    Veröffentlicht einen Post mit Fotos auf einer Facebook-Seite.
    Fotos werden in der Ausspielungs-Variante des Profils übertragen
    (Zielformat + Filter). Liefert die URL des Facebook-Posts.
    """
    zugang = lade_zugang(profil)
    if not zugang or not zugang.get("page_id") or not zugang.get("page_token"):
        raise RuntimeError("Keine Zugangsdaten hinterlegt (Profil bearbeiten -> Seiten-ID/Token)")
    page_id, token = zugang["page_id"], zugang["page_token"]

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
KANAL_PUBLISHER = {
    "facebook_seite": _publiziere_fb_seite,
}

KANAL_VERBINDUNGSTEST = {
    "facebook_seite": teste_verbindung_fb_seite,
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
