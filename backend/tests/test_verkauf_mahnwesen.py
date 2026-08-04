"""
Tests für Mahnwesen und Skonto (Etappe 3b, Befunde C-1 und C-9).

  C-1  Es gab keinen Weg, eine überfällige Rechnung anzumahnen — der Begriff
       kam im ganzen Repository nicht vor.
  C-9  „2 % Skonto binnen 10 Tagen" war weder als Text auf dem Beleg noch
       rechnerisch beim Zahlungseingang abbildbar.

Zwei Dinge werden hier besonders scharf geprüft, weil sie steuerlich falsch zu
machen teuer ist:

  * **Mahngebühr und Verzugszinsen sind kein Umsatz.** Sie dürfen weder in der
    UVA noch im Buchungsjournal auftauchen.
  * **Skonto wirkt im Monat der Zahlung**, nicht im Monat der Rechnung
    (§ 16 UStG) — und mindert bei gemischten Steuersätzen jeden Satz anteilig.

Schema analog zu test_verkauf_zahlungen.py.
"""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceSettings, InvoicePayment
from app.services import dunning as dunning_service
from app.services import skonto as skonto_service


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Muster GmbH", **daten):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    werte = {"email": "info@muster.at", "debitornummer": "20001"}
    werte.update(daten)
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name, data=werte)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create_invoice(client, contact_id=None, **extra):
    """Beleg über 1.200,00 € brutto (1.000 netto + 20 %), fällig 05.08.2026."""
    payload = {
        "doc_type": extra.pop("doc_type", "rechnung"),
        "contact_id": str(contact_id) if contact_id else None,
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "due_date": extra.pop("due_date", "2026-08-05"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Beratung",
            "quantity": "1", "unit_price": "1000", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ausstellen(client, invoice_id, status="offen"):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _offener_beleg(client, db, kontakt=None, **extra):
    kontakt = kontakt or _make_kontakt(db)
    inv = _create_invoice(client, kontakt.id, **extra)
    _ausstellen(client, inv["id"])
    return inv


def _mahnlauf(client, stichtag="2026-08-20"):
    resp = client.get("/api/invoices/dunning/run", params={"stichtag": stichtag})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _zeile(lauf, invoice_id):
    return next(z for z in lauf["items"] if z["invoice_id"] == invoice_id)


# ── C-1: Mahnlauf und Stufenlogik ─────────────────────────────────────────────

def test_mahnlauf_findet_ueberfaelligen_beleg(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)

    lauf = _mahnlauf(auth_client)          # 15 Tage nach Fälligkeit
    z = _zeile(lauf, inv["id"])
    assert z["dunnable"] is True
    assert z["next_level"] == 1
    assert z["next_label"] == "Zahlungserinnerung"
    assert z["days_overdue"] == 15
    assert Decimal(z["open_amount"]) == Decimal("1200.00")


def test_wartezeit_wird_eingehalten(auth_client, db_session):
    """
    Stufe 1 ist erst sieben Tage nach Fälligkeit dran. Vorher taucht der Beleg
    zwar auf — mit Begründung —, ist aber nicht mahnbar.
    """
    inv = _offener_beleg(auth_client, db_session)

    lauf = _mahnlauf(auth_client, stichtag="2026-08-08")   # 3 Tage überfällig
    z = _zeile(lauf, inv["id"])
    assert z["dunnable"] is False
    assert "12.08.2026" in z["reason"]

    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                            json={"dunned_at": "2026-08-08"})
    assert resp.status_code == 400
    assert "12.08.2026" in resp.json()["detail"]


def test_force_uebergeht_die_wartezeit(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                            json={"dunned_at": "2026-08-08", "force": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["level"] == 1


def test_stufen_folgen_aufeinander(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)

    erste = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                             json={"dunned_at": "2026-08-13"}).json()
    assert erste["level"] == 1
    assert erste["due_date"] == "2026-08-20"        # 7 Tage Nachfrist

    # Stufe 2 wartet 14 Tage NACH der ersten Mahnung, nicht ab Fälligkeit
    lauf = _mahnlauf(auth_client, stichtag="2026-08-20")
    assert _zeile(lauf, inv["id"])["dunnable"] is False

    lauf = _mahnlauf(auth_client, stichtag="2026-08-28")
    z = _zeile(lauf, inv["id"])
    assert z["dunnable"] is True
    assert z["next_level"] == 2
    assert z["current_level"] == 1


def test_alle_stufen_ausgeschoepft(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    for stufe in range(1, 5):
        resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                                json={"dunned_at": "2026-08-20", "force": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["level"] == stufe

    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                            json={"dunned_at": "2026-08-20", "force": True})
    assert resp.status_code == 400
    assert "ausgeschöpft" in resp.json()["detail"]


def test_beglichener_beleg_wird_nicht_gemahnt(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": "2026-08-10", "amount": "1200.00"})

    lauf = _mahnlauf(auth_client)
    assert all(z["invoice_id"] != inv["id"] for z in lauf["items"])

    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning", json={})
    assert resp.status_code == 400


def test_teilzahlung_mahnt_nur_den_rest(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": "2026-08-10", "amount": "700.00"})

    eintrag = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                               json={"dunned_at": "2026-08-20"}).json()
    assert Decimal(eintrag["open_amount"]) == Decimal("500.00")


# ── C-1: Mahnsperre ───────────────────────────────────────────────────────────

def test_mahnsperre_am_beleg_haelt_auch_gegen_force(auth_client, db_session):
    """
    Die Sperre ist eine bewusste Entscheidung. Sie darf nicht durch dieselbe
    Option fallen, die nur die Wartezeit übergehen soll.
    """
    inv = _offener_beleg(auth_client, db_session)
    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning-block",
                            json={"blocked": True, "reason": "Ratenvereinbarung"})
    assert resp.status_code == 200
    assert resp.json()["dunning_blocked"] is True

    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                            json={"dunned_at": "2026-08-20", "force": True})
    assert resp.status_code == 400
    assert "Ratenvereinbarung" in resp.json()["detail"]

    lauf = _mahnlauf(auth_client)
    assert _zeile(lauf, inv["id"])["dunnable"] is False


def test_mahnsperre_beim_kunden_wirkt_auf_alle_belege(auth_client, db_session):
    kontakt = _make_kontakt(db_session, "Sperrfirma GmbH", mahnsperre=True)
    a = _offener_beleg(auth_client, db_session, kontakt=kontakt)
    b = _offener_beleg(auth_client, db_session, kontakt=kontakt, date="2026-07-07",
                       delivery_date="2026-07-07", due_date="2026-08-06")

    lauf = _mahnlauf(auth_client)
    for inv in (a, b):
        z = _zeile(lauf, inv["id"])
        assert z["dunnable"] is False
        assert z["reason"] == "Mahnsperre beim Kunden"


def test_sperre_aufheben_macht_wieder_mahnbar(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/dunning-block",
                     json={"blocked": True, "reason": "Klärung"})
    resp = auth_client.post(f"/api/invoices/{inv['id']}/dunning-block",
                            json={"blocked": False})
    assert resp.json()["dunning_blocked"] is False
    assert resp.json()["dunning_block_reason"] is None
    assert _zeile(_mahnlauf(auth_client), inv["id"])["dunnable"] is True


# ── C-1: Verzugszinsen ────────────────────────────────────────────────────────

def test_ohne_basiszinssatz_keine_zinsen_aber_ein_hinweis(auth_client, db_session):
    """
    Lieber keine Zinsen als erfundene: Ohne gepflegten Basiszinssatz bleibt der
    Betrag null — und der Mahnlauf sagt, warum.

    Der Kunde braucht hier eine UID: Nur beim Unternehmer hängt der Zinssatz am
    Basiszinssatz. Gegenüber Verbrauchern gilt der feste gesetzliche Satz, der
    auch ohne Pflege bekannt ist.
    """
    kontakt = _make_kontakt(db_session, "Firma mit UID", uid="ATU12345678")
    inv = _offener_beleg(auth_client, db_session, kontakt=kontakt)
    auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                     json={"dunned_at": "2026-08-13"})          # Stufe 1, ohne Zinsen

    lauf = _mahnlauf(auth_client, stichtag="2026-08-28")         # Stufe 2, mit Zinsen
    z = _zeile(lauf, inv["id"])
    assert Decimal(z["interest"]) == Decimal("0.00")
    assert z["interest_rate"] is None
    assert "Basiszinssatz" in (lauf["interest_hint"] or "")


def test_zinsen_werden_taggenau_gerechnet(auth_client, db_session):
    db_session.add(InvoiceSettings(key="dunning_base_rate", value=0.8))
    db_session.commit()

    kontakt = _make_kontakt(db_session, "Firma mit UID", uid="ATU12345678")
    inv = _offener_beleg(auth_client, db_session, kontakt=kontakt)

    eintrag = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                               json={"dunned_at": "2026-09-04", "level": 2,
                                     "force": True}).json()
    # 0,8 + 9,2 = 10 % auf 1.200 € für 30 Tage: 1200 * 0,10 * 30/365
    assert Decimal(eintrag["interest_rate"]) == Decimal("10.000")
    assert eintrag["interest_days"] == 30
    assert Decimal(eintrag["interest"]) == Decimal("9.86")


def test_privatkunde_bekommt_den_gesetzlichen_satz(auth_client, db_session):
    """Ohne UID gilt der Verbrauchersatz von 4 % — unabhängig vom Basiszinssatz."""
    db_session.add(InvoiceSettings(key="dunning_base_rate", value=0.8))
    db_session.commit()

    kontakt = _make_kontakt(db_session, "Maria Muster")           # keine UID
    inv = _offener_beleg(auth_client, db_session, kontakt=kontakt)

    eintrag = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                               json={"dunned_at": "2026-09-04", "level": 2,
                                     "force": True}).json()
    assert Decimal(eintrag["interest_rate"]) == Decimal("4.000")


def test_gebuehr_kommt_aus_der_stufe(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    stufe1 = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                              json={"dunned_at": "2026-08-13"}).json()
    stufe2 = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                              json={"dunned_at": "2026-08-28"}).json()
    assert Decimal(stufe1["fee"]) == Decimal("0.00")     # Erinnerung ohne Gebühr
    assert Decimal(stufe2["fee"]) == Decimal("5.00")


def test_eigene_mahnstufen_haben_vorrang(auth_client, db_session):
    db_session.add(InvoiceSettings(key="dunning_levels", value=[
        {"level": 1, "label": "Freundliche Erinnerung", "days_after": 3,
         "grace_days": 5, "fee": "2.50", "interest": False, "text": "Bitte prüfen."},
    ]))
    db_session.commit()

    inv = _offener_beleg(auth_client, db_session)
    lauf = _mahnlauf(auth_client, stichtag="2026-08-09")
    z = _zeile(lauf, inv["id"])
    assert z["next_label"] == "Freundliche Erinnerung"
    assert z["dunnable"] is True
    assert Decimal(z["fee"]) == Decimal("2.50")


# ── C-1: Sammelmahnung ────────────────────────────────────────────────────────

def test_sammelmahnung_buendelt_je_kunde(auth_client, db_session):
    kunde_a = _make_kontakt(db_session, "Alpha GmbH")
    kunde_b = _make_kontakt(db_session, "Beta OG")
    a1 = _offener_beleg(auth_client, db_session, kontakt=kunde_a)
    a2 = _offener_beleg(auth_client, db_session, kontakt=kunde_a, date="2026-07-07",
                        delivery_date="2026-07-07", due_date="2026-08-06")
    b1 = _offener_beleg(auth_client, db_session, kontakt=kunde_b)

    resp = auth_client.post("/api/invoices/dunning/batch", json={
        "invoice_ids": [a1["id"], a2["id"], b1["id"]], "dunned_at": "2026-08-20"})
    assert resp.status_code == 200, resp.text
    eintraege = {e["invoice_id"]: e for e in resp.json()}
    assert len(eintraege) == 3
    assert eintraege[a1["id"]]["batch_id"] == eintraege[a2["id"]]["batch_id"]
    assert eintraege[b1["id"]]["batch_id"] != eintraege[a1["id"]]["batch_id"]


def test_gesperrter_beleg_bricht_den_sammellauf_nicht_ab(auth_client, db_session):
    """
    Ein Sonderfall darf den Lauf nicht kippen — sonst müsste man die Auswahl
    nach jedem gesperrten Beleg neu zusammenstellen.
    """
    offen = _offener_beleg(auth_client, db_session)
    gesperrt = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{gesperrt['id']}/dunning-block",
                     json={"blocked": True, "reason": "strittig"})

    resp = auth_client.post("/api/invoices/dunning/batch", json={
        "invoice_ids": [offen["id"], gesperrt["id"]], "dunned_at": "2026-08-20"})
    assert resp.status_code == 200
    assert [e["invoice_id"] for e in resp.json()] == [offen["id"]]


def test_sammellauf_ohne_mahnbaren_beleg_meldet_das(auth_client, db_session):
    gesperrt = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{gesperrt['id']}/dunning-block",
                     json={"blocked": True, "reason": "strittig"})
    resp = auth_client.post("/api/invoices/dunning/batch",
                            json={"invoice_ids": [gesperrt["id"]]})
    assert resp.status_code == 400


# ── C-1: Historie und Rücknahme ───────────────────────────────────────────────

def test_historie_und_ruecknahme(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/dunning", json={"dunned_at": "2026-08-13"})
    zweite = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                              json={"dunned_at": "2026-08-28"}).json()

    historie = auth_client.get(f"/api/invoices/{inv['id']}/dunning").json()
    assert [e["level"] for e in historie] == [1, 2]

    resp = auth_client.delete(f"/api/invoices/dunning/{zweite['id']}")
    assert resp.status_code == 200
    assert [e["level"] for e in resp.json()] == [1]

    beleg = auth_client.get(f"/api/invoices/{inv['id']}").json()
    assert beleg["dunning_level"] == 1
    assert beleg["dunning_last_at"] == "2026-08-13"


def test_mahnung_steht_im_aenderungsprotokoll(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/dunning", json={"dunned_at": "2026-08-13"})

    protokoll = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    eintrag = next(e for e in protokoll if e["action"] == "mahnung")
    assert "Zahlungserinnerung" in eintrag["note"]


def test_mahnschreiben_nennt_beleg_frist_und_betrag(auth_client, db_session):
    from app.services.dunning_pdf import baue_html
    from app.models.invoice import InvoiceDunning

    inv = _offener_beleg(auth_client, db_session)
    eintrag_json = auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                                    json={"dunned_at": "2026-08-13"}).json()
    eintrag = db_session.query(InvoiceDunning).filter_by(id=eintrag_json["id"]).first()

    html, dateiname = baue_html(db_session, eintrag)
    beleg = auth_client.get(f"/api/invoices/{inv['id']}").json()
    assert beleg["number"] in html
    assert "20. August 2026" in html             # Nachfrist, Langform im Brieftext
    assert "05.08.2026" in html                  # Fälligkeit in der Tabelle
    assert "1.200,00" in html
    assert "gegenstandslos" in html              # Überschneidungs-Hinweis
    assert dateiname.endswith("Stufe1.pdf")


def test_sammelmahnung_listet_alle_belege_auf_einem_schreiben(auth_client, db_session):
    from app.services.dunning_pdf import baue_html
    from app.models.invoice import InvoiceDunning

    kunde = _make_kontakt(db_session, "Alpha GmbH")
    a1 = _offener_beleg(auth_client, db_session, kontakt=kunde)
    a2 = _offener_beleg(auth_client, db_session, kontakt=kunde, date="2026-07-07",
                        delivery_date="2026-07-07", due_date="2026-08-06")
    resp = auth_client.post("/api/invoices/dunning/batch", json={
        "invoice_ids": [a1["id"], a2["id"]], "dunned_at": "2026-08-20"})
    erster = db_session.query(InvoiceDunning).filter_by(id=resp.json()[0]["id"]).first()

    html, _ = baue_html(db_session, erster)
    for beleg_id in (a1["id"], a2["id"]):
        nummer = auth_client.get(f"/api/invoices/{beleg_id}").json()["number"]
        assert nummer in html
    assert "2.400,00" in html                    # Gesamtforderung beider Belege


# ── C-1: Mahnkosten sind kein Umsatz ──────────────────────────────────────────

def test_mahngebuehr_taucht_nicht_in_der_uva_auf(auth_client, db_session):
    """
    Der wichtigste Test dieser Etappe: Gebühr und Zinsen sind Schadenersatz.
    Landeten sie im Umsatz, wäre die Umsatzsteuervoranmeldung falsch.
    """
    db_session.add(InvoiceSettings(key="dunning_base_rate", value=0.8))
    db_session.commit()
    kontakt = _make_kontakt(db_session, "Firma mit UID", uid="ATU12345678")
    inv = _offener_beleg(auth_client, db_session, kontakt=kontakt)

    vorher = auth_client.get("/api/invoices/uva",
                             params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                     json={"dunned_at": "2026-08-20", "level": 3, "force": True})
    nachher = auth_client.get("/api/invoices/uva",
                              params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()

    assert Decimal(nachher["kz_000"]) == Decimal(vorher["kz_000"]) == Decimal("1000.00")
    assert Decimal(nachher["steuer_gesamt"]) == Decimal("200.00")


def test_mahngebuehr_taucht_nicht_im_buchungsjournal_auf(auth_client, db_session):
    inv = _offener_beleg(auth_client, db_session)
    auth_client.post(f"/api/invoices/{inv['id']}/dunning",
                     json={"dunned_at": "2026-08-20", "level": 3, "force": True})

    resp = auth_client.get("/api/accounting/export/bmd",
                           params={"date_from": "2026-07-01", "date_to": "2026-08-31"})
    zeilen = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))
    betraege = [z[6] for z in zeilen[1:]]
    assert betraege == ["1000,00"]              # nur der Umsatz, keine Mahnkosten


# ── C-9: Skonto ───────────────────────────────────────────────────────────────

def test_skonto_bedingung_steht_auf_dem_beleg(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])

    html = auth_client.get(f"/api/invoices/{inv['id']}/preview").text
    assert "2 % Skonto" in html
    assert "16. Juli 2026" in html              # Belegdatum + 10 Tage


def test_skonto_felder_sind_nach_dem_ausstellen_gesperrt(auth_client, db_session):
    kontakt = _make_kontakt(db_session)
    inv = _create_invoice(auth_client, kontakt.id, skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])

    resp = auth_client.put(f"/api/invoices/{inv['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06", "skonto_percent": "5", "skonto_days": 10,
        "positions": [],
    })
    assert resp.status_code == 400
    assert "Skontosatz" in resp.json()["detail"]


def test_vorschau_kennt_frist_und_betrag(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])

    innerhalb = auth_client.get(f"/api/invoices/{inv['id']}/skonto",
                                params={"paid_at": "2026-07-14"}).json()
    assert innerhalb["in_frist"] is True
    assert Decimal(innerhalb["betrag"]) == Decimal("24.00")     # 2 % von 1.200
    assert innerhalb["frist_ende"] == "2026-07-16"

    danach = auth_client.get(f"/api/invoices/{inv['id']}/skonto",
                             params={"paid_at": "2026-07-20"}).json()
    assert danach["in_frist"] is False
    assert "16.07.2026" in danach["hinweis"]


def test_skonto_verteilt_sich_anteilig_auf_gemischte_saetze(auth_client, db_session):
    """
    Der rechnerische Kern: Ein Skonto mindert jeden Steuersatz anteilig. Läge
    er ganz auf einem Satz, wäre die Steuerberichtigung falsch.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10, positions=[
        {"pos_type": "item", "description": "Beratung", "quantity": "1",
         "unit_price": "1000", "tax_rate": "20"},
        {"pos_type": "item", "description": "Buch", "quantity": "1",
         "unit_price": "500", "tax_rate": "10"},
    ])
    _ausstellen(auth_client, inv["id"])

    daten = auth_client.get(f"/api/invoices/{inv['id']}/skonto",
                            params={"paid_at": "2026-07-10"}).json()
    # Brutto 1.200 + 550 = 1.750; 2 % = 35,00
    assert Decimal(daten["betrag"]) == Decimal("35.00")
    je_satz = {Decimal(z["satz"]): z for z in daten["zeilen"]}
    assert Decimal(je_satz[Decimal("20")]["brutto"]) == Decimal("24.00")
    assert Decimal(je_satz[Decimal("10")]["brutto"]) == Decimal("11.00")
    # Netto + Steuer ergibt wieder den Bruttoanteil, je Satz korrekt getrennt
    assert Decimal(je_satz[Decimal("20")]["netto"]) == Decimal("20.00")
    assert Decimal(je_satz[Decimal("20")]["steuer"]) == Decimal("4.00")
    assert Decimal(je_satz[Decimal("10")]["netto"]) == Decimal("10.00")
    assert Decimal(je_satz[Decimal("10")]["steuer"]) == Decimal("1.00")
    assert sum(Decimal(z["brutto"]) for z in daten["zeilen"]) == Decimal("35.00")


def test_skonto_ausbuchen_schliesst_den_beleg(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": "2026-07-10", "amount": "1176.00"})

    resp = auth_client.post(f"/api/invoices/{inv['id']}/skonto",
                            json={"paid_at": "2026-07-10"})
    assert resp.status_code == 200, resp.text
    stand = resp.json()
    assert stand["status"] == "bezahlt"
    assert Decimal(stand["open_amount"]) == Decimal("0.00")
    skonti = [z for z in stand["payments"] if z["payment_type"] == "skonto"]
    assert len(skonti) == 1
    assert Decimal(skonti[0]["amount"]) == Decimal("24.00")


def test_skonto_ueber_dem_offenen_betrag_wird_abgelehnt(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])
    resp = auth_client.post(f"/api/invoices/{inv['id']}/skonto",
                            json={"paid_at": "2026-07-10", "amount": "2000"})
    assert resp.status_code == 400
    assert "übersteigt" in resp.json()["detail"]


def test_skonto_steht_im_aenderungsprotokoll_mit_steuerbetrag(auth_client, db_session):
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=10)
    _ausstellen(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": "2026-07-10", "amount": "1176.00"})
    auth_client.post(f"/api/invoices/{inv['id']}/skonto", json={"paid_at": "2026-07-10"})

    protokoll = auth_client.get(f"/api/invoices/{inv['id']}/audit").json()
    eintrag = next(e for e in protokoll if e["action"] == "skonto")
    assert "4.00" in eintrag["note"]
    assert "§ 16 UStG" in eintrag["note"]


# ── C-9: Wirkung auf UVA und Buchhaltung ──────────────────────────────────────

def _skonto_beleg(auth_client, db_session, zahltag):
    """Rechnung vom Juli, Skonto im August ausgebucht."""
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=45)
    _ausstellen(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": zahltag, "amount": "1176.00"})
    resp = auth_client.post(f"/api/invoices/{inv['id']}/skonto", json={"paid_at": zahltag})
    assert resp.status_code == 200, resp.text
    return inv


def test_skonto_wirkt_im_monat_der_zahlung_nicht_der_rechnung(auth_client, db_session):
    """
    § 16 UStG: Die Berichtigung gehört in den Voranmeldungszeitraum der
    Änderung. Zöge sie den Rechnungsmonat mit, wäre eine bereits abgegebene
    Voranmeldung nachträglich falsch.
    """
    _skonto_beleg(auth_client, db_session, zahltag="2026-08-10")

    juli = auth_client.get("/api/invoices/uva",
                           params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    august = auth_client.get("/api/invoices/uva",
                             params={"date_from": "2026-08-01", "date_to": "2026-08-31"}).json()

    assert Decimal(juli["kz_000"]) == Decimal("1000.00")      # unberührt
    assert Decimal(august["kz_000"]) == Decimal("-20.00")     # nur die Minderung
    assert Decimal(august["steuer_gesamt"]) == Decimal("-4.00")
    assert any("Entgeltminderung" in h for h in august["hinweise"])


def test_skonto_erscheint_im_buchungsjournal_am_zahltag(auth_client, db_session):
    _skonto_beleg(auth_client, db_session, zahltag="2026-08-10")

    resp = auth_client.get("/api/accounting/export/bmd",
                           params={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    zeilen = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))[1:]
    assert len(zeilen) == 1                       # die Rechnung selbst ist im Juli
    zeile = zeilen[0]
    assert zeile[0] == "10.08.2026"
    assert zeile[2].startswith("Skonto")
    assert zeile[6] == "-20,00"                   # Erlösschmälerung netto
    assert zeile[8] == "-4,00"                    # Steuerberichtigung


def test_skonto_bucht_auf_das_erloeskonto_des_belegs(auth_client, db_session):
    """
    Der Skonto entlastet dasselbe Erlöskonto, das der Umsatz belastet hat —
    sonst stimmt bei zwei Erlöskonten am Beleg keines von beiden.
    """
    inv = _create_invoice(auth_client, _make_kontakt(db_session).id,
                          skonto_percent="2", skonto_days=45, positions=[
        {"pos_type": "item", "description": "Beratung", "quantity": "1",
         "unit_price": "1000", "tax_rate": "20", "account_nr": "4100"},
    ])
    _ausstellen(auth_client, inv["id"])
    auth_client.post(f"/api/invoices/{inv['id']}/payments",
                     json={"paid_at": "2026-08-10", "amount": "1176.00"})
    auth_client.post(f"/api/invoices/{inv['id']}/skonto", json={"paid_at": "2026-08-10"})

    resp = auth_client.get("/api/accounting/export/bmd",
                           params={"date_from": "2026-08-01", "date_to": "2026-08-31"})
    zeilen = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig")), delimiter=";"))[1:]
    assert zeilen[0][3] == "4100"


# ── Dienst-Ebene ──────────────────────────────────────────────────────────────

def test_zinsberechnung_ist_taggenau():
    assert dunning_service.zinsbetrag(
        Decimal("1200"), date(2026, 8, 5), date(2026, 9, 4), Decimal("10")
    ) == Decimal("9.86")
    # Kein Zeitraum, kein Zins
    assert dunning_service.zinsbetrag(
        Decimal("1200"), date(2026, 8, 5), date(2026, 8, 5), Decimal("10")
    ) == Decimal("0.00")
    # Ohne Satz wird nichts geschätzt
    assert dunning_service.zinsbetrag(
        Decimal("1200"), date(2026, 8, 5), date(2026, 9, 4), None
    ) == Decimal("0.00")


def test_skontoaufteilung_ohne_grundlage_bleibt_leer():
    class Leer:
        tax_mode = "per_position"
        positions = []
        subtotal = Decimal("0")
    assert skonto_service.aufteilung(Leer(), Decimal("10")) == []
