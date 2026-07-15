"""
Tests für das Modul Zeiterfassung: Stundenkonten & Projekt-Budgets.

Fachlogik:
- Stundenkonten sind vom Kunden im Voraus erworbene Stundenpakete je
  Projektzeit (EntityRecord vom Typ 'projektzeiten').
- Budget = Summe der Stundenkonten.
- Verbraucht wird das Budget NUR durch verrechenbare, abgeschlossene
  Zeiteinträge auf dem Projekt.
- exhausted=True → dem Kunden ein neues Stundenkonto anbieten
  (Erfassung bleibt möglich, Restwert kann negativ werden).
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.masterdata import EntityType, EntityRecord


# ── Hilfen ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def projektzeit(db_session):
    """Legt Stammdaten-Typ 'projektzeiten' + eine Projektzeit an."""
    typ = EntityType(name="Projektzeiten", slug="projektzeiten")
    db_session.add(typ)
    db_session.flush()
    record = EntityRecord(entity_type_id=typ.id, data={"name": "WWIntern"},
                          display_name="WWIntern")
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def _create_entry(client, project_id, minutes, billable=True, pause=0):
    """Abgeschlossenen Zeiteintrag mit gegebener Brutto-Dauer anlegen."""
    start = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=minutes)
    resp = client.post("/api/zeiterfassung/entries", json={
        "project_id": str(project_id),
        "project_name": "WWIntern",
        "started_at": start.isoformat(),
        "ended_at": end.isoformat(),
        "pause_minutes": pause,
        "billable": billable,
        "data": {},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _budget(client, project_id):
    resp = client.get("/api/zeiterfassung/budgets",
                      params={"project_ids": str(project_id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    return body[0]


# ── Stundenkonten CRUD ────────────────────────────────────────────────────────

def test_stundenkonto_anlegen_und_listen(auth_client, projektzeit):
    resp = auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"bezeichnung": "Stundenpaket 10h", "stunden": 10,
              "preis": 950, "erworben_am": "2026-07-01"},
    )
    assert resp.status_code == 200, resp.text
    konto = resp.json()
    assert konto["project_id"] == str(projektzeit.id)
    assert float(konto["stunden"]) == 10.0

    resp = auth_client.get(f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_stundenkonto_unbekannte_projektzeit(auth_client, projektzeit):
    resp = auth_client.post(
        "/api/zeiterfassung/projekte/00000000-0000-0000-0000-000000000000/stundenkonten",
        json={"stunden": 5, "erworben_am": "2026-07-01"},
    )
    assert resp.status_code == 404


def test_stundenkonto_ungueltige_stunden(auth_client, projektzeit):
    resp = auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 0, "erworben_am": "2026-07-01"},
    )
    assert resp.status_code == 422  # stunden muss > 0 sein


def test_stundenkonto_loeschen(auth_client, projektzeit, admin_user):
    """Löschen ist Admin-Sache (vom Kunden erworbene Pakete) —
    normale Benutzer bekommen 403 (Regel seit Bugfix Datenzusammenhänge)."""
    from tests.conftest import TEST_USER_PASSWORD

    resp = auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 5, "erworben_am": "2026-07-01"},
    )
    konto_id = resp.json()["id"]

    # Normaler Benutzer: verboten
    resp = auth_client.delete(f"/api/zeiterfassung/stundenkonten/{konto_id}")
    assert resp.status_code == 403

    # Admin: erlaubt
    login = auth_client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": TEST_USER_PASSWORD},
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = auth_client.delete(f"/api/zeiterfassung/stundenkonten/{konto_id}",
                              headers=admin_headers)
    assert resp.status_code == 200
    resp = auth_client.get(f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten")
    assert resp.json() == []


# ── Budget-Berechnung ─────────────────────────────────────────────────────────

def test_budget_ohne_stundenkonto(auth_client, projektzeit):
    """Ohne Stundenkonten wird kein Budget geführt."""
    b = _budget(auth_client, projektzeit.id)
    assert b["has_budget"] is False
    assert b["exhausted"] is False
    assert b["budget_minutes"] == 0


def test_budget_restwert(auth_client, projektzeit):
    """Budget 2h, 90 min verrechenbar verbraucht → Rest 30 min."""
    auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 2, "erworben_am": "2026-07-01"},
    )
    _create_entry(auth_client, projektzeit.id, minutes=90, billable=True)

    b = _budget(auth_client, projektzeit.id)
    assert b["has_budget"] is True
    assert b["budget_minutes"] == 120
    assert b["consumed_minutes"] == 90
    assert b["remaining_minutes"] == 30
    assert b["exhausted"] is False


def test_budget_nur_verrechenbare_zaehlen(auth_client, projektzeit):
    """Nicht verrechenbare Einträge zehren das Budget nicht auf."""
    auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 1, "erworben_am": "2026-07-01"},
    )
    _create_entry(auth_client, projektzeit.id, minutes=45, billable=False)

    b = _budget(auth_client, projektzeit.id)
    assert b["consumed_minutes"] == 0
    assert b["remaining_minutes"] == 60
    assert b["exhausted"] is False


def test_budget_pause_wird_abgezogen(auth_client, projektzeit):
    """Pausen zählen nicht als Verbrauch (Netto-Dauer)."""
    auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 1, "erworben_am": "2026-07-01"},
    )
    _create_entry(auth_client, projektzeit.id, minutes=60, billable=True, pause=20)

    b = _budget(auth_client, projektzeit.id)
    assert b["consumed_minutes"] == 40
    assert b["remaining_minutes"] == 20


def test_budget_verbraucht(auth_client, projektzeit):
    """Verbrauch >= Budget → exhausted, Rest negativ (Erfassung bleibt möglich)."""
    auth_client.post(
        f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
        json={"stunden": 1, "erworben_am": "2026-07-01"},
    )
    _create_entry(auth_client, projektzeit.id, minutes=90, billable=True)

    b = _budget(auth_client, projektzeit.id)
    assert b["exhausted"] is True
    assert b["remaining_minutes"] == -30

    # Erfassung ist weiterhin möglich (Warnung statt Blockade)
    entry = _create_entry(auth_client, projektzeit.id, minutes=30, billable=True)
    assert entry["duration_minutes"] == 30


def test_budget_mehrere_stundenkonten(auth_client, projektzeit):
    """Nachkauf: mehrere Konten summieren sich zum Budget."""
    for stunden in (1, 2):
        auth_client.post(
            f"/api/zeiterfassung/projekte/{projektzeit.id}/stundenkonten",
            json={"stunden": stunden, "erworben_am": "2026-07-01"},
        )
    b = _budget(auth_client, projektzeit.id)
    assert b["budget_minutes"] == 180
    assert b["konten_count"] == 2


def test_budgets_mehrere_projekte_und_ungueltige_id(auth_client, projektzeit):
    resp = auth_client.get("/api/zeiterfassung/budgets",
                           params={"project_ids": "keine-uuid"})
    assert resp.status_code == 400

    resp = auth_client.get(
        "/api/zeiterfassung/budgets",
        params={"project_ids": f"{projektzeit.id},00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── KI: Projektzeit per Sprache nachtragen ────────────────────────────────────

def test_ki_nachtragen_projekt_gefunden(auth_client, projektzeit, monkeypatch):
    """Die KI matcht eine bestehende Projektzeit → Vorschlag mit Stammdaten-Daten."""
    import json
    import app.api.zeiterfassung as api_mod

    ki_antwort = json.dumps({
        "matched_project_id": str(projektzeit.id),
        "spoken_project_name": "WW Intern",
        "spoken_contact_name": None,
        "date": "2026-07-14", "end_date": None,
        "start_time": "13:28", "end_time": "14:05",
        "pause_minutes": 0,
        "note": "Online Meeting zum Thema Datenmigration",
        "billable": True,
        "warnings": [],
    })
    monkeypatch.setattr(api_mod, "call_ki", lambda ki, prompt, **kw: ki_antwort)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "Projektzeit nachtragen bei WWIntern …"})
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert v["project_id"] == str(projektzeit.id)
    assert v["project_name"] == "WWIntern"      # Name aus Stammdaten, nicht gesprochener
    assert v["start_time"] == "13:28"
    assert v["end_time"] == "14:05"
    assert v["note"] == "Online Meeting zum Thema Datenmigration"
    assert v["warnings"] == []


def test_ki_nachtragen_projekt_nicht_gefunden(auth_client, projektzeit, monkeypatch):
    """Unbekannte Projektzeit → keine ID, aber Warnung für den Benutzer."""
    import json
    import app.api.zeiterfassung as api_mod

    ki_antwort = json.dumps({
        "matched_project_id": None,
        "spoken_project_name": "Eurofib",
        "spoken_contact_name": "Keplinger",
        "date": "2026-07-13", "end_date": None,
        "start_time": "13:28", "end_time": "14:05",
        "pause_minutes": 0, "note": None, "billable": True,
        "warnings": [],
    })
    monkeypatch.setattr(api_mod, "call_ki", lambda ki, prompt, **kw: ki_antwort)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "… beim Kunden Keplinger zum Projekt Eurofib …"})
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert v["project_id"] is None
    assert v["project_name"] == "Eurofib"
    assert v["contact_name"] == "Keplinger"
    assert any("nicht gefunden" in w for w in v["warnings"])


def test_ki_nachtragen_unsicherer_match_wird_verworfen(auth_client, projektzeit, monkeypatch):
    """Gesprochener Name passt nicht zum gematchten Projekt → keine Vorauswahl,
    gesprochener Name bleibt als Suchbegriff, Warnung für den Benutzer."""
    import json
    import app.api.zeiterfassung as api_mod

    # KI matcht fälschlich 'WWIntern', obwohl 'EuroFit' gesprochen wurde
    ki_antwort = json.dumps({
        "matched_project_id": str(projektzeit.id),
        "spoken_project_name": "EuroFit",
        "spoken_contact_name": "Keplinger",
        "date": "2026-07-14", "end_date": None,
        "start_time": "17:30", "end_time": "18:25",
        "pause_minutes": 0, "note": None, "billable": True,
        "warnings": [],
    })
    monkeypatch.setattr(api_mod, "call_ki", lambda ki, prompt, **kw: ki_antwort)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "… zum Projekt EuroFit …"})
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert v["project_id"] is None                    # keine falsche Vorauswahl
    assert v["project_name"] == "EuroFit"             # gesprochener Name als Suchbegriff
    assert v["contact_name"] == "Keplinger"
    assert any("nicht sicher" in w for w in v["warnings"])


def test_ki_nachtragen_aehnlicher_name_bleibt_gematcht(auth_client, projektzeit, monkeypatch):
    """Leichte Abweichungen (Transkription/Schreibweise) bleiben gematcht."""
    import json
    import app.api.zeiterfassung as api_mod

    ki_antwort = json.dumps({
        "matched_project_id": str(projektzeit.id),
        "spoken_project_name": "WW Intern",   # ~ 'WWIntern'
        "spoken_contact_name": None,
        "date": None, "end_date": None, "start_time": None, "end_time": None,
        "pause_minutes": 0, "note": None, "billable": True, "warnings": [],
    })
    monkeypatch.setattr(api_mod, "call_ki", lambda ki, prompt, **kw: ki_antwort)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "… bei WW Intern …"})
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert v["project_id"] == str(projektzeit.id)
    assert v["warnings"] == []


def test_ki_nachtragen_markdown_codeblock(auth_client, projektzeit, monkeypatch):
    """KI-Antworten in ```json-Codeblöcken werden toleriert."""
    import app.api.zeiterfassung as api_mod

    ki_antwort = ('```json\n{"matched_project_id": null, "spoken_project_name": null,'
                  ' "spoken_contact_name": null, "date": null, "end_date": null,'
                  ' "start_time": null, "end_time": null, "pause_minutes": 0,'
                  ' "note": "Test", "billable": false, "warnings": []}\n```')
    monkeypatch.setattr(api_mod, "call_ki", lambda ki, prompt, **kw: ki_antwort)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "irgendein Transkript"})
    assert resp.status_code == 200, resp.text
    v = resp.json()
    assert v["note"] == "Test"
    assert v["billable"] is False


def test_ki_nachtragen_ki_fehler(auth_client, projektzeit, monkeypatch):
    """Fehler des KI-Providers (z.B. kein API-Key) → verständlicher 502."""
    import app.api.zeiterfassung as api_mod

    def _raise(ki, prompt, **kw):
        raise RuntimeError("Kein KI-API-Key konfiguriert")
    monkeypatch.setattr(api_mod, "call_ki", _raise)

    resp = auth_client.post("/api/zeiterfassung/ki-nachtragen",
                            json={"transcript": "irgendein Transkript"})
    assert resp.status_code == 502
    assert "API-Key" in resp.json()["detail"]
