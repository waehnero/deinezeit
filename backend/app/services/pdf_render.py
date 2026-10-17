"""
Zentrale PDF-Erzeugung (S02) — einziger erlaubter Weg zu WeasyPrint
===================================================================

Alle Dokumente (Belege, Mahnungen, Projektzeitberichte, Belegbuch,
Umsatzsteuer-Aufstellung, Aufgaben-Laufzettel, DSGVO-Löschbescheinigungen)
rufen ``render_pdf(html)``. Ein direkter Aufruf von ``weasyprint.HTML`` / ``write_pdf``
im Anwendungscode ist nicht mehr zulässig — ``tests/test_pdf_render.py``
wacht darüber.

Warum ein eigener Prozess?
--------------------------
WeasyPrint löst Ressourcen (Bilder, Stylesheets, Schriften, PDF-Anhänge über
``<link rel="attachment">``) standardmäßig über ``http``, ``ftp`` und
``file`` auf. Mit ``base_url="/"`` reicht dafür schon ein relativer Pfad: Im
Test hat ein ``<link rel="attachment" href="/pfad/zur/markerdatei">`` aus
einem Feldinhalt die Datei als Anhang ins PDF übernommen. Neben der
Eingabebereinigung (``core/dokument_html.py``) verhindern das hier drei
voneinander unabhängige Ebenen:

1. **Ressourcenfilter** im Renderprozess: nur ``data:``-Bilder mit Größen-
   und Typprüfung, kein Rückfall auf den Standardabruf
   (``pdf_render_worker.ressource_holen``).
2. **Audit-Hook** im Renderprozess: kein Netz, keine Unterprozesse, Lesen nur
   aus Bibliotheks-/Schriftverzeichnissen.
3. **Prozessgrenzen**: eigener Prozess mit leerer Umgebung (keine
   Datenbank-, MinIO- oder Schlüsselwerte), als unprivilegierter Benutzer
   (``PDF_RENDER_UID``, Standard 65534/nobody, wenn das Backend als root
   läuft — damit sind z. B. die Let's-Encrypt-Schlüssel unter
   ``/etc/letsencrypt`` nicht lesbar), mit Speicher-, CPU-, Datei- und
   Wanduhr-Grenze. Beim Überschreiten wird die **ganze Prozessgruppe**
   beendet (SIGKILL) — die Renderarbeit hört tatsächlich auf, es wird nicht
   nur das Warten abgebrochen.

Parallelität
------------
Je Arbeitsprozess höchstens ``PDF_RENDER_PARALLEL`` gleichzeitige
Renderprozesse (Standard 2). Wer länger als ``PDF_RENDER_WARTEZEIT`` Sekunden
auf einen freien Platz wartet, bekommt ``PdfRenderUeberlastet`` (→ HTTP 503).
Bei ``UVICORN_WORKERS=n`` sind es also höchstens n × PDF_RENDER_PARALLEL.

Grenzen (Umgebungsvariablen, alle optional)
-------------------------------------------
=============================  ========  =====================================
PDF_RENDER_ZEITLIMIT           60        Sekunden Wanduhr je Dokument
PDF_RENDER_CPU_SEKUNDEN        60        CPU-Sekunden je Dokument
PDF_RENDER_MAX_SPEICHER_MB     1024      Adressraum des Renderprozesses
PDF_RENDER_MAX_EINGABE_MB      40        HTML inkl. eingebetteter Bilder
PDF_RENDER_MAX_AUSGABE_MB      50        fertiges PDF
PDF_RENDER_MAX_RESSOURCE_MB    8         einzelnes eingebettetes Bild
PDF_RENDER_PARALLEL            2         gleichzeitige Renderprozesse
PDF_RENDER_WARTEZEIT           30        Sekunden Warten auf freien Platz
PDF_RENDER_UID                 65534     Benutzer des Renderprozesses (nur als root)
=============================  ========  =====================================
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import signal
import subprocess  # nosec B404 — fester Befehl, keine Shell, keine Benutzereingabe im Aufruf
import sys
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_render_worker.py")


class PdfRenderFehler(RuntimeError):
    """Das PDF konnte nicht erzeugt werden."""


class PdfRenderZeitueberschreitung(PdfRenderFehler):
    """Zeit- oder CPU-Grenze überschritten; der Renderprozess wurde beendet."""


class PdfRenderZuGross(PdfRenderFehler):
    """Eingabe oder Ausgabe überschreitet die Größengrenze."""


class PdfRenderUeberlastet(PdfRenderFehler):
    """Zu viele gleichzeitige Renderaufträge."""


def _zahl(name: str, vorgabe: float) -> float:
    try:
        wert = float(os.environ.get(name, vorgabe))
        return wert if wert > 0 else vorgabe
    except (TypeError, ValueError):
        return vorgabe


def grenzen() -> dict:
    """Aktuelle Grenzen (bei jedem Aufruf gelesen — in Tests umstellbar)."""
    mb = 1024 * 1024
    return {
        "zeitlimit": _zahl("PDF_RENDER_ZEITLIMIT", 60),
        "cpu_sekunden": int(_zahl("PDF_RENDER_CPU_SEKUNDEN", 60)),
        "max_speicher": int(_zahl("PDF_RENDER_MAX_SPEICHER_MB", 1024) * mb),
        "max_eingabe": int(_zahl("PDF_RENDER_MAX_EINGABE_MB", 40) * mb),
        "max_ausgabe": int(_zahl("PDF_RENDER_MAX_AUSGABE_MB", 50) * mb),
        "max_ressource": int(_zahl("PDF_RENDER_MAX_RESSOURCE_MB", 8) * mb),
        "parallel": int(_zahl("PDF_RENDER_PARALLEL", 2)),
        "wartezeit": _zahl("PDF_RENDER_WARTEZEIT", 30),
        "uid": int(_zahl("PDF_RENDER_UID", 65534)),
    }


# ── Parallelitätsgrenze ──────────────────────────────────────────────────────

_sperre = threading.Lock()
_belegt = 0
_frei = threading.Condition(_sperre)
#: Höchststand gleichzeitiger Renderprozesse (für Tests/Diagnose)
hoechststand = 0


def _platz_belegen(parallel: int, wartezeit: float) -> None:
    global _belegt, hoechststand
    ende = time.monotonic() + wartezeit
    with _frei:
        while _belegt >= parallel:
            rest = ende - time.monotonic()
            if rest <= 0:
                raise PdfRenderUeberlastet(
                    "Zu viele PDFs gleichzeitig in Arbeit — bitte gleich noch einmal versuchen.")
            _frei.wait(rest)
        _belegt += 1
        hoechststand = max(hoechststand, _belegt)


def _platz_freigeben() -> None:
    global _belegt
    with _frei:
        _belegt -= 1
        _frei.notify()


# ── Prozessstart ─────────────────────────────────────────────────────────────

def _umgebung(arbeitsverzeichnis: str) -> dict:
    """Leere Umgebung — bewusst ohne DATABASE_URL, SECRET_KEY, MINIO_* usw."""
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": arbeitsverzeichnis,
        "TMPDIR": arbeitsverzeichnis,
        "XDG_CACHE_HOME": arbeitsverzeichnis,
        "FONTCONFIG_CACHE": arbeitsverzeichnis,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def render_pdf(html: str, *, pdf_variant: str | None = None,
               erechnung: dict | None = None) -> bytes:
    """Erzeugt aus ``html`` ein PDF im abgeschotteten Renderprozess.

    ``erechnung``: ``{"xml": bytes, "dateiname": str, "titel": str, "autor": str}``
    für einen hybriden Beleg (PDF/A-3 mit eingebettetem XML).

    Wirft ``PdfRenderFehler`` (bzw. eine Unterklasse).
    """
    g = grenzen()
    if not isinstance(html, str):
        raise PdfRenderFehler("HTML muss als Text übergeben werden")
    auftrag = {
        "html": html,
        "pdf_variant": pdf_variant,
        "grenzen": {
            "max_ressource_bytes": g["max_ressource"],
            "max_ressourcen_gesamt": g["max_eingabe"],
            "max_ausgabe_bytes": g["max_ausgabe"],
        },
    }
    if erechnung:
        auftrag["erechnung"] = {
            "xml_b64": base64.b64encode(erechnung["xml"]).decode("ascii"),
            "dateiname": erechnung["dateiname"],
            "titel": erechnung.get("titel", ""),
            "autor": erechnung.get("autor", ""),
        }
    eingabe = json.dumps(auftrag).encode("utf-8")
    if len(eingabe) > g["max_eingabe"]:
        raise PdfRenderZuGross("Das Dokument ist zu groß für die PDF-Erzeugung.")

    _platz_belegen(g["parallel"], g["wartezeit"])
    arbeitsverzeichnis = None
    prozess = None
    try:
        # Innerhalb des try: Scheitert schon das Anlegen (z. B. Platte voll),
        # muss der belegte Platz trotzdem zurückgegeben werden.
        arbeitsverzeichnis = tempfile.mkdtemp(prefix="dz-pdf-")
        uid = g["uid"] if os.geteuid() == 0 else None
        if uid is not None:
            os.chown(arbeitsverzeichnis, uid, uid)
        os.chmod(arbeitsverzeichnis, 0o700)
        # Kein preexec_fn (nicht thread-sicher unter uvicorn): Rechte gibt
        # Popen selbst ab, eigene Prozessgruppe über process_group, die
        # rlimits setzt der Renderprozess als Allererstes selbst.
        rechte = {"user": uid, "group": uid, "extra_groups": []} if uid is not None else {}
        prozess = subprocess.Popen(  # nosec B603 — feste Argumentliste, kein Shell
            [sys.executable, "-I", WORKER,
             str(g["max_speicher"]), str(g["cpu_sekunden"])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=arbeitsverzeichnis, env=_umgebung(arbeitsverzeichnis),
            close_fds=True, process_group=0, **rechte,
        )
        try:
            ausgabe, fehler = prozess.communicate(eingabe, timeout=g["zeitlimit"])
        except subprocess.TimeoutExpired as e:
            _beenden(prozess)
            raise PdfRenderZeitueberschreitung(
                "Die PDF-Erzeugung hat das Zeitlimit überschritten und wurde abgebrochen.") from e
        meldung = (fehler or b"").decode("utf-8", "replace").strip()
        if prozess.returncode != 0:
            # Negative Codes = Signal (SIGXCPU bei CPU-Grenze, SIGKILL …)
            if prozess.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
                raise PdfRenderZeitueberschreitung(
                    "Die PDF-Erzeugung hat das Zeitlimit überschritten und wurde abgebrochen.")
            if prozess.returncode == 3:
                raise PdfRenderZuGross("Das erzeugte PDF überschreitet die Größengrenze.")
            logger.warning("PDF-Renderprozess endete mit Code %s: %s",
                           prozess.returncode, meldung[-500:])
            raise PdfRenderFehler("Das PDF konnte nicht erzeugt werden.")
        if meldung:
            logger.info("PDF-Renderprozess: %s", meldung[-500:])
        if len(ausgabe) > g["max_ausgabe"]:
            raise PdfRenderZuGross("Das erzeugte PDF überschreitet die Größengrenze.")
        if not ausgabe.startswith(b"%PDF-"):
            raise PdfRenderFehler("Der Renderprozess lieferte kein PDF.")
        return ausgabe
    finally:
        if prozess is not None and prozess.poll() is None:
            _beenden(prozess)
        if arbeitsverzeichnis:
            shutil.rmtree(arbeitsverzeichnis, ignore_errors=True)
        _platz_freigeben()


def _beenden(prozess: subprocess.Popen) -> None:
    """Beendet den Renderprozess samt allem, was er gestartet hat."""
    try:
        os.killpg(prozess.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            prozess.kill()
        except ProcessLookupError:
            pass
    try:
        prozess.communicate(timeout=5)
    except Exception:                       # noqa: BLE001 — Aufräumen, nicht mehr retten
        logger.warning("PDF-Renderprozess %s ließ sich nicht abräumen", prozess.pid,
                       exc_info=True)
