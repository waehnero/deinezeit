"""
Sitzungsübersicht für Administratoren
=====================================

Beantwortet im Betrieb zwei Fragen: „Wer arbeitet gerade?" (vor einem Update
oder einem Lasttest) und „Wer hat vergessen, sich abzumelden?".

Geprüft wird vor allem, dass ein Widerruf **sofort** wirkt. Eine Abmeldung, die
erst greift, wenn der Zugangstoken von selbst abläuft, ist keine Abmeldung —
sie sieht nur so aus, und im Zweifel arbeitet der vermeintlich Hinausgeworfene
noch eine halbe Stunde weiter.
"""
from datetime import datetime, timedelta, timezone

from app.models.user import AuthEvent, UserSession
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

# Der admin_user-Fixture legt dieses Konto an; conftest exportiert dafür keine
# Konstante, das Passwort teilt es sich mit dem Standardbenutzer.
TEST_ADMIN_EMAIL = "admin@deinezeit.local"
TEST_ADMIN_PASSWORD = TEST_USER_PASSWORD


def _anmelden(client, email, passwort):
    """Anmelden und Kopfzeilen samt Sitzungs-Cookie zurückgeben."""
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _offene_sitzungen(db, user_id=None):
    q = db.query(UserSession).filter(UserSession.revoked_at.is_(None))
    if user_id:
        q = q.filter(UserSession.user_id == user_id)
    return q.all()


# ── Übersicht ────────────────────────────────────────────────────────────────

def test_uebersicht_nur_fuer_admins(client, test_user):
    kopf = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    assert client.get("/api/system/sitzungen", headers=kopf).status_code == 403


def test_uebersicht_zeigt_fremde_sitzungen_mit_namen(client, test_user, admin_user):
    _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    resp = client.get("/api/system/sitzungen", headers=kopf_admin)
    assert resp.status_code == 200, resp.text
    mails = [s["user_email"] for s in resp.json()]
    assert TEST_USER_EMAIL in mails
    assert TEST_ADMIN_EMAIL in mails


def test_uebersicht_zeigt_auch_lange_untaetige(client, test_user, admin_user,
                                               db_session):
    """Der eigentliche Zweck: Die Vergessenen sind die Stillen.

    Eine Anzeige, die nur die letzten fünf Minuten zeigt, blendet genau den
    Fall aus, den man aufräumen will.
    """
    _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    sitzung = _offene_sitzungen(db_session, test_user.id)[0]
    sitzung.last_used_at = datetime.now(timezone.utc) - timedelta(hours=6)
    db_session.commit()

    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    eintrag = next(s for s in client.get("/api/system/sitzungen",
                                         headers=kopf_admin).json()
                   if s["user_email"] == TEST_USER_EMAIL)
    assert eintrag["untaetig_minuten"] >= 350


def test_widerrufene_sitzung_taucht_nicht_mehr_auf(client, test_user, admin_user,
                                                   db_session):
    _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    sitzung = _offene_sitzungen(db_session, test_user.id)[0]
    client.delete(f"/api/system/sitzungen/{sitzung.id}", headers=kopf_admin)

    ids = [s["id"] for s in client.get("/api/system/sitzungen",
                                       headers=kopf_admin).json()]
    assert str(sitzung.id) not in ids


# ── Abmelden ─────────────────────────────────────────────────────────────────

def test_abmelden_wirkt_sofort(client, test_user, admin_user, db_session):
    """Der Kern der Sache: Der Zugangstoken muss augenblicklich wertlos sein."""
    kopf_user = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    assert client.get("/api/auth/me", headers=kopf_user).status_code == 200

    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    sitzung = _offene_sitzungen(db_session, test_user.id)[0]
    weg = client.delete(f"/api/system/sitzungen/{sitzung.id}", headers=kopf_admin)
    assert weg.status_code == 200, weg.text

    danach = client.get("/api/auth/me", headers=kopf_user)
    assert danach.status_code == 401, \
        "Nach dem Widerruf darf der Zugangstoken nicht mehr gelten"


def test_abmelden_nur_fuer_admins(client, test_user, admin_user, db_session):
    kopf_user = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    fremde = _offene_sitzungen(db_session, admin_user.id)[0]
    resp = client.delete(f"/api/system/sitzungen/{fremde.id}", headers=kopf_user)
    assert resp.status_code == 403
    assert fremde.revoked_at is None


def test_alle_geraete_eines_benutzers_abmelden(client, test_user, admin_user,
                                               db_session):
    kopf_erstes = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    kopf_zweites = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    assert len(_offene_sitzungen(db_session, test_user.id)) == 2

    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    resp = client.delete(f"/api/system/sitzungen/benutzer/{test_user.id}",
                         headers=kopf_admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["anzahl"] == 2

    assert _offene_sitzungen(db_session, test_user.id) == []
    assert client.get("/api/auth/me", headers=kopf_erstes).status_code == 401
    assert client.get("/api/auth/me", headers=kopf_zweites).status_code == 401


def test_andere_benutzer_bleiben_angemeldet(client, test_user, admin_user,
                                            db_session):
    """Ein Sammelabmelden darf nicht den halben Betrieb hinauswerfen."""
    _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    client.delete(f"/api/system/sitzungen/benutzer/{test_user.id}",
                  headers=kopf_admin)
    assert client.get("/api/auth/me", headers=kopf_admin).status_code == 200


def test_unbekannte_sitzung_liefert_404(client, admin_user):
    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    resp = client.delete(
        "/api/system/sitzungen/11111111-1111-1111-1111-111111111111",
        headers=kopf_admin)
    assert resp.status_code == 404


# ── Prüfpfad ─────────────────────────────────────────────────────────────────

def test_abmelden_steht_im_pruefpfad_des_betroffenen(client, test_user,
                                                     admin_user, db_session):
    """Wer sich wundert, warum er abgemeldet wurde, soll es selbst nachsehen
    können — der Eintrag gehört deshalb in SEINE Liste, nicht in die des
    Administrators."""
    _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    kopf_admin = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    sitzung = _offene_sitzungen(db_session, test_user.id)[0]

    client.delete(f"/api/system/sitzungen/{sitzung.id}", headers=kopf_admin)

    eintrag = (db_session.query(AuthEvent)
               .filter(AuthEvent.user_id == test_user.id,
                       AuthEvent.event == "session_revoked")
               .first())
    assert eintrag is not None
    assert TEST_ADMIN_EMAIL in (eintrag.detail or ""), \
        "Im Prüfpfad muss stehen, welcher Administrator es war"
