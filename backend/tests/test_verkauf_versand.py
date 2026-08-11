"""
Tests für den E-Mail-Versand eines Belegs.

Anlass ist ein Fehler aus dem Betrieb (Oliver): Wer einen frisch angelegten
Beleg gleich per E-Mail verschickt, bekommt beim Kunden ein PDF mit dem
Wasserzeichen **ENTWURF** quer darüber. Erst beim zweiten Versand ist es weg.

Ursache war die Reihenfolge: Das PDF entstand, **bevor** der Beleg den Entwurf
verließ. Das betraf nicht nur das Wasserzeichen — der Empfänger wurde live aus
den Stammdaten gerendert statt aus dem eingefrorenen Snapshot, und die
Pflichtprüfungen (Leistungsdatum, Periodensperre) liefen erst *nach* dem
Versand: Die Mail war beim Kunden, und der Server meldete anschließend einen
Fehler.

Die Tests prüfen deshalb nicht das Aussehen des PDF, sondern **den Zustand des
Belegs im Augenblick der PDF-Erzeugung**. Das ist die eigentliche Bedingung —
und im Gegensatz zu einer Suche nach „ENTWURF" in komprimierten PDF-Bytes kann
sie nicht falsch grün werden.

Schema analog zu test_verkauf_erweiterungen.py.
"""
import pytest

from app.models.masterdata import EntityType, EntityRecord


# ── Hilfen ────────────────────────────────────────────────────────────────────

def _make_kontakt(db, display_name="Bauherr GmbH"):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    rec = EntityRecord(entity_type_id=et.id, display_name=display_name,
                       data={"email": "buero@bauherr.at", "adresse": "Ringstraße 9",
                             "plz": "1010", "ort": "Wien"})
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _create(client, contact_id, doc_type="rechnung", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id),
        "title": extra.pop("title", "Sanierung"),
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Leistung", "quantity": "1",
            "unit": "Stk", "unit_price": "1000", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def versand(monkeypatch):
    """
    Fängt den Versand ab und hält fest, in welchem Zustand der Beleg war, als
    das PDF entstand.

    Der SMTP-Versand wird ersetzt, die PDF-Erzeugung nur belauscht — sie soll
    tatsächlich laufen, damit auch ein Fehler beim Rendern auffällt.
    """
    from app.services import invoice_pdf, email_service

    protokoll = {"pdf": [], "mails": [], "anhaenge": []}
    echtes_pdf = invoice_pdf.generate_pdf

    def _mit_protokoll(invoice, positions, *args, **kwargs):
        protokoll["pdf"].append({
            "status": invoice.status,
            "nummer": invoice.number,
            "hat_snapshot": bool(invoice.recipient_snapshot),
            "erechnung": kwargs.get("erechnung_xml") is not None,
        })
        return echtes_pdf(invoice, positions, *args, **kwargs)

    def _mail(settings=None, to_email=None, **kwargs):
        protokoll["mails"].append(to_email)
        protokoll["anhaenge"] = kwargs.get("attachments") or []
        return True

    monkeypatch.setattr(invoice_pdf, "generate_pdf", _mit_protokoll)
    monkeypatch.setattr(email_service, "send_email", _mail)
    return protokoll


def _senden(client, invoice_id, **body):
    return client.post(f"/api/invoices/{invoice_id}/send-email", json=body)


# ── Der gemeldete Fehler ──────────────────────────────────────────────────────

def test_beleg_ist_beim_erzeugen_des_pdf_kein_entwurf_mehr(auth_client, db_session, versand):
    """
    Der Kern des Fehlers. Das Wasserzeichen hängt am Status: Solange der Beleg
    ein Entwurf ist, druckt das PDF „ENTWURF" quer darüber. Entsteht es vor dem
    Statuswechsel, bekommt der Kunde genau das.
    """
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    assert beleg["status"] == "entwurf"

    resp = _senden(auth_client, beleg["id"])
    assert resp.status_code == 200, resp.text

    assert len(versand["pdf"]) >= 1
    beim_druck = versand["pdf"][0]
    assert beim_druck["status"] != "entwurf", \
        "Das PDF entstand noch im Entwurf — der Kunde bekäme das Wasserzeichen"
    assert beim_druck["nummer"], "Ohne Nummer stünde auf dem Beleg keine Belegnummer"


def test_empfaenger_ist_beim_druck_bereits_eingefroren(auth_client, db_session, versand):
    """
    Sonst entstünde das versendete PDF aus den Live-Stammdaten, jeder spätere
    Nachdruck aber aus dem Snapshot — zwei Fassungen desselben Belegs.
    """
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    assert _senden(auth_client, beleg["id"]).status_code == 200
    assert versand["pdf"][0]["hat_snapshot"] is True


def test_umgewandeltes_angebot_geht_ohne_wasserzeichen_hinaus(auth_client, db_session, versand):
    """
    Der Weg, auf dem der Fehler aufgefallen ist: Angebot anlegen, in eine
    Rechnung umwandeln, die Rechnung sofort verschicken.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id, doc_type="angebot")
    rechnung = auth_client.post(f"/api/invoices/{angebot['id']}/convert-to-invoice").json()
    assert rechnung["status"] == "entwurf"

    assert _senden(auth_client, rechnung["id"]).status_code == 200
    assert versand["pdf"][0]["status"] != "entwurf"


def test_beleg_ist_nach_dem_versand_ausgestellt(auth_client, db_session, versand):
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    assert _senden(auth_client, beleg["id"]).status_code == 200

    danach = auth_client.get(f"/api/invoices/{beleg['id']}").json()
    assert danach["status"] == "gesendet"
    assert danach["number"]


# ── Die Prüfungen laufen jetzt vor dem Versand ────────────────────────────────

def test_fehlendes_leistungsdatum_verhindert_den_versand(auth_client, db_session, versand):
    """
    Vorher ging die Mail hinaus und der Server meldete danach einen Fehler —
    der Kunde hatte den Beleg, das System wusste nichts davon. Jetzt wird
    vorher geprüft, und es geht gar nichts hinaus.
    """
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id, delivery_date=None)

    resp = _senden(auth_client, beleg["id"])
    assert resp.status_code == 400
    assert "Leistungsdatum" in resp.json()["detail"]
    assert versand["mails"] == [], "Es darf nichts hinausgegangen sein"

    danach = auth_client.get(f"/api/invoices/{beleg['id']}").json()
    assert danach["status"] == "entwurf", "Der Beleg muss Entwurf geblieben sein"
    assert danach["number"] is None


def test_klartext_statt_technischer_meldung(auth_client, db_session, versand):
    """
    Die Prüfmeldung darf nicht als „E-Mail konnte nicht gesendet werden"
    verkleidet werden — gesendet wurde ja gerade nicht, und der Grund liegt
    am Beleg.
    """
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id, delivery_date=None)
    detail = _senden(auth_client, beleg["id"]).json()["detail"]
    assert "E-Mail konnte nicht gesendet werden" not in detail


# ── Erneuter Versand ──────────────────────────────────────────────────────────

def test_zweiter_versand_aendert_den_status_nicht(auth_client, db_session, versand):
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    assert _senden(auth_client, beleg["id"]).status_code == 200
    erste_nummer = auth_client.get(f"/api/invoices/{beleg['id']}").json()["number"]

    assert _senden(auth_client, beleg["id"]).status_code == 200
    danach = auth_client.get(f"/api/invoices/{beleg['id']}").json()
    assert danach["status"] == "gesendet"
    assert danach["number"] == erste_nummer, "Die Nummer darf sich nicht ändern"
    # Auch beim zweiten Mal ohne Wasserzeichen
    assert all(p["status"] != "entwurf" for p in versand["pdf"])


def test_erneuter_versand_steht_im_protokoll(auth_client, db_session, versand):
    """„Wann ging der Beleg zum zweiten Mal hinaus" wird tatsächlich gefragt."""
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    _senden(auth_client, beleg["id"])
    _senden(auth_client, beleg["id"])

    protokoll = auth_client.get(f"/api/invoices/{beleg['id']}/audit").json()
    notizen = [e.get("note") or "" for e in protokoll]
    assert any("Erneut per E-Mail" in n for n in notizen)


def test_bezahlter_beleg_behaelt_seinen_status(auth_client, db_session, versand):
    """Ein Nachdruck an den Kunden darf „bezahlt" nicht auf „gesendet" zurückdrehen."""
    kontakt = _make_kontakt(db_session)
    beleg = _create(auth_client, kontakt.id)
    _senden(auth_client, beleg["id"])
    auth_client.post(f"/api/invoices/{beleg['id']}/mark-paid",
                     json={"paid_at": "2026-07-20"})

    assert _senden(auth_client, beleg["id"]).status_code == 200
    assert auth_client.get(f"/api/invoices/{beleg['id']}").json()["status"] == "bezahlt"
