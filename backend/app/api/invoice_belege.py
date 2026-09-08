"""
Verkauf – Belege: Liste, Anlegen, Nummernkreise, Detail, Änderungsprotokoll,
PDF/Vorschau, Ändern, Löschen, unverrechnete Zeiteinträge.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from uuid import UUID
from datetime import date
import logging

from app.db.base import get_db
from app.api.deps import (get_current_user, require_admin)
from app.models.user import User
from app.models.invoice import (Invoice, InvoicePosition, InvoiceNumberSequence, InvoiceSettings,
                                 InvoiceAuditLog)
from app.models.masterdata import EntityRecord
from app.services.invoice_pdf import generate_pdf, generate_html_preview
from app.services.invoice_snapshot import ensure_recipient_snapshot
from app.services import period_service
from app.services import positionen as positionen_service
from app.services import angebot as angebot_service
from app.services import anzahlung as anzahlung_service
from app.services.erechnung import beleg as erechnung_service
from app.schemas.invoice import (
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceListItem,
    NextNumberResponse,
    InvoiceAuditEntry,
)
from app.core import zeit
from app.core.http import content_disposition

from app.api.invoice_common import (
    TYPE_PREFIX,
    _audit,
    _calc_totals,
    _load_pdf_context,
    _nummernformat,
    _pruefe_belegsperre,
    _pruefe_periode,
    _pruefe_stufe,
    _verwaiste_bilder_entfernen,
    nummernformat_pruefen,
)

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[InvoiceListItem])
def list_invoices(
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Wiederkehrende Vorlagen laufen bewusst in der Hauptliste mit (violett
    # markiert); der eigene Tab "Wiederkehrend" zeigt sie zusätzlich gefiltert.
    q = db.query(Invoice)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    if status:
        q = q.filter(Invoice.status == status)
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if search:
        like = f"%{search}%"
        # Kontakt- und Projekt-Datensätze (beide EntityRecord) mit passendem Namen
        entity_subq = db.query(EntityRecord.id).filter(EntityRecord.display_name.ilike(like))
        # Belege mit passendem Positions-/Artikeltext
        pos_subq = db.query(InvoicePosition.invoice_id).filter(or_(
            InvoicePosition.description.ilike(like),
            InvoicePosition.detail.ilike(like),
        ))
        q = q.filter(or_(
            Invoice.number.ilike(like),
            Invoice.title.ilike(like),
            Invoice.reference.ilike(like),
            Invoice.contact_id.in_(entity_subq),   # Suche nach Kontakt
            Invoice.project_id.in_(entity_subq),    # Suche nach Projekt
            Invoice.id.in_(pos_subq),               # Suche nach Artikel/Positionstext
        ))
    invoices = q.order_by(Invoice.date.desc(), Invoice.number.desc()).offset(skip).limit(limit).all()

    # Batch-Lookup Kontaktnamen
    contact_ids = list({inv.contact_id for inv in invoices if inv.contact_id})
    contact_map: dict = {}
    if contact_ids:
        recs = db.query(EntityRecord).filter(EntityRecord.id.in_(contact_ids)).all()
        for r in recs:
            contact_map[r.id] = r.display_name or ""

    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "doc_type": inv.doc_type,
            "number": inv.number,
            "date": inv.date,
            "due_date": inv.due_date,
            "contact_id": inv.contact_id,
            "contact_name": contact_map.get(inv.contact_id) if inv.contact_id else None,
            "title": inv.title,
            "total": inv.total,
            "currency": inv.currency,
            "status": inv.status,
            "created_at": inv.created_at,
            "is_recurring_template": inv.is_recurring_template,
            "recurring_source_id": inv.recurring_source_id,
            "valid_until": inv.valid_until,
            # Abgeleitet, nicht gespeichert — siehe services/angebot.py
            "expired": angebot_service.ist_abgelaufen(inv),
            "billing_stage": inv.billing_stage,
            "chain_id": inv.chain_id,
        })
    return result


@router.post("", response_model=InvoiceResponse)
def create_invoice(
    body: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.doc_type not in TYPE_PREFIX:
        raise HTTPException(400, f"Ungültiger doc_type: {body.doc_type}")

    if body.date and period_service.ist_gesperrt(db, body.date):
        period_service.pruefe_periode_offen(db, body.date, "angelegt")

    _pruefe_stufe(body.doc_type, body.billing_stage)

    # Bewusst OHNE Nummer: Der Beleg entsteht als Entwurf, die Nummer fällt
    # erst beim Finalisieren (siehe _ensure_number).
    data = body.model_dump(exclude={"positions"})
    data["created_by"] = current_user.email
    data["updated_by"] = current_user.email
    # Bindefrist vorbelegen, wenn der Anwender keine angegeben hat. Ohne
    # Vorbelegung müsste sie bei jedem Angebot getippt werden — und wird
    # vergessen.
    if not data.get("valid_until"):
        data["valid_until"] = angebot_service.vorbelegen(db, body.doc_type, body.date)

    invoice = Invoice(**data)
    db.add(invoice)
    db.flush()

    # Eine Rechnung mit Abrechnungsstufe, die keinem Strang zugeordnet wurde,
    # eröffnet einen eigenen. Sonst stünde sie allein da und die spätere
    # Schlussrechnung fände sie nicht.
    if invoice.billing_stage and not invoice.chain_id:
        anzahlung_service.strang_anlegen(db, invoice)

    for i, pos_data in enumerate(body.positions):
        pos = InvoicePosition(invoice_id=invoice.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    db.refresh(invoice)
    _calc_totals(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/templates", response_model=List[InvoiceListItem])
def list_recurring_templates(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Invoice).filter(Invoice.is_recurring_template == True)\
             .order_by(Invoice.created_at.desc()).all()


@router.get("/next-number", response_model=NextNumberResponse)
def get_next_number(
    doc_type: str = Query("rechnung"),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    y = year or zeit.jetzt().year
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    next_seq = (seq.last_sequence + 1) if seq else 1
    preview = nummernformat_pruefen(_nummernformat(db, doc_type)).format(year=y, seq=next_seq)
    return {"doc_type": doc_type, "year": y, "next_sequence": next_seq, "preview": preview}

DOC_TYPES_LIST = ["rechnung", "angebot", "auftragsbestaetigung", "gutschrift", "lieferschein"]
DOC_TYPE_DEFAULTS = {
    "rechnung":             "RE-{year}-{seq:03d}",
    "angebot":              "AN-{year}-{seq:03d}",
    "auftragsbestaetigung": "AB-{year}-{seq:03d}",
    "gutschrift":           "GS-{year}-{seq:03d}",
    "lieferschein":         "LS-{year}-{seq:03d}",
}


@router.get("/number-sequences")
def get_number_sequences(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt Nummernkreise (Format + aktueller Zähler) für alle Dokumenttypen zurück."""
    y = year or zeit.jetzt().year
    result = []
    for doc_type in DOC_TYPES_LIST:
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
        fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
              or DOC_TYPE_DEFAULTS[doc_type]
        last = seq.last_sequence if seq else 0
        # Vorschau nächste Nummer
        preview = fmt.format(year=y, seq=last + 1)
        result.append({
            "doc_type": doc_type,
            "year": y,
            "format": fmt,
            "last_sequence": last,
            "next_sequence": last + 1,
            "next_preview": preview,
        })
    return result


@router.put("/number-sequences/{doc_type}")
def update_number_sequence(
    doc_type: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Aktualisiert Format und/oder Zählerstand für einen Dokumenttyp.
    Body: { year, format, last_sequence }
    """
    if doc_type not in DOC_TYPES_LIST:
        raise HTTPException(400, f"Ungültiger Dokumenttyp: {doc_type}")

    y = body.get("year", zeit.jetzt().year)

    # Format speichern — vorher prüfen, damit kein Format gespeichert wird,
    # an dem später jede Belegerstellung scheitert.
    if "format" in body:
        nummernformat_pruefen(str(body["format"]))
        fmt_key = f"number_format_{doc_type}"
        setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
        if setting:
            setting.value = body["format"]
        else:
            setting = InvoiceSettings(key=fmt_key, value=body["format"])
            db.add(setting)

    # Zählerstand setzen — nur aufwärts.
    # Ein Zurücksetzen würde eine bereits vergebene Nummer ein zweites Mal
    # erzeugen; der UNIQUE-Index auf invoices.number bricht dann mit einem
    # unverständlichen Serverfehler ab.
    if "last_sequence" in body:
        new_seq = int(body["last_sequence"])
        if new_seq < 0:
            raise HTTPException(400, "Zählerstand darf nicht negativ sein")
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        if seq:
            if new_seq < seq.last_sequence:
                raise HTTPException(
                    400,
                    f"Der Zählerstand kann nur erhöht werden (aktuell "
                    f"{seq.last_sequence}). Ein Zurücksetzen würde eine bereits "
                    f"vergebene Belegnummer erneut erzeugen.",
                )
            seq.last_sequence = new_seq
        else:
            seq = InvoiceNumberSequence(doc_type=doc_type, year=y, last_sequence=new_seq)
            db.add(seq)

    db.commit()

    # Aktuellen Stand zurückgeben
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
    fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
          or DOC_TYPE_DEFAULTS[doc_type]
    last = seq.last_sequence if seq else 0
    return {
        "doc_type": doc_type,
        "year": y,
        "format": fmt,
        "last_sequence": last,
        "next_sequence": last + 1,
        "next_preview": fmt.format(year=y, seq=last + 1),
    }


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return inv


@router.get("/{invoice_id}/audit", response_model=List[InvoiceAuditEntry])
def get_invoice_audit(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Änderungsprotokoll eines Belegs, neueste Änderung zuerst.

    Protokolliert wird ab dem Finalisieren — am Entwurf wird laufend
    gearbeitet, das wäre nur Rauschen.
    """
    if not db.query(Invoice.id).filter(Invoice.id == invoice_id).first():
        raise HTTPException(404, "Beleg nicht gefunden")
    return (db.query(InvoiceAuditLog)
            .filter(InvoiceAuditLog.invoice_id == invoice_id)
            .order_by(InvoiceAuditLog.changed_at.desc())
            .all())


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Beleg als PDF herunterladen (Vorlage + Fußzeile wie in den Einstellungen)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)
    xml = erechnung_service.xml_fuer_pdf(db, inv, inv_settings_d,
                                          sender_contact, recipient_contact)
    try:
        pdf_bytes = generate_pdf(inv, inv.positions, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, db=db,
                                 erechnung_xml=xml)
    except Exception as e:
        logger.exception("Fehler bei invoice: %s", e)
        raise HTTPException(500, "Das PDF konnte nicht erzeugt werden (Ursache im Serverlog).")

    filename = f"{(inv.number or 'beleg').replace('/', '-')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition("attachment", filename)},
    )


@router.get("/{invoice_id}/preview")
def preview_invoice_html(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """HTML-Vorschau eines Belegs (für das Vorschau-Popup im Beleg-Formular)."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)
    html = generate_html_preview(inv, inv.positions, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, db=db)
    return Response(content=html, media_type="text/html")


@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Belege können nicht bearbeitet werden")
    # Beide Daten prüfen: aus einem abgeschlossenen Monat heraus- und in
    # einen hineinzubuchen ist gleichermaßen gesperrt.
    _pruefe_periode(db, inv)
    period_service.pruefe_periode_offen(db, body.date, "angelegt")

    # ── Finalisierter Beleg: nur noch Nicht-Gedrucktes änderbar ──────────────
    if inv.status != "entwurf":
        erlaubte_aenderungen = _pruefe_belegsperre(inv, body)   # wirft 400 bei Verstoß

        inv.notes = body.notes
        inv.project_id = body.project_id
        inv.updated_by = current_user.email
        # Altbestand ohne Snapshot nachziehen (Empfänger ist gesperrt, ein
        # force-Neuaufbau kommt daher nicht mehr vor)
        ensure_recipient_snapshot(db, inv)

        if erlaubte_aenderungen:
            _audit(db, inv, "bearbeitet", changes=erlaubte_aenderungen,
                   user_email=current_user.email)

        db.commit()
        db.refresh(inv)
        return inv

    # ── Entwurf: frei bearbeitbar ────────────────────────────────────────────
    _pruefe_stufe(inv.doc_type, body.billing_stage)
    update_data = body.model_dump(exclude={"positions"})
    for k, v in update_data.items():
        setattr(inv, k, v)
    inv.updated_by = current_user.email
    # Wer eine Rechnung nachträglich zur Anzahlung erklärt, eröffnet damit
    # einen Strang — sonst fände die spätere Schlussrechnung sie nicht.
    if inv.billing_stage and not inv.chain_id:
        anzahlung_service.strang_anlegen(db, inv)

    # Positionen ersetzen. Vorher merken, welche Bilder daran hingen — beim
    # Speichern werden alle Positionen gelöscht und neu angelegt, und ein Bild,
    # dessen Position verschwindet, bliebe sonst für immer im Speicher liegen.
    alte_bilder = {p.image_key: p.image_provider for p in inv.positions if p.image_key}

    db.query(InvoicePosition).filter(InvoicePosition.invoice_id == invoice_id).delete()
    for i, pos_data in enumerate(body.positions):
        # Der Anzahlungsabzug wird nicht vom Formular übernommen, sondern
        # gleich darunter neu gerechnet: Er hängt an den bereits gestellten
        # Rechnungen, nicht an dem, was im Browser stand. Käme in der
        # Zwischenzeit eine weitere Teilrechnung dazu, wäre der Abzug aus dem
        # Formular veraltet — und niemand würde es merken.
        if (pos_data.pos_type or "item") == positionen_service.ANZAHLUNGSABZUG:
            continue
        pos = InvoicePosition(invoice_id=inv.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    if inv.billing_stage == "schluss" and inv.chain_id:
        # Erst auffrischen: Die Positionen wurden per Massenlöschung ersetzt,
        # die Beziehung am Beleg zeigt sonst noch den alten Stand — und die
        # Abzugszeile bekäme eine Sortierung, die schon vergeben ist.
        db.refresh(inv)
        anzahlung_service.zeilen_anhaengen(
            db, inv,
            anzahlung_service.abzugsfaehige_belege(db, inv.chain_id, ausser_id=inv.id))
        db.flush()

    _verwaiste_bilder_entfernen(db, alte_bilder)
    db.refresh(inv)
    _calc_totals(inv)
    # Zeiteinträge bleiben am Entwurf bewusst unangetastet — sie werden erst
    # beim Finalisieren auf 'abgerechnet' gezogen (_sync_time_entry_status).
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")
    # Nur Entwürfe. Ein stornierter Beleg wurde ausgestellt und unterliegt der
    # Aufbewahrungspflicht (§ 132 BAO) — er bleibt erhalten. Entwürfe haben
    # keine Nummer, ihr Löschen reißt daher auch keine Lücke mehr.
    if inv.status != "entwurf":
        raise HTTPException(
            400,
            "Nur Entwürfe können gelöscht werden. Ausgestellte Belege — auch "
            "stornierte — unterliegen der Aufbewahrungspflicht.",
        )
    # Bilder der Positionen mitnehmen, sonst bleiben sie im Speicher zurück.
    bilder = {p.image_key: p.image_provider for p in inv.positions if p.image_key}
    db.delete(inv)
    db.flush()
    _verwaiste_bilder_entfernen(db, bilder)
    db.commit()
# ─────────────────────────────────────────────────────────────────────────────
# Zeiteinträge für Rechnung vorschlagen
# ─────────────────────────────────────────────────────────────────────────────
    return {"ok": True}


@router.get("/time-entries/unbilled")
def get_unbilled_time_entries(
    contact_id: Optional[UUID] = Query(None),
    project_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Gibt die verrechenbaren, noch nicht fakturierten Zeiteinträge zurück.

    Ein Eintrag erscheint hier, wenn er
      * abgeschlossen ist (``ended_at`` gesetzt — laufende Timer zählen nicht),
      * als verrechenbar markiert ist (``billable``),
      * den Status ``freigegeben`` hat (erst nach der Freigabe darf fakturiert
        werden — siehe Abrechnungs-Workflow in ``models/zeiterfassung.py``) und
      * auf keinem gültigen Beleg liegt.

    Positionen **stornierter** Belege zählen dabei nicht: Wird eine Rechnung
    storniert, sollen die darauf abgerechneten Stunden wieder fakturierbar sein.
    """
    from app.models.zeiterfassung import TimeEntry

    # Zeiteinträge, die bereits auf einem gültigen (nicht stornierten) Beleg liegen
    billed_subq = (
        db.query(InvoicePosition.time_entry_id)
        .join(Invoice, Invoice.id == InvoicePosition.invoice_id)
        .filter(InvoicePosition.time_entry_id.isnot(None),
                Invoice.status != "storniert")
    )

    q = db.query(TimeEntry).filter(
        TimeEntry.ended_at.isnot(None),
        TimeEntry.billable.is_(True),
        TimeEntry.status == "freigegeben",
        TimeEntry.id.notin_(billed_subq),
    )

    # Kontakt-/Projektfilter mit Namens-Rückfall:
    # Nicht jeder Zeiteintrag trägt eine contact_id/project_id — Einträge aus
    # „KI nachtragen" und älterer Erfassung haben nur den Namen. Ohne diesen
    # Rückfall verschwinden sie aus dem Übernahme-Dialog, sobald am Beleg ein
    # Kontakt gewählt ist. Verglichen wird der Anzeigename exakt (aber ohne
    # Rücksicht auf Groß-/Kleinschreibung), damit „Muster GmbH“ nicht auch
    # „Mustermann GmbH“ einsammelt.
    def _mit_namensrueckfall(query, ziel_id, id_spalte, name_spalte):
        rec = db.query(EntityRecord).filter(EntityRecord.id == ziel_id).first()
        name = (rec.display_name or "").strip() if rec else ""
        bedingungen = [id_spalte == ziel_id]
        if name:
            bedingungen.append(and_(id_spalte.is_(None), name_spalte.ilike(name)))
        return query.filter(or_(*bedingungen))

    if contact_id:
        q = _mit_namensrueckfall(q, contact_id, TimeEntry.contact_id, TimeEntry.contact_name)
    if project_id:
        q = _mit_namensrueckfall(q, project_id, TimeEntry.project_id, TimeEntry.project_name)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            TimeEntry.note.ilike(like),
            TimeEntry.contact_name.ilike(like),
            TimeEntry.project_name.ilike(like),
            TimeEntry.task_title.ilike(like),
        ))

    entries = q.order_by(TimeEntry.started_at.desc()).limit(limit).all()

    result = []
    for e in entries:
        minuten = e.duration_minutes or 0
        result.append({
            "id":               str(e.id),
            "started_at":       e.started_at.isoformat() if e.started_at else None,
            "ended_at":         e.ended_at.isoformat() if e.ended_at else None,
            "duration_minutes": minuten,
            "duration_hours":   round(minuten / 60, 2),
            "description":      e.note or e.task_title or "Zeitaufwand",
            "note":             e.note or "",
            # Das Frontend liest `contact`/`project`; die *_name-Schlüssel
            # bleiben für ältere Aufrufer zusätzlich erhalten.
            "contact":          e.contact_name or "",
            "project":          e.project_name or "",
            "contact_name":     e.contact_name or "",
            "project_name":     e.project_name or "",
            "contact_id":       str(e.contact_id) if e.contact_id else None,
            "project_id":       str(e.project_id) if e.project_id else None,
            "billable":         e.billable,
        })
    return result
