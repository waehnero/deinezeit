"""
Tests für die Berichte der Zeiterfassung (``/api/reports/zeiterfassung/...``).

Geprüft wird die Auswertung, die den Berichtsseiten unter
Zeiterfassung → Berichte zugrunde liegt:

- Summen je Benutzer und je Zeitprojekt (verrechenbar / nicht verrechenbar)
- Rundung je Eintrag (nicht auf die Summe!)
- Zeitraumgrenzen
- laufende Zeitgeber („Jetzt aktiv")

Bewusst wird das Ergebnis der Rechnung geprüft und nicht nur, dass ein Aufruf
200 liefert: Eine Auswertung, die antwortet, aber falsch rechnet, ist
schlimmer als eine, die gar nicht antwortet — der Fehler fällt erst auf der
Rechnung des Kunden auf.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.masterdata import EntityType, EntityRecord
from app.core.zeitprojekte import ZEITPROJEKTE_SLUG


BASIS = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)   # Montag


@pytest.fixture()
def zeitprojekt(db_session):
    """Stammdaten-Typ 'zeitprojekte' + ein Zeitprojekt."""
    typ = EntityType(name="Zeitprojekte", slug=ZEITPROJEKTE_SLUG)
    db_session.add(typ)
    db_session.flush()
    record = EntityRecord(entity_type_id=typ.id, data={"name": "Website"},
                          display_name="Website")
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def _eintrag(client, projekt, minuten, billable=True, versatz_stunden=0,
             name="Website", pause=0):
    start = BASIS + timedelta(hours=versatz_stunden)
    resp = client.post("/api/zeiterfassung/entries", json={
        "project_id": str(projekt.id),
        "project_name": name,
        "contact_name": "Musterkunde",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(minutes=minuten)).isoformat(),
        "pause_minutes": pause,
        "billable": billable,
        "data": {},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _uebersicht(client, **params):
    params.setdefault("date_from", "2026-07-01")
    params.setdefault("date_to", "2026-07-31")
    resp = client.get("/api/reports/zeiterfassung/uebersicht", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Summen ────────────────────────────────────────────────────────────────────

def test_summe_trennt_verrechenbar(auth_client, zeitprojekt):
    """Gesamt = verrechenbar + nicht verrechenbar, je Benutzer eine Zeile."""
    _eintrag(auth_client, zeitprojekt, 120, billable=True)
    _eintrag(auth_client, zeitprojekt, 60, billable=False, versatz_stunden=3)

    body = _uebersicht(auth_client, group_by="benutzer")

    assert len(body["zeilen"]) == 1
    zeile = body["zeilen"][0]
    assert zeile["minuten"] == 180
    assert zeile["verrechenbar_minuten"] == 120
    assert zeile["nicht_verrechenbar_minuten"] == 60
    assert zeile["dauer"] == "3:00"
    assert body["summe"]["minuten"] == 180
    assert body["summe"]["anteil_verrechenbar"] == 67   # 120/180


def test_gruppierung_nach_zeitprojekt(auth_client, zeitprojekt):
    """Nach Zeitprojekt gruppiert steht der Kontakt als Zusatz in der Zeile."""
    _eintrag(auth_client, zeitprojekt, 90)

    body = _uebersicht(auth_client, group_by="zeitprojekt")

    assert len(body["zeilen"]) == 1
    zeile = body["zeilen"][0]
    assert zeile["name"] == "Website"
    assert zeile["zusatz"] == "Musterkunde"
    assert zeile["minuten"] == 90
    # Ohne Stundenkonto: Feld vorhanden, aber ohne Budget
    assert zeile["budget"]["has_budget"] is False


def test_umbenanntes_zeitprojekt_bleibt_eine_zeile(auth_client, zeitprojekt):
    """Gruppiert wird nach Kennung, nicht nach Name.

    Der Projektname liegt denormalisiert im Zeiteintrag. Nach einer
    Umbenennung stehen für dasselbe Zeitprojekt zwei Namen in der Datenbank —
    die Auswertung darf daraus keine zwei Zeilen machen.
    """
    _eintrag(auth_client, zeitprojekt, 60, name="Website")
    _eintrag(auth_client, zeitprojekt, 30, name="Website neu", versatz_stunden=2)

    body = _uebersicht(auth_client, group_by="zeitprojekt")

    assert len(body["zeilen"]) == 1
    assert body["zeilen"][0]["minuten"] == 90


# ── Rundung ───────────────────────────────────────────────────────────────────

def test_rundung_gilt_je_eintrag(auth_client, zeitprojekt):
    """Gerundet wird jeder Eintrag einzeln, nicht die Summe.

    Drei Einträge à 10 min, Aufrundung auf 15:
      je Eintrag gerundet   → 3 × 15 = 45  (richtig, so rechnet auch das PDF)
      Summe gerundet        → 30 → 30      (falsch)
    Die beiden Wege liefern hier verschiedene Zahlen — genau deshalb taugt
    dieser Fall als Prüfung.
    """
    _eintrag(auth_client, zeitprojekt, 10)
    _eintrag(auth_client, zeitprojekt, 10, versatz_stunden=2)
    _eintrag(auth_client, zeitprojekt, 10, versatz_stunden=4)

    # je Eintrag: 3 × 15 = 45.  Auf die Summe gerundet wären es 30.
    body = _uebersicht(auth_client, group_by="benutzer", round_to=15, round_dir="up")
    assert body["summe"]["minuten"] == 45

    # ohne Rundung: 30
    body = _uebersicht(auth_client, group_by="benutzer")
    assert body["summe"]["minuten"] == 30


def test_abrunden(auth_client, zeitprojekt):
    _eintrag(auth_client, zeitprojekt, 100)
    body = _uebersicht(auth_client, group_by="benutzer", round_to=30, round_dir="down")
    assert body["summe"]["minuten"] == 90


# ── Zeitraum & Filter ─────────────────────────────────────────────────────────

def test_zeitraum_grenzt_ab(auth_client, zeitprojekt):
    """Ein Eintrag außerhalb des Zeitraums zählt nicht mit."""
    _eintrag(auth_client, zeitprojekt, 60)

    body = _uebersicht(auth_client, group_by="benutzer",
                       date_from="2026-08-01", date_to="2026-08-31")
    assert body["zeilen"] == []
    assert body["summe"]["minuten"] == 0


def test_zeitzone_der_grenzen_wird_beachtet(auth_client, zeitprojekt):
    """Grenzen mit Zeitzonen-Versatz meinen den Ortstag, nicht den UTC-Tag.

    Der Fall aus dem Betrieb (01.09.2026): Ein Eintrag am 1. September um
    01:15 Ortszeit (MESZ, UTC+2) liegt in UTC am 31. August um 23:15 — und
    erschien deshalb im August-Bericht. Wer den August auswertet, meint den
    österreichischen August.
    """
    start = datetime(2026, 8, 31, 23, 15, tzinfo=timezone.utc)   # = 01.09. 01:15 MESZ
    resp = auth_client.post("/api/zeiterfassung/entries", json={
        "project_id": str(zeitprojekt.id),
        "project_name": "Website",
        "started_at": start.isoformat(),
        "ended_at": (start + timedelta(minutes=60)).isoformat(),
        "pause_minutes": 0,
        "billable": True,
        "data": {},
    })
    assert resp.status_code == 200, resp.text

    # August in Ortszeit: der Eintrag gehört NICHT dazu
    august = _uebersicht(auth_client, group_by="benutzer",
                         date_from="2026-08-01T00:00:00+02:00",
                         date_to="2026-08-31T23:59:59+02:00")
    assert august["summe"]["minuten"] == 0

    # September in Ortszeit: hier gehört er hin
    september = _uebersicht(auth_client, group_by="benutzer",
                            date_from="2026-09-01T00:00:00+02:00",
                            date_to="2026-09-30T23:59:59+02:00")
    assert september["summe"]["minuten"] == 60


def test_datum_ohne_zeitzone_bleibt_zulaessig(auth_client, zeitprojekt):
    """Reine Datumsangaben (alte Lesezeichen, direkte Aufrufe) gehen weiter."""
    _eintrag(auth_client, zeitprojekt, 60)
    body = _uebersicht(auth_client, group_by="benutzer",
                       date_from="2026-07-01", date_to="2026-07-31")
    assert body["summe"]["minuten"] == 60


def test_filter_verrechenbar(auth_client, zeitprojekt):
    _eintrag(auth_client, zeitprojekt, 60, billable=True)
    _eintrag(auth_client, zeitprojekt, 45, billable=False, versatz_stunden=2)

    body = _uebersicht(auth_client, group_by="benutzer", billable="no")
    assert body["summe"]["minuten"] == 45


def test_ungueltige_gruppierung_wird_abgewiesen(auth_client):
    resp = auth_client.get("/api/reports/zeiterfassung/uebersicht", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31", "group_by": "quatsch",
    })
    assert resp.status_code == 400


def test_ungueltiges_datum_wird_abgewiesen(auth_client):
    resp = auth_client.get("/api/reports/zeiterfassung/uebersicht", params={
        "date_from": "01.07.2026", "date_to": "2026-07-31",
    })
    assert resp.status_code == 400


# ── Jetzt aktiv ───────────────────────────────────────────────────────────────

def test_laufender_zeitgeber_erscheint_unter_laufend(auth_client, zeitprojekt):
    """Ein gestarteter Timer zählt nicht in die Summen, aber in „Jetzt aktiv"."""
    resp = auth_client.post("/api/zeiterfassung/start", json={
        "project_id": str(zeitprojekt.id),
        "project_name": "Website",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "billable": True,
        "data": {},
    })
    assert resp.status_code == 200, resp.text

    body = _uebersicht(auth_client, group_by="benutzer",
                       date_from="2026-01-01", date_to="2030-12-31")
    assert body["summe"]["minuten"] == 0          # noch nicht abgeschlossen
    assert len(body["laufend"]) == 1
    assert body["laufend"][0]["zeitprojekt"] == "Website"


# ── Ausgabe: Gruppierung im Bericht ──────────────────────────────────────────

def test_bericht_gruppiert_nach_kunde(auth_client, zeitprojekt):
    """group_by=kontakt macht aus jedem Kunden einen eigenen Abschnitt.

    Geprüft wird die Struktur, nicht das bloße Vorkommen der Namen: Ein Name
    steht auch dann irgendwo im HTML, wenn die Gruppierung gar nicht greift
    (z.B. in einer Detailzeile). Aussagekräftig ist die Überschrift.
    """
    import re

    _eintrag(auth_client, zeitprojekt, 60, name="Website")
    resp = auth_client.post("/api/zeiterfassung/entries", json={
        "project_id": str(zeitprojekt.id),
        "project_name": "Wartung",
        "contact_name": "Zweiter Kunde",
        "started_at": (BASIS + timedelta(hours=4)).isoformat(),
        "ended_at": (BASIS + timedelta(hours=5)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {},
    })
    assert resp.status_code == 200, resp.text

    html = auth_client.get("/api/reports/zeiterfassung", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31",
        "group_by": "kontakt", "format": "html",
    })
    assert html.status_code == 200, html.text
    ueberschriften = re.findall(r"<h3>(.*?)</h3>", html.text)
    assert ueberschriften == ["Musterkunde", "Zweiter Kunde"]

    # Nach Zeitprojekt gruppiert heißen die Abschnitte anders — gleiche Daten,
    # andere Struktur. Ohne diese Gegenprobe würde der Test auch dann grün,
    # wenn group_by ignoriert wird.
    html2 = auth_client.get("/api/reports/zeiterfassung", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31",
        "group_by": "aufgabe", "format": "html",
    })
    assert re.findall(r"<h3>(.*?)</h3>", html2.text) == ["Wartung", "Website"]


def test_empfaengerblock_nur_bei_einem_kunden(auth_client, zeitprojekt):
    """Bei genau einem Kunden steht dessen Anschrift im Kopf, sonst nicht."""
    _eintrag(auth_client, zeitprojekt, 60)

    einer = auth_client.get("/api/reports/zeiterfassung", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31", "format": "html",
    })
    assert 'class="empfaenger"' in einer.text

    resp = auth_client.post("/api/zeiterfassung/entries", json={
        "project_id": str(zeitprojekt.id), "project_name": "Website",
        "contact_name": "Zweiter Kunde",
        "started_at": (BASIS + timedelta(hours=4)).isoformat(),
        "ended_at": (BASIS + timedelta(hours=5)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {},
    })
    assert resp.status_code == 200

    zwei = auth_client.get("/api/reports/zeiterfassung", params={
        "date_from": "2026-07-01", "date_to": "2026-07-31", "format": "html",
    })
    assert 'class="empfaenger"' not in zwei.text


# ── Auswahllisten der Filter ─────────────────────────────────────────────────

def test_auswahllisten(auth_client, zeitprojekt):
    _eintrag(auth_client, zeitprojekt, 30)

    tasks = auth_client.get("/api/reports/zeiterfassung/tasks")
    assert tasks.status_code == 200
    assert "Website" in tasks.json()["tasks"]

    kontakte = auth_client.get("/api/reports/zeiterfassung/contacts")
    assert kontakte.status_code == 200
    assert "Musterkunde" in kontakte.json()["contacts"]
