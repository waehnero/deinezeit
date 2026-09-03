"""Einstellungen: Geheimnisse verschlüsselt ablegen

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-02

SMTP-Passwort, Microsoft-Client-Secret, WebDAV-Passwort und die beiden
OneDrive-Client-Secrets lagen bisher im Klartext in der Tabelle ``settings``
— und damit in jedem Datenbank-Backup (Audit 02.09.2026, SEC-005).

Seit dieser Etappe ver- und entschlüsselt das Modell ``Setting`` diese Werte
selbst (siehe ``app/models/settings.py``, Verfahren wie beim TOTP-Secret in
Migration 0054). Diese Migration holt die Verschlüsselung für bereits
vorhandene Zeilen einmalig nach.

Fehlertolerant wie 0054: Gelingt die Verschlüsselung nicht (fehlender
SECRET_KEY, fehlende Bibliothek), bleiben die Werte im Klartext — das ist der
Zustand von vorher, und das Modell liest Klartext weiterhin. Beim nächsten
Speichern in den Einstellungen werden sie dann verschlüsselt. Ein Abbruch
wäre der schlechtere Ausgang, weil entrypoint.sh vor dem Start
``alembic upgrade head`` ausführt.

Kein Schema-Umbau; downgrade lässt die Werte verschlüsselt stehen (das
Modell des vorherigen Standes würde sie als Fernet-Token anzeigen — die
Geheimnisse müssten dann neu eingetragen werden). Wer sicher zurück will,
entschlüsselt vorher über die Einstellungsseite bzw. trägt die Werte neu ein.
"""
from alembic import op
import sqlalchemy as sa

revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None

GEHEIME_SCHLUESSEL = (
    "smtp_password",
    "ms_client_secret",
    "webdav_password",
    "onedrive_client_secret",
    "backup_onedrive_client_secret",
)


def upgrade():
    try:
        from app.core.crypto import verschluesseln, ist_verschluesselt

        bind = op.get_bind()
        zeilen = bind.execute(sa.text(
            "SELECT key, value FROM settings WHERE key IN :keys AND value <> ''"
        ).bindparams(sa.bindparam("keys", expanding=True)),
            {"keys": list(GEHEIME_SCHLUESSEL)}).fetchall()
        anzahl = 0
        for zeile in zeilen:
            if ist_verschluesselt(zeile.value):
                continue
            bind.execute(
                sa.text("UPDATE settings SET value = :v WHERE key = :k"),
                {"v": verschluesseln(zeile.value), "k": zeile.key},
            )
            anzahl += 1
        if anzahl:
            print(f"[0060] {anzahl} Geheimnis(se) in den Einstellungen verschlüsselt.")
    except Exception as e:                                   # noqa: BLE001
        print("[0060] Geheimnisse bleiben vorerst unverschlüsselt "
              f"({type(e).__name__}: {e}). Sie werden beim nächsten Speichern "
              "der Einstellungen automatisch verschlüsselt.")


def downgrade():
    # Bewusst keine Entschlüsselung: Ein Downgrade soll keine Geheimnisse im
    # Klartext in die Datenbank zurückschreiben.
    pass
