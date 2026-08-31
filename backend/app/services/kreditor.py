"""
Kontofindung für die Einkaufsseite.

Gegenstück zur Kontenkaskade des Verkaufs (``services/artikelstamm.py``), aber
bewusst viel einfacher: Die Eingangsrechnung hat keine Positionen, also gibt es
keinen Artikel, von dem ein Konto kommen könnte. Übrig bleibt eine Stufe — das
Standard-Aufwandskonto des Lieferanten.

Absichtlich **kein** Vorgabekonto als letzte Stufe: Beim Erlös ist 4000 eine
vertretbare Annahme, weil fast jeder Umsatz dorthin gehört. Im Aufwand ist das
anders — Miete, Wareneinsatz und Personalaufwand sind verschiedene Konten, und
ein geratenes Konto fiele in der Buchhaltung weniger auf als ein leeres. Lieber
eine sichtbare Lücke als eine stille Falschbuchung.

Hier wächst später die Lieferanten-Kontengruppe hinein, falls die
Steuerfall-Matrix (Inland / innergemeinschaftlich / Drittland / Reverse Charge)
gebaut wird.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.masterdata import EntityRecord


def aufwandskonto_fuer_lieferant(db: Session,
                                 supplier_id: Optional[UUID]) -> Optional[str]:
    """Standard-Aufwandskonto des Lieferanten, oder ``None``.

    Liest ``aufwand_konto`` aus dem Kontaktdatensatz (Feld aus Migration 0057).
    Ein leerer Text zählt als „nicht gesetzt" — ein leeres Formularfeld kommt
    als ``""`` an, nicht als ``None``, und würde sonst als bewusste Angabe
    durchgehen.
    """
    if not supplier_id:
        return None

    rec = (db.query(EntityRecord)
           .filter(EntityRecord.id == supplier_id)
           .first())
    if not rec:
        return None

    konto = (rec.data or {}).get("aufwand_konto")
    if konto is None:
        return None
    konto = str(konto).strip()
    return konto or None
