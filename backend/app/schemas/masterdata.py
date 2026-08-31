from pydantic import BaseModel, field_validator
from typing import Optional, List, Any, Dict
from uuid import UUID
from datetime import datetime
from decimal import Decimal


# ── Felddefinitionen ──────────────────────────────────────────────────────────

class FieldDefinitionBase(BaseModel):
    name: str
    key: str
    field_type: str   # text, number, date, email, phone, dropdown, checkbox, textarea, url, relation
    is_required: bool = False
    is_unique: bool = False
    show_in_list: bool = True
    sort_order: int = 0
    col_span: int = 12   # 3=25%, 4=33%, 6=50%, 9=75%, 12=100%
    tab: Optional[str] = None  # Tab-Name, z.B. "Allgemein", "Bankdaten"
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    linked_type_slug: Optional[str] = None  # Für relation-Felder: Slug des Ziel-EntityType
    lookup_source: Optional[str] = None     # Für lookup-Felder: "konten" | "artikelgruppen"


class FieldDefinitionCreate(FieldDefinitionBase):
    pass


class FieldDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    is_unique: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None
    col_span: Optional[int] = None
    tab: Optional[str] = None
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    linked_type_slug: Optional[str] = None
    lookup_source: Optional[str] = None


class FieldDefinitionResponse(FieldDefinitionBase):
    id: UUID
    entity_type_id: UUID
    created_at: datetime
    # Systemfeld: nicht löschbar, Schlüssel und Typ liegen fest. Das Frontend
    # blendet die Lösch-Schaltfläche danach aus; erzwungen wird es im Backend.
    is_system: bool = False

    @field_validator('is_system', mode='before')
    @classmethod
    def system_none_to_false(cls, v):
        return bool(v)

    class Config:
        from_attributes = True


# ── Stammdaten-Typen ─────────────────────────────────────────────────────────

class EntityTypeBase(BaseModel):
    name: str
    slug: str
    icon: Optional[str] = "Database"
    color: Optional[str] = "#6b7280"
    description: Optional[str] = None
    sort_order: int = 0


class EntityTypeCreate(BaseModel):
    """Eingabe-Schema: slug wird vom Backend automatisch aus dem Namen generiert."""
    name: str
    icon: Optional[str] = "Database"
    color: Optional[str] = "#6b7280"
    description: Optional[str] = None
    sort_order: int = 0


class EntityTypeUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class EntityTypeResponse(EntityTypeBase):
    id: UUID
    is_active: bool
    record_count: int = 0
    tabs: List[str] = []           # Geordnete Tab-Liste, z.B. ["Allgemein", "Bankdaten"]
    fields: List[FieldDefinitionResponse] = []
    created_at: datetime

    # None aus DB → leere Liste (Spalte neu, Altdaten haben NULL)
    @field_validator('tabs', mode='before')
    @classmethod
    def tabs_none_to_list(cls, v):
        return v if v is not None else []

    class Config:
        from_attributes = True


# ── Datensätze ────────────────────────────────────────────────────────────────

class EntityRecordCreate(BaseModel):
    data: Dict[str, Any]


class EntityRecordUpdate(BaseModel):
    data: Dict[str, Any]


class EntityRecordResponse(BaseModel):
    id: UUID
    entity_type_id: UUID
    data: Dict[str, Any]
    display_name: Optional[str]
    created_by: Optional[UUID]
    updated_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    anonymized_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EntityRecordListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[EntityRecordResponse]


# ── Feldreihenfolge ───────────────────────────────────────────────────────────

class FieldSortOrder(BaseModel):
    field_id: UUID
    sort_order: int


class UpdateFieldSortOrders(BaseModel):
    orders: List[FieldSortOrder]


# ── Import (CSV / Excel) ──────────────────────────────────────────────────────

class ImportRequest(BaseModel):
    """Ein Importlauf — als Probelauf oder zum Schreiben.

    ``rows``: bereits zugeordnete Zeilen, Schlüssel sind Feld-Keys. Das Lesen
    der Datei und die Spaltenzuordnung passieren im Browser; hierher kommt nur
    das Ergebnis.
    """
    rows: List[Dict[str, Any]]
    # Feld-Key, über den vorhandene Datensätze wiedererkannt werden. Ohne
    # Angabe wird jede Zeile neu angelegt (altes Verhalten).
    match_field: Optional[str] = None
    # Vorgabe ist der Probelauf: Ein versehentlich abgeschickter Aufruf darf
    # keine 2000 Datensätze anlegen.
    dry_run: bool = True
    # Nur wirksam außerhalb des Probelaufs: beanstandete Zeilen auslassen und
    # den Rest schreiben. Ohne diese Zusage wird bei Beanstandungen nichts
    # geschrieben.
    skip_invalid: bool = False


class ImportIssue(BaseModel):
    zeile: int
    feld: Optional[str] = None
    wert: str = ""
    grund: str


class ImportReport(BaseModel):
    geprueft: int
    anlegen: int
    aktualisieren: int
    angelegt: int
    aktualisiert: int
    uebersprungen: int
    beanstandungen: List[ImportIssue]


# ── Artikelgruppen ────────────────────────────────────────────────────────────

class ArticleGroupBase(BaseModel):
    """Artikelgruppe — Sortimentsstruktur, Nummernkreis und Buchungsvorgabe."""
    nr: str
    name: str
    beschreibung: Optional[str] = None

    praefix: Optional[str] = None
    stellen: int = 4

    erloes_konto_nr: Optional[str] = None
    aufwand_konto_nr: Optional[str] = None
    ust_satz: Optional[Decimal] = None
    artikelart: Optional[str] = None
    einheit: Optional[str] = None

    is_active: bool = True
    sort_order: int = 0


class ArticleGroupCreate(ArticleGroupBase):
    # Startwert des Zählers. Wer Altdaten übernimmt, setzt ihn einmal über die
    # höchste bereits vergebene Nummer und vermeidet so eine Kollisionsschleife
    # bei jedem der nächsten Artikel.
    naechste_nummer: int = 1


class ArticleGroupUpdate(BaseModel):
    nr: Optional[str] = None
    name: Optional[str] = None
    beschreibung: Optional[str] = None
    praefix: Optional[str] = None
    stellen: Optional[int] = None
    naechste_nummer: Optional[int] = None
    erloes_konto_nr: Optional[str] = None
    aufwand_konto_nr: Optional[str] = None
    ust_satz: Optional[Decimal] = None
    artikelart: Optional[str] = None
    einheit: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ArticleGroupAccountBase(BaseModel):
    """Konto und Steuerangabe einer Artikelgruppe für einen Steuerfall.

    ``ohne_steuer`` und ``ust_satz`` sind nicht dasselbe: ``ohne_steuer``
    heißt „kein Satz" (Reverse Charge), ``ust_satz = 0`` heißt „steuerfrei mit
    Satz null" (IG-Lieferung, Ausfuhr). Beides leer heißt „es gilt der Satz des
    Artikels" — der Inlandsfall.
    """
    steuerfall: str
    konto_nr: Optional[str] = None
    ust_satz: Optional[Decimal] = None
    ohne_steuer: bool = False


class ArticleGroupAccountResponse(ArticleGroupAccountBase):
    id: UUID
    # Anzeigename des Steuerfalls, damit das Frontend keine eigene
    # Übersetzungstabelle führen muss, die auseinanderlaufen kann.
    bezeichnung: Optional[str] = None

    class Config:
        from_attributes = True


class ArticleGroupResponse(ArticleGroupBase):
    id: UUID
    naechste_nummer: int
    # Konten je Steuerfall; leer, solange nichts gepflegt ist.
    konten: List[ArticleGroupAccountResponse] = []
    # Wie viele Artikel hängen an der Gruppe? Entscheidet im Frontend darüber,
    # ob Löschen angeboten wird.
    artikel_anzahl: int = 0
    # Vorschau der nächsten Nummer, damit die Verwaltung zeigt, was
    # herauskommt, statt Präfix und Zähler im Kopf zusammensetzen zu lassen.
    naechste_artikelnummer: Optional[str] = None

    class Config:
        from_attributes = True


class ArtikelVorgaben(BaseModel):
    """Aufgelöste Vorgabewerte eines Artikels.

    Kaskade: Artikel → Artikelgruppe×Steuerfall → Artikelgruppe → Standard.
    """
    erloes_konto: Optional[str] = None
    aufwand_konto: Optional[str] = None
    ust_satz: Optional[Decimal] = None
    reverse_charge: bool = False
    einheit: str = "Stk"
    artikelart: Optional[str] = None
    # Zugrunde gelegter Steuerfall — damit das Belegformular anzeigen kann,
    # *warum* dieses Konto gilt, statt es nur zu setzen.
    steuerfall: str = "inland"


class SteuerfallInfo(BaseModel):
    kennung: str
    bezeichnung: str
