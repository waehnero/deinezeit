"""
Automatische PDF-Archivierung von Verkaufsbelegen ins Datacenter.

Bei bestimmten Ereignissen (E-Mail-Versand, Statuswechsel …) wird vom Beleg ein
PDF erzeugt und im Datacenter unter dem **Kontakt** in einem **Unterordner je
Belegart** abgelegt. Der Dateiname enthält Datum + Uhrzeit, damit eine
lückenlose Historie entsteht.

Welche Ereignisse archiviert werden, ist in den Verkaufseinstellungen
parametrierbar (InvoiceSettings-Key ``archive_triggers`` = Liste von Auslösern).
Mögliche Auslöser: email | gesendet | angenommen | abgelehnt | bezahlt | storniert
"""
from datetime import datetime


# Belegart → Unterordner-Name im Datacenter (unter dem Kontakt)
DOC_TYPE_FOLDER = {
    "rechnung":             "Rechnungen",
    "angebot":              "Angebote",
    "auftragsbestaetigung": "Auftragsbestätigungen",
    "gutschrift":           "Gutschriften",
    "lieferschein":         "Lieferscheine",
}

# Auslöser, falls in den Einstellungen (noch) nichts hinterlegt ist
DEFAULT_TRIGGERS = ["email"]

# Menschlich lesbare Labels der Auslöser (für die Einstellungen-UI referenziert)
TRIGGER_LABELS = {
    "email":      "Bei E-Mail-Versand",
    "gesendet":   "Status „Gesendet“",
    "angenommen": "Status „Angenommen“",
    "abgelehnt":  "Status „Abgelehnt“",
    "bezahlt":    "Status „Bezahlt“",
    "storniert":  "Status „Storniert“",
}


def get_archive_triggers(db) -> list:
    """Liest die aktivierten Auslöser aus den Verkaufseinstellungen."""
    from app.models.invoice import InvoiceSettings
    row = db.query(InvoiceSettings).filter_by(key="archive_triggers").first()
    if row is not None and isinstance(row.value, list):
        return row.value
    return DEFAULT_TRIGGERS


def archive_invoice_pdf(db, invoice, trigger: str) -> bool:
    """
    Erzeugt bei aktiviertem Auslöser ein PDF des Belegs und legt es im Datacenter
    unter dem Kontakt + Belegart-Unterordner ab.

    Fehler beim Archivieren dürfen den auslösenden Vorgang (z.B. Statuswechsel)
    NICHT scheitern lassen – daher wird alles defensiv behandelt und im Zweifel
    ``False`` zurückgegeben. Das Attachment wird via ``db.flush()`` in die laufende
    Transaktion des Aufrufers eingefügt (der Aufrufer committet).
    """
    if not invoice or not getattr(invoice, "contact_id", None):
        return False
    if trigger not in get_archive_triggers(db):
        return False

    from app.models.masterdata import EntityRecord
    from app.models.attachment import Attachment
    from app.services import storage_service
    from app.services.invoice_pdf import generate_pdf
    from app.api.invoice import _load_pdf_context

    try:
        settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, invoice)
        pdf_bytes = generate_pdf(invoice, invoice.positions, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact)
    except Exception as e:
        print(f"[WARN] Archiv-PDF konnte nicht erzeugt werden ({getattr(invoice, 'number', '?')}): {e}")
        return False

    folder = DOC_TYPE_FOLDER.get(invoice.doc_type, "Belege")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_num = (invoice.number or "beleg").replace("/", "-")
    filename = f"{safe_num}_{ts}.pdf"

    # Storage-Key mit Ordnerpfad selbst bauen (build_storage_key würde den
    # Schrägstrich entfernen). Pfadsegmente ASCII-sicher machen.
    def _safe(s: str) -> str:
        return "".join(c for c in s if c.isalnum() or c in "._- ").strip() or "Belege"
    _folder = storage_service.folder_name_for(db, invoice.contact_id)
    storage_key = f"kontakte/{_folder}/{_safe(folder)}/{_safe(filename)}"

    backend = storage_service.current_backend(db)
    try:
        storage_service.upload_file(storage_key, pdf_bytes, "application/pdf", db=db, backend=backend)
    except Exception as e:
        print(f"[WARN] Archiv-Upload fehlgeschlagen ({invoice.number}): {e}")
        return False

    rec = db.query(EntityRecord).filter(EntityRecord.id == invoice.contact_id).first()
    contact_name = rec.display_name if rec else None

    att = Attachment(
        entity_type="kontakte", entity_id=invoice.contact_id,
        type="file", storage_key=storage_key, storage_provider=backend,
        filename=filename, filesize=len(pdf_bytes), mimetype="application/pdf",
        display_name=f"{invoice.number} · {ts}",
        contact_id=invoice.contact_id, contact_name=contact_name,
        folder=folder,
    )
    db.add(att)
    db.flush()
    return True
