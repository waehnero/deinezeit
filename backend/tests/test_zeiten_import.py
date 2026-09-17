"""
Zeiten-Import (Projektzeiten aus Fremdsystemen)
===============================================

Geprüft wird, was bei einem Import von Arbeitszeiten schiefgehen kann, ohne
dass es jemand merkt:

* Ein Probelauf, der doch schreibt.
* Eine Datei, die zweimal eingespielt wird und die Stunden verdoppelt.
* Ein Mitarbeiter, der Zeiten auf einen Kollegen bucht.
* Eine Uhrzeit, die erfunden wird, weil die Datei nur eine Dauer kennt.
* Ein Datum, das still Tag und Monat vertauscht.
* Eine PDF-Tabelle der KI, die am Token-Limit abgerissen ist.

Wie beim Stammdaten-Import läuft alles über den Endpunkt: Der Bericht ist das,
was der Benutzer sieht, und er muss zur tatsächlichen Wirkung passen.
"""
import json
from datetime import datetime, timezone

import pytest

from app.core import zeitprojekte
from app.models.masterdata import EntityRecord, EntityType
from app.models.zeiterfassung import TimeEntry, TimeEntryField
from app.services import zeiten_pdf
from app.services.auth_service import auth_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"


def _kopf(client, email=TEST_USER_EMAIL) -> dict:
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _import(client, kopf, rows, **body):
    return client.post("/api/zeiterfassung/import", headers=kopf,
                       json={"rows": rows, **body})


def _zeile(**werte):
    zeile = {"datum": "03.08.2026", "beginn": "07:30", "ende": "12:00"}
    zeile.update(werte)
    return zeile


def _gruende(resp) -> str:
    return " | ".join(b["grund"] for b in resp.json()["beanstandungen"])


def _zeitprojekt(db, name="Musterbau Wartung", kontakt="Musterbau GmbH"):
    typ = EntityType(name="Zeitprojekte", slug=zeitprojekte.ZEITPROJEKTE_SLUG)
    db.add(typ)
    db.flush()
    satz = EntityRecord(entity_type_id=typ.id, display_name=name,
                        data={"kontakt": {"id": "x", "display_name": kontakt}})
    db.add(satz)
    db.commit()
    return satz


# ── Probelauf und Schreiben ──────────────────────────────────────────────────

def test_probelauf_schreibt_nichts(client, db_session, test_user):
    resp = _import(client, _kopf(client), [_zeile()])          # dry_run ist Vorgabe
    assert resp.status_code == 200, resp.text
    assert resp.json()["anlegen"] == 1
    assert resp.json()["angelegt"] == 0
    assert db_session.query(TimeEntry).count() == 0


def test_import_legt_eintrag_in_ortszeit_an(client, db_session, test_user):
    resp = _import(client, _kopf(client),
                   [_zeile(pause="0:30", notiz="Wartung", verrechenbar="nein")],
                   dry_run=False)
    assert resp.json()["angelegt"] == 1, resp.text
    assert resp.json()["minuten_gesamt"] == 240            # 4,5 h minus 30 min

    eintrag = db_session.query(TimeEntry).one()
    assert eintrag.user_id == test_user.id
    # 07:30 Wiener Sommerzeit = 05:30 UTC. Wäre die Angabe als UTC gelesen
    # worden, stünde jeder importierte Eintrag zwei Stunden daneben.
    assert eintrag.started_at.astimezone(timezone.utc) == datetime(
        2026, 8, 3, 5, 30, tzinfo=timezone.utc)
    assert eintrag.pause_minutes == 30
    assert eintrag.note == "Wartung"
    assert eintrag.billable is False
    assert eintrag.status == "veraenderbar"


def test_datum_und_uhrzeit_in_einer_spalte_und_iso(client, db_session, test_user):
    rows = [
        {"beginn": "03.08.2026 07:30", "ende": "03.08.2026 12:00"},
        {"beginn": "2026-08-04T05:30:00Z", "ende": "2026-08-04T10:00:00.000Z"},  # Toggl/Clockify
    ]
    resp = _import(client, _kopf(client), rows, dry_run=False)
    assert resp.json()["angelegt"] == 2, resp.text
    zweiter = (db_session.query(TimeEntry)
               .order_by(TimeEntry.started_at.desc()).first())
    assert zweiter.started_at.astimezone(timezone.utc).hour == 5


def test_ohne_entscheidung_wird_bei_beanstandungen_nichts_geschrieben(
        client, db_session, test_user):
    rows = [_zeile(), _zeile(datum="04.08.2026", ende="kaputt")]
    resp = _import(client, _kopf(client), rows, dry_run=False)
    assert resp.json()["angelegt"] == 0
    assert db_session.query(TimeEntry).count() == 0

    resp = _import(client, _kopf(client), rows, dry_run=False, skip_invalid=True)
    assert resp.json()["angelegt"] == 1
    assert resp.json()["uebersprungen"] == 1


# ── Nichts raten ─────────────────────────────────────────────────────────────

def test_nur_datum_und_dauer_wird_beanstandet(client, db_session, test_user):
    """Beschluss Oliver 18.09.2026: keine erfundene Uhrzeit."""
    resp = _import(client, _kopf(client), [{"datum": "03.08.2026", "notiz": "7,5 h"}])
    assert resp.json()["anlegen"] == 0
    assert "Beginn und Ende fehlen" in _gruende(resp)


@pytest.mark.parametrize("zeile, stichwort", [
    (_zeile(datum="03/04/2026"), "nicht eindeutig"),
    (_zeile(beginn="12:00", ende="07:30"), "nicht nach dem Beginn"),
    (_zeile(ende=""), "Ende fehlt"),
    (_zeile(pause="300"), "Pause ist so lang"),
    (_zeile(pause="halbe Stunde"), "Pause in ganzen Minuten"),
    (_zeile(verrechenbar="vielleicht"), "Ja/Nein"),
    ({"beginn": "07:30", "ende": "12:00"}, "Uhrzeit ohne Datum"),
    ({"beginn": "03.08.2026 07:30", "ende": "05.08.2026 12:00"}, "länger als 24"),
])
def test_unklares_wird_beanstandet(client, test_user, zeile, stichwort):
    resp = _import(client, _kopf(client), [zeile])
    assert resp.status_code == 200, resp.text
    assert resp.json()["anlegen"] == 0
    assert stichwort in _gruende(resp)


def test_eindeutiges_schraegstrich_datum_geht(client, db_session, test_user):
    rows = [_zeile(datum="25/03/2026"), _zeile(datum="03/26/2026")]   # TT/MM und MM/TT
    resp = _import(client, _kopf(client), rows, dry_run=False)
    assert resp.json()["angelegt"] == 2, resp.text
    tage = sorted(e.started_at.astimezone(timezone.utc).day
                  for e in db_session.query(TimeEntry).all())
    assert tage == [25, 26]


# ── Doppelte ─────────────────────────────────────────────────────────────────

def test_zweimal_dieselbe_datei_verdoppelt_nichts(client, db_session, test_user):
    kopf = _kopf(client)
    rows = [_zeile(), _zeile(datum="04.08.2026")]
    assert _import(client, kopf, rows, dry_run=False).json()["angelegt"] == 2

    resp = _import(client, kopf, rows, dry_run=False, skip_invalid=True)
    assert resp.json()["angelegt"] == 0
    assert "gibt es schon" in _gruende(resp)
    assert db_session.query(TimeEntry).count() == 2


def test_doppelte_zeile_in_der_datei(client, test_user):
    resp = _import(client, _kopf(client), [_zeile(), _zeile()])
    assert resp.json()["anlegen"] == 1
    assert "schon in Zeile 1" in _gruende(resp)


# ── Wem gehören die Einträge? ────────────────────────────────────────────────

def test_mitarbeiter_darf_nicht_fuer_andere_importieren(
        client, db_session, test_user, admin_user):
    kopf = _kopf(client)
    resp = _import(client, kopf, [_zeile(benutzer=ADMIN_EMAIL)], dry_run=False)
    assert resp.status_code == 403
    resp = _import(client, kopf, [_zeile()], user_id=str(admin_user.id), dry_run=False)
    assert resp.status_code == 403
    assert db_session.query(TimeEntry).count() == 0


def test_admin_ordnet_ueber_spalte_zu(client, db_session, test_user, admin_user):
    rows = [_zeile(benutzer=TEST_USER_EMAIL.upper()),
            _zeile(benutzer="Test Admin"),
            _zeile(benutzer="Niemand")]
    resp = _import(client, _kopf(client, ADMIN_EMAIL), rows,
                   dry_run=False, skip_invalid=True)
    assert resp.json()["angelegt"] == 2, resp.text
    assert "kein Benutzer" in _gruende(resp)
    besitzer = {e.user_id for e in db_session.query(TimeEntry).all()}
    assert besitzer == {test_user.id, admin_user.id}


def test_admin_waehlt_einen_benutzer_fuer_die_ganze_datei(
        client, db_session, test_user, admin_user):
    resp = _import(client, _kopf(client, ADMIN_EMAIL), [_zeile()],
                   user_id=str(test_user.id), dry_run=False)
    assert resp.json()["angelegt"] == 1, resp.text
    assert db_session.query(TimeEntry).one().user_id == test_user.id


def test_gleicher_name_zweimal_ist_nicht_eindeutig(client, db_session, test_user, admin_user):
    auth_service.create_user(db_session, email="zweiter@deinezeit.local",
                             full_name="Test Benutzer",
                             password=TEST_USER_PASSWORD, role="employee")
    resp = _import(client, _kopf(client, ADMIN_EMAIL), [_zeile(benutzer="Test Benutzer")])
    assert "mehrere Benutzer" in _gruende(resp)


def test_benutzerspalte_wird_nur_admins_angeboten(client, test_user, admin_user):
    felder = client.get("/api/zeiterfassung/import/felder", headers=_kopf(client)).json()
    assert "benutzer" not in [f["key"] for f in felder]
    felder = client.get("/api/zeiterfassung/import/felder",
                        headers=_kopf(client, ADMIN_EMAIL)).json()
    assert "benutzer" in [f["key"] for f in felder]


# ── Zeitprojekt und Custom-Felder ────────────────────────────────────────────

def test_zeitprojekt_wird_ueber_den_namen_gefunden(client, db_session, test_user):
    satz = _zeitprojekt(db_session)
    rows = [_zeile(zeitprojekt="musterbau wartung"),
            _zeile(datum="04.08.2026", zeitprojekt="Gibt es nicht")]
    resp = _import(client, _kopf(client), rows, dry_run=False, skip_invalid=True)
    assert resp.json()["angelegt"] == 1, resp.text
    assert "Zeitprojekt nicht gefunden" in _gruende(resp)
    eintrag = db_session.query(TimeEntry).one()
    assert eintrag.project_id == satz.id
    assert eintrag.project_name == "Musterbau Wartung"       # Schreibweise des Stammsatzes
    assert eintrag.contact_name == "Musterbau GmbH"


def test_custom_feld_wird_gedeutet_und_kernfeld_nicht_ueberdeckt(
        client, db_session, test_user):
    db_session.add(TimeEntryField(name="Kilometer", key="kilometer", field_type="number"))
    db_session.add(TimeEntryField(name="Notiz", key="notiz", field_type="text"))
    db_session.commit()

    felder = client.get("/api/zeiterfassung/import/felder", headers=_kopf(client)).json()
    assert "feld:kilometer" in [f["key"] for f in felder]

    rows = [_zeile(**{"feld:kilometer": "1.234,5", "feld:notiz": "frei", "notiz": "kern"})]
    resp = _import(client, _kopf(client), rows, dry_run=False)
    assert resp.json()["angelegt"] == 1, resp.text
    eintrag = db_session.query(TimeEntry).one()
    assert eintrag.data == {"kilometer": 1234.5, "notiz": "frei"}
    assert eintrag.note == "kern"

    resp = _import(client, _kopf(client),
                   [_zeile(datum="05.08.2026", **{"feld:kilometer": "weit"})])
    assert "keine Zahl" in _gruende(resp)


def test_zu_viele_zeilen_werden_abgelehnt(client, test_user):
    resp = _import(client, _kopf(client), [_zeile()] * 5001)
    assert resp.status_code == 422


# ── PDF über die KI ──────────────────────────────────────────────────────────

def _pdf_hochladen(client, kopf, inhalt=b"%PDF-1.7 test"):
    return client.post("/api/zeiterfassung/import/pdf", headers=kopf,
                       files={"file": ("zettel.pdf", inhalt, "application/pdf")})


def _ki_antwortet(monkeypatch, antwort, abgeschnitten=False, aufrufe=None):
    def _call_ki(ki, prompt, **kw):
        if aufrufe is not None:
            aufrufe.append(kw)
        if kw.get("meta") is not None:
            kw["meta"]["abgeschnitten"] = abgeschnitten
        return antwort
    monkeypatch.setattr(zeiten_pdf, "call_ki", _call_ki)


def test_pdf_wird_zur_tabelle_und_nichts_wird_gespeichert(
        client, db_session, test_user, monkeypatch):
    aufrufe = []
    _ki_antwortet(monkeypatch, "```json\n" + json.dumps({
        "spalten": ["Datum", "Zeit", "Zeit", ""],
        "zeilen": [["03.08.2026", "07:30", "12:00", "Wartung"],
                   ["", "", "", ""],
                   ["04.08.2026", "08:00"]],
        "hinweise": ["Zeile 2 handschriftlich korrigiert"],
    }) + "\n```", aufrufe=aufrufe)

    resp = _pdf_hochladen(client, _kopf(client))
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    # Doppelte und leere Spaltennamen werden eindeutig gemacht
    assert daten["spalten"] == ["Datum", "Zeit", "Zeit (2)", "Spalte 4"]
    assert daten["zeilen"][0] == {"Datum": "03.08.2026", "Zeit": "07:30",
                                  "Zeit (2)": "12:00", "Spalte 4": "Wartung"}
    assert len(daten["zeilen"]) == 2                       # Leerzeile entfällt
    assert any("Spaltenzahl" in h for h in daten["hinweise"])
    assert aufrufe[0]["dokumente"][0][0].startswith(b"%PDF")
    assert db_session.query(TimeEntry).count() == 0


def test_abgeschnittene_ki_antwort_wird_nicht_uebernommen(client, test_user, monkeypatch):
    _ki_antwortet(monkeypatch, '{"spalten": ["Datum"], "zeilen": [["03.08.', abgeschnitten=True)
    resp = _pdf_hochladen(client, _kopf(client))
    assert resp.status_code == 422
    assert "aufteilen" in resp.json()["detail"]


def test_kein_pdf_und_unbrauchbare_antwort(client, test_user, monkeypatch):
    _ki_antwortet(monkeypatch, "Das ist leider keine Tabelle.")
    assert _pdf_hochladen(client, _kopf(client), b"PK\x03\x04 zip").status_code == 422
    resp = _pdf_hochladen(client, _kopf(client))
    assert resp.status_code == 422
    assert "nicht ausgewertet" in resp.json()["detail"]


def test_ki_bekommt_pdf_als_dokument(monkeypatch):
    """Beide Provider erhalten das PDF als Dokument, nicht als Bild."""
    from app.services import ki as ki_service
    gesendet = {}

    class _Antwort:
        status_code = 200
        text = ""
        def __init__(self, daten): self._d = daten
        def json(self): return self._d
        def raise_for_status(self): return None

    monkeypatch.setattr(ki_service, "decrypt_secret", lambda enc: "k")

    def _post(url, **kw):
        gesendet[url] = kw
        if "anthropic" in url:
            return _Antwort({"content": [{"type": "text", "text": "ok"}],
                             "stop_reason": "max_tokens"})
        return _Antwort({"choices": [{"message": {"content": "ok"},
                                      "finish_reason": "stop"}]})
    monkeypatch.setattr(ki_service.httpx, "post", _post)

    meta = {}
    ki_service.call_ki({"provider": "anthropic", "api_key_enc": "x", "model": "m"},
                       "p", dokumente=[(b"%PDF", "a.pdf")], timeout=170, meta=meta)
    kw = gesendet["https://api.anthropic.com/v1/messages"]
    assert kw["json"]["messages"][0]["content"][0]["type"] == "document"
    assert kw["timeout"] == 170
    assert meta["abgeschnitten"] is True

    meta = {}
    ki_service.call_ki({"provider": "openai", "api_key_enc": "x", "model": "m"},
                       "p", dokumente=[(b"%PDF", "a.pdf")], meta=meta)
    teil = gesendet["https://api.openai.com/v1/chat/completions"]["json"]["messages"][0]["content"][0]
    assert teil["type"] == "file"
    assert teil["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert meta["abgeschnitten"] is False
