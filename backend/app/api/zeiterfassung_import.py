"""
Zeiterfassung — Import von Projektzeiten aus Fremdsystemen
==========================================================

Drei Endpunkte unter ``/zeiterfassung/import``:

  GET  /felder   Zielfelder für die Spaltenzuordnung (Kern- + Custom-Felder)
  POST /pdf      PDF → Tabelle über die KI-Schnittstelle (schreibt nichts)
  POST /         Zeilen prüfen (``dry_run``) oder schreiben

Das Modulrecht hängt am Router (``main.py``): GET verlangt „Ansehen", POST
„Ändern" an der Zeiterfassung. Wer für ANDERE importiert, muss Administrator
sein — das prüft der Dienst, weil es von den Daten abhängt.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.models.user import User, UserRole
from app.services.ki import load_ki_settings
from app.services.zeiten_import import MAX_ZEILEN, zeiten_import, zielfelder
from app.services.zeiten_pdf import MAX_PDF_BYTES, PdfLesefehler, pdf_zu_tabelle

router = APIRouter(prefix="/zeiterfassung/import", tags=["Zeiterfassung"])


class ZielfeldAntwort(BaseModel):
    key: str
    name: str
    synonyme: List[str] = []


class ZeitenImportAnfrage(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list, max_length=MAX_ZEILEN)
    user_id: Optional[UUID] = None       # nur Admin: ein Benutzer für die ganze Datei
    dry_run: bool = True
    skip_invalid: bool = False


class ZeitenImportBeanstandung(BaseModel):
    zeile: int
    feld: Optional[str] = None
    wert: str = ""
    grund: str


class ZeitenImportBericht(BaseModel):
    geprueft: int
    anlegen: int
    angelegt: int
    uebersprungen: int
    minuten_gesamt: int
    beanstandungen: List[ZeitenImportBeanstandung]


class PdfTabelle(BaseModel):
    spalten: List[str]
    zeilen: List[Dict[str, str]]
    hinweise: List[str] = []


def _ist_admin(user: User) -> bool:
    return user.role == UserRole.admin


@router.get("/felder", response_model=List[ZielfeldAntwort])
def import_felder(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Felder, auf die der Assistent eine Spalte zuordnen kann."""
    return zielfelder(db, _ist_admin(current_user))


@router.post("/pdf", response_model=PdfTabelle)
def import_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """PDF über die KI in eine Tabelle überführen. Gespeichert wird NICHTS —
    weder die Datei noch die Tabelle. Die Tabelle geht an den Assistenten
    zurück und von dort durch denselben Prüflauf wie jede andere Datei."""
    # Ein Byte mehr lesen als erlaubt: So fällt eine zu große Datei auf, ohne
    # dass sie ganz in den Speicher muss.
    inhalt = file.file.read(MAX_PDF_BYTES + 1)
    try:
        return pdf_zu_tabelle(load_ki_settings(db), inhalt,
                              file.filename or "zeiten.pdf")
    except PdfLesefehler as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=ZeitenImportBericht)
def import_zeiten(
    body: ZeitenImportAnfrage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Projektzeiten importieren — als Probelauf oder zum Schreiben."""
    try:
        bericht = zeiten_import.durchfuehren(
            db, body.rows, current_user, _ist_admin(current_user),
            fixer_benutzer_id=body.user_id,
            probelauf=body.dry_run,
            fehlerhafte_ueberspringen=body.skip_invalid,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return ZeitenImportBericht(
        geprueft=bericht.geprueft,
        anlegen=bericht.anlegen,
        angelegt=bericht.angelegt,
        uebersprungen=bericht.uebersprungen,
        minuten_gesamt=bericht.minuten_gesamt,
        beanstandungen=[ZeitenImportBeanstandung(
            zeile=b.zeile, feld=b.feld, wert=b.wert, grund=b.grund)
            for b in bericht.beanstandungen],
    )
