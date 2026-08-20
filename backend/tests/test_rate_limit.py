"""
Anfragebremse: gilt je Absender, nicht für alle gemeinsam
=========================================================

Der Fehler, den diese Tests festhalten (gefunden 18.08.2026): Beide Limiter
benutzten ``get_remote_address``, also ``request.client.host``. Hinter nginx
ist das immer die Adresse des Proxy-Containers — damit teilten sich **alle**
Benutzer der Installation dieselben 200 Anfragen und 10 Anmeldungen pro Minute.

Das ist besonders tückisch, weil es lokal und in den Tests nie auffällt: Ohne
Proxy stimmt ``request.client.host``. Erst im echten Betrieb hinter nginx
laufen alle auf denselben Zähler, und dann sieht es aus wie ein sporadischer
Aussetzer der Anwendung.
"""
import pytest

from app.core.netz import echte_ip
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


class _Anfrage:
    """Das Nötigste einer Request für ``echte_ip``."""
    def __init__(self, headers=None, client_host="127.0.0.1"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": client_host})() if client_host else None


# ── Adressermittlung ─────────────────────────────────────────────────────────

def test_x_real_ip_gewinnt():
    """nginx setzt den Header selbst und überschreibt einen mitgeschickten Wert."""
    ip = echte_ip(_Anfrage({"x-real-ip": "89.144.200.10",
                            "x-forwarded-for": "6.6.6.6, 89.144.200.10"}))
    assert ip == "89.144.200.10"


def test_ohne_real_ip_zaehlt_der_letzte_eintrag_der_kette():
    """Der vorderste Eintrag stammt womöglich vom Aufrufer selbst.

    Nähme man ihn, könnte sich jeder mit einem erfundenen Header eine eigene,
    leere Zählung verschaffen — die Bremse wäre wirkungslos.
    """
    ip = echte_ip(_Anfrage({"x-forwarded-for": "6.6.6.6, 10.0.0.5"}))
    assert ip == "10.0.0.5"


def test_ohne_proxy_gilt_die_verbindungsadresse():
    assert echte_ip(_Anfrage(client_host="203.0.113.9")) == "203.0.113.9"


def test_ohne_jede_angabe_kein_leerer_schluessel():
    """Ein leerer Schlüssel würfe alle Aufrufer wieder auf denselben Topf."""
    assert echte_ip(_Anfrage(headers={}, client_host=None)) == "unbekannt"


# ── Verdrahtung ──────────────────────────────────────────────────────────────

def test_beide_limiter_nutzen_die_echte_adresse():
    """Regressionsschutz für genau den Fehler.

    Es gibt zwei Limiter-Instanzen (App-weit in ``main``, strenger in ``auth``).
    Eine davon zu übersehen ist der wahrscheinlichste Rückfall.
    """
    from app.api.auth import limiter as auth_limiter
    from app.main import limiter as app_limiter

    assert app_limiter._key_func is echte_ip
    assert auth_limiter._key_func is echte_ip


# ── Wirkung am Endpunkt ──────────────────────────────────────────────────────

@pytest.fixture()
def bremse_an():
    """Die Bremse für einen Test scharf schalten.

    ``conftest`` schaltet sie global ab, weil sonst die gesamte Testreihe nach
    zehn Anmeldungen stehen bliebe.
    """
    from app.api.auth import limiter as auth_limiter
    from app.main import limiter as app_limiter

    app_limiter.enabled = True
    auth_limiter.enabled = True
    # Zähler leeren, damit vorherige Tests nicht hineinspielen
    app_limiter.reset()
    auth_limiter.reset()
    yield
    app_limiter.enabled = False
    auth_limiter.enabled = False
    app_limiter.reset()
    auth_limiter.reset()


def _anmelden(client, ip):
    return client.post("/api/auth/login",
                       json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
                       headers={"X-Real-IP": ip})


def test_zu_viele_anmeldungen_von_einer_adresse_werden_gebremst(
        client, test_user, bremse_an):
    letzte = None
    for _ in range(12):
        letzte = _anmelden(client, "198.51.100.1")
    assert letzte.status_code == 429, \
        "Nach zehn Anmeldungen je Minute muss die Bremse greifen"


def test_andere_adresse_hat_ihr_eigenes_kontingent(client, test_user, bremse_an):
    """Der Kern der Sache: Ein Kollege darf sich anmelden können, auch wenn
    jemand anderes gerade das Kontingent ausgeschöpft hat."""
    for _ in range(12):
        _anmelden(client, "198.51.100.2")

    andere = _anmelden(client, "198.51.100.3")
    assert andere.status_code == 200, \
        ("Die zweite Adresse hat ihr eigenes Kontingent — sonst gilt das Limit "
         "für die gesamte Installation gemeinsam")
