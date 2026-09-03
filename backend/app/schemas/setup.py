from typing import Optional
from pydantic import BaseModel


class SetupStatusResponse(BaseModel):
    """Zustand des Erstinstallations-Assistenten."""
    needs_setup: bool          # True = noch kein Benutzer vorhanden
    user_count: int
    token_required: bool = False   # True = SETUP_TOKEN ist gesetzt und wird verlangt


class CompanyData(BaseModel):
    """Firmen-/Mandantenstammdaten fuer den Briefkopf (alles optional)."""
    firmenname: Optional[str] = None
    ansprechperson: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    adresse: Optional[str] = None
    plz: Optional[str] = None
    ort: Optional[str] = None
    land: Optional[str] = None
    uid: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bankname: Optional[str] = None


class SetupInitRequest(BaseModel):
    """Erstellt den ersten Admin und optional die Firma (Briefkopf)."""
    admin_email: str
    admin_full_name: str
    admin_password: str
    language: str = "de"
    company: Optional[CompanyData] = None
    # Einrichtungs-Token aus der .env (SETUP_TOKEN). Pflicht, sobald der
    # Betreiber einen gesetzt hat — siehe api/setup.py.
    setup_token: Optional[str] = None


class SetupInitResponse(BaseModel):
    """Antwort des Erstinstallations-Assistenten.

    ``refresh_token`` bleibt leer — wie beim normalen Anmelden steckt der
    langlebige Token in einem ``httpOnly``-Cookie und ist für JavaScript nicht
    lesbar. Das Feld bleibt im Schema, damit eine zwischengespeicherte,
    ältere Oberfläche nicht über ein fehlendes Feld stolpert.
    """
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    company_contact_id: Optional[str] = None
