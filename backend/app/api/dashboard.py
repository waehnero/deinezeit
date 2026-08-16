"""
Dashboard — gesammelte Kennzahlen für die Startseite.

Ein einziger Aufruf ersetzt die bisher bis zu 13 Einzelanfragen beim Öffnen
des Dashboards. Angefragt wird gezielt: das Frontend kennt seit der
Ansichten-Verwaltung genau die Bausteine, die gerade sichtbar sind, und lässt
nur für diese rechnen.

Die eigentliche Berechnung steht in services/dashboard.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models.user import User
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kennzahlen")
async def get_kennzahlen(
    bausteine: str = Query(
        "",
        description="Kommaliste der gewünschten Bausteine, z. B. "
                    "'aufgaben,rechnungen,projekte'. Leer = alle erlaubten.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kennzahlen der angefragten Dashboard-Bausteine.

    Bausteine, für die dem Benutzer das Modul fehlt, fehlen in der Antwort —
    das ist kein Fehler. Ein 403 für den gesamten Aufruf würde bedeuten, dass
    eine einzige gesperrte Kachel das ganze Dashboard leer lässt.

    Ohne Parameter werden alle Bausteine geliefert, die der Benutzer sehen
    darf. Das ist als Rückfalloption gedacht; im Normalfall fragt das Frontend
    gezielt an und spart sich damit die Rechenarbeit für unsichtbare Kacheln.
    """
    gewuenscht = [b.strip() for b in bausteine.split(",") if b.strip()]
    if not gewuenscht:
        gewuenscht = sorted(dashboard_service.BAUSTEIN_MODUL)

    daten = await dashboard_service.kennzahlen(db, current_user, gewuenscht)
    return {"kennzahlen": daten}
