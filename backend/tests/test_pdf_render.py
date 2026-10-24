"""
S02 — abgeschotteter PDF-Renderer (``services/pdf_render.py``).

Geprüft wird mit dem **echten** WeasyPrint im echten Renderprozess, nicht mit
Mocks: Ressourcenfilter, Audit-Hook, Prozessgrenzen, Abbruch und Aufräumen.
Für Dateizugriffe gibt es ausschließlich eigens angelegte Markerdateien, für
Netzwerkzugriffe einen lokalen Zähl-Server auf 127.0.0.1 — keine echten
Dateien, keine externen Dienste.

Die Markerdateien sind bewusst für alle lesbar (0644): Sonst würde schon der
Benutzerwechsel des Renderprozesses den Zugriff verhindern, und der Test
sagte nichts über den Ressourcenfilter.

Prüfungen auf das PDF lesen es mit pypdf (Anhänge, Text) — nie über
Zeichenfolgen im Rohtext (siehe Merkzettel „Tests gegen Binärformate").
"""
import base64
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

import pypdf
import pytest

from app.services import pdf_render
from app.services.pdf_render_worker import RessourceGesperrt, ressource_holen

MARKER = "S02-MARKER-7f3a"
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


# ── Hilfen ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def oeffentlich_dir():
    """Verzeichnis, das auch der unprivilegierte Renderbenutzer lesen kann."""
    pfad = tempfile.mkdtemp(prefix="s02-test-")
    os.chmod(pfad, 0o755)
    yield pfad
    shutil.rmtree(pfad, ignore_errors=True)


@pytest.fixture()
def marker(oeffentlich_dir):
    pfad = os.path.join(oeffentlich_dir, "marker.txt")
    with open(pfad, "w") as f:
        f.write(MARKER)
    os.chmod(pfad, 0o644)
    return pfad


@pytest.fixture()
def zaehl_server():
    """HTTP-Server auf 127.0.0.1, der jede Anfrage zählt (und umleitet)."""
    treffer = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):              # noqa: N802
            treffer.append(self.path)
            if self.path.startswith("/umleitung"):
                self.send_response(302)
                self.send_header("Location", "file:///etc/hostname")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(PNG_1x1)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", treffer
    server.shutdown()


def _pdf(daten: bytes) -> pypdf.PdfReader:
    assert daten.startswith(b"%PDF-")
    return pypdf.PdfReader(io.BytesIO(daten))


def _anhaenge(daten: bytes) -> dict:
    return {name: [bytes(x) for x in inhalte]
            for name, inhalte in _pdf(daten).attachments.items()}


def _text(daten: bytes) -> str:
    return "\n".join(seite.extract_text() for seite in _pdf(daten).pages)


def _worker_prozesse() -> list:
    """PIDs laufender Renderprozesse (über /proc)."""
    gefunden = []
    for eintrag in os.listdir("/proc"):
        if not eintrag.isdigit():
            continue
        try:
            with open(f"/proc/{eintrag}/cmdline", "rb") as f:
                if b"pdf_render_worker.py" in f.read():
                    gefunden.append(int(eintrag))
        except OSError:
            continue
    return gefunden


def _sonde(oeffentlich_dir, code: str) -> str:
    """Ersatz-Worker für Tests des Prozessrahmens (Rechte, Umgebung, Abbruch)."""
    pfad = os.path.join(oeffentlich_dir, "sonde.py")
    with open(pfad, "w") as f:
        f.write(textwrap.dedent(code))
    os.chmod(pfad, 0o644)
    return pfad


# ── Ressourcenfilter (reine Funktion) ─────────────────────────────────────────

def _png_url(daten=PNG_1x1, typ="image/png"):
    return f"data:{typ};base64,{base64.b64encode(daten).decode()}"


def test_filter_laesst_eingebettetes_bild_durch():
    daten, typ = ressource_holen(_png_url(), 1024 * 1024)
    assert daten == PNG_1x1 and typ == "image/png"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x.png",
    "https://example.invalid/x.png",
    "HTTP://127.0.0.1/x.png",
    "ftp://127.0.0.1/x.png",
    "file:///etc/hostname",
    "FILE:///etc/hostname",
    "file://localhost/etc/hostname",
    "/etc/hostname",
    "../../etc/hostname",
    "marker.txt",
    "%66ile:///etc/hostname",
    "javascript:alert(1)",
    "about:blank",
    "data:text/html;base64,PHNjcmlwdD4=",
    "data:application/pdf;base64,JVBERi0=",
    "data:text/plain,S02",
])
def test_filter_sperrt_alles_ausser_bild_daten(url):
    with pytest.raises(RessourceGesperrt):
        ressource_holen(url, 1024 * 1024)


def test_filter_prueft_inhalt_gegen_bildtyp():
    with pytest.raises(RessourceGesperrt):
        ressource_holen(_png_url(b"<svg></svg>", "image/png"), 1024)
    with pytest.raises(RessourceGesperrt):
        ressource_holen(_png_url(b"GIF89a", "image/jpeg"), 1024)


def test_filter_begrenzt_groesse():
    gross = PNG_1x1 + b"\0" * 5000
    with pytest.raises(RessourceGesperrt):
        ressource_holen(_png_url(gross), 1000)


@pytest.mark.parametrize("deklaration", [
    b'<!ENTITY ext SYSTEM "file:///etc/hostname">',
    b'<!ENTITY % ext SYSTEM "http://127.0.0.1:9/x.dtd">',
    b'<!ENTITY ext PUBLIC "-//X//EN" "file:///etc/hostname">',
])
def test_filter_lehnt_svg_mit_externer_entitaet_ab(deklaration):
    svg = (b'<?xml version="1.0"?><!DOCTYPE svg [' + deklaration + b']>'
           b'<svg xmlns="http://www.w3.org/2000/svg">&ext;</svg>')
    with pytest.raises(RessourceGesperrt):
        ressource_holen(_png_url(svg, "image/svg+xml"), 1024 * 1024)


ILLUSTRATOR_SVG = (
    b'<?xml version="1.0" encoding="utf-8"?>\n'
    b'<!-- Generator: Adobe Illustrator 27.0.0, SVG Export Plug-In -->\n'
    b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd" [\n'
    b'  <!ENTITY ns_svg "http://www.w3.org/2000/svg">\n'
    b'  <!ENTITY ns_xlink "http://www.w3.org/1999/xlink">\n]>\n'
    b'<svg version="1.1" xmlns="&ns_svg;" xmlns:xlink="&ns_xlink;" width="120" height="40" viewBox="0 0 120 40">'
    b'<rect width="120" height="40" fill="#ef7d00"/></svg>')


def test_illustrator_svg_logo_bleibt_erlaubt():
    """Regression aus dem Review: DOCTYPE + interne Entitäten sind bei Logos üblich."""
    daten, typ = ressource_holen(_png_url(ILLUSTRATOR_SVG, "image/svg+xml"), 1024 * 1024)
    assert typ == "image/svg+xml"
    html = f'<html><body><img src="{_png_url(ILLUSTRATOR_SVG, "image/svg+xml")}" style="width:40mm"></body></html>'
    pdf = pdf_render.render_pdf(html)
    # Vektorgrafik → kein Rasterbild; geprüft wird, dass die Seite Zeichenbefehle
    # in der Logofarbe enthält (entpackter Inhaltsstrom, kein Rohtext-Vergleich)
    inhalt = _pdf(pdf).pages[0].get_contents().get_data()
    assert b"0.937255 0.490196 0 rg" in inhalt or b"0.937255 0.490196 0.0 rg" in inhalt


def test_svg_entitaetsflut_bleibt_in_den_grenzen():
    """Milliarden-Lacher: expat bricht ab bzw. die Prozessgrenzen greifen — kein Hängen."""
    stufen = b'<!ENTITY a0 "lol">' + b"".join(
        b'<!ENTITY a%d "' % i + (b"&a%d;" % (i - 1)) * 10 + b'">' for i in range(1, 10))
    svg = (b'<?xml version="1.0"?><!DOCTYPE svg [' + stufen + b']>'
           b'<svg xmlns="http://www.w3.org/2000/svg"><text>&a9;</text></svg>')
    start = time.monotonic()
    try:
        pdf_render.render_pdf(f'<img src="{_png_url(svg, "image/svg+xml")}">')
    except pdf_render.PdfRenderFehler:
        pass
    assert time.monotonic() - start < 30


# ── Echter Renderer: Datei-, Netz-, CSS- und SVG-Wege ─────────────────────────

def test_relativer_und_file_anhang_wird_nicht_eingebettet(marker):
    """
    Der ursprüngliche Befund: ``<link rel="attachment">`` mit relativem Pfad
    bettete bei ``base_url="/"`` die Datei als PDF-Anhang ein. Jetzt weder
    relativ noch per ``file://``, auch nicht prozentkodiert.
    """
    kodiert = marker.replace("/", "%2F")
    html = f"""<html><body><p>Inhalt</p>
      <link rel="attachment" href="{marker}">
      <link rel="attachment" href="file://{marker}">
      <a rel="attachment" href="file://{marker}">x</a>
      <link rel="attachment" href="file:{kodiert}">
      <img src="file://{marker}"><img src="{marker}">
    </body></html>"""
    pdf = pdf_render.render_pdf(html)
    assert _anhaenge(pdf) == {}
    assert MARKER not in _text(pdf)

    # Gegenprobe: Der frühere Aufruf (WeasyPrint direkt, base_url="/") hätte
    # die Markerdatei eingebettet — der Test erkennt den Befund also.
    from weasyprint import HTML
    alt = HTML(string=html, base_url="/").write_pdf()
    assert any(MARKER.encode() in b"".join(v) for v in _anhaenge(alt).values())


def test_netzwerk_css_und_svg_ressourcen_werden_nicht_abgerufen(zaehl_server, marker):
    basis, treffer = zaehl_server
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'xmlns:xlink="http://www.w3.org/1999/xlink" width="10" height="10">'
           f'<image href="{basis}/svg-bild.png" width="10" height="10"/>'
           f'<image xlink:href="file://{marker}" width="10" height="10"/>'
           f'<use href="{basis}/svg-use.svg#a"/>'
           f'<style>@import url({basis}/svg-css.css);</style></svg>')
    svg_url = _png_url(svg.encode(), "image/svg+xml")
    html = f"""<html><head>
      <link rel="stylesheet" href="{basis}/stil.css">
      <style>
        @import url("{basis}/import.css");
        @font-face {{ font-family: X; src: url({basis}/schrift.woff); }}
        body {{ background: url({basis}/hintergrund.png); font-family: X; }}
        p {{ background-image: url("{basis}/umleitung"); }}
        div {{ background: url(file://{marker}); }}
      </style></head><body>
      <p>Text</p><div>x</div>
      <img src="{basis}/bild.png"><img src="{basis}/umleitung">
      <object data="{basis}/objekt"></object><embed src="{basis}/embed">
      <iframe src="{basis}/rahmen"></iframe>
      <img src="{svg_url}">
      <link rel="attachment" href="{basis}/anhang.txt">
    </body></html>"""
    pdf = pdf_render.render_pdf(html)
    assert treffer == [], f"Renderer hat Netzwerkressourcen abgerufen: {treffer}"
    assert _anhaenge(pdf) == {}

    # Gegenprobe: WeasyPrint mit Standard-Abruf erreicht den Zähl-Server —
    # der Server funktioniert, das Ausbleiben oben ist also echt.
    from weasyprint import HTML
    HTML(string=f'<img src="{basis}/gegenprobe.png">').write_pdf()
    assert "/gegenprobe.png" in treffer


def test_erlaubtes_eingebettetes_bild_wird_gerendert():
    html = f'<html><body><p>Mit Bild</p><img src="{_png_url()}" style="width:20mm"></body></html>'
    pdf = _pdf(pdf_render.render_pdf(html))
    bilder = [b for s in pdf.pages for b in s.images]
    assert len(bilder) == 1


def test_umlaute_und_seitenumbrueche_bleiben():
    html = ("<html><head><meta charset='utf-8'></head><body>"
            "<p>Grüße aus Lengau – Maß, Öl, Übergröße</p>"
            "<p style='page-break-before: always'>Seite zwei</p></body></html>")
    pdf = pdf_render.render_pdf(html)
    assert len(_pdf(pdf).pages) == 2
    text = _text(pdf)
    assert "Grüße aus Lengau – Maß, Öl, Übergröße" in text
    assert "Seite zwei" in text


# ── Audit-Hook im Renderprozess ───────────────────────────────────────────────

def test_audit_hook_sperrt_datei_netz_und_unterprozesse(oeffentlich_dir, marker):
    """
    Zweite, vom Filter unabhängige Ebene: Selbst wenn eine Bibliothek am
    ``url_fetcher`` vorbei liest, verweigert der Prozess Datei, Netz und
    Unterprozess.
    """
    schreib = tempfile.mkdtemp(prefix="s02-schreib-")
    worker = pdf_render.WORKER
    code = f"""
import importlib.util, json, os, socket, subprocess, sys
spec = importlib.util.spec_from_file_location("w", {worker!r})
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
w.sperren_einrichten({schreib!r})
erg = {{}}
def versuch(name, f):
    try:
        f(); erg[name] = "erlaubt"
    except PermissionError:
        erg[name] = "gesperrt"
    except Exception as e:
        erg[name] = "fehler:" + type(e).__name__
versuch("marker_lesen", lambda: open({marker!r}).read())
versuch("os_open", lambda: os.open({marker!r}, os.O_RDONLY))
versuch("etc_lesen", lambda: open("/etc/hostname").read())
versuch("proc_environ", lambda: open("/proc/self/environ", "rb").read())
versuch("schreiben_aussen", lambda: open({os.path.join(oeffentlich_dir, "neu.txt")!r}, "w"))
versuch("schreiben_innen", lambda: open(os.path.join({schreib!r}, "ok.txt"), "w").close())
versuch("verbinden", lambda: socket.create_connection(("127.0.0.1", 9), timeout=1))
versuch("namensaufloesung", lambda: socket.getaddrinfo("localhost", 80))
versuch("unterprozess", lambda: subprocess.run(["true"]))
versuch("os_system", lambda: os.system("true"))
versuch("bibliothek_lesen", lambda: open(os.__file__).read(10))
versuch("bibliothek_auflisten", lambda: os.listdir(os.path.dirname(os.__file__)))
versuch("auflisten_aussen", lambda: os.listdir({oeffentlich_dir!r}))
versuch("kuerzen", lambda: os.truncate({marker!r}, 0))
versuch("verzeichnis_anlegen", lambda: os.mkdir({os.path.join(oeffentlich_dir, "neu")!r}))
versuch("sqlite", lambda: __import__("sqlite3").connect({os.path.join(oeffentlich_dir, "x.db")!r}))
versuch("signal", lambda: os.kill(os.getppid(), 0))
print(json.dumps(erg))
"""
    try:
        aus = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True,
                             text=True, timeout=60, env={"PATH": "/usr/bin:/bin"})
        erg = json.loads(aus.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(schreib, ignore_errors=True)
    assert erg["bibliothek_lesen"] == "erlaubt"
    assert erg["bibliothek_auflisten"] == "erlaubt"
    assert erg["schreiben_innen"] == "erlaubt"
    for name in ("marker_lesen", "os_open", "etc_lesen", "proc_environ", "schreiben_aussen",
                 "verbinden", "namensaufloesung", "unterprozess", "os_system",
                 "auflisten_aussen", "kuerzen", "verzeichnis_anlegen", "sqlite", "signal"):
        assert erg[name] == "gesperrt", (name, erg)


# ── Prozessrahmen: Rechte, Umgebung, Grenzen ──────────────────────────────────

def test_renderprozess_bekommt_keine_zugangsdaten(oeffentlich_dir, monkeypatch):
    sonde = _sonde(oeffentlich_dir, """
        import json, os, sys
        sys.stdout.write("%PDF-" + json.dumps({"uid": os.getuid(), "euid": os.geteuid(),
                                               "env": sorted(os.environ)}))
    """)
    monkeypatch.setattr(pdf_render, "WORKER", sonde)
    monkeypatch.setenv("SECRET_KEY", "s02-test-geheim")
    monkeypatch.setenv("DATABASE_URL", "postgresql://s02:test@localhost/x")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "s02-test")
    info = json.loads(pdf_render.render_pdf("<p>x</p>")[5:])
    for geheim in ("SECRET_KEY", "DATABASE_URL", "MINIO_ROOT_PASSWORD", "MINIO_ROOT_USER",
                   "SETUP_TOKEN", "BACKUP_PING_TOKEN", "TEST_DATABASE_URL"):
        assert geheim not in info["env"]
    if os.geteuid() == 0:
        # Backend als root (wie im Container) → Renderprozess nicht als root
        assert info["uid"] != 0 and info["euid"] != 0


@pytest.mark.skipif(os.geteuid() != 0, reason="Benutzerwechsel nur prüfbar, wenn die Tests als root laufen")
def test_renderprozess_kann_root_dateien_nicht_lesen(oeffentlich_dir, monkeypatch):
    """Ersatz für /etc/letsencrypt: eine nur für root lesbare Markerdatei."""
    geheim = os.path.join(oeffentlich_dir, "nur-root.txt")
    with open(geheim, "w") as f:
        f.write(MARKER)
    os.chmod(geheim, 0o600)
    sonde = _sonde(oeffentlich_dir, f"""
        import sys
        try:
            open({geheim!r}).read(); erg = "gelesen"
        except PermissionError:
            erg = "verweigert"
        sys.stdout.write("%PDF-" + erg)
    """)
    monkeypatch.setattr(pdf_render, "WORKER", sonde)
    assert pdf_render.render_pdf("<p>x</p>") == b"%PDF-verweigert"


def test_zeitlimit_beendet_den_echten_renderer(monkeypatch):
    """Ein großes Dokument mit 1 s Zeitlimit: der Prozess wird beendet, nicht nur verlassen."""
    monkeypatch.setenv("PDF_RENDER_ZEITLIMIT", "1")
    zeilen = "".join(f"<tr><td>Zeile {i}</td><td>{'x' * 40}</td></tr>" for i in range(30000))
    vorher = set(_worker_prozesse())
    temp_vorher = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("dz-pdf-")}
    start = time.monotonic()
    with pytest.raises(pdf_render.PdfRenderZeitueberschreitung):
        pdf_render.render_pdf(f"<table>{zeilen}</table>")
    assert time.monotonic() - start < 15
    time.sleep(0.2)
    assert set(_worker_prozesse()) - vorher == set(), "Renderprozess läuft nach dem Abbruch weiter"
    temp_nachher = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("dz-pdf-")}
    assert temp_nachher - temp_vorher == set(), "Arbeitsverzeichnis wurde nicht aufgeräumt"


def test_cpu_grenze_beendet_den_echten_renderer(monkeypatch):
    monkeypatch.setenv("PDF_RENDER_ZEITLIMIT", "60")
    monkeypatch.setenv("PDF_RENDER_CPU_SEKUNDEN", "1")
    zeilen = "".join(f"<tr><td>Zeile {i}</td><td>{'x' * 40}</td></tr>" for i in range(30000))
    with pytest.raises(pdf_render.PdfRenderZeitueberschreitung):
        pdf_render.render_pdf(f"<table>{zeilen}</table>")


def test_speichergrenze_greift(monkeypatch):
    """Mit 64 MB Adressraum kann der Renderprozess nicht arbeiten → Fehler, kein Hängen."""
    monkeypatch.setenv("PDF_RENDER_MAX_SPEICHER_MB", "64")
    with pytest.raises(pdf_render.PdfRenderFehler):
        pdf_render.render_pdf("<p>x</p>")


def test_fehler_beim_anlegen_gibt_den_platz_zurueck(monkeypatch):
    """Review-Befund: Scheitert mkdtemp (Platte voll), darf kein Platz verloren gehen."""
    monkeypatch.setenv("PDF_RENDER_PARALLEL", "1")
    monkeypatch.setenv("PDF_RENDER_WARTEZEIT", "0.5")
    echt = tempfile.mkdtemp

    def _voll(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(pdf_render.tempfile, "mkdtemp", _voll)
    for _ in range(3):
        with pytest.raises(OSError):
            pdf_render.render_pdf("<p>x</p>")
    monkeypatch.setattr(pdf_render.tempfile, "mkdtemp", echt)
    assert pdf_render.render_pdf("<p>wieder da</p>").startswith(b"%PDF-")


def test_eingabegrenze_greift_vor_dem_prozessstart(monkeypatch):
    monkeypatch.setenv("PDF_RENDER_MAX_EINGABE_MB", "0.001")
    vorher = set(_worker_prozesse())
    with pytest.raises(pdf_render.PdfRenderZuGross):
        pdf_render.render_pdf("<p>" + "x" * 5000 + "</p>")
    assert set(_worker_prozesse()) - vorher == set()


def test_ausgabegrenze_greift(monkeypatch):
    monkeypatch.setenv("PDF_RENDER_MAX_AUSGABE_MB", "0.002")      # ~2 KB
    seiten = "".join(f"<p style='page-break-after:always'>Seite {i}</p>" for i in range(30))
    with pytest.raises(pdf_render.PdfRenderZuGross):
        pdf_render.render_pdf(seiten)


def test_parallelitaet_bleibt_in_der_grenze(oeffentlich_dir, monkeypatch):
    sonde = _sonde(oeffentlich_dir, """
        import sys, time
        sys.stdin.buffer.read(); time.sleep(0.4); sys.stdout.write("%PDF-ok")
    """)
    monkeypatch.setattr(pdf_render, "WORKER", sonde)
    monkeypatch.setenv("PDF_RENDER_PARALLEL", "2")
    monkeypatch.setattr(pdf_render, "hoechststand", 0)
    fehler = []

    def auftrag():
        try:
            pdf_render.render_pdf("<p>x</p>")
        except Exception as e:          # noqa: BLE001
            fehler.append(e)

    start = time.monotonic()
    faeden = [threading.Thread(target=auftrag) for _ in range(6)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(30)
    assert fehler == []
    assert pdf_render.hoechststand == 2
    assert time.monotonic() - start >= 1.1          # 6 Aufträge / 2 Plätze × 0,4 s


def test_ueberlastung_wird_abgewiesen(oeffentlich_dir, monkeypatch):
    sonde = _sonde(oeffentlich_dir, """
        import sys, time
        sys.stdin.buffer.read(); time.sleep(1.5); sys.stdout.write("%PDF-ok")
    """)
    monkeypatch.setattr(pdf_render, "WORKER", sonde)
    monkeypatch.setenv("PDF_RENDER_PARALLEL", "1")
    monkeypatch.setenv("PDF_RENDER_WARTEZEIT", "0.3")
    ergebnisse = []
    faeden = [threading.Thread(target=lambda: ergebnisse.append(_versuch())) for _ in range(2)]

    def _versuch():
        try:
            return pdf_render.render_pdf("<p>x</p>")
        except pdf_render.PdfRenderUeberlastet:
            return "ueberlastet"

    for f in faeden:
        f.start()
    for f in faeden:
        f.join(30)
    assert sorted(map(str, ergebnisse)) == sorted(["b'%PDF-ok'", "ueberlastet"])


def test_ueberlastung_wird_als_503_beantwortet(auth_client, monkeypatch):
    from app.services import invoice_pdf

    def _voll(*a, **k):
        raise pdf_render.PdfRenderUeberlastet("Zu viele PDFs gleichzeitig in Arbeit")
    monkeypatch.setattr(invoice_pdf, "render_pdf", _voll)
    beleg = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung", "date": "2026-07-06", "delivery_date": "2026-07-06",
        "positions": [{"pos_type": "item", "description": "x", "quantity": "1",
                       "unit_price": "1", "tax_rate": "20"}]}).json()
    resp = auth_client.get(f"/api/invoices/{beleg['id']}/pdf")
    assert resp.status_code == 503


# ── Wächter: kein Weg an render_pdf vorbei ───────────────────────────────────

def test_kein_direkter_weasyprint_aufruf_im_anwendungscode():
    wurzel = os.path.join(os.path.dirname(__file__), "..", "app")
    erlaubt = {os.path.normpath(os.path.join(wurzel, "services", "pdf_render_worker.py"))}
    funde = []
    for ordner, _, dateien in os.walk(wurzel):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            pfad = os.path.normpath(os.path.join(ordner, name))
            if pfad in erlaubt:
                continue
            with open(pfad, encoding="utf-8") as f:
                for nr, zeile in enumerate(f, 1):
                    code = zeile.split("#", 1)[0]
                    if ("import weasyprint" in code or "from weasyprint" in code
                            or ".write_pdf(" in code):
                        funde.append(f"{pfad}:{nr}: {zeile.strip()}")
    assert funde == [], "PDF nur über services.pdf_render.render_pdf erzeugen:\n" + "\n".join(funde)
