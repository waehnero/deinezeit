"""
E-Mail-Service
==============
Zentraler E-Mail-Versand für DeineZeit.
Unterstützt zwei Modi:
  - SMTP        (Gmail, GMX, web.de, eigener Server)
  - Graph API   (Office 365 / Microsoft 365 via OAuth2 Client Credentials)

Wird von Einstellungen (Test-Mail) und Belege-Versand verwendet.
"""
import base64
import json
import smtplib
import urllib.request
import urllib.parse
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _smtp_config(settings: dict) -> dict:
    """Liest SMTP-Konfiguration aus Settings-Dict."""
    return {
        "host":       settings.get("smtp_host", ""),
        "port":       int(settings.get("smtp_port", "587") or 587),
        "user":       settings.get("smtp_user", ""),
        "password":   settings.get("smtp_password", ""),
        "from_name":  settings.get("smtp_from_name", "DeineZeit"),
        "from_email": settings.get("smtp_from_email", "") or settings.get("smtp_user", ""),
        "use_tls":    str(settings.get("smtp_tls", "true")).lower() == "true",
    }


def _send_smtp(
    settings: dict,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    attachments: Optional[list] = None,
) -> None:
    """Versendet E-Mail via SMTP (STARTTLS oder SSL)."""
    cfg = _smtp_config(settings)
    if not cfg["host"]:
        raise ValueError("SMTP-Host nicht konfiguriert. Bitte unter Einstellungen → E-Mail einrichten.")

    msg = MIMEMultipart("mixed") if attachments else MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{cfg['from_name']} <{cfg['from_email']}>" if cfg["from_name"] else cfg["from_email"]
    msg["To"]      = to_email

    alt = MIMEMultipart("alternative") if attachments else msg
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        alt.attach(MIMEText(body_html, "html", "utf-8"))
    if attachments:
        msg.attach(alt)

    for att in (attachments or []):
        part = MIMEBase(*att["mime_type"].split("/", 1))
        part.set_payload(att["data"])
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att["filename"])
        msg.attach(part)

    if cfg["use_tls"]:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
    else:
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20)
        server.ehlo()

    if cfg["user"] and cfg["password"]:
        server.login(cfg["user"], cfg["password"])

    server.sendmail(cfg["from_email"], [to_email], msg.as_string())
    server.quit()


# ── Microsoft Graph API ───────────────────────────────────────────────────────

def _graph_get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Holt OAuth2-Access-Token via Client Credentials Flow."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     client_id,
        "client_secret": client_secret,
        "scope":         "https://graph.microsoft.com/.default",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            code = err.get("error", "")
            desc = err.get("error_description", body)[:300]
        except Exception:
            code, desc = "unknown", body[:300]
        raise ValueError(f"Token-Fehler ({code}): {desc}")

    if "access_token" not in result:
        raise ValueError(f"Kein Access-Token erhalten: {result}")
    return result["access_token"]


def _send_graph(
    settings: dict,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    attachments: Optional[list] = None,
) -> None:
    """Versendet E-Mail via Microsoft Graph API (sendMail)."""
    tenant_id     = settings.get("ms_tenant_id", "").strip()
    client_id     = settings.get("ms_client_id", "").strip()
    client_secret = settings.get("ms_client_secret", "").strip()
    from_email    = (settings.get("smtp_from_email", "") or "").strip()
    from_name     = (settings.get("smtp_from_name", "DeineZeit") or "DeineZeit").strip()

    if not all([tenant_id, client_id, client_secret, from_email]):
        raise ValueError(
            "Microsoft Graph nicht vollständig konfiguriert. "
            "Bitte Tenant-ID, Client-ID, Client-Secret und Absender-E-Mail eintragen."
        )

    token = _graph_get_token(tenant_id, client_id, client_secret)

    # Nachricht aufbauen
    body_content = body_html if body_html else body_text
    body_type    = "HTML" if body_html else "Text"

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": body_type,
            "content":     body_content,
        },
        "from": {
            "emailAddress": {
                "name":    from_name,
                "address": from_email,
            }
        },
        "toRecipients": [
            {"emailAddress": {"address": to_email}}
        ],
    }

    # Anhänge (base64-kodiert)
    if attachments:
        message["attachments"] = [
            {
                "@odata.type":  "#microsoft.graph.fileAttachment",
                "name":         att["filename"],
                "contentType":  att["mime_type"],
                "contentBytes": base64.b64encode(att["data"]).decode("ascii"),
            }
            for att in attachments
        ]

    payload = json.dumps({"message": message, "saveToSentItems": False}).encode("utf-8")
    url     = f"https://graph.microsoft.com/v1.0/users/{from_email}/sendMail"

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type",  "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # HTTP 202 Accepted = Erfolg (kein Body)
            _ = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err  = json.loads(body)
            msg  = err.get("error", {}).get("message", body)[:400]
            code = err.get("error", {}).get("code", str(e.code))
        except Exception:
            msg, code = body[:400], str(e.code)
        raise ValueError(f"Graph API Fehler ({code}): {msg}")


# ── Öffentliche Schnittstelle ─────────────────────────────────────────────────

def send_email(
    settings: dict,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    attachments: Optional[list] = None,
) -> None:
    """
    Versendet eine E-Mail — automatische Auswahl zwischen Graph API und SMTP.

    Wenn email_provider == 'graph' wird Microsoft Graph verwendet,
    sonst klassisches SMTP.

    attachments: Liste von Dicts mit keys:
      - filename:  str
      - data:      bytes
      - mime_type: str  (z.B. "application/pdf")
    """
    provider = settings.get("email_provider", "smtp")
    if provider == "graph":
        _send_graph(settings, to_email, subject, body_text, body_html, attachments)
    else:
        _send_smtp(settings, to_email, subject, body_text, body_html, attachments)
