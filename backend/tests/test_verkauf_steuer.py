"""
Tests für Leistungsdatum, Steuersätze und Rundung (Modul Verkauf).

Deckt die Befunde A-5, A-6, B-1 und B-2 aus `docs/VERKAUF_ANALYSE.md` ab:

  A-5  Steuersätze standen an drei Stellen fest verdrahtet; 13 % war nicht
       erfassbar und wurde im Export still als 20 % gebucht
  A-6  Die Steuer wurde je Position gerundet — auf dem Beleg ergab
       Netto + MwSt. dadurch nicht die Gesamtsumme
  B-1  Das Liefer-/Leistungsdatum (Pflichtangabe § 11 Abs. 1 Z 4 UStG) war
       über kein Eingabefeld erreichbar und blieb immer leer
  B-2  Für Zeitabrechnung fehlte der Leistungszeitraum

Schema analog zu test_verkauf_belegsperre.py.
"""
import csv
import io
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceSettings
from app.services import tax_rates as tax_rates_service


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data={"email": "info@muster.at"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id=None, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "date": extra.pop("date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "2", "unit_price": "100", "tax_rate": "20",
        }]),
    }
    if "delivery_date" not in extra:
        payload["delivery_date"] = "2026-07-06"
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _export_zeilen(client, **params):
    resp = client.get("/api/accounting/export/bmd", params=params)
    assert resp.status_code == 200, resp.text
    return list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))


# ── A-6: Rundung je Steuersatz ────────────────────────────────────────────────

def test_steuer_wird_je_satz_gerundet(auth_client, db_session):
    """
    Drei Positionen zu 9,99 € mit 20 %.

    Je Position gerundet:  3 × 2,00 = 6,00 €  (falsch, ein Cent zu viel)
    Je Satz gerundet:      29,97 × 20 % = 5,994 → 5,99 €
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": f"Posten {i}", "quantity": "1",
         "unit_price": "9.99", "tax_rate": "20"} for i in range(3)
    ])
    assert Decimal(inv["subtotal"]) == Decimal("29.97")
    assert Decimal(inv["tax_total"]) == Decimal("5.99")
    assert Decimal(inv["total"]) == Decimal("35.96")


def test_netto_plus_steuer_ergibt_die_gesamtsumme(auth_client, db_session):
    """Gemischte Sätze — die Summenprobe muss aufgehen."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "item", "description": "A", "quantity": "1", "unit_price": "0.33", "tax_rate": "20"},
        {"pos_type": "item", "description": "B", "quantity": "1", "unit_price": "0.33", "tax_rate": "20"},
        {"pos_type": "item", "description": "C", "quantity": "1", "unit_price": "7.77", "tax_rate": "13"},
        {"pos_type": "item", "description": "D", "quantity": "1", "unit_price": "7.77", "tax_rate": "13"},
    ])
    assert Decimal(inv["subtotal"]) + Decimal(inv["tax_total"]) == Decimal(inv["total"])
    assert Decimal(inv["tax_total"]) == Decimal("2.15")


def test_textzeile_zaehlt_nicht_zur_summe(auth_client, db_session):
    """
    Eine Textzeile hat keinen Betrag. Früher lief sie in die Steuergruppen
    mit und erzeugte auf dem PDF eine erfundene Reverse-Charge-Zeile.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, positions=[
        {"pos_type": "text", "description": "Zwischenüberschrift",
         "quantity": "1", "unit_price": "500", "tax_rate": None},
        {"pos_type": "item", "description": "Leistung", "quantity": "1",
         "unit_price": "100", "tax_rate": "20"},
    ])
    assert Decimal(inv["subtotal"]) == Decimal("100.00")
    assert Decimal(inv["total"]) == Decimal("120.00")


def test_kleinunternehmer_ohne_steuer(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          tax_mode="kleinunternehmer")
    assert Decimal(inv["tax_total"]) == Decimal("0")
    assert Decimal(inv["total"]) == Decimal(inv["subtotal"])


# ── A-5: Steuersätze konfigurierbar ───────────────────────────────────────────

def test_vorgabesaetze_enthalten_dreizehn_prozent(db_session):
    saetze = tax_rates_service.get_tax_rates(db_session)
    werte = {int(s["satz"]) for s in saetze}
    assert werte == {20, 13, 10, 0}


def test_einstellungen_liefern_wirksame_saetze(auth_client, db_session):
    """Die Oberfläche soll keinen eigenen Vorgabewert vorhalten müssen."""
    daten = auth_client.get("/api/invoices/settings/all").json()
    assert [s["satz"] for s in daten["tax_rates"]] == [20, 13, 10, 0]
    assert daten["tax_rates"][0]["ust_code"] == "U20"


def test_gepflegte_saetze_haben_vorrang(auth_client, db_session):
    db_session.add(InvoiceSettings(key="tax_rates", value=[
        {"satz": 19, "bezeichnung": "Deutschland", "ust_code": "D19",
         "aktiv": True, "standard": True},
    ]))
    db_session.commit()

    daten = auth_client.get("/api/invoices/settings/all").json()
    assert daten["tax_rates"] == [{
        "satz": 19, "bezeichnung": "Deutschland", "ust_code": "D19",
        "aktiv": True, "standard": True}]


def test_unbrauchbarer_gespeicherter_wert_faellt_auf_vorgabe_zurueck(db_session):
    """
    Der Schlüssel lag in Bestandsinstallationen bereits in der Datenbank, ohne
    je gelesen worden zu sein — sein Inhalt ist unbekannt.
    """
    db_session.add(InvoiceSettings(key="tax_rates", value=["Unsinn", {"satz": "abc"}]))
    db_session.commit()

    saetze = tax_rates_service.get_tax_rates(db_session)
    assert {int(s["satz"]) for s in saetze} == {20, 13, 10, 0}


def test_ust_code_aus_den_einstellungen_im_export(auth_client, db_session):
    """Der gepflegte Code wandert unverändert in den BMD-Export."""
    db_session.add(InvoiceSettings(key="tax_rates", value=[
        {"satz": 20, "bezeichnung": "Normalsatz", "ust_code": "EIGEN20",
         "aktiv": True, "standard": True},
    ]))
    db_session.commit()

    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    assert _export_zeilen(auth_client)[0]["USt-Code"] == "EIGEN20"


def test_ungepflegter_satz_faellt_nicht_auf_zwanzig_zurueck(db_session):
    """
    Der frühere Fallback buchte jeden unbekannten Satz als U20 — ein 13-%-Umsatz
    landete damit still im Normalsatz. Jetzt wird der Code aus dem Prozentwert
    gebildet: falsch benannt fällt beim Steuerberater auf, falsch gebucht nicht.
    """
    saetze = tax_rates_service.get_tax_rates(db_session)
    assert tax_rates_service.ust_code_for(saetze, 7) == "U07"
    assert tax_rates_service.ust_code_for(saetze, None) == "URC"


# ── B-1 / B-2: Liefer- und Leistungsdatum ─────────────────────────────────────

def test_entwurf_ohne_leistungsdatum_speicherbar(auth_client, db_session):
    """Am Entwurf soll man arbeiten können, auch ohne Leistungsdatum."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, delivery_date=None)
    assert inv["delivery_date"] is None
    assert inv["status"] == "entwurf"


def test_ausstellen_ohne_leistungsdatum_abgelehnt(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, delivery_date=None)

    resp = auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})
    assert resp.status_code == 400
    assert "Leistungsdatum" in resp.json()["detail"]

    # Beleg bleibt Entwurf und ohne Nummer
    danach = auth_client.get(f"/api/invoices/{inv['id']}").json()
    assert danach["status"] == "entwurf"
    assert danach["number"] is None


def test_angebot_braucht_kein_leistungsdatum(auth_client, db_session):
    """Ein Angebot rechnet nichts ab — die Pflichtangabe greift dort nicht."""
    angebot = _create_invoice(auth_client, _make_kontakt(db_session).id,
                              doc_type="angebot", delivery_date=None)
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/set-status",
                            json={"status": "gesendet"})
    assert resp.status_code == 200, resp.text


def test_leistungszeitraum_wird_gespeichert(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          delivery_date="2026-07-01", delivery_date_to="2026-07-31")
    assert inv["delivery_date"] == "2026-07-01"
    assert inv["delivery_date_to"] == "2026-07-31"

    final = auth_client.post(f"/api/invoices/{inv['id']}/set-status",
                             json={"status": "offen"})
    assert final.status_code == 200, final.text


def test_verdrehter_zeitraum_abgelehnt(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          delivery_date="2026-07-31", delivery_date_to="2026-07-01")
    resp = auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})
    assert resp.status_code == 400
    assert "endet vor" in resp.json()["detail"]


def test_leistungszeitraum_auf_dem_beleg(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          delivery_date="2026-07-01", delivery_date_to="2026-07-31")
    html = auth_client.get(f"/api/invoices/{inv['id']}/preview").text
    assert "Leistungszeitraum" in html


def test_leistungsdatum_nach_dem_ausstellen_gesperrt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id)
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-09-01",
        "positions": [{"pos_type": "item", "description": "Beratung",
                       "quantity": "2", "unit_price": "100", "tax_rate": "20"}],
    })
    assert resp.status_code == 400
    assert "Liefer-/Leistungsdatum" in resp.json()["detail"]


def test_storno_gutschrift_uebernimmt_den_leistungszeitraum(auth_client, db_session):
    """Die Gutschrift betrifft dieselbe Leistung — sonst fehlt ihr die Pflichtangabe."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          delivery_date="2026-07-01", delivery_date_to="2026-07-31")
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})
    auth_client.post(f"/api/invoices/{inv['id']}/cancel", json={"cancel_mode": "with_credit"})

    gutschrift = db_session.query(Invoice).filter(Invoice.doc_type == "gutschrift").first()
    assert gutschrift is not None
    assert str(gutschrift.delivery_date) == "2026-07-01"
    assert str(gutschrift.delivery_date_to) == "2026-07-31"
