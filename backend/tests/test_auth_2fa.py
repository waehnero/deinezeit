"""
Zweiter Faktor: TOTP, Einmal-Codes, verschlüsseltes Secret
=========================================================

Drei Dinge werden hier abgesichert, die vorher Schwachstellen waren:

1. Das TOTP-Secret lief beim Aktivieren als **Query-Parameter** zurück zum
   Server und landete damit in Zugriffslogs und im Browserverlauf.
2. Es lag **im Klartext** in der Datenbank. Wer das Secret kennt, erzeugt
   beliebig gültige Codes — der zweite Faktor ist dann wertlos, während die
   Passwörter weiterhin als bcrypt-Hash geschützt sind.
3. Es gab **keine Einmal-Codes**. Beim Verlust des Handys war der Benutzer
   endgültig ausgesperrt und auf einen Administrator angewiesen — der selbst
   betroffen sein kann.
"""
import pyotp

from app.core import auth_events as EV
from app.core.crypto import entschluesseln, ist_verschluesselt
from app.models.user import AuthEvent, TotpRecoveryCode
from app.services.auth_service import auth_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _kopf(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD):
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _aktivieren(client, kopf):
    """2FA einrichten und aktivieren; gibt (secret, recovery_codes) zurück."""
    setup = client.post("/api/auth/totp/setup", headers=kopf)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]

    resp = client.post("/api/auth/totp/enable", headers=kopf,
                       json={"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 200, resp.text
    return secret, resp.json().get("recovery_codes", [])


# ── Einrichtung ──────────────────────────────────────────────────────────────

def test_secret_wird_serverseitig_vorgemerkt(client, test_user, db_session):
    """Der Client muss das Secret beim Aktivieren nicht zurückschicken."""
    kopf = _kopf(client)
    setup = client.post("/api/auth/totp/setup", headers=kopf)
    db_session.refresh(test_user)
    assert test_user.totp_secret_pending, \
        "Das Secret muss serverseitig liegen, nicht nur beim Client"
    # Und zwar verschlüsselt — auch im Zwischenzustand.
    assert ist_verschluesselt(test_user.totp_secret_pending)
    assert entschluesseln(test_user.totp_secret_pending) == setup.json()["secret"]


def test_aktivieren_mit_falschem_code_scheitert(client, test_user):
    kopf = _kopf(client)
    client.post("/api/auth/totp/setup", headers=kopf)
    resp = client.post("/api/auth/totp/enable", headers=kopf,
                       json={"code": "000000"})
    assert resp.status_code == 400


def test_aktivieren_ohne_setup_scheitert(client, test_user):
    """Ohne vorgemerktes Secret darf sich 2FA nicht aktivieren lassen."""
    kopf = _kopf(client)
    resp = client.post("/api/auth/totp/enable", headers=kopf,
                       json={"code": "123456"})
    assert resp.status_code == 400


def test_secret_liegt_verschluesselt_in_der_db(client, test_user, db_session):
    secret, _ = _aktivieren(client, _kopf(client))
    db_session.refresh(test_user)

    assert test_user.totp_enabled is True
    # Der gespeicherte Wert darf nicht das Secret sein …
    assert test_user.totp_secret != secret
    assert ist_verschluesselt(test_user.totp_secret)
    # … muss aber wieder darauf zurückführen, sonst wäre 2FA kaputt.
    assert entschluesseln(test_user.totp_secret) == secret
    # Der Zwischenzustand ist aufgeräumt.
    assert test_user.totp_secret_pending is None


def test_klartext_secret_aus_bestand_funktioniert_weiter(db_session, test_user):
    """Bestandsdaten von vor Migration 0054 dürfen nicht ausgesperrt werden.

    Die Migration verschlüsselt sie, aber der Backfill ist absichtlich
    fehlertolerant. Bleibt ein Wert im Klartext, muss die Anmeldung trotzdem
    gehen.
    """
    secret = pyotp.random_base32()
    test_user.totp_secret = secret          # bewusst unverschlüsselt
    test_user.totp_enabled = True
    db_session.commit()
    assert auth_service.verify_totp(test_user, pyotp.TOTP(secret).now())


# ── Anmelden mit 2FA ─────────────────────────────────────────────────────────

def test_login_fragt_code_nach_und_gibt_kein_token(client, test_user):
    secret, _ = _aktivieren(client, _kopf(client))
    client.cookies.clear()

    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["requires_totp"] is True
    # Entscheidend: In diesem Zwischenschritt darf noch kein verwendbarer
    # Token herausfallen, sonst wäre der zweite Faktor umgehbar.
    assert resp.json()["access_token"] == ""
    assert resp.json()["refresh_token"] == ""


def test_login_mit_richtigem_code(client, test_user):
    secret, _ = _aktivieren(client, _kopf(client))
    client.cookies.clear()
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "totp_code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


def test_login_mit_falschem_code(client, test_user, monkeypatch):
    monkeypatch.setattr(auth_service, "verzoegerung_sek", lambda _n: 0.0)
    _aktivieren(client, _kopf(client))
    client.cookies.clear()
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "totp_code": "000000"})
    assert resp.status_code == 401


# ── Einmal-Codes ─────────────────────────────────────────────────────────────

def test_aktivierung_liefert_einmal_codes(client, test_user, db_session):
    _, codes = _aktivieren(client, _kopf(client))
    assert len(codes) == 10, "Ohne Einmal-Codes ist ein Handyverlust endgültig"
    # Gespeichert wird nur der Hash.
    gespeichert = db_session.query(TotpRecoveryCode).all()
    assert len(gespeichert) == 10
    assert all(e.code_hash not in codes for e in gespeichert)


def test_einmal_code_ersetzt_den_2fa_code(client, test_user):
    _, codes = _aktivieren(client, _kopf(client))
    client.cookies.clear()

    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "recovery_code": codes[0]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    # Die Oberfläche warnt anhand dieses Werts, wenn es knapp wird.
    assert resp.json()["recovery_codes_left"] == 9


def test_einmal_code_gilt_nur_einmal(client, test_user, monkeypatch):
    monkeypatch.setattr(auth_service, "verzoegerung_sek", lambda _n: 0.0)
    _, codes = _aktivieren(client, _kopf(client))
    client.cookies.clear()

    erst = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "recovery_code": codes[0]})
    assert erst.status_code == 200
    client.cookies.clear()

    nochmal = client.post("/api/auth/login",
                          json={"email": TEST_USER_EMAIL,
                                "password": TEST_USER_PASSWORD,
                                "recovery_code": codes[0]})
    assert nochmal.status_code == 401


def test_einmal_code_schreibweise_egal(client, test_user, db_session):
    """Die Codes werden abgeschrieben, oft von einem Ausdruck."""
    _aktivieren(client, _kopf(client))
    codes = auth_service.recovery_codes_erzeugen(db_session, test_user)
    verunstaltet = codes[0].lower().replace("-", " ")
    assert auth_service.recovery_code_einloesen(db_session, test_user,
                                                verunstaltet)


def test_neue_codes_entwerten_die_alten(client, test_user, db_session):
    secret, alte = _aktivieren(client, _kopf(client))

    # Neu anmelden, jetzt mit 2FA-Code — die Sitzung von vor der Aktivierung
    # soll hier nicht weiterverwendet werden.
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "totp_code": pyotp.TOTP(secret).now()})
    kopf = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    neu = client.post("/api/auth/recovery-codes", headers=kopf,
                      json={"code": pyotp.TOTP(secret).now()})
    assert neu.status_code == 200, neu.text
    neue_codes = neu.json()["codes"]
    assert set(neue_codes).isdisjoint(set(alte))
    # Ein alter Code darf jetzt nicht mehr funktionieren.
    assert auth_service.recovery_code_einloesen(db_session, test_user,
                                                alte[0]) is False


# ── Deaktivieren ─────────────────────────────────────────────────────────────

def test_deaktivieren_raeumt_alles_auf(client, test_user, db_session):
    secret, _ = _aktivieren(client, _kopf(client))
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD,
                             "totp_code": pyotp.TOTP(secret).now()})
    kopf = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    aus = client.post("/api/auth/totp/disable", headers=kopf,
                      json={"code": pyotp.TOTP(secret).now()})
    assert aus.status_code == 200, aus.text

    db_session.refresh(test_user)
    assert test_user.totp_enabled is False
    assert test_user.totp_secret is None
    # Übrig gebliebene Einmal-Codes wären ein Zweitschlüssel zu einem Schloss,
    # das es nicht mehr gibt.
    assert db_session.query(TotpRecoveryCode).filter(
        TotpRecoveryCode.user_id == test_user.id).count() == 0


def test_2fa_aenderungen_landen_im_pruefpfad(client, test_user, db_session):
    _aktivieren(client, _kopf(client))
    arten = [e.event for e in db_session.query(AuthEvent).all()]
    assert EV.TOTP_ENABLED in arten
    assert EV.RECOVERY_GENERATED in arten
