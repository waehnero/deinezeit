"""Mail-Import: zentrale Zugangsdaten an bestätigte Ziele binden

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-15

Hintergrund (Sicherheitsbefund zu Commit 1a5787e)
-------------------------------------------------
Ein Mitarbeiter mit Aufgabenrechten konnte ein persönliches IMAP-Konto mit
„zentralen Zugangsdaten" anlegen und den Zielserver frei wählen — das Backend
meldete sich dann mit dem zentralen SMTP-Benutzer und -Passwort bei diesem
Server an. Seit dieser Etappe gilt (services/mail_sicherheit.py):

* zentrale Zugangsdaten nur an globalen, vom Admin verwalteten Konten,
* und nur an das vom Admin bestätigte Ziel (``zentral_bindung``),
* globale Konten nutzt nur, wer freigegeben ist (``freigabe_alle`` oder
  Mitglied einer Gruppe aus ``freigabe_gruppen``).

Übernahme des Bestands — erweitert keine Berechtigung
-----------------------------------------------------
1. Globale Konten bekommen ``freigabe_alle = true``. Bisher sah jeder
   angemeldete Benutzer mit Aufgabenrechten diese Konten und ihre Vorschläge;
   genau dieser Kreis bleibt berechtigt. Einschränken kann der Admin danach.
2. Globale Konten mit zentralen Zugangsdaten: Ihr Ziel hat der Admin selbst
   eingetragen (globale Konten konnte nur er anlegen und ändern). Das
   derzeitige Ziel wird deshalb als bestätigt übernommen — aber nur, wenn es
   vollständig bestimmbar ist (IMAP: Server + zentraler SMTP-Benutzer; Graph:
   Tenant, Client und Mailbox). Sonst bleibt die Bindung leer und das Konto
   gesperrt, bis der Admin bestätigt.
3. Persönliche Konten mit zentralen Zugangsdaten werden NICHT übernommen: Ihr
   Ziel hat ein Mitarbeiter gewählt, niemand hat es autorisiert. Das Konto
   bleibt bestehen, verbindet aber nicht mehr; ``last_error`` erklärt, was zu
   tun ist (eigene Zugangsdaten hinterlegen oder ein zentrales Konto nutzen).

Der Rückweg entfernt die Spalten wieder; die Sperre persönlicher Konten mit
zentralen Zugangsdaten hebt der alte Programmstand damit auf — der Befund
wäre wieder offen.
"""
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_HINWEIS_PERSOENLICH = (
    "Zentrale Zugangsdaten sind für persönliche Mail-Konten nicht zulässig. "
    "Bitte eigene Zugangsdaten hinterlegen oder ein vom Admin freigegebenes "
    "zentrales Konto verwenden.")


def _setting(bind, key: str) -> str:
    row = bind.execute(sa.text("SELECT value FROM settings WHERE key = :k"),
                       {"k": key}).fetchone()
    return (row[0] or "").strip() if row else ""


def upgrade():
    op.add_column("mail_accounts", sa.Column("zentral_bindung", JSONB, nullable=True))
    op.add_column("mail_accounts", sa.Column(
        "freigabe_alle", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("mail_accounts", sa.Column(
        "freigabe_gruppen", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))

    bind = op.get_bind()

    # 1. Globale Konten: bisheriger Nutzerkreis (alle) bleibt berechtigt
    bind.execute(sa.text(
        "UPDATE mail_accounts SET freigabe_alle = true WHERE owner_user_id IS NULL"))

    # 2. Globale Konten mit zentralen Zugangsdaten: Ziel übernehmen, wenn eindeutig
    smtp_user = _setting(bind, "smtp_user").lower()
    tenant = _setting(bind, "ms_tenant_id").lower()
    client = _setting(bind, "ms_client_id").lower()
    absender = _setting(bind, "smtp_from_email").lower()
    jetzt = datetime.now(timezone.utc).isoformat()

    konten = bind.execute(sa.text(
        "SELECT id, protocol, imap_host, imap_port, imap_ssl, graph_mailbox "
        "FROM mail_accounts WHERE owner_user_id IS NULL "
        "AND use_central_credentials = true")).fetchall()
    for k in konten:
        bindung = None
        if k.protocol == "imap" and k.imap_host and smtp_user:
            bindung = {
                "protocol": "imap",
                "host": k.imap_host.strip().lower().rstrip("."),
                "port": k.imap_port or (993 if k.imap_ssl else 143),
                "tls": "ssl" if k.imap_ssl else "starttls",
                "identitaet": smtp_user,
                "mailbox": None,
            }
        elif k.protocol == "graph":
            mailbox = (k.graph_mailbox or absender or "").strip().lower()
            if tenant and client and mailbox:
                bindung = {
                    "protocol": "graph",
                    "host": "graph.microsoft.com",
                    "port": 443,
                    "tls": "ssl",
                    "identitaet": f"{client}@{tenant}",
                    "mailbox": mailbox,
                }
        if bindung:
            bindung.update({"bestaetigt_von": None, "bestaetigt_am": jetzt,
                            "quelle": "migration_0063"})
            bind.execute(sa.text(
                "UPDATE mail_accounts SET zentral_bindung = CAST(:b AS jsonb) WHERE id = :id"),
                {"b": json.dumps(bindung), "id": k.id})

    # 3. Persönliche Konten mit zentralen Zugangsdaten: gesperrt, mit Hinweis
    bind.execute(sa.text(
        "UPDATE mail_accounts SET last_error = :h "
        "WHERE owner_user_id IS NOT NULL AND use_central_credentials = true"),
        {"h": _HINWEIS_PERSOENLICH})


def downgrade():
    op.drop_column("mail_accounts", "freigabe_gruppen")
    op.drop_column("mail_accounts", "freigabe_alle")
    op.drop_column("mail_accounts", "zentral_bindung")
