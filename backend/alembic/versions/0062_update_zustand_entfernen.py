"""Reste des In-App-Updates aus der Tabelle settings entfernen

Revision ID: 0062
Revises: 0061
Create Date: 2026-09-04

Hintergrund (Audit 02.09.2026, SEC-002 / Korrekturschritt K-21)
----------------------------------------------------------------
Das In-App-Update (Knopf in den Einstellungen, Backend baut den Server per
Docker-Socket neu) wurde am 04.09.2026 ersatzlos gestrichen. Seinen Zustand
hielt es seit Migration 0060 in ``settings`` unter den Schlüsseln
``update_status``, ``update_scheduled_at``, ``update_initiated_by`` und
``update_message``. Diese Zeilen haben keinen Leser mehr und werden entfernt.

Reine Datenbereinigung, keine Schemaänderung. Der Rückweg legt nichts neu an:
Ein alter Programmstand liest die Vorgabe „idle", wenn die Zeilen fehlen.
"""
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

_SCHLUESSEL = ("update_status", "update_scheduled_at",
               "update_initiated_by", "update_message")


def upgrade() -> None:
    op.execute(
        "DELETE FROM settings WHERE key IN ("
        + ", ".join(f"'{k}'" for k in _SCHLUESSEL) + ")"
    )


def downgrade() -> None:
    pass
