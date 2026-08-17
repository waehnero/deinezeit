"""
Passwort ändern und zurücksetzen
================================

Beides gab es vorher so nicht: „Passwort vergessen" fehlte im Backend komplett
(die Seite im Frontend lief ins Leere), und das Ändern im Profil lief über
``PUT /users/me`` — ohne Abfrage des alten Passworts, ohne Richtlinie und ohne
dass bestehende Anmeldungen beendet wurden.
"""
from app.core import auth_events as EV
from app.models.user import AuthEvent, PasswordResetToken, UserSession
from app.services.auth_service import auth_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

NEUES_PASSWORT = "Regenschirm-Blau-42"


def _token(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD):
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── Ändern im Profil ─────────────────────────────────────────────────────────

def test_aendern_verlangt_aktuelles_passwort(client, test_user):
    kopf = {"Authorization": f"Bearer {_token(client)}"}
    resp = client.post("/api/auth/password/change", headers=kopf, json={
        "current_password": "falsch-falsch-99",
        "new_password": NEUES_PASSWORT,
    })
    assert resp.status_code == 400


def test_aendern_prueft_richtlinie(client, test_user):
    kopf = {"Authorization": f"Bearer {_token(client)}"}
    resp = client.post("/api/auth/password/change", headers=kopf, json={
        "current_password": TEST_USER_PASSWORD,
        "new_password": "geheim",
    })
    assert resp.status_code == 400
    # Die Meldung soll sagen, was zu tun ist.
    assert "Zeichen" in resp.json()["detail"]


def test_aendern_beendet_andere_geraete(client, test_user, db_session):
    """Ein Passwortwechsel muss Mitleser aussperren.

    Solange alte Sitzungen weitergelten, ist die Änderung wirkungslos — genau
    das war vorher der Fall, weil es keinen Widerruf gab.
    """
    fremdes_geraet = _token(client)
    client.cookies.clear()
    eigenes_geraet = _token(client)

    resp = client.post("/api/auth/password/change",
                       headers={"Authorization": f"Bearer {eigenes_geraet}"},
                       json={"current_password": TEST_USER_PASSWORD,
                             "new_password": NEUES_PASSWORT})
    assert resp.status_code == 200, resp.text

    # Das andere Gerät ist draußen …
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {fremdes_geraet}"}
                      ).status_code == 401
    # … das eigene bleibt drin, damit man sich nicht selbst aus der laufenden
    # Arbeit wirft.
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {eigenes_geraet}"}
                      ).status_code == 200

    # Und das neue Passwort gilt.
    client.cookies.clear()
    assert _token(client, passwort=NEUES_PASSWORT)


def test_users_me_aendert_kein_passwort_mehr(client, test_user):
    """Der alte, unsichere Weg muss geschlossen sein.

    Über ``PUT /users/me`` genügte ein gültiger Access-Token, um das Passwort
    zu überschreiben — ohne das alte zu kennen. Wer ein unbeaufsichtigtes Gerät
    vorfand, konnte damit das Konto übernehmen.
    """
    kopf = {"Authorization": f"Bearer {_token(client)}"}
    resp = client.put("/api/users/me", headers=kopf,
                      json={"password": "Regenschirm-Blau-99"})
    assert resp.status_code == 400
    # Das alte Passwort muss weiterhin gelten.
    client.cookies.clear()
    assert _token(client)


# ── Zurücksetzen ─────────────────────────────────────────────────────────────

def test_forgot_antwortet_immer_gleich(client, test_user):
    """Sonst wäre die Seite ein Verzeichnis der vorhandenen Adressen."""
    bekannt = client.post("/api/auth/password/forgot",
                          json={"email": TEST_USER_EMAIL})
    unbekannt = client.post("/api/auth/password/forgot",
                            json={"email": "niemand@deinezeit.local"})
    assert bekannt.status_code == unbekannt.status_code == 200
    assert bekannt.json() == unbekannt.json()


def test_forgot_legt_token_nur_fuer_echtes_konto_an(client, test_user,
                                                    db_session):
    client.post("/api/auth/password/forgot", json={"email": TEST_USER_EMAIL})
    client.post("/api/auth/password/forgot",
                json={"email": "niemand@deinezeit.local"})
    tokens = db_session.query(PasswordResetToken).all()
    assert len(tokens) == 1
    assert tokens[0].user_id == test_user.id
    # Gespeichert wird nur der Hash — wer die Datenbank liest, kann damit kein
    # Passwort setzen.
    assert len(tokens[0].token_hash) == 64


def test_reset_setzt_passwort_und_verbraucht_token(client, test_user,
                                                   db_session):
    roh = auth_service.reset_token_erzeugen(db_session, test_user)
    assert roh

    resp = client.post("/api/auth/password/reset",
                       json={"token": roh, "new_password": NEUES_PASSWORT})
    assert resp.status_code == 200, resp.text

    # Neues Passwort gilt, altes nicht mehr.
    assert _token(client, passwort=NEUES_PASSWORT)
    assert client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD}
                       ).status_code == 401

    # Derselbe Link darf nicht zweimal funktionieren.
    zweiter = client.post("/api/auth/password/reset",
                          json={"token": roh, "new_password": "Andere-Wahl-77"})
    assert zweiter.status_code == 400


def test_reset_lehnt_unbekannten_token_ab(client, test_user):
    resp = client.post("/api/auth/password/reset",
                       json={"token": "frei-erfunden", "new_password": NEUES_PASSWORT})
    assert resp.status_code == 400


def test_reset_lehnt_abgelaufenen_token_ab(client, test_user, db_session):
    from datetime import datetime, timedelta, timezone
    roh = auth_service.reset_token_erzeugen(db_session, test_user)
    eintrag = db_session.query(PasswordResetToken).first()
    eintrag.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    resp = client.post("/api/auth/password/reset",
                       json={"token": roh, "new_password": NEUES_PASSWORT})
    assert resp.status_code == 400


def test_reset_beendet_alle_sitzungen(client, test_user, db_session):
    """Wer zurücksetzt, tut das oft, weil ein Fremder Zugang hat."""
    token = _token(client)
    roh = auth_service.reset_token_erzeugen(db_session, test_user)
    client.post("/api/auth/password/reset",
                json={"token": roh, "new_password": NEUES_PASSWORT})

    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {token}"}
                      ).status_code == 401
    offen = db_session.query(UserSession).filter(
        UserSession.user_id == test_user.id,
        UserSession.revoked_at.is_(None)).count()
    assert offen == 0


def test_reset_wird_im_pruefpfad_vermerkt(client, test_user, db_session):
    roh = auth_service.reset_token_erzeugen(db_session, test_user)
    client.post("/api/auth/password/reset",
                json={"token": roh, "new_password": NEUES_PASSWORT})
    arten = [e.event for e in db_session.query(AuthEvent).all()]
    assert EV.RESET_DONE in arten


def test_zu_viele_reset_anfragen_werden_gebremst(client, test_user, db_session):
    """Sonst lässt sich das Postfach eines Benutzers zumüllen."""
    for _ in range(5):
        assert auth_service.reset_token_erzeugen(db_session, test_user)
    assert auth_service.reset_token_erzeugen(db_session, test_user) is None
