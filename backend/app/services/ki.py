"""
Gemeinsamer KI-Service (Provider-Abstraktion)
=============================================

Zentrale Anlaufstelle für alle Module, die den konfigurierten KI-Provider
nutzen (Mail-Importer, Postecke, ...). Die Einstellungen (Provider, API-Key,
Modell) werden unter dem Setting-Key "ki_settings" gespeichert und über
Einstellungen -> System -> KI & Mail-Importer gepflegt.

Funktionsumfang:
  1. Verschlüsselung von Geheimnissen (Fernet, Schlüssel aus SECRET_KEY)
  2. Laden/Speichern der KI-Einstellungen
  3. call_ki(): generischer Provider-Aufruf (Anthropic oder OpenAI),
     optional mit Bildern (Vision) — z.B. Fotos für Social-Media-Posts.

Alle Funktionen sind synchron — FastAPI führt sync-Endpunkte im Threadpool aus.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.settings import Setting

KI_SETTINGS_KEY = "ki_settings"
KI_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}

# Bilder werden vor der Übergabe an die KI verkleinert (Kosten/Kontext).
MAX_BILD_KANTE = 1568


# ── 1. Verschlüsselung ────────────────────────────────────────────────────────
def _fernet() -> Fernet:
    """Fernet-Schlüssel deterministisch aus SECRET_KEY ableiten."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(enc: str) -> str:
    return _fernet().decrypt(enc.encode()).decode()


# ── 2. KI-Einstellungen ───────────────────────────────────────────────────────
def load_ki_settings(db: Session) -> dict:
    """{provider, api_key_enc, model} — api_key_enc bleibt verschlüsselt."""
    row = db.query(Setting).filter(Setting.key == KI_SETTINGS_KEY).first()
    if not row or not row.value:
        return {"provider": "anthropic", "api_key_enc": None, "model": None}
    try:
        return json.loads(row.value)
    except Exception:
        return {"provider": "anthropic", "api_key_enc": None, "model": None}


def save_ki_settings(db: Session, provider: str, api_key_plain: Optional[str],
                     model: Optional[str]):
    """Speichert die KI-Einstellungen; ohne neuen Key bleibt der alte erhalten."""
    current = load_ki_settings(db)
    value = {
        "provider": provider,
        "api_key_enc": encrypt_secret(api_key_plain) if api_key_plain else current.get("api_key_enc"),
        "model": model or None,
    }
    row = db.query(Setting).filter(Setting.key == KI_SETTINGS_KEY).first()
    if row:
        row.value = json.dumps(value)
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=KI_SETTINGS_KEY, value=json.dumps(value),
                       updated_at=datetime.now(timezone.utc)))
    db.commit()


# ── 3. Bild-Aufbereitung ──────────────────────────────────────────────────────
def _bild_verkleinern(data: bytes, mimetype: str) -> Tuple[bytes, str]:
    """
    Verkleinert ein Bild auf max. MAX_BILD_KANTE Pixel Kantenlänge und wandelt
    es nach JPEG (spart Tokens/Kosten). Schlägt die Verarbeitung fehl, wird
    das Original unverändert zurückgegeben.
    """
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_BILD_KANTE:
            img.thumbnail((MAX_BILD_KANTE, MAX_BILD_KANTE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mimetype


# ── 4. Provider-Aufruf ────────────────────────────────────────────────────────
def _api_fehlertext(provider: str, resp: httpx.Response) -> str:
    """Baut eine verständliche Fehlermeldung aus einer Provider-Fehlerantwort."""
    detail = ""
    try:
        daten = resp.json()
        detail = (daten.get("error") or {}).get("message") or ""
    except Exception:
        detail = resp.text[:200]
    hinweis = ""
    if resp.status_code == 401:
        hinweis = " — API-Key prüfen (Einstellungen -> System -> KI & Mail-Importer)"
    elif resp.status_code == 404:
        hinweis = " — Modellname prüfen (Einstellungen -> System -> KI & Mail-Importer)"
    return f"KI-Provider {provider}: HTTP {resp.status_code}{hinweis}. {detail}".strip()


def _post_mit_fehlerbehandlung(url: str, provider: str, **kwargs) -> httpx.Response:
    try:
        resp = httpx.post(url, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.HTTPStatusError as e:
        raise RuntimeError(_api_fehlertext(provider, e.response))
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"KI-Provider {provider} nicht erreichbar ({e.__class__.__name__}) — "
            "Internetzugang des Backends prüfen")


def call_ki(ki: dict, prompt: str,
            images: Optional[List[Tuple[bytes, str]]] = None,
            max_tokens: int = 1500) -> str:
    """
    Ruft den konfigurierten KI-Provider auf und liefert den Antworttext.

    ki      dict aus load_ki_settings() (api_key_enc verschlüsselt)
    prompt  Nutzertext/Anweisung
    images  optionale Liste [(bytes, mimetype), ...] — wird als Vision-Input
            übergeben (beide Provider unterstützen Base64-Bilder)
    """
    if not ki.get("api_key_enc"):
        raise RuntimeError(
            "Kein KI-API-Key konfiguriert (Einstellungen -> System -> KI & Mail-Importer)")
    api_key = decrypt_secret(ki["api_key_enc"])
    provider = ki.get("provider") or "anthropic"
    model = ki.get("model") or KI_DEFAULT_MODELS.get(provider, KI_DEFAULT_MODELS["anthropic"])

    bilder: List[Tuple[bytes, str]] = []
    unterstuetzt = ("image/jpeg", "image/png", "image/gif", "image/webp")
    for data, mimetype in (images or []):
        data, mimetype = _bild_verkleinern(data, mimetype)
        if mimetype not in unterstuetzt:
            # z.B. HEIC, das Pillow nicht konvertieren konnte
            raise RuntimeError(
                f"Fotoformat {mimetype} wird vom KI-Provider nicht unterstützt — "
                "bitte das Foto als JPEG/PNG hochladen")
        bilder.append((data, mimetype))

    if provider == "anthropic":
        content = []
        for data, mimetype in bilder:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mimetype,
                    "data": base64.b64encode(data).decode(),
                },
            })
        content.append({"type": "text", "text": prompt})
        resp = _post_mit_fehlerbehandlung(
            "https://api.anthropic.com/v1/messages", provider,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=120,
        )
        return "".join(b.get("text", "") for b in resp.json().get("content", []))

    # openai
    content = []
    for data, mimetype in bilder:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mimetype};base64,{base64.b64encode(data).decode()}"},
        })
    content.append({"type": "text", "text": prompt})
    resp = _post_mit_fehlerbehandlung(
        "https://api.openai.com/v1/chat/completions", provider,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
        },
        timeout=120,
    )
    return resp.json()["choices"][0]["message"]["content"]
