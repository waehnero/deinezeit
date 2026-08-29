"""
Sitzungen: erneuern, abmelden, widerrufen (Migration 0054)
=========================================================

Was hier abgesichert wird, ist genau das, was vorher fehlte: Die Tabelle
``user_sessions`` wurde beschrieben, aber nie gelesen — es gab weder
``/auth/refresh`` noch ``/auth/logout``, also war keine Anmeldung widerrufbar.

Die Tests prüfen deshalb nicht nur „Endpunkt antwortet 200", sondern die
Wirkung: Nach dem Abmelden muss ein vorher gültiger Access-Token abgelehnt
werden. Sonst wäre das Abmelden bloß Kosmetik im Browser.
"""
from app.models.user import UserSession
from app.services.auth_service import REFRESH_COOKIE_NAME, auth_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _anmelden(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD):
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return resp


# ── Anmelden legt eine überprüfbare Sitzung an ───────────────────────────────

def test_login_legt_sitzung_an(client, test_user, db_session):
    _anmelden(client)
    sitzungen = db_session.query(UserSession).filter(
        UserSession.user_id == test_user.id).all()
    assert len(sitzungen) == 1
    assert sitzungen[0].revoked_at is None
    # Der Gerätename wird aus dem User-Agent abgeleitet, damit die Übersicht
    # „Hier bist du angemeldet" lesbar ist.
    assert sitzungen[0].device_label


def test_access_token_enthaelt_sitzung(client, test_user):
    """Ohne ``sid`` im Token ließe sich eine Sitzung nicht beenden."""
    from app.core.security import decode_token
    token = _anmelden(client).json()["access_token"]
    payload = decode_token(token)
    assert payload["sid"]
    assert payload["sub"] == str(test_user.id)


# ── Erneuern ─────────────────────────────────────────────────────────────────

def test_refresh_liefert_neuen_token(client, test_user):
    _anmelden(client)
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    # Der neue Access-Token muss auch tatsächlich funktionieren.
    neu = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {neu}"})
    assert me.status_code == 200


def test_refresh_ohne_cookie_abgelehnt(client, test_user):
    client.cookies.clear()
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_rotiert_den_token(client, test_user, db_session):
    """Der eingelöste Refresh-Token darf danach nicht mehr gelten.

    Ohne Rotation bleibt ein einmal abgefangener Token die ganze Laufzeit über
    brauchbar. Mit Rotation fällt eine Zweitverwendung auf.
    """
    _anmelden(client)
    alter_cookie = client.cookies.get(REFRESH_COOKIE_NAME)

    assert client.post("/api/auth/refresh").status_code == 200
    neuer_cookie = client.cookies.get(REFRESH_COOKIE_NAME)
    assert neuer_cookie and neuer_cookie != alter_cookie

    # Die alte Sitzung ist als rotiert markiert und zeigt auf die neue.
    alte = db_session.query(UserSession).filter(
        UserSession.revoked_reason == "rotation").all()
    assert len(alte) == 1
    assert alte[0].replaced_by_id is not None


def test_refresh_zweitverwendung_entwertet_alles(client, test_user, db_session):
    """Ein zweites Einlösen desselben Tokens beendet die ganze Kette.

    Von außen ist nicht zu unterscheiden, ob ein Client den Token doppelt
    geschickt hat oder ob ihn jemand kopiert hat. Deshalb wird der Fall wie ein
    Diebstahl behandelt: einmal neu anmelden ist zumutbar, ein Angreifer mit
    dauerhaftem Zugang nicht.
    """
    _anmelden(client)
    alter_cookie = client.cookies.get(REFRESH_COOKIE_NAME)
    assert client.post("/api/auth/refresh").status_code == 200

    # Denselben (bereits verbrauchten) Token erneut einlösen.
    client.cookies.set(REFRESH_COOKIE_NAME, alter_cookie)
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401

    offen = db_session.query(UserSession).filter(
        UserSession.user_id == test_user.id,
        UserSession.revoked_at.is_(None)).count()
    assert offen == 0, "Nach erkannter Zweitverwendung darf keine Sitzung offen bleiben"


def test_zweitverwendung_wirft_auch_den_zuvorgekommenen_hinaus(
        client, test_user, db_session):
    """Der eigentliche Angriffsfall — und die Lücke, die er aufgedeckt hat.

    Ein Angreifer mit kopiertem Refresh-Token erneuert **zuerst** und besitzt
    danach die Nachfolge-Sitzung. Kommt der echte Benutzer mit demselben, nun
    verbrauchten Token, genügt es nicht, ihn bloß abzuweisen: Dann behielte der
    Angreifer seinen Zugang, und der Diebstahl bliebe unbemerkt. Die Sitzung des
    Angreifers muss mitfallen.

    Beim ersten Testlauf war genau das nicht der Fall — die Zweitverwendung
    wurde am Hash erkannt, und der stimmte weiterhin, weil die rotierte Sitzung
    ihren Hash behält. Der Fall lief also in die gewöhnliche
    „Sitzung ungültig"-Abweisung, ohne die Kette zu entwerten.
    """
    _anmelden(client)
    gestohlener_cookie = client.cookies.get(REFRESH_COOKIE_NAME)

    # Der Angreifer kommt zuvor und erhält eine frische Sitzung.
    angreifer = client.post("/api/auth/refresh")
    assert angreifer.status_code == 200
    angreifer_token = angreifer.json()["access_token"]
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {angreifer_token}"}
                      ).status_code == 200

    # Jetzt versucht der echte Benutzer sein Erneuern.
    client.cookies.set(REFRESH_COOKIE_NAME, gestohlener_cookie)
    assert client.post("/api/auth/refresh").status_code == 401

    # Der Zugang des Angreifers ist damit ebenfalls erledigt.
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {angreifer_token}"}
                      ).status_code == 401
    # Und die Kette ist als betroffen gekennzeichnet, nicht bloß als „rotiert".
    gruende = {s.revoked_reason for s in db_session.query(UserSession).filter(
        UserSession.user_id == test_user.id).all()}
    assert "reuse_detected" in gruende


# ── Abmelden ─────────────────────────────────────────────────────────────────

def test_logout_entwertet_den_access_token(client, test_user):
    """Der Kern der Etappe: Abmelden wirkt serverseitig.

    Vorher blieb ein ausgestellter Access-Token bis zum Ablauf gültig, weil
    niemand die Sitzung prüfte — „abmelden" hieß nur „Token im Browser
    löschen".
    """
    token = _anmelden(client).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=kopf).status_code == 200

    assert client.post("/api/auth/logout", headers=kopf).status_code == 200
    assert client.get("/api/auth/me", headers=kopf).status_code == 401


def test_logout_all_beendet_alle_geraete(client, test_user, db_session):
    # Zwei getrennte Anmeldungen („zwei Geräte")
    erste = _anmelden(client).json()["access_token"]
    client.cookies.clear()
    zweite = _anmelden(client).json()["access_token"]

    resp = client.post("/api/auth/logout-all",
                       headers={"Authorization": f"Bearer {zweite}"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 2

    for token in (erste, zweite):
        assert client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {token}"}
                          ).status_code == 401


# ── Sitzungsübersicht ────────────────────────────────────────────────────────

def test_sessions_zeigt_eigene_sitzungen(client, test_user):
    token = _anmelden(client).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/auth/sessions", headers=kopf)
    assert resp.status_code == 200
    liste = resp.json()
    assert len(liste) == 1
    # Genau eine Sitzung ist die aktuelle — sonst weiß der Benutzer nicht,
    # welchen Eintrag er gerade benutzt.
    assert sum(1 for s in liste if s["is_current"]) == 1


def test_sessions_fremde_sitzung_nicht_beendbar(client, test_user, admin_user,
                                                db_session):
    """Niemand darf die Sitzung eines anderen Kontos beenden."""
    fremde = auth_service.create_tokens(db_session, admin_user, {})
    token = _anmelden(client).json()["access_token"]

    resp = client.delete(f"/api/auth/sessions/{fremde['session_id']}",
                         headers={"Authorization": f"Bearer {token}"})
    # 404 und nicht 403: Sonst wäre die Antwort eine Auskunft darüber, welche
    # Sitzungs-IDs es gibt.
    assert resp.status_code == 404

    unberuehrt = auth_service.sitzung_laden(db_session, fremde["session_id"])
    assert unberuehrt.revoked_at is None


def test_einzelne_sitzung_beenden(client, test_user, db_session):
    erste = _anmelden(client).json()["access_token"]
    client.cookies.clear()
    zweite = _anmelden(client).json()["access_token"]

    kopf = {"Authorization": f"Bearer {zweite}"}
    liste = client.get("/api/auth/sessions", headers=kopf).json()
    andere = [s for s in liste if not s["is_current"]]
    assert andere, "Es muss eine zweite Sitzung sichtbar sein"

    assert client.delete(f"/api/auth/sessions/{andere[0]['id']}",
                         headers=kopf).status_code == 200
    # Die beendete Sitzung ist tot, die eigene lebt weiter.
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {erste}"}
                      ).status_code == 401
    assert client.get("/api/auth/me", headers=kopf).status_code == 200


# ── Deaktiviertes Konto ──────────────────────────────────────────────────────

def test_deaktiviertes_konto_verliert_zugang(client, test_user, db_session):
    """„Zugang entziehen" muss sofort wirken.

    Vorher lief ein deaktiviertes Konto bis zum Ablauf des Tokens weiter — bis
    zu 30 Minuten mit dem Access-Token und sieben Tage über das Erneuern.
    """
    token = _anmelden(client).json()["access_token"]
    kopf = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=kopf).status_code == 200

    test_user.is_active = False
    db_session.commit()

    assert client.get("/api/auth/me", headers=kopf).status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401


# ── Cookie-Kennzeichen ───────────────────────────────────────────────────────

def test_refresh_cookie_ist_ueber_https_geschuetzt(monkeypatch):
    """Das ``secure``-Kennzeichen des Refresh-Cookies hängt am Schema.

    Diese Prüfung steht hier, weil genau dieser Zusammenhang die Testreihe auf
    dem Server rot gemacht hat: Dort steht ``https://…`` in der ``.env``, das
    Cookie wird ``secure`` — und der Testclient spricht ``http``, schickt es
    also nie zurück. Behoben ist das in ``conftest.py``, indem die Testreihe
    ``FRONTEND_URL`` selbst festlegt.

    Der naheliegende „Fix", ``_cookie_sicher()`` einfach auf ``False`` zu
    setzen, wäre ein Sicherheitsfehler: Der Refresh-Token liefe dann im
    Produktivbetrieb unverschlüsselt über die Leitung. Dieser Test hält das
    fest.
    """
    from app.api import auth as auth_api

    monkeypatch.setattr(auth_api.settings, "FRONTEND_URL",
                        "https://dz.example.online")
    assert auth_api._cookie_sicher() is True

    monkeypatch.setattr(auth_api.settings, "FRONTEND_URL", "http://localhost")
    assert auth_api._cookie_sicher() is False
