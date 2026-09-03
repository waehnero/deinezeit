"""
Monatsabschluss — Prüfen, Abschließen, Übergeben.

Liegt bewusst in einem eigenen Router (nicht unter ``/invoices``), weil der
Abschluss zur Buchhaltung gehört und nicht zur Belegerfassung. Deshalb hängt
er auch am Modul ``buchhaltung``.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.period import AccountingPeriod, PeriodHandover
from app.services import period_service
from app.schemas.period import (PeriodResponse, PeriodCheckResponse,
                                PeriodReopenRequest, HandoverResponse)

router = APIRouter(prefix="/periods", tags=["Monatsabschluss"])


@router.get("", response_model=List[PeriodResponse])
def list_periods(
    jahr: Optional[int] = Query(None, description="Standard: laufendes Jahr"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Alle zwölf Monate eines Jahres mit ihrem Stand.

    Monate ohne Eintrag sind offen — es wird nichts im Voraus angelegt.
    """
    y = jahr or datetime.now().year
    vorhanden = {p.month: p for p in db.query(AccountingPeriod).filter_by(year=y).all()}

    ergebnis = []
    for monat in range(1, 13):
        p = vorhanden.get(monat)
        ergebnis.append(PeriodResponse(
            jahr=y, monat=monat, monatsname=period_service.MONATSNAMEN[monat],
            status=p.status if p else "offen",
            closed_at=p.closed_at if p else None,
            closed_by=p.closed_by if p else None,
            reopened_at=p.reopened_at if p else None,
            reopened_by=p.reopened_by if p else None,
            reopen_reason=p.reopen_reason if p else None,
            totals=p.totals if p else None,
            summen=period_service._summen(db, y, monat),
        ))
    return ergebnis


@router.get("/{jahr}/{monat}/check", response_model=PeriodCheckResponse)
def check_period(
    jahr: int, monat: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Prüfliste: Was steht dem Abschluss im Weg?"""
    return period_service.pruefliste(db, jahr, monat)


@router.post("/{jahr}/{monat}/close", response_model=PeriodResponse)
def close_period(
    jahr: int, monat: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Schließt den Monat ab. Danach sind Belege mit Datum in diesem Monat
    gesperrt — weder neue noch Änderungen an vorhandenen.
    """
    p = period_service.abschliessen(db, jahr, monat, current_user.email)
    return PeriodResponse(
        jahr=p.year, monat=p.month, monatsname=period_service.MONATSNAMEN[p.month],
        status=p.status, closed_at=p.closed_at, closed_by=p.closed_by,
        reopened_at=p.reopened_at, reopened_by=p.reopened_by,
        reopen_reason=p.reopen_reason, totals=p.totals,
        summen=period_service._summen(db, p.year, p.month),
    )


@router.post("/{jahr}/{monat}/reopen", response_model=PeriodResponse)
def reopen_period(
    jahr: int, monat: int,
    body: PeriodReopenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Öffnet einen abgeschlossenen Monat wieder — nur mit Begründung.

    Der Vorgang wird nicht verwischt: Wer wann warum geöffnet hat, bleibt am
    Monat dokumentiert.
    """
    p = period_service.wieder_oeffnen(db, jahr, monat, current_user.email, body.grund)
    return PeriodResponse(
        jahr=p.year, monat=p.month, monatsname=period_service.MONATSNAMEN[p.month],
        status=p.status, closed_at=p.closed_at, closed_by=p.closed_by,
        reopened_at=p.reopened_at, reopened_by=p.reopened_by,
        reopen_reason=p.reopen_reason, totals=p.totals,
        summen=period_service._summen(db, p.year, p.month),
    )


@router.get("/{jahr}/{monat}/package")
async def download_package(
    jahr: int, monat: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Übergabepaket als ZIP: Buchungsjournal, Belegjournal, Umsatzsteuer-
    Aufstellung, offene Posten und jeder Beleg als PDF — dazu ein
    Inhaltsverzeichnis mit Prüfsumme je Datei.

    Funktioniert auch bei offenem Monat (etwa für eine Zwischenübergabe);
    jede Erzeugung wird als Übergabe protokolliert.
    """
    inhalt, handover = await period_service.paket_bauen(db, jahr, monat, current_user)
    name = f"uebergabe_{jahr}-{monat:02d}.zip"
    return Response(
        content=inhalt, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"',
                 "X-Handover-Checksum": handover.checksum or ""},
    )


@router.get("/{jahr}/{monat}/handovers", response_model=List[HandoverResponse])
def list_handovers(
    jahr: int, monat: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Übergabe-Historie des Monats, neueste zuerst."""
    return (db.query(PeriodHandover)
            .filter_by(year=jahr, month=monat)
            .order_by(PeriodHandover.created_at.desc()).all())
