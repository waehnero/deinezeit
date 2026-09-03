"""
Migrationen ↔ Modelle (Audit 02.09.2026, DATA-004).

Die übrigen Tests bauen ihr Schema mit ``Base.metadata.create_all`` — also
aus den Modellen. Die Produktion bekommt ihr Schema aber aus den
Alembic-Migrationen. Laufen beide auseinander, prüfen die Tests ein anderes
Schema als das, gegen das die Anwendung tatsächlich arbeitet: Ein UNIQUE, das
nur im Modell steht, greift im Test und in der Produktion nicht; eine
Löschkaskade, die nur in der Datenbank steht, fällt im Test nie auf.

Dieser Test lässt deshalb alle Migrationen in einem eigenen, leeren
Datenbank-Schema durchlaufen und vergleicht das Ergebnis mit den Modellen.
Jede Abweichung ist ein Fehler — der Weg zurück ins Grüne ist entweder eine
neue Migration oder eine Korrektur am Modell, nie ein Anpassen dieses Tests.
"""
import pathlib

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from app.db.base import Base
from tests.conftest import engine

SCHEMA = "migrationstest"
BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _beschreiben(eintrag) -> str:
    art = eintrag[0]
    if art in ("add_index", "remove_index"):
        ix = eintrag[1]
        return (f"{art:18} {ix.table.name}.{ix.name} {[c.name for c in ix.columns]}"
                f"{' UNIQUE' if ix.unique else ''}")
    if art in ("add_fk", "remove_fk"):
        fk = eintrag[1]
        return (f"{art:18} {fk.table.name}.{fk.name} {[c.name for c in fk.columns]}"
                f" -> {fk.referred_table.name} ondelete={fk.ondelete}")
    if art == "modify_nullable":
        return (f"{art:18} {eintrag[2]}.{eintrag[3]} DB nullable={eintrag[5]}"
                f" Modell nullable={eintrag[6]}")
    if art in ("add_constraint", "remove_constraint"):
        c = eintrag[1]
        return f"{art:18} {c.table.name}.{c.name} {[cc.name for cc in c.columns]}"
    if art in ("add_column", "remove_column"):
        return f"{art:18} {eintrag[2]}.{eintrag[3].name}"
    if art in ("add_table", "remove_table"):
        return f"{art:18} {eintrag[1].name}"
    return f"{art:18} {str(eintrag)[:160]}"


def test_migrationen_ergeben_das_modellschema():
    """``alembic upgrade head`` auf leerem Schema == ``Base.metadata``."""
    # Alle Modelle registrieren — auch die, die nur über Router importiert
    # werden (die App importiert sie vollständig).
    import app.main  # noqa: F401

    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}"))
        conn.commit()
        try:
            # Bewusst OHNE alembic.ini: env.py würde daraus die Logging-
            # Konfiguration laden (fileConfig) und dabei alle bestehenden
            # Logger abschalten — die caplog-Tests anderer Module fänden
            # danach keine Meldungen mehr. Die Verbindungs-URL setzt env.py
            # ohnehin selbst aus den Einstellungen.
            cfg = Config()
            cfg.set_main_option("script_location", str(BACKEND / "alembic"))
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.commit()

            conn.execute(text(f"SET search_path TO {SCHEMA}"))
            mc = MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": False})
            assert mc.get_current_revision() is not None

            roh = compare_metadata(mc, Base.metadata)
            abweichungen = []
            for d in roh:
                abweichungen.extend(d if isinstance(d, list) else [d])
        finally:
            conn.rollback()
            conn.execute(text("SET search_path TO public"))
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.commit()

    assert not abweichungen, (
        f"{len(abweichungen)} Abweichung(en) zwischen Migrationen (Produktionsschema) "
        "und Modellen (Testschema):\n  "
        + "\n  ".join(_beschreiben(a) for a in abweichungen))
