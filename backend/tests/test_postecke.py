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


# Alle Postecke-Tests laufen ohne echtes MinIO: der Datacenter-Sync in
# create_post/update_post ruft sonst echten Storage (in der CI nicht vorhanden ->
# Hänger). Storage wird daher generell in-memory gestubbt. Tests mit eigenem
# Storage-Mock überschreiben das einfach (spätere monkeypatch-Zuweisung gewinnt).
@pytest.fixture(autouse=True)
def _storage_in_memory(monkeypatch):
    ablage = {}
    monkeypatch.setattr(
        "app.services.storage_service.upload_file",
        lambda key, data, mimetype=None, db=None, backend=None: ablage.__setitem__(key, data))
    monkeypatch.setattr(
        "app.services.storage_service.download_file",
        lambda key, db=None: (ablage.get(key, b""), "application/octet-stream"))
    monkeypatch.setattr(
        "app.services.storage_service.delete_file",
        lambda key, db=None: ablage.pop(key, None))


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
    speicher = _mock_storage(monkeypatch)

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


# ── Video (Etappe „Video + Instagram", Teilschritt 1) ─────────────────────────
def _mock_storage(monkeypatch):
    """In-Memory-Storage-Mock (upload/delete) für die fokussierten Medien-Tests.
    Der Datacenter-Sync wird hier deaktiviert, damit die Storage-Anzahl nur die
    Medien widerspiegelt (die Datacenter-Ablage wird separat getestet)."""
    speicher = {}
    monkeypatch.setattr("app.api.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None, backend=None: speicher.__setitem__(key, data))
    monkeypatch.setattr("app.api.postecke.storage_service.delete_file",
                        lambda key, db=None: speicher.pop(key, None))
    monkeypatch.setattr("app.services.postecke.synchronisiere_datacenter",
                        lambda db, post, user_id=None: 0)
    return speicher


def test_video_upload_und_loeschen(auth_client, monkeypatch):
    """Upload legt Datensatz + Storage-Objekt an; Löschen räumt beides weg."""
    speicher = _mock_storage(monkeypatch)

    post = _post_anlegen(auth_client)
    resp = auth_client.post(
        f"/api/postecke/posts/{post['id']}/video",
        files={"file": ("clip.mp4", b"fake-mp4-daten", "video/mp4")})
    assert resp.status_code == 201, resp.text
    video = resp.json()["video"]
    assert video is not None
    assert video["filename"] == "clip.mp4"
    assert len(speicher) == 1  # Objekt liegt im (gemockten) Storage

    # Nicht erlaubter Typ (nur MP4/MOV)
    post_b = _post_anlegen(auth_client)
    resp = auth_client.post(
        f"/api/postecke/posts/{post_b['id']}/video",
        files={"file": ("clip.avi", b"x", "video/x-msvideo")})
    assert resp.status_code == 422

    # Löschen entfernt auch das Storage-Objekt
    resp = auth_client.delete(f"/api/postecke/videos/{video['id']}")
    assert resp.status_code == 204
    assert speicher == {}


def test_video_ersetzt_vorhandenes(auth_client, monkeypatch):
    """Ein zweites Video ersetzt das erste; nur das neue bleibt im Storage."""
    speicher = _mock_storage(monkeypatch)

    post = _post_anlegen(auth_client)
    auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                     files={"file": ("a.mp4", b"aaa", "video/mp4")})
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                            files={"file": ("b.mov", b"bbb", "video/quicktime")})
    assert resp.status_code == 201, resp.text
    assert resp.json()["video"]["filename"] == "b.mov"
    assert len(speicher) == 1


def test_foto_und_video_schliessen_sich_aus(auth_client, monkeypatch):
    """Kein Misch-Post: Foto blockiert Video-Upload und umgekehrt (422)."""
    _mock_storage(monkeypatch)

    # Foto vorhanden -> Video wird abgelehnt
    p1 = _post_anlegen(auth_client)
    auth_client.post(f"/api/postecke/posts/{p1['id']}/fotos",
                     files=[("files", ("f.jpg", b"jpeg", "image/jpeg"))])
    resp = auth_client.post(f"/api/postecke/posts/{p1['id']}/video",
                            files={"file": ("v.mp4", b"mp4", "video/mp4")})
    assert resp.status_code == 422

    # Video vorhanden -> Foto wird abgelehnt
    p2 = _post_anlegen(auth_client)
    auth_client.post(f"/api/postecke/posts/{p2['id']}/video",
                     files={"file": ("v.mp4", b"mp4", "video/mp4")})
    resp = auth_client.post(f"/api/postecke/posts/{p2['id']}/fotos",
                            files=[("files", ("f.jpg", b"jpeg", "image/jpeg"))])
    assert resp.status_code == 422


def test_post_loeschen_entfernt_video_im_storage(auth_client, monkeypatch):
    """Post löschen räumt auch das Video-Storage-Objekt weg."""
    speicher = _mock_storage(monkeypatch)

    post = _post_anlegen(auth_client)
    auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                     files={"file": ("clip.mp4", b"daten", "video/mp4")})
    assert len(speicher) == 1
    resp = auth_client.delete(f"/api/postecke/posts/{post['id']}")
    assert resp.status_code == 204
    assert speicher == {}


def test_video_poster_wird_erzeugt_und_ausgeliefert(auth_client, monkeypatch):
    """Beim Upload wird ein Standbild abgelegt (ffmpeg gemockt); Poster abrufbar."""
    speicher = _mock_storage(monkeypatch)
    monkeypatch.setattr("app.api.postecke.postecke_service.erzeuge_video_poster",
                        lambda data, endung=".mp4": b"jpeg-poster-bytes")
    monkeypatch.setattr("app.api.postecke.storage_service.download_file",
                        lambda key, db=None: (speicher.get(key, b""), "image/jpeg"))

    post = _post_anlegen(auth_client)
    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                            files={"file": ("clip.mp4", b"x", "video/mp4")})
    assert resp.status_code == 201, resp.text
    video = resp.json()["video"]
    assert video["has_poster"] is True

    r = auth_client.get(f"/api/postecke/videos/{video['id']}/poster")
    assert r.status_code == 200
    assert r.content == b"jpeg-poster-bytes"

    # Video löschen entfernt auch das Poster-Objekt
    auth_client.delete(f"/api/postecke/videos/{video['id']}")
    assert auth_client.get(f"/api/postecke/videos/{video['id']}/poster").status_code == 404


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
                        lambda key, data, mt, db=None, backend=None: speicher.__setitem__(key, data))
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


# ── Direktanbindung Facebook-Seite ───────────────────────────────────────────
def test_profil_zugang_verschluesselt(auth_client):
    """Zugangsdaten werden gespeichert (has_zugang), aber nie zurückgegeben."""
    profil = _profil_anlegen(auth_client, kanal="facebook_seite",
                             zugang={"page_id": "123456", "page_token": "GEHEIM-TOKEN"})
    assert profil["has_zugang"] is True
    assert profil["direktanbindung"] is True
    assert "GEHEIM-TOKEN" not in str(profil)

    # Update ohne zugang lässt die Daten unverändert
    resp = auth_client.put(f"/api/postecke/profile/{profil['id']}",
                           json={"name": "Umbenannt"})
    assert resp.json()["has_zugang"] is True

    # facebook_privat hat nie eine Direktanbindung
    p2 = _profil_anlegen(auth_client, name="Privat", kanal="facebook_privat")
    assert p2["direktanbindung"] is False


def test_fb_seite_video_publisher_nutzt_videos_endpunkt(auth_client, monkeypatch):
    """Ein Post mit Video wird über den /videos-Endpunkt der Seite gepostet."""
    from app.services import social_publish

    aufrufe = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"id": "555"}

    def _fake_post(url, data=None, files=None, timeout=None):
        aufrufe["url"] = url
        aufrufe["data"] = data
        aufrufe["hat_datei"] = files is not None
        return _Resp()

    monkeypatch.setattr(social_publish.httpx, "post", _fake_post)
    monkeypatch.setattr(social_publish.storage_service, "download_file",
                        lambda key, db=None: (b"videobytes", "video/mp4"))
    monkeypatch.setattr("app.api.postecke.storage_service.upload_file",
                        lambda key, data, mt, db=None, backend=None: None)

    profil = _profil_anlegen(auth_client, kanal="facebook_seite",
                             zugang={"page_id": "42", "page_token": "tok"})
    post = _post_anlegen(auth_client, profil_id=profil["id"])
    auth_client.put(f"/api/postecke/posts/{post['id']}", json={"text": "Videobeitrag"})
    auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                     files={"file": ("clip.mp4", b"x", "video/mp4")})

    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/veroeffentlichen")
    assert resp.status_code == 200, resp.text
    assert resp.json()["extern_url"] == "https://www.facebook.com/555"
    assert aufrufe["url"].endswith("/42/videos")
    assert aufrufe["data"]["description"] == "Videobeitrag"
    assert aufrufe["hat_datei"] is True


def test_direkt_veroeffentlichen(auth_client, monkeypatch):
    """Veröffentlichen über die Direktanbindung setzt Status + extern_url."""
    from app.services import social_publish

    def _fake_publisher(db, post, profil):
        return "https://www.facebook.com/123_456"
    monkeypatch.setitem(social_publish.KANAL_PUBLISHER, "facebook_seite", _fake_publisher)

    profil = _profil_anlegen(auth_client, kanal="facebook_seite",
                             zugang={"page_id": "1", "page_token": "t"})
    post = _post_anlegen(auth_client, profil_id=profil["id"])
    auth_client.put(f"/api/postecke/posts/{post['id']}", json={"text": "Hallo Seite!"})

    resp = auth_client.post(f"/api/postecke/posts/{post['id']}/veroeffentlichen")
    assert resp.status_code == 200, resp.text
    daten = resp.json()
    assert daten["status"] == "veroeffentlicht"
    assert daten["extern_url"] == "https://www.facebook.com/123_456"
    assert daten["veroeffentlicht_am"] is not None

    # Ohne Text -> 422; ohne Direktanbindung -> 400
    post2 = _post_anlegen(auth_client, profil_id=profil["id"])
    assert auth_client.post(f"/api/postecke/posts/{post2['id']}/veroeffentlichen").status_code == 422
    privat = _profil_anlegen(auth_client, name="Privat", kanal="facebook_privat")
    post3 = _post_anlegen(auth_client, profil_id=privat["id"])
    auth_client.put(f"/api/postecke/posts/{post3['id']}", json={"text": "x"})
    assert auth_client.post(f"/api/postecke/posts/{post3['id']}/veroeffentlichen").status_code == 400


def test_worker_veroeffentlicht_faellige(auth_client, db_session, monkeypatch):
    """Der Worker veröffentlicht fällige geplante Posts; Fehler bleiben am Post."""
    from app.services import social_publish

    aufrufe = []
    def _fake_publisher(db, post, profil):
        aufrufe.append(post.id)
        return "https://www.facebook.com/x"
    monkeypatch.setitem(social_publish.KANAL_PUBLISHER, "facebook_seite", _fake_publisher)

    profil = _profil_anlegen(auth_client, kanal="facebook_seite",
                             zugang={"page_id": "1", "page_token": "t"})

    # fälliger Post (geplant in der Vergangenheit)
    vergangen = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    post = _post_anlegen(auth_client, profil_id=profil["id"])
    auth_client.put(f"/api/postecke/posts/{post['id']}", json={"text": "Automatisch!"})
    auth_client.post(f"/api/postecke/posts/{post['id']}/status",
                     json={"status": "geplant", "geplant_am": vergangen})

    # noch nicht fälliger Post
    zukunft = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    post2 = _post_anlegen(auth_client, profil_id=profil["id"])
    auth_client.post(f"/api/postecke/posts/{post2['id']}/status",
                     json={"status": "geplant", "geplant_am": zukunft})

    anzahl = social_publish.veroeffentliche_faellige(db_session)
    assert anzahl == 1
    assert len(aufrufe) == 1

    fertig = auth_client.get(f"/api/postecke/posts/{post['id']}").json()
    assert fertig["status"] == "veroeffentlicht"
    offen = auth_client.get(f"/api/postecke/posts/{post2['id']}").json()
    assert offen["status"] == "geplant"

    # Fehlerfall: Publisher wirft -> publish_error am Post, Status bleibt geplant
    def _kaputt(db, post, profil):
        raise RuntimeError("Token abgelaufen")
    monkeypatch.setitem(social_publish.KANAL_PUBLISHER, "facebook_seite", _kaputt)
    post3 = _post_anlegen(auth_client, profil_id=profil["id"])
    auth_client.put(f"/api/postecke/posts/{post3['id']}", json={"text": "x"})
    auth_client.post(f"/api/postecke/posts/{post3['id']}/status",
                     json={"status": "geplant", "geplant_am": vergangen})
    assert social_publish.veroeffentliche_faellige(db_session) == 0
    fehler = auth_client.get(f"/api/postecke/posts/{post3['id']}").json()
    assert fehler["status"] == "geplant"
    assert "Token abgelaufen" in fehler["publish_error"]


# ── Datacenter-Ablage (Postecke) ──────────────────────────────────────────────
def _mock_storage_mit_download(monkeypatch):
    """Storage-Mock (upload/download/delete, api + service) für die Sync-Tests."""
    speicher = {}
    _up = lambda key, data, mt, db=None, backend=None: speicher.__setitem__(key, data)
    _del = lambda key, db=None: speicher.pop(key, None)
    for pfad in ("app.api.postecke.storage_service.upload_file",
                 "app.services.postecke.storage_service.upload_file"):
        monkeypatch.setattr(pfad, _up)
    for pfad in ("app.api.postecke.storage_service.delete_file",
                 "app.services.postecke.storage_service.delete_file"):
        monkeypatch.setattr(pfad, _del)
    monkeypatch.setattr("app.services.postecke.storage_service.download_file",
                        lambda key, db=None: (speicher[key], "application/octet-stream"))
    return speicher


def test_datacenter_ablage_beim_speichern_ohne_kontakt(auth_client, db_session, monkeypatch):
    """Ohne Kontakt: Content + Foto landen beim Speichern im Ordner „Postecke"."""
    from app.models.attachment import Attachment
    speicher = _mock_storage_mit_download(monkeypatch)

    post = _post_anlegen(auth_client, titel="Feuerwehrfest")
    auth_client.post(f"/api/postecke/posts/{post['id']}/fotos",
                     files=[("files", ("a.jpg", b"foto-a", "image/jpeg"))])
    auth_client.put(f"/api/postecke/posts/{post['id']}",
                    json={"text": "Toller Abend!", "hashtags": "#ff"})

    anlagen = (db_session.query(Attachment)
               .filter(Attachment.description.like(f"postecke:{post['id']}%")).all())
    assert len(anlagen) == 2  # Content-Text + 1 Foto
    assert all(a.folder == "Postecke" for a in anlagen)
    assert all(a.entity_type == "postecke" for a in anlagen)
    assert all(a.storage_key.startswith(f"postecke/Postecke/{post['id']}/") for a in anlagen)
    md = [a for a in anlagen if a.mimetype == "text/markdown"][0]
    inhalt = speicher[md.storage_key].decode("utf-8")
    assert "Toller Abend!" in inhalt and "#ff" in inhalt

    # Foto löschen -> Kopie verschwindet, Content bleibt
    foto = auth_client.get(f"/api/postecke/posts/{post['id']}").json()["fotos"][0]
    auth_client.delete(f"/api/postecke/fotos/{foto['id']}")
    rest = (db_session.query(Attachment)
            .filter(Attachment.description.like(f"postecke:{post['id']}%")).all())
    assert len(rest) == 1 and rest[0].mimetype == "text/markdown"


def test_datacenter_ablage_mit_kontakt(auth_client, db_session, monkeypatch):
    """Mit Kontakt: Ablage im Unterordner „Postecke" beim Kontakt."""
    from uuid import uuid4
    from app.models.attachment import Attachment
    _mock_storage_mit_download(monkeypatch)

    kontakt_id = str(uuid4())
    post = _post_anlegen(auth_client, titel="Kundenevent",
                         kontakt_id=kontakt_id, kontakt_name="Musterfirma")
    a = (db_session.query(Attachment)
         .filter(Attachment.description.like(f"postecke:{post['id']}%")).first())
    assert a is not None
    assert a.entity_type == "kontakte"
    assert str(a.entity_id) == kontakt_id
    assert a.contact_name == "Musterfirma"
    assert a.folder == "Postecke"
    assert a.storage_key.startswith("kontakte/Musterfirma/Postecke/")


def test_datacenter_ablage_video_und_persistenz(auth_client, db_session, monkeypatch):
    """Video wird als Kopie abgelegt und bleibt beim Löschen des Posts erhalten."""
    from app.models.attachment import Attachment
    speicher = _mock_storage_mit_download(monkeypatch)

    post = _post_anlegen(auth_client, titel="Clip")
    auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                     files={"file": ("clip.mp4", b"video-bytes", "video/mp4")})

    anlagen = (db_session.query(Attachment)
               .filter(Attachment.description.like(f"postecke:{post['id']}%")).all())
    v = [a for a in anlagen if "#video:" in a.description][0]
    assert v.mimetype == "video/mp4"
    assert v.storage_key.endswith("_Video.mp4")
    assert speicher[v.storage_key] == b"video-bytes"

    # Post löschen -> Datacenter-Kopien bleiben als Beleg erhalten
    auth_client.delete(f"/api/postecke/posts/{post['id']}")
    rest = (db_session.query(Attachment)
            .filter(Attachment.description.like(f"postecke:{post['id']}%")).count())
    assert rest >= 2  # Content-Text + Video-Kopie bleiben


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


# ── Instagram + öffentlicher Medien-Abruf ─────────────────────────────────────
class _IGResp:
    """Minimale httpx.Response-Attrappe für die Instagram-Tests."""
    def __init__(self, data):
        self._d = data
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._d


def _mock_ig_httpx(monkeypatch, status="FINISHED"):
    """httpx in social_publish mocken; sammelt die Aufrufe für Assertions."""
    from app.services import social_publish
    aufrufe = []

    def _post(url, data=None, files=None, timeout=None):
        aufrufe.append(("POST", url, data))
        if url.endswith("/media"):
            return _IGResp({"id": "container-x"})
        if url.endswith("/media_publish"):
            return _IGResp({"id": "media-x"})
        return _IGResp({})

    def _get(url, params=None, timeout=None):
        aufrufe.append(("GET", url, params))
        felder = (params or {}).get("fields", "")
        if "permalink" in felder:
            return _IGResp({"permalink": "https://www.instagram.com/p/abc/"})
        if "status_code" in felder:
            return _IGResp({"status_code": status})
        return _IGResp({})

    monkeypatch.setattr(social_publish.httpx, "post", _post)
    monkeypatch.setattr(social_publish.httpx, "get", _get)
    monkeypatch.setattr(social_publish.time, "sleep", lambda s: None)
    return aufrufe


def test_medien_token_signatur():
    from app.services import social_publish
    tok = social_publish.signiere_medien_token("foto", "abc-123", ttl=60)
    assert social_publish.pruefe_medien_token(tok) == ("foto", "abc-123")
    assert social_publish.pruefe_medien_token(tok + "x") is None   # manipuliert
    assert social_publish.pruefe_medien_token("kaputt") is None
    abgelaufen = social_publish.signiere_medien_token("foto", "abc-123", ttl=-5)
    assert social_publish.pruefe_medien_token(abgelaufen) is None


def test_oeffentlicher_medien_abruf(auth_client, monkeypatch):
    """Öffentlicher Endpunkt liefert ein Video per gültigem Token; sonst 404."""
    from app.services import social_publish
    _mock_storage(monkeypatch)
    monkeypatch.setattr("app.api.oeffentlich.storage_service.download_file",
                        lambda key, db=None: (b"video-bytes", "video/mp4"))

    post = _post_anlegen(auth_client)
    r = auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                         files={"file": ("clip.mp4", b"x", "video/mp4")})
    video_id = r.json()["video"]["id"]

    token = social_publish.signiere_medien_token("video", video_id, ttl=60)
    resp = auth_client.get(f"/api/oeffentlich/postecke/medien/{token}")
    assert resp.status_code == 200
    assert resp.content == b"video-bytes"

    assert auth_client.get("/api/oeffentlich/postecke/medien/kaputt").status_code == 404
    abgelaufen = social_publish.signiere_medien_token("video", video_id, ttl=-5)
    assert auth_client.get(f"/api/oeffentlich/postecke/medien/{abgelaufen}").status_code == 404


def _ig_profil_mit_post(auth_client, **post_kwargs):
    profil = _profil_anlegen(auth_client, name="Insta", kanal="instagram",
                             zugang={"ig_user_id": "123", "ig_token": "t"})
    assert profil["direktanbindung"] is True
    post = _post_anlegen(auth_client, profil_id=profil["id"], **post_kwargs)
    auth_client.put(f"/api/postecke/posts/{post['id']}", json={"text": "Hallo Insta"})
    return post


def test_instagram_einzelfoto(auth_client, monkeypatch):
    _mock_storage(monkeypatch)
    aufrufe = _mock_ig_httpx(monkeypatch)

    post = _ig_profil_mit_post(auth_client)
    auth_client.post(f"/api/postecke/posts/{post['id']}/fotos",
                     files=[("files", ("a.jpg", b"jpeg", "image/jpeg"))])

    r = auth_client.post(f"/api/postecke/posts/{post['id']}/veroeffentlichen")
    assert r.status_code == 200, r.text
    assert r.json()["extern_url"] == "https://www.instagram.com/p/abc/"
    container = [u for (m, u, d) in aufrufe if m == "POST" and u.endswith("/media")]
    assert len(container) == 1  # ein Foto = ein Container
    publish = [u for (m, u, d) in aufrufe if m == "POST" and u.endswith("/media_publish")]
    assert len(publish) == 1


def test_instagram_carousel(auth_client, monkeypatch):
    _mock_storage(monkeypatch)
    aufrufe = _mock_ig_httpx(monkeypatch)

    post = _ig_profil_mit_post(auth_client)
    for i in range(3):
        auth_client.post(f"/api/postecke/posts/{post['id']}/fotos",
                         files=[("files", (f"f{i}.jpg", b"jpeg", "image/jpeg"))])

    r = auth_client.post(f"/api/postecke/posts/{post['id']}/veroeffentlichen")
    assert r.status_code == 200, r.text
    container = [d for (m, u, d) in aufrufe if m == "POST" and u.endswith("/media")]
    # 3 Kind-Container + 1 Carousel-Container
    assert len(container) == 4
    carousel = [d for d in container if d.get("media_type") == "CAROUSEL"]
    assert len(carousel) == 1
    assert carousel[0]["children"].count(",") == 2  # 3 Kinder -> 2 Kommata


def test_instagram_reel(auth_client, monkeypatch):
    _mock_storage(monkeypatch)
    aufrufe = _mock_ig_httpx(monkeypatch, status="FINISHED")

    post = _ig_profil_mit_post(auth_client)
    auth_client.post(f"/api/postecke/posts/{post['id']}/video",
                     files={"file": ("clip.mp4", b"x", "video/mp4")})

    r = auth_client.post(f"/api/postecke/posts/{post['id']}/veroeffentlichen")
    assert r.status_code == 200, r.text
    container = [d for (m, u, d) in aufrufe if m == "POST" and u.endswith("/media")]
    assert len(container) == 1 and container[0]["media_type"] == "REELS"
    assert any("status_code" in (p or {}).get("fields", "")
               for (m, u, p) in aufrufe if m == "GET")


def test_instagram_verbindung_testen(auth_client, monkeypatch):
    from app.services import social_publish
    monkeypatch.setattr(social_publish.httpx, "get",
                        lambda url, params=None, timeout=None: _IGResp({"username": "wwinterface"}))
    profil = _profil_anlegen(auth_client, name="Insta", kanal="instagram",
                             zugang={"ig_user_id": "123", "ig_token": "t"})
    r = auth_client.post(f"/api/postecke/profile/{profil['id']}/verbindung-testen")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "wwinterface" in r.json()["message"]
