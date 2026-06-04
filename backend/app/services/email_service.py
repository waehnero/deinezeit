"""
E-Mail-Service
==============
Zentraler SMTP-Versand für DeineZeit.
Wird von Einstellungen (Test-Mail) und Belege-Versand verwendet.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional


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


def send_email(
    settings: dict,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    attachments: Optional[list] = None,
) -> None:
    """
    Versendet eine E-Mail via SMTP.

    attachments: Liste von Dicts mit keys:
      - filename: str
      - data: bytes
      - mime_type: str  (z.B. "application/pdf")
    """
    cfg = _smtp_config(settings)
    if not cfg["host"]:
        raise ValueError("SMTP-Host nicht konfiguriert. Bitte unter Einstellungen → E-Mail einrichten.")

    # Nachricht aufbauen
    msg = MIMEMultipart("mixed") if attachments else MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{cfg['from_name']} <{cfg['from_email']}>" if cfg["from_name"] else cfg["from_email"]
    msg["To"]      = to_email

    # Text-Teil
    alt = MIMEMultipart("alternative") if attachments else msg
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        alt.attach(MIMEText(body_html, "html", "utf-8"))
    if attachments:
        msg.attach(alt)

    # Anhänge
    for att in (attachments or []):
        part = MIMEBase(*att["mime_type"].split("/", 1))
        part.set_payload(att["data"])
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att["filename"])
        msg.attach(part)

    # Versenden
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
