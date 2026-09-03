from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, event
from sqlalchemy.orm.attributes import set_committed_value
from app.db.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key        = Column(String(100), primary_key=True)
    value      = Column(Text, nullable=False, default='')
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ── Geheimnisse verschlüsselt ablegen ────────────────────────────────────────
#
# Diese Schlüssel stehen in der Datenbank nur noch als Fernet-Token (siehe
# core/crypto.py, dasselbe Verfahren wie beim TOTP-Secret). Bis 02.09.2026
# lagen SMTP-Passwort, Microsoft-Client-Secret und Cloud-Zugangsdaten im
# Klartext in der Tabelle — und damit in jedem Datenbank-Backup, das ein
# Administrator herunterlädt oder das nach OneDrive geht (Audit SEC-005).
#
# Die Ver- und Entschlüsselung hängt am ORM: Beim Schreiben wird verschlüsselt,
# beim Laden entschlüsselt. Alle Stellen, die ``Setting`` lesen (Mailversand,
# Speicher-Provider, Backup, Mail-Import …), bekommen dadurch weiterhin den
# Klartext und mussten nicht angefasst werden. Bestandswerte im Klartext
# bleiben lesbar (``entschluesseln`` gibt Nicht-Token unverändert zurück) und
# werden beim nächsten Speichern verschlüsselt; Migration 0060 holt das für
# vorhandene Zeilen einmalig nach.
#
# Nicht abgedeckt sind Abfragen, die nur die Spalte holen
# (``db.query(Setting.value)``) — die gibt es im Projekt nicht.
GEHEIME_SCHLUESSEL = frozenset({
    "smtp_password",
    "ms_client_secret",
    "webdav_password",
    "onedrive_client_secret",
    "backup_onedrive_client_secret",
})


def _ist_geheim(target) -> bool:
    return target.key in GEHEIME_SCHLUESSEL and bool(target.value)


@event.listens_for(Setting, "load")
@event.listens_for(Setting, "refresh")
def _beim_laden_entschluesseln(target, context, *args):
    if _ist_geheim(target):
        from app.core.crypto import entschluesseln
        # set_committed_value: Wert setzen, ohne die Zeile als geändert zu
        # markieren — sonst würde der Klartext beim nächsten Flush zurück in
        # die Datenbank geschrieben.
        set_committed_value(target, "value", entschluesseln(target.value))


@event.listens_for(Setting, "before_insert")
@event.listens_for(Setting, "before_update")
def _beim_schreiben_verschluesseln(mapper, connection, target):
    if _ist_geheim(target):
        from app.core.crypto import verschluesseln, ist_verschluesselt
        if not ist_verschluesselt(target.value):
            target._klartext = target.value
            target.value = verschluesseln(target.value)


@event.listens_for(Setting, "after_insert")
@event.listens_for(Setting, "after_update")
def _nach_dem_schreiben_klartext_behalten(mapper, connection, target):
    """Im Arbeitsspeicher bleibt der Klartext — wer die Zeile in derselben
    Sitzung gleich noch einmal liest (vor dem Ablauf durch commit), bekommt
    nicht plötzlich das Fernet-Token."""
    klartext = getattr(target, "_klartext", None)
    if klartext is not None:
        set_committed_value(target, "value", klartext)
        del target._klartext
