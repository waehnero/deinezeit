"""Zeitprojekte — der Stammdaten-Typ, auf den Projektzeiten gebucht werden.

Begriffe (seit Migration 0059 im ganzen Modul einheitlich):

  Zeitprojekt   Stammsatz (Kunde/Projekt) — ``EntityRecord`` vom Typ
                ``zeitprojekte``. Traegt Stundenkonten und Anhaenge.
  Projektzeit   einzelner Zeiteintrag — ``TimeEntry``.

Der Slug steht hier an einer Stelle und nicht als Zeichenkette in jeder
Abfrage: Die Umbenennung von ``projekte`` (bis 0038) ueber ``projektzeiten``
(bis 0059) auf ``zeitprojekte`` hat gezeigt, wie teuer verstreute Literale
sind — jede vergessene Stelle faellt erst zur Laufzeit auf, und dann als
"Stammdaten-Typ nicht gefunden".
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.masterdata import EntityType

ZEITPROJEKTE_SLUG = "zeitprojekte"

# Frueher verwendete Slugs. Nur fuer den Notfall-Rueckfall in ``typ_holen``
# (siehe dort) — nicht fuer neue Abfragen verwenden.
ALTE_SLUGS = ("projektzeiten", "projekte")


def typ_holen(db: Session) -> Optional[EntityType]:
    """Den Stammdaten-Typ der Zeitprojekte laden.

    Faellt auf die alten Slugs zurueck, falls die Migration 0059 noch nicht
    gelaufen ist. Das ist bewusst defensiv: Der Backend-Container fuehrt beim
    Start ``alembic upgrade head`` aus, aber ein Frontend, das gegen ein
    aelteres Backend laeuft (Neustart-Fenster beim Deploy), soll die
    Projektzeit-Auswahl nicht mit einer leeren Liste beantworten.
    """
    typ = db.query(EntityType).filter(EntityType.slug == ZEITPROJEKTE_SLUG).first()
    if typ:
        return typ
    for alt in ALTE_SLUGS:
        typ = db.query(EntityType).filter(EntityType.slug == alt).first()
        if typ:
            return typ
    return None
