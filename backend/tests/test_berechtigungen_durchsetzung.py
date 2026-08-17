"""
Durchsetzung der Rechte an den Endpunkten (Teiletappe 2b)
========================================================

Das Rechtemodell ist nur so viel wert wie seine Durchsetzung. Getestet wird
deshalb nicht die Rechenlogik (das tut ``test_berechtigungen.py``), sondern
was am HTTP-Endpunkt wirklich passiert:

* Leserecht allein darf nicht zum Anlegen, Ändern oder Löschen genügen.
* Der Umfang „nur eigene" muss auch greifen, wenn jemand ausdrücklich nach
  einem fremden Benutzer filtert oder eine ID direkt aufruft.
* Stornieren gilt als Löschen, nicht als Ändern.
"""
import pytest

from app.core import berechtigungen as B
from app.models.user import PermissionGroup
from app.models.zeiterfassung import TimeEntry
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def _blatt(**module) -> dict:
    blatt = B.leeres_rechteblatt()
    for modul, werte in module.items():
        blatt[modul].update(werte)
    return blatt


def _in_gruppe(db, user, name, rechte):
    g = PermissionGroup(name=name, rechte=rechte)
    db.add(g)
    user.groups = [g]
    db.commit()
    return g


def _kopf(client, email=TEST_USER_EMAIL, passwort=TEST_USER_PASSWORD) -> dict:
    resp = client.post("/api/auth/login",
                       json={"email": email, "password": passwort})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Lesen genügt nicht zum Schreiben ─────────────────────────────────────────

def test_leserecht_erlaubt_kein_anlegen(client, test_user, db_session):
    """Der Kern der Etappe: Ansehen und Ändern sind jetzt zwei Dinge.

    Vorher war beides dasselbe Häkchen — wer Aufgaben sehen durfte, durfte sie
    auch anlegen und löschen.
    """
    _in_gruppe(db_session, test_user, "Nur ansehen",
               _blatt(aufgaben={"lesen": True, "umfang": "alle"}))
    kopf = _kopf(client)

    assert client.get("/api/aufgaben/", headers=kopf).status_code == 200
    angelegt = client.post("/api/aufgaben/", headers=kopf,
                           json={"title": "Sollte nicht gehen"})
    assert angelegt.status_code == 403
    # Die Meldung muss sagen, welches Recht fehlt — sonst kann auch der
    # Administrator die Rückfrage nicht beantworten.
    assert "Anlegen und ändern" in angelegt.json()["detail"]


def test_schreibrecht_erlaubt_kein_loeschen(client, test_user, db_session):
    _in_gruppe(db_session, test_user, "Schreiben ohne Löschen",
               _blatt(aufgaben={"lesen": True, "schreiben": True,
                                "umfang": "alle"}))
    kopf = _kopf(client)

    neu = client.post("/api/aufgaben/", headers=kopf, json={"title": "Testaufgabe"})
    # 201 Created — nicht auf einen einzelnen Erfolgscode festnageln, sonst
    # prüft der Test die HTTP-Konvention des Endpunkts statt der Rechte.
    assert neu.status_code in (200, 201), neu.text
    todo_id = neu.json()["id"]

    weg = client.delete(f"/api/aufgaben/{todo_id}", headers=kopf)
    assert weg.status_code == 403
    assert "Löschen" in weg.json()["detail"]


def test_volles_recht_darf_loeschen(client, test_user, db_session):
    _in_gruppe(db_session, test_user, "Alles auf Aufgaben",
               _blatt(aufgaben={"lesen": True, "schreiben": True,
                                "loeschen": True, "umfang": "alle"}))
    kopf = _kopf(client)
    neu = client.post("/api/aufgaben/", headers=kopf, json={"title": "Weg damit"})
    assert neu.status_code in (200, 201), neu.text
    weg = client.delete(f"/api/aufgaben/{neu.json()['id']}", headers=kopf)
    assert weg.status_code in (200, 204), weg.text


def test_lesender_post_braucht_kein_schreibrecht(client, test_user, db_session):
    """``/ki-nachtragen`` speichert nichts und darf deshalb mit Lesen laufen.

    Die Ausnahmeliste soll klein bleiben, aber sie muss funktionieren — sonst
    wäre eine reine Auswertung ohne Grund gesperrt.
    """
    _in_gruppe(db_session, test_user, "Zeit lesen",
               _blatt(zeiterfassung={"lesen": True, "umfang": "alle"}))
    kopf = _kopf(client)
    resp = client.post("/api/zeiterfassung/ki-nachtragen", headers=kopf,
                       json={"transkript": "Gestern zwei Stunden Musterprojekt"})
    # Kein 403. Ob die KI-Auswertung selbst gelingt, hängt von der
    # Konfiguration ab und ist hier nicht die Frage.
    assert resp.status_code != 403


def test_status_batch_braucht_schreibrecht(client, test_user, db_session):
    """Gegenprobe zur Ausnahmeliste: Dieser POST *setzt* Status."""
    _in_gruppe(db_session, test_user, "Zeit lesen",
               _blatt(zeiterfassung={"lesen": True, "umfang": "alle"}))
    kopf = _kopf(client)
    resp = client.post("/api/zeiterfassung/entries/status-batch", headers=kopf,
                       json={"entry_ids": [], "status": "gesperrt"})
    assert resp.status_code == 403


# ── Umfang: nur eigene ───────────────────────────────────────────────────────

def _zeiteintrag(db, user, notiz="Test"):
    from datetime import datetime, timezone
    eintrag = TimeEntry(user_id=user.id, note=notiz,
                        started_at=datetime.now(timezone.utc))
    db.add(eintrag)
    db.commit()
    db.refresh(eintrag)
    return eintrag


def test_umfang_eigene_blendet_fremde_zeiten_aus(client, test_user, admin_user,
                                                 db_session):
    """Die größte Lücke im Modul: Der ``user_id``-Filter war ungeprüft.

    Ohne ihn lieferte die Abfrage die Einträge aller Mitarbeiter, mit ihm die
    eines beliebigen Kollegen — wer das Modul hatte, sah die Arbeitszeiten des
    ganzen Betriebs.
    """
    _zeiteintrag(db_session, test_user, "meine Zeit")
    _zeiteintrag(db_session, admin_user, "fremde Zeit")

    _in_gruppe(db_session, test_user, "Nur eigene Zeiten",
               _blatt(zeiterfassung={"lesen": True, "umfang": "eigene"}))
    kopf = _kopf(client)

    liste = client.get("/api/zeiterfassung/entries", headers=kopf)
    assert liste.status_code == 200
    notizen = [e["note"] for e in liste.json()["items"]]
    assert notizen == ["meine Zeit"]

    # Auch der ausdrückliche Filter auf einen fremden Benutzer bringt nichts.
    gezielt = client.get("/api/zeiterfassung/entries",
                         params={"user_id": str(admin_user.id)}, headers=kopf)
    assert [e["note"] for e in gezielt.json()["items"]] == ["meine Zeit"]


def test_umfang_eigene_sperrt_fremden_einzelabruf(client, test_user, admin_user,
                                                  db_session):
    """Sonst genügte eine bekannte ID, um die Einschränkung zu umgehen."""
    fremd = _zeiteintrag(db_session, admin_user, "fremde Zeit")
    _in_gruppe(db_session, test_user, "Nur eigene Zeiten",
               _blatt(zeiterfassung={"lesen": True, "umfang": "eigene"}))

    resp = client.get(f"/api/zeiterfassung/entries/{fremd.id}",
                      headers=_kopf(client))
    # 404 statt 403 — ein „verboten" wäre die Auskunft, dass es den Eintrag gibt.
    assert resp.status_code == 404


def test_umfang_alle_zeigt_auch_fremde(client, test_user, admin_user, db_session):
    _zeiteintrag(db_session, test_user, "meine Zeit")
    _zeiteintrag(db_session, admin_user, "fremde Zeit")
    _in_gruppe(db_session, test_user, "Alle Zeiten",
               _blatt(zeiterfassung={"lesen": True, "umfang": "alle"}))

    liste = client.get("/api/zeiterfassung/entries", headers=_kopf(client))
    assert len(liste.json()["items"]) == 2


def test_umfang_eigene_bei_aufgaben(client, test_user, admin_user, db_session):
    from app.models.aufgaben import Todo
    db_session.add(Todo(title="meine", created_by=test_user.id))
    db_session.add(Todo(title="fremde", created_by=admin_user.id))
    db_session.commit()

    _in_gruppe(db_session, test_user, "Nur eigene Aufgaben",
               _blatt(aufgaben={"lesen": True, "umfang": "eigene"}))

    liste = client.get("/api/aufgaben/", headers=_kopf(client))
    assert liste.status_code == 200
    assert [t["title"] for t in liste.json()] == ["meine"]


# ── Stornieren gilt als Löschen ──────────────────────────────────────────────

def test_stornieren_verlangt_loeschrecht(client, test_user, db_session):
    """Ein ausgestellter Beleg lässt sich nicht löschen — Storno ist der
    einzige Weg, ihn unwirksam zu machen. Wer Rechnungen schreiben darf, soll
    sie deshalb nicht zwangsläufig entwerten können.
    """
    _in_gruppe(db_session, test_user, "Verkauf ohne Löschen",
               _blatt(verkauf={"lesen": True, "schreiben": True,
                               "umfang": "alle"}))
    kopf = _kopf(client)

    # Pflichtfelder wie in test_verkauf_belegsperre._create_invoice — sonst
    # antwortet der Endpunkt mit 422 und die Rechteprüfung kommt nie dran.
    neu = client.post("/api/invoices", headers=kopf, json={
        "doc_type": "rechnung",
        "title": "Storno-Versuch",
        "date": "2026-07-06",
        "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "Beratung",
                       "quantity": "1", "unit_price": "100", "tax_rate": "20"}],
    })
    assert neu.status_code in (200, 201), neu.text
    invoice_id = neu.json()["id"]

    storno = client.post(f"/api/invoices/{invoice_id}/cancel", headers=kopf,
                         json={"reason": "Versuch"})
    assert storno.status_code == 403
    assert "Löschen" in storno.json()["detail"]


# ── Stammdaten: Lesen bleibt offen, Schreiben nicht ──────────────────────────

def test_stammdaten_lesen_offen_schreiben_braucht_recht(client, test_user,
                                                        db_session):
    """Stammdaten müssen aus jedem Modul lesbar sein (Auswahlfelder).

    Deshalb hat der Router bewusst keine Sperre — das Ändern prüft der Endpunkt
    selbst, und zwar seit Migration 0055 auf das Schreibrecht statt auf die
    reine Modulfreigabe.
    """
    _in_gruppe(db_session, test_user, "Ohne Stammdaten",
               _blatt(aufgaben={"lesen": True, "umfang": "alle"}))
    kopf = _kopf(client)

    assert client.get("/api/masterdata/types", headers=kopf).status_code == 200
    resp = client.post("/api/masterdata/types/kunden/records", headers=kopf,
                       json={"data": {"name": "Nicht erlaubt"}})
    assert resp.status_code == 403


# ── Administratoren bleiben handlungsfähig ───────────────────────────────────

def test_admin_darf_alles_ohne_gruppe(client, admin_user, db_session):
    admin_user.groups = []
    db_session.commit()
    kopf = _kopf(client, admin_user.email)

    neu = client.post("/api/aufgaben/", headers=kopf, json={"title": "Adminsache"})
    assert neu.status_code in (200, 201), neu.text
    weg = client.delete(f"/api/aufgaben/{neu.json()['id']}", headers=kopf)
    assert weg.status_code in (200, 204), weg.text
