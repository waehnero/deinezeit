"""
Tests für das Dashboard-Modul:

1) Persönliche Dashboard-Konfiguration je Benutzer
   (GET/PUT /api/users/me/dashboard, JSONB am User)
2) Aufgaben-Statistik fürs Dashboard-Widget
   (GET /api/aufgaben/stats: offen/heute fällig/überfällig + nächste)
3) Datacenter-Statistik fürs Dashboard-Widget
   (GET /api/datacenter/stats: Gesamt, Neuzugänge, neueste Dateien)
"""
from datetime import date, timedelta


# ── 1) Dashboard-Konfiguration ────────────────────────────────────────────────
def test_dashboard_config_ohne_token_abgelehnt(client):
    assert client.get("/api/users/me/dashboard").status_code in (401, 403)


def test_dashboard_config_initial_leer(auth_client):
    resp = auth_client.get("/api/users/me/dashboard")
    assert resp.status_code == 200
    assert resp.json()["config"] is None


def test_dashboard_config_speichern_und_lesen(auth_client):
    config = {
        "widgets": [
            {"id": "widget_zeit", "type": "zeiterfassung", "size": 2, "hidden": False},
            {"id": "widget_aufgaben", "type": "aufgaben", "size": 2, "hidden": True},
        ]
    }
    resp = auth_client.put("/api/users/me/dashboard", json={"config": config})
    assert resp.status_code == 200
    assert resp.json()["config"] == config

    # Persistiert?
    resp = auth_client.get("/api/users/me/dashboard")
    assert resp.status_code == 200
    assert resp.json()["config"] == config


def test_dashboard_config_zuruecksetzen(auth_client):
    auth_client.put("/api/users/me/dashboard",
                    json={"config": {"widgets": [{"id": "w", "type": "x", "size": 1}]}})
    resp = auth_client.put("/api/users/me/dashboard", json={"config": None})
    assert resp.status_code == 200
    assert resp.json()["config"] is None
    assert auth_client.get("/api/users/me/dashboard").json()["config"] is None


# ── 1b) Konfiguration Format v2 (mehrere Ansichten) ───────────────────────────
def _config_v2(layouts=None):
    """Minimale, gültige v2-Konfiguration."""
    return {
        "version": 2,
        "aktivesLayout": "standard",
        "bekannt": {"typen": ["zeiterfassung"], "slugs": []},
        "layouts": layouts or [
            {
                "id": "standard",
                "name": "Standard",
                "widgets": [
                    {"id": "w_zeit_ab12", "type": "zeiterfassung", "size": 2},
                    {"id": "w_aufg_cd34", "type": "aufgaben", "size": 2,
                     "titel": "Meine Aufgaben"},
                ],
            },
        ],
    }


def test_dashboard_v2_speichern_und_lesen(auth_client):
    """v2 wird unverändert gespeichert — inklusive eigener Kachelüberschrift."""
    config = _config_v2()
    resp = auth_client.put("/api/users/me/dashboard", json={"config": config})
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"] == config

    gelesen = auth_client.get("/api/users/me/dashboard").json()["config"]
    assert gelesen == config
    assert gelesen["layouts"][0]["widgets"][1]["titel"] == "Meine Aufgaben"


def test_dashboard_v2_mehrere_ansichten(auth_client):
    """Zweite Ansicht mit eigener Kachelauswahl bleibt getrennt erhalten."""
    config = _config_v2(layouts=[
        {"id": "standard", "name": "Standard",
         "widgets": [{"id": "w1", "type": "zeiterfassung", "size": 2}]},
        {"id": "layout_xy99", "name": "Unterwegs",
         "widgets": [{"id": "w2", "type": "aufgaben", "size": 4}]},
    ])
    config["aktivesLayout"] = "layout_xy99"

    resp = auth_client.put("/api/users/me/dashboard", json={"config": config})
    assert resp.status_code == 200, resp.text

    gelesen = auth_client.get("/api/users/me/dashboard").json()["config"]
    assert [l["name"] for l in gelesen["layouts"]] == ["Standard", "Unterwegs"]
    assert gelesen["aktivesLayout"] == "layout_xy99"
    # Die Ansichten teilen sich keine Bausteine
    assert gelesen["layouts"][0]["widgets"][0]["type"] == "zeiterfassung"
    assert gelesen["layouts"][1]["widgets"][0]["type"] == "aufgaben"


def test_dashboard_v1_wird_weiter_angenommen(auth_client):
    """Ein Client mit altem Stand darf weiterhin schreiben (PWA-Cache)."""
    alt = {"widgets": [{"id": "widget_zeit", "type": "zeiterfassung",
                        "size": 2, "hidden": False}]}
    resp = auth_client.put("/api/users/me/dashboard", json={"config": alt})
    assert resp.status_code == 200
    assert resp.json()["config"] == alt


def test_dashboard_config_je_benutzer_getrennt(auth_client, admin_user, db_session):
    """Die Konfiguration hängt am Benutzer, nicht global an der Installation."""
    auth_client.put("/api/users/me/dashboard", json={"config": _config_v2()})

    # Der zweite Benutzer hat davon nichts
    db_session.refresh(admin_user)
    assert admin_user.dashboard_config is None


# ── 1c) Validierung: kaputte Konfigurationen werden abgewiesen ────────────────
def test_dashboard_v2_ohne_layouts_abgelehnt(auth_client):
    resp = auth_client.put("/api/users/me/dashboard",
                           json={"config": {"version": 2, "layouts": []}})
    assert resp.status_code == 422


def test_dashboard_v2_ansicht_ohne_id_abgelehnt(auth_client):
    kaputt = _config_v2(layouts=[{"name": "Ohne Id", "widgets": []}])
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_v2_baustein_ohne_typ_abgelehnt(auth_client):
    kaputt = _config_v2(layouts=[
        {"id": "standard", "name": "Standard", "widgets": [{"id": "w1", "size": 2}]},
    ])
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_v2_ungueltige_groesse_abgelehnt(auth_client):
    kaputt = _config_v2(layouts=[
        {"id": "standard", "name": "Standard",
         "widgets": [{"id": "w1", "type": "aufgaben", "size": 99}]},
    ])
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_v2_aktives_layout_muss_existieren(auth_client):
    kaputt = _config_v2()
    kaputt["aktivesLayout"] = "gibt_es_nicht"
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_zu_viele_ansichten_abgelehnt(auth_client):
    kaputt = _config_v2(layouts=[
        {"id": f"l{i}", "name": f"Ansicht {i}", "widgets": []} for i in range(6)
    ])
    kaputt["aktivesLayout"] = "l0"
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_zu_langer_titel_abgelehnt(auth_client):
    kaputt = _config_v2(layouts=[
        {"id": "standard", "name": "Standard",
         "widgets": [{"id": "w1", "type": "aufgaben", "size": 2, "titel": "x" * 41}]},
    ])
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": kaputt}).status_code == 422


def test_dashboard_unbekanntes_format_abgelehnt(auth_client):
    assert auth_client.put("/api/users/me/dashboard",
                           json={"config": {"irgendwas": True}}).status_code == 422


# ── 2) Aufgaben-Statistik ─────────────────────────────────────────────────────
def _neue_aufgabe(auth_client, titel, due=None, status="offen"):
    payload = {"title": titel, "status": status}
    if due:
        payload["due_date"] = due.isoformat()
    resp = auth_client.post("/api/aufgaben/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_aufgaben_stats_ohne_token_abgelehnt(client):
    assert client.get("/api/aufgaben/stats").status_code in (401, 403)


def test_aufgaben_stats_leer(auth_client):
    resp = auth_client.get("/api/aufgaben/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["offen_gesamt"] == 0
    assert data["heute_faellig"] == 0
    assert data["ueberfaellig"] == 0
    assert data["naechste"] == []


def test_aufgaben_stats_zaehlt_richtig(auth_client):
    heute = date.today()
    _neue_aufgabe(auth_client, "Überfällige Aufgabe", due=heute - timedelta(days=2))
    _neue_aufgabe(auth_client, "Heute fällig", due=heute)
    _neue_aufgabe(auth_client, "Ohne Termin")
    _neue_aufgabe(auth_client, "Schon erledigt", due=heute, status="erledigt")

    resp = auth_client.get("/api/aufgaben/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["offen_gesamt"] == 3          # erledigte zählt nicht
    assert data["heute_faellig"] == 1
    assert data["ueberfaellig"] == 1

    # Reihung: überfällig zuerst, ohne Termin zuletzt
    titel = [a["title"] for a in data["naechste"]]
    assert titel[0] == "Überfällige Aufgabe"
    assert titel[-1] == "Ohne Termin"
    assert data["naechste"][0]["ueberfaellig"] is True


def test_aufgaben_stats_limit(auth_client):
    for i in range(4):
        _neue_aufgabe(auth_client, f"Aufgabe {i}", due=date.today() + timedelta(days=i))
    resp = auth_client.get("/api/aufgaben/stats", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["naechste"]) == 2


def test_aufgaben_stats_mine_filter(auth_client, admin_user, db_session):
    """mine=true liefert nur eigene (zugewiesene/erstellte) Aufgaben."""
    _neue_aufgabe(auth_client, "Meine Aufgabe")

    # Aufgabe eines anderen (echten) Benutzers direkt in der DB anlegen —
    # created_by hat einen Fremdschlüssel auf users, daher admin_user-Fixture.
    from app.models.aufgaben import Todo
    fremde = Todo(title="Fremde Aufgabe", status="offen", priority="mittel",
                  created_by=admin_user.id, data={})
    db_session.add(fremde)
    db_session.commit()

    alle = auth_client.get("/api/aufgaben/stats").json()
    meine = auth_client.get("/api/aufgaben/stats", params={"mine": True}).json()
    assert alle["offen_gesamt"] == 2
    assert meine["offen_gesamt"] == 1
    assert meine["naechste"][0]["title"] == "Meine Aufgabe"


# ── 3) Datacenter-Statistik ───────────────────────────────────────────────────
def test_datacenter_stats_ohne_token_abgelehnt(client):
    assert client.get("/api/datacenter/stats").status_code in (401, 403)


def test_datacenter_stats_leer(auth_client):
    resp = auth_client.get("/api/datacenter/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gesamt"] == 0
    assert data["neu_7_tage"] == 0
    assert data["neueste"] == []


def test_datacenter_stats_zaehlt(auth_client, db_session):
    import uuid
    from datetime import datetime, timezone
    from app.models.attachment import Attachment

    alt = Attachment(entity_type="kontakt", entity_id=uuid.uuid4(), type="link",
                     display_name="Alte Datei", link_url="https://example.com")
    db_session.add(alt)
    db_session.commit()
    # created_at nachträglich auf vor 30 Tagen setzen (Default war "jetzt")
    alt.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db_session.add(Attachment(entity_type="kontakt", entity_id=uuid.uuid4(), type="link",
                              display_name="Neue Datei", link_url="https://example.com"))
    db_session.commit()

    resp = auth_client.get("/api/datacenter/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gesamt"] == 2
    assert data["neu_7_tage"] == 1
    # Neueste zuerst
    assert data["neueste"][0]["display_name"] == "Neue Datei"
