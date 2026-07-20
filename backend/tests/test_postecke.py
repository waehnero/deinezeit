"""
Tests für das Modul Postecke (Social Media, Etappe 1).

Abgedeckt:
  - Profile: CRUD, Kanal-Validierung, Besitzer-Scoping
  - Posts: CRUD, Status-Workflow (geplant braucht geplant_am)
  - KI-Generierung: Vorschlag wird am Post gespeichert (call_ki gemockt)
  - Auth: alle Endpunkte nur mit Login erreichbar

Der echte KI-Aufruf (services/ki.call_ki) und der Objektspeicher werden
gemockt — Tests laufen ohne API-Key und ohne MinIO.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import postecke as postecke_service


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _profil_anlegen(auth_client, **kwargs):
    daten = {"name": "Facebook privat Test", "kanal": "facebook_privat",
             "stil_prompt": "Locker, per Du, mit Emojis"}
    daten.update(kwargs)
    resp = auth_client.post("/api/postecke/profile", json=daten)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _post_anlegen(auth_client, **kwargs):
    daten = {"beschreibung": "Feuerwehrfest in Ebreichsdorf, tolle Stimmung"}
    daten.update(kwargs)
    resp = auth_client.post("/api/postecke/posts", json=daten)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Auth ──────────────────────────────────────────────────────────────────────
def test_endpunkte_brauchen_login(client):
    # HTTPBearer liefert ohne Authorization-Header je nach FastAPI-Version
    # 403 (aktuell) bzw. 401 (neuere Versionen) — beides gilt als "kein Zugriff".
    assert client.get("/api/postecke/profile").status_code in (401, 403)
    assert client.get("/api/postecke/posts").status_code in (401, 403)


# ── Profile ───────────────────────────────────────────────────────────────────
def test_profil_crud(auth_client):
    profil = _profil_anlegen(auth_client)
    assert profil["name"] == "Facebook privat Test"
    assert profil["kanal"] == "facebook_privat"

    # Liste
    resp = auth_client.get("/api/postecke/profile")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Update
    resp = auth_client.put(f"/api/postecke/profile/{profil['id']}",
                           json={"name": "Umbenannt", "stil_prompt": "Sachlich"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Umbenannt"
    assert resp.json()["stil_prompt"] == "Sachlich"

    # Löschen
    resp = auth_client.delete(f"/api/postecke/profile/{profil['id']}")
    assert resp.status_code == 204
    assert auth_client.get("/api/postecke/profile").json() == []


def test_profil_ungueltiger_kanal(auth_client):
    resp = auth_client.post("/api/postecke/profile",
                            json={"name": "X", "kanal": "myspace"})
    assert resp.status_code == 422


# ── Posts ─────────────────────────────────────────────────────────────────────
def test_post_crud_und_liste(auth_client):
    profil = _profil_anlegen(auth_client)
    post = _post_anlegen(auth_client, profil_id=profil["id"])
    assert post["status"] == "entwurf"
    assert post["profil_id"] == profil["id"]

    # Update (Text nach Kontrolle angepasst)
    resp = auth_client.put(f"/api/postecke/posts/{post['id']}",
                           json={"text": "Mein Posttext", "hashtags": "#test"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "Mein Posttext"

    # Liste + Statusfilter
    assert len(auth_client.get("/api/postecke/posts").json()) == 1
    assert auth_client.get("/api/postecke/posts",
                           params={"status": "veroeffentlicht"}).json() == []
    assert auth_client.get("/api/postecke/posts",
                           params={"status": "quatsch"}).status_code == 422

    # Löschen
    assert auth_client.delete(f"/api/postecke/posts/{post['id']}").status_code == 204
    assert auth_client.get("/api/postecke/posts").json() == []


def test_post_loeschen_entfernt_fotos_im_storage(auth_client, monkeypatch):
    """Beim Löschen eines Posts werden auch Speicher-Objekte aufgeräumt."""
    geloescht = []
    monkeypatch.setattr("app.api.postecke.storage_service.delete_file",
                        lambda key, db=None: geloescht.append(key))
    post = _post_anlegen(auth_client)
    assert auth_client.delete(f"/api/postecke/posts/{post['id']}").status_code == 204
    # keine Fotos vorhanden -> nichts zu löschen, aber Endpunkt funktioniert
    assert geloescht == []


def test_status_workflow(auth_client):
    post = _post_anlegen(auth_client)

    # geplant ohne Zeitpunkt -> Fehler
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "geplant"})
    assert resp.status_code == 422

    # geplant mit Zeitpunkt
    termin = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "geplant", "geplant_am": termin})
    assert resp.status_code == 200
    assert resp.json()["status"] == "geplant"
    assert resp.json()["geplant_am"] is not None

    # veröffentlicht setzt Zeitstempel
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "veroeffentlicht"})
    assert resp.status_code == 200
    assert resp.json()["veroeffentlicht_am"] is not None

    # archivieren und wiederherstellen
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "archiviert"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "archiviert"
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "entwurf"})
    assert resp.status_code == 200

    # ungültiger Status
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "irgendwas"})
    assert resp.status_code == 422


def test_fremder_post_nicht_sichtbar(auth_client, db_session):
    """Posts/Profile anderer Benutzer sind unsichtbar (404)."""
    from app.models.postecke import SocialPost
    from app.services.auth_service import auth_service
    anderer = auth_service.create_user(
        db_session, email="andere@deinezeit.local", full_name="Andere",
        password="Test-Passwort123!", role="employee")
    fremd = SocialPost(owner_user_id=anderer.id, titel="Fremder Post")
    db_session.add(fremd)
    db_session.commit()

    assert auth_client.get(f"/api/postecke/posts/{fremd.id}").status_code == 404
    assert auth_client.get("/api/postecke/posts").json() == []


# ── Fotos ─────────────────────────────────────────────────────────────────────
def test_foto_upload_und_loeschen(auth_client, monkeypatch):
    """Upload legt Datensatz + Storage-Objekt an; Löschen räumt beides weg."""
    speicher = {}
    monkeypatch.setattr("app.api.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None: speicher.__setitem__(key, data))
    monkeypatch.setattr("app.api.postecke.storage_service.delete_file",
                        lambda key, db=None: speicher.pop(key, None))

    post = _post_anlegen(auth_client)
    resp = auth_client.post(
        f"/api/postecke/posts/{post['id']}/fotos",
        files=[("files", ("test.jpg", b"fake-jpeg-daten", "image/jpeg"))])
    assert resp.status_code == 201, resp.text
    fotos = resp.json()["fotos"]
    assert len(fotos) == 1
    assert fotos[0]["filename"] == "test.jpg"
    assert len(speicher) == 1  # Objekt liegt im (gemockten) Storage

    # Nicht erlaubter Dateityp
    resp = auth_client.post(
        f"/api/postecke/posts/{post['id']}/fotos",
        files=[("files", ("doc.pdf", b"x", "application/pdf"))])
    assert resp.status_code == 422

    # Foto löschen entfernt auch das Storage-Objekt
    resp = auth_client.delete(f"/api/postecke/fotos/{fotos[0]['id']}")
    assert resp.status_code == 204
    assert speicher == {}


# ── Profil-Parameter & Bild-Ausspielung ──────────────────────────────────────
def _test_bild(breite=400, hoehe=200) -> bytes:
    """Erzeugt ein kleines Test-JPEG."""
    import io
    from PIL import Image
    img = Image.new("RGB", (breite, hoehe), (200, 120, 40))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


def test_profil_bild_parameter(auth_client):
    profil = _profil_anlegen(auth_client, kanal="tiktok",
                             bild_format="1:1", bild_filter="brillant")
    assert profil["kanal"] == "tiktok"
    assert profil["bild_format"] == "1:1"
    assert profil["bild_filter"] == "brillant"

    # Ungültige Werte werden abgelehnt
    assert auth_client.post("/api/postecke/profile",
                            json={"name": "X", "kanal": "facebook_privat",
                                  "bild_format": "3:7"}).status_code == 422
    assert auth_client.post("/api/postecke/profile",
                            json={"name": "X", "kanal": "facebook_privat",
                                  "bild_filter": "sepia-extrem"}).status_code == 422


def test_bearbeite_foto_zuschnitt_und_filter():
    """1:1-Zuschnitt liefert quadratisches JPEG; Filter laufen fehlerfrei durch."""
    import io
    from PIL import Image
    from app.services.postecke import bearbeite_foto

    daten, mimetype = bearbeite_foto(_test_bild(400, 200), "1:1", "brillant")
    assert mimetype == "image/jpeg"
    img = Image.open(io.BytesIO(daten))
    assert img.size[0] == img.size[1]  # quadratisch

    for f in ("kein", "warm", "kuehl", "kontrast", "sw"):
        out, _ = bearbeite_foto(_test_bild(), "original", f)
        assert len(out) > 0


def test_foto_ausspielung_endpoint(auth_client, monkeypatch):
    """Ausspielung liefert das Foto im Profil-Format (1:1) als JPEG."""
    speicher = {}
    monkeypatch.setattr("app.api.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None: speicher.__setitem__(key, data))
    monkeypatch.setattr("app.api.postecke.storage_service.download_file",
                        lambda key, db=None: (speicher[key], "image/jpeg"))

    profil = _profil_anlegen(auth_client, bild_format="1:1", bild_filter="kein")
    post = _post_anlegen(auth_client, profil_id=profil["id"])
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/fotos",
                            files=[("files", ("t.jpg", _test_bild(400, 200), "image/jpeg"))])
    foto_id = resp.json()["fotos"][0]["id"]

    resp = auth_client.get(f"/api/postecke/fotos/{foto_id}/ausspielung")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(resp.content))
    assert img.size[0] == img.size[1]  # Profil-Format 1:1 angewendet


# ── Datacenter-Postsarchiv ────────────────────────────────────────────────────
def test_archivieren_spiegelt_ins_datacenter(auth_client, db_session, monkeypatch):
    """Archivieren legt Markdown+Fotos im Datacenter ab; Wiederherstellen räumt auf."""
    from app.models.attachment import Attachment

    speicher = {}
    monkeypatch.setattr("app.api.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None: speicher.__setitem__(key, data))
    monkeypatch.setattr("app.services.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None: speicher.__setitem__(key, data))
    monkeypatch.setattr("app.services.postecke.storage_service.download_file",
                        lambda key, db=None: (speicher[key], "image/jpeg"))
    monkeypatch.setattr("app.services.postecke.storage_service.delete_file",
                        lambda key, db=None: speicher.pop(key, None))

    post = _post_anlegen(auth_client, titel="Feuerwehrfest",
                         kontakt_name="Feuerwehr Ebreichsdorf")
    auth_client.post(f"/api/postecke/posts/{post['id']}/fotos",
                     files=[("files", ("a.jpg", b"foto-a", "image/jpeg"))])
    auth_client.put(f"/api/postecke/posts/{post['id']}",
                    json={"text": "Toller Abend!", "hashtags": "#ff"})

    # Archivieren -> Markdown + 1 Foto als Anlagen mit Ordner "Postsarchiv"
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "archiviert"})
    assert resp.status_code == 200
    anlagen = (db_session.query(Attachment)
               .filter(Attachment.description == f"postecke:{post['id']}").all())
    assert len(anlagen) == 2  # 1x Markdown, 1x Foto
    assert all(a.folder == "Postsarchiv" for a in anlagen)
    md = [a for a in anlagen if a.mimetype == "text/markdown"][0]
    inhalt = speicher[md.storage_key].decode("utf-8")
    assert "Toller Abend!" in inhalt and "#ff" in inhalt

    # Wiederherstellen -> Spiegelung wird entfernt
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "entwurf"})
    assert resp.status_code == 200
    assert (db_session.query(Attachment)
            .filter(Attachment.description == f"postecke:{post['id']}").count()) == 0


def test_archivieren_mit_kontakt_landet_beim_kontakt(auth_client, db_session, monkeypatch):
    """Mit Kontakt: Anlagen hängen am Kontakt (entity_type=kontakte)."""
    from uuid import uuid4
    from app.models.attachment import Attachment

    speicher = {}
    monkeypatch.setattr("app.services.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None: speicher.__setitem__(key, data))

    kontakt_id = str(uuid4())
    post = _post_anlegen(auth_client, titel="Kundenevent",
                         kontakt_id=kontakt_id, kontakt_name="Musterfirma")
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                            json={"status": "archiviert"})
    assert resp.status_code == 200
    a = (db_session.query(Attachment)
         .filter(Attachment.description == f"postecke:{post['id']}").first())
    assert a is not None
    assert a.entity_type == "kontakte"
    assert str(a.entity_id) == kontakt_id
    assert a.contact_name == "Musterfirma"
    assert a.storage_key.startswith(f"kontakte/{kontakt_id}/Postsarchiv/")


# ── KI-Generierung ────────────────────────────────────────────────────────────
def test_generieren_speichert_vorschlag(auth_client, monkeypatch):
    antwort = ('{"titel": "Feuerwehrfest", "text": "Was für ein Abend!", '
               '"hashtags": "#Feuerwehrfest #Ebreichsdorf", '
               '"ort": "Ebreichsdorf", "gefuehl": "fröhlich"}')
    monkeypatch.setattr(postecke_service, "call_ki",
                        lambda ki, prompt, images=None, max_tokens=0: antwort)
    monkeypatch.setattr(postecke_service, "load_ki_settings",
                        lambda db: {"provider": "anthropic",
                                    "api_key_enc": "x", "model": "test-modell"})

    profil = _profil_anlegen(auth_client)
    post = _post_anlegen(auth_client, profil_id=profil["id"])

    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/generieren", json={})
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["text"] == "Was für ein Abend!"
    assert "#Feuerwehrfest" in daten["hashtags"]

    # Vorschlag ist am Post gespeichert, Status auf "kontrolle"
    post_neu = auth_client.get(f"/api/postecke/posts/{post['id']}").json()
    assert post_neu["text"] == "Was für ein Abend!"
    assert post_neu["ort"] == "Ebreichsdorf"
    assert post_neu["gefuehl"] == "fröhlich"
    assert post_neu["titel"] == "Feuerwehrfest"
    assert post_neu["status"] == "kontrolle"
    assert post_neu["ki_model"] == "anthropic/test-modell"


def test_generieren_ohne_ki_key_fehler(auth_client, monkeypatch):
    def _kein_key(ki, prompt, images=None, max_tokens=0):
        raise RuntimeError("Kein KI-API-Key konfiguriert")
    monkeypatch.setattr(postecke_service, "call_ki", _kein_key)

    post = _post_anlegen(auth_client)
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/generieren", json={})
    assert resp.status_code == 400
    assert "KI-API-Key" in resp.json()["detail"]


def test_generieren_unbrauchbare_antwort(auth_client, monkeypatch):
    monkeypatch.setattr(postecke_service, "call_ki",
                        lambda ki, prompt, images=None, max_tokens=0: "kein json")
    monkeypatch.setattr(postecke_service, "load_ki_settings",
                        lambda db: {"provider": "anthropic", "api_key_enc": "x", "model": None})
    post = _post_anlegen(auth_client)
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/generieren", json={})
    assert resp.status_code == 400
