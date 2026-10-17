"""
Bestandsübernahme durch Migration 0063 (zentrale Mail-Zugangsdaten binden).

Läuft wie tests/test_migrationen.py in einem eigenen, leeren DB-Schema: erst
bis 0062 migrieren, dann Altdaten anlegen, die es vor der Behebung geben
konnte, dann 0063 einspielen und prüfen, dass

  * keine Berechtigung erweitert wird,
  * eindeutig sichere Konfigurationen erhalten bleiben,
  * unklare (persönliche Konten mit zentralen Zugangsdaten) gesperrt werden.

Alle Werte sind erfunden.
"""
import pathlib
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.conftest import engine

SCHEMA = "mailmigrationstest"
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _cfg(conn):
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["connection"] = conn
    return cfg


def _konto(conn, zentral=False, **werte):
    werte.setdefault("id", uuid.uuid4())
    werte.setdefault("folder", "INBOX")
    werte.setdefault("imap_ssl", True)
    werte["use_central_credentials"] = zentral
    spalten = ", ".join(werte)
    platzhalter = ", ".join(f":{k}" for k in werte)
    conn.execute(text(
        f"INSERT INTO mail_accounts ({spalten}, flag_erledigt, auto_scan, "
        f"scan_interval_minutes, is_active) VALUES ({platzhalter}, false, true, 15, true)"),
        werte)
    return werte["id"]


def test_migration_0063_uebernimmt_sicher_und_sperrt_unklares():
    import app.main  # noqa: F401  (alle Modelle registrieren)

    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}"))
        conn.commit()
        try:
            command.upgrade(_cfg(conn), "0062")
            conn.commit()
            conn.execute(text(f"SET search_path TO {SCHEMA}"))

            uid = uuid.uuid4()
            conn.execute(text(
                "INSERT INTO users (id, email, full_name, hashed_password, role, "
                "language, is_active) VALUES (:id, 'm@firma.example', 'M', 'x', "
                "'employee', 'de', true)"), {"id": uid})
            for k, v in (("smtp_user", "Office@Firma.example"),
                         ("ms_tenant_id", "firma.onmicrosoft.com"),
                         ("ms_client_id", "app-1"),
                         ("smtp_from_email", "office@firma.example")):
                conn.execute(text(
                    "INSERT INTO settings (key, value) VALUES (:k, :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
                    {"k": k, "v": v})

            # a) persönliches Konto mit zentralen Daten und fremdem Server
            persoenlich_zentral = _konto(conn, owner_user_id=uid, name="a", protocol="imap",
                                         imap_host="mail.angreifer.example", zentral=True)
            # b) persönliches Konto mit eigenen Daten
            persoenlich_eigen = _konto(conn, owner_user_id=uid, name="b", protocol="imap",
                                       imap_host="imap.example.com", imap_user="m")
            # c) globales IMAP-Konto mit zentralen Daten (vom Admin eingerichtet)
            global_imap = _konto(conn, name="c", protocol="imap",
                                 imap_host="IMAP.Firma.example", imap_ssl=False, zentral=True)
            # d) globales Graph-Konto mit zentralen Daten, Mailbox leer
            global_graph = _konto(conn, name="d", protocol="graph", zentral=True)
            # e) globales IMAP-Konto ohne Host -> nicht eindeutig
            global_unklar = _konto(conn, name="e", protocol="imap", zentral=True)
            # f) globales Konto mit eigenen Daten
            global_eigen = _konto(conn, name="f", protocol="imap",
                                  imap_host="imap.example.com", imap_user="x")
            conn.commit()

            command.upgrade(_cfg(conn), "0063")
            conn.commit()
            conn.execute(text(f"SET search_path TO {SCHEMA}"))

            def zeile(i):
                return conn.execute(text(
                    "SELECT owner_user_id, use_central_credentials, zentral_bindung, "
                    "freigabe_alle, freigabe_gruppen, last_error "
                    "FROM mail_accounts WHERE id = :i"), {"i": i}).fetchone()

            a = zeile(persoenlich_zentral)
            assert a.zentral_bindung is None
            assert a.freigabe_alle is False
            assert "nicht zulässig" in a.last_error

            b = zeile(persoenlich_eigen)
            assert (b.zentral_bindung, b.freigabe_alle, b.last_error) == (None, False, None)

            c = zeile(global_imap)
            assert c.freigabe_alle is True          # bisheriger Nutzerkreis: alle
            assert c.freigabe_gruppen == []
            assert c.zentral_bindung["host"] == "imap.firma.example"
            assert c.zentral_bindung["port"] == 143
            assert c.zentral_bindung["tls"] == "starttls"   # kein Klartext mehr
            assert c.zentral_bindung["identitaet"] == "office@firma.example"
            assert "password" not in str(c.zentral_bindung).lower()

            d = zeile(global_graph)
            assert d.zentral_bindung["mailbox"] == "office@firma.example"
            assert d.zentral_bindung["identitaet"] == "app-1@firma.onmicrosoft.com"

            e = zeile(global_unklar)
            assert e.zentral_bindung is None        # bleibt gesperrt bis Bestätigung

            f = zeile(global_eigen)
            assert f.zentral_bindung is None and f.freigabe_alle is True

            # Rückweg funktioniert
            command.downgrade(_cfg(conn), "0062")
            conn.commit()
        finally:
            conn.rollback()
            conn.execute(text("SET search_path TO public"))
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.commit()
