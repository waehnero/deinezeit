"""
Sicherheitsregeln des Mail-Imports (services/mail_sicherheit.py).

Bezug: Sicherheitsbefund „Zentrale Mailzugangsdaten können an einen frei
wählbaren IMAP-Server gesendet werden" (Bestandsaufnahme zu Commit 1a5787e);
den eigentlichen Angriff stellt test_mailimport_befund.py nach.

Grundsätze der Testreihe:
  * alle Zugangsdaten sind erfunden,
  * IMAP wird simuliert (imaplib ersetzt) bzw. — nur für die TLS-Prüfung —
    gegen einen Wegwerf-Server auf 127.0.0.1 mit selbst erzeugten
    Testzertifikaten gefahren,
  * Microsoft Graph wird nie aufgerufen (httpx ersetzt),
  * DNS wird simuliert; es verlässt kein Paket den Rechner.
"""
import datetime as dt
import imaplib
import ipaddress
import socket
import ssl
import threading

import pytest
from sqlalchemy import text

from app.models.mailimport import MailAccount, MailTaskSuggestion
from app.models.settings import Setting
from app.models.user import PermissionGroup
from app.services import mail_ingest, mail_sicherheit
from app.services.mail_sicherheit import MailSicherheitsFehler
from tests.conftest import TEST_USER_PASSWORD

ZENTRAL_USER = "zentral-office@firma.invalid"
ZENTRAL_PASSWORT = "Erfunden-Zentral-9f3c"
EIGENES_PASSWORT = "Erfunden-Eigen-71ab"
FIRMEN_HOST = "imap.firma.example"
FREMD_HOST = "mail.angreifer.example"
OEFFENTLICHE_IP = "81.10.20.30"


# ── Simulationen ──────────────────────────────────────────────────────────────
class _Imap:
    """Ersatz für imaplib: merkt sich Verbindungen und Anmeldungen."""

    verbindungen: list = []
    anmeldungen: list = []
    starttls_fehler = False

    def __init__(self, host="", port=None, *args, **kwargs):
        self.host = host
        self.port = port
        self.ssl_context = kwargs.get("ssl_context")
        _Imap.verbindungen.append((host, port, "ssl" if self.ssl_context else "plain"))

    def starttls(self, ssl_context=None):
        if _Imap.starttls_fehler:
            raise imaplib.IMAP4.error("STARTTLS not supported")
        _Imap.verbindungen.append((self.host, self.port, "starttls"))
        return ("OK", [b""])

    def login(self, user, password):
        _Imap.anmeldungen.append((self.host, user, password))
        return ("OK", [b""])

    def list(self):
        return ("OK", [b'(\\HasNoChildren) "/" "INBOX"'])

    def select(self, *a, **k):
        return ("OK", [b"0"])

    def search(self, *a):
        return ("OK", [b""])

    def logout(self):
        return ("BYE", [b""])

    def shutdown(self):
        pass


@pytest.fixture()
def imap(monkeypatch):
    _Imap.verbindungen = []
    _Imap.anmeldungen = []
    _Imap.starttls_fehler = False
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _Imap)
    monkeypatch.setattr(imaplib, "IMAP4", _Imap)
    return _Imap


@pytest.fixture()
def dns(monkeypatch):
    """Simuliertes DNS: Name -> Liste von IP-Adressen (Vorgabe: öffentlich)."""
    eintraege = {}

    def _getaddrinfo(host, port, *a, **k):
        try:
            ipaddress.ip_address(host)
            ips = [host]
        except ValueError:
            ips = eintraege.get(host, [OEFFENTLICHE_IP])
        out = []
        for ip in ips:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            out.append((fam, socket.SOCK_STREAM, 6, "", (ip, port)))
        return out

    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo)
    return eintraege


@pytest.fixture()
def kein_graph(monkeypatch):
    """Jeder Graph-Aufruf wäre ein Testfehler — es darf keiner stattfinden."""
    aufrufe = []

    def _verboten(*a, **k):
        aufrufe.append((a, k))
        raise AssertionError("Graph darf in diesem Test nicht aufgerufen werden")

    monkeypatch.setattr(mail_ingest.httpx, "post", _verboten)
    monkeypatch.setattr(mail_ingest.httpx, "get", _verboten)
    monkeypatch.setattr(mail_ingest.httpx, "patch", _verboten)
    return aufrufe


def _keine_ki(monkeypatch):
    monkeypatch.setattr(mail_ingest, "load_ki_settings",
                        lambda db: {"provider": "anthropic", "api_key_enc": None})
    monkeypatch.setattr(mail_ingest, "extract_tasks", lambda ki, mail: [])


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _login(client, email):
    client.headers.pop("Authorization", None)
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _als_admin(client):
    return _login(client, "admin@deinezeit.local")


def _als_mitarbeiter(client):
    return _login(client, "test@deinezeit.local")


def _zentrale_smtp(db, user=ZENTRAL_USER, pw=ZENTRAL_PASSWORT):
    for k, v in (("smtp_user", user), ("smtp_password", pw)):
        row = db.query(Setting).filter(Setting.key == k).first()
        if row:
            row.value = v
        else:
            db.add(Setting(key=k, value=v))
    db.commit()


def _zentrale_graph(db, mailbox="office@firma.example"):
    for k, v in (("ms_tenant_id", "firma.onmicrosoft.com"), ("ms_client_id", "app-123"),
                 ("ms_client_secret", "Erfunden-Graph-55aa"), ("smtp_from_email", mailbox)):
        db.add(Setting(key=k, value=v))
    db.commit()


def _gruppe(db, name, mitglieder=()):
    # Aufgabenrechte, damit die Mitglieder das Modul überhaupt erreichen —
    # die Freigabe des Mailkontos ist eine zusätzliche, eigene Hürde.
    g = PermissionGroup(name=name, rechte={"aufgaben": {
        "lesen": True, "schreiben": True, "loeschen": False, "umfang": "alle"}})
    g.users = list(mitglieder)
    db.add(g)
    db.commit()
    return g


def _zentrales_konto_als_admin(client, **extra):
    payload = {"name": "Office zentral", "protocol": "imap",
               "imap_host": FIRMEN_HOST, "imap_port": 993, "imap_ssl": True,
               "use_central_credentials": True, "is_global": True,
               "folder": "INBOX", **extra}
    resp = client.post("/api/mail-import/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _zentrale_anmeldungen():
    return [(h, u) for h, u, p in _Imap.anmeldungen if p == ZENTRAL_PASSWORT]


# ═══ 1. Nicht-Admin kann zentrale Zugangsdaten nicht umleiten ═════════════════
def test_mitarbeiter_kann_kein_persoenliches_konto_mit_zentralen_daten_anlegen(
        auth_client, db_session, imap, dns):
    _zentrale_smtp(db_session)
    for protokoll, extra in (("imap", {"imap_host": FREMD_HOST}),
                             ("graph", {"graph_mailbox": "chef@firma.example"})):
        resp = auth_client.post("/api/mail-import/accounts", json={
            "name": "x", "protocol": protokoll, "use_central_credentials": True,
            "folder": "INBOX", **extra})
        assert resp.status_code == 403
    assert db_session.query(MailAccount).count() == 0
    assert _Imap.anmeldungen == []


def test_mitarbeiter_kann_kein_globales_konto_anlegen(auth_client, db_session):
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": FREMD_HOST,
        "use_central_credentials": True, "is_global": True})
    assert resp.status_code == 403


def test_eingeschleuste_serverfelder_werden_ignoriert(auth_client, db_session):
    """owner_user_id/zentral_bindung bestimmt allein der Server."""
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT,
        "owner_user_id": None, "zentral_bindung": {"host": FREMD_HOST},
        "freigabe_alle": True})
    # freigabe_* an persönlichen Konten ist unzulässig
    assert resp.status_code == 400
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT,
        "owner_user_id": None, "zentral_bindung": {"host": FREMD_HOST}})
    assert resp.status_code == 201
    acc = db_session.query(MailAccount).one()
    assert acc.owner_user_id is not None
    assert acc.zentral_bindung is None


# ═══ 2. Nachträgliche Änderung öffnet den Weg nicht ═══════════════════════════
def test_nachtraegliches_einschalten_zentraler_daten_abgewiesen(
        auth_client, db_session, imap, dns):
    _zentrale_smtp(db_session)
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Mein Postfach", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT})
    konto_id = resp.json()["id"]

    resp = auth_client.put(f"/api/mail-import/accounts/{konto_id}", json={
        "imap_host": FREMD_HOST, "use_central_credentials": True})
    assert resp.status_code == 403
    db_session.expire_all()
    acc = db_session.get(MailAccount, konto_id)
    assert acc.use_central_credentials is False
    assert acc.imap_host == "imap.example.com"

    # Verbindungstest danach: eigene Zugangsdaten, nie die zentralen
    auth_client.get(f"/api/mail-import/accounts/{konto_id}/folders")
    assert _zentrale_anmeldungen() == []


def test_mitarbeiter_kann_zentrales_konto_nicht_aendern(client, admin_user, test_user,
                                                        db_session, imap, dns):
    _zentrale_smtp(db_session)
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_alle=True)
    _als_mitarbeiter(client)
    for aenderung in ({"imap_host": FREMD_HOST}, {"imap_port": 1993},
                      {"imap_ssl": False}, {"use_central_credentials": False},
                      {"freigabe_alle": False}):
        resp = client.put(f"/api/mail-import/accounts/{konto['id']}", json=aenderung)
        assert resp.status_code == 403, aenderung
    assert client.post(
        f"/api/mail-import/accounts/{konto['id']}/zentral-bestaetigen").status_code == 403
    db_session.expire_all()
    assert db_session.get(MailAccount, konto["id"]).imap_host == FIRMEN_HOST


def test_altes_persoenliches_konto_mit_zentralen_daten_ist_gesperrt(
        auth_client, test_user, db_session, imap, dns, monkeypatch):
    """Bestandskonto aus der Zeit vor der Behebung (direkt in der DB)."""
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    acc = MailAccount(owner_user_id=test_user.id, name="Alt", protocol="imap",
                      imap_host=FREMD_HOST, imap_ssl=True,
                      use_central_credentials=True, auto_scan=True)
    db_session.add(acc)
    db_session.commit()

    liste = auth_client.get("/api/mail-import/accounts").json()
    assert liste[0]["zentral_sperrgrund"] == mail_sicherheit.SPERRE_PERSOENLICH

    assert auth_client.get(f"/api/mail-import/accounts/{acc.id}/folders").status_code == 403
    assert auth_client.post(f"/api/mail-import/accounts/{acc.id}/scan").status_code == 403
    # Hintergrundimport: dieselbe Regel
    assert mail_ingest.auto_scan_durchlauf(db_session) == 0
    db_session.refresh(acc)
    assert acc.last_error == mail_sicherheit.SPERRE_PERSOENLICH
    assert _Imap.verbindungen == [] and _Imap.anmeldungen == []

    # Ausweg: auf eigene Zugangsdaten umstellen
    resp = auth_client.put(f"/api/mail-import/accounts/{acc.id}", json={
        "use_central_credentials": False, "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT})
    assert resp.status_code == 200, resp.text
    assert resp.json()["zentral_sperrgrund"] is None
    assert auth_client.get(f"/api/mail-import/accounts/{acc.id}/folders").status_code == 200
    assert _Imap.anmeldungen == [("imap.example.com", "ich@example.com", EIGENES_PASSWORT)]


# ═══ 3. Freigegebene Mitarbeiter nutzen ein zentrales Konto weiter ════════════
def test_freigegebener_mitarbeiter_nutzt_zentrales_konto(
        client, admin_user, test_user, db_session, imap, dns, monkeypatch):
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    team = _gruppe(db_session, "Office-Team", [test_user])
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_gruppen=[str(team.id)])
    assert konto["zentral_sperrgrund"] is None
    assert konto["freigabe_gruppen"] == [str(team.id)]

    _als_mitarbeiter(client)
    liste = client.get("/api/mail-import/accounts").json()
    assert isinstance(liste, list), liste
    assert [k["id"] for k in liste] == [konto["id"]]
    # Keine Zugangsdaten/Kennungen für Mitarbeiter
    assert liste[0]["imap_user"] is None
    assert liste[0]["freigabe_gruppen"] is None
    assert ZENTRAL_USER not in str(liste) and ZENTRAL_PASSWORT not in str(liste)

    resp = client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert resp.status_code == 200, resp.text
    # Anmeldung genau beim bestätigten Ziel, verschlüsselt
    assert _zentrale_anmeldungen() == [(FIRMEN_HOST, ZENTRAL_USER)]
    assert _Imap.verbindungen == [(FIRMEN_HOST, 993, "ssl")]

    # Verbindungstest (Verwalten) bleibt dem Admin vorbehalten
    assert client.get(f"/api/mail-import/accounts/{konto['id']}/folders").status_code == 403


def test_freigabe_fuer_alle(client, admin_user, test_user, db_session, imap, dns, monkeypatch):
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_alle=True)
    _als_mitarbeiter(client)
    assert client.post(f"/api/mail-import/accounts/{konto['id']}/scan").status_code == 200


# ═══ 4. Nicht freigegebene Benutzer werden abgewiesen ═════════════════════════
def test_nicht_freigegebener_mitarbeiter_abgewiesen(
        client, admin_user, test_user, db_session, imap, dns):
    _zentrale_smtp(db_session)
    andere = _gruppe(db_session, "Buchhaltung", [])
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_gruppen=[str(andere.id)])
    vorschlag = MailTaskSuggestion(account_id=konto["id"], message_id="<m@x>",
                                   title="Vertraulich")
    db_session.add(vorschlag)
    db_session.commit()

    _als_mitarbeiter(client)
    assert client.get("/api/mail-import/accounts").json() == []
    assert client.post(f"/api/mail-import/accounts/{konto['id']}/scan").status_code == 403
    assert client.get("/api/mail-import/suggestions").json() == []
    assert client.post(f"/api/mail-import/suggestions/{vorschlag.id}/accept",
                       json={}).status_code == 403
    assert client.post(f"/api/mail-import/suggestions/{vorschlag.id}/dismiss").status_code == 403
    assert _Imap.anmeldungen == []


def test_unbekannte_gruppe_in_freigabe_abgewiesen(client, admin_user, db_session):
    _zentrale_smtp(db_session)
    _als_admin(client)
    resp = client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": FIRMEN_HOST,
        "use_central_credentials": True, "is_global": True,
        "freigabe_gruppen": ["00000000-0000-0000-0000-000000000001"]})
    assert resp.status_code == 400


# ═══ 5. Persönliche Konten mit eigenen Zugangsdaten ═══════════════════════════
def test_persoenliches_konto_mit_eigenen_daten_funktioniert(
        auth_client, db_session, imap, dns, monkeypatch):
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Mein Postfach", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT, "imap_ssl": False})
    assert resp.status_code == 201, resp.text
    konto = resp.json()
    assert EIGENES_PASSWORT not in resp.text

    assert auth_client.get(f"/api/mail-import/accounts/{konto['id']}/folders").json() == ["INBOX"]
    assert auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan").status_code == 200
    # STARTTLS (Port 143) — verschlüsselt vor der Anmeldung, nie zentral
    assert ("imap.example.com", 143, "starttls") in _Imap.verbindungen
    assert {u for _, u, _ in _Imap.anmeldungen} == {"ich@example.com"}
    assert _zentrale_anmeldungen() == []


def test_persoenliches_konto_ins_interne_netz_abgewiesen(
        auth_client, db_session, imap, dns):
    dns["intern.example.com"] = ["10.0.0.5"]
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": "intern.example.com",
        "imap_user": "ich", "secret": EIGENES_PASSWORT})
    resp = auth_client.get(f"/api/mail-import/accounts/{resp.json()['id']}/folders")
    assert resp.status_code == 400
    # Gleiche Meldung wie „nicht auflösbar" und ohne IP-Adresse — der
    # Verbindungstest darf nicht zum Auskundschaften des internen Netzes taugen
    assert "nicht erreichbar oder nicht freigegeben" in resp.json()["detail"]
    assert "10.0.0.5" not in resp.text
    assert _Imap.verbindungen == []


# ═══ 6. Verbindungstest, manueller und Hintergrundimport: dieselben Regeln ═════
def test_identitaetswechsel_sperrt_bis_zur_bestaetigung(
        client, admin_user, test_user, db_session, imap, dns, monkeypatch):
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_alle=True, auto_scan=True)

    # Credential-Wechsel: anderer zentraler SMTP-Benutzer
    _zentrale_smtp(db_session, user="neu@firma.invalid")
    acc = db_session.get(MailAccount, konto["id"])
    assert mail_sicherheit.zentral_sperrgrund(db_session, acc) == mail_sicherheit.SPERRE_GEAENDERT

    assert client.get(f"/api/mail-import/accounts/{konto['id']}/folders").status_code == 403
    assert client.post(f"/api/mail-import/accounts/{konto['id']}/scan").status_code == 403
    assert mail_ingest.auto_scan_durchlauf(db_session) == 0
    assert _Imap.anmeldungen == []

    # Admin bestätigt ausdrücklich -> wieder nutzbar, für alle Wege
    resp = client.post(f"/api/mail-import/accounts/{konto['id']}/zentral-bestaetigen")
    assert resp.status_code == 200
    assert resp.json()["zentral_sperrgrund"] is None
    db_session.expire_all()
    acc = db_session.get(MailAccount, konto["id"])
    acc.last_scan_at = None
    db_session.commit()
    assert mail_ingest.auto_scan_durchlauf(db_session) == 1
    assert client.get(f"/api/mail-import/accounts/{konto['id']}/folders").status_code == 200
    assert {u for _, u, _ in _Imap.anmeldungen} == {"neu@firma.invalid"}


def test_ziel_im_datenbestand_veraendert_wird_nicht_genutzt(
        client, admin_user, test_user, db_session, imap, dns, monkeypatch):
    """Selbst wenn das Ziel an der Oberfläche/API vorbei geändert wird."""
    _zentrale_smtp(db_session)
    _keine_ki(monkeypatch)
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_alle=True, auto_scan=True)
    db_session.execute(text("UPDATE mail_accounts SET imap_host = :h WHERE id = :i"),
                       {"h": FREMD_HOST, "i": konto["id"]})
    db_session.commit()
    db_session.expire_all()

    _als_mitarbeiter(client)
    assert client.post(f"/api/mail-import/accounts/{konto['id']}/scan").status_code == 403
    assert mail_ingest.auto_scan_durchlauf(db_session) == 0
    acc = db_session.get(MailAccount, konto["id"])
    with pytest.raises(MailSicherheitsFehler):
        mail_ingest._imap_connect(db_session, acc)
    assert _Imap.verbindungen == [] and _Imap.anmeldungen == []


def test_admin_aenderung_des_ziels_bindet_neu(client, admin_user, db_session, imap, dns):
    _zentrale_smtp(db_session)
    _als_admin(client)
    konto = _zentrales_konto_als_admin(client, freigabe_alle=True)
    resp = client.put(f"/api/mail-import/accounts/{konto['id']}",
                      json={"imap_host": "imap2.firma.example"})
    assert resp.status_code == 200
    assert resp.json()["zentral_sperrgrund"] is None
    acc = db_session.get(MailAccount, konto["id"])
    assert acc.zentral_bindung["host"] == "imap2.firma.example"
    # Abschalten der zentralen Nutzung lässt die Bindung verfallen
    client.put(f"/api/mail-import/accounts/{konto['id']}",
               json={"use_central_credentials": False, "imap_user": "x", "secret": "y"})
    db_session.expire_all()
    assert db_session.get(MailAccount, konto["id"]).zentral_bindung is None


# ═══ 7. Graph: zentrale Anwendungsrechte nur für die gebundene Mailbox ════════
def test_graph_mitarbeiter_kann_keine_mailbox_waehlen(auth_client, db_session, kein_graph):
    _zentrale_graph(db_session)
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Chef", "protocol": "graph", "use_central_credentials": True,
        "graph_mailbox": "chef@firma.example", "folder": "inbox"})
    assert resp.status_code == 403
    assert kein_graph == []


def test_graph_mailbox_bindung(client, admin_user, test_user, db_session, kein_graph, monkeypatch):
    _zentrale_graph(db_session)
    _als_admin(client)
    resp = client.post("/api/mail-import/accounts", json={
        "name": "Office", "protocol": "graph", "use_central_credentials": True,
        "graph_mailbox": "office@firma.example", "is_global": True,
        "freigabe_alle": True, "folder": "inbox"})
    assert resp.status_code == 201, resp.text
    konto_id = resp.json()["id"]

    acc = db_session.get(MailAccount, konto_id)
    tenant, client_id, _, mailbox = mail_ingest._graph_credentials(db_session, acc)
    assert mailbox == "office@firma.example"

    # Mailbox an der API vorbei auf ein fremdes Postfach umgebogen
    db_session.execute(text("UPDATE mail_accounts SET graph_mailbox = 'chef@firma.example' "
                            "WHERE id = :i"), {"i": konto_id})
    db_session.commit()
    db_session.expire_all()
    acc = db_session.get(MailAccount, konto_id)
    with pytest.raises(MailSicherheitsFehler):
        mail_ingest._graph_credentials(db_session, acc)
    _als_mitarbeiter(client)
    assert client.post(f"/api/mail-import/accounts/{konto_id}/scan").status_code == 403
    with pytest.raises(MailSicherheitsFehler):
        mail_ingest.graph_set_flag(db_session, acc, "msg-1", "complete")
    assert kein_graph == []


def test_graph_mailbox_ohne_pfadtricks(auth_client):
    for mailbox in ("a@b.example/messages", "../users/chef@firma.example", "x?y@z.example"):
        resp = auth_client.post("/api/mail-import/accounts", json={
            "name": "x", "protocol": "graph", "graph_tenant_id": "t.onmicrosoft.com",
            "graph_client_id": "c", "graph_mailbox": mailbox, "secret": "s"})
        assert resp.status_code == 400, mailbox
    assert mail_ingest._url_teil("a/b?c#d") == "a%2Fb%3Fc%23d"


# ═══ 8. TLS: Zertifikats- und Hostnamenfehler brechen vor der Anmeldung ab ════
def _zertifikat(cn, ausgeber=None):
    """Erzeugt (Zertifikat-PEM, Schlüssel-PEM) — selbstsigniert oder von ``ausgeber``."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    jetzt = dt.datetime.now(dt.timezone.utc)
    issuer_name, issuer_key = (ausgeber[2], ausgeber[3]) if ausgeber else (name, key)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(issuer_name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(jetzt - dt.timedelta(minutes=5))
               .not_valid_after(jetzt + dt.timedelta(days=1)))
    if ausgeber:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), False)
    else:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
    cert = builder.sign(issuer_key, hashes.SHA256())
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode(),
            name, key)


class _TlsImapServer:
    """Minimaler IMAP-Server mit TLS auf 127.0.0.1 — merkt sich LOGIN-Versuche."""

    def __init__(self, tmp_path, cert_pem, key_pem):
        (tmp_path / "c.pem").write_text(cert_pem)
        (tmp_path / "k.pem").write_text(key_pem)
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(tmp_path / "c.pem", tmp_path / "k.pem")
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.sock.settimeout(10)
        self.port = self.sock.getsockname()[1]
        self.logins = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            roh, _ = self.sock.accept()
            try:
                conn = self.ctx.wrap_socket(roh, server_side=True)
            except (ssl.SSLError, OSError):
                roh.close()
                return
            f = conn.makefile("rwb")
            f.write(b"* OK [CAPABILITY IMAP4rev1] Test bereit\r\n")
            f.flush()
            for zeile in f:
                tag, befehl = zeile.strip().split(b" ", 2)[:2]
                if befehl.upper() == b"CAPABILITY":
                    f.write(b"* CAPABILITY IMAP4rev1\r\n" + tag + b" OK fertig\r\n")
                elif befehl.upper() == b"LOGIN":
                    self.logins.append(zeile)
                    f.write(tag + b" OK angemeldet\r\n")
                elif befehl.upper() == b"LOGOUT":
                    f.write(b"* BYE ade\r\n" + tag + b" OK fertig\r\n")
                    f.flush()
                    break
                else:
                    f.write(tag + b" BAD unbekannt\r\n")
                f.flush()
            conn.close()
        except (OSError, ValueError):
            pass
        finally:
            self.sock.close()


def _tls_konto(db, host, port):
    acc = MailAccount(name="TLS", protocol="imap", imap_host=host, imap_port=port,
                      imap_ssl=True, imap_user="ich@firma.example",
                      secret_enc=mail_ingest.encrypt_secret(EIGENES_PASSWORT))
    # Interner Testserver auf Zufallsport: Freigabe genau für host:port
    db.add(Setting(key=mail_sicherheit.SETTING_INTERNE_ZIELE, value=f"{host}:{port}"))
    db.commit()
    return acc


def test_tls_selbstsigniertes_zertifikat_bricht_vor_anmeldung_ab(
        db_session, dns, tmp_path):
    cert, key, _, _ = _zertifikat("imap.firma.example")
    server = _TlsImapServer(tmp_path, cert, key)
    dns["imap.firma.example"] = ["127.0.0.1"]
    acc = _tls_konto(db_session, "imap.firma.example", server.port)
    with pytest.raises(ssl.SSLCertVerificationError):
        mail_ingest._imap_connect(db_session, acc)
    server.thread.join(5)
    assert server.logins == []


def test_tls_falscher_hostname_bricht_vor_anmeldung_ab(db_session, dns, tmp_path):
    ca = _zertifikat("Firmen-Test-CA")
    cert, key, _, _ = _zertifikat("anderer.firma.example", ausgeber=ca)
    server = _TlsImapServer(tmp_path, cert, key)
    dns["imap.firma.example"] = ["127.0.0.1"]
    db_session.add(Setting(key=mail_sicherheit.SETTING_CA_ZERTIFIKATE, value=ca[0]))
    acc = _tls_konto(db_session, "imap.firma.example", server.port)
    with pytest.raises(ssl.SSLCertVerificationError):
        mail_ingest._imap_connect(db_session, acc)
    server.thread.join(5)
    assert server.logins == []


def test_tls_interner_server_mit_firmen_ca_funktioniert(db_session, dns, tmp_path):
    """Interne Mailserver: ausdrücklich freigegebenes Ziel + hinterlegte CA."""
    ca = _zertifikat("Firmen-Test-CA")
    cert, key, _, _ = _zertifikat("imap.firma.example", ausgeber=ca)
    server = _TlsImapServer(tmp_path, cert, key)
    dns["imap.firma.example"] = ["127.0.0.1"]
    db_session.add(Setting(key=mail_sicherheit.SETTING_CA_ZERTIFIKATE, value=ca[0]))
    acc = _tls_konto(db_session, "imap.firma.example", server.port)
    conn = mail_ingest._imap_connect(db_session, acc)
    conn.logout()
    server.thread.join(5)
    assert len(server.logins) == 1


def test_tls_kontext_prueft_immer(db_session):
    ctx = mail_sicherheit.tls_kontext(db_session)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_starttls_fehlt_kein_klartext_rueckfall(db_session, imap, dns):
    imap.starttls_fehler = True
    acc = MailAccount(name="x", protocol="imap", imap_host="imap.example.com",
                      imap_ssl=False, imap_user="ich",
                      secret_enc=mail_ingest.encrypt_secret(EIGENES_PASSWORT))
    with pytest.raises(MailSicherheitsFehler):
        mail_ingest._imap_connect(db_session, acc)
    assert imap.anmeldungen == []


# ═══ 9. Interne Ziele: Loopback, privat, Metadaten, IPv6, DNS ═════════════════
@pytest.mark.parametrize("ips", [
    ["127.0.0.1"], ["::1"], ["10.1.2.3"], ["172.16.0.9"], ["192.168.1.1"],
    ["169.254.169.254"], ["fd00::1"], ["fe80::1"], ["::ffff:127.0.0.1"],
    ["100.64.0.1"], ["0.0.0.0"], ["::"], ["224.0.0.1"], ["fec0::1"],
    ["64:ff9b::7f00:1"], ["2001::1"], ["2002:7f00:1::1"], ["::127.0.0.1"],
    [OEFFENTLICHE_IP, "10.0.0.1"],          # gemischte Antwort: alle müssen passen
])
def test_interne_adressen_abgewiesen(db_session, dns, ips):
    dns["mail.example.com"] = ips
    with pytest.raises(MailSicherheitsFehler):
        mail_sicherheit.ziel_aufloesen(db_session, "mail.example.com", 993)


@pytest.mark.parametrize("host", ["127.0.0.1", "[::1]", "169.254.169.254",
                                  "localhost/x", "a b", "mail.example.com:25", ""])
def test_ungueltige_oder_interne_hosts_direkt(db_session, dns, host):
    dns["localhost"] = ["127.0.0.1"]
    with pytest.raises(MailSicherheitsFehler):
        mail_sicherheit.ziel_aufloesen(db_session, host, 993)


def test_oeffentliches_ziel_wird_auf_gepruefte_ip_festgelegt(db_session, dns):
    dns["mail.example.com"] = [OEFFENTLICHE_IP]
    assert mail_sicherheit.ziel_aufloesen(db_session, "mail.example.com", 993) == OEFFENTLICHE_IP


def test_admin_freigabe_interner_ziele(db_session, dns):
    dns["exchange.intern.example"] = ["10.20.0.5"]
    dns["anderer.intern.example"] = ["10.30.0.5"]
    db_session.add(Setting(key=mail_sicherheit.SETTING_INTERNE_ZIELE,
                           value="exchange.intern.example\n10.40.0.0/24"))
    db_session.commit()
    assert mail_sicherheit.ziel_aufloesen(db_session, "exchange.intern.example", 993) == "10.20.0.5"
    assert mail_sicherheit.ziel_aufloesen(db_session, "10.40.0.7", 993) == "10.40.0.7"
    # Freigabe gilt nur für das Freigegebene — und nur auf den IMAP-Ports
    with pytest.raises(MailSicherheitsFehler):
        mail_sicherheit.ziel_aufloesen(db_session, "anderer.intern.example", 993)
    with pytest.raises(MailSicherheitsFehler):
        mail_sicherheit.ziel_aufloesen(db_session, "exchange.intern.example", 22)


def test_admin_freigabe_mit_port(db_session, dns):
    dns["exchange.intern.example"] = ["10.20.0.5"]
    db_session.add(Setting(key=mail_sicherheit.SETTING_INTERNE_ZIELE,
                           value="exchange.intern.example:1993, [fd00::/64]:1143"))
    db_session.commit()
    assert mail_sicherheit.ziel_aufloesen(db_session, "exchange.intern.example", 1993)
    assert mail_sicherheit.ziel_aufloesen(db_session, "fd00::5", 1143) == "fd00::5"
    for host, port in (("exchange.intern.example", 993), ("fd00::5", 993)):
        with pytest.raises(MailSicherheitsFehler):
            mail_sicherheit.ziel_aufloesen(db_session, host, port)
    ok, _ = mail_sicherheit.interne_ziele_gueltig(["a.example:99999"])
    assert not ok
    with pytest.raises(MailSicherheitsFehler):
        mail_sicherheit.ziel_aufloesen(db_session, "169.254.169.254", 993)


def test_gepruefte_ip_wird_tatsaechlich_verwendet(monkeypatch):
    """Kein zweiter DNS-Abruf beim Verbinden (DNS-Rebinding)."""
    ziele = []

    def _connect(addr, timeout=None, *a, **k):
        ziele.append(addr)
        raise OSError("simuliert")

    monkeypatch.setattr(socket, "create_connection", _connect)
    with pytest.raises(OSError):
        mail_ingest._imap_oeffnen("imap.example.com", 993, OEFFENTLICHE_IP, True,
                                  ssl.create_default_context())
    assert ziele == [(OEFFENTLICHE_IP, 993)]
    # Mehrere geprüfte Adressen: der Reihe nach, keine anderen
    ziele.clear()
    with pytest.raises(OSError):
        mail_ingest._imap_oeffnen("imap.example.com", 993, ["2a01::1", OEFFENTLICHE_IP],
                                  True, ssl.create_default_context())
    assert ziele == [("2a01::1", 993), (OEFFENTLICHE_IP, 993)]


def test_update_mit_null_fuehrt_nicht_zu_serverfehler(auth_client):
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich", "secret": EIGENES_PASSWORT})
    resp = auth_client.put(f"/api/mail-import/accounts/{resp.json()['id']}",
                           json={"use_central_credentials": None, "imap_ssl": None})
    assert resp.status_code == 200
    assert resp.json()["use_central_credentials"] is False


# ═══ 10. Keine Geheimnisse in Antworten, Fehlern und Logs ═════════════════════
def test_keine_geheimnisse_in_fehlern_und_logs(auth_client, db_session, imap, dns, caplog,
                                               monkeypatch):
    class _Abweisend(_Imap):
        def login(self, user, password):
            raise imaplib.IMAP4.error(f"LOGIN abgelehnt fuer {user}/{password}")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _Abweisend)
    caplog.set_level("INFO")
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "x", "protocol": "imap", "imap_host": "imap.example.com",
        "imap_user": "ich@example.com", "secret": EIGENES_PASSWORT})
    konto_id = resp.json()["id"]
    resp = auth_client.get(f"/api/mail-import/accounts/{konto_id}/folders")
    assert resp.status_code == 400
    assert EIGENES_PASSWORT not in resp.text
    resp = auth_client.post(f"/api/mail-import/accounts/{konto_id}/scan")
    assert EIGENES_PASSWORT not in resp.text
    liste = auth_client.get("/api/mail-import/accounts")
    assert EIGENES_PASSWORT not in liste.text
    assert "secret_enc" not in liste.text
    assert EIGENES_PASSWORT not in caplog.text
    # Konfigurationsänderung wird protokolliert — ohne Werte
    assert any("Mail-Konto angelegt" in r.getMessage() for r in caplog.records)


# ═══ 11. Admin-Sicherheitsregeln ══════════════════════════════════════════════
def test_sicherheitsregeln_nur_admin(auth_client):
    assert auth_client.get("/api/mail-import/sicherheit").status_code == 403
    assert auth_client.put("/api/mail-import/sicherheit",
                           json={"interne_ziele": ["10.0.0.0/8"]}).status_code == 403


def test_sicherheitsregeln_speichern_und_pruefen(client, admin_user, db_session):
    _als_admin(client)
    resp = client.put("/api/mail-import/sicherheit", json={
        "interne_ziele": ["Exchange.Intern.Example", "10.40.0.0/24"],
        "ca_zertifikate": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["interne_ziele"] == ["exchange.intern.example", "10.40.0.0/24"]
    assert client.put("/api/mail-import/sicherheit",
                      json={"interne_ziele": ["a/b"]}).status_code == 400
    assert client.put("/api/mail-import/sicherheit",
                      json={"ca_zertifikate": "kein pem"}).status_code == 400
