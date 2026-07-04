"""
Tests für den Mail-Import (Aufgabenmodul, Etappe 3).

Mail-Abruf (IMAP/Graph) und KI-Aufrufe werden gemockt — getestet werden
Rechte, Verschlüsselung, Scan-Ablauf und der Bestätigungs-Workflow.
"""
from datetime import datetime, timezone

from tests.conftest import TEST_USER_PASSWORD
from app.services import mail_ingest


def _admin_client(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": "admin@deinezeit.local",
                             "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def _imap_konto(auth_client, **overrides):
    payload = {
        "name": "Mein Postfach", "protocol": "imap",
        "imap_host": "imap.example.com", "imap_user": "user@example.com",
        "secret": "geheim123", "folder": "INBOX", **overrides,
    }
    resp = auth_client.post("/api/mail-import/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Verschlüsselung ───────────────────────────────────────────────────────────
def test_secret_verschluesselung_roundtrip():
    enc = mail_ingest.encrypt_secret("mein-passwort")
    assert enc != "mein-passwort"
    assert mail_ingest.decrypt_secret(enc) == "mein-passwort"


# ── Konten ────────────────────────────────────────────────────────────────────
def test_konten_ohne_token_abgelehnt(client):
    assert client.get("/api/mail-import/accounts").status_code in (401, 403)


def test_konto_anlegen_ohne_klartext_secret(auth_client):
    konto = _imap_konto(auth_client)
    assert konto["has_secret"] is True
    assert "secret" not in konto and "secret_enc" not in konto


def test_globales_konto_nur_admin(auth_client):
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Office", "protocol": "imap", "imap_host": "x",
        "imap_user": "x", "secret": "x", "is_global": True,
    })
    assert resp.status_code == 403


def test_globales_konto_als_admin_fuer_alle_sichtbar(client, admin_user, test_user):
    _admin_client(client, admin_user)
    resp = client.post("/api/mail-import/accounts", json={
        "name": "Office", "protocol": "imap", "imap_host": "x",
        "imap_user": "x", "secret": "x", "is_global": True,
    })
    assert resp.status_code == 201
    assert resp.json()["owner_user_id"] is None

    # Als normaler Benutzer neu einloggen -> globales Konto sichtbar
    client.headers.pop("Authorization")
    resp = client.post("/api/auth/login",
                       json={"email": "test@deinezeit.local",
                             "password": TEST_USER_PASSWORD})
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    namen = [a["name"] for a in client.get("/api/mail-import/accounts").json()]
    assert "Office" in namen
    # … aber nicht durch ihn löschbar
    acc_id = client.get("/api/mail-import/accounts").json()[0]["id"]
    assert client.delete(f"/api/mail-import/accounts/{acc_id}").status_code == 403


def test_konto_aendern_und_loeschen(auth_client):
    konto = _imap_konto(auth_client)
    resp = auth_client.put(f"/api/mail-import/accounts/{konto['id']}",
                           json={"folder": "Aufgaben", "auto_scan": True})
    assert resp.status_code == 200
    assert resp.json()["folder"] == "Aufgaben"
    assert resp.json()["auto_scan"] is True
    assert auth_client.delete(f"/api/mail-import/accounts/{konto['id']}").status_code == 204


# ── Zentrale E-Mail-Zugangsdaten (Einstellungen -> System -> E-Mail) ─────────
def test_konto_mit_zentralen_zugangsdaten_ohne_secret(auth_client):
    resp = auth_client.post("/api/mail-import/accounts", json={
        "name": "Zentral", "protocol": "graph",
        "use_central_credentials": True, "folder": "inbox",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["use_central_credentials"] is True
    assert resp.json()["has_secret"] is False


def test_zentrale_imap_zugangsdaten_aufloesen(db_session, auth_client):
    from app.models.settings import Setting
    from app.models.mailimport import MailAccount
    db_session.add(Setting(key="smtp_user", value="office@firma.at"))
    db_session.add(Setting(key="smtp_password", value="smtp-geheim"))
    db_session.commit()

    acc = MailAccount(name="Z", protocol="imap", imap_host="imap.firma.at",
                      use_central_credentials=True, folder="INBOX")
    user, password = mail_ingest._imap_credentials(db_session, acc)
    assert user == "office@firma.at"
    assert password == "smtp-geheim"


def test_zentrale_graph_zugangsdaten_aufloesen(db_session):
    from app.models.settings import Setting
    from app.models.mailimport import MailAccount
    for k, v in [("ms_tenant_id", "t-1"), ("ms_client_id", "c-1"),
                 ("ms_client_secret", "s-1"), ("smtp_from_email", "office@firma.at")]:
        db_session.add(Setting(key=k, value=v))
    db_session.commit()

    # Mailbox leer -> Absenderadresse aus der zentralen Konfiguration
    acc = MailAccount(name="Z", protocol="graph",
                      use_central_credentials=True, folder="inbox")
    tenant, client, secret, mailbox = mail_ingest._graph_credentials(db_session, acc)
    assert (tenant, client, secret) == ("t-1", "c-1", "s-1")
    assert mailbox == "office@firma.at"


def test_zentrale_zugangsdaten_fehlen_fehler(db_session):
    from app.models.mailimport import MailAccount
    import pytest
    acc = MailAccount(name="Z", protocol="graph",
                      use_central_credentials=True, folder="inbox")
    with pytest.raises(RuntimeError):
        mail_ingest._graph_credentials(db_session, acc)


# ── KI-Einstellungen ──────────────────────────────────────────────────────────
def test_ki_settings_nur_admin_schreibt(auth_client):
    resp = auth_client.put("/api/mail-import/ki-settings",
                           json={"provider": "anthropic", "api_key": "sk-test"})
    assert resp.status_code == 403


def test_ki_settings_speichern_und_maskieren(client, admin_user):
    _admin_client(client, admin_user)
    resp = client.put("/api/mail-import/ki-settings", json={
        "provider": "openai", "api_key": "sk-geheim", "model": "gpt-4o-mini"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["has_api_key"] is True
    assert "sk-geheim" not in str(data)

    # Provider wechseln ohne neuen Key -> Key bleibt erhalten
    resp = client.put("/api/mail-import/ki-settings", json={"provider": "anthropic"})
    assert resp.json()["has_api_key"] is True


# ── Scan + Bestätigungs-Workflow (gemockt) ────────────────────────────────────
def _mock_scan(monkeypatch, mails, vorschlaege_pro_mail):
    monkeypatch.setattr(mail_ingest, "fetch_messages", lambda db, acc, limit=25: mails)
    monkeypatch.setattr(mail_ingest, "extract_tasks",
                        lambda ki, mail: vorschlaege_pro_mail.get(mail["message_id"], []))
    monkeypatch.setattr(mail_ingest, "load_ki_settings",
                        lambda db: {"provider": "anthropic",
                                    "api_key_enc": mail_ingest.encrypt_secret("x"),
                                    "model": None})


def test_scan_erzeugt_vorschlaege(auth_client, monkeypatch):
    konto = _imap_konto(auth_client)
    mails = [{
        "message_id": "<m1@example.com>", "subject": "Angebot bitte",
        "sender": "kunde@example.com",
        "received_at": datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        "body": "Bitte bis Freitag das Angebot schicken.",
    }]
    _mock_scan(monkeypatch, mails, {
        "<m1@example.com>": [{"title": "Angebot an Kunde schicken",
                              "description": "Bis Freitag",
                              "due_date": None, "priority": "hoch"}],
    })
    resp = auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert resp.status_code == 200, resp.text
    assert resp.json()["neue_vorschlaege"] == 1

    # Doppelter Scan derselben Mail -> keine neuen Vorschläge
    resp = auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert resp.json()["neue_vorschlaege"] == 0

    offene = auth_client.get("/api/mail-import/suggestions").json()
    assert len(offene) == 1
    assert offene[0]["title"] == "Angebot an Kunde schicken"
    assert offene[0]["priority"] == "hoch"
    assert offene[0]["account_name"] == "Mein Postfach"


def test_vorschlag_uebernehmen_erzeugt_todo(auth_client, monkeypatch):
    konto = _imap_konto(auth_client)
    mails = [{"message_id": "<m2@example.com>", "subject": "Rechnung",
              "sender": "b@example.com", "received_at": None,
              "body": "Bitte Rechnung 123 prüfen."}]
    _mock_scan(monkeypatch, mails, {
        "<m2@example.com>": [{"title": "Rechnung 123 prüfen", "description": None,
                              "due_date": None, "priority": "mittel"}],
    })
    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]

    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/accept",
                            json={"due_date": "2026-07-10"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "uebernommen"
    assert data["todo_id"]

    # Das Todo existiert mit source=email + Herkunftsdaten
    todo = auth_client.get(f"/api/aufgaben/{data['todo_id']}").json()
    assert todo["title"] == "Rechnung 123 prüfen"
    assert todo["due_date"] == "2026-07-10"
    assert todo["source"] == "email"
    assert todo["source_meta"]["message_id"] == "<m2@example.com>"

    # Zweite Entscheidung abgelehnt
    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/dismiss")
    assert resp.status_code == 400


def test_vorschlag_verwerfen(auth_client, monkeypatch):
    konto = _imap_konto(auth_client)
    mails = [{"message_id": "<m3@example.com>", "subject": "x",
              "sender": "x@example.com", "received_at": None, "body": "y"}]
    _mock_scan(monkeypatch, mails, {
        "<m3@example.com>": [{"title": "Irgendwas", "description": None,
                              "due_date": None, "priority": "mittel"}],
    })
    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]
    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/dismiss")
    assert resp.status_code == 200
    assert resp.json()["status"] == "verworfen"
    assert auth_client.get("/api/mail-import/suggestions").json() == []


def test_mail_ohne_aufgabe_wird_gemerkt(auth_client, monkeypatch):
    konto = _imap_konto(auth_client)
    mails = [{"message_id": "<m4@example.com>", "subject": "Newsletter",
              "sender": "n@example.com", "received_at": None, "body": "Werbung"}]
    _mock_scan(monkeypatch, mails, {})  # KI findet nichts
    resp = auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert resp.json()["neue_vorschlaege"] == 0
    # Mail gilt als verarbeitet, erscheint aber nirgends als Vorschlag
    assert auth_client.get("/api/mail-import/suggestions").json() == []
    resp = auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert resp.json()["neue_vorschlaege"] == 0


# ── Erledigt-Flag in Outlook (Graph) ──────────────────────────────────────────
def _graph_konto(auth_client, **overrides):
    payload = {
        "name": "Outlook", "protocol": "graph",
        "graph_tenant_id": "t", "graph_client_id": "c",
        "graph_mailbox": "o@x.at", "secret": "s",
        "folder": "inbox", **overrides,
    }
    resp = auth_client.post("/api/mail-import/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_scan_setzt_rote_flagge_und_uebernahme_erledigt(auth_client, monkeypatch):
    konto = _graph_konto(auth_client, flag_erledigt=True)
    mails = [{"message_id": "graph-abc", "subject": "Bitte prüfen",
              "sender": "k@x.at", "received_at": None, "body": "Prüfen bitte"}]
    _mock_scan(monkeypatch, mails, {
        "graph-abc": [{"title": "Prüfen", "description": None,
                       "due_date": None, "priority": "mittel"}],
    })
    geflaggt = []
    monkeypatch.setattr(mail_ingest, "graph_set_flag",
                        lambda db, acc, mid, status="complete": geflaggt.append((mid, status)))

    # Scan: Vorschlag erkannt -> rote Flagge
    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    assert geflaggt == [("graph-abc", "flagged")]

    # Übernahme -> Erledigt-Hakerl
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]
    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/accept", json={})
    assert resp.status_code == 200
    assert resp.json()["mail_flagged"] is True
    assert geflaggt == [("graph-abc", "flagged"), ("graph-abc", "complete")]


def test_ablehnung_laesst_rote_flagge_stehen(auth_client, monkeypatch):
    konto = _graph_konto(auth_client, flag_erledigt=True)
    mails = [{"message_id": "graph-dis", "subject": "x",
              "sender": "k@x.at", "received_at": None, "body": "y"}]
    _mock_scan(monkeypatch, mails, {
        "graph-dis": [{"title": "T", "description": None,
                       "due_date": None, "priority": "mittel"}],
    })
    geflaggt = []
    monkeypatch.setattr(mail_ingest, "graph_set_flag",
                        lambda db, acc, mid, status="complete": geflaggt.append((mid, status)))
    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]
    auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/dismiss")
    # Nur die rote Flagge vom Scan — kein complete beim Verwerfen
    assert geflaggt == [("graph-dis", "flagged")]


def test_uebernahme_flag_fehler_blockiert_nicht(auth_client, monkeypatch):
    konto = _graph_konto(auth_client, flag_erledigt=True)
    mails = [{"message_id": "graph-err", "subject": "x",
              "sender": "k@x.at", "received_at": None, "body": "y"}]
    _mock_scan(monkeypatch, mails, {
        "graph-err": [{"title": "T", "description": None,
                       "due_date": None, "priority": "mittel"}],
    })
    def _fehler(db, acc, mid, status="complete"):
        raise RuntimeError("403 Forbidden")
    monkeypatch.setattr(mail_ingest, "graph_set_flag", _fehler)

    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]
    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/accept", json={})
    # Übernahme klappt trotzdem, Flag-Fehler wird gemeldet
    assert resp.status_code == 200
    assert resp.json()["status"] == "uebernommen"
    assert resp.json()["mail_flagged"] is False


def test_flag_aus_kein_versuch(auth_client, monkeypatch):
    konto = _graph_konto(auth_client, flag_erledigt=False)
    mails = [{"message_id": "graph-off", "subject": "x",
              "sender": "k@x.at", "received_at": None, "body": "y"}]
    _mock_scan(monkeypatch, mails, {
        "graph-off": [{"title": "T", "description": None,
                       "due_date": None, "priority": "mittel"}],
    })
    aufrufe = []
    monkeypatch.setattr(mail_ingest, "graph_set_flag",
                        lambda db, acc, mid, status="complete": aufrufe.append(mid))
    auth_client.post(f"/api/mail-import/accounts/{konto['id']}/scan")
    vorschlag = auth_client.get("/api/mail-import/suggestions").json()[0]
    resp = auth_client.post(f"/api/mail-import/suggestions/{vorschlag['id']}/accept", json={})
    assert resp.json()["mail_flagged"] is None
    assert aufrufe == []


# ── KI-Antwort-Parser ─────────────────────────────────────────────────────────
def test_ki_json_parser_tolerant():
    text = 'Hier die Aufgaben:\n```json\n[{"title": "Test", "description": "d", "due_date": "2026-08-01", "priority": "hoch"}]\n```'
    out = mail_ingest._parse_ki_json(text)
    assert len(out) == 1
    assert out[0]["title"] == "Test"
    assert str(out[0]["due_date"]) == "2026-08-01"

    assert mail_ingest._parse_ki_json("keine aufgaben") == []
    assert mail_ingest._parse_ki_json("[]") == []
    # Ungültige Priorität -> mittel
    out = mail_ingest._parse_ki_json('[{"title": "X", "priority": "mega"}]')
    assert out[0]["priority"] == "mittel"
