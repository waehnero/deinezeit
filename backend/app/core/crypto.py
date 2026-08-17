"""
Verschlüsselung schutzbedürftiger Feldinhalte (Etappe „Sicherheit & Anmeldung")
==============================================================================

Manche Werte müssen im Klartext *verwendbar* bleiben — ein Hash genügt also
nicht — dürfen aber nicht lesbar in der Datenbank stehen. Bisher betrifft das
genau ein Feld: ``users.totp_secret``.

Warum das zählt: Wer das TOTP-Secret kennt, kann für dieses Konto beliebig
gültige 2FA-Codes erzeugen. Der zweite Faktor ist damit wertlos. Ein
Datenbank-Auszug — ein Backup auf einer falschen Ablage, eine SQL-Injection,
ein kompromittiertes Datenbankkonto — reicht dann aus, obwohl das Passwort
weiterhin nur als bcrypt-Hash vorliegt. Die Passwörter waren also geschützt,
der zweite Faktor nicht.

Verfahren
---------
Fernet (AES-128-CBC + HMAC-SHA256, aus der ``cryptography``-Bibliothek). Der
Schlüssel wird über HKDF-SHA256 aus ``SECRET_KEY`` abgeleitet — es gibt also
kein zusätzliches Geheimnis zu verwalten, aber auch keine direkte Verwendung
von ``SECRET_KEY`` als Schlüsselmaterial.

**Achtung — Wechsel von SECRET_KEY:** Danach sind bestehende verschlüsselte
Werte nicht mehr entschlüsselbar. Betroffene Benutzer müssen ihr 2FA neu
einrichten (Administrator: „2FA deaktivieren" in der Benutzerverwaltung). Das
gilt ohnehin für alle ausgestellten Token und ist daher kein neuer Nachteil.

Bestandsdaten
-------------
``entschluesseln()`` gibt einen Wert, der kein gültiges Fernet-Token ist,
unverändert zurück. Vor Migration 0054 gespeicherte Klartext-Secrets
funktionieren deshalb weiter und werden beim nächsten Schreiben automatisch
verschlüsselt. Ein Zwangs-Backfill wäre nicht nötig, ist aber in Migration
0054 als Bequemlichkeit enthalten.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

logger = logging.getLogger(__name__)

# Trennt die Schlüsselableitung von anderen Verwendungen desselben SECRET_KEY
# (JWT-Signatur). Nicht ändern — sonst sind bestehende Werte unlesbar.
_HKDF_INFO = b"deinezeit.feldverschluesselung.v1"

_fernet: Optional[Fernet] = None


def _schluessel() -> Fernet:
    """Fernet-Instanz, einmalig aus SECRET_KEY abgeleitet."""
    global _fernet
    if _fernet is None:
        rohschluessel = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=_HKDF_INFO,
        ).derive(settings.SECRET_KEY.encode("utf-8"))
        _fernet = Fernet(base64.urlsafe_b64encode(rohschluessel))
    return _fernet


def verschluesseln(wert: Optional[str]) -> Optional[str]:
    """Klartext → Fernet-Token. ``None`` und Leerstring bleiben unverändert."""
    if not wert:
        return wert
    return _schluessel().encrypt(wert.encode("utf-8")).decode("ascii")


def entschluesseln(wert: Optional[str]) -> Optional[str]:
    """Fernet-Token → Klartext.

    Ist der Wert kein gültiges Fernet-Token, wird er unverändert
    zurückgegeben: so bleiben Bestandswerte aus der Zeit vor Migration 0054
    (unverschlüsseltes Base32-Secret) lesbar.
    """
    if not wert:
        return wert
    try:
        return _schluessel().decrypt(wert.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return wert


def ist_verschluesselt(wert: Optional[str]) -> bool:
    """Prüft, ob der Wert mit dem aktuellen Schlüssel entschlüsselbar ist."""
    if not wert:
        return False
    try:
        _schluessel().decrypt(wert.encode("ascii"))
        return True
    except (InvalidToken, ValueError):
        return False
