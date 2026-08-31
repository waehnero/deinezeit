"""
Tests für Eingangsrechnungen und Vorsteuer (Etappe 7).

Bis hierher kannte DeineZeit nur die Umsatzseite; jede Umsatzsteuer-Auswertung
trug den Vermerk, dass die Vorsteuer fehlt. Damit ließ sich keine
Voranmeldung erstellen, sondern nur eine Zuarbeit.

Der fachlich heikelste Punkt und daher am schärfsten geprüft: **Reverse Charge
und innergemeinschaftlicher Erwerb erzeugen zwei Einträge** — die selbst
geschuldete Steuer und, bei Abzugsberechtigung, die gleich hohe Vorsteuer.
Wird nur eine Seite gebucht, steht in der Voranmeldung eine Steuerschuld ohne
Gegenposten, und man zahlt zu viel.

Schema analog zu test_verkauf_zahlungen.py.
"""
import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import InvoiceSettings
from app.services import vorsteuer as vorsteuer_service


# Eingangsrechnungen legen ihr Original im Objektspeicher ab. In der CI gibt
# es kein MinIO — gleiche Stubbing-Regel wie in test_postecke.py und
# test_verkauf_positionstypen.py.
@pytest.fixture(autouse=True)
def _speicher_in_memory(monkeypatch):
    ablage = {}

    def _upload(key, data, mimetype=None, db=None, backend=None):
        ablage[key] = (data, mimetype or "application/octet-stream")

    def _download(key, db=None, backend=None):
        if key not in ablage:
            raise FileNotFoundError(key)
        return ablage[key]

    monkeypatch.setattr("app.services.storage_service.upload_file", _upload)
    monkeypatch.setattr("app.services.storage_service.download_file", _download)
    monkeypatch.setattr("app.services.storage_service.delete_file",
                        lambda key, db=None, backend=None: ablage.pop(key, None))
    return ablage


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_lieferant(db, name="Zulieferer GmbH", **daten):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    werte = {"typ": "Lieferant", "kreditornummer": "70001"}
    werte.update(daten)
    rec = EntityRecord(entity_type_id=et.id, display_name=name, data=werte)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _erfassen(client, lieferant=None, **extra):
    """Eingangsrechnung über 1.000 netto + 200 Vorsteuer."""
    payload = {
        "supplier_id": str(lieferant.id) if lieferant else None,
        "supplier_number": extra.pop("supplier_number", "RE-4711"),
        "date": extra.pop("date", "2026-07-10"),
        "delivery_date": extra.pop("delivery_date", "2026-07-10"),
        "due_date": extra.pop("due_date", "2026-08-09"),
        "title": extra.pop("title", "Büromaterial"),
        "account_nr": extra.pop("account_nr", None),
        "taxes": extra.pop("taxes", [
            {"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"},
        ]),
    }
    payload.update(extra)
    resp = client.post("/api/purchase-invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _uva(client, von="2026-07-01", bis="2026-07-31"):
    resp = client.get("/api/invoices/uva", params={"date_from": von, "date_to": bis})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _zeile(daten, kennzahl):
    treffer = [z for z in daten["zeilen"] if z["kennzahl"] == kennzahl]
    assert treffer, f"Keine Zeile mit Kennzahl {kennzahl} in {daten['zeilen']}"
    return treffer[0]


# ── Erfassung ─────────────────────────────────────────────────────────────────

def test_erfassung_rechnet_die_summen(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    assert Decimal(beleg["net_total"]) == Decimal("1000.00")
    assert Decimal(beleg["tax_total"]) == Decimal("200.00")
    assert Decimal(beleg["gross_total"]) == Decimal("1200.00")
    assert beleg["status"] == "offen"
    assert beleg["internal_number"] == "ER-2026-001"


def test_lieferantenname_wird_eingefroren(auth_client, db_session):
    """
    Wie der Empfänger-Snapshot beim Verkaufsbeleg: Eine spätere Umbenennung
    darf einen gebuchten Beleg nicht verändern.
    """
    lieferant = _make_lieferant(db_session, "Alte Firma GmbH", uid="ATU99999999")
    beleg = _erfassen(auth_client, lieferant)
    assert beleg["supplier_name"] == "Alte Firma GmbH"
    assert beleg["supplier_uid"] == "ATU99999999"

    lieferant.display_name = "Neue Firma GmbH"
    db_session.commit()

    nachher = auth_client.get(f"/api/purchase-invoices/{beleg['id']}").json()
    assert nachher["supplier_name"] == "Alte Firma GmbH"


def test_laufende_nummer_zaehlt_je_jahr(auth_client, db_session):
    lieferant = _make_lieferant(db_session)
    a = _erfassen(auth_client, lieferant)
    b = _erfassen(auth_client, lieferant)
    c = _erfassen(auth_client, lieferant, date="2027-01-05", due_date="2027-02-04",
                  delivery_date="2027-01-05")
    assert [a["internal_number"], b["internal_number"], c["internal_number"]] == \
           ["ER-2026-001", "ER-2026-002", "ER-2027-001"]


def test_ohne_betraege_wird_abgelehnt(auth_client, db_session):
    resp = auth_client.post("/api/purchase-invoices", json={
        "supplier_id": str(_make_lieferant(db_session).id),
        "date": "2026-07-10", "taxes": [],
    })
    assert resp.status_code == 400
    assert "Steuerzeile" in resp.json()["detail"]


def test_unbekannte_steuerart_wird_abgelehnt(auth_client, db_session):
    resp = auth_client.post("/api/purchase-invoices", json={
        "supplier_id": str(_make_lieferant(db_session).id),
        "date": "2026-07-10", "tax_kind": "phantasie",
        "taxes": [{"tax_rate": "20", "net_amount": "100", "tax_amount": "20"}],
    })
    assert resp.status_code == 400


def test_erfasster_steuerbetrag_wird_nicht_nachgerechnet(auth_client, db_session):
    """
    Auf der Lieferantenrechnung steht ein bestimmter Betrag — der gilt, auch
    wenn er um einen Cent von der eigenen Rundung abweicht. Sonst stimmt die
    Buchung nicht mit dem Beleg überein.
    """
    beleg = _erfassen(auth_client, _make_lieferant(db_session), taxes=[
        {"tax_rate": "20", "net_amount": "999.99", "tax_amount": "199.99"},
    ])
    assert Decimal(beleg["tax_total"]) == Decimal("199.99")   # nicht 200,00
    assert Decimal(beleg["gross_total"]) == Decimal("1199.98")


def test_gemischte_saetze_auf_einem_beleg(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session), taxes=[
        {"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"},
        {"tax_rate": "10", "net_amount": "500", "tax_amount": "50"},
    ])
    assert Decimal(beleg["net_total"]) == Decimal("1500.00")
    assert Decimal(beleg["tax_total"]) == Decimal("250.00")
    assert len(beleg["taxes"]) == 2


def test_reverse_charge_hat_keinen_zahlbetrag_aus_der_steuer(auth_client, db_session):
    """
    Bei Reverse Charge steht auf der Rechnung keine Steuer. Der Zahlbetrag ist
    der Nettobetrag — die Steuer geht ans Finanzamt, nicht an den Lieferanten.
    """
    beleg = _erfassen(auth_client, _make_lieferant(db_session),
                      tax_kind="reverse_charge", taxes=[
        {"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"},
    ])
    assert Decimal(beleg["net_total"]) == Decimal("1000.00")
    assert Decimal(beleg["tax_total"]) == Decimal("200.00")
    assert Decimal(beleg["gross_total"]) == Decimal("1000.00")


# ── Vorsteuer in der Auswertung ───────────────────────────────────────────────

def test_vorsteuer_erscheint_unter_kennzahl_060(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session))
    daten = _uva(auth_client)

    zeile = _zeile(daten, "060")
    assert Decimal(zeile["steuer"]) == Decimal("200.00")
    assert Decimal(zeile["bemessungsgrundlage"]) == Decimal("1000.00")
    assert zeile["zugeordnet"] is True


def test_vorsteuer_mindert_die_zahllast(auth_client, db_session):
    """
    Der eigentliche Zweck der Etappe: Umsatzsteuer minus Vorsteuer. Vorher
    stand hier die volle Umsatzsteuer und der Hinweis, dass die Vorsteuer
    fehlt.
    """
    from tests.test_verkauf_uva import _create_invoice, _ausstellen, _make_kontakt

    inv = _create_invoice(auth_client, _make_kontakt(db_session).id)   # 1.000 + 20 %
    _ausstellen(auth_client, inv["id"])
    _erfassen(auth_client, _make_lieferant(db_session))                 # 1.000 + 20 %

    daten = _uva(auth_client)
    assert Decimal(daten["kz_000"]) == Decimal("1000.00")     # nur eigene Umsätze
    assert Decimal(daten["steuer_gesamt"]) == Decimal("0.00") # 200 USt − 200 VSt


def test_nicht_abziehbare_vorsteuer_bleibt_draussen(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session),
              vat_deductible=False, vat_note="PKW, § 12 Abs. 2 UStG")
    daten = _uva(auth_client)

    assert not [z for z in daten["zeilen"] if z["kennzahl"] == "060"]
    assert any("nicht abziehbar" in h for h in daten["hinweise"])


def test_ohne_vorsteuer_erfasst_keine_vorsteuer(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session), tax_kind="ohne_vorsteuer")
    daten = _uva(auth_client)
    assert not [z for z in daten["zeilen"] if z["kennzahl"] == "060"]


def test_ig_erwerb_erzeugt_schuld_und_vorsteuer(auth_client, db_session):
    """
    Der Klassiker: Erwerbsteuer (070) und Vorsteuer (065) in gleicher Höhe.
    Fehlt die zweite Zeile, weist die Voranmeldung eine Steuerschuld aus, die
    es wirtschaftlich nicht gibt.
    """
    _erfassen(auth_client, _make_lieferant(db_session, "EU-Lieferant", uid="DE123456789"),
              tax_kind="ig_erwerb", taxes=[
        {"tax_rate": "20", "net_amount": "2000", "tax_amount": "400"},
    ])
    daten = _uva(auth_client)

    erwerb = _zeile(daten, "070")
    vorsteuer = _zeile(daten, "065")
    assert Decimal(erwerb["steuer"]) == Decimal("400.00")
    assert Decimal(erwerb["bemessungsgrundlage"]) == Decimal("2000.00")
    assert Decimal(vorsteuer["steuer"]) == Decimal("400.00")
    # Beide heben einander auf — die Zahllast bleibt unberührt
    assert Decimal(daten["steuer_gesamt"]) == Decimal("0.00")


def test_ig_erwerb_ohne_abzugsrecht_kostet_wirklich(auth_client, db_session):
    """
    Ohne Abzugsberechtigung bleibt die Erwerbsteuer stehen — das ist der
    teure Fall, den man in der Auswertung sehen muss.
    """
    _erfassen(auth_client, _make_lieferant(db_session), tax_kind="ig_erwerb",
              vat_deductible=False, taxes=[
        {"tax_rate": "20", "net_amount": "2000", "tax_amount": "400"},
    ])
    daten = _uva(auth_client)
    assert Decimal(_zeile(daten, "070")["steuer"]) == Decimal("400.00")
    assert not [z for z in daten["zeilen"] if z["kennzahl"] == "065"]
    assert Decimal(daten["steuer_gesamt"]) == Decimal("400.00")


def test_reverse_charge_schuld_erscheint_unter_057(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session), tax_kind="reverse_charge",
              taxes=[{"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"}])
    daten = _uva(auth_client)
    assert Decimal(_zeile(daten, "057")["steuer"]) == Decimal("200.00")


def test_ungepflegte_kennzahl_wird_gemeldet_nicht_geraten(auth_client, db_session):
    """
    Für die Vorsteuer aus Reverse Charge ist keine Kennzahl belegt. Sie bleibt
    leer und wird als solche ausgewiesen — dieselbe Regel wie auf der
    Umsatzseite.
    """
    _erfassen(auth_client, _make_lieferant(db_session), tax_kind="reverse_charge",
              taxes=[{"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"}])
    daten = _uva(auth_client)

    offen = [z for z in daten["zeilen"]
             if z["bezeichnung"].startswith("Vorsteuer zur übergegangenen")]
    assert offen and offen[0]["kennzahl"] == ""
    assert offen[0]["zugeordnet"] is False
    assert any("keine UVA-Kennzahl" in h for h in daten["hinweise"])


def test_gepflegte_kennzahl_hat_vorrang(auth_client, db_session):
    db_session.add(InvoiceSettings(key=vorsteuer_service.KENNZAHLEN_KEY,
                                   value={"vorsteuer_rc": "066"}))
    db_session.commit()

    _erfassen(auth_client, _make_lieferant(db_session), tax_kind="reverse_charge",
              taxes=[{"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"}])
    daten = _uva(auth_client)
    assert Decimal(_zeile(daten, "066")["steuer"]) == Decimal("200.00")


def test_auswertung_folgt_dem_rechnungsdatum(auth_client, db_session):
    """
    Eine im August erfasste Julirechnung gehört in die Voranmeldung für Juli —
    maßgeblich ist das Rechnungsdatum, nicht der Tag der Erfassung.
    """
    _erfassen(auth_client, _make_lieferant(db_session), date="2026-07-31",
              delivery_date="2026-07-31", due_date="2026-08-30")

    juli = _uva(auth_client, "2026-07-01", "2026-07-31")
    august = _uva(auth_client, "2026-08-01", "2026-08-31")
    assert Decimal(_zeile(juli, "060")["steuer"]) == Decimal("200.00")
    assert not [z for z in august["zeilen"] if z["kennzahl"] == "060"]


def test_stornierte_rechnung_zaehlt_nicht_mehr(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    assert auth_client.post(f"/api/purchase-invoices/{beleg['id']}/cancel").status_code == 200

    daten = _uva(auth_client)
    assert not [z for z in daten["zeilen"] if z["kennzahl"] == "060"]


def test_hinweis_auf_fehlende_originale(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session))
    daten = _uva(auth_client)
    assert any("kein hinterlegtes Original" in h for h in daten["hinweise"])


# ── Zahlungen und offene Posten ───────────────────────────────────────────────

def test_teilzahlung_und_ausgleich(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    pfad = f"/api/purchase-invoices/{beleg['id']}/payments"

    stand = auth_client.post(pfad, json={"paid_at": "2026-08-01", "amount": "700"}).json()
    assert stand["status"] == "teilbezahlt"
    assert Decimal(stand["open_amount"]) == Decimal("500.00")

    stand = auth_client.post(pfad, json={"paid_at": "2026-08-05", "amount": "500"}).json()
    assert stand["status"] == "bezahlt"
    assert Decimal(stand["open_amount"]) == Decimal("0.00")


def test_zahlung_zuruecknehmen(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    stand = auth_client.post(f"/api/purchase-invoices/{beleg['id']}/payments",
                             json={"paid_at": "2026-08-01", "amount": "1200"}).json()
    assert stand["status"] == "bezahlt"

    zurueck = auth_client.delete(
        f"/api/purchase-invoices/payments/{stand['payments'][0]['id']}").json()
    assert zurueck["status"] == "offen"
    assert Decimal(zurueck["open_amount"]) == Decimal("1200.00")


def test_offene_posten_mit_staffel(auth_client, db_session):
    """
    Fälligkeitsstaffel wie auf der Debitorenseite. Die Tage sind bewusst
    ausgerechnet im Test vermerkt — beim ersten Anlauf hatte ich sie im Kopf
    geschätzt und lag um eine Staffel daneben.
    """
    lieferant = _make_lieferant(db_session, "Alpha GmbH")
    _erfassen(auth_client, lieferant)                        # fällig 09.08. → 11 Tage
    _erfassen(auth_client, lieferant, date="2026-04-01",
              delivery_date="2026-04-01", due_date="2026-04-30")   # → 112 Tage

    resp = auth_client.get("/api/purchase-invoices/open-items",
                           params={"stichtag": "2026-08-20"})
    assert resp.status_code == 200
    daten = resp.json()
    assert daten["count"] == 2
    assert Decimal(daten["total_open"]) == Decimal("2400.00")
    assert daten["by_supplier"][0]["supplier_name"] == "Alpha GmbH"
    assert daten["by_supplier"][0]["count"] == 2

    je_beleg = {z["due_date"]: z for z in daten["items"]}
    assert je_beleg["2026-08-09"]["bucket"] == "b1_30"
    assert je_beleg["2026-08-09"]["days_overdue"] == 11
    assert je_beleg["2026-04-30"]["bucket"] == "b90_plus"
    assert je_beleg["2026-04-30"]["days_overdue"] == 112


def test_bezahlte_verschwinden_aus_den_offenen_posten(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    auth_client.post(f"/api/purchase-invoices/{beleg['id']}/payments",
                     json={"paid_at": "2026-08-01", "amount": "1200"})
    daten = auth_client.get("/api/purchase-invoices/open-items").json()
    assert daten["count"] == 0


def test_storno_mit_zahlung_wird_abgelehnt(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    auth_client.post(f"/api/purchase-invoices/{beleg['id']}/payments",
                     json={"paid_at": "2026-08-01", "amount": "500"})
    resp = auth_client.post(f"/api/purchase-invoices/{beleg['id']}/cancel")
    assert resp.status_code == 400
    assert "Zahlungen" in resp.json()["detail"]


# ── Periodensperre ────────────────────────────────────────────────────────────

def _als_admin(client):
    """Der Abschluss ist Admin-Sache — dieselbe Hilfe wie in test_verkauf_abschluss.py."""
    from tests.conftest import TEST_USER_PASSWORD
    resp = client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})


def _monat_schliessen(client, jahr=2026, monat=7):
    return client.post(f"/api/periods/{jahr}/{monat}/close")


def test_keine_erfassung_im_abgeschlossenen_monat(auth_client, db_session, admin_user):
    _erfassen(auth_client, _make_lieferant(db_session))
    _als_admin(auth_client)
    assert _monat_schliessen(auth_client).status_code == 200

    resp = auth_client.post("/api/purchase-invoices", json={
        "supplier_id": None, "title": "Nachzügler", "date": "2026-07-15",
        "taxes": [{"tax_rate": "20", "net_amount": "100", "tax_amount": "20"}],
    })
    assert resp.status_code == 400


def test_zahlung_bleibt_trotz_abschluss_moeglich(auth_client, db_session, admin_user):
    """
    Gleiche Entscheidung wie auf der Verkaufsseite: Eine Zahlung ändert nichts
    am Belegjournal des abgeschlossenen Monats.
    """
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    _als_admin(auth_client)
    assert _monat_schliessen(auth_client).status_code == 200

    resp = auth_client.post(f"/api/purchase-invoices/{beleg['id']}/payments",
                            json={"paid_at": "2026-07-20", "amount": "1200"})
    assert resp.status_code == 200


# ── Original und Export ───────────────────────────────────────────────────────

def test_original_hochladen_und_abrufen(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    resp = auth_client.post(f"/api/purchase-invoices/{beleg['id']}/file",
                            files={"file": ("rechnung.pdf", b"%PDF-1.4 test",
                                            "application/pdf")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_name"] == "rechnung.pdf"

    abruf = auth_client.get(f"/api/purchase-invoices/{beleg['id']}/file")
    assert abruf.status_code == 200
    assert abruf.content == b"%PDF-1.4 test"

    # Mit Original verschwindet der Mahn-Hinweis aus der Auswertung
    daten = _uva(auth_client)
    assert not any("kein hinterlegtes Original" in h for h in daten["hinweise"])


def test_fremder_dateityp_abgelehnt(auth_client, db_session):
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    resp = auth_client.post(f"/api/purchase-invoices/{beleg['id']}/file",
                            files={"file": ("liste.exe", b"x", "application/x-msdownload")})
    assert resp.status_code == 400


def test_buchungsjournal_eingang(auth_client, db_session):
    _erfassen(auth_client, _make_lieferant(db_session), account_nr="7600", taxes=[
        {"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"},
        {"tax_rate": "10", "net_amount": "500", "tax_amount": "50"},
    ])
    resp = auth_client.get("/api/accounting/export/bmd-eingang",
                           params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    assert resp.status_code == 200
    zeilen = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))
    kopf, daten = zeilen[0], zeilen[1:]
    assert "Aufwandskonto" in kopf and "Kreditorkonto" in kopf
    assert len(daten) == 2
    assert all(z[4] == "7600" for z in daten)          # Aufwandskonto beider Zeilen
    assert [z[6] for z in daten] == ["1000,00", "500,00"]
    assert [z[8] for z in daten] == ["200,00", "50,00"]


def test_eingangsrechnungen_stehen_nicht_im_verkaufsjournal(auth_client, db_session):
    """Die beiden Journale bleiben getrennt — sonst stünde Aufwand unter Erlös."""
    _erfassen(auth_client, _make_lieferant(db_session))
    resp = auth_client.get("/api/accounting/export/bmd",
                           params={"date_from": "2026-07-01", "date_to": "2026-07-31"})
    zeilen = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))
    assert len(zeilen) == 1          # nur die Kopfzeile


# ── Rechte ────────────────────────────────────────────────────────────────────

def test_eingangsrechnungen_verlangen_das_modul_buchhaltung(client, db_session, test_user):
    """Wer Belege schreibt, muss nicht sehen, was das Unternehmen einkauft."""
    from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

    test_user.allowed_modules = ["verkauf"]
    db_session.commit()
    token = client.post("/api/auth/login", json={
        "email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/invoices", headers=kopf).status_code == 200
    assert client.get("/api/purchase-invoices", headers=kopf).status_code == 403
    assert client.get("/api/purchase-invoices/open-items", headers=kopf).status_code == 403


# ── Aufwandskonto aus dem Lieferanten (Etappe 2) ──────────────────────────────
#
# Die Eingangsrechnung hat keine Positionen und damit keinen Artikelbezug —
# das Konto kann nur vom Lieferanten kommen. Gepflegt wird es am Kontakt im
# Feld ``aufwand_konto`` (Migration 0057).

def test_konto_wird_aus_dem_lieferanten_vorbelegt(auth_client, db_session):
    lieferant = _make_lieferant(db_session, aufwand_konto="5000")
    beleg = _erfassen(auth_client, lieferant)
    assert beleg["account_nr"] == "5000"


def test_eigene_angabe_hat_vorrang(auth_client, db_session):
    """Die Vorbelegung ist ein Vorschlag, keine Vorschrift."""
    lieferant = _make_lieferant(db_session, aufwand_konto="5000")
    beleg = _erfassen(auth_client, lieferant, account_nr="7200")
    assert beleg["account_nr"] == "7200"


def test_lieferant_ohne_konto_bleibt_leer(auth_client, db_session):
    """Kein geratenes Vorgabekonto.

    Beim Erlös ist 4000 eine vertretbare Annahme — im Aufwand nicht: Miete,
    Wareneinsatz und Personalaufwand sind verschiedene Konten. Eine sichtbare
    Lücke ist besser als eine stille Falschbuchung.
    """
    beleg = _erfassen(auth_client, _make_lieferant(db_session))
    assert not beleg["account_nr"]


def test_leeres_kontofeld_am_kontakt_zaehlt_als_nicht_gesetzt(auth_client, db_session):
    """Ein leeres Formularfeld kommt als "" an, nicht als None."""
    lieferant = _make_lieferant(db_session, aufwand_konto="   ")
    beleg = _erfassen(auth_client, lieferant)
    assert not beleg["account_nr"]


def test_ohne_lieferant_kein_konto(auth_client):
    beleg = _erfassen(auth_client, None)
    assert not beleg["account_nr"]


def test_aendern_fuellt_ein_geleertes_konto_nicht_wieder(auth_client, db_session):
    """Beim Ändern heißt leer: absichtlich entfernt.

    Würde die Vorbelegung auch hier greifen, ließe sich ein falsch
    zugeordnetes Konto nie entfernen — es käme beim nächsten Speichern wortlos
    zurück. Deshalb greift sie nur beim Anlegen.
    """
    lieferant = _make_lieferant(db_session, aufwand_konto="5000")
    beleg = _erfassen(auth_client, lieferant)
    assert beleg["account_nr"] == "5000"

    resp = auth_client.put(f"/api/purchase-invoices/{beleg['id']}", json={
        "supplier_id": str(lieferant.id),
        "date": beleg["date"],
        "account_nr": None,
        "taxes": [{"tax_rate": "20", "net_amount": "1000", "tax_amount": "200"}],
    })
    assert resp.status_code == 200, resp.text
    assert not resp.json()["account_nr"]


# ── Dienst-Ebene ──────────────────────────────────────────────────────────────

def test_kontofindung_ohne_lieferant(db_session):
    from app.services import kreditor
    assert kreditor.aufwandskonto_fuer_lieferant(db_session, None) is None


def test_kontofindung_bei_unbekanntem_kontakt(db_session):
    """Ein Verweis ins Leere darf keinen Fehler werfen, nur nichts liefern."""
    import uuid as _uuid
    from app.services import kreditor
    assert kreditor.aufwandskonto_fuer_lieferant(db_session, _uuid.uuid4()) is None


def test_kennzahlen_vorgaben_sind_belegt():
    """060, 065, 057 und 070 sind belegt; der Rest bleibt bewusst offen."""
    vorgaben = vorsteuer_service.DEFAULT_KENNZAHLEN
    assert vorgaben["vorsteuer_inland"] == "060"
    assert vorgaben["vorsteuer_ig"] == "065"
    assert vorgaben["steuerschuld_rc"] == "057"
    assert vorgaben["erwerb_gesamt"] == "070"
    assert vorgaben["vorsteuer_rc"] == ""
    assert vorgaben["vorsteuer_einfuhr"] == ""
