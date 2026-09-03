"""
Ortszeit der Installation
=========================

Die Container laufen in UTC. Für Zeitstempel ist das richtig (alle Spalten
sind ``DateTime(timezone=True)``), für *Kalenderdaten* nicht: Ein Beleg, der
um 23:30 Ortszeit ausgestellt wird, bekäme mit ``date.today()`` das Datum des
Vortags — am 31.12. sogar den falschen Jahres-Nummernkreis. Fälligkeits- und
Wiederkehr-Worker liefen 1–2 Stunden „zu spät", gedruckte Berichte zeigten
UTC-Uhrzeiten (Audit BUG-002).

Zwei Riegel:

1. ``config.py`` setzt beim Start ``TZ`` für den Prozess (``time.tzset``).
   Damit liefern auch ``date.today()`` und ``datetime.now()`` in Bibliotheken
   und an übersehenen Stellen die Ortszeit.
2. Eigener Code nimmt ``heute()`` und ``jetzt()`` aus diesem Modul — dann
   steht die Absicht im Code, und ein Test kann die Uhr stellen.

Die Zeitzone kommt aus der Umgebungsvariable ``TZ`` (docker-compose.yml,
Vorgabe Europe/Vienna).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

ZONE = ZoneInfo(settings.TZ)


def jetzt() -> datetime:
    """Aktuelle Ortszeit — bewusst *ohne* tzinfo, damit sich ``.date()``,
    ``.year`` und ``strftime`` genauso verhalten wie beim bisherigen
    ``datetime.now()``. Für Zeitstempel in der Datenbank weiterhin
    ``datetime.now(timezone.utc)`` verwenden."""
    return datetime.now(ZONE).replace(tzinfo=None)


def heute() -> date:
    """Heutiges Kalenderdatum in Ortszeit."""
    return datetime.now(ZONE).date()
