from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import StreamingResponse, Response
import csv
import io
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin, require_module
from app.core.berechtigungen import SCHREIBEN, hat_recht
from app.models.user import User
from app.models.accounting import AccountingAccount
from app.models.masterdata import (EntityType, FieldDefinition, EntityRecord,
                                   ArticleGroup, ArticleGroupAccount)
from app.schemas.masterdata import (
    EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse,
    FieldDefinitionCreate, FieldDefinitionUpdate, FieldDefinitionResponse,
    EntityRecordCreate, EntityRecordUpdate, EntityRecordResponse,
    EntityRecordListResponse, UpdateFieldSortOrders,
    ImportRequest, ImportReport, ImportIssue,
    ArticleGroupCreate, ArticleGroupUpdate, ArticleGroupResponse,
    ArticleGroupAccountBase, ArticleGroupAccountResponse,
    ArtikelVorgaben, SteuerfallInfo,
)
from app.services.masterdata_service import masterdata_service
from app.services.masterdata_import import masterdata_import
from app.services import integrity
from app.services import artikelstamm
from app.services import steuerfall as steuerfall_service
from app.core.zeitprojekte import ZEITPROJEKTE_SLUG

router = APIRouter(prefix="/masterdata", tags=["Stammdaten"])

# Erlaubte Feldtypen. ``lookup`` (Auswahl aus Kontenplan oder Artikelgruppen)
# und ``image`` (ein Bild am Datensatz) sind mit dem Ausbau des Artikelstamms
# dazugekommen, gelten aber für jeden Stammdaten-Typ.
VALID_FIELD_TYPES = ['text', 'number', 'date', 'email', 'phone', 'dropdown',
                     'checkbox', 'textarea', 'url', 'relation', 'lookup',
                     'image']

# Verzeichnisse, aus denen ein lookup-Feld wählen kann.
LOOKUP_SOURCES = ['konten', 'artikelgruppen']

# Ablageort für Stammdaten-Bilder im Objektspeicher.
BILD_PRAEFIX = "stammdaten/bilder/"


def _csv_wert(wert, feld) -> str:
    """Feldwert für den CSV-Export.

    Zusammengesetzte Werte dürfen nicht als Python-Darstellung in der Datei
    landen — ``{'key': 'stammdaten/bilder/…'}`` in einer Tabellenspalte ist
    weder lesbar noch wieder importierbar. Verknüpfungen zeigen ihren
    Anzeigenamen, Bilder ihren Dateinamen.
    """
    if wert is None:
        return ''
    if isinstance(wert, dict):
        return wert.get('display_name') or wert.get('name') or ''
    return wert


def _schreibrecht_pruefen(user: User, slug: Optional[str] = None) -> None:
    """Schreibrecht auf Stammdaten verlangen.

    Der Router hat bewusst keine Modulsperre: Stammdaten müssen aus jedem
    anderen Modul heraus *lesbar* sein (Auswahlfelder in Zeiterfassung,
    Belegen, Aufgaben). Nur das Ändern ist eingeschränkt — und zwar seit
    Migration 0055 über das Schreibrecht statt über die reine Modulfreigabe.

    Ausnahme Zeitprojekte: Sie sind aus den Stammdaten in die Zeiterfassung
    gewandert (Beschluss 01.09.2026) und hängen deshalb am Schreibrecht des
    Moduls „Zeiterfassung". Wer Zeiten bucht, legt das Projekt dazu an — ohne
    dafür Kontakte und Artikel ändern zu dürfen. Ohne diese Fallunterscheidung
    stünde die Seite im Zeiterfassungs-Menü, ließe sich aber nur mit
    Stammdaten-Recht bedienen; das fällt erst beim Speichern auf.
    """
    modul = ("zeiterfassung" if slug == ZEITPROJEKTE_SLUG else "stammdaten")
    if not hat_recht(user, modul, SCHREIBEN):
        beschriftung = "Zeiterfassung" if modul == "zeiterfassung" else "Stammdaten"
        raise HTTPException(
            status_code=403,
            detail=(f"Kein Zugriff — für „{beschriftung}“ fehlt das Recht "
                    "„Anlegen und ändern“."))


# Archivieren, Wiederherstellen und Löschen bleiben bewusst bei ``require_admin``
# und hängen NICHT am Löschrecht der Gruppen (geprüft und verworfen 18.08.2026).
#
# Der Grund liegt nicht in der Fachlichkeit, sondern im Rechtemodell: Wer keiner
# Gruppe angehört, fällt auf ``allowed_modules`` zurück, und ``NULL`` heißt dort
# „alles erlaubt" — einschließlich Löschen. Ein Wechsel auf ``hat_recht`` würde
# das Löschen von Stammdaten in jeder Installation freigeben, in der die Gruppen
# noch nicht gepflegt sind. Genau davor schützt die Admin-Regel seit dem
# Beschluss Löschregeln vom 11.07.2026 (Anlass: verlorene Projekte und
# Stundenkonten auf dem Server).
#
# Archivieren zählt dabei als Löschen, nicht als Ändern: Der Datensatz
# verschwindet aus allen Auswahllisten. Es als Schreiben zu führen, wäre eine
# Hintertür an der Sperre vorbei.
#
# Sobald überall Gruppen gepflegt sind und der Rückfall auf ``allowed_modules``
# entfallen kann, ist die Umstellung auf ``hat_recht(user, "stammdaten",
# LOESCHEN)`` der richtige nächste Schritt — vorher nicht.


# ─── Stammdaten-Typen ─────────────────────────────────────────────────────────

@router.get("/types", response_model=List[EntityTypeResponse])
async def list_entity_types(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Stammdaten-Typen abrufen (z.B. Kunden, Lieferanten, Projekte)."""
    types = masterdata_service.list_entity_types(db)
    result = []
    for et in types:
        count = db.query(EntityRecord).filter(EntityRecord.entity_type_id == et.id).count()
        r = EntityTypeResponse.model_validate(et)
        r.record_count = count
        result.append(r)
    return result


@router.post("/types", response_model=EntityTypeResponse)
async def create_entity_type(
    body: EntityTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neuen Stammdaten-Typ anlegen (nur Admin)."""
    return masterdata_service.create_entity_type(
        db, body.name, body.icon, body.color, body.description, body.sort_order
    )


@router.get("/types/{slug}", response_model=EntityTypeResponse)
async def get_entity_type(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Einen Stammdaten-Typ abrufen (inkl. aller Felddefinitionen)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    count = db.query(EntityRecord).filter(EntityRecord.entity_type_id == et.id).count()
    r = EntityTypeResponse.model_validate(et)
    r.record_count = count
    return r


@router.put("/types/{slug}", response_model=EntityTypeResponse)
async def update_entity_type(
    slug: str,
    body: EntityTypeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Stammdaten-Typ bearbeiten (nur Admin)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    return masterdata_service.update_entity_type(db, et, body.model_dump(exclude_none=True))


@router.delete("/types/{slug}")
async def delete_entity_type(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Stammdaten-Typ deaktivieren (nur Admin)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    masterdata_service.delete_entity_type(db, et)
    return {"message": f"'{et.name}' wurde deaktiviert"}


# ─── Felddefinitionen ─────────────────────────────────────────────────────────

@router.post("/types/{slug}/fields", response_model=FieldDefinitionResponse)
async def add_field(
    slug: str,
    body: FieldDefinitionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neues Feld zum Stammdaten-Typ hinzufügen."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    if body.field_type not in VALID_FIELD_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"Ungültiger Feldtyp. Erlaubt: {VALID_FIELD_TYPES}")

    if body.field_type == 'relation' and not body.linked_type_slug:
        raise HTTPException(status_code=400, detail="Verknüpfungs-Felder benötigen einen Ziel-Typ (linked_type_slug)")

    if body.field_type == 'lookup' and body.lookup_source not in LOOKUP_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=("Auswahl-aus-Verzeichnis-Felder benötigen eine Quelle "
                    f"(lookup_source). Erlaubt: {LOOKUP_SOURCES}"))

    feld = masterdata_service.add_field(
        db, et, body.name, body.field_type,
        is_required=body.is_required,
        is_unique=body.is_unique,
        show_in_list=body.show_in_list,
        col_span=body.col_span,
        tab=body.tab,
        options=body.options,
        placeholder=body.placeholder,
        default_value=body.default_value,
        linked_type_slug=body.linked_type_slug,
    )
    # ``add_field`` kennt die Quelle nicht — sie kam erst mit dem lookup-Typ
    # dazu. Nachträglich setzen statt die Signatur des Dienstes zu erweitern,
    # die von Zeiterfassung und Projektplan mitbenutzt wird.
    if body.lookup_source:
        feld.lookup_source = body.lookup_source
        db.commit()
        db.refresh(feld)
    return feld


@router.put("/types/{slug}/fields/{field_id}", response_model=FieldDefinitionResponse)
async def update_field(
    slug: str,
    field_id: UUID,
    body: FieldDefinitionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Felddefinition bearbeiten.

    Bei Systemfeldern bleibt der Feldtyp gesperrt: Umbenennen, verschieben und
    ausblenden ist erlaubt, aber aus ``preis`` ein Textfeld zu machen, würde
    jede Preisrechnung im Beleg stillschweigend kaputtmachen.
    """
    field = masterdata_service.get_field(db, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")

    # ``exclude_unset`` ist hier wesentlich, nicht kosmetisch: ``update_field``
    # schreibt ``options`` auch dann, wenn der Wert ``None`` ist (damit sich
    # eine Auswahlliste absichtlich leeren lässt). Ohne ``exclude_unset``
    # füllt Pydantic jedes nicht mitgeschickte Feld mit ``None`` — und der
    # Feld-Editor schickt nur Name, Pflicht und Listenanzeige. Ein simples
    # Umbenennen hat damit die komplette Auswahlliste des Feldes gelöscht,
    # ohne Meldung. Aufgefallen beim USt-Satz und der Einheit im Artikel.
    daten = body.model_dump(exclude_unset=True)
    if field.is_system and daten.get("field_type") and daten["field_type"] != field.field_type:
        raise HTTPException(
            status_code=400,
            detail=(f"„{field.name}“ ist ein Systemfeld — der Feldtyp liegt fest, "
                    "weil andere Module damit rechnen. Bezeichnung, Register "
                    "und Breite lassen sich ändern."))
    return masterdata_service.update_field(db, field, daten)


@router.delete("/types/{slug}/fields/{field_id}")
async def delete_field(
    slug: str,
    field_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Feld entfernen.

    Systemfelder sind ausgenommen. Sie sind keine freie Ausstattung, sondern
    Voraussetzung anderer Module: Der Belegpicker liest ``preis``, ``einheit``
    und ``erloes_konto`` direkt aus dem Artikeldatensatz. Verschwindet eines
    davon, kommt im Beleg still eine Null oder ein leeres Konto an — ohne
    Fehlermeldung, an der man es merken würde. Wer das Feld nicht braucht,
    blendet es aus (``show_in_list``) und nimmt es aus dem Register.
    """
    field = masterdata_service.get_field(db, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    if field.is_system:
        raise HTTPException(
            status_code=400,
            detail=(f"„{field.name}“ ist ein Systemfeld und kann nicht gelöscht "
                    "werden — andere Module lesen es. Du kannst es stattdessen "
                    "aus der Listenansicht und dem Register nehmen."))
    masterdata_service.delete_field(db, field)
    return {"message": f"Feld '{field.name}' wurde entfernt"}


@router.put("/types/{slug}/fields-order")
async def update_field_order(
    slug: str,
    body: UpdateFieldSortOrders,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reihenfolge der Felder aktualisieren."""
    masterdata_service.update_field_order(
        db, [{"field_id": o.field_id, "sort_order": o.sort_order} for o in body.orders]
    )
    return {"message": "Reihenfolge gespeichert"}


@router.put("/types/{slug}/fields-layout")
async def update_fields_layout(
    slug: str,
    layout: List[dict],
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reihenfolge, Breite UND Tab-Zuweisung aller Felder in einem Aufruf speichern."""
    from app.models.masterdata import FieldDefinition as FD
    for item in layout:
        update_data = {
            "sort_order": item["sort_order"],
            "col_span":   item.get("col_span", 12),
        }
        # Tab nur schreiben wenn explizit mitgegeben (auch None/null ist gültig)
        if "tab" in item:
            update_data["tab"] = item["tab"]
        db.query(FD).filter(FD.id == item["field_id"]).update(update_data)
    db.commit()
    return {"message": "Layout gespeichert"}


@router.put("/types/{slug}/tabs")
async def update_tabs(
    slug: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Tab-Liste des Stammdaten-Typs aktualisieren.
    Body: { "tabs": ["Allgemein", "Bankdaten", "Kontakt"] }
    """
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    tabs = body.get("tabs", [])
    if not isinstance(tabs, list):
        raise HTTPException(status_code=400, detail="tabs muss eine Liste sein")

    # Tabs bereinigen: leere Strings entfernen, Duplikate entfernen (Reihenfolge erhalten)
    seen = set()
    clean_tabs = []
    for t in tabs:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            clean_tabs.append(t)

    et.tabs = clean_tabs
    db.commit()
    db.refresh(et)
    return {"tabs": et.tabs}


# ─── Datensätze ───────────────────────────────────────────────────────────────

@router.get("/types/{slug}/records", response_model=EntityRecordListResponse)
async def list_records(
    slug: str,
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    filter_field: Optional[str] = Query(None),
    filter_value: Optional[str] = Query(None),
    archived: str = Query("active", pattern="^(active|only|all)$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Datensätze eines Stammdaten-Typs abrufen (mit Suche & Paginierung).

    archived: 'active' (Standard) = ohne archivierte, 'only' = nur Archiv, 'all' = beides.
    """
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    total, items = masterdata_service.list_records(
        db, et, search, page, page_size, filter_field, filter_value,
        archived=archived,
    )
    return EntityRecordListResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/types/{slug}/records", response_model=EntityRecordResponse)
async def create_record(
    slug: str,
    body: EntityRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Neuen Datensatz anlegen (erfordert Modul Stammdaten).

    Lesen bleibt für alle offen (Auswahlfelder in anderen Modulen) —
    Anlegen nur mit Schreibrecht auf Stammdaten. Vor Migration 0055 genügte
    hier die Modulfreigabe, die auch reines Ansehen einschloss.
    Zeitprojekte hängen am Schreibrecht der Zeiterfassung (s. Prüffunktion).
    """
    _schreibrecht_pruefen(current_user, slug)
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    daten = dict(body.data or {})

    # Artikelnummer vergeben, wenn keine eingetragen wurde. Vergeben wird hier
    # und nicht im Browser: Nur serverseitig lässt sich der Zähler unter einer
    # Sperre hochzählen. Eine im Formular vorgeschlagene Nummer, die zwischen
    # Vorschlag und Speichern von jemand anderem verbraucht wurde, würde sonst
    # zur Doppelvergabe führen.
    if et.slug == artikelstamm.ARTIKEL_SLUG and not str(daten.get("artikelnummer") or "").strip():
        gruppe = artikelstamm.gruppe_nach_nr(db, daten.get("artikelgruppe"))
        if gruppe:
            try:
                daten["artikelnummer"] = artikelstamm.naechste_artikelnummer(
                    db, gruppe, festschreiben=True)
            except ValueError as fehler:
                raise HTTPException(status_code=409, detail=str(fehler))

    try:
        return masterdata_service.create_record(db, et, daten, current_user.id)
    except ValueError as fehler:
        # Verletzte Eindeutigkeit — 409, nicht 400: Der Datensatz ist in Ordnung,
        # er kollidiert nur mit einem bestehenden.
        raise HTTPException(status_code=409, detail=str(fehler))


@router.get("/types/{slug}/records/{record_id}", response_model=EntityRecordResponse)
async def get_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Einen Datensatz abrufen."""
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    return record


@router.put("/types/{slug}/records/{record_id}", response_model=EntityRecordResponse)
async def update_record(
    slug: str,
    record_id: UUID,
    body: EntityRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datensatz bearbeiten (Schreibrecht auf Stammdaten bzw. Zeiterfassung)."""
    _schreibrecht_pruefen(current_user, slug)
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    try:
        return masterdata_service.update_record(db, record, body.data, current_user.id)
    except ValueError as fehler:
        raise HTTPException(status_code=409, detail=str(fehler))


@router.get("/types/{slug}/records/export/csv")
async def export_records_csv(
    slug: str,
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Datensätze als CSV exportieren."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    _, records = masterdata_service.list_records(db, et, search, page=1, page_size=10000)
    fields = sorted(et.fields, key=lambda f: f.sort_order)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([f.name for f in fields])

    # Daten
    for record in records:
        writer.writerow([_csv_wert(record.data.get(f.key), f) for f in fields])

    output.seek(0)
    filename = f"{slug}_export.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/types/{slug}/records/import", response_model=ImportReport)
async def import_records(
    slug: str,
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datensätze importieren — als Probelauf oder zum Schreiben.

    Erfordert das Schreibrecht auf Stammdaten. Derselbe Endpunkt bedient beide
    Durchgänge des Assistenten: ``dry_run=true`` liefert nur den Bericht,
    ``dry_run=false`` schreibt. Dass beide Wege durch dieselbe Prüfung laufen,
    ist der Punkt — ein Bericht, der anders prüft als der Schreibvorgang, wäre
    schlimmer als keiner.

    Neue Felder legt der Assistent vorab über die Feld-Endpunkte an (nur Admin);
    hier kommen nur Zeilen an, deren Schlüssel bereits Felder sind.
    """
    _schreibrecht_pruefen(current_user, slug)
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    try:
        bericht = masterdata_import.durchfuehren(
            db, et, body.rows,
            benutzer_id=current_user.id,
            abgleichsfeld=body.match_field,
            probelauf=body.dry_run,
            fehlerhafte_ueberspringen=body.skip_invalid,
        )
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler))

    return ImportReport(
        geprueft=bericht.geprueft,
        anlegen=bericht.anlegen,
        aktualisieren=bericht.aktualisieren,
        angelegt=bericht.angelegt,
        aktualisiert=bericht.aktualisiert,
        uebersprungen=bericht.uebersprungen,
        beanstandungen=[ImportIssue(zeile=b.zeile, feld=b.feld, wert=b.wert,
                                    grund=b.grund)
                        for b in bericht.beanstandungen],
    )


@router.get("/types/{slug}/records/{record_id}/references")
async def get_record_references(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Verweise anderer Module auf diesen Datensatz (für den Lösch-Dialog)."""
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    refs = integrity.count_references(db, record.id)
    return {
        "references": refs,
        "has_references": bool(refs),
        "deletable": not refs,
    }


@router.post("/types/{slug}/records/{record_id}/archive",
             response_model=EntityRecordResponse)
async def archive_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Datensatz archivieren (nur Admin — siehe Kommentar oben).

    Archivierte Datensätze verschwinden aus Listen und Auswahlfeldern,
    bleiben aber für die Historie erhalten (Zeiten, Belege, Projekte
    verweisen weiter darauf) und können wiederhergestellt werden.
    """
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    if record.archived_at:
        raise HTTPException(status_code=400, detail="Datensatz ist bereits archiviert")
    return masterdata_service.archive_record(db, record, current_user.id)


@router.post("/types/{slug}/records/{record_id}/restore",
             response_model=EntityRecordResponse)
async def restore_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Archivierten Datensatz wiederherstellen (nur Admin).

    Wiederherstellen ist die Rücknahme des Archivierens und hängt deshalb am
    selben Recht — wer nicht archivieren darf, soll es auch nicht rückgängig
    machen können.
    """
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    if not record.archived_at:
        raise HTTPException(status_code=400, detail="Datensatz ist nicht archiviert")
    return masterdata_service.restore_record(db, record)


@router.delete("/types/{slug}/records/{record_id}")
async def delete_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Datensatz endgültig löschen (nur Admin, nur ohne Verweise).

    Sobald andere Module auf den Datensatz verweisen (Zeiten, Belege,
    Projekte, Aufgaben, Dateien, …), ist Löschen gesperrt — stattdessen
    archivieren. Kontakte mit Belegen: DSGVO-Löschung (Anonymisierung)
    über die Einstellungen.
    """
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")

    refs = integrity.count_references(db, record.id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": ("Löschen nicht möglich — der Datensatz wird noch "
                            f"verwendet: {integrity.references_summary(refs)}. "
                            "Bitte stattdessen archivieren."),
                "references": refs,
            },
        )

    masterdata_service.delete_record(db, record)
    return {"message": "Datensatz gelöscht"}


# ─── Artikelgruppen ───────────────────────────────────────────────────────────
#
# Eigene Tabelle statt eines weiteren Stammdaten-Typs: An der Gruppe hängen
# Erlös- und Aufwandskonto sowie der Zähler für die Artikelnummer. Begründung
# siehe Modell ``ArticleGroup``.
#
# Lesen darf jeder Angemeldete — die Gruppe erscheint als Auswahlfeld im
# Artikel und im Beleg. Ändern darf nur ein Admin, wie beim Kontenplan: Ein
# verstelltes Erlöskonto wirkt sich auf jede künftige Buchung aus.


def _gruppe_antwort(db: Session, gruppe: ArticleGroup) -> ArticleGroupResponse:
    """Gruppe samt Artikelzahl, Nummernvorschau und Konten je Steuerfall."""
    antwort = ArticleGroupResponse.model_validate(gruppe)
    antwort.artikel_anzahl = _artikel_in_gruppe(db, gruppe.nr)
    try:
        antwort.naechste_artikelnummer = artikelstamm.naechste_artikelnummer(
            db, gruppe, festschreiben=False)
    except ValueError:
        antwort.naechste_artikelnummer = None

    # Immer alle Steuerfälle ausliefern, auch die ungepflegten. Sonst müsste
    # das Formular die fehlenden Zeilen selbst erfinden — und eine fehlende
    # Zeile sähe aus wie „gibt es nicht" statt „noch nicht hinterlegt".
    vorhandene = {k.steuerfall: k for k in gruppe.konten}
    antwort.konten = []
    for kennung, name in steuerfall_service.STEUERFAELLE:
        k = vorhandene.get(kennung)
        antwort.konten.append(ArticleGroupAccountResponse(
            id=k.id if k else uuid_leer(),
            steuerfall=kennung,
            bezeichnung=name,
            konto_nr=k.konto_nr if k else None,
            ust_satz=k.ust_satz if k else None,
            ohne_steuer=bool(k.ohne_steuer) if k else False,
        ))
    return antwort


def uuid_leer() -> UUID:
    """Platzhalter-Kennung für einen noch nicht gespeicherten Steuerfall."""
    return UUID("00000000-0000-0000-0000-000000000000")


def _artikel_in_gruppe(db: Session, gruppen_nr: str) -> int:
    et = masterdata_service.get_entity_type(db, artikelstamm.ARTIKEL_SLUG)
    if not et:
        return 0
    return (db.query(EntityRecord)
            .filter(EntityRecord.entity_type_id == et.id,
                    EntityRecord.data["artikelgruppe"].astext == gruppen_nr)
            .count())


def _konto_pruefen(db: Session, nr: Optional[str], bezeichnung: str) -> Optional[str]:
    """Kontonummer gegen den Kontenplan prüfen.

    Bewusst eine Prüfung statt eines Fremdschlüssels: Ein FK würde beim Löschen
    eines Kontos entweder die Gruppe mitreißen oder die Zuordnung stillschweigend
    leeren. Hier fällt ein Tippfehler beim Speichern auf — und ein später
    gelöschtes Konto lässt die Gruppe unangetastet, was der Buchhaltung eine
    nachvollziehbare Lücke statt einer stillen Änderung hinterlässt.
    """
    if not nr or not str(nr).strip():
        return None
    nr = str(nr).strip()
    vorhanden = (db.query(AccountingAccount)
                 .filter(AccountingAccount.nr == nr)
                 .first())
    if not vorhanden:
        raise HTTPException(
            status_code=400,
            detail=f"{bezeichnung} {nr} steht nicht im Kontenplan.")
    return nr


@router.get("/artikelgruppen", response_model=List[ArticleGroupResponse])
async def list_article_groups(
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Artikelgruppen (Auswahlfeld im Artikel und in der Verwaltung)."""
    q = db.query(ArticleGroup)
    if active_only:
        q = q.filter(ArticleGroup.is_active == True)        # noqa: E712
    gruppen = q.order_by(ArticleGroup.sort_order, ArticleGroup.nr).all()
    return [_gruppe_antwort(db, g) for g in gruppen]


@router.post("/artikelgruppen", response_model=ArticleGroupResponse)
async def create_article_group(
    body: ArticleGroupCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neue Artikelgruppe anlegen (nur Admin)."""
    nr = body.nr.strip()
    if not nr:
        raise HTTPException(status_code=400, detail="Die Gruppe braucht einen Kurzschlüssel.")
    if db.query(ArticleGroup).filter(ArticleGroup.nr == nr).first():
        raise HTTPException(status_code=409,
                            detail=f"Die Artikelgruppe „{nr}“ gibt es bereits.")

    gruppe = ArticleGroup(
        nr=nr,
        name=body.name.strip(),
        beschreibung=body.beschreibung,
        praefix=(body.praefix or nr).strip().upper(),
        stellen=max(1, min(body.stellen, 10)),
        naechste_nummer=max(1, body.naechste_nummer),
        erloes_konto_nr=_konto_pruefen(db, body.erloes_konto_nr, "Erlöskonto"),
        aufwand_konto_nr=_konto_pruefen(db, body.aufwand_konto_nr, "Aufwandskonto"),
        ust_satz=body.ust_satz,
        artikelart=body.artikelart,
        einheit=body.einheit,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(gruppe)
    db.commit()
    db.refresh(gruppe)
    return _gruppe_antwort(db, gruppe)


@router.put("/artikelgruppen/{group_id}", response_model=ArticleGroupResponse)
async def update_article_group(
    group_id: UUID,
    body: ArticleGroupUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Artikelgruppe ändern (nur Admin).

    Der Kurzschlüssel bleibt gesperrt, sobald Artikel an der Gruppe hängen: Die
    Artikel speichern ihn als Wert, ein Umbenennen würde sie alle von ihrer
    Gruppe abschneiden — ohne dass das irgendwo auffällt.
    """
    gruppe = db.query(ArticleGroup).filter(ArticleGroup.id == group_id).first()
    if not gruppe:
        raise HTTPException(status_code=404, detail="Artikelgruppe nicht gefunden")

    daten = body.model_dump(exclude_unset=True)

    if "nr" in daten and daten["nr"] and daten["nr"].strip() != gruppe.nr:
        anzahl = _artikel_in_gruppe(db, gruppe.nr)
        if anzahl:
            raise HTTPException(
                status_code=409,
                detail=(f"Der Kurzschlüssel lässt sich nicht ändern — {anzahl} "
                        "Artikel verweisen darauf. Lege stattdessen eine neue "
                        "Gruppe an und ordne die Artikel um."))
        if db.query(ArticleGroup).filter(ArticleGroup.nr == daten["nr"].strip()).first():
            raise HTTPException(status_code=409,
                                detail=f"Die Artikelgruppe „{daten['nr']}“ gibt es bereits.")

    if "erloes_konto_nr" in daten:
        daten["erloes_konto_nr"] = _konto_pruefen(db, daten["erloes_konto_nr"], "Erlöskonto")
    if "aufwand_konto_nr" in daten:
        daten["aufwand_konto_nr"] = _konto_pruefen(db, daten["aufwand_konto_nr"], "Aufwandskonto")
    if "stellen" in daten and daten["stellen"] is not None:
        daten["stellen"] = max(1, min(daten["stellen"], 10))
    if "naechste_nummer" in daten and daten["naechste_nummer"] is not None:
        daten["naechste_nummer"] = max(1, daten["naechste_nummer"])

    for feld, wert in daten.items():
        setattr(gruppe, feld, wert.strip() if feld == "nr" and wert else wert)

    db.commit()
    db.refresh(gruppe)
    return _gruppe_antwort(db, gruppe)


@router.put("/artikelgruppen/{group_id}/konten", response_model=ArticleGroupResponse)
async def set_article_group_accounts(
    group_id: UUID,
    body: List[ArticleGroupAccountBase],
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Konten je Steuerfall einer Artikelgruppe setzen (nur Admin).

    Ersetzt die Zeilen vollständig — das Formular schickt immer alle vier
    Steuerfälle. Eine teilweise Aktualisierung wäre hier gefährlicher als
    bequem: Fehlte eine Zeile im Aufruf, bliebe unklar, ob sie unverändert
    bleiben oder gelöscht werden soll, und im Zweifel bucht eine
    stehengebliebene Zeile weiter auf ein Konto, das niemand mehr wollte.

    Eine Zeile ohne Konto, ohne Satz und ohne „kein Satz"-Kennzeichen wird
    nicht gespeichert: Sie sagt nichts aus, und die Kaskade würde sie
    ohnehin überspringen.
    """
    gruppe = db.query(ArticleGroup).filter(ArticleGroup.id == group_id).first()
    if not gruppe:
        raise HTTPException(status_code=404, detail="Artikelgruppe nicht gefunden")

    gesehen = set()
    for zeile in body:
        if not steuerfall_service.ist_gueltig(zeile.steuerfall):
            raise HTTPException(
                status_code=400,
                detail=(f"Unbekannter Steuerfall „{zeile.steuerfall}“. "
                        f"Erlaubt: {steuerfall_service.KENNUNGEN}"))
        if zeile.steuerfall in gesehen:
            raise HTTPException(
                status_code=400,
                detail=f"Steuerfall „{zeile.steuerfall}“ kommt doppelt vor.")
        gesehen.add(zeile.steuerfall)
        _konto_pruefen(db, zeile.konto_nr, "Erlöskonto")
        if zeile.ohne_steuer and zeile.ust_satz is not None:
            raise HTTPException(
                status_code=400,
                detail=("„Kein Steuersatz“ und ein Steuersatz schließen "
                        "einander aus — Reverse Charge hat keinen Satz, auch "
                        "nicht null."))

    db.query(ArticleGroupAccount).filter(
        ArticleGroupAccount.article_group_id == gruppe.id).delete()

    for zeile in body:
        leer = (not zeile.konto_nr and zeile.ust_satz is None
                and not zeile.ohne_steuer)
        if leer:
            continue
        db.add(ArticleGroupAccount(
            article_group_id=gruppe.id,
            steuerfall=zeile.steuerfall,
            konto_nr=(zeile.konto_nr or None),
            ust_satz=zeile.ust_satz,
            ohne_steuer=zeile.ohne_steuer,
        ))

    db.commit()
    db.refresh(gruppe)
    return _gruppe_antwort(db, gruppe)


@router.get("/steuerfaelle", response_model=List[SteuerfallInfo])
async def list_steuerfaelle(_: User = Depends(get_current_user)):
    """Die möglichen Steuerfälle — feste Liste, siehe services/steuerfall.py."""
    return [SteuerfallInfo(kennung=k, bezeichnung=n)
            for k, n in steuerfall_service.STEUERFAELLE]


@router.delete("/artikelgruppen/{group_id}")
async def delete_article_group(
    group_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Artikelgruppe löschen (nur Admin, nur solange kein Artikel daran hängt).

    Gleiche Regel wie bei den Stammdatensätzen: Was noch verwendet wird, wird
    nicht gelöscht, sondern stillgelegt (``is_active = false``). Sonst stünde
    in den Artikeln eine Gruppennummer, zu der es nichts mehr gibt — und die
    Kontenkaskade fiele wortlos auf das Standardkonto zurück.
    """
    gruppe = db.query(ArticleGroup).filter(ArticleGroup.id == group_id).first()
    if not gruppe:
        raise HTTPException(status_code=404, detail="Artikelgruppe nicht gefunden")

    anzahl = _artikel_in_gruppe(db, gruppe.nr)
    if anzahl:
        raise HTTPException(
            status_code=409,
            detail=(f"Löschen nicht möglich — {anzahl} Artikel gehören zur "
                    f"Gruppe „{gruppe.name}“. Setze sie stattdessen auf inaktiv."))

    db.delete(gruppe)
    db.commit()
    return {"message": f"Artikelgruppe „{gruppe.name}“ wurde gelöscht"}


# ─── Artikel: Nummernvorschlag und Vorgabewerte ───────────────────────────────

@router.get("/artikel/naechste-nummer")
async def naechste_artikelnummer(
    gruppe: str = Query(..., description="Kurzschlüssel der Artikelgruppe"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Vorschlag für die nächste Artikelnummer — ohne den Zähler zu verbrauchen.

    Der Zähler steigt erst beim Anlegen. Ein geöffnetes und wieder verworfenes
    Formular soll keine Lücke in der Nummernfolge hinterlassen; anders als bei
    Rechnungsnummern ist eine Lücke hier zwar nicht verboten, aber sie stiftet
    Verwirrung im Sortiment.
    """
    g = artikelstamm.gruppe_nach_nr(db, gruppe)
    if not g:
        raise HTTPException(status_code=404, detail=f"Artikelgruppe „{gruppe}“ nicht gefunden")
    try:
        return {"artikelnummer": artikelstamm.naechste_artikelnummer(db, g, festschreiben=False),
                "gruppe": g.nr, "praefix": g.praefix}
    except ValueError as fehler:
        raise HTTPException(status_code=409, detail=str(fehler))


@router.get("/artikel/{record_id}/vorgaben", response_model=ArtikelVorgaben)
async def artikel_vorgaben(
    record_id: UUID,
    contact_id: Optional[UUID] = Query(
        None, description="Kunde des Belegs — bestimmt den Steuerfall"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aufgelöste Vorgabewerte eines Artikels für die Belegposition.

    Konto, USt-Satz und Einheit nach der Kaskade Artikel →
    Artikelgruppe×Steuerfall → Artikelgruppe → Standard. Der Steuerfall kommt
    vom Kunden; ohne ``contact_id`` gilt das Inland.

    Der Beleg fragt hier nach, statt die Kaskade selbst nachzubauen — sonst
    gäbe es zwei Auslegungen davon, welches Konto gilt.
    """
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Artikel nicht gefunden")
    return ArtikelVorgaben(**artikelstamm.vorgaben_fuer_artikel(
        db, record.data, contact_id=contact_id))


# ─── Bilder an Stammdatensätzen ───────────────────────────────────────────────

@router.post("/bild")
async def upload_masterdata_image(
    size: str = Query("mittel", description="klein | mittel | gross"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bild für ein Feld vom Typ ``image`` hochladen.

    Bewusst nicht an einen Datensatz gebunden, sondern wie beim Positionsbild
    an einen Schlüssel: Beim Neuanlegen gibt es den Datensatz noch nicht, wenn
    das Bild gewählt wird. Zurück kommt der Speicher-Schlüssel, den das
    Formular als Feldwert mitführt.

    Das Bild wird beim Hochladen verkleinert — dieselbe Mechanik wie bei den
    Belegpositionen, damit ein 12-MB-Handyfoto nicht unverändert im Speicher
    landet.
    """
    _schreibrecht_pruefen(current_user)
    from app.services import position_image, storage_service

    if file.content_type and file.content_type not in position_image.ERLAUBTE_TYPEN:
        raise HTTPException(400, f"Dateityp {file.content_type} wird nicht unterstützt. "
                                 f"Erlaubt sind JPEG, PNG, WebP und GIF.")
    rohdaten = await file.read()
    if len(rohdaten) > position_image.MAX_UPLOAD:
        raise HTTPException(400, "Bild zu groß (max. 15 MB)")

    daten, mime, endung = position_image.verkleinern(rohdaten, size)
    import uuid as _uuid
    schluessel = f"{BILD_PRAEFIX}{_uuid.uuid4().hex}.{endung}"
    # Speicher festhalten: Nach einem Wechsel auf OneDrive liegen ältere Bilder
    # weiter in MinIO — ohne diese Angabe wird am falschen Ort gesucht
    # (dieselbe Lehre wie bei den Anhängen, Migration 0039).
    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(schluessel, daten, mime, db=db, backend=backend)
    except Exception as exc:
        raise HTTPException(500, f"Speicher-Fehler: {exc}")

    return {"key": schluessel, "provider": backend, "size": size,
            "bytes": len(daten), "name": file.filename}


@router.get("/bild")
async def get_masterdata_image(
    key: str = Query(..., description="Speicher-Schlüssel aus dem Upload"),
    provider: Optional[str] = Query(None, description="Speicher der Datei; leer = aktiver"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Liefert ein Stammdaten-Bild aus — für die Vorschau im Formular."""
    from app.services import storage_service
    # Ohne diese Prüfung wäre der Endpunkt ein Leseweg auf den ganzen
    # Objektspeicher: Wer einen beliebigen Schlüssel raten kann, bekäme jede
    # Datei — Belege und Vertragsanhänge eingeschlossen.
    if not key.startswith(BILD_PRAEFIX):
        raise HTTPException(400, "Ungültiger Bildschlüssel")
    try:
        daten, mime = storage_service.download_file(key, db=db, backend=provider)
    except Exception:
        raise HTTPException(404, "Bild nicht gefunden")
    return Response(content=daten, media_type=mime or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})
