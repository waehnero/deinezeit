"""
Steuerfall-Matrix — Erlöskonto und Steuersatz aus Artikelgruppe × Kunde.

Der Befund, der diese Etappe ausgelöst hat: Im BMD-Export bestimmte sich das
Erlöskonto als ``pos.account_nr or default_erloes``, der USt-Code allein aus
dem Steuersatz. Die Konten 4040 (steuerbefreit), 4050 (innergemeinschaftlich)
und 4060 (Reverse Charge) standen zwar im Kontenplan, wurden aber nur bebucht,
wenn jemand sie an jeder einzelnen Position von Hand eintrug. Eine
IG-Lieferung landete sonst still auf 4000, dem Inlandskonto.

Am schärfsten geprüft ist deshalb die Unterscheidung, an der es hängt:
**Reverse Charge hat keinen Steuersatz, eine IG-Lieferung hat den Satz null.**
Würde man beides zusammenlegen, erschiene jeder Reverse-Charge-Umsatz in der
Voranmeldung als steuerfreier Umsatz statt als übergegangene Steuerschuld.

Die Tests bauen ihre Stammdaten selbst auf — die Reihe läuft gegen ein per
``create_all`` erzeugtes Schema, nicht gegen die Migrationen.
"""
from decimal import Decimal

import pytest

from app.models.accounting import AccountingAccount
from app.models.masterdata import (ArticleGroup, ArticleGroupAccount,
                                   EntityRecord, EntityType, FieldDefinition)
from app.services import artikelstamm
from app.services import steuerfall as steuerfall_service
from tests.conftest import TEST_USER_PASSWORD


# ── Hilfen ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "email": "admin@deinezeit.local", "password": TEST_USER_PASSWORD})
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


@pytest.fixture()
def konten(db_session):
    """Die vier Erlöskonten, um die es geht (EKR-Ausschnitt aus 0013)."""
    db_session.add_all([
        AccountingAccount(nr="4000", name="Erlöse 20% USt", typ="ertrag",
                          ust_code="U20", is_default_erloes=True),
        AccountingAccount(nr="4020", name="Erlöse 10% USt", typ="ertrag", ust_code="U10"),
        AccountingAccount(nr="4040", name="Erlöse steuerbefreit", typ="ertrag", ust_code="U00"),
        AccountingAccount(nr="4050", name="Erlöse innergemeinschaftlich", typ="ertrag", ust_code="UIG"),
        AccountingAccount(nr="4060", name="Erlöse Reverse Charge", typ="ertrag", ust_code="URC"),
    ])
    db_session.commit()


@pytest.fixture()
def artikel_typ(db_session):
    et = EntityType(name="Artikel", slug="artikel", tabs=[])
    db_session.add(et)
    db_session.flush()
    for name, key, typ, sort in [
        ("Bezeichnung", "bezeichnung", "text", 10),
        ("Artikelgruppe", "artikelgruppe", "lookup", 40),
        ("USt-Satz", "ust_satz", "dropdown", 230),
        ("Erlöskonto", "erloes_konto", "lookup", 400),
    ]:
        db_session.add(FieldDefinition(entity_type_id=et.id, name=name, key=key,
                                       field_type=typ, sort_order=sort))
    db_session.commit()
    return et


@pytest.fixture()
def kontakt_typ(db_session):
    et = EntityType(name="Kontakte", slug="kontakte", tabs=[])
    db_session.add(et)
    db_session.flush()
    db_session.add(FieldDefinition(entity_type_id=et.id, name="Name", key="name",
                                   field_type="text", sort_order=10))
    db_session.add(FieldDefinition(entity_type_id=et.id, name="Steuerfall",
                                   key="steuerfall", field_type="dropdown",
                                   sort_order=26, is_system=True))
    db_session.commit()
    return et


@pytest.fixture()
def gruppe(db_session, konten):
    """Artikelgruppe „DL" mit vollständig gepflegten Steuerfällen."""
    g = ArticleGroup(nr="DL", name="Dienstleistung", praefix="DL",
                     erloes_konto_nr="4000")
    db_session.add(g)
    db_session.flush()
    db_session.add_all([
        # Inland: kein eigener Satz — 20/13/10 hängen am Artikel.
        ArticleGroupAccount(article_group_id=g.id, steuerfall="inland",
                            konto_nr="4000"),
        ArticleGroupAccount(article_group_id=g.id, steuerfall="ig_lieferung",
                            konto_nr="4050", ust_satz=Decimal("0")),
        ArticleGroupAccount(article_group_id=g.id, steuerfall="drittland",
                            konto_nr="4040", ust_satz=Decimal("0")),
        ArticleGroupAccount(article_group_id=g.id, steuerfall="reverse_charge",
                            konto_nr="4060", ohne_steuer=True),
    ])
    db_session.commit()
    db_session.refresh(g)
    return g


def _kunde(db, kontakt_typ, fall=None, name="Kunde"):
    daten = {"name": name}
    if fall is not None:
        daten["steuerfall"] = fall
    rec = EntityRecord(entity_type_id=kontakt_typ.id, display_name=name, data=daten)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _artikel(db, artikel_typ, **daten):
    werte = {"bezeichnung": "Beratung", "artikelgruppe": "DL", "ust_satz": "20"}
    werte.update(daten)
    rec = EntityRecord(entity_type_id=artikel_typ.id,
                       display_name=werte["bezeichnung"], data=werte)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# ── Steuerfall-Kennungen ──────────────────────────────────────────────────────

def test_unbekannter_steuerfall_wird_zum_inland():
    """Ein Tippfehler im Stammsatz darf keinen Umsatz steuerfrei stellen.

    Von den beiden möglichen Irrtümern ist nur einer schmerzlos heilbar: Wer
    fälschlich Inland bucht, zahlt zu viel Steuer — wer fälschlich steuerfrei
    bucht, schuldet sie nach.
    """
    for eingabe in [None, "", "   ", "mondphase", "Inland ", "IG"]:
        assert steuerfall_service.normieren(eingabe) in steuerfall_service.KENNUNGEN
    assert steuerfall_service.normieren("mondphase") == "inland"
    assert steuerfall_service.normieren(None) == "inland"


def test_anzeigename_wird_auch_angenommen():
    """Der Kontakt speichert den Wert einer Auswahlliste, nicht die Kennung."""
    assert steuerfall_service.normieren("Reverse Charge") == "reverse_charge"
    assert steuerfall_service.normieren("Innergemeinschaftliche Lieferung") == "ig_lieferung"


# ── Kaskade je Steuerfall ─────────────────────────────────────────────────────

def test_inland_bucht_auf_das_inlandskonto(db_session, artikel_typ, kontakt_typ, gruppe):
    kunde = _kunde(db_session, kontakt_typ, "Inland")
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4000"
    assert v["ust_satz"] == Decimal("20")
    assert v["reverse_charge"] is False


def test_ig_lieferung_bucht_auf_4050_steuerfrei(db_session, artikel_typ,
                                                kontakt_typ, gruppe):
    """Der Fall, der vorher still auf 4000 gelandet ist."""
    kunde = _kunde(db_session, kontakt_typ, "Innergemeinschaftliche Lieferung")
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4050"
    assert v["ust_satz"] == Decimal("0")
    assert v["reverse_charge"] is False


def test_drittland_bucht_auf_4040(db_session, artikel_typ, kontakt_typ, gruppe):
    kunde = _kunde(db_session, kontakt_typ, "Ausfuhr (Drittland)")
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4040"
    assert v["ust_satz"] == Decimal("0")


def test_reverse_charge_hat_keinen_satz(db_session, artikel_typ, kontakt_typ, gruppe):
    """Kein Satz — nicht null Prozent.

    Geprüft wird die Bedingung: ``ust_satz`` ist None UND das Kennzeichen ist
    gesetzt. Eine Null würde den Umsatz in der Voranmeldung als steuerfreien
    Umsatz ausweisen statt als übergegangene Steuerschuld.
    """
    kunde = _kunde(db_session, kontakt_typ, "Reverse Charge")
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4060"
    assert v["reverse_charge"] is True
    assert v["ust_satz"] is None


def test_gegenprobe_ig_ist_nicht_reverse_charge(db_session, artikel_typ,
                                                kontakt_typ, gruppe):
    """Die beiden dürfen sich nicht angleichen — sonst ist der Test blind."""
    ig = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data,
        contact_id=_kunde(db_session, kontakt_typ, "Innergemeinschaftliche Lieferung", name="A").id)
    rc = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data,
        contact_id=_kunde(db_session, kontakt_typ, "Reverse Charge", name="B").id)

    assert ig["reverse_charge"] is False and ig["ust_satz"] == Decimal("0")
    assert rc["reverse_charge"] is True and rc["ust_satz"] is None
    assert ig["erloes_konto"] != rc["erloes_konto"]


# ── Rückfälle ─────────────────────────────────────────────────────────────────

def test_kunde_ohne_steuerfall_gilt_als_inland(db_session, artikel_typ,
                                               kontakt_typ, gruppe):
    """Das bisherige Verhalten — Bestandsdaten ändern sich nicht."""
    kunde = _kunde(db_session, kontakt_typ, None)
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data, contact_id=kunde.id)
    assert v["steuerfall"] == "inland"
    assert v["erloes_konto"] == "4000"


def test_ohne_kunde_gilt_das_inland(db_session, artikel_typ, gruppe):
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ).data)
    assert v["steuerfall"] == "inland"
    assert v["erloes_konto"] == "4000"


def test_ungepflegter_steuerfall_faellt_auf_das_gruppenkonto(
        db_session, artikel_typ, kontakt_typ, konten):
    """Ohne Steuerfall-Zeile bleibt es beim bisherigen Verhalten.

    Wichtig für Bestände, in denen die Startbelegung nicht griff, weil der
    Kontenplan umgebaut wurde.
    """
    g = ArticleGroup(nr="WA", name="Ware", praefix="WA", erloes_konto_nr="4020")
    db_session.add(g)
    db_session.commit()

    kunde = _kunde(db_session, kontakt_typ, "Ausfuhr (Drittland)")
    v = artikelstamm.vorgaben_fuer_artikel(
        db_session, _artikel(db_session, artikel_typ, artikelgruppe="WA").data,
        contact_id=kunde.id)
    assert v["erloes_konto"] == "4020"


# ── Vorrang zwischen Artikelkonto und Steuerfall ──────────────────────────────

def test_artikelkonto_gewinnt_im_inland(db_session, artikel_typ, kontakt_typ, gruppe):
    """Im Inland ist das Artikelkonto eine Einordnung des Sortiments."""
    kunde = _kunde(db_session, kontakt_typ, "Inland")
    artikel = _artikel(db_session, artikel_typ, erloes_konto="4020")
    v = artikelstamm.vorgaben_fuer_artikel(db_session, artikel.data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4020"


def test_steuerfall_gewinnt_im_ausland(db_session, artikel_typ, kontakt_typ, gruppe):
    """Und hier gewinnt er gegen das Artikelkonto — mit Absicht.

    Der Steuerfall ist eine rechtliche Eigenschaft des Geschäfts, das
    Artikelkonto nur eine Einordnung des Sortiments. Ein Artikel mit fest
    hinterlegtem 4020 dürfte keine innergemeinschaftliche Lieferung auf ein
    Inlandserlöskonto buchen — das wäre nicht „so eingestellt", sondern falsch.
    """
    kunde = _kunde(db_session, kontakt_typ, "Innergemeinschaftliche Lieferung")
    artikel = _artikel(db_session, artikel_typ, erloes_konto="4020")
    v = artikelstamm.vorgaben_fuer_artikel(db_session, artikel.data, contact_id=kunde.id)
    assert v["erloes_konto"] == "4050"


# ── Endpunkte ─────────────────────────────────────────────────────────────────

def test_vorgaben_endpunkt_nimmt_den_kunden(admin_client, db_session, artikel_typ,
                                            kontakt_typ, gruppe):
    artikel = _artikel(db_session, artikel_typ)
    kunde = _kunde(db_session, kontakt_typ, "Reverse Charge")

    ohne = admin_client.get(f"/api/masterdata/artikel/{artikel.id}/vorgaben")
    assert ohne.status_code == 200
    assert ohne.json()["erloes_konto"] == "4000"

    mit = admin_client.get(f"/api/masterdata/artikel/{artikel.id}/vorgaben",
                           params={"contact_id": str(kunde.id)})
    assert mit.status_code == 200
    assert mit.json()["erloes_konto"] == "4060"
    assert mit.json()["reverse_charge"] is True
    assert mit.json()["ust_satz"] is None
    assert mit.json()["steuerfall"] == "reverse_charge"


def test_gruppe_liefert_alle_steuerfaelle(admin_client, db_session, konten):
    """Auch die ungepflegten — sonst sähe „noch nicht hinterlegt" aus wie
    „gibt es nicht", und das Formular müsste die Zeilen selbst erfinden."""
    db_session.add(ArticleGroup(nr="WA", name="Ware", praefix="WA"))
    db_session.commit()

    resp = admin_client.get("/api/masterdata/artikelgruppen")
    assert resp.status_code == 200
    konten_liste = resp.json()[0]["konten"]
    assert [k["steuerfall"] for k in konten_liste] == steuerfall_service.KENNUNGEN
    assert all(k["konto_nr"] is None for k in konten_liste)


def test_konten_setzen_und_lesen(admin_client, db_session, konten):
    db_session.add(ArticleGroup(nr="WA", name="Ware", praefix="WA"))
    db_session.commit()
    gid = admin_client.get("/api/masterdata/artikelgruppen").json()[0]["id"]

    resp = admin_client.put(f"/api/masterdata/artikelgruppen/{gid}/konten", json=[
        {"steuerfall": "inland", "konto_nr": "4000"},
        {"steuerfall": "ig_lieferung", "konto_nr": "4050", "ust_satz": "0"},
        {"steuerfall": "drittland", "konto_nr": None},
        {"steuerfall": "reverse_charge", "konto_nr": "4060", "ohne_steuer": True},
    ])
    assert resp.status_code == 200, resp.text
    zeilen = {k["steuerfall"]: k for k in resp.json()["konten"]}
    assert zeilen["ig_lieferung"]["konto_nr"] == "4050"
    assert zeilen["reverse_charge"]["ohne_steuer"] is True
    # Die leere Zeile wurde nicht gespeichert, erscheint aber als ungepflegt
    assert zeilen["drittland"]["konto_nr"] is None


def test_satz_und_kein_satz_schliessen_einander_aus(admin_client, db_session, konten):
    db_session.add(ArticleGroup(nr="WA", name="Ware", praefix="WA"))
    db_session.commit()
    gid = admin_client.get("/api/masterdata/artikelgruppen").json()[0]["id"]

    resp = admin_client.put(f"/api/masterdata/artikelgruppen/{gid}/konten", json=[
        {"steuerfall": "reverse_charge", "konto_nr": "4060",
         "ust_satz": "0", "ohne_steuer": True},
    ])
    assert resp.status_code == 400
    assert "Reverse Charge" in resp.json()["detail"]


def test_unbekannter_steuerfall_wird_abgelehnt(admin_client, db_session, konten):
    db_session.add(ArticleGroup(nr="WA", name="Ware", praefix="WA"))
    db_session.commit()
    gid = admin_client.get("/api/masterdata/artikelgruppen").json()[0]["id"]

    resp = admin_client.put(f"/api/masterdata/artikelgruppen/{gid}/konten", json=[
        {"steuerfall": "mondphase", "konto_nr": "4000"},
    ])
    assert resp.status_code == 400


def test_konten_setzen_nur_admin(auth_client, db_session, konten):
    db_session.add(ArticleGroup(nr="WA", name="Ware", praefix="WA"))
    db_session.commit()
    gid = str(db_session.query(ArticleGroup).first().id)
    resp = auth_client.put(f"/api/masterdata/artikelgruppen/{gid}/konten", json=[])
    assert resp.status_code == 403


def test_steuerfaelle_endpunkt(auth_client):
    resp = auth_client.get("/api/masterdata/steuerfaelle")
    assert resp.status_code == 200
    assert [f["kennung"] for f in resp.json()] == steuerfall_service.KENNUNGEN
