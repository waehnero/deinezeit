"""
Tests für das Datacenter (/api/datacenter) — Schwerpunkt Sicherheit der
Dateiablage und der Vorschau (Audit 02.09.2026, SEC-001 / SEC-007 / SEC-013).

Der Objektspeicher wird durch ein Dict ersetzt (wie in test_postecke.py):
Es geht hier um die Regeln der API, nicht um MinIO.
"""
import uuid

import pytest

from app.services import storage_service
from tests.conftest import TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"

SVG_MIT_SKRIPT = (b'<svg xmlns="http://www.w3.org/2000/svg">'
                  b'<script>alert(document.domain)</script></svg>')
PNG_KOPF = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _speicher(monkeypatch):
    """Objektspeicher im Arbeitsspeicher; gibt beim Download den Typ zurück,
    den der Upload gemeldet hat — genau wie MinIO es täte."""
    ablage = {}
    typen = {}

    def upload(key, data, mimetype=None, db=None, backend=None):
        ablage[key] = data
        typen[key] = mimetype or "application/octet-stream"

    monkeypatch.setattr(storage_service, "upload_file", upload)
    monkeypatch.setattr(storage_service, "download_file",
                        lambda key, db=None, backend=None: (ablage.get(key, b""),
                                                            typen.get(key, "application/octet-stream")))
    monkeypatch.setattr(storage_service, "delete_file",
                        lambda key, db=None, backend=None: ablage.pop(key, None))
    monkeypatch.setattr(storage_service, "current_backend", lambda db=None: "minio")
    return ablage


def _hochladen(auth_client, dateiname, inhalt, mimetype, entity_type="kontakte",
               entity_id=None):
    entity_id = entity_id or str(uuid.uuid4())
    resp = auth_client.post(
        f"/api/datacenter/{entity_type}/{entity_id}/upload",
        files={"file": (dateiname, inhalt, mimetype)},
    )
    return resp


def _admin_client(client, admin_user):
    resp = client.post("/api/auth/login",
                       json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


# ── Vorschau: aktive Inhalte nie inline ──────────────────────────────────────

def test_svg_vorschau_kommt_nur_als_download(auth_client):
    """SEC-001: Ein SVG mit Skript darf nicht unter der App-Adresse gerendert
    werden — die Vorschau liefert es als Download mit neutralem Typ."""
    resp = _hochladen(auth_client, "logo.svg", SVG_MIT_SKRIPT, "image/svg+xml")
    assert resp.status_code == 200, resp.text
    att_id = resp.json()["id"]

    vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
    assert vorschau.status_code == 200
    assert vorschau.headers["content-type"].startswith("application/octet-stream")
    assert vorschau.headers["content-disposition"].startswith("attachment")
    assert vorschau.headers["x-content-type-options"] == "nosniff"


def test_html_als_textdatei_getarnt_wird_nicht_gerendert(auth_client):
    """Die Endung entscheidet mit: eine .html-Datei mit behauptetem
    text/plain bleibt Download."""
    resp = _hochladen(auth_client, "seite.html", b"<script>1</script>", "text/plain")
    att_id = resp.json()["id"]
    vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
    assert vorschau.status_code == 200
    assert vorschau.headers["content-disposition"].startswith("attachment")


def test_svg_mimetype_mit_harmloser_endung_wird_nicht_gerendert(auth_client):
    """Umgekehrt: image/svg+xml unter einer .png-Endung ebenfalls nicht."""
    resp = _hochladen(auth_client, "bild.png", SVG_MIT_SKRIPT, "image/svg+xml")
    att_id = resp.json()["id"]
    vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
    assert vorschau.headers["content-disposition"].startswith("attachment")


def test_png_vorschau_bleibt_inline(auth_client):
    """Echte Bilder werden weiterhin im Browser angezeigt."""
    resp = _hochladen(auth_client, "foto.png", PNG_KOPF, "image/png")
    att_id = resp.json()["id"]
    vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
    assert vorschau.status_code == 200
    assert vorschau.headers["content-type"].startswith("image/png")
    assert vorschau.headers["content-disposition"].startswith("inline")
    assert vorschau.headers["x-content-type-options"] == "nosniff"
    assert vorschau.content == PNG_KOPF


def test_pdf_und_text_vorschau_bleiben_inline(auth_client):
    for name, inhalt, typ in (("beleg.pdf", b"%PDF-1.4 x", "application/pdf"),
                              ("notiz.txt", b"Hallo", "text/plain")):
        att_id = _hochladen(auth_client, name, inhalt, typ).json()["id"]
        vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
        assert vorschau.status_code == 200, name
        assert vorschau.headers["content-type"].startswith(typ), name
        assert vorschau.headers["content-disposition"].startswith("inline"), name


def test_unbekannter_typ_liefert_415(auth_client):
    att_id = _hochladen(auth_client, "tabelle.xlsx", b"PK\x03\x04",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").json()["id"]
    assert auth_client.get(f"/api/datacenter/{att_id}/preview").status_code == 415


def test_eml_vorschau_verbietet_skripte(auth_client):
    """Die erzeugte HTML-Vorschau trägt eine CSP ohne Skripte."""
    eml = (b"From: a@example.com\r\nTo: b@example.com\r\nSubject: Test\r\n"
           b"Content-Type: text/html\r\n\r\n<b>Hallo</b><script>1</script>")
    att_id = _hochladen(auth_client, "mail.eml", eml, "message/rfc822").json()["id"]
    vorschau = auth_client.get(f"/api/datacenter/{att_id}/preview")
    assert vorschau.status_code == 200
    assert vorschau.headers["content-type"].startswith("text/html")
    assert vorschau.headers["content-security-policy"] == "script-src 'none'"
    # Der HTML-Body steht nur escaped in einem sandbox-iframe
    assert "<script>1</script>" not in vorschau.text


def test_download_bleibt_unveraendert(auth_client):
    """Der normale Download war schon immer ein Attachment."""
    att_id = _hochladen(auth_client, "logo.svg", SVG_MIT_SKRIPT, "image/svg+xml").json()["id"]
    dl = auth_client.get(f"/api/datacenter/{att_id}/download")
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.content == SVG_MIT_SKRIPT


# ── Zuordnung: entity_type / entity_id ───────────────────────────────────────

@pytest.mark.parametrize("entity_type", ["..", "Kontakte", "a.b", "x/y", "ü", ""])
def test_ungueltiger_datensatztyp_wird_abgelehnt(auth_client, entity_type):
    """SEC-007: Kein Pfadbestandteil außer [a-z0-9_-] im Typ."""
    resp = auth_client.post(
        f"/api/datacenter/{entity_type}/{uuid.uuid4()}/upload",
        files={"file": ("a.txt", b"x", "text/plain")},
    )
    assert resp.status_code in (400, 404, 405), (entity_type, resp.status_code)
    if resp.status_code == 400:
        assert resp.json()["detail"] == "Ungültiger Datensatztyp"


def test_ungueltige_datensatz_id_liefert_400_statt_500(auth_client):
    # („../" in der URL löst schon der HTTP-Client auf — der Traversal-Fall
    # steckt deshalb im Service-Test test_speicherschluessel_wird_bereinigt.)
    resp = _hochladen(auth_client, "a.txt", b"x", "text/plain", entity_id="keine-uuid")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Ungültige Datensatz-ID"

    liste = auth_client.get("/api/datacenter/kontakte/keine-uuid")
    assert liste.status_code == 400

    link = auth_client.post("/api/datacenter/link", json={
        "entity_type": "kontakte", "entity_id": "keine-uuid",
        "display_name": "x", "link_url": "https://example.com"})
    assert link.status_code == 400


def test_gueltige_zuordnung_funktioniert_wie_bisher(auth_client):
    eid = str(uuid.uuid4())
    assert _hochladen(auth_client, "a.txt", b"x", "text/plain",
                      entity_type="zeiterfassung", entity_id=eid).status_code == 200
    liste = auth_client.get(f"/api/datacenter/zeiterfassung/{eid}")
    assert liste.status_code == 200
    assert len(liste.json()["attachments"]) == 1


def test_speicherschluessel_wird_bereinigt():
    """Zweiter Riegel im Service: kein '/' oder '..' aus Typ und ID."""
    key = storage_service.build_storage_key("../x", "../../y", "d.pdf")
    teile = key.split("/")
    assert len(teile) == 3
    assert ".." not in teile[0] and ".." not in teile[1]
    assert teile[2] == "d.pdf"
    # Unverändertes Verhalten für gültige Werte
    eid = str(uuid.uuid4())
    assert storage_service.build_storage_key("kontakte", eid, "d.pdf") == f"kontakte/{eid}/d.pdf"


# ── Logo/Favicon: SVG mit Skript (SEC-013) ───────────────────────────────────

def test_logo_svg_mit_skript_wird_abgelehnt(client, admin_user, tmp_path, monkeypatch):
    from app.api import settings as settings_api
    monkeypatch.setattr(settings_api, "LOGO_PATH", str(tmp_path / "logo"))
    c = _admin_client(client, admin_user)
    resp = c.post("/api/settings/logo",
                  files={"file": ("logo.svg", SVG_MIT_SKRIPT, "image/svg+xml")})
    assert resp.status_code == 400
    assert "Skripte" in resp.json()["detail"]

    resp = c.post("/api/settings/favicon",
                  files={"file": ("f.svg", b'<svg onload="alert(1)"/>', "image/svg+xml")})
    assert resp.status_code == 400


def test_logo_svg_ohne_skript_wird_angenommen(client, admin_user, tmp_path, monkeypatch):
    from app.api import settings as settings_api
    monkeypatch.setattr(settings_api, "LOGO_PATH", str(tmp_path / "logo"))
    c = _admin_client(client, admin_user)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle r="4"/></svg>'
    resp = c.post("/api/settings/logo", files={"file": ("logo.svg", svg, "image/svg+xml")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["logo_url"].startswith("/api/static/logo/logo_original.svg")
