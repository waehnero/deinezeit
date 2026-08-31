"""
Artikelstamm — Artikelgruppen, Nummernvergabe, Kontenkaskade.

Drei Dinge, die zusammengehören, weil sie alle an der Artikelgruppe hängen:

1. **Nummernvergabe.** Jede Gruppe führt ihren eigenen Zähler und ein Präfix;
   daraus entsteht ``DL-0007``. Vergeben wird serverseitig unter einer
   Zeilensperre — zwei gleichzeitige Anlagen dürfen nicht dieselbe Nummer
   ziehen.

2. **Kontenkaskade.** Welches Erlös- bzw. Aufwandskonto gilt für einen Artikel?
   Erst der Artikel selbst, dann seine Gruppe, zuletzt die Vorgabe aus dem
   Kontenplan. Diese Reihenfolge steht hier an *einer* Stelle, damit Beleg,
   Eingangsrechnung und Export nicht drei Meinungen dazu haben.

3. **Vorgabewerte.** USt-Satz, Einheit und Artikelart erbt der Artikel von der
   Gruppe, solange er nichts Eigenes gesetzt hat.

Warum die Kaskade nicht nach Steuerfall aufgefächert ist (Inland / innergemein-
schaftliche Lieferung / Drittland / Reverse Charge, wie es SelectLine über eine
Erlös-× Kundenkontengruppen-Matrix löst): Das wäre erst dann richtig, wenn auch
die Kontakte eine Kontengruppe tragen. Beschlossen ist die einfache Kaskade —
die Matrix bleibt ein eigener Schritt und lässt sich anfügen, ohne das hier
Gebaute umzubauen.
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.accounting import AccountingAccount
from app.models.masterdata import (ArticleGroup, ArticleGroupAccount,
                                   EntityRecord, EntityType)
from app.services import steuerfall as steuerfall_service

# Slug des Stammdaten-Typs „Artikel" (angelegt in Migration 0010)
ARTIKEL_SLUG = "artikel"


# ── Artikelgruppen lesen ──────────────────────────────────────────────────────

def gruppe_nach_nr(db: Session, nr: Optional[str]) -> Optional[ArticleGroup]:
    """Artikelgruppe über ihren Kurzschlüssel; leere Angabe ergibt None."""
    if not nr:
        return None
    return (db.query(ArticleGroup)
            .filter(ArticleGroup.nr == str(nr).strip())
            .first())


# ── Nummernvergabe ────────────────────────────────────────────────────────────

def naechste_artikelnummer(db: Session, gruppe: ArticleGroup,
                           festschreiben: bool = False) -> str:
    """
    Nächste freie Artikelnummer der Gruppe, z.B. ``DL-0007``.

    ``festschreiben=False`` ist ein reiner Vorschlag für das Formular: Der
    Zähler bleibt stehen. Erst beim tatsächlichen Anlegen wird mit
    ``festschreiben=True`` hochgezählt — sonst reißt jedes geöffnete und wieder
    verworfene Formular eine Lücke in die Nummernfolge.

    Die Zeile wird dabei mit ``FOR UPDATE`` gesperrt. Ohne die Sperre lesen zwei
    gleichzeitige Anlagen denselben Zähler und vergeben dieselbe Nummer; das
    fällt erst auf, wenn die Eindeutigkeitsprüfung des Feldes zuschlägt — beim
    zweiten Benutzer, mit einem Formular voller Eingaben.

    Ist die errechnete Nummer bereits vergeben (übernommene Altdaten, von Hand
    gesetzte Nummern), wird weitergezählt statt eine Kollision zu erzeugen.
    """
    if festschreiben:
        gesperrt = (db.query(ArticleGroup)
                    .filter(ArticleGroup.id == gruppe.id)
                    .with_for_update()
                    .one())
    else:
        gesperrt = gruppe

    praefix = (gesperrt.praefix or gesperrt.nr or "ART").strip()
    stellen = max(1, min(int(gesperrt.stellen or 4), 10))
    zaehler = max(1, int(gesperrt.naechste_nummer or 1))

    # Höchstens 1000 Versuche: Wer so viele Kollisionen hat, hat ein anderes
    # Problem, und eine Endlosschleife im Anlegen wäre das schlechtere Ende.
    for _ in range(1000):
        nummer = f"{praefix}-{zaehler:0{stellen}d}"
        if not _artikelnummer_vergeben(db, nummer):
            break
        zaehler += 1
    else:                                                   # pragma: no cover
        raise ValueError(
            f"Für die Gruppe „{gesperrt.name}“ konnte keine freie "
            f"Artikelnummer gefunden werden.")

    if festschreiben:
        gesperrt.naechste_nummer = zaehler + 1
        db.flush()

    return nummer


def _artikelnummer_vergeben(db: Session, nummer: str) -> bool:
    """Gibt es bereits einen Artikel mit dieser Nummer?

    Auch archivierte zählen: Ihre Nummer steht in alten Belegen und darf nicht
    ein zweites Mal vergeben werden.
    """
    et = (db.query(EntityType)
          .filter(EntityType.slug == ARTIKEL_SLUG)
          .first())
    if not et:
        return False
    return db.query(
        db.query(EntityRecord)
        .filter(EntityRecord.entity_type_id == et.id,
                EntityRecord.data["artikelnummer"].astext == nummer)
        .exists()
    ).scalar()


# ── Kontenkaskade ─────────────────────────────────────────────────────────────

def standard_erloeskonto(db: Session) -> Optional[str]:
    """Das im Kontenplan als Standard markierte Erlöskonto (Vorgabe 4000)."""
    konto = (db.query(AccountingAccount)
             .filter(AccountingAccount.is_default_erloes == True)   # noqa: E712
             .first())
    return konto.nr if konto else None


def steuerfall_zeile(db: Session, gruppe: Optional[ArticleGroup],
                     fall: str) -> Optional[ArticleGroupAccount]:
    """Die Konten-Zeile einer Artikelgruppe für einen Steuerfall."""
    if not gruppe:
        return None
    return (db.query(ArticleGroupAccount)
            .filter(ArticleGroupAccount.article_group_id == gruppe.id,
                    ArticleGroupAccount.steuerfall == fall)
            .first())


def konten_fuer_artikel(db: Session, artikel_data: Dict[str, Any],
                        fall: str = None
                        ) -> Tuple[Optional[str], Optional[str]]:
    """
    ``(erloes_konto_nr, aufwand_konto_nr)`` für einen Artikel-Datensatz.

    Reihenfolge des Erlöskontos:
    Artikel → Artikelgruppe×Steuerfall → Artikelgruppe → Vorgabe aus dem
    Kontenplan.

    **Ausnahme, die man kennen muss:** Ist der Steuerfall *nicht* das Inland,
    gewinnt die Steuerfall-Zeile gegen ein am Artikel eingetragenes Konto. Der
    Steuerfall ist eine rechtliche Eigenschaft des Geschäfts, das Artikelkonto
    dagegen eine Einordnung des Sortiments. Ein Artikel mit fest hinterlegtem
    4000 dürfte sonst eine innergemeinschaftliche Lieferung auf das
    Inlandserlöskonto buchen — und das wäre nicht „so eingestellt", sondern
    falsch. Im Inlandsfall gilt weiterhin das Artikelkonto.

    Ein Standard-Aufwandskonto gibt es weiterhin bewusst nicht: Ein falsch
    geratenes Aufwandskonto fällt im Einkauf schwerer auf als ein leeres.
    """
    artikel_data = artikel_data or {}
    fall = steuerfall_service.normieren(fall)

    erloes = _nicht_leer(artikel_data.get("erloes_konto"))
    aufwand = _nicht_leer(artikel_data.get("aufwand_konto"))

    gruppe = gruppe_nach_nr(db, _nicht_leer(artikel_data.get("artikelgruppe")))
    zeile = steuerfall_zeile(db, gruppe, fall)

    if fall in steuerfall_service.OHNE_INLANDSSTEUER and zeile and zeile.konto_nr:
        erloes = _nicht_leer(zeile.konto_nr)
    elif erloes is None and zeile:
        erloes = _nicht_leer(zeile.konto_nr)

    if gruppe:
        if erloes is None:
            erloes = _nicht_leer(gruppe.erloes_konto_nr)
        if aufwand is None:
            aufwand = _nicht_leer(gruppe.aufwand_konto_nr)

    if erloes is None:
        erloes = standard_erloeskonto(db)

    return erloes, aufwand


def steuerfall_des_kontakts(db: Session, contact_id) -> str:
    """Steuerfall eines Kontakts; ohne Angabe gilt das Inland.

    Bewusst das Inland als Rückfall: Wer fälschlich Inland bucht, zahlt zu viel
    Steuer — wer fälschlich steuerfrei bucht, schuldet sie nach. Von den beiden
    möglichen Irrtümern ist nur der erste heilbar, ohne dass es weh tut.
    """
    if not contact_id:
        return steuerfall_service.VORGABE
    rec = db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()
    if not rec:
        return steuerfall_service.VORGABE
    return steuerfall_service.normieren((rec.data or {}).get("steuerfall"))


def vorgaben_fuer_artikel(db: Session, artikel_data: Dict[str, Any],
                          contact_id=None) -> Dict[str, Any]:
    """
    Aufgelöste Vorgabewerte eines Artikels für die Belegposition.

    Liefert ``erloes_konto``, ``aufwand_konto``, ``ust_satz`` (als Zahl oder
    ``None`` bei fehlendem Satz), ``reverse_charge``, ``einheit``,
    ``artikelart`` und den zugrunde gelegten ``steuerfall``.

    ``contact_id`` ist der Kunde des Belegs. Ohne ihn gilt das Inland — dann
    verhält sich die Auflösung wie vor der Steuerfall-Matrix.

    Der Beleg soll diese Auflösung nicht selbst nachbauen: Zwei Auslegungen
    davon, welches Konto gilt, sind eine zu viel. Genau daran ist es vorher
    gescheitert, als das Erlöskonto zwar im Stammsatz stand, aber nie in der
    Position ankam.
    """
    artikel_data = artikel_data or {}
    fall = steuerfall_des_kontakts(db, contact_id)

    erloes, aufwand = konten_fuer_artikel(db, artikel_data, fall)
    gruppe = gruppe_nach_nr(db, _nicht_leer(artikel_data.get("artikelgruppe")))
    zeile = steuerfall_zeile(db, gruppe, fall)

    # Steuerangabe. Die Steuerfall-Zeile gewinnt, sobald sie etwas sagt — beim
    # Auslandsgeschäft ist der Satz eine Eigenschaft des Geschäfts, nicht des
    # Artikels. Sagt sie nichts (Inlandsfall), zählt der Artikel, dann die
    # Gruppe.
    ohne_satz = False
    satz = None
    if zeile is not None and (zeile.ohne_steuer or zeile.ust_satz is not None):
        ohne_satz = bool(zeile.ohne_steuer)
        satz = None if ohne_satz else zeile.ust_satz
    else:
        ust_roh = _nicht_leer(artikel_data.get("ust_satz"))
        if ust_roh is None and gruppe and gruppe.ust_satz is not None:
            ust_roh = str(gruppe.ust_satz)
        ohne_satz = ist_reverse_charge(ust_roh)
        satz = ust_satz_als_zahl(ust_roh)

    einheit = _nicht_leer(artikel_data.get("einheit"))
    if einheit is None and gruppe:
        einheit = _nicht_leer(gruppe.einheit)

    artikelart = _nicht_leer(artikel_data.get("artikelart"))
    if artikelart is None and gruppe:
        artikelart = _nicht_leer(gruppe.artikelart)

    return {
        "erloes_konto":  erloes,
        "aufwand_konto": aufwand,
        "ust_satz":      satz,
        "reverse_charge": ohne_satz,
        "einheit":       einheit or "Stk",
        "artikelart":    artikelart,
        "steuerfall":    fall,
    }


# ── USt-Satz ──────────────────────────────────────────────────────────────────

REVERSE_CHARGE = "Reverse Charge"


def ist_reverse_charge(wert: Any) -> bool:
    """Steht im USt-Feld die Kennzeichnung „Reverse Charge“?

    Der USt-Satz ist eine Auswahlliste mit Zahlen *und* diesem einen Wort. Das
    ist kein Schönheitsfehler: Bei Reverse Charge gibt es keinen Steuersatz von
    null, sondern gar keinen — die Belegposition führt dort ``tax_rate = NULL``.
    Eine Null würde in der UVA als steuerfreier Umsatz erscheinen und wäre damit
    schlicht falsch.
    """
    return isinstance(wert, str) and wert.strip().lower() in (
        "reverse charge", "reverse-charge", "rc")


def ust_satz_als_zahl(wert: Any) -> Optional[Decimal]:
    """USt-Satz als Zahl; ``None`` bei Reverse Charge oder leerer Angabe."""
    if wert is None or wert == "" or ist_reverse_charge(wert):
        return None
    try:
        return Decimal(str(wert).replace("%", "").replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def _nicht_leer(wert: Any) -> Optional[str]:
    """Leerstring und Leerzeichen zählen als „nicht gesetzt“.

    Ein leeres Formularfeld kommt als ``""`` an, nicht als ``None``. Ohne diese
    Umdeutung würde die Kaskade beim Artikel stehenbleiben und die Gruppe nie
    befragen — der häufigste Fall wäre damit der einzige, der nicht funktioniert.
    """
    if wert is None:
        return None
    text = str(wert).strip()
    return text or None
