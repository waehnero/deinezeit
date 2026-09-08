"""
Verkauf – Mahnwesen (Modulrecht Buchhaltung).

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import date
from decimal import Decimal
import logging

from app.db.base import get_db
from app.api.deps import (get_current_user, require_modul_rechte)
from app.models.user import User
from app.models.invoice import (Invoice, InvoiceDunning)
from app.models.masterdata import EntityRecord
from app.services import dunning as dunning_service
from app.schemas.invoice import (
    InvoiceResponse, DunningCandidate, DunningRunResponse, DunningCreateRequest, DunningEntry,
    DunningBlockRequest, DunningBatchRequest, DunningLevelConfig,
)
from app.core import zeit
from app.core.http import content_disposition

from app.api.invoice_common import (
    _audit,
    _zahlstand,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Mahnwesen
#
# Die Reihenfolge der Routen ist hier wichtig: Alles unter „/dunning/…" muss
# VOR „/{invoice_id}" stehen, sonst schluckt der Platzhalter den festen Pfad.
#
# Sämtliche Mahn-Endpunkte hängen am Zusatzrecht „Buchhaltung" — genau wie die
# Offene-Posten-Liste. Der Mahnlauf zeigt dieselben Zahlen: welcher Kunde
# schuldet wie viel seit wann. Wäre er ohne das Recht erreichbar, stünde die
# Sperre der OP-Liste nur auf dem Papier.
MAHN_RECHT = [Depends(require_modul_rechte("buchhaltung"))]
# ─────────────────────────────────────────────────────────────────────────────

def _kontakt(db: Session, contact_id):
    if not contact_id:
        return None
    return db.query(EntityRecord).filter(EntityRecord.id == contact_id).first()


@router.get("/dunning/run", response_model=DunningRunResponse, dependencies=MAHN_RECHT)
def dunning_run(
    stichtag: Optional[date] = Query(None, description="Standard: heute"),
    contact_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Mahnlauf-Vorschau: was wäre heute zu mahnen.

    Verschickt wird hier nichts. Die Liste enthält bewusst auch die nicht
    mahnbaren Belege samt Begründung — sonst rätselt man, warum eine Rechnung
    fehlt, die man erwartet hätte.
    """
    daten = dunning_service.kandidaten(db, stichtag, contact_id)
    return DunningRunResponse(
        stichtag=daten["stichtag"],
        items=[DunningCandidate(**z) for z in daten["items"]],
        dunnable_count=daten["dunnable_count"],
        levels=[DunningLevelConfig(**s) for s in daten["levels"]],
        interest_hint=daten["interest_hint"],
    )


def _mahnung_erzeugen(db: Session, inv: Invoice, level: Optional[int],
                      stichtag: date, force: bool, benutzer: str,
                      batch_id=None) -> InvoiceDunning:
    """
    Gemeinsamer Kern von Einzel- und Sammelmahnung.

    Wirft 400 mit einer Begründung, wenn nicht gemahnt werden darf. Die
    Mahnsperre ist auch mit ``force`` nicht zu übergehen: Sie wurde bewusst
    gesetzt, ein Sammellauf darf sie nicht versehentlich aushebeln.
    """
    if inv.doc_type != "rechnung":
        raise HTTPException(400, "Nur Rechnungen können gemahnt werden")
    if inv.status in ("entwurf", "storniert"):
        raise HTTPException(400, "Entwürfe und stornierte Belege werden nicht gemahnt")

    kontakt = _kontakt(db, inv.contact_id)
    grund = dunning_service.sperrgrund(inv, dunning_service.kontakt_gesperrt(kontakt))
    if grund:
        raise HTTPException(400, grund)

    _, offen, _ = _zahlstand(inv)
    if offen <= Decimal("0.00"):
        raise HTTPException(400, "Der Beleg ist beglichen — es gibt nichts zu mahnen")

    stufen = dunning_service.get_levels(db)
    if level is None:
        stufe = dunning_service.naechste_stufe(inv, stufen)
        if stufe is None:
            raise HTTPException(400, "Alle Mahnstufen sind ausgeschöpft")
    else:
        stufe = next((s for s in stufen if s["level"] == level), None)
        if stufe is None:
            raise HTTPException(400, f"Mahnstufe {level} ist nicht eingerichtet")

    if not force:
        ab = dunning_service.mahnbar_ab(inv, stufe)
        if ab is None:
            raise HTTPException(400, "Ohne Zahlungsziel gibt es keinen Verzug — "
                                     "bitte zuerst ein Zahlungsziel hinterlegen.")
        if ab > stichtag:
            raise HTTPException(400, f"Diese Mahnstufe ist erst ab "
                                     f"{ab:%d.%m.%Y} an der Reihe.")

    eintrag = dunning_service.mahnung_anlegen(
        db, inv, stufe, stichtag=stichtag, benutzer=benutzer,
        batch_id=batch_id, kontakt=kontakt)

    bezeichnung = stufe.get("label") or f"Stufe {stufe['level']}"
    _audit(db, inv, "mahnung",
           note=f"{bezeichnung} erstellt — offen "
                f"{float(eintrag.open_amount):.2f} {inv.currency}, Gebühr "
                f"{float(eintrag.fee):.2f}, Zinsen {float(eintrag.interest):.2f}",
           user_email=benutzer)
    return eintrag


@router.post("/dunning/batch", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
def dunning_batch(
    body: DunningBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sammelmahnlauf über eine Auswahl von Belegen.

    Belege desselben Kunden teilen sich eine ``batch_id`` — daraus entsteht das
    Sammelschreiben. Ein einzelner abgelehnter Beleg (Sperre, Wartezeit) lässt
    den Lauf NICHT scheitern: Er wird übersprungen, der Rest läuft durch.
    Andernfalls müsste man den Lauf nach jedem Sonderfall neu zusammenstellen.
    """
    stichtag = body.dunned_at or zeit.heute()
    if not body.invoice_ids:
        raise HTTPException(400, "Keine Belege ausgewählt")

    belege = db.query(Invoice).filter(Invoice.id.in_(body.invoice_ids)).all()
    batch_je_kontakt: dict = {}
    ergebnis = []

    for inv in belege:
        schluessel = inv.contact_id or inv.id
        batch_id = batch_je_kontakt.setdefault(schluessel, uuid4())
        try:
            ergebnis.append(_mahnung_erzeugen(
                db, inv, None, stichtag, body.force, current_user.email, batch_id))
        except HTTPException:
            continue                    # Begründung steht im Mahnlauf

    if not ergebnis:
        raise HTTPException(400, "Kein einziger der gewählten Belege war mahnbar")
    db.commit()
    return ergebnis


@router.get("/dunning/{dunning_id}/pdf", dependencies=MAHN_RECHT)
def dunning_pdf(
    dunning_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Mahnschreiben als PDF. Bei einer Sammelmahnung stehen alle Belege des Laufs drauf."""
    from app.services.dunning_pdf import generate_dunning_pdf

    eintrag = db.query(InvoiceDunning).filter(InvoiceDunning.id == dunning_id).first()
    if not eintrag:
        raise HTTPException(404, "Mahnung nicht gefunden")

    pdf_bytes, dateiname = generate_dunning_pdf(db, eintrag)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition("inline", dateiname)})


@router.delete("/dunning/{dunning_id}", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
def dunning_zuruecknehmen(
    dunning_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Nimmt eine Mahnung zurück (Fehleingabe) und setzt die Stufe auf den
    verbliebenen Höchststand zurück.

    Das Schreiben selbst ist damit natürlich nicht zurückgeholt — der Vorgang
    bleibt deshalb im Änderungsprotokoll stehen.
    """
    eintrag = db.query(InvoiceDunning).filter(InvoiceDunning.id == dunning_id).first()
    if not eintrag:
        raise HTTPException(404, "Mahnung nicht gefunden")

    inv = db.query(Invoice).filter(Invoice.id == eintrag.invoice_id).first()
    beschreibung = (f"{eintrag.label or f'Stufe {eintrag.level}'} vom "
                    f"{eintrag.dunned_at:%d.%m.%Y} zurückgenommen")
    db.delete(eintrag)
    db.flush()
    db.refresh(inv)

    rest = sorted(inv.dunnings, key=lambda d: d.level)
    inv.dunning_level = rest[-1].level if rest else 0
    inv.dunning_last_at = max((d.dunned_at for d in rest), default=None)
    _audit(db, inv, "mahnung", note=beschreibung, user_email=current_user.email)

    db.commit()
    db.refresh(inv)
    return sorted(inv.dunnings, key=lambda d: d.level)


@router.get("/{invoice_id}/dunning", response_model=List[DunningEntry], dependencies=MAHN_RECHT)
def dunning_historie(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Mahnhistorie eines Belegs."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    return sorted(inv.dunnings, key=lambda d: d.level)


@router.post("/{invoice_id}/dunning", response_model=DunningEntry, dependencies=MAHN_RECHT)
def dunning_anlegen(
    invoice_id: UUID,
    body: DunningCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erzeugt eine Mahnung zu einem einzelnen Beleg."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    eintrag = _mahnung_erzeugen(db, inv, body.level, body.dunned_at or zeit.heute(),
                                body.force, current_user.email)
    db.commit()
    db.refresh(eintrag)
    return eintrag


@router.post("/{invoice_id}/dunning-block", response_model=InvoiceResponse, dependencies=MAHN_RECHT)
def dunning_sperre(
    invoice_id: UUID,
    body: DunningBlockRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Setzt oder löst die Mahnsperre für einen Beleg (Ratenvereinbarung,
    strittige Forderung, Klärung mit dem Kunden).
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    inv.dunning_blocked = bool(body.blocked)
    inv.dunning_block_reason = body.reason if body.blocked else None
    inv.updated_by = current_user.email
    _audit(db, inv, "mahnung",
           note=(f"Mahnsperre gesetzt: {body.reason or 'ohne Begründung'}"
                 if body.blocked else "Mahnsperre aufgehoben"),
           user_email=current_user.email)
    db.commit()
    db.refresh(inv)
    return inv
