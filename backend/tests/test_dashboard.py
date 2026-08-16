"""
Tests für das Dashboard-Modul:

1) Persönliche Dashboard-Konfiguration je Benutzer
   (GET/PUT /api/users/me/dashboard, JSONB am User)
2) Aufgaben-Statistik fürs Dashboard-Widget
   (GET /api/aufgaben/stats: offen/heute fällig/überfällig + nächste)
3) Datacenter-Statistik fürs Dashboard-Widget
   (GET /api/datacenter/stats: Gesamt, Neuzugänge, neueste Dateien)
4) Gesammelte Kennzahlen (GET /api/dashboard/kennzahlen)
   Ein Aufruf statt bis zu 13; Auswahl je Baustein, Rechteprüfung,
   Finanz-Kennzahlen als SQL-Aggregat.
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


# ── 4) Gesammelte Kennzahlen ──────────────────────────────────────────────────
# Der Endpunkt ersetzt die früheren Einzelanfragen des Dashboards. Wichtig ist
# dreierlei: die Auswahl je Baustein greift, fehlende Modulrechte lassen den
# Aufruf nicht scheitern, und die Finanzwerte stimmen.

def _rechnung(db, *, status, total="1200.00", due_date=None, paid_at=None,
              zahlungen=()):
    """Legt eine Rechnung direkt in der DB an (schneller als über die API).

    `zahlungen` ist eine Liste von (Betrag, Datum)-Paaren.
    """
    from decimal import Decimal
    from app.models.invoice import Invoice, InvoicePayment

    inv = Invoice(
        doc_type="rechnung",
        date=date(2026, 7, 6),
        due_date=due_date,
        subtotal=Decimal(total), tax_total=Decimal("0"), total=Decimal(total),
        currency="EUR", status=status, paid_at=paid_at,
        is_recurring_template=False,
    )
    db.add(inv)
    db.flush()
    for betrag, tag in zahlungen:
        db.add(InvoicePayment(invoice_id=inv.id, paid_at=tag,
                              amount=Decimal(str(betrag))))
    db.commit()
    db.refresh(inv)
    return inv


def _kennzahlen(auth_client, bausteine=None):
    params = {"bausteine": ",".join(bausteine)} if bausteine else {}
    resp = auth_client.get("/api/dashboard/kennzahlen", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["kennzahlen"]


def test_kennzahlen_ohne_token_abgelehnt(client):
    assert client.get("/api/dashboard/kennzahlen").status_code in (401, 403)


def test_kennzahlen_auswahl_wird_beachtet(auth_client):
    """Nur die angefragten Bausteine stehen in der Antwort."""
    daten = _kennzahlen(auth_client, ["aufgaben"])
    assert "aufgaben" in daten
    assert "rechnungen" not in daten
    assert "projekte" not in daten


def test_kennzahlen_ohne_auswahl_liefert_alles(auth_client):
    """Ohne Parameter kommen alle Bausteine, die der Benutzer sehen darf."""
    daten = _kennzahlen(auth_client)
    # test_user ist kein Admin -> Admin-Bausteine fehlen, der Rest ist da
    assert {"aufgaben", "zeiterfassung", "rechnungen", "projekte",
            "datacenter"} <= set(daten)


def test_kennzahlen_unbekannter_baustein_wird_ignoriert(auth_client):
    """Ein Tippfehler im Parameter darf keinen Fehler auslösen."""
    daten = _kennzahlen(auth_client, ["gibt_es_nicht", "aufgaben"])
    assert "gibt_es_nicht" not in daten
    assert "aufgaben" in daten


def test_kennzahlen_statische_bausteine_liefern_nichts(auth_client):
    """Kacheln ohne Serverdaten sind kein Fehler, liefern aber auch nichts."""
    daten = _kennzahlen(auth_client, ["berichte", "quick_access"])
    assert daten == {}


# ── Rechteprüfung ─────────────────────────────────────────────────────────────
def test_kennzahlen_ohne_modul_wird_weggelassen(auth_client, test_user, db_session):
    """Fehlt ein Modul, fehlt der Baustein — der Aufruf bleibt trotzdem 200.

    Ein 403 für den gesamten Aufruf würde bedeuten, dass eine einzige
    gesperrte Kachel das ganze Dashboard leer lässt.
    """
    test_user.allowed_modules = ["dashboard", "aufgaben"]
    db_session.commit()

    daten = _kennzahlen(auth_client, ["aufgaben", "rechnungen", "projekte"])
    assert "aufgaben" in daten
    assert "rechnungen" not in daten
    assert "projekte" not in daten


def test_kennzahlen_ohne_dashboard_modul_abgelehnt(auth_client, test_user, db_session):
    """Das Grundrecht aufs Dashboard sperrt den Endpunkt komplett."""
    test_user.allowed_modules = ["aufgaben"]
    db_session.commit()
    assert auth_client.get("/api/dashboard/kennzahlen").status_code == 403


def test_kennzahlen_adminbausteine_nur_fuer_admins(auth_client):
    """Buchhaltung und Benutzer/System bleiben Nicht-Admins verborgen."""
    daten = _kennzahlen(auth_client, ["buchhaltung", "benutzer_system"])
    assert daten == {}


# ── Finanz-Kennzahlen ─────────────────────────────────────────────────────────
def test_finanzen_zaehlt_alle_unbeglichenen(auth_client, db_session):
    """gesendet, offen und teilbezahlt gelten als offen (Beschluss 15.08.2026).

    Vorher zählte das Dashboard nur den Status 'offen' und wies gesendete
    sowie teilbezahlte Rechnungen gar nicht aus.
    """
    morgen = date.today() + timedelta(days=10)
    _rechnung(db_session, status="offen",       total="100.00", due_date=morgen)
    _rechnung(db_session, status="gesendet",    total="200.00", due_date=morgen)
    _rechnung(db_session, status="teilbezahlt", total="300.00", due_date=morgen,
              zahlungen=[("100.00", date.today())])
    # Zählt nicht mit:
    _rechnung(db_session, status="entwurf",   total="999.00")
    _rechnung(db_session, status="storniert", total="888.00")

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"]["count"] == 3
    # 100 + 200 + (300 - 100 bereits gezahlt) = 500
    assert finanzen["offen"]["sum"] == 500.00


def test_finanzen_teilzahlung_mindert_den_betrag(auth_client, db_session):
    """Ausgewiesen wird der Restbetrag, nicht die Bruttosumme."""
    _rechnung(db_session, status="teilbezahlt", total="1000.00",
              due_date=date.today() + timedelta(days=5),
              zahlungen=[("400.00", date.today()), ("100.00", date.today())])

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"]["sum"] == 500.00      # 1000 - 400 - 100


def test_finanzen_ueberfaellig_getrennt_von_offen(auth_client, db_session):
    """Überfällige zählen nur in ihrer eigenen Gruppe — die Zeilen der Kachel
    sollen sich wie bisher zur Gesamtzahl addieren."""
    gestern = date.today() - timedelta(days=1)
    morgen  = date.today() + timedelta(days=10)
    _rechnung(db_session, status="offen", total="100.00", due_date=morgen)
    _rechnung(db_session, status="offen", total="700.00", due_date=gestern)

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"]["count"] == 1
    assert finanzen["offen"]["sum"] == 100.00
    assert finanzen["ueberfaellig"]["count"] == 1
    assert finanzen["ueberfaellig"]["sum"] == 700.00


def test_finanzen_ueberfaellig_unabhaengig_vom_status(auth_client, db_session):
    """Der Status 'ueberfaellig' wird von einem täglichen Lauf gesetzt und kann
    hinterherhinken — gerechnet wird deshalb aus dem Zahlungsziel."""
    gestern = date.today() - timedelta(days=1)
    # Status sagt noch 'offen', das Zahlungsziel ist aber überschritten
    _rechnung(db_session, status="offen", total="500.00", due_date=gestern)

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["ueberfaellig"]["count"] == 1
    assert finanzen["offen"]["count"] == 0


def test_finanzen_ohne_zahlungsziel_nicht_ueberfaellig(auth_client, db_session):
    _rechnung(db_session, status="offen", total="400.00", due_date=None)
    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"]["count"] == 1
    assert finanzen["ueberfaellig"]["count"] == 0


def test_finanzen_bezahlt_im_monat(auth_client, db_session):
    """Nur im laufenden Monat beglichene Rechnungen; hier zählt die volle Summe."""
    heute = date.today()
    monatsbeginn = heute.replace(day=1)
    vormonat = monatsbeginn - timedelta(days=1)

    _rechnung(db_session, status="bezahlt", total="250.00", paid_at=heute)
    _rechnung(db_session, status="bezahlt", total="150.00", paid_at=monatsbeginn)
    _rechnung(db_session, status="bezahlt", total="900.00", paid_at=vormonat)

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["bezahlt_monat"]["count"] == 2
    assert finanzen["bezahlt_monat"]["sum"] == 400.00


def test_finanzen_leer(auth_client):
    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"] == {"count": 0, "sum": 0.0}
    assert finanzen["ueberfaellig"] == {"count": 0, "sum": 0.0}
    assert finanzen["bezahlt_monat"] == {"count": 0, "sum": 0.0}


def test_finanzen_ignoriert_wiederkehrende_vorlagen(auth_client, db_session):
    """Vorlagen für wiederkehrende Belege sind keine Forderung."""
    from app.models.invoice import Invoice
    inv = _rechnung(db_session, status="offen", total="777.00",
                    due_date=date.today() + timedelta(days=5))
    inv.is_recurring_template = True
    db_session.commit()

    finanzen = _kennzahlen(auth_client, ["rechnungen"])["rechnungen"]
    assert finanzen["offen"]["count"] == 0


# ── Übereinstimmung mit den bestehenden Endpunkten ───────────────────────────
def test_kennzahlen_aufgaben_gleich_wie_stats(auth_client):
    """Sammelaufruf und /aufgaben/stats müssen dasselbe sagen.

    Genau dafür ruft services/dashboard.py die vorhandene Funktion auf, statt
    die Zählung nachzubauen: zwei Kopien liefen sonst irgendwann auseinander,
    und ein Dashboard mit falschen Zahlen meldet niemand als Fehler.
    """
    heute = date.today()
    _neue_aufgabe(auth_client, "Überfällig", due=heute - timedelta(days=1))
    _neue_aufgabe(auth_client, "Heute", due=heute)
    _neue_aufgabe(auth_client, "Ohne Termin")

    direkt = auth_client.get("/api/aufgaben/stats", params={"limit": 4}).json()
    ueber_dashboard = _kennzahlen(auth_client, ["aufgaben"])["aufgaben"]["stats"]

    assert ueber_dashboard["offen_gesamt"] == direkt["offen_gesamt"]
    assert ueber_dashboard["ueberfaellig"] == direkt["ueberfaellig"]
    assert ueber_dashboard["heute_faellig"] == direkt["heute_faellig"]


def test_kennzahlen_datacenter_gleich_wie_stats(auth_client, db_session):
    import uuid
    from app.models.attachment import Attachment
    db_session.add(Attachment(entity_type="kontakt", entity_id=uuid.uuid4(),
                              type="link", display_name="Datei",
                              link_url="https://example.com"))
    db_session.commit()

    direkt = auth_client.get("/api/datacenter/stats").json()
    ueber_dashboard = _kennzahlen(auth_client, ["datacenter"])["datacenter"]
    assert ueber_dashboard["gesamt"] == direkt["gesamt"]


def test_kennzahlen_system_ohne_updatepruefung(auth_client, admin_user, db_session):
    """Die Systemkachel liefert die lokale Version, aber keine Update-Info.

    Die Update-Prüfung fragt GitHub ab (5 s Timeout, notfalls git fetch mit
    10 s) — im Sammelaufruf hinge daran das ganze Dashboard. Das Frontend holt
    sie deshalb weiterhin getrennt nach.
    """
    from tests.conftest import TEST_USER_PASSWORD
    resp = auth_client.post("/api/auth/login",
                            json={"email": admin_user.email,
                                  "password": TEST_USER_PASSWORD})
    token = resp.json()["access_token"]
    auth_client.headers.update({"Authorization": f"Bearer {token}"})

    daten = _kennzahlen(auth_client, ["benutzer_system"])["benutzer_system"]
    assert daten["benutzer_gesamt"] >= 1
    assert daten["version"]
    assert "update_available" not in daten
