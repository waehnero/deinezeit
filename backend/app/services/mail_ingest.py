"""
Mail-Ingest-Service (Aufgabenmodul, Etappe 3)
=============================================

Aufgabenbereiche:
  1. Verschlüsselung der Mail-Zugangsdaten (Fernet, Schlüssel aus SECRET_KEY)
  2. Nachrichten abrufen: IMAP (Standardbibliothek) und Microsoft Graph (httpx)
  3. KI-Extraktion von Aufgabenvorschlägen (Anthropic oder OpenAI, konfigurierbar
     über Setting-Key "ki_settings")
  4. scan_account(): neue Nachrichten eines Kontos analysieren -> Vorschläge
  5. Hintergrund-Scanner (Thread), der Auto-Scan-Konten periodisch abarbeitet

Alle Funktionen sind synchron — FastAPI führt sync-Endpunkte im Threadpool aus,
der Hintergrund-Scanner läuft in einem eigenen Daemon-Thread.
"""

import base64
import hashlib
import imaplib
import email
import email.header
import email.utils
import json
import re
import threading
import time
import os
from datetime import datetime, timezone, timedelta, date
from typing import List, Optional

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mailimport import MailAccount, MailTaskSuggestion
from app.models.settings import Setting

# Wie viele Nachrichten pro Scan maximal betrachtet werden (neueste zuerst)
MAX_MESSAGES_PER_SCAN = 25
# Wie viel Mail-Text der KI übergeben wird (Kosten-/Kontextbegrenzung)
MAX_BODY_CHARS = 6000

KI_SETTINGS_KEY = "ki_settings"
KI_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}


# ── 1. Verschlüsselung ────────────────────────────────────────────────────────
def _fernet() -> Fernet:
    """Fernet-Schlüssel deterministisch aus SECRET_KEY ableiten."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(enc: str) -> str:
    return _fernet().decrypt(enc.encode()).decode()


# ── Zentrale E-Mail-Konfiguration (Einstellungen -> System -> E-Mail) ────────
def _settings_dict(db: Session, keys: List[str]) -> dict:
    rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
    return {r.key: (r.value or "") for r in rows}


def _imap_credentials(db: Session, account: MailAccount) -> tuple:
    """(user, password) — kontoeigen oder aus der zentralen SMTP-Konfiguration."""
    if account.use_central_credentials:
        s = _settings_dict(db, ["smtp_user", "smtp_password"])
        user, password = s.get("smtp_user", ""), s.get("smtp_password", "")
        if not user or not password:
            raise RuntimeError(
                "Zentrale E-Mail-Zugangsdaten fehlen (Einstellungen -> System -> E-Mail)")
        return user, password
    if not account.secret_enc:
        raise RuntimeError("Für dieses Konto ist kein Passwort hinterlegt")
    return account.imap_user, decrypt_secret(account.secret_enc)


def _graph_credentials(db: Session, account: MailAccount) -> tuple:
    """(tenant_id, client_id, client_secret, mailbox) — kontoeigen oder zentral."""
    if account.use_central_credentials:
        s = _settings_dict(db, ["ms_tenant_id", "ms_client_id",
                                "ms_client_secret", "smtp_from_email"])
        tenant, client, secret = s.get("ms_tenant_id"), s.get("ms_client_id"), s.get("ms_client_secret")
        if not (tenant and client and secret):
            raise RuntimeError(
                "Zentrale Microsoft-Zugangsdaten fehlen (Einstellungen -> System -> E-Mail)")
        mailbox = account.graph_mailbox or s.get("smtp_from_email")
        if not mailbox:
            raise RuntimeError("Keine Mailbox angegeben (Konto oder Absenderadresse)")
        return tenant, client, secret, mailbox
    if not account.secret_enc:
        raise RuntimeError("Für dieses Konto ist kein Client-Secret hinterlegt")
    return (account.graph_tenant_id, account.graph_client_id,
            decrypt_secret(account.secret_enc), account.graph_mailbox)


# ── Hilfen: Mail-Inhalte ──────────────────────────────────────────────────────
def _decode_header(value) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _html_to_text(html: str) -> str:
    """Sehr einfache HTML->Text-Umwandlung (reicht für die KI-Analyse)."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&") \
               .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"[ \t]+", " ", text).strip()


def _mail_body_text(msg: email.message.Message) -> str:
    """Bevorzugt text/plain, sonst text/html (konvertiert)."""
    plain, html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get("Content-Disposition", "").startswith("attachment"):
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
    else:
        try:
            payload = msg.get_payload(decode=True)
            text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""
        except Exception:
            text = ""
        if msg.get_content_type() == "text/html":
            html = text
        else:
            plain = text
    return (plain if plain is not None else _html_to_text(html or "")).strip()


# ── 2a. IMAP ──────────────────────────────────────────────────────────────────
def _imap_connect(db: Session, account: MailAccount) -> imaplib.IMAP4:
    host = account.imap_host
    port = account.imap_port or (993 if account.imap_ssl else 143)
    if account.imap_ssl:
        conn = imaplib.IMAP4_SSL(host, port, timeout=20)
    else:
        conn = imaplib.IMAP4(host, port, timeout=20)
    user, password = _imap_credentials(db, account)
    conn.login(user, password)
    return conn


def imap_list_folders(db: Session, account: MailAccount) -> List[str]:
    conn = _imap_connect(db, account)
    try:
        typ, rows = conn.list()
        folders = []
        for row in rows or []:
            if not row:
                continue
            # Format: (\Flags) "Trenner" "Ordnername"
            m = re.search(rb'"([^"]*)"\s*$', row) or re.search(rb"(\S+)$", row)
            if m:
                name = m.group(1).decode("utf-7", errors="replace")
                folders.append(name)
        return folders
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def imap_fetch_messages(db: Session, account: MailAccount,
                        limit: int = MAX_MESSAGES_PER_SCAN) -> List[dict]:
    """Holt die neuesten Nachrichten aus dem konfigurierten Ordner."""
    conn = _imap_connect(db, account)
    try:
        typ, _ = conn.select(f'"{account.folder}"', readonly=True)
        if typ != "OK":
            raise RuntimeError(f"IMAP-Ordner '{account.folder}' nicht wählbar")
        typ, data = conn.search(None, "ALL")
        ids = (data[0] or b"").split()
        out = []
        for msg_id in reversed(ids[-limit:]):
            typ, msg_data = conn.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            received = None
            if msg.get("Date"):
                try:
                    received = email.utils.parsedate_to_datetime(msg["Date"])
                except Exception:
                    received = None
            out.append({
                "message_id": _decode_header(msg.get("Message-ID")) or f"imap-{msg_id.decode()}",
                "subject": _decode_header(msg.get("Subject")),
                "sender": _decode_header(msg.get("From")),
                "received_at": received,
                "body": _mail_body_text(msg),
            })
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# ── 2b. Microsoft Graph ───────────────────────────────────────────────────────
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _graph_token(db: Session, account: MailAccount) -> tuple:
    """Liefert (access_token, mailbox)."""
    tenant, client, secret, mailbox = _graph_credentials(db, account)
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    resp = httpx.post(url, data={
        "client_id": client,
        "client_secret": secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"], mailbox


def graph_list_folders(db: Session, account: MailAccount) -> List[str]:
    token, mailbox = _graph_token(db, account)
    url = f"{GRAPH_BASE}/users/{mailbox}/mailFolders?$top=100"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()
    return [f["displayName"] for f in resp.json().get("value", [])]


def _graph_folder_id(mailbox: str, folder: str, token: str) -> str:
    """Ordnername -> ID (bekannte Namen wie 'inbox' funktionieren direkt)."""
    known = {"inbox", "drafts", "sentitems", "deleteditems", "junkemail", "archive"}
    if folder.lower() in known:
        return folder.lower()
    url = f"{GRAPH_BASE}/users/{mailbox}/mailFolders?$top=100"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    resp.raise_for_status()
    for f in resp.json().get("value", []):
        if f.get("displayName", "").lower() == folder.lower():
            return f["id"]
    raise RuntimeError(f"Graph-Ordner '{folder}' nicht gefunden")


def graph_fetch_messages(db: Session, account: MailAccount,
                         limit: int = MAX_MESSAGES_PER_SCAN) -> List[dict]:
    token, mailbox = _graph_token(db, account)
    folder_id = _graph_folder_id(mailbox, account.folder, token)
    url = (f"{GRAPH_BASE}/users/{mailbox}/mailFolders/{folder_id}/messages"
           f"?$top={limit}&$orderby=receivedDateTime desc"
           f"&$select=id,subject,from,receivedDateTime,body,bodyPreview")
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    out = []
    for m in resp.json().get("value", []):
        body = m.get("body") or {}
        text = body.get("content", "")
        if (body.get("contentType") or "").lower() == "html":
            text = _html_to_text(text)
        received = None
        if m.get("receivedDateTime"):
            try:
                received = datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00"))
            except Exception:
                received = None
        out.append({
            "message_id": m["id"],
            "subject": m.get("subject") or "",
            "sender": ((m.get("from") or {}).get("emailAddress") or {}).get("address", ""),
            "received_at": received,
            "body": text.strip(),
        })
    return out


def fetch_messages(db: Session, account: MailAccount,
                   limit: int = MAX_MESSAGES_PER_SCAN) -> List[dict]:
    if account.protocol == "imap":
        return imap_fetch_messages(db, account, limit)
    return graph_fetch_messages(db, account, limit)


def list_folders(db: Session, account: MailAccount) -> List[str]:
    if account.protocol == "imap":
        return imap_list_folders(db, account)
    return graph_list_folders(db, account)


# ── 3. KI-Extraktion ──────────────────────────────────────────────────────────
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


_EXTRACT_PROMPT = """Du bist ein Assistent, der aus E-Mails konkrete Aufgaben (To-dos) extrahiert.

Analysiere die folgende E-Mail. Extrahiere alle konkreten Aufgaben, die sich aus
ihrem Inhalt ergeben (Aufträge, Bitten, Fristen, Zusagen, nötige Antworten).
Wenn die E-Mail keine Aufgabe enthält (z.B. Newsletter, reine Info, Werbung),
gib eine leere Liste zurück.

Heutiges Datum: {today}

Antworte AUSSCHLIESSLICH mit einem JSON-Array in genau diesem Format, ohne
weiteren Text:
[{{"title": "Kurzer Aufgabentitel (max. 100 Zeichen, Deutsch)",
   "description": "1-3 Sätze Kontext, worum es geht und was zu tun ist",
   "due_date": "YYYY-MM-DD oder null, falls kein Termin erkennbar",
   "priority": "niedrig|mittel|hoch|kritisch"}}]

E-Mail:
Von: {sender}
Betreff: {subject}
Empfangen: {received}

{body}"""


def _parse_ki_json(text: str) -> List[dict]:
    """Extrahiert das JSON-Array aus der KI-Antwort (tolerant gegen Codeblöcke)."""
    m = re.search(r"\[.*\]", text, flags=re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        due = item.get("due_date")
        due_parsed = None
        if due and isinstance(due, str):
            try:
                due_parsed = date.fromisoformat(due[:10])
            except Exception:
                due_parsed = None
        prio = item.get("priority")
        if prio not in ("niedrig", "mittel", "hoch", "kritisch"):
            prio = "mittel"
        out.append({
            "title": title[:500],
            "description": (item.get("description") or "").strip() or None,
            "due_date": due_parsed,
            "priority": prio,
        })
    return out


def extract_tasks(ki: dict, mail: dict) -> List[dict]:
    """Ruft den konfigurierten KI-Provider auf und liefert Aufgabenvorschläge."""
    if not ki.get("api_key_enc"):
        raise RuntimeError("Kein KI-API-Key konfiguriert (Einstellungen -> Mail-Import & KI)")
    api_key = decrypt_secret(ki["api_key_enc"])
    provider = ki.get("provider") or "anthropic"
    model = ki.get("model") or KI_DEFAULT_MODELS.get(provider, KI_DEFAULT_MODELS["anthropic"])

    prompt = _EXTRACT_PROMPT.format(
        today=date.today().isoformat(),
        sender=mail.get("sender") or "-",
        subject=mail.get("subject") or "-",
        received=(mail.get("received_at").isoformat() if mail.get("received_at") else "-"),
        body=(mail.get("body") or "")[:MAX_BODY_CHARS],
    )

    if provider == "anthropic":
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
    else:  # openai
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]

    return _parse_ki_json(text)


# ── 4. Konto scannen ──────────────────────────────────────────────────────────
def scan_account(db: Session, account: MailAccount) -> int:
    """
    Holt neue Nachrichten des Kontos, lässt die KI Aufgaben extrahieren und
    legt Vorschläge an. Liefert die Anzahl neuer Vorschläge. Fehler werden
    am Konto in last_error vermerkt und erneut geworfen.
    """
    try:
        ki = load_ki_settings(db)
        messages = fetch_messages(db, account)

        # Bereits verarbeitete Nachrichten überspringen
        bekannte = {
            m[0] for m in db.query(MailTaskSuggestion.message_id)
            .filter(MailTaskSuggestion.account_id == account.id).all()
        }
        neue = [m for m in messages if m["message_id"] not in bekannte]

        anzahl = 0
        for mail in neue:
            vorschlaege = extract_tasks(ki, mail)
            preview = (mail.get("body") or "")[:800]
            if not vorschlaege:
                # Merken, dass die Mail analysiert wurde (ohne Vorschlag) —
                # sonst würde sie bei jedem Scan erneut zur KI geschickt.
                db.add(MailTaskSuggestion(
                    account_id=account.id,
                    message_id=mail["message_id"],
                    subject=(mail.get("subject") or "")[:1000],
                    sender=(mail.get("sender") or "")[:500],
                    received_at=mail.get("received_at"),
                    body_preview=preview,
                    title="(keine Aufgabe erkannt)",
                    status="verworfen",
                    decided_at=datetime.now(timezone.utc),
                ))
                continue
            for v in vorschlaege:
                db.add(MailTaskSuggestion(
                    account_id=account.id,
                    message_id=mail["message_id"],
                    subject=(mail.get("subject") or "")[:1000],
                    sender=(mail.get("sender") or "")[:500],
                    received_at=mail.get("received_at"),
                    body_preview=preview,
                    title=v["title"],
                    description=v["description"],
                    due_date=v["due_date"],
                    priority=v["priority"],
                ))
                anzahl += 1

        account.last_scan_at = datetime.now(timezone.utc)
        account.last_error = None
        db.commit()
        return anzahl
    except Exception as e:
        db.rollback()
        account.last_error = str(e)[:2000]
        account.last_scan_at = datetime.now(timezone.utc)
        db.commit()
        raise


# ── 5. Hintergrund-Scanner ────────────────────────────────────────────────────
_scanner_started = False


def _scanner_loop():
    from app.db.base import SessionLocal
    while True:
        time.sleep(60)
        try:
            db = SessionLocal()
            try:
                jetzt = datetime.now(timezone.utc)
                konten = (db.query(MailAccount)
                          .filter(MailAccount.auto_scan.is_(True),
                                  MailAccount.is_active.is_(True)).all())
                for konto in konten:
                    faellig = (konto.last_scan_at is None or
                               konto.last_scan_at + timedelta(minutes=konto.scan_interval_minutes) <= jetzt)
                    if not faellig:
                        continue
                    try:
                        scan_account(db, konto)
                    except Exception as e:
                        print(f"[WARN] Auto-Scan '{konto.name}' fehlgeschlagen: {e}")
            finally:
                db.close()
        except Exception as e:
            print(f"[WARN] Mail-Scanner-Schleife: {e}")


def start_background_scanner():
    """Startet den Auto-Scan-Thread (einmalig; in Tests deaktiviert)."""
    global _scanner_started
    if _scanner_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_MAIL_SCANNER") == "1":
        return
    _scanner_started = True
    threading.Thread(target=_scanner_loop, daemon=True, name="mail-scanner").start()
