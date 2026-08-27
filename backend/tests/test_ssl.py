"""
Überwachung des HTTPS-Zertifikats
=================================

Anlass: Am 27.08.2026 ist das Zertifikat abgelaufen, obwohl eine automatische
Erneuerung eingerichtet war. Der certbot-Container lief nach einem Server-
Neustart nicht wieder an, und nginx liest ein erneuertes Zertifikat nicht von
selbst neu ein. Beides ist repariert — aber der eigentliche Fehler war, dass
es wochenlang niemand bemerkt hat.

Diese Tests sichern deshalb genau den Melder ab. Sie erzeugen jeweils ein
echtes, selbst signiertes Zertifikat mit einem gewünschten Ablaufdatum und
prüfen, was die Anwendung daraus macht. Wichtig ist besonders der Fall
„Zertifikat noch lange gültig, aber die Automatik steht" — so fängt jeder
Zertifikatsausfall an, und nur dort bleiben noch Wochen zum Reagieren.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import ssl_service
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

TEST_ADMIN_EMAIL = "admin@deinezeit.local"
TEST_ADMIN_PASSWORD = TEST_USER_PASSWORD


# ── Hilfsmittel ───────────────────────────────────────────────────────────────

def _zertifikat_anlegen(verzeichnis, domain: str, gueltig_tage: int):
    """Legt unter ``verzeichnis`` eine Let's-Encrypt-ähnliche Ordnerstruktur an
    und schreibt ein selbst signiertes Zertifikat mit der gewünschten
    Restlaufzeit hinein. Gibt den Pfad zurück, der als LETSENCRYPT_DIR dient.

    Negative Werte erzeugen ein bereits abgelaufenes Zertifikat.
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    live = verzeichnis / "live" / domain
    live.mkdir(parents=True, exist_ok=True)

    schluessel = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    jetzt = datetime.now(timezone.utc)
    bauer = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(schluessel.public_key())
        .serial_number(x509.random_serial_number())
    )
    # 90 Tage vor dem Ablauf ausgestellt — wie bei Let's Encrypt. Die
    # ..._utc-Setter gibt es ab cryptography 42; der Rückfall hält den Test
    # auch mit älteren Versionen lauffähig.
    beginn = jetzt + timedelta(days=gueltig_tage - 90)
    ende   = jetzt + timedelta(days=gueltig_tage)
    if hasattr(bauer, "not_valid_before_utc"):
        bauer = bauer.not_valid_before_utc(beginn).not_valid_after_utc(ende)
    else:                                                    # pragma: no cover
        bauer = (bauer.not_valid_before(beginn.replace(tzinfo=None))
                      .not_valid_after(ende.replace(tzinfo=None)))
    zertifikat = bauer.sign(schluessel, hashes.SHA256())
    (live / "fullchain.pem").write_bytes(
        zertifikat.public_bytes(serialization.Encoding.PEM)
    )
    return str(verzeichnis)


@pytest.fixture()
def zertifikat(tmp_path, monkeypatch):
    """Baut ein Zertifikat mit frei wählbarer Restlaufzeit und hängt es dem
    ssl_service unter. Die Automatik gilt dabei als laufend, sofern der Test
    nichts anderes sagt."""
    def _bauen(gueltig_tage: int, domain: str = "test.deinezeit.local",
               automatik: bool = True):
        pfad = _zertifikat_anlegen(tmp_path, domain, gueltig_tage)
        monkeypatch.setattr(ssl_service, "LETSENCRYPT_DIR", pfad)
        monkeypatch.setattr(ssl_service, "_automatik_laeuft", lambda: automatik)
        return pfad
    return _bauen


# ── Restlaufzeit richtig einstufen ───────────────────────────────────────────

def test_langes_zertifikat_ist_in_ordnung(zertifikat):
    zertifikat(75)
    zustand = ssl_service.zertifikat_status()
    assert zustand["status"] == "ok"
    assert zustand["domain"] == "test.deinezeit.local"
    # Rundung: 75 Tage können je nach Uhrzeit als 74 herauskommen.
    assert zustand["tage_verbleibend"] in (74, 75)


def test_unter_21_tagen_wird_gewarnt(zertifikat):
    """Ab hier ist etwas schiefgelaufen: Let's Encrypt hätte bei 30 Tagen
    Restlaufzeit längst erneuert."""
    zertifikat(15)
    assert ssl_service.zertifikat_status()["status"] == "warnung"


def test_unter_7_tagen_ist_kritisch(zertifikat):
    zertifikat(3)
    assert ssl_service.zertifikat_status()["status"] == "kritisch"


def test_abgelaufenes_zertifikat_wird_als_solches_erkannt(zertifikat):
    zertifikat(-2)
    zustand = ssl_service.zertifikat_status()
    assert zustand["status"] == "abgelaufen"
    assert zustand["tage_verbleibend"] < 0


def test_ohne_zertifikat_kein_fehlalarm(tmp_path, monkeypatch):
    """Die lokale Entwicklungsinstanz läuft ohne HTTPS. Sie darf deswegen
    nicht dauernd Alarm schlagen."""
    monkeypatch.setattr(ssl_service, "LETSENCRYPT_DIR", str(tmp_path / "leer"))
    monkeypatch.setattr(ssl_service, "_automatik_laeuft", lambda: None)
    assert ssl_service.zertifikat_status()["status"] == "nicht_konfiguriert"


# ── Der eigentliche Frühwarner ───────────────────────────────────────────────

def test_stehengebliebene_automatik_warnt_trotz_gueltigem_zertifikat(zertifikat):
    """Der Fall, der am 27.08.2026 gefehlt hat.

    Das Zertifikat ist noch 75 Tage gültig — alles sieht bestens aus. Aber die
    Erneuerungsschleife läuft nicht mehr. Ohne diese Warnung merkt es niemand,
    bis die Seite eines Morgens nicht mehr aufgeht."""
    zertifikat(75, automatik=False)
    zustand = ssl_service.zertifikat_status()
    assert zustand["status"] == "warnung"
    assert zustand["automatik_laeuft"] is False


def test_unbekannte_automatik_ist_keine_warnung(zertifikat):
    """Ohne Docker-Socket (lokal) lässt sich der Zustand nicht feststellen.
    Nichtwissen darf nicht als Störung durchgehen — sonst gewöhnt man sich an
    eine rote Meldung und übersieht die echte."""
    zertifikat(75, automatik=None)
    assert ssl_service.zertifikat_status()["status"] == "ok"


# ── E-Mail an die Administratoren ────────────────────────────────────────────

def test_warnung_geht_an_alle_admins(db_session, admin_user, test_user,
                                     zertifikat, monkeypatch):
    zertifikat(4)
    versendet = []
    # ssl_service importiert send_email erst beim Aufruf aus email_service —
    # deshalb dort patchen, nicht am ssl_service-Modul.
    monkeypatch.setattr("app.services.email_service.send_email",
                        lambda **k: versendet.append(k["to_email"]))

    ergebnis = ssl_service.pruefen_und_warnen(db_session)

    assert ergebnis["mails_verschickt"] == 1
    assert versendet == [TEST_ADMIN_EMAIL]      # nicht an den Mitarbeiter


def test_bei_ordnung_keine_mail(db_session, admin_user, zertifikat, monkeypatch):
    zertifikat(75)
    versendet = []
    monkeypatch.setattr("app.services.email_service.send_email",
                        lambda **k: versendet.append(k["to_email"]))

    ssl_service.pruefen_und_warnen(db_session)
    assert versendet == []


def test_keine_taegliche_mailflut_bei_milder_warnung(db_session, admin_user,
                                                     zertifikat, monkeypatch):
    """Bei 15 Tagen Restlaufzeit reicht eine Mail alle drei Tage. Wer täglich
    dieselbe Warnung bekommt, filtert sie irgendwann weg — und übersieht dann
    auch die kritische."""
    zertifikat(15)
    versendet = []
    monkeypatch.setattr("app.services.email_service.send_email",
                        lambda **k: versendet.append(k["to_email"]))

    ssl_service.pruefen_und_warnen(db_session)
    ssl_service.pruefen_und_warnen(db_session)      # sofort danach nochmal

    assert len(versendet) == 1, "Die zweite Prüfung hätte nicht mailen dürfen"


def test_kritisch_meldet_sich_taeglich(db_session, admin_user, zertifikat,
                                       monkeypatch):
    """Unter 7 Tagen gilt die Sperre nur einen Tag. Hier ist Hartnäckigkeit
    wichtiger als Ruhe."""
    from app.models.settings import Setting
    zertifikat(3)
    versendet = []
    monkeypatch.setattr("app.services.email_service.send_email",
                        lambda **k: versendet.append(k["to_email"]))

    ssl_service.pruefen_und_warnen(db_session)

    # Letzte Warnung künstlich auf "vor 25 Stunden" setzen.
    row = db_session.query(Setting).filter(Setting.key == "ssl_warn_last_at").first()
    assert row is not None, "Der Zeitpunkt der Warnung wurde nicht gespeichert"
    row.value = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    db_session.commit()

    ssl_service.pruefen_und_warnen(db_session)
    assert len(versendet) == 2


# ── Endpunkt ─────────────────────────────────────────────────────────────────

def _anmelden(client, email, passwort):
    resp = client.post("/api/auth/login", json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_endpunkt_nur_fuer_admins(client, test_user):
    """Ob die Erneuerungsautomatik ausgefallen ist, sagt einem Angreifer, wann
    der Server angreifbar wird. Das gehört nicht in jede Hand."""
    kopf = _anmelden(client, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    assert client.get("/api/system/ssl-status", headers=kopf).status_code == 403


def test_endpunkt_liefert_den_zustand(client, admin_user, zertifikat):
    zertifikat(15)
    kopf = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)

    resp = client.get("/api/system/ssl-status", headers=kopf)
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["status"] == "warnung"
    assert daten["domain"] == "test.deinezeit.local"
    assert daten["gueltig_bis"]
    assert daten["meldung"]


def test_endpunkt_bleibt_stehen_wenn_das_lesen_scheitert(client, admin_user,
                                                          monkeypatch):
    """Die System-Seite darf nicht ausfallen, nur weil das Zertifikat gerade
    nicht lesbar ist — dort steht auch der Update-Knopf."""
    def _kaputt():
        raise OSError("Verzeichnis nicht lesbar")
    monkeypatch.setattr(ssl_service, "zertifikat_status", _kaputt)

    kopf = _anmelden(client, TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    resp = client.get("/api/system/ssl-status", headers=kopf)
    assert resp.status_code == 200
    assert resp.json()["status"] == "nicht_konfiguriert"
