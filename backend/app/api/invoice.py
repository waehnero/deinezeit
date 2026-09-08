"""
Verkauf – Sammelrouter.

Bis Audit K-26 (ARCH-001) lagen alle ~70 Endpunkte des Verkaufsmoduls in dieser
einen Datei (3.700 Zeilen). Sie sind jetzt nach Fachgebiet aufgeteilt; diese
Datei bündelt die Teil-Router (jeder trägt das unveränderte Präfix ``/invoices``) und
stellt die Hilfsfunktionen weiter unter ``app.api.invoice`` bereit, damit
Dienste (Mahnwesen, Serienrechnungen, Periodenabschluss, Archiv) und Tests
nicht umziehen müssen.

Reihenfolge der Teil-Router ist bewusst gewählt: feste Pfade wie ``/uva``,
``/open-items`` oder ``/dunning/…`` müssen VOR der Detailroute
``/{invoice_id}`` registriert sein, sonst schluckt der Platzhalter den Pfad.
Deshalb kommt ``invoice_belege`` (mit ``GET /{invoice_id}``) zuletzt.
"""
from fastapi import APIRouter

from app.api import (
    invoice_einstellungen,
    invoice_buchhaltung,
    invoice_zahlungen,
    invoice_mahnwesen,
    invoice_erechnung,
    invoice_versand,
    invoice_anhaenge,
    invoice_status,
    invoice_belege,
)

# Weiter von außen genutzte Bausteine (Dienste, Tests) — bleiben hier erreichbar.
from app.api.invoice_common import (  # noqa: F401
    TYPE_PREFIX, UID_SCHWELLE, ZAHLUNG_UNBERUEHRT, GESPERRTE_FELDER,
    DOC_TYPE_LABELS_DE,
    nummernformat_pruefen, _nummernformat, _next_number, _calc_totals,
    _ensure_number, _audit, _audit_changes, _zahlstand, _recalc_payment_status,
    _ist_ueberfaellig, _pruefe_periode, _pruefe_pflichtangaben, _uid_fehlt,
    _finalize, _pruefe_stufe, _pruefe_belegsperre, _load_pdf_context,
)
from app.api.invoice_buchhaltung import (  # noqa: F401
    get_book_list, get_book_csv, get_book_pdf, get_uva, get_uva_pdf, get_open_items,
)
from app.api.invoice_versand import _send_invoice_email  # noqa: F401
from app.models.invoice import InvoiceNumberSequence  # noqa: F401

router = APIRouter(tags=["Rechnungen"])   # Präfix /invoices tragen die Teil-Router
for _teil in (
    invoice_einstellungen,
    invoice_buchhaltung,
    invoice_zahlungen,
    invoice_mahnwesen,
    invoice_erechnung,
    invoice_versand,
    invoice_anhaenge,
    invoice_status,
    invoice_belege,
):
    router.include_router(_teil.router)
