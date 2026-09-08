"""
Verkauf – Belegeinstellungen, Vorlagen-Vorschau, Positionsbilder, E-Mail-Vorlagen.

Herausgelöst aus app/api/invoice.py (Audit K-26, ARCH-001) — reine Verschiebung,
die Pfade bleiben unverändert; app/api/invoice.py bündelt die Teil-Router.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
import logging

from app.db.base import get_db
from app.api.deps import (get_current_user, require_admin)
from app.models.user import User
from app.models.invoice import InvoiceSettings
from app.models.settings import Setting
from app.models.email_template import EmailTemplate
from app.models.masterdata import EntityRecord
from app.services.invoice_pdf import generate_html_preview
from app.services import dunning as dunning_service
from app.services import angebot as angebot_service
from app.services.erechnung import beleg as erechnung_service
from app.schemas.invoice import (
    InvoiceSettingsUpdate,
)
from app.core import zeit

logger = logging.getLogger(__name__)

# Präfix hier statt im Sammelrouter: FastAPI erlaubt keine Route mit leerem Pfad
# in einem Router ohne Präfix (betrifft GET/POST "" = Belegliste/Anlegen).
router = APIRouter(prefix="/invoices")

# ─────────────────────────────────────────────────────────────────────────────
# Belegeinstellungen (Key-Value-Store: Bankdaten, Vorlagen, Texte, Steuersätze)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings/all")
def get_invoice_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt alle Belegeinstellungen als Dict {key: value} zurück."""
    werte = {r.key: r.value for r in db.query(InvoiceSettings).all()}
    # Die WIRKSAMEN Archiv-Auslöser mitliefern, auch wenn nichts gespeichert
    # ist. Sonst müsste die Oberfläche einen eigenen Vorgabewert vorhalten —
    # und würde ihn beim nächsten Speichern über den echten schreiben.
    from app.services.invoice_archive import get_archive_triggers
    from app.services import tax_rates as tax_rates_service
    werte.setdefault("archive_triggers", get_archive_triggers(db))
    # Dasselbe für die Steuersätze: Die Oberfläche soll die wirksamen Sätze
    # anzeigen, ohne eine eigene Kopie der Vorgabewerte vorzuhalten.
    werte["tax_rates"] = tax_rates_service.as_json(tax_rates_service.get_tax_rates(db))
    # Ebenso die Mahnstufen und die Zinsparameter: Die Oberfläche soll die
    # wirksamen Werte zeigen, nicht eine zweite Kopie der Vorgaben pflegen.
    werte["dunning_levels"] = dunning_service.get_levels(db)
    zins = dunning_service.get_zins_einstellungen(db)
    werte.setdefault("dunning_base_rate",
                     None if zins["basiszinssatz"] is None else float(zins["basiszinssatz"]))
    werte.setdefault("dunning_surcharge_b2b", float(zins["aufschlag_b2b"]))
    werte.setdefault("dunning_rate_b2c", float(zins["zins_b2c"]))
    werte.setdefault("dunning_interest_mode", zins["modus"])
    werte.setdefault("default_offer_valid_days", angebot_service.vorgabe_tage(db))
    # E-Rechnung ist standardmäßig AUS. Sie ändert das Dateiformat jedes
    # versendeten Belegs — das gehört eingeschaltet, nicht stillschweigend
    # übernommen.
    werte.setdefault("erechnung_aktiv", erechnung_service.ist_aktiv(db))
    return werte


@router.put("/settings/{key}")
def update_invoice_setting(
    key: str,
    body: InvoiceSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Speichert eine einzelne Belegeinstellung (Upsert). Wert ist beliebiges JSON."""
    setting = db.query(InvoiceSettings).filter_by(key=key).first()
    if setting:
        setting.value = body.value
    else:
        setting = InvoiceSettings(key=key, value=body.value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": setting.value}


@router.get("/template-preview/{template_id}")
def template_preview(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """HTML-Vorschau einer PDF-Vorlage mit Beispieldaten (Einstellungen → Belegeinstellungen)."""
    from types import SimpleNamespace
    from decimal import Decimal
    from datetime import timedelta

    if template_id not in (1, 2, 3, 4, 5):
        raise HTTPException(404, "Unbekannte Vorlage")

    settings     = {r.key: r.value for r in db.query(Setting).all()}
    inv_settings = {r.key: r.value for r in db.query(InvoiceSettings).all()}

    # Eigener Firmen-Kontakt als Absender (falls verknüpft)
    sender_contact = None
    cid = settings.get("company_contact_id")
    if cid:
        try:
            sender_contact = db.query(EntityRecord).filter(EntityRecord.id == UUID(cid)).first()
        except Exception:
            pass

    # Beispiel-Empfänger und -Positionen, damit die Vorschau realistisch aussieht
    recipient = SimpleNamespace(
        display_name="Musterfirma GmbH",
        data={"ansprechperson": "Max Mustermann", "adresse": "Musterstraße 1",
              "plz": "1010", "ort": "Wien", "land": "Österreich", "uid": "ATU12345678"},
    )
    positions = [
        SimpleNamespace(pos_type="item", description="Beratung & Konzeption",
                        detail="Workshop inkl. Vor- und Nachbereitung",
                        quantity=Decimal("8"), unit="Std.", unit_price=Decimal("120"),
                        discount_pct=None, tax_rate=Decimal("20"), line_total=Decimal("960.00")),
        SimpleNamespace(pos_type="item", description="Entwicklung Webanwendung",
                        detail=None, quantity=Decimal("24"), unit="Std.", unit_price=Decimal("95"),
                        discount_pct=Decimal("10"), tax_rate=Decimal("20"), line_total=Decimal("2052.00")),
        SimpleNamespace(pos_type="item", description="Hosting-Pauschale",
                        detail=None, quantity=Decimal("1"), unit="Pausch.", unit_price=Decimal("49.90"),
                        discount_pct=None, tax_rate=Decimal("20"), line_total=Decimal("49.90")),
    ]
    subtotal  = sum((p.line_total for p in positions), Decimal("0"))
    tax_total = (subtotal * Decimal("0.20")).quantize(Decimal("0.01"))
    today = zeit.heute()
    demo_invoice = SimpleNamespace(
        doc_type="rechnung", status="offen", tax_mode="normal",
        number="RE-2026-042", date=today, due_date=today + timedelta(days=30),
        delivery_date=None, reference="Beispiel-Projekt",
        intro_text="Vielen Dank für Ihren Auftrag! Wir stellen folgende Leistungen in Rechnung:",
        outro_text="Zahlbar innerhalb von 30 Tagen ohne Abzug.",
        subtotal=subtotal, tax_total=tax_total, total=subtotal + tax_total,
    )

    html = generate_html_preview(demo_invoice, positions, settings, inv_settings,
                                 sender_contact, recipient, template_id=template_id)
    return Response(content=html, media_type="text/html")


@router.post("/positions/image")
def upload_position_image(
    size: str = Query("mittel", description="klein | mittel | gross"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Nimmt ein Bild für eine Belegposition entgegen und verkleinert es sofort
    auf die gewählte Druckgröße.

    Bewusst **nicht** an eine Position gebunden: Positionen werden beim
    Speichern gelöscht und neu angelegt, haben also keine dauerhafte Kennung.
    Zurück kommt der Speicher-Schlüssel, den das Formular als Feld der Position
    mitführt — genau wie das Erlöskonto.
    """
    from app.services import position_image, storage_service

    if file.content_type and file.content_type not in position_image.ERLAUBTE_TYPEN:
        raise HTTPException(400, f"Dateityp {file.content_type} wird nicht unterstützt. "
                                 f"Erlaubt sind JPEG, PNG, WebP und GIF.")
    rohdaten = file.file.read()
    if len(rohdaten) > position_image.MAX_UPLOAD:
        raise HTTPException(400, "Bild zu groß (max. 15 MB)")

    daten, mime, endung = position_image.verkleinern(rohdaten, size)
    schluessel = position_image.speicher_schluessel(endung)
    # Den Speicher festhalten, in den wir schreiben. Ohne diese Angabe wird die
    # Datei nach einem Speicherwechsel am falschen Ort gesucht — dieselbe
    # Lehre wie bei den Anhängen (Migration 0039).
    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(schluessel, daten, mime, db=db, backend=backend)
    except Exception as exc:
        logger.exception("Fehler bei invoice: %s", exc)
        raise HTTPException(500, "Die Datei konnte nicht gespeichert werden (Ursache im Serverlog).")

    return {"image_key": schluessel, "image_size": size, "image_provider": backend,
            "breite_mm": position_image.breite_mm(size), "bytes": len(daten)}


@router.get("/positions/image")
def get_position_image(
    key: str = Query(..., description="Speicher-Schlüssel aus dem Upload"),
    provider: Optional[str] = Query(None, description="Speicher der Datei; leer = aktiver"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Liefert ein Positionsbild aus — für die Vorschau im Formular."""
    from app.services import storage_service
    if not key.startswith("belege/positionsbilder/"):
        raise HTTPException(400, "Ungültiger Bildschlüssel")
    try:
        daten, mime = storage_service.download_file(key, db=db, backend=provider)
    except Exception:
        raise HTTPException(404, "Bild nicht gefunden")
    return Response(content=daten, media_type=mime or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/email-templates/{doc_type}")
def get_email_template(
    doc_type: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Lädt die E-Mail-Vorlage für eine Belegart."""
    tmpl = db.query(EmailTemplate).filter(EmailTemplate.doc_type == doc_type).first()
    if not tmpl:
        return {"doc_type": doc_type, "subject": "", "body_html": ""}
    return {"doc_type": tmpl.doc_type, "subject": tmpl.subject, "body_html": tmpl.body_html}


@router.put("/email-templates/{doc_type}")
def update_email_template(
    doc_type: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Speichert die E-Mail-Vorlage für eine Belegart."""
    tmpl = db.query(EmailTemplate).filter(EmailTemplate.doc_type == doc_type).first()
    if not tmpl:
        tmpl = EmailTemplate(doc_type=doc_type)
        db.add(tmpl)
    tmpl.subject   = body.get("subject", "")
    tmpl.body_html = body.get("body_html", "")
    db.commit()
