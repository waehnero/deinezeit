"""
Worker-Sperre: Die Hintergrund-Worker laufen in genau EINEM Arbeitsprozess.

Die Worker (Mail-Scan, wiederkehrende Rechnungen, Fälligkeit, Postecke,
Backup, SSL-Überwachung) sind Threads im App-Prozess. Startet uvicorn mit
``--workers 2``, gäbe es jeden Worker zweimal — doppelte Rechnungsentwürfe,
doppelte Backups, doppelte E-Mails. Genau deshalb musste UVICORN_WORKERS bis
04.09.2026 auf 1 stehen (Audit OPS-003 / K-21).

Der Riegel ist ein PostgreSQL-Advisory-Lock auf Sitzungsebene
(``pg_try_advisory_lock``). Er gehört der Datenbankverbindung, die ihn hält,
und wird automatisch frei, sobald diese Verbindung endet — also auch dann,
wenn der Prozess abstürzt. Es braucht keine Tabelle, keine Migration, keinen
Aufräum-Cron.

Ablauf je Prozess:
  1. Ein eigener Thread öffnet EINE dauerhafte Verbindung (außerhalb des
     Pools, damit sie nie recycelt wird) und versucht den Lock.
  2. Bekommt er ihn, startet er die Worker und hält die Verbindung offen —
     für immer. Dieser Prozess ist der „Anführer".
  3. Bekommt er ihn nicht, versucht er es jede Minute erneut. Stirbt der
     Anführer, übernimmt so binnen einer Minute ein anderer Prozess.

In Tests (TEST_DATABASE_URL) wird nichts gestartet: Die Worker selbst sind
dort ohnehin abgeschaltet, und die Test-Datenbank verträgt keine zweite
dauerhafte Verbindung.
"""
import logging
import os
import threading
import time
from typing import Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Beliebige, aber feste Kennung. Advisory-Locks sind datenbankweit; ein
# anderer Dienst auf derselben Datenbank dürfte diese Zahl nicht verwenden.
SPERR_ID = 20260904

# Wie oft ein Prozess ohne Lock nachfragt.
WARTEZEIT_SEKUNDEN = 60

_gestartet = False
_ist_anfuehrer = False


def ist_anfuehrer() -> bool:
    """True, wenn dieser Prozess die Worker betreibt."""
    return _ist_anfuehrer


def sperre_versuchen(verbindung) -> bool:
    """Versucht den Lock auf der gegebenen Verbindung. Nicht blockierend."""
    return bool(verbindung.execute(
        text("SELECT pg_try_advisory_lock(:id)"), {"id": SPERR_ID}).scalar())


def sperre_freigeben(verbindung) -> bool:
    return bool(verbindung.execute(
        text("SELECT pg_advisory_unlock(:id)"), {"id": SPERR_ID}).scalar())


def _schleife(starter: Callable[[], None]) -> None:
    global _ist_anfuehrer
    from app.db.base import engine

    verbindung = None
    while True:
        try:
            if verbindung is None:
                # AUTOCOMMIT: Der Lock hängt an der Sitzung, nicht an einer
                # Transaktion — eine ewig offene Transaktion („idle in
                # transaction") wäre hier nur ein Ärgernis für die Datenbank.
                verbindung = engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT")
            if sperre_versuchen(verbindung):
                _ist_anfuehrer = True
                logger.info("Worker-Sperre erhalten (PID %s) — Hintergrund-Worker "
                            "starten in diesem Prozess.", os.getpid())
                starter()
                # Verbindung bewusst offen lassen: Mit ihr lebt der Lock.
                # Ein billiges Lebenszeichen alle paar Minuten deckt auf,
                # wenn die Datenbank die Verbindung gekappt hat.
                while True:
                    time.sleep(300)
                    verbindung.execute(text("SELECT 1"))
            logger.debug("Worker-Sperre belegt — ein anderer Prozess betreibt die Worker.")
        except Exception as e:                                   # noqa: BLE001
            if _ist_anfuehrer:
                # Verbindung weg = Lock weg. Die Worker laufen hier weiter,
                # ein anderer Prozess könnte jetzt ebenfalls starten. Laut
                # melden — ein Neustart des Containers räumt das auf.
                logger.error("Worker-Sperre verloren (%s). Bitte Backend neu "
                             "starten, sonst können Worker doppelt laufen.", e)
                return
            logger.warning("Worker-Sperre nicht prüfbar: %s", e)
            try:
                if verbindung is not None:
                    verbindung.close()
            except Exception:                                    # noqa: BLE001
                pass
            verbindung = None
        time.sleep(WARTEZEIT_SEKUNDEN)


def worker_exklusiv_starten(starter: Callable[[], None]) -> None:
    """Ruft ``starter()`` in genau einem Prozess der Installation auf.

    ``starter`` startet die Worker-Threads (siehe main.startup_event). Der
    Aufruf kehrt sofort zurück; die Entscheidung fällt im Hintergrund.
    """
    global _gestartet
    if _gestartet:
        return
    if os.environ.get("TEST_DATABASE_URL"):
        return
    _gestartet = True
    threading.Thread(target=_schleife, args=(starter,), daemon=True,
                     name="worker-sperre").start()
