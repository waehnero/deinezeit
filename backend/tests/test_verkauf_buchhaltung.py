"""
Tests für Buchhaltungs-Export und Zeiteintrags-Verrechnung (Modul Verkauf).

Deckt die in `docs/VERKAUF_ANALYSE.md` beschriebenen Befunde ab:

  A-1  BMD-Export lief in einen AttributeError, weil `account_nr` im Modell fehlte
  A-2  `/invoices/time-entries/unbilled` war abgeschnitten und lieferte `null`
  A-3  Gutschriften wurden doppelt negiert und damit als Umsatz gebucht
  A-4  Gutschriften fehlten im Export (Vorgabewert doc_type="rechnung")
  A-12 Kontaktname im Belegbuch blieb leer (falsche data-Keys statt display_name)

Schema analog zu test_verkauf_erweiterungen.py.
"""
import csv
import io
from datetime import date, datetime, timedelta, timezone

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoicePosition
from app.models.zeiterfassung import TimeEntry


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH", data=None):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data=data or {"email": "info@muster.at", "debitornummer": "20001"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id=None, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Projekt Juli"),
        "date": extra.pop("date", "2026-07-06"),
        # Pflichtangabe seit 0043 — ohne sie schlägt das Finalisieren fehl
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "2", "unit_price": "100", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _finalisieren(client, invoice_id, status="offen"):
    """Beleg aus dem Entwurf holen (Voraussetzung für den Export)."""
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _export_zeilen(client, **params):
    """BMD-Export abrufen und als Liste von Zeilen-Dicts zurückgeben."""
    resp = client.get("/api/accounting/export/bmd", params=params)
    assert resp.status_code == 200, resp.text
    text = resp.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _make_time_entry(db, user, *, note="Programmierung", status="freigegeben",
                     billable=True, stunden=2, contact=None, project_name=None,
                     nur_kontaktname=False):
    """
    Legt einen Zeiteintrag an.

    nur_kontaktname=True bildet den Fall nach, den „KI nachtragen" und ältere
    Erfassung erzeugen: Der Kontaktname steht am Eintrag, die contact_id nicht.
    """
    start = datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc)
    entry = TimeEntry(
        user_id=user.id,
        started_at=start,
        ended_at=start + timedelta(hours=stunden),
        pause_minutes=0,
        note=note,
        billable=billable,
        status=status,
        contact_id=None if nur_kontaktname else (contact.id if contact else None),
        contact_name=contact.display_name if contact else None,
        project_name=project_name,
        data={},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ── A-1 / A-4: Export läuft überhaupt und hat den richtigen Umfang ────────────

def test_bmd_export_laeuft_und_enthaelt_die_rechnung(auth_client, db_session):
    """Regression A-1: griff früher auf das nicht gemappte Feld `account_nr` zu."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    # Die Nummer fällt erst beim Finalisieren — in der Anlage-Antwort steht
    # daher noch None.
    final = _finalisieren(auth_client, inv["id"])

    zeilen = _export_zeilen(auth_client)
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z["Belegnummer"] == final["number"] == "RE-2026-001"
    assert z["Nettobetrag"] == "200,00"
    assert z["USt-Betrag"] == "40,00"
    assert z["Bruttobetrag"] == "240,00"
    assert z["USt-Code"] == "U20"
    assert z["Erlöskonto"] == "4000"       # Standard, da kein Konto gepflegt
    assert z["Debitornummer"] == "20001"
    assert z["Kontakt"] == "Muster GmbH"


def test_bmd_export_nutzt_erloeskonto_der_position(auth_client, db_session):
    """Positionen mit eigenem Erlöskonto werden getrennt gebucht."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Ware", "quantity": "1",
         "unit_price": "100", "tax_rate": "20", "account_nr": "4100"},
        {"pos_type": "item", "description": "Dienstleistung", "quantity": "1",
         "unit_price": "50", "tax_rate": "20", "account_nr": "4200"},
    ])
    _finalisieren(auth_client, inv["id"])

    zeilen = _export_zeilen(auth_client)
    konten = {z["Erlöskonto"]: z["Nettobetrag"] for z in zeilen}
    assert konten == {"4100": "100,00", "4200": "50,00"}


def test_bmd_export_trennt_nach_steuersatz(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id, positions=[
        {"pos_type": "item", "description": "Beratung", "quantity": "1",
         "unit_price": "100", "tax_rate": "20"},
        {"pos_type": "item", "description": "Nächtigung", "quantity": "1",
         "unit_price": "200", "tax_rate": "13"},
    ])
    _finalisieren(auth_client, inv["id"])

    zeilen = _export_zeilen(auth_client)
    codes = {z["USt-Code"]: z["USt-Betrag"] for z in zeilen}
    assert codes == {"U20": "20,00", "U13": "26,00"}


def test_bmd_export_ignoriert_entwuerfe(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    _create_invoice(auth_client, kontakt.id)          # bleibt Entwurf
    assert _export_zeilen(auth_client) == []


def test_bmd_export_lehnt_nicht_buchungsrelevante_belegart_ab(auth_client, db_session):
    """Angebote sind kein Umsatz und dürfen nicht in die Buchhaltung."""
    resp = auth_client.get("/api/accounting/export/bmd", params={"doc_type": "angebot"})
    assert resp.status_code == 400
    assert "buchungsrelevant" in resp.json()["detail"]


def test_bmd_export_enthaelt_angebote_nicht(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    angebot = _create_invoice(auth_client, kontakt.id, doc_type="angebot")
    _finalisieren(auth_client, angebot["id"], status="gesendet")

    assert _export_zeilen(auth_client) == []


# ── A-3: Gutschriften mindern den Umsatz ──────────────────────────────────────

def test_storno_mit_gutschrift_hebt_die_rechnung_auf(auth_client, db_session):
    """
    Regression A-3/A-4: Die Storno-Gutschrift trägt bereits negative Mengen.
    Früher wurde das Vorzeichen zusätzlich gedreht (→ Gutschrift als Umsatz)
    und die Gutschrift fehlte mangels doc_type-Filter ganz im Export.
    """
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "with_credit"})
    assert resp.status_code == 200, resp.text

    zeilen = _export_zeilen(auth_client)
    # Rechnung UND Gutschrift müssen im Export stehen …
    assert len(zeilen) == 2
    betraege = sorted(z["Nettobetrag"] for z in zeilen)
    assert betraege == ["-200,00", "200,00"]
    # … und sich in Summe aufheben
    summe = sum(float(z["Bruttobetrag"].replace(",", ".")) for z in zeilen)
    assert summe == 0.0


def test_storno_ohne_gutschrift_wird_nicht_exportiert(auth_client, db_session):
    """Reiner Status-Storno: es gab keine Buchung, also auch keine Zeile."""
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "status_only"})
    assert resp.status_code == 200, resp.text

    assert _export_zeilen(auth_client) == []


def test_bmd_export_filtert_nach_zeitraum(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    juni = _create_invoice(auth_client, kontakt.id, date="2026-06-15")
    juli = _create_invoice(auth_client, kontakt.id, date="2026-07-15")
    _finalisieren(auth_client, juni["id"])
    juli_final = _finalisieren(auth_client, juli["id"])

    zeilen = _export_zeilen(auth_client, date_from="2026-07-01", date_to="2026-07-31")
    assert [z["Belegnummer"] for z in zeilen] == [juli_final["number"]]


# ── A-12: Kontaktname im Belegbuch ────────────────────────────────────────────

def test_belegbuch_zeigt_den_kontaktnamen(auth_client, db_session):
    """Regression A-12: las früher data['name'] — ein Key, den es nicht gibt."""
    kontakt = _make_kontakt(db_session, display_name="Sonnenschein AG")
    inv = _create_invoice(auth_client, kontakt.id)
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.get("/api/invoices/book/list")
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["summary"]["count"] == 1
    assert daten["invoices"][0]["contact_name"] == "Sonnenschein AG"


# ── A-2: Zeiteinträge übernehmen ──────────────────────────────────────────────

def test_unbilled_liefert_freigegebene_eintraege(auth_client, db_session, test_user):
    """Regression A-2: Der Endpunkt war abgeschnitten und lieferte `null`."""
    kontakt = _make_kontakt(db_session)
    _make_time_entry(db_session, test_user, contact=kontakt, note="Programmierung")

    resp = auth_client.get("/api/invoices/time-entries/unbilled")
    assert resp.status_code == 200, resp.text
    eintraege = resp.json()
    assert isinstance(eintraege, list)
    assert len(eintraege) == 1
    e = eintraege[0]
    assert e["description"] == "Programmierung"
    assert e["duration_hours"] == 2.0
    assert e["duration_minutes"] == 120
    assert e["contact"] == "Muster GmbH"        # Schlüssel, den das Frontend liest


def test_unbilled_zeigt_nur_freigegebene(auth_client, db_session, test_user):
    _make_time_entry(db_session, test_user, status="veraenderbar", note="Entwurf")
    _make_time_entry(db_session, test_user, status="freigegeben", note="Fertig")

    eintraege = auth_client.get("/api/invoices/time-entries/unbilled").json()
    assert [e["description"] for e in eintraege] == ["Fertig"]


def test_unbilled_ohne_verrechenbar_und_ohne_ende(auth_client, db_session, test_user):
    _make_time_entry(db_session, test_user, billable=False, note="Intern")
    laufend = _make_time_entry(db_session, test_user, note="Laufend")
    laufend.ended_at = None
    db_session.commit()

    assert auth_client.get("/api/invoices/time-entries/unbilled").json() == []


def test_unbilled_schliesst_verrechnete_aus(auth_client, db_session, test_user):
    kontakt = _make_kontakt(db_session)
    eintrag = _make_time_entry(db_session, test_user, contact=kontakt)

    _create_invoice(auth_client, kontakt.id, positions=[{
        "pos_type": "time_entry", "description": "Zeitaufwand", "quantity": "2",
        "unit": "h", "unit_price": "100", "tax_rate": "20",
        "time_entry_id": str(eintrag.id),
    }])

    assert auth_client.get("/api/invoices/time-entries/unbilled").json() == []


def test_unbilled_filtert_nach_kontakt_und_suche(auth_client, db_session, test_user):
    a = _make_kontakt(db_session, display_name="Alpha GmbH")
    b = _make_kontakt(db_session, display_name="Beta GmbH")
    _make_time_entry(db_session, test_user, contact=a, note="Alpha-Arbeit")
    _make_time_entry(db_session, test_user, contact=b, note="Beta-Arbeit")

    nur_a = auth_client.get("/api/invoices/time-entries/unbilled",
                            params={"contact_id": str(a.id)}).json()
    assert [e["description"] for e in nur_a] == ["Alpha-Arbeit"]

    suche = auth_client.get("/api/invoices/time-entries/unbilled",
                            params={"search": "Beta"}).json()
    assert [e["description"] for e in suche] == ["Beta-Arbeit"]


def test_unbilled_findet_eintrag_ohne_kontakt_id_ueber_den_namen(auth_client, db_session, test_user):
    """
    Einträge aus „KI nachtragen" tragen nur den Kontaktnamen, keine contact_id.
    Ohne Namens-Rückfall verschwinden sie, sobald am Beleg ein Kontakt gewählt
    ist — der Übernahme-Dialog wäre dann grundlos leer.
    """
    kontakt = _make_kontakt(db_session, display_name="Muster GmbH")
    _make_time_entry(db_session, test_user, contact=kontakt,
                     note="Per KI nachgetragen", nur_kontaktname=True)

    treffer = auth_client.get("/api/invoices/time-entries/unbilled",
                              params={"contact_id": str(kontakt.id)}).json()
    assert [e["description"] for e in treffer] == ["Per KI nachgetragen"]


def test_unbilled_namensrueckfall_trifft_nicht_zu_viel(auth_client, db_session, test_user):
    """Der Rückfall vergleicht exakt — „Muster GmbH“ darf „Mustermann GmbH“ nicht einsammeln."""
    muster = _make_kontakt(db_session, display_name="Muster GmbH")
    mustermann = _make_kontakt(db_session, display_name="Mustermann GmbH")
    _make_time_entry(db_session, test_user, contact=mustermann,
                     note="Fremde Arbeit", nur_kontaktname=True)

    treffer = auth_client.get("/api/invoices/time-entries/unbilled",
                              params={"contact_id": str(muster.id)}).json()
    assert treffer == []


# ── Zeiteintrags-Status folgt dem Beleg ───────────────────────────────────────

def test_zeiteintrag_wird_beim_finalisieren_abgerechnet(auth_client, db_session, test_user):
    """
    Entwurf blockiert die Stunden noch nicht — erst wenn der Beleg den Entwurf
    verlässt, gilt der Zeiteintrag als abgerechnet.
    """
    kontakt = _make_kontakt(db_session)
    eintrag = _make_time_entry(db_session, test_user, contact=kontakt)
    inv = _create_invoice(auth_client, kontakt.id, positions=[{
        "pos_type": "time_entry", "description": "Zeitaufwand", "quantity": "2",
        "unit": "h", "unit_price": "100", "tax_rate": "20",
        "time_entry_id": str(eintrag.id),
    }])

    db_session.refresh(eintrag)
    assert eintrag.status == "freigegeben"      # Entwurf ändert nichts

    _finalisieren(auth_client, inv["id"])
    db_session.refresh(eintrag)
    assert eintrag.status == "abgerechnet"


def test_zeitposition_auf_finalisiertem_beleg_abgelehnt(auth_client, db_session, test_user):
    """
    Nachträglich Stunden auf einen ausgestellten Beleg zu buchen ist seit der
    Belegsperre nicht mehr möglich.

    Vorher war das erlaubt und der Zeiteintrag blieb dabei 'freigegeben' —
    er wäre im Übernahme-Dialog erneut angeboten und damit doppelt verrechnet
    worden. Die Sperre schließt diese Lücke an der Wurzel.
    """
    kontakt = _make_kontakt(db_session)
    eintrag = _make_time_entry(db_session, test_user, contact=kontakt)

    inv = _create_invoice(auth_client, kontakt.id)      # zunächst ohne Zeitposition
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "positions": [{
            "pos_type": "time_entry", "description": "Zeitaufwand",
            "quantity": "2", "unit": "h", "unit_price": "100", "tax_rate": "20",
            "time_entry_id": str(eintrag.id),
        }],
    })
    assert resp.status_code == 400
    assert "Positionen" in resp.json()["detail"]

    db_session.refresh(eintrag)
    assert eintrag.status == "freigegeben"     # unangetastet, weiter verrechenbar


def test_entwurf_laesst_zeiteintrag_offen(auth_client, db_session, test_user):
    """Gegenprobe: Ein Entwurf darf die Stunden nicht blockieren."""
    kontakt = _make_kontakt(db_session)
    eintrag = _make_time_entry(db_session, test_user, contact=kontakt)
    inv = _create_invoice(auth_client, kontakt.id, positions=[{
        "pos_type": "time_entry", "description": "Zeitaufwand", "quantity": "2",
        "unit": "h", "unit_price": "100", "tax_rate": "20",
        "time_entry_id": str(eintrag.id),
    }])

    # Entwurf erneut speichern — Status bleibt unberührt
    auth_client.put(f"/api/invoices/{inv['id']}", json={
        "doc_type": "rechnung", "contact_id": str(kontakt.id), "date": "2026-07-06",
        "positions": [{"pos_type": "time_entry", "description": "Zeitaufwand",
                       "quantity": "2", "unit": "h", "unit_price": "100",
                       "tax_rate": "20", "time_entry_id": str(eintrag.id)}],
    })
    db_session.refresh(eintrag)
    assert eintrag.status == "freigegeben"


def test_zeiteintrag_nach_storno_wieder_verrechenbar(auth_client, db_session, test_user):
    """Storno gibt die Stunden wieder frei — sonst wären sie dauerhaft verloren."""
    kontakt = _make_kontakt(db_session)
    eintrag = _make_time_entry(db_session, test_user, contact=kontakt)
    inv = _create_invoice(auth_client, kontakt.id, positions=[{
        "pos_type": "time_entry", "description": "Zeitaufwand", "quantity": "2",
        "unit": "h", "unit_price": "100", "tax_rate": "20",
        "time_entry_id": str(eintrag.id),
    }])
    _finalisieren(auth_client, inv["id"])

    resp = auth_client.post(f"/api/invoices/{inv['id']}/cancel",
                            json={"cancel_mode": "with_credit"})
    assert resp.status_code == 200, resp.text

    db_session.refresh(eintrag)
    assert eintrag.status == "freigegeben"

    # … und taucht wieder im Übernahme-Dialog auf
    eintraege = auth_client.get("/api/invoices/time-entries/unbilled").json()
    assert [e["id"] for e in eintraege] == [str(eintrag.id)]
