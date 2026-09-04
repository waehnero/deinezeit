from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.base import Base
from app.models import *  # noqa: F401,F403  (alle Modelle importieren)
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Eine von außen übergebene Verbindung verwenden (Alembic-Standardmuster,
    # siehe „Sharing a Connection" in der Alembic-Doku). Gebraucht von
    # tests/test_migrationen.py, das die Migrationen in einem eigenen
    # Datenbank-Schema durchlaufen lässt und das Ergebnis mit den Modellen
    # vergleicht. Beim normalen Aufruf (`alembic upgrade head`) ist das
    # Attribut nicht gesetzt, und es ändert sich nichts.
    verbindung = config.attributes.get("connection")
    if verbindung is not None:
        context.configure(connection=verbindung, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
