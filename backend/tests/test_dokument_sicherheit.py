"""
S02 — Feldinhalte in Dokumenten (Belege, Mahnungen, Berichte, Protokolle).

Prüft die Regeln aus ``core/dokument_html.py`` und dass alle Dokumentwege
sie benutzen: Vorschau, PDF-Download, Archivierung, E-Mail-Anhang, Mahnung,
Projektzeitbericht, Belegbuch, Umsatzsteuer, Aufgabe, DSGVO-Bescheinigung.

Alle Daten sind erfunden; „Angriffe" sind harmlose Marker (``S02-…``). Der
eigentliche Renderer läuft echt; wo das HTML geprüft wird, wird es an der
Schnittstelle zu ``render_pdf`` mitgeschnitten (der Aufruf geht danach
unverändert weiter).
"""
import base64
import io
from html.parser import HTMLParser
import os
import re
import shutil
import tempfile

import pypdf
import pytest

from app.core import dokument_html as dh
from app.models.masterdata import EntityType, EntityRecord

# Feldinhalt mit allen typischen Einschleusungsversuchen (harmlose Marker)
BOESE = ('<b>Fett</b> &amp; <i>kursiv</i> A&B 1<2 '
         '<script>window.S02=1</script><style>body{background:url(http://127.0.0.1:9/s02)}</style>'
         '<img src="http://127.0.0.1:9/s02-img" onerror="S02()">'
         '<link rel="attachment" href="/tmp/s02-marker.txt">'
         '<a href="javascript:S02()">Link</a>'
         '<iframe src="http://127.0.0.1:9/s02-frame"></iframe>'
         '<svg><image href="http://127.0.0.1:9/s02-svg"/></svg>'
         '<p style="text-align:center;background:url(http://127.0.0.1:9/s02-css)" onclick="S02()">Mitte</p>')

class _Struktur(HTMLParser):
    """Sammelt, was im HTML strukturwirksam ist (Tags, Attribute, Stylesheets)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.attribute, self.stile = [], [], []
        self._im_stil = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attribute.extend((tag, k, v or "") for k, v in attrs)
        self._im_stil = tag == "style"

    def handle_endtag(self, tag):
        self._im_stil = False

    def handle_data(self, data):
        if self._im_stil:
            self.stile.append(data)


def _ohne_verbotenes(html: str):
    """
    Prüft die **Struktur**, nicht den Text: Ein maskiertes ``&lt;img …&gt;``
    ist harmloser sichtbarer Text, ein echtes ``<img src="http…">`` nicht.
    """
    p = _Struktur()
    p.feed(html)
    verboten = {"script", "img", "link", "iframe", "svg", "object", "embed", "a",
                "form", "input", "base", "image", "use", "audio", "video", "source"}
    # <img> ist nur mit data:-Quelle erlaubt (Logo, Positionsbild)
    for tag in p.tags:
        if tag in verboten and tag != "img":
            raise AssertionError(f"<{tag}> im Dokument-HTML")
    for tag, name, wert in p.attribute:
        assert not name.startswith("on"), f"Eventhandler {name} an <{tag}>"
        if name in ("src", "href", "xlink:href", "data", "action", "srcset", "poster"):
            assert wert.startswith("data:"), f"{name}={wert!r} an <{tag}>"
        if name == "style":
            assert "url(" not in wert.lower() and "127.0.0.1" not in wert, (tag, wert)
    for stil in p.stile:
        klein = stil.lower()
        assert "@import" not in klein and "127.0.0.1" not in klein and "</" not in klein, stil[:200]
    # Rohtext darf keine unmaskierten Marker-Tags enthalten
    assert "<script" not in html.lower()


# ── Regeln: text / rich_text / CSS ────────────────────────────────────────────

def test_text_maskiert_alles():
    assert dh.text('<b>x</b> & "y"') == "&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;"
    assert dh.text(None) == ""
    assert dh.text(12) == "12"


def test_rich_text_behaelt_erlaubte_formatierung():
    erg = dh.rich_text("<p>Absatz <b>fett</b> <strong>stark</strong> <i>k</i> <em>e</em> "
                       "<u>u</u> <s>s</s><br><small>klein</small> m<sup>2</sup> H<sub>2</sub>O</p>"
                       "<ul><li>eins</li></ul><ol><li>zwei</li></ol>")
    for tag in ("<p>", "<b>fett</b>", "<strong>stark</strong>", "<i>k</i>", "<em>e</em>",
                "<u>u</u>", "<s>s</s>", "<br>", "<small>klein</small>", "<sup>2</sup>",
                "<sub>2</sub>", "<ul><li>eins</li></ul>", "<ol><li>zwei</li></ol>"):
        assert tag in erg


def test_rich_text_entfernt_aktive_inhalte_und_ressourcen():
    erg = dh.rich_text(BOESE)
    _ohne_verbotenes(erg)
    assert "<b>Fett</b>" in erg and "<i>kursiv</i>" in erg
    assert "window.S02" not in erg                      # Skriptinhalt entfällt ganz
    assert '<p style="text-align: center">Mitte</p>' in erg
    assert "Link" in erg                                 # Text des Links bleibt


def test_rich_text_maskiert_einfachen_text_korrekt_und_nicht_doppelt():
    assert dh.rich_text("Müller & Söhne GmbH") == "Müller &amp; Söhne GmbH"
    # Wie bisher im Browser/PDF: ``<Wort>`` gilt in Rich-Text-Feldern als Tag
    # und ist kein erlaubtes — es entfällt, statt sichtbar zu werden.
    assert dh.rich_text("Firma <GmbH>") == "Firma "
    assert dh.rich_text("A &amp; B") == "A &amp; B"        # Altbestand: nicht doppelt
    assert dh.rich_text("1 < 2 > 0") == "1 &lt; 2 &gt; 0"
    assert dh.rich_text(None) == ""


@pytest.mark.parametrize("stil", [
    "color:red", "text-align:center;color:red", "text-align: url(x)",
    "background:url(http://127.0.0.1:9/x)", "text-align:center}body{x:y",
])
def test_rich_text_laesst_nur_textausrichtung_als_stil(stil):
    erg = dh.rich_text(f'<p style="{stil}">x</p>')
    assert "url" not in erg and "color" not in erg and "{" not in erg


def test_farbe_nur_hex():
    assert dh.farbe("#ef7d00", "#000") == "#ef7d00"
    assert dh.farbe("#abc", "#000") == "#abc"
    for wert in ("red", "#ef7d00;}body{x", "url(x)", "", None, "#12345g", "expression(1)"):
        assert dh.farbe(wert, "#000000") == "#000000"


def test_css_block_bleibt_im_style_element():
    erg = dh.css_block('.a{color:red}</style><script>S02()</script>@import url("http://x/y.css");')
    assert "<" not in erg and "@import" not in erg
    assert ".a{color:red}" in erg


def test_css_zeichenkette():
    erg = dh.css_zeichenkette('Max "Muster"; }<b>\\')
    assert '"' not in erg and ";" not in erg and "}" not in erg and "<" not in erg
    assert erg.startswith("Max ")


def test_vorschau_absichern_setzt_csp_als_erstes():
    html = dh.vorschau_absichern("<!DOCTYPE html><html><head><meta charset='utf-8'></head><body></body></html>")
    assert html.index("Content-Security-Policy") < html.index("charset")
    assert "default-src 'none'" in html and "img-src data:" in html


# ── Logos aus dem static-Verzeichnis ──────────────────────────────────────────

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture()
def static_dir():
    basis = tempfile.mkdtemp(prefix="s02-static-")
    wurzel = os.path.join(basis, "static")
    os.makedirs(os.path.join(wurzel, "logos"))
    with open(os.path.join(wurzel, "logos", "logo.png"), "wb") as f:
        f.write(PNG)
    with open(os.path.join(wurzel, "logos", "falsch.png"), "wb") as f:
        f.write(b"S02-MARKER kein Bild")
    with open(os.path.join(basis, "geheim.png"), "wb") as f:
        f.write(PNG)                                        # außerhalb von static
    os.symlink(os.path.join(basis, "geheim.png"), os.path.join(wurzel, "logos", "link.png"))
    yield wurzel
    shutil.rmtree(basis, ignore_errors=True)


def test_logo_aus_static_wird_eingebettet(static_dir):
    url = dh.static_bild_datenurl("/api/static/logos/logo.png", static_dir)
    assert url.startswith("data:image/png;base64,")


@pytest.mark.parametrize("pfad", [
    "/api/static/../geheim.png",
    "/api/static/logos/../../geheim.png",
    "/api/static/logos/link.png",              # Symlink hinaus
    "/api/static/logos/falsch.png",            # Inhalt passt nicht zur Endung
    "/api/static/logos/fehlt.png",
    "/etc/hostname",
    "file:///etc/hostname",
    "http://127.0.0.1:9/logo.png",
    "/api/staticX/logo.png",
])
def test_logo_ausserhalb_oder_kein_bild_wird_abgewiesen(static_dir, pfad):
    assert dh.static_bild_datenurl(pfad, static_dir) == ""


# ── Belege: Vorschau, PDF, alle fünf Vorlagen ─────────────────────────────────

def _kontakt(db, name="Bauherr <b>GmbH</b>", **daten):
    et = db.query(EntityType).filter_by(slug="kontakte").first()
    if not et:
        et = EntityType(name="Kontakte", slug="kontakte")
        db.add(et)
        db.flush()
    werte = {"email": "buero@bauherr.example", "adresse": "Ringstraße 9<img src=x>",
             "plz": "1010", "ort": "Wien", "fusszeile": "<b>Eigentumsvorbehalt</b><script>x</script>"}
    werte.update(daten)
    rec = EntityRecord(entity_type_id=et.id, display_name=name, data=werte)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _beleg(client, contact_id=None, **extra):
    payload = {
        "doc_type": "rechnung",
        "contact_id": str(contact_id) if contact_id else None,
        "title": 'Sanierung <img src="http://127.0.0.1:9/titel">',
        "reference": "<script>S02</script>REF-1",
        "date": "2026-07-06", "delivery_date": "2026-07-06", "due_date": "2026-08-05",
        "intro_text": BOESE, "outro_text": "Danke! <b>Zahlbar</b> sofort.",
        "positions": [
            {"pos_type": "heading", "description": "Überschrift <u>Bau</u>"},
            {"pos_type": "item", "description": BOESE, "detail": "Detail <i>ok</i><img src=x onerror=S02()>",
             "quantity": "2", "unit": "<b>Std</b>", "unit_price": "100", "tax_rate": "20"},
            {"pos_type": "text", "description": "Hinweis <script>S02()</script>"},
        ],
    }
    payload.update(extra)
    resp = client.post("/api/invoices", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def mitschnitt(monkeypatch):
    """Schneidet das HTML an der Schnittstelle zu render_pdf mit (Aufruf läuft weiter)."""
    from app.services import (aufgaben_pdf, dunning_pdf, gdpr_pdf, invoice_pdf, pdf_render)
    from app.api import invoice_buchhaltung, reports
    gesehen = []
    echt = pdf_render.render_pdf

    def _render(html, **kw):
        gesehen.append(html)
        return echt(html, **kw)

    for modul in (invoice_pdf, dunning_pdf, aufgaben_pdf, gdpr_pdf, invoice_buchhaltung, reports):
        monkeypatch.setattr(modul, "render_pdf", _render)
    return gesehen


def test_beleg_vorschau_ist_bereinigt_und_abgeschottet(auth_client, db_session):
    from app.models.settings import Setting
    k = _kontakt(db_session)
    firma = _kontakt(db_session, "Eigene Firma", ort="Lengau")
    db_session.add(Setting(key="company_contact_id", value=str(firma.id)))
    db_session.commit()
    b = _beleg(auth_client, k.id)
    resp = auth_client.get(f"/api/invoices/{b['id']}/preview")
    assert resp.status_code == 200
    csp = resp.headers["content-security-policy"]
    assert "sandbox" in csp and "default-src 'none'" in csp and "script-src" not in csp.replace("default-src", "")
    assert resp.headers["x-content-type-options"] == "nosniff"
    html = resp.text
    assert '<meta http-equiv="Content-Security-Policy"' in html
    _ohne_verbotenes(html)
    assert "<b>Fett</b>" in html                          # Rich Text bleibt formatiert
    assert "&lt;b&gt;Std&lt;/b&gt;" in html                # Einheit ist gewöhnlicher Text
    assert "Bauherr &lt;b&gt;GmbH&lt;/b&gt;" in html       # Name ebenso
    assert "<b>Eigentumsvorbehalt</b>" in html             # Fußzeile = Rich Text


@pytest.mark.parametrize("vorlage", [1, 2, 3, 4, 5])
def test_alle_vorlagen_bereinigen(auth_client, db_session, vorlage):
    from app.models.invoice import Invoice
    from app.api.invoice import _load_pdf_context
    from app.services.invoice_pdf import generate_html_preview
    k = _kontakt(db_session)
    b = _beleg(auth_client, k.id)
    inv = db_session.query(Invoice).filter_by(id=b["id"]).first()
    s, i, sender, empf = _load_pdf_context(db_session, inv)
    s = {**s, "primary_color": "#fff;}body{background:url(http://127.0.0.1:9/farbe)}"}
    i = {**i, "custom_template_css": '.x{}</style><script>S02()</script>@import url("http://127.0.0.1:9/i.css");'}
    html = generate_html_preview(inv, inv.positions, s, i, sender, empf,
                                 template_id=vorlage, db=db_session)
    _ohne_verbotenes(html)
    assert "<b>Fett</b>" in html


def test_beleg_pdf_download_enthaelt_text_aber_keine_tags(auth_client, db_session, mitschnitt):
    k = _kontakt(db_session)
    b = _beleg(auth_client, k.id)
    resp = auth_client.get(f"/api/invoices/{b['id']}/pdf")
    assert resp.status_code == 200, resp.text
    assert len(mitschnitt) == 1
    _ohne_verbotenes(mitschnitt[0])
    pdf = pypdf.PdfReader(io.BytesIO(resp.content))
    text = "\n".join(s.extract_text() for s in pdf.pages)
    assert "Fett" in text and "<b>Fett" not in text        # Formatierung, keine sichtbaren Tags
    assert "Bauherr <b>GmbH</b>" in text                   # Name = gewöhnlicher Text, wörtlich
    assert "<b>Std</b>" in text                            # gewöhnlicher Text bleibt wörtlich
    assert "Überschrift" in text and "Ringstraße" in text  # Umlaute
    assert "s02-marker" not in "".join(pdf.attachments)    # kein eingeschleuster Anhang


def test_archivierung_und_email_anhang_nutzen_den_abgesicherten_weg(
        auth_client, db_session, mitschnitt, monkeypatch):
    from app.services import email_service, storage_service
    k = _kontakt(db_session)
    b = _beleg(auth_client, k.id)
    anhaenge = []
    monkeypatch.setattr(email_service, "send_email",
                        lambda settings=None, to_email=None, **kw: anhaenge.extend(kw.get("attachments") or []) or True)
    abgelegt = []
    monkeypatch.setattr(storage_service, "upload_file",
                        lambda key, daten, mime, **kw: abgelegt.append((key, daten)))

    resp = auth_client.post(f"/api/invoices/{b['id']}/send-email",
                            json={"to_email": "kunde@example.invalid"})
    assert resp.status_code == 200, resp.text
    # Versand (Anhang) und Archivierung (Auslöser „email") laufen beide über render_pdf
    assert len(mitschnitt) >= 2
    for html in mitschnitt:
        _ohne_verbotenes(html)
    assert anhaenge, "kein PDF-Anhang"
    assert any(d.startswith(b"%PDF-") for _, d in abgelegt), "keine Archivkopie"


# ── Positionsbilder: Referenzen ───────────────────────────────────────────────

@pytest.mark.parametrize("schluessel", [
    "datacenter/kontakte/vertrag.pdf",
    "belege/positionsbilder/../datacenter/x.jpg",
    "belege/positionsbilder/unter/ordner.jpg",
    "belege/positionsbilder/bild.svg",
    "belege/positionsbilder/bild.html",
    "/belege/positionsbilder/bild.jpg",
    "belege/positionsbilder/bild.jpg?x=1",
    "belege/positionsbilder/bild.png\n",
])
def test_fremde_bildreferenz_wird_beim_speichern_abgewiesen(auth_client, schluessel):
    resp = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung", "date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "x", "quantity": "1",
                       "unit_price": "1", "tax_rate": "20", "image_key": schluessel}]})
    assert resp.status_code == 422


def test_unbekannter_bildspeicher_wird_abgewiesen(auth_client):
    resp = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung", "date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "x", "quantity": "1",
                       "unit_price": "1", "tax_rate": "20",
                       "image_key": "belege/positionsbilder/abc.jpg", "image_provider": "file"}]})
    assert resp.status_code == 422


def test_bildvorschau_endpunkt_prueft_dieselbe_regel(auth_client):
    resp = auth_client.get("/api/invoices/positions/image",
                           params={"key": "belege/positionsbilder/../../datacenter/x.pdf"})
    assert resp.status_code == 400


def test_positionsbild_wird_nur_als_echtes_bild_eingebettet(monkeypatch):
    from app.services import position_image, storage_service
    inhalte = {
        "belege/positionsbilder/gut.png": PNG,
        "belege/positionsbilder/falsch.jpg": b"<html>S02-MARKER</html>",
    }
    monkeypatch.setattr(storage_service, "download_file",
                        lambda key, db=None, backend=None: (inhalte[key], "text/html"))
    url = position_image.als_datenurl(None, "belege/positionsbilder/gut.png")
    assert url.startswith("data:image/png;base64,")      # Typ aus Endung + Inhalt, nicht vom Speicher
    assert position_image.als_datenurl(None, "belege/positionsbilder/falsch.jpg") is None
    assert position_image.als_datenurl(None, "datacenter/x.png") is None


def test_hochladen_begrenzt_bildpunkte(monkeypatch):
    from fastapi import HTTPException
    from PIL import Image
    from app.services import position_image
    puffer = io.BytesIO()
    Image.new("1", (8000, 6000)).save(puffer, format="PNG")    # 48 MP, Datei winzig
    with pytest.raises(HTTPException) as e:
        position_image.verkleinern(puffer.getvalue(), "mittel")
    assert e.value.status_code == 400


def test_hochladen_begrenzt_hoehe():
    from fastapi import HTTPException
    from PIL import Image
    from app.services import position_image
    puffer = io.BytesIO()
    Image.new("RGB", (240, 4000)).save(puffer, format="PNG")
    with pytest.raises(HTTPException):
        position_image.verkleinern(puffer.getvalue(), "klein")


def test_erlaubtes_positionsbild_erscheint_im_pdf(auth_client, db_session, monkeypatch):
    """Positionsbilder bleiben erhalten: Bild über den regulären Upload, dann PDF."""
    from app.services import storage_service
    ablage = {}
    monkeypatch.setattr(storage_service, "upload_file",
                        lambda key, daten, mime, **kw: ablage.__setitem__(key, daten))
    monkeypatch.setattr(storage_service, "download_file",
                        lambda key, db=None, backend=None: (ablage[key], "image/jpeg"))
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (600, 300), (200, 30, 30)).save(puffer, format="JPEG")
    up = auth_client.post("/api/invoices/positions/image", params={"size": "mittel"},
                          files={"file": ("bild.jpg", puffer.getvalue(), "image/jpeg")})
    assert up.status_code == 200, up.text
    daten = up.json()
    b = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung", "date": "2026-07-06", "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "Mit Bild", "quantity": "1",
                       "unit_price": "1", "tax_rate": "20", "image_key": daten["image_key"],
                       "image_size": "mittel", "image_provider": daten["image_provider"]}]}).json()
    pdf = auth_client.get(f"/api/invoices/{b['id']}/pdf")
    assert pdf.status_code == 200
    bilder = [x for s in pypdf.PdfReader(io.BytesIO(pdf.content)).pages for x in s.images]
    assert len(bilder) == 1


# ── Weitere Dokumente ─────────────────────────────────────────────────────────

def test_mahnung_bereinigt_bezeichnung_und_text(auth_client, db_session, mitschnitt):
    from app.models.invoice import InvoiceDunning
    from app.services import dunning as dunning_service
    k = _kontakt(db_session)
    b = _beleg(auth_client, k.id)
    assert auth_client.post(f"/api/invoices/{b['id']}/set-status", json={"status": "offen"}).status_code == 200
    from app.models.invoice import InvoiceSettings
    stufen = dunning_service.get_levels(db_session)
    stufen[0]["text"] = BOESE                      # Mahntext = erlaubter Rich Text
    db_session.add(InvoiceSettings(key="dunning_levels", value=stufen))
    db_session.commit()
    e = auth_client.post(f"/api/invoices/{b['id']}/dunning", json={"dunned_at": "2026-08-20"})
    assert e.status_code == 200, e.text
    eintrag = db_session.query(InvoiceDunning).filter_by(id=e.json()["id"]).first()
    eintrag.label = "Erinnerung <img src=http://127.0.0.1:9/label>"
    db_session.commit()
    resp = auth_client.get(f"/api/invoices/dunning/{eintrag.id}/pdf")
    assert resp.status_code == 200, resp.text
    html = mitschnitt[-1]
    _ohne_verbotenes(html)
    assert "Erinnerung &lt;img" in html
    assert "<b>Fett</b>" in html


def test_projektzeitbericht_vorschau_und_pdf(auth_client, db_session, mitschnitt):
    from datetime import datetime, timedelta, timezone
    from app.core.zeitprojekte import ZEITPROJEKTE_SLUG
    typ = EntityType(name="Zeitprojekte", slug=ZEITPROJEKTE_SLUG)
    db_session.add(typ)
    db_session.flush()
    projekt = EntityRecord(entity_type_id=typ.id, data={"name": "P"}, display_name="P")
    db_session.add(projekt)
    db_session.commit()
    start = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)
    resp = auth_client.post("/api/zeiterfassung/entries", json={
        "project_id": str(projekt.id), "project_name": "Projekt <script>S02()</script>",
        "contact_name": 'Kunde <img src="http://127.0.0.1:9/k">',
        "note": "Notiz <link rel=attachment href=/tmp/s02-marker.txt>\nZeile 2",
        "started_at": start.isoformat(), "ended_at": (start + timedelta(hours=1)).isoformat(),
        "pause_minutes": 0, "billable": True, "data": {}})
    assert resp.status_code == 200, resp.text
    parameter = {"date_from": "2026-07-01", "date_to": "2026-07-31", "group_by": "aufgabe",
                 "project_name": "Projekt <script>S02()</script>"}
    vorschau = auth_client.get("/api/reports/zeiterfassung", params={**parameter, "format": "html"})
    assert vorschau.status_code == 200
    assert "sandbox" in vorschau.headers["content-security-policy"]
    _ohne_verbotenes(vorschau.text)
    assert "Notiz &lt;link" in vorschau.text and "<br>Zeile 2" in vorschau.text
    pdf = auth_client.get("/api/reports/zeiterfassung", params=parameter)
    assert pdf.status_code == 200
    _ohne_verbotenes(mitschnitt[-1])


def test_belegbuch_und_umsatzsteuer(auth_client, db_session, mitschnitt):
    from app.models.settings import Setting
    db_session.add(Setting(key="company_name", value="Firma <script>S02()</script>"))
    db_session.commit()
    b = _beleg(auth_client)
    auth_client.post(f"/api/invoices/{b['id']}/set-status", json={"status": "offen"})
    assert auth_client.get("/api/invoices/book/pdf").status_code == 200
    _ohne_verbotenes(mitschnitt[-1])
    assert "Sanierung &lt;img" in mitschnitt[-1]
    assert auth_client.get("/api/invoices/uva/pdf").status_code == 200
    _ohne_verbotenes(mitschnitt[-1])
    assert "Firma &lt;script&gt;" in mitschnitt[-1]


def test_aufgaben_laufzettel_farben_und_text(mitschnitt):
    from app.services.aufgaben_pdf import generate_todo_pdf
    pdf = generate_todo_pdf(
        {"id": "00000000-0000-0000-0000-000000000001", "title": "Aufgabe <script>S02()</script>",
         "status": "offen", "priority": "hoch", "description": "Text <img src=x>"},
        "https://example.invalid/aufgaben?id=1",
        [{"value": "offen", "label": "Offen", "color": "red;background:url(http://127.0.0.1:9/f)"}],
        [{"value": "hoch", "label": "<b>Hoch</b>", "color": "#ff0000"}],
        company_name="Firma <i>x</i>")
    assert pdf.startswith(b"%PDF-")
    _ohne_verbotenes(mitschnitt[-1])
    assert "background:#6b7280" in mitschnitt[-1].replace(" ", "")


def test_dsgvo_bescheinigung(mitschnitt):
    from datetime import datetime, timezone
    from app.services.gdpr_pdf import build_erasure_pdf
    pdf = build_erasure_pdf(
        variant="personal",
        report={"categories": {"todos": 1},
                "record": {"id": "x", "display_name": "Person <script>S02()</script>",
                           "data": {"adresse": '<img src="http://127.0.0.1:9/a">', "ort": "Wien"}},
                "retention": {}},
        log_id="<b>log</b>", executed_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
        executed_by="admin <i>x</i>", files_action="none", company_name="Firma <u>x</u>",
        company_lines=["Firma <u>x</u>", "Straße <script>1</script>"], note="Anmerkung <iframe>")
    assert pdf.startswith(b"%PDF-")
    _ohne_verbotenes(mitschnitt[-1])
    assert "Person &lt;script&gt;" in mitschnitt[-1]


def test_vorlagenvorschau_ist_abgeschottet(auth_client, db_session):
    from app.models.invoice import InvoiceSettings
    db_session.add(InvoiceSettings(key="custom_template_css",
                                   value='</style><script>S02()</script>'))
    db_session.commit()
    resp = auth_client.get("/api/invoices/template-preview/1")
    assert resp.status_code == 200
    assert "sandbox" in resp.headers["content-security-policy"]
    assert "<script" not in resp.text.lower()
