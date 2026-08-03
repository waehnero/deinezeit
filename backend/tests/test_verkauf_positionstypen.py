"""
Tests für Überschrift, Freitext, Zwischensumme und Rabattzeile (A-15).

Die Typen standen seit jeher im Modell, hatten aber kein Verhalten: `text`
wurde gerendert, war im Formular aber nicht anlegbar; `discount` und
`subtotal` waren reine Beschriftungen.

Der heikle Punkt ist die **Rabattzeile bei gemischten Steuersätzen**: Sie
trägt selbst keinen Satz, sondern mindert die Sätze ihrer Gruppe anteilig.
Ohne diese Aufteilung wäre die MwSt.-Aufschlüsselung auf dem Beleg falsch —
und der Buchhaltungs-Export gleich mit. Deshalb prüfen die Tests alle drei
Auswerter: gespeicherte Summen, PDF-Aufschlüsselung und BMD-Export.

Schema analog zu test_verkauf_steuer.py.
"""
import csv
import io
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.services import positionen as positionen_service


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data={"email": "info@muster.at", "debitornummer": "20001"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _pos(typ="item", text="Position", menge="1", preis="0", satz=None, pct=None):
    return {"pos_type": typ, "description": text, "quantity": menge,
            "unit_price": preis, "tax_rate": satz, "discount_pct": pct}


def _create_invoice(client, contact_id, positionen, **extra):
    payload = {
        "doc_type": "rechnung", "contact_id": str(contact_id),
        "date": "2026-07-06", "delivery_date": "2026-07-06",
        "positions": positionen,
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _zeilen(inv):
    return {p["pos_type"]: p for p in inv["positions"]}


# ── Gliederung ────────────────────────────────────────────────────────────────

def test_ueberschrift_und_freitext_tragen_nichts_bei(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("heading", "Leistungsblock A"),
        _pos("text", "Erläuterung zur Ausführung"),
        _pos("item", "Beratung", "1", "1000", "20"),
    ])
    assert Decimal(inv["subtotal"]) == Decimal("1000.00")
    assert Decimal(inv["total"]) == Decimal("1200.00")
    zeilen = _zeilen(inv)
    assert Decimal(zeilen["heading"]["line_total"]) == 0
    assert Decimal(zeilen["text"]["line_total"]) == 0


def test_zwischensumme_summiert_seit_der_ueberschrift(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Vorspann", "1", "500", "20"),
        _pos("heading", "Block A"),
        _pos("item", "A1", "1", "300", "20"),
        _pos("item", "A2", "1", "200", "20"),
        _pos("subtotal", "Summe Block A"),
    ])
    # Die 500 vor der Überschrift zählen NICHT zur Gruppe
    assert Decimal(inv["positions"][4]["line_total"]) == Decimal("500.00")
    assert Decimal(inv["subtotal"]) == Decimal("1000.00")


def test_freitext_zerreisst_die_gruppe_nicht(auth_client, db_session):
    """Nur die Überschrift eröffnet eine Gruppe — das war die Entscheidung."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("heading", "Block A"),
        _pos("item", "A1", "1", "300", "20"),
        _pos("text", "Zwischenbemerkung"),
        _pos("item", "A2", "1", "200", "20"),
        _pos("subtotal", "Summe Block A"),
    ])
    assert Decimal(inv["positions"][4]["line_total"]) == Decimal("500.00")


def test_zweite_zwischensumme_beginnt_neu(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "A", "1", "100", "20"),
        _pos("subtotal", "Summe 1"),
        _pos("item", "B", "1", "200", "20"),
        _pos("subtotal", "Summe 2"),
    ])
    assert Decimal(inv["positions"][1]["line_total"]) == Decimal("100.00")
    assert Decimal(inv["positions"][3]["line_total"]) == Decimal("200.00")


# ── Rabattzeile ───────────────────────────────────────────────────────────────

def test_rabatt_als_fester_betrag(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Leistung", "1", "1000", "20"),
        _pos("discount", "Nachlass", "1", "100"),
    ])
    assert Decimal(inv["positions"][1]["line_total"]) == Decimal("-100.00")
    assert Decimal(inv["subtotal"]) == Decimal("900.00")
    assert Decimal(inv["tax_total"]) == Decimal("180.00")
    assert Decimal(inv["total"]) == Decimal("1080.00")


def test_rabatt_in_prozent_der_gruppe(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Leistung", "1", "1000", "20"),
        _pos("discount", "10 % Nachlass", "1", "0", pct="10"),
    ])
    assert Decimal(inv["positions"][1]["line_total"]) == Decimal("-100.00")
    assert Decimal(inv["tax_total"]) == Decimal("180.00")


def test_rabatt_wird_anteilig_auf_die_saetze_verteilt(auth_client, db_session):
    """
    Der Kern der Sache: 500 € Rabatt auf eine Gruppe aus 1.000 € zu 20 % und
    1.000 € zu 10 %. Beide Sätze werden um je 250 € gemindert — 20 %: 750 →
    150 €, 10 %: 750 → 75 €, zusammen 225 €.

    Läge der Rabatt komplett auf einem Satz, wären es 200 € oder 250 €, und
    die Aufschlüsselung auf dem Beleg wäre falsch.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Zu 20 %", "1", "1000", "20"),
        _pos("item", "Zu 10 %", "1", "1000", "10"),
        _pos("discount", "Projektnachlass", "1", "500"),
    ])
    assert Decimal(inv["subtotal"]) == Decimal("1500.00")
    assert Decimal(inv["tax_total"]) == Decimal("225.00")
    assert Decimal(inv["total"]) == Decimal("1725.00")


def test_rabatt_wirkt_nur_auf_die_eigene_gruppe(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("heading", "Block A"),
        _pos("item", "A1", "1", "1000", "20"),
        _pos("subtotal", "Summe A"),
        _pos("heading", "Block B"),
        _pos("item", "B1", "1", "500", "20"),
        _pos("discount", "Nachlass auf B", "1", "100"),
    ])
    assert Decimal(inv["positions"][5]["line_total"]) == Decimal("-100.00")
    assert Decimal(inv["subtotal"]) == Decimal("1400.00")


def test_rabatt_nicht_groesser_als_die_gruppe(auth_client, db_session):
    """Ein Rabatt über den Gruppenbetrag hinaus würde einen Negativumsatz erzeugen."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Leistung", "1", "100", "20"),
        _pos("discount", "Zu viel", "1", "500"),
    ])
    assert Decimal(inv["positions"][1]["line_total"]) == Decimal("-100.00")
    assert Decimal(inv["subtotal"]) == Decimal("0.00")


def test_zwischensumme_enthaelt_den_rabatt(auth_client, db_session):
    """Die Zwischensumme soll zeigen, was die Gruppe tatsächlich kostet."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("heading", "Block A"),
        _pos("item", "A1", "1", "1000", "20"),
        _pos("discount", "Nachlass", "1", "200"),
        _pos("subtotal", "Summe A"),
    ])
    assert Decimal(inv["positions"][3]["line_total"]) == Decimal("800.00")


# ── Dieselbe Regel in allen Auswertern ────────────────────────────────────────

def test_pdf_aufschluesselung_stimmt_mit_den_summen(auth_client, db_session):
    """Netto + MwSt. muss auch mit Rabattzeile die Gesamtsumme ergeben."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Zu 20 %", "1", "1000", "20"),
        _pos("item", "Zu 10 %", "1", "1000", "10"),
        _pos("discount", "Nachlass", "1", "500"),
    ])
    html = auth_client.get(f"/api/invoices/{inv['id']}/preview").text

    # Der Beleg druckt die Steuer je Satz, nicht als eine Summe. Richtig
    # verteilt sind es 150,00 (20 % auf 750) und 75,00 (10 % auf 750).
    # Läge der Rabatt komplett auf einem Satz, stünde dort 100,00/200,00
    # oder 250,00/50,00.
    assert "150,00" in html
    assert "75,00" in html
    assert "1.725,00" in html                # Gesamtsumme = 1500 + 225
    assert "Reverse Charge" not in html      # der Rabatt darf nicht im RC-Topf landen


def test_bmd_export_verteilt_den_rabatt_ebenfalls(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("item", "Zu 20 %", "1", "1000", "20"),
        _pos("item", "Zu 10 %", "1", "1000", "10"),
        _pos("discount", "Nachlass", "1", "500"),
    ])
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    resp = auth_client.get("/api/accounting/export/bmd")
    zeilen = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))
    je_code = {z["USt-Code"]: z for z in zeilen}
    assert je_code["U20"]["Nettobetrag"] == "750,00"
    assert je_code["U20"]["USt-Betrag"] == "150,00"
    assert je_code["U10"]["Nettobetrag"] == "750,00"
    assert je_code["U10"]["USt-Betrag"] == "75,00"
    assert "URC" not in je_code              # keine Rabattzeile im RC-Topf


def test_gliederungszeilen_nicht_im_export(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        _pos("heading", "Block A"),
        _pos("text", "Hinweis"),
        _pos("item", "A1", "1", "1000", "20"),
        _pos("subtotal", "Summe A"),
    ])
    auth_client.post(f"/api/invoices/{inv['id']}/set-status", json={"status": "offen"})

    resp = auth_client.get("/api/accounting/export/bmd")
    zeilen = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))
    assert len(zeilen) == 1
    assert zeilen[0]["Nettobetrag"] == "1000,00"


# ── Die gemeinsame Rechenregel selbst ─────────────────────────────────────────

def test_rabattverteilung_summiert_exakt():
    """Die Rundungsdifferenz darf nicht verloren gehen."""
    gruppe = {Decimal("20"): Decimal("333.33"), Decimal("10"): Decimal("333.33"),
              Decimal("0"): Decimal("333.34")}
    basis = sum(gruppe.values(), Decimal("0"))
    betrag = Decimal("100.00")
    anteile = positionen_service.rabatt_verteilen(gruppe, basis, betrag)
    assert sum(anteile.values(), Decimal("0")) == betrag


def test_rabattverteilung_ohne_basis():
    assert positionen_service.rabatt_verteilen({}, Decimal("0"), Decimal("50")) == {}


# ── Bild je Position ──────────────────────────────────────────────────────────

def _testbild(breite=1200, hoehe=800) -> bytes:
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (200, 60, 40)).save(puffer, format="PNG")
    return puffer.getvalue()


def test_bild_wird_auf_die_gewaehlte_groesse_verkleinert(auth_client, db_session):
    """
    Die Größe wird beim Hochladen physisch festgelegt — das war die
    Entscheidung „nach dem Upload fixieren".
    """
    from PIL import Image
    from app.services import position_image, storage_service

    for groesse, erwartete_breite in [("klein", 240), ("mittel", 480), ("gross", 800)]:
        resp = auth_client.post(f"/api/invoices/positions/image?size={groesse}",
                                files={"file": ("bild.png", _testbild(), "image/png")})
        assert resp.status_code == 200, resp.text
        daten = resp.json()
        assert daten["image_size"] == groesse
        assert daten["breite_mm"] == position_image.GROESSEN[groesse][0]

        roh, _mime = storage_service.download_file(daten["image_key"], db=db_session)
        assert Image.open(io.BytesIO(roh)).width == erwartete_breite


def test_kleines_bild_wird_nicht_vergroessert(auth_client, db_session):
    from PIL import Image
    from app.services import storage_service

    resp = auth_client.post("/api/invoices/positions/image?size=gross",
                            files={"file": ("klein.png", _testbild(100, 80), "image/png")})
    roh, _ = storage_service.download_file(resp.json()["image_key"], db=db_session)
    assert Image.open(io.BytesIO(roh)).width == 100


def test_unbekannte_groesse_abgelehnt(auth_client, db_session):
    resp = auth_client.post("/api/invoices/positions/image?size=riesig",
                            files={"file": ("bild.png", _testbild(), "image/png")})
    assert resp.status_code == 400
    assert "Größe" in resp.json()["detail"]


def test_nicht_bild_abgelehnt(auth_client, db_session):
    resp = auth_client.post("/api/invoices/positions/image?size=mittel",
                            files={"file": ("text.txt", b"kein Bild", "text/plain")})
    assert resp.status_code == 400


def test_bild_ueberlebt_das_speichern(auth_client, db_session):
    """
    Der Kern der Konstruktion: Positionen werden beim Speichern gelöscht und
    neu angelegt. Das Bild hängt deshalb nicht an der Position, sondern reist
    als Feld mit — sonst wäre es nach dem ersten Bearbeiten weg.
    """
    hoch = auth_client.post("/api/invoices/positions/image?size=mittel",
                            files={"file": ("bild.png", _testbild(), "image/png")}).json()
    kontakt = _make_kontakt(db_session)

    inv = _create_invoice(auth_client, kontakt.id, [
        {**_pos("item", "Mit Bild", "1", "100", "20"),
         "image_key": hoch["image_key"], "image_size": "mittel"},
    ])
    assert inv["positions"][0]["image_key"] == hoch["image_key"]

    # Bearbeiten — dabei werden die Positionen neu angelegt
    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06",
        "positions": [{**_pos("item", "Mit Bild", "1", "100", "20"),
                       "image_key": hoch["image_key"], "image_size": "mittel"}],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["positions"][0]["image_key"] == hoch["image_key"]


def test_bild_erscheint_im_beleg(auth_client, db_session):
    hoch = auth_client.post("/api/invoices/positions/image?size=klein",
                            files={"file": ("bild.png", _testbild(), "image/png")}).json()
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        {**_pos("item", "Mit Bild", "1", "100", "20"),
         "image_key": hoch["image_key"], "image_size": "klein"},
    ])

    html = auth_client.get(f"/api/invoices/{inv['id']}/preview").text
    assert "data:image/" in html          # als Data-URL eingebettet
    assert "width:30mm" in html           # Druckbreite der Größe „klein"


def test_fehlendes_bild_verhindert_den_beleg_nicht(auth_client, db_session):
    """Ein nicht auffindbares Bild darf die Vorschau nicht scheitern lassen."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id, [
        {**_pos("item", "Mit totem Verweis", "1", "100", "20"),
         "image_key": "belege/positionsbilder/gibtesnicht.jpg", "image_size": "mittel"},
    ])
    resp = auth_client.get(f"/api/invoices/{inv['id']}/preview")
    assert resp.status_code == 200
    assert "Mit totem Verweis" in resp.text


def test_bildabruf_lehnt_fremde_schluessel_ab(auth_client, db_session):
    """Der Endpunkt darf nicht zum Auslesen beliebiger Speicherpfade werden."""
    resp = auth_client.get("/api/invoices/positions/image",
                           params={"key": "kontakte/Muster/Vertraege/geheim.pdf"})
    assert resp.status_code == 400
