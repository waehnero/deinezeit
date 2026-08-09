"""
Tests für die Angebotsgültigkeit (A-17h) und den Umgang mit Positionsbildern.

A-17h war der letzte offene Punkt aus Teil A der Analyse: Ein Angebot ohne
Bindefrist bindet einen unbefristet an Preise, die vor Monaten kalkuliert
wurden.

Die wichtigste Entscheidung dabei ist eine Unterlassung: **„abgelaufen" wird
nicht als Status gespeichert.** Ein abgelaufenes Angebot ist nicht abgelehnt —
würde ein Hintergrundlauf es dazu machen, ginge der Unterschied zwischen „hat
abgesagt" und „hat sich nicht gemeldet" verloren. Der Ablauf wird deshalb aus
dem Datum abgeleitet, und wer nach Fristende umwandelt, wird gefragt statt
gehindert.

Dazu die Bilder: Beim Speichern werden Positionen gelöscht und neu angelegt.
Bisher blieb das Bild einer entfernten Position für immer im Speicher liegen.

Schema analog zu test_verkauf_steuer.py.
"""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.models.invoice import Invoice, InvoiceSettings
from app.services import angebot as angebot_service


class Speicher(dict):
    """
    Objektspeicher-Attrappe, die **je Anbieter getrennt** ablegt.

    Genau das ist der Punkt: Im Mischbetrieb liegt eine ältere Datei noch in
    MinIO, während längst OneDrive aktiv ist. Eine Attrappe mit nur einem Topf
    würde diesen Fehler verstecken — sie fände die Datei immer.
    """
    def __init__(self):
        super().__init__()
        self.aktiv = "minio"

    def _topf(self, backend):
        return self.setdefault(backend or self.aktiv, {})

    def __contains__(self, key):
        return any(key in topf for topf in self.values())

    def liegt_in(self, backend, key) -> bool:
        return key in self.get(backend, {})


@pytest.fixture(autouse=True)
def _speicher_in_memory(monkeypatch):
    """Objektspeicher in-memory — in der CI gibt es kein MinIO."""
    ablage = Speicher()

    def _upload(key, data, mimetype=None, db=None, backend=None):
        ablage._topf(backend)[key] = (data, mimetype or "application/octet-stream")

    def _download(key, db=None, backend=None):
        topf = ablage._topf(backend)
        if key not in topf:
            raise FileNotFoundError(key)
        return topf[key]

    def _delete(key, db=None, backend=None):
        ablage._topf(backend).pop(key, None)

    monkeypatch.setattr("app.services.storage_service.upload_file", _upload)
    monkeypatch.setattr("app.services.storage_service.download_file", _download)
    monkeypatch.setattr("app.services.storage_service.delete_file", _delete)
    monkeypatch.setattr("app.services.storage_service.current_backend",
                        lambda db=None: ablage.aktiv)
    return ablage


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


def _create(client, contact_id, doc_type="angebot", **extra):
    payload = {
        "doc_type": doc_type,
        "contact_id": str(contact_id) if contact_id else None,
        "title": extra.pop("title", "Angebot Sanierung"),
        "date": extra.pop("date", "2026-07-06"),
        "delivery_date": extra.pop("delivery_date", "2026-07-06"),
        "positions": extra.pop("positions", [{
            "pos_type": "item", "description": "Planung",
            "quantity": "1", "unit_price": "1000", "tax_rate": "20",
        }]),
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ausstellen(client, invoice_id, status="gesendet"):
    resp = client.post(f"/api/invoices/{invoice_id}/set-status", json={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _liste(client):
    return client.get("/api/invoices").json()


# ── Vorbelegung ───────────────────────────────────────────────────────────────

def test_angebot_bekommt_die_vorgabefrist(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    assert angebot["valid_until"] == "2026-08-05"      # Belegdatum + 30 Tage


def test_eigene_frist_hat_vorrang(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id,
                      valid_until="2026-07-20")
    assert angebot["valid_until"] == "2026-07-20"


def test_gepflegte_vorgabe_wird_verwendet(auth_client, db_session):
    db_session.add(InvoiceSettings(key=angebot_service.VORGABE_KEY, value="14"))
    db_session.commit()

    angebot = _create(auth_client, _make_kontakt(db_session).id)
    assert angebot["valid_until"] == "2026-07-20"      # 6.7. + 14 Tage


def test_vorgabe_null_laesst_das_feld_leer(auth_client, db_session):
    """
    Null Tage heißt „keine Vorbelegung" — nicht „Frist am Belegdatum". Sonst
    wäre jedes Angebot am Tag seiner Erstellung schon abgelaufen.
    """
    db_session.add(InvoiceSettings(key=angebot_service.VORGABE_KEY, value="0"))
    db_session.commit()

    angebot = _create(auth_client, _make_kontakt(db_session).id)
    assert angebot["valid_until"] is None


def test_unbrauchbare_vorgabe_faellt_auf_dreissig_zurueck(auth_client, db_session):
    db_session.add(InvoiceSettings(key=angebot_service.VORGABE_KEY, value="bald"))
    db_session.commit()
    assert angebot_service.vorgabe_tage(db_session) == 30


def test_rechnung_bekommt_keine_bindefrist(auth_client, db_session):
    """Eine Rechnung hat ein Zahlungsziel, keine Bindefrist."""
    rechnung = _create(auth_client, _make_kontakt(db_session).id, doc_type="rechnung")
    assert rechnung["valid_until"] is None


# ── Ablauf wird abgeleitet, nicht gespeichert ─────────────────────────────────

def test_abgelaufenes_angebot_behaelt_seinen_status(auth_client, db_session):
    """
    Der Kern der Entscheidung: Kein Hintergrundlauf setzt das Angebot auf
    „abgelehnt". Es bleibt gesendet und wird nur als abgelaufen ausgewiesen.
    """
    gestern = (date.today() - timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=gestern)
    _ausstellen(auth_client, angebot["id"])

    eintrag = [z for z in _liste(auth_client) if z["id"] == angebot["id"]][0]
    assert eintrag["status"] == "gesendet"
    assert eintrag["expired"] is True


def test_laufendes_angebot_ist_nicht_abgelaufen(auth_client, db_session):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=morgen)
    _ausstellen(auth_client, angebot["id"])

    eintrag = [z for z in _liste(auth_client) if z["id"] == angebot["id"]][0]
    assert eintrag["expired"] is False


def test_erledigte_angebote_gelten_nicht_als_abgelaufen(auth_client, db_session):
    """
    Ein angenommenes oder abgelehntes Angebot nachträglich als „abgelaufen" zu
    kennzeichnen wäre bloß Lärm — die Sache ist entschieden.
    """
    gestern = (date.today() - timedelta(days=1)).isoformat()
    for ziel in ("angenommen", "abgelehnt"):
        angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=gestern)
        _ausstellen(auth_client, angebot["id"])
        auth_client.post(f"/api/invoices/{angebot['id']}/set-status", json={"status": ziel})

        eintrag = [z for z in _liste(auth_client) if z["id"] == angebot["id"]][0]
        assert eintrag["status"] == ziel
        assert eintrag["expired"] is False


def test_entwurf_gilt_nicht_als_abgelaufen(auth_client, db_session):
    gestern = (date.today() - timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=gestern)
    eintrag = [z for z in _liste(auth_client) if z["id"] == angebot["id"]][0]
    assert eintrag["expired"] is False


def test_angebot_ohne_frist_laeuft_nie_ab(auth_client, db_session):
    db_session.add(InvoiceSettings(key=angebot_service.VORGABE_KEY, value="0"))
    db_session.commit()
    angebot = _create(auth_client, _make_kontakt(db_session).id)
    _ausstellen(auth_client, angebot["id"])

    eintrag = [z for z in _liste(auth_client) if z["id"] == angebot["id"]][0]
    assert eintrag["valid_until"] is None
    assert eintrag["expired"] is False


# ── Umwandeln nach Fristende ──────────────────────────────────────────────────

def test_umwandeln_nach_ablauf_fragt_nach(auth_client, db_session):
    gestern = (date.today() - timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=gestern)
    _ausstellen(auth_client, angebot["id"])

    resp = auth_client.post(f"/api/invoices/{angebot['id']}/convert-to-ab")
    assert resp.status_code == 409
    assert "Bindefrist" in resp.json()["detail"]

    # Mit Bestätigung geht es durch
    resp = auth_client.post(f"/api/invoices/{angebot['id']}/convert-to-ab",
                            params={"trotz_ablauf": True})
    assert resp.status_code == 200
    assert resp.json()["doc_type"] == "auftragsbestaetigung"


def test_umwandeln_in_rechnung_fragt_ebenfalls_nach(auth_client, db_session):
    gestern = (date.today() - timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=gestern)
    _ausstellen(auth_client, angebot["id"])

    assert auth_client.post(
        f"/api/invoices/{angebot['id']}/convert-to-invoice").status_code == 409
    assert auth_client.post(
        f"/api/invoices/{angebot['id']}/convert-to-invoice",
        params={"trotz_ablauf": True}).status_code == 200


def test_gueltiges_angebot_wandelt_ohne_rueckfrage(auth_client, db_session):
    morgen = (date.today() + timedelta(days=1)).isoformat()
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until=morgen)
    _ausstellen(auth_client, angebot["id"])

    resp = auth_client.post(f"/api/invoices/{angebot['id']}/convert-to-ab")
    assert resp.status_code == 200


# ── Beleg und Sperre ──────────────────────────────────────────────────────────

def test_frist_steht_auf_dem_angebot(auth_client, db_session):
    angebot = _create(auth_client, _make_kontakt(db_session).id, valid_until="2026-07-20")
    _ausstellen(auth_client, angebot["id"])

    html = auth_client.get(f"/api/invoices/{angebot['id']}/preview").text
    assert "Gültig bis" in html
    assert "20. Juli 2026" in html          # Vorlage 1 schreibt die Langform


def test_rechnung_zeigt_keine_bindefrist(auth_client, db_session):
    rechnung = _create(auth_client, _make_kontakt(db_session).id, doc_type="rechnung")
    _ausstellen(auth_client, rechnung["id"], status="offen")
    html = auth_client.get(f"/api/invoices/{rechnung['id']}/preview").text
    assert "Gültig bis" not in html


def test_frist_ist_nach_dem_ausstellen_gesperrt(auth_client, db_session):
    """
    Die Frist steht auf dem versendeten Angebot. Sie nachträglich zu verlängern
    hieße, dem Kunden stillschweigend etwas anderes zuzusagen.
    """
    kontakt = _make_kontakt(db_session)
    angebot = _create(auth_client, kontakt.id, valid_until="2026-07-20")
    _ausstellen(auth_client, angebot["id"])

    resp = auth_client.put(f"/api/invoices/{angebot['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06", "valid_until": "2026-12-31",
        "positions": [],
    })
    assert resp.status_code == 400
    assert "Gültig bis" in resp.json()["detail"]


def test_vorgabe_gehoert_zu_den_einstellungen(auth_client):
    daten = auth_client.get("/api/invoices/settings/all").json()
    assert daten["default_offer_valid_days"] == 30


# ── Positionsbilder: keine Waisen mehr ────────────────────────────────────────

def _bild(breite=400, hoehe=300) -> bytes:
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (30, 90, 200)).save(puffer, format="PNG")
    return puffer.getvalue()


def _bild_hochladen(client):
    """Gibt (schlüssel, provider) zurück — der Provider reist mit der Position mit."""
    daten = client.post("/api/invoices/positions/image?size=mittel",
                        files={"file": ("bild.png", _bild(), "image/png")}).json()
    return daten["image_key"], daten["image_provider"]


def test_entfernte_position_nimmt_ihr_bild_mit(auth_client, db_session, _speicher_in_memory):
    """
    Bisher blieb die Datei für immer liegen. Ein Aufräumlauf über den
    Objektspeicher ist nicht möglich — die Provider können nicht auflisten.
    Beim Ersetzen der Positionen wissen wir aber genau, welche Schlüssel
    betroffen sind.
    """
    kontakt = _make_kontakt(db_session)
    schluessel, provider = _bild_hochladen(auth_client)
    assert schluessel in _speicher_in_memory

    beleg = _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "Mit Bild", "quantity": "1",
         "unit_price": "100", "tax_rate": "20",
         "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider},
    ])

    # Position ohne Bild ersetzen
    resp = auth_client.put(f"/api/invoices/{beleg['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "Ohne Bild",
                       "quantity": "1", "unit_price": "100", "tax_rate": "20"}],
    })
    assert resp.status_code == 200
    assert schluessel not in _speicher_in_memory


def test_weiter_verwendetes_bild_bleibt_erhalten(auth_client, db_session, _speicher_in_memory):
    """
    Dasselbe Bild kann durch Duplizieren an zwei Belegen hängen. Es darf erst
    verschwinden, wenn die letzte Position darauf verzichtet.
    """
    kontakt = _make_kontakt(db_session)
    schluessel, provider = _bild_hochladen(auth_client)

    a = _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "A", "quantity": "1", "unit_price": "100",
         "tax_rate": "20", "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider}])
    _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "B", "quantity": "1", "unit_price": "100",
         "tax_rate": "20", "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider}])

    auth_client.put(f"/api/invoices/{a['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "A ohne Bild",
                       "quantity": "1", "unit_price": "100", "tax_rate": "20"}],
    })
    assert schluessel in _speicher_in_memory       # Beleg B nutzt es noch


def test_unveraenderte_position_behaelt_ihr_bild(auth_client, db_session, _speicher_in_memory):
    kontakt = _make_kontakt(db_session)
    schluessel, provider = _bild_hochladen(auth_client)
    beleg = _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "Mit Bild", "quantity": "1",
         "unit_price": "100", "tax_rate": "20",
         "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider}])

    auth_client.put(f"/api/invoices/{beleg['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06", "title": "neuer Titel",
        "positions": [{"pos_type": "item", "description": "Mit Bild", "quantity": "1",
                       "unit_price": "100", "tax_rate": "20",
                       "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider}],
    })
    assert schluessel in _speicher_in_memory


def test_geloeschter_entwurf_nimmt_seine_bilder_mit(auth_client, db_session,
                                                    _speicher_in_memory, admin_user):
    from tests.conftest import TEST_USER_PASSWORD

    kontakt = _make_kontakt(db_session)
    schluessel, provider = _bild_hochladen(auth_client)
    beleg = _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "Mit Bild", "quantity": "1",
         "unit_price": "100", "tax_rate": "20",
         "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider}])

    # Löschen ist Admin-Sache
    token = auth_client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local",
        "password": TEST_USER_PASSWORD}).json()["access_token"]
    auth_client.headers.update({"Authorization": f"Bearer {token}"})

    assert auth_client.delete(f"/api/invoices/{beleg['id']}").status_code == 204
    assert schluessel not in _speicher_in_memory


# ── Dienst-Ebene ──────────────────────────────────────────────────────────────

def test_resttage_und_ablauf_rechnen_richtig():
    from types import SimpleNamespace as NS

    angebot = NS(doc_type="angebot", status="gesendet", valid_until=date(2026, 8, 20))
    assert angebot_service.resttage(angebot, date(2026, 8, 15)) == 5
    assert angebot_service.resttage(angebot, date(2026, 8, 25)) == -5
    assert angebot_service.ist_abgelaufen(angebot, date(2026, 8, 20)) is False   # letzter Tag zählt
    assert angebot_service.ist_abgelaufen(angebot, date(2026, 8, 21)) is True

    rechnung = NS(doc_type="rechnung", status="offen", valid_until=date(2026, 1, 1))
    assert angebot_service.resttage(rechnung) is None
    assert angebot_service.ist_abgelaufen(rechnung) is False


def test_bild_wird_im_eigenen_speicher_geloescht(auth_client, db_session, _speicher_in_memory):
    """
    Der Fall, den Oliver zu Recht angemahnt hat: Das Bild wurde in MinIO
    abgelegt, danach wurde auf OneDrive umgestellt. Wird beim Aufräumen der
    AKTIVE Speicher verwendet statt des gespeicherten, bleibt die Datei
    unbemerkt in MinIO liegen — und die Vorschau fände sie ebenfalls nicht.
    """
    kontakt = _make_kontakt(db_session)
    schluessel, provider = _bild_hochladen(auth_client)
    assert provider == "minio"
    assert _speicher_in_memory.liegt_in("minio", schluessel)

    beleg = _create(auth_client, kontakt.id, doc_type="rechnung", positions=[
        {"pos_type": "item", "description": "Mit Bild", "quantity": "1",
         "unit_price": "100", "tax_rate": "20",
         "image_key": schluessel, "image_size": "mittel",
         "image_provider": provider},
    ])

    # Ab jetzt ist ein anderer Speicher aktiv
    _speicher_in_memory.aktiv = "onedrive"

    # Die Vorschau muss das Bild weiterhin finden
    abruf = auth_client.get("/api/invoices/positions/image",
                            params={"key": schluessel, "provider": provider})
    assert abruf.status_code == 200

    # Und das Aufräumen muss in MinIO löschen, nicht in OneDrive
    auth_client.put(f"/api/invoices/{beleg['id']}", json={
        "contact_id": str(kontakt.id), "date": "2026-07-06",
        "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "Ohne Bild",
                       "quantity": "1", "unit_price": "100", "tax_rate": "20"}],
    })
    assert not _speicher_in_memory.liegt_in("minio", schluessel)


def test_vorschau_ohne_provider_nutzt_den_aktiven_speicher(auth_client, _speicher_in_memory):
    """
    Bestandsdaten haben keinen Provider (NULL). Für sie gilt weiter der aktive
    Speicher — das ist das bisherige Verhalten und darf nicht brechen.
    """
    schluessel, _provider = _bild_hochladen(auth_client)
    abruf = auth_client.get("/api/invoices/positions/image", params={"key": schluessel})
    assert abruf.status_code == 200
