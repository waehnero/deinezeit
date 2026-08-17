"""
Anmeldeschutz: Kontosperre, Prüfpfad, Passwort-Richtlinie, Enumeration
=====================================================================

Der Schwerpunkt liegt auf den Eigenschaften, die man leicht übersieht, weil
„es funktioniert doch" — etwa dass die Antwort für ein unbekanntes Konto
dieselbe sein muss wie für ein falsches Passwort. Ein Test, der nur prüft
„Anmeldung mit falschem Passwort ergibt 401", würde eine Meldung wie
„E-Mail-Adresse nicht registriert" nicht bemerken, obwohl damit von außen die
Mitarbeiterliste abfragbar wäre.
"""
import pytest

from app.core import auth_events as EV
from app.core import passwort as pw_regeln
from app.models.user import AuthEvent, User
from app.services.auth_service import SPERRE_AB, auth_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _falsch_anmelden(client, email=TEST_USER_EMAIL, passwort="ganz-falsch-9876"):
    return client.post("/api/auth/login",
                       json={"email": email, "password": passwort})


# ── Keine Auskunft über vorhandene Konten ────────────────────────────────────

def test_gleiche_meldung_fuer_unbekannt_und_falsch(client, test_user):
    unbekannt = _falsch_anmelden(client, email="niemand@deinezeit.local")
    falsch = _falsch_anmelden(client)

    assert unbekannt.status_code == falsch.status_code == 401
    # Identischer Text — sonst ist die Anmeldemaske ein Verzeichnis der
    # vorhandenen E-Mail-Adressen.
    assert unbekannt.json()["detail"] == falsch.json()["detail"]


def test_deaktiviertes_konto_meldet_nicht_deaktiviert(client, test_user,
                                                     db_session):
    test_user.is_active = False
    db_session.commit()
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD})
    assert resp.status_code == 401
    text = resp.json()["detail"].lower()
    assert "deaktiv" not in text and "gesperrt" not in text


def test_passkey_beginn_verraet_kein_konto(client, test_user):
    """Vorher meldete dieser Endpunkt 404 „Benutzer nicht gefunden".

    Damit ließen sich vorhandene Konten auflisten, ohne ein einziges Passwort
    zu kennen.
    """
    ohne_konto = client.post("/api/auth/webauthn/login/begin",
                             json={"email": "niemand@deinezeit.local"})
    mit_konto = client.post("/api/auth/webauthn/login/begin",
                            json={"email": TEST_USER_EMAIL})
    assert ohne_konto.status_code == mit_konto.status_code == 401
    assert ohne_konto.json()["detail"] == mit_konto.json()["detail"]


# ── Kontosperre ──────────────────────────────────────────────────────────────

def test_sperre_nach_zu_vielen_fehlversuchen(client, test_user, db_session,
                                             monkeypatch):
    # Die gestaffelte Verzögerung würde den Test unnötig lange laufen lassen;
    # geprüft wird hier die Sperre, nicht das Warten.
    monkeypatch.setattr(auth_service, "verzoegerung_sek", lambda _n: 0.0)

    for _ in range(SPERRE_AB):
        assert _falsch_anmelden(client).status_code == 401

    db_session.refresh(test_user)
    assert test_user.is_locked
    assert test_user.failed_login_count >= SPERRE_AB

    # Ab jetzt wird sogar das RICHTIGE Passwort abgewiesen — das ist der Sinn
    # der Sperre. 429 statt 401, damit die Oberfläche die Wartezeit anzeigen
    # kann.
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_erfolgreiche_anmeldung_setzt_zaehler_zurueck(client, test_user,
                                                     db_session, monkeypatch):
    monkeypatch.setattr(auth_service, "verzoegerung_sek", lambda _n: 0.0)
    _falsch_anmelden(client)
    _falsch_anmelden(client)
    db_session.refresh(test_user)
    assert test_user.failed_login_count == 2

    client.post("/api/auth/login", json={"email": TEST_USER_EMAIL,
                                         "password": TEST_USER_PASSWORD})
    db_session.refresh(test_user)
    assert test_user.failed_login_count == 0
    assert test_user.last_login_at is not None


def test_sperre_laeuft_von_selbst_ab(db_session, test_user):
    """Nach Ablauf darf sich der Benutzer ohne Administrator wieder anmelden."""
    from datetime import datetime, timedelta, timezone
    test_user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert test_user.is_locked is False


def test_sperrdauer_waechst(db_session):
    """Wer weiter probiert, wartet länger — aber nie unbegrenzt."""
    kurz = auth_service.sperrdauer(SPERRE_AB)
    laenger = auth_service.sperrdauer(SPERRE_AB + 3)
    assert laenger > kurz
    assert auth_service.sperrdauer(9999).total_seconds() <= 24 * 3600


def test_admin_kann_sperre_aufheben(client, admin_user, test_user, db_session):
    from datetime import datetime, timedelta, timezone
    test_user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
    test_user.failed_login_count = 12
    db_session.commit()

    resp = client.post("/api/auth/login",
                       json={"email": admin_user.email,
                             "password": TEST_USER_PASSWORD})
    token = resp.json()["access_token"]

    resp = client.post(f"/api/users/{test_user.id}/unlock",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    db_session.refresh(test_user)
    assert test_user.is_locked is False
    assert test_user.failed_login_count == 0


# ── Prüfpfad ─────────────────────────────────────────────────────────────────

def test_pruefpfad_haelt_erfolg_und_fehlschlag_fest(client, test_user,
                                                    db_session, monkeypatch):
    monkeypatch.setattr(auth_service, "verzoegerung_sek", lambda _n: 0.0)
    _falsch_anmelden(client)
    client.post("/api/auth/login", json={"email": TEST_USER_EMAIL,
                                         "password": TEST_USER_PASSWORD})

    arten = [e.event for e in db_session.query(AuthEvent).all()]
    assert EV.LOGIN_FAIL in arten
    assert EV.LOGIN_OK in arten


def test_pruefpfad_vermerkt_unbekannte_adresse(client, db_session):
    _falsch_anmelden(client, email="niemand@deinezeit.local")
    eintrag = db_session.query(AuthEvent).filter(
        AuthEvent.event == EV.LOGIN_FAIL).first()
    assert eintrag is not None
    # Ohne die versuchte Adresse wäre nicht nachvollziehbar, auf welches Konto
    # gezielt wurde — und die Sperre für unbekannte Konten hätte keine
    # Grundlage.
    assert eintrag.email_attempted == "niemand@deinezeit.local"
    assert eintrag.user_id is None


def test_pruefpfad_nimmt_die_echte_adresse_und_nicht_die_gefaelschte(
        client, test_user, db_session):
    """Die Herkunftsadresse darf nicht vom Aufrufer bestimmbar sein.

    ``X-Forwarded-For`` ist eine Kette, an die jeder Proxy anhängt — ein Client
    kann also mit einem bereits gefüllten Header ankommen. Nimmt man den
    vordersten Eintrag, schreibt sich jeder seine Wunschadresse in den
    Prüfpfad. Der ist dann schlimmer als keiner: Er sieht belastbar aus.

    ``X-Real-IP`` setzt der eigene nginx aus ``$remote_addr`` und überschreibt
    dabei einen mitgeschickten Wert — deshalb hat er Vorrang.
    """
    client.post("/api/auth/login",
                json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
                headers={"X-Real-IP": "89.144.200.10",
                         "X-Forwarded-For": "6.6.6.6, 89.144.200.10"})

    eintrag = db_session.query(AuthEvent).filter(
        AuthEvent.event == EV.LOGIN_OK).first()
    assert eintrag is not None
    assert eintrag.ip_address == "89.144.200.10"
    assert eintrag.ip_address != "6.6.6.6", \
        "Die vom Client gefälschte Adresse darf nicht im Prüfpfad landen"


def test_events_endpunkt_zeigt_nur_eigene(client, test_user, admin_user,
                                          db_session):
    auth_service.ereignis(db_session, EV.LOGIN_FAIL, user=admin_user,
                          detail="fremdes Konto")
    resp = client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL,
                             "password": TEST_USER_PASSWORD})
    token = resp.json()["access_token"]

    liste = client.get("/api/auth/events",
                       headers={"Authorization": f"Bearer {token}"}).json()
    assert liste, "Die eigene Anmeldung muss sichtbar sein"
    assert all(e["detail"] != "fremdes Konto" for e in liste)
    # Jede Ereignisart bekommt einen deutschen Text für die Oberfläche.
    assert all(e["label"] for e in liste)


# ── Passwort-Richtlinie ──────────────────────────────────────────────────────

@pytest.mark.parametrize("schlecht", [
    "kurz",                # zu kurz
    "Passwort123",         # bekanntes Wort mit Ziffern
    "P@ssw0rt123",         # dasselbe in Zeichenersetzung
    "Sommer2026!",         # steht in jeder Angriffsliste
    "qwertzuiop",          # Tastaturreihe
    "aaaaaaaaaaaa",        # zu wenig verschiedene Zeichen
])
def test_richtlinie_lehnt_ab(schlecht):
    assert pw_regeln.pruefen(schlecht) is not None


@pytest.mark.parametrize("gut", [
    "gelberstuhlamfenster",
    "KaffeeMitZimt7",
    "Regenschirm-Blau-42",
])
def test_richtlinie_laesst_brauchbare_durch(gut):
    assert pw_regeln.pruefen(gut) is None


def test_richtlinie_lehnt_eigene_daten_ab():
    assert pw_regeln.pruefen("oliver-ist-super", email="oliver@waehner.at")
    assert pw_regeln.pruefen("WaehnerWaehner", name="Oliver Waehner")


def test_benutzer_anlegen_prueft_richtlinie(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": admin_user.email,
                             "password": TEST_USER_PASSWORD})
    kopf = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    schwach = client.post("/api/users/", headers=kopf, json={
        "email": "neu@deinezeit.local", "full_name": "Neuer Mitarbeiter",
        "password": "geheim", "role": "employee",
    })
    assert schwach.status_code == 400

    stark = client.post("/api/users/", headers=kopf, json={
        "email": "neu@deinezeit.local", "full_name": "Neuer Mitarbeiter",
        "password": "Regenschirm-Blau-42", "role": "employee",
    })
    assert stark.status_code == 200, stark.text
