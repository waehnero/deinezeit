"""
Rechtegruppen: Vereinigungsmenge, Ausnahmen, Umfang (Migration 0055)
====================================================================

Der Schwerpunkt liegt auf den Stellen, an denen ein Rechtemodell still falsch
sein kann. Ein Test „Gruppe vergibt Recht, Benutzer hat Recht" fängt das
Wesentliche nicht: Fehler entstehen dort, wo mehrere Regeln zusammentreffen —
zwei Gruppen mit unterschiedlichem Umfang, eine Ausnahme gegen eine Gruppe,
ein Tippfehler in einem Rechtenamen. Ein zu großzügiges Ergebnis fällt im
Betrieb nicht auf, weil nichts kaputt aussieht.
"""
import pytest

from app.core import berechtigungen as B
from app.core.modules import MODULE_KEYS
from app.models.user import PermissionGroup, User
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _blatt(**module) -> dict:
    """Rechteblatt mit den genannten Abweichungen vom leeren Blatt."""
    blatt = B.leeres_rechteblatt()
    for modul, werte in module.items():
        blatt[modul].update(werte)
    return blatt


def _gruppe(db, name, rechte, ist_system=False) -> PermissionGroup:
    g = PermissionGroup(name=name, rechte=rechte, ist_system=ist_system)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _kopf(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD) -> dict:
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Zusammenrechnen der Gruppenrechte ────────────────────────────────────────

def test_rechte_mehrerer_gruppen_addieren_sich(db_session, test_user):
    test_user.groups = [
        _gruppe(db_session, "Zeit", _blatt(zeiterfassung={"lesen": True})),
        _gruppe(db_session, "Verkauf",
                _blatt(verkauf={"lesen": True, "schreiben": True})),
    ]
    db_session.commit()

    blatt = B.effektive_rechte(test_user)
    assert blatt["zeiterfassung"]["lesen"] is True
    assert blatt["verkauf"]["schreiben"] is True
    # Was keine Gruppe vergibt, darf nicht entstehen.
    assert blatt["verkauf"]["loeschen"] is False
    assert blatt["buchhaltung"]["lesen"] is False


def test_weiterer_umfang_gewinnt(db_session, test_user):
    """Eine Gruppe hinzuzufügen darf keine Rechte wegnehmen.

    Sonst wäre das Ergebnis von der Reihenfolge abhängig, und ein Administrator
    könnte nicht erklären, warum jemand nach dem Hinzufügen einer Gruppe
    *weniger* sieht.
    """
    test_user.groups = [
        _gruppe(db_session, "Eigene",
                _blatt(zeiterfassung={"lesen": True, "umfang": "eigene"})),
        _gruppe(db_session, "Alle",
                _blatt(zeiterfassung={"lesen": True, "umfang": "alle"})),
    ]
    db_session.commit()
    assert B.umfang(test_user, "zeiterfassung") == B.UMFANG_ALLE


def test_schreiben_zieht_lesen_nach(db_session, test_user):
    """Ändern ohne Ansehen ist keine sinnvolle Kombination."""
    test_user.groups = [_gruppe(db_session, "Nur schreiben",
                                _blatt(aufgaben={"schreiben": True}))]
    db_session.commit()
    assert B.effektive_rechte(test_user)["aufgaben"]["lesen"] is True


# ── Individuelle Ausnahmen ───────────────────────────────────────────────────

def test_ausnahme_entzieht_gegen_die_gruppe(db_session, test_user):
    """Ein Entzug muss stärker sein als jede Gruppenzugehörigkeit.

    Andernfalls kann man einem einzelnen Mitarbeiter nichts wegnehmen, ohne ihn
    aus der Gruppe zu werfen — und damit alles andere mit.
    """
    test_user.groups = [_gruppe(db_session, "Verkauf voll",
                                _blatt(verkauf={"lesen": True, "schreiben": True,
                                                "loeschen": True, "umfang": "alle"}))]
    test_user.permission_overrides = {"verkauf": {"loeschen": False}}
    db_session.commit()

    blatt = B.effektive_rechte(test_user)
    assert blatt["verkauf"]["loeschen"] is False
    assert blatt["verkauf"]["schreiben"] is True


def test_ausnahme_gewaehrt_zusaetzlich(db_session, test_user):
    test_user.groups = [_gruppe(db_session, "Nur lesen",
                                _blatt(stammdaten={"lesen": True}))]
    test_user.permission_overrides = {"stammdaten": {"schreiben": True}}
    db_session.commit()
    assert B.effektive_rechte(test_user)["stammdaten"]["schreiben"] is True


# ── Robustheit gegen fehlerhafte Angaben ─────────────────────────────────────

def test_tippfehler_erzeugt_kein_recht(db_session, test_user):
    """Die Rechte liegen als JSONB — es gibt keine Spaltenprüfung.

    Ein ``"loschen": true`` (ohne e) darf nicht als Recht durchgehen, das
    niemand vergeben hat und das niemandem auffällt.
    """
    test_user.groups = [_gruppe(db_session, "Krumm", {
        "verkauf": {"loschen": True, "lesen": True},
        "erfundenesmodul": {"lesen": True},
    })]
    db_session.commit()

    blatt = B.effektive_rechte(test_user)
    assert blatt["verkauf"]["loeschen"] is False
    assert "erfundenesmodul" not in blatt


def test_leeres_rechteblatt_sperrt_alles(db_session, test_user):
    test_user.groups = [_gruppe(db_session, "Nichts", B.leeres_rechteblatt())]
    db_session.commit()
    assert B.module_mit_zugang(test_user) == []


# ── Umfang nur dort, wo er wirkt ─────────────────────────────────────────────

def test_umfang_ohne_zuordnungsfeld_ist_alle(db_session, test_user):
    """Wo Datensätze niemandem „gehören", wäre „nur eigene" eine leere Zusage.

    Ein Kontakt in den Stammdaten hat keinen Eigentümer. Ein ``eigene`` würde
    Endpunkte zu einer Filterung verleiten, für die es kein Feld gibt.
    """
    test_user.groups = [_gruppe(db_session, "Stamm",
                                _blatt(stammdaten={"lesen": True,
                                                   "umfang": "eigene"}))]
    db_session.commit()
    assert B.umfang(test_user, "stammdaten") == B.UMFANG_ALLE
    assert B.darf_nur_eigene(test_user, "stammdaten") is False


# ── Administratoren ──────────────────────────────────────────────────────────

def test_admin_hat_alles_ohne_gruppe(db_session, admin_user):
    """Der Notausgang: Ohne ihn kann eine Gruppenänderung die Anlage aussperren."""
    admin_user.groups = []
    db_session.commit()
    assert B.hat_recht(admin_user, "verkauf", B.LOESCHEN) is True
    assert B.umfang(admin_user, "zeiterfassung") == B.UMFANG_ALLE
    assert set(B.module_mit_zugang(admin_user)) == set(MODULE_KEYS)


# ── Rückfall auf das alte Format ─────────────────────────────────────────────

def test_ohne_gruppe_gilt_weiter_allowed_modules(db_session, test_user):
    """Damit niemand vor einer leeren Anwendung steht.

    Falls die Übernahme in Migration 0055 aus irgendeinem Grund nicht
    durchgelaufen ist, greifen die alten Einzelrechte weiter — statt dass alle
    Benutzer ohne Gruppe plötzlich nichts mehr sehen.
    """
    test_user.groups = []
    test_user.allowed_modules = ["zeiterfassung", "aufgaben"]
    db_session.commit()

    assert set(B.module_mit_zugang(test_user)) == {"zeiterfassung", "aufgaben"}
    # Das alte Format kannte kein Lesen/Schreiben-Gefälle — der Umstieg darf
    # niemandem etwas wegnehmen, was er vorher konnte.
    assert B.hat_recht(test_user, "zeiterfassung", B.SCHREIBEN) is True
    assert B.hat_recht(test_user, "verkauf", B.LESEN) is False


def test_allowed_modules_null_bedeutet_alles(db_session, test_user):
    test_user.groups = []
    test_user.allowed_modules = None
    db_session.commit()
    assert B.hat_recht(test_user, "buchhaltung", B.LOESCHEN) is True


# ── Endpunkte ────────────────────────────────────────────────────────────────

def test_gruppenverwaltung_nur_fuer_admins(client, test_user):
    kopf = _kopf(client)
    assert client.get("/api/groups/", headers=kopf).status_code == 403
    assert client.post("/api/groups/", headers=kopf,
                       json={"name": "Selbstbedienung"}).status_code == 403


def test_admin_legt_gruppe_an_und_weist_zu(client, admin_user, test_user,
                                           db_session):
    kopf = _kopf(client, admin_user.email)

    neu = client.post("/api/groups/", headers=kopf, json={
        "name": "Lager",
        "beschreibung": "Nur Aufgaben",
        "rechte": {"aufgaben": {"lesen": True, "schreiben": True,
                                "umfang": "alle"}},
        "user_ids": [str(test_user.id)],
    })
    assert neu.status_code == 200, neu.text
    daten = neu.json()
    assert daten["ist_system"] is False
    assert [m["id"] for m in daten["mitglieder"]] == [str(test_user.id)]
    # Das Blatt kommt vollständig zurück, nicht nur die gesetzten Module.
    assert daten["rechte"]["verkauf"]["lesen"] is False

    db_session.refresh(test_user)
    assert B.hat_recht(test_user, "aufgaben", B.SCHREIBEN) is True


def test_gruppe_mit_mitgliedern_nicht_loeschbar(client, admin_user, test_user,
                                                db_session):
    """Kein stilles Entziehen von Rechten."""
    gruppe = _gruppe(db_session, "Mit Leuten", _blatt(aufgaben={"lesen": True}))
    test_user.groups = [gruppe]
    db_session.commit()

    kopf = _kopf(client, admin_user.email)
    resp = client.delete(f"/api/groups/{gruppe.id}", headers=kopf)
    assert resp.status_code == 400
    assert "zugeordnet" in resp.json()["detail"]


def test_systemgruppe_nicht_loeschbar(client, admin_user, db_session):
    gruppe = _gruppe(db_session, "Mitarbeiter", B.leeres_rechteblatt(),
                     ist_system=True)
    kopf = _kopf(client, admin_user.email)
    resp = client.delete(f"/api/groups/{gruppe.id}", headers=kopf)
    assert resp.status_code == 400


def test_administratorengruppe_behaelt_alle_rechte(client, admin_user,
                                                   db_session):
    """Die Rechteverwaltung darf sich nicht selbst aussperren können."""
    gruppe = _gruppe(db_session, "Administratoren", B.volles_rechteblatt(),
                     ist_system=True)
    kopf = _kopf(client, admin_user.email)

    resp = client.put(f"/api/groups/{gruppe.id}", headers=kopf,
                      json={"rechte": B.leeres_rechteblatt()})
    assert resp.status_code == 200, resp.text
    assert resp.json()["rechte"]["stammdaten"]["schreiben"] is True


def test_eigene_rechte_zeigen_die_herkunft(client, test_user, db_session):
    """Ohne diese Auskunft wird die Rechteverwaltung zur Ratesache."""
    test_user.groups = [_gruppe(db_session, "Zeit",
                                _blatt(zeiterfassung={"lesen": True}))]
    test_user.permission_overrides = {"aufgaben": {"lesen": True}}
    db_session.commit()

    resp = client.get("/api/groups/me/rechte", headers=_kopf(client))
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["gruppen"] == ["Zeit"]
    assert daten["ausnahmen"] == {"aufgaben": {"lesen": True}}
    assert set(daten["module"]) == {"zeiterfassung", "aufgaben"}


def test_fremde_rechte_nur_fuer_admins(client, test_user, admin_user):
    kopf = _kopf(client)
    assert client.get(f"/api/groups/users/{admin_user.id}/rechte",
                      headers=kopf).status_code == 403
    # Die eigenen darf jeder sehen — die Oberfläche blendet damit Schaltflächen
    # aus, statt den Benutzer in eine Fehlermeldung laufen zu lassen.
    assert client.get(f"/api/groups/users/{test_user.id}/rechte",
                      headers=kopf).status_code == 200


def test_ausnahmen_setzen_bleibt_eine_ausnahme(client, admin_user, test_user,
                                               db_session):
    """Ein vollständiges Blatt als „Ausnahme" würde die Gruppen aushebeln."""
    kopf = _kopf(client, admin_user.email)
    resp = client.put(f"/api/groups/users/{test_user.id}/overrides",
                      headers=kopf, json={"overrides": {
                          "verkauf": {"loeschen": False},
                          "erfundenesmodul": {"lesen": True},
                      }})
    assert resp.status_code == 200, resp.text
    db_session.refresh(test_user)
    assert test_user.permission_overrides == {"verkauf": {"loeschen": False}}


def test_alte_modulliste_wird_abgelehnt(client, admin_user, test_user,
                                       db_session):
    """Das alte Feld ``allowed_modules`` wird nicht mehr angenommen.

    Vorgeschichte in zwei Stufen — beide Male ging es um still verfallende
    Versprechen:

    1. Nach Migration 0055 schrieben die Modul-Häkchen der Benutzerverwaltung
       weiter nach ``allowed_modules``, das bei Gruppenmitgliedern niemand
       mehr liest. Das Häkchen sah gesetzt aus und bewirkte nichts.
    2. Die Zwischenlösung übersetzte die Häkchen in individuelle Ausnahmen —
       und setzte dabei für **jedes** abweichende Modul alle drei Rechte.
       Diese Ausnahmen überschrieben anschließend die Gruppenrechte, ohne dass
       es in der Gruppenansicht sichtbar war: Eine Gruppe stand auf „nur
       ansehen", der Benutzer konnte trotzdem anlegen und löschen.

    Seit die Benutzerverwaltung Gruppen zuweist, gibt es für beides keinen
    Grund mehr. Das Feld wird jetzt mit einer erklärenden Meldung abgelehnt —
    ein Fehler ist hier besser als ein wirkungsloses Häkchen.
    """
    kopf = _kopf(client, admin_user.email)
    resp = client.put(f"/api/users/{test_user.id}", headers=kopf,
                      json={"allowed_modules": ["zeiterfassung", "stammdaten"]})
    assert resp.status_code == 400
    assert "Rechtegruppen" in resp.json()["detail"]


def test_rechte_kommen_ausschliesslich_aus_gruppen(client, admin_user,
                                                   test_user, db_session):
    """Eine Gruppe auf „nur ansehen" darf nicht durch Altlasten aufgeweicht sein."""
    test_user.groups = [_gruppe(db_session, "Nur ansehen",
                                _blatt(projekte={"lesen": True, "umfang": "alle"}))]
    test_user.permission_overrides = None
    db_session.commit()

    assert B.hat_recht(test_user, "projekte", B.LESEN) is True
    assert B.hat_recht(test_user, "projekte", B.SCHREIBEN) is False
    assert B.hat_recht(test_user, "projekte", B.LOESCHEN) is False


def test_me_liefert_module_aus_dem_neuen_modell(client, test_user, db_session):
    """Das Menü im Frontend hängt an /auth/me — der Weg muss durchgehen."""
    test_user.groups = [_gruppe(db_session, "Nur Aufgaben",
                                _blatt(aufgaben={"lesen": True}))]
    db_session.commit()
    resp = client.get("/api/auth/me", headers=_kopf(client))
    assert resp.status_code == 200
    assert resp.json()["modules"] == ["aufgaben"]
    assert resp.json()["gruppen_namen"] == ["Nur Aufgaben"]


def test_modulsperre_greift_auf_gruppenrechte(client, test_user, db_session):
    """require_module prüft jetzt das Leserecht aus dem Gruppenmodell."""
    test_user.groups = [_gruppe(db_session, "Ohne Verkauf",
                                _blatt(aufgaben={"lesen": True}))]
    db_session.commit()
    kopf = _kopf(client)
    # Verkauf ist nicht freigegeben → die Modulsperre greift …
    assert client.get("/api/invoices", headers=kopf).status_code == 403
    # … Aufgaben schon, dort darf der Aufruf durch.
    assert client.get("/api/aufgaben/", headers=kopf).status_code == 200


def test_katalog_nennt_alle_module(client, test_user):
    """Damit die Rechtematrix im Frontend nicht dieselbe Liste doppelt pflegt."""
    resp = client.get("/api/groups/katalog", headers=_kopf(client))
    assert resp.status_code == 200
    daten = resp.json()
    assert [m["modul"] for m in daten["module"]] == list(MODULE_KEYS)
    # Dashboard hat keine eigenen Datensätze — dort gibt es nur „Ansehen".
    dashboard = next(m for m in daten["module"] if m["modul"] == "dashboard")
    assert [r["key"] for r in dashboard["rechte"]] == ["lesen"]
