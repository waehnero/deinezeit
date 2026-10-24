"""
PDF-Renderprozess (S02) — läuft als eigener, kurzlebiger Prozess
================================================================

Wird ausschließlich von ``services/pdf_render.py`` gestartet:

    python -I <diese Datei>   (stdin: JSON-Auftrag, stdout: PDF-Bytes)

und ist bewusst **eigenständig**: kein Import aus ``app.core``/Einstellungen,
keine Datenbank, keine Zugangsdaten. Der Elternprozess startet ihn mit leerer
Umgebung, als unprivilegierter Benutzer (wenn das Backend als root läuft) und
mit harten Ressourcengrenzen (Speicher, CPU, Dateien).

Innerhalb des Prozesses gelten zwei voneinander unabhängige Sperren:

1. **Ressourcenfilter** (``ressource_holen``) als ``url_fetcher`` für
   WeasyPrint: Aufgelöst werden ausschließlich ``data:``-URIs mit erlaubtem
   Bildtyp und begrenzter Größe. ``http(s)``, ``ftp``, ``file``, relative Pfade
   und alles andere werden abgewiesen. Der Filter baut auf keinem urllib-
   Opener auf — es gibt also keinen Standardabruf, auf den ein Fehler
   zurückfallen könnte.

2. **Audit-Hook** (``sys.addaudithook``, nicht wieder entfernbar): Nach dem
   Laden der Bibliotheken sind Netzwerkverbindungen, Namensauflösung,
   Unterprozesse und das Öffnen von Dateien außerhalb der Bibliotheks- und
   Schriftverzeichnisse gesperrt. Greift auch dann, wenn ein künftiger
   WeasyPrint-Pfad am ``url_fetcher`` vorbei liest.

Exit-Codes: 0 = PDF auf stdout, 2 = ungültiger Auftrag, 3 = Ausgabe zu groß,
4 = Renderfehler, 5 = läuft als root. Fehlermeldungen gehen nach stderr (ohne Dokumentinhalt).
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
import sys
import urllib.parse

# ── Ressourcenfilter ─────────────────────────────────────────────────────────

ERLAUBTE_BILDTYPEN = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
    "image/svg+xml": None,            # Text; Prüfung siehe unten
}


_EXTERNE_ENTITAET = re.compile(rb"<!ENTITY\s+(?:%\s*)?[^\s>]+\s+(?:SYSTEM|PUBLIC)\b", re.I)


class RessourceGesperrt(ValueError):
    """Eine Ressource wurde vom Filter abgewiesen."""


def ressource_holen(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Löst eine ``data:``-URI auf und gibt ``(daten, mime)`` zurück.

    Alles andere wirft ``RessourceGesperrt``. Reine Funktion ohne WeasyPrint —
    damit direkt testbar.
    """
    if not isinstance(url, str):
        raise RessourceGesperrt("Ungültige Ressourcenangabe")
    if not url[:5].lower() == "data:":
        schema = url.split(":", 1)[0][:20] if ":" in url else "(relativ)"
        raise RessourceGesperrt(f"Ressource gesperrt (Schema {schema!r})")
    kopf, trenner, nutzlast = url[5:].partition(",")
    if not trenner:
        raise RessourceGesperrt("Ungültige data:-URI")
    teile = [t.strip().lower() for t in kopf.split(";")]
    mime = teile[0] or "text/plain"
    if mime not in ERLAUBTE_BILDTYPEN:
        raise RessourceGesperrt(f"Typ {mime[:40]!r} nicht erlaubt")
    # Grobe Vorabgrenze, bevor dekodiert wird (Base64 ist ~4/3 größer)
    if len(nutzlast) > max_bytes * 4 // 3 + 16:
        raise RessourceGesperrt("Ressource zu groß")
    if "base64" in teile[1:]:
        try:
            daten = base64.b64decode("".join(urllib.parse.unquote(nutzlast).split()),
                                     validate=True)
        except (binascii.Error, ValueError) as e:
            raise RessourceGesperrt("Ungültige Base64-Daten") from e
    else:
        daten = urllib.parse.unquote_to_bytes(nutzlast)
    if len(daten) > max_bytes:
        raise RessourceGesperrt("Ressource zu groß")
    signaturen = ERLAUBTE_BILDTYPEN[mime]
    if signaturen is not None:
        if not any(daten.startswith(s) for s in signaturen):
            raise RessourceGesperrt("Inhalt passt nicht zum angegebenen Bildtyp")
        if mime == "image/webp" and daten[8:12] != b"WEBP":
            raise RessourceGesperrt("Inhalt passt nicht zum angegebenen Bildtyp")
    else:
        anfang = daten[:4096].lstrip().lower()
        if not (anfang.startswith(b"<svg") or anfang.startswith(b"<?xml")
                or anfang.startswith(b"<!--") or anfang.startswith(b"<!doctype")):
            raise RessourceGesperrt("Inhalt ist kein SVG")
        # DOCTYPE und interne Entitäten bleiben erlaubt — Illustrator schreibt
        # beides (``<!ENTITY ns_svg "http://…">``). Externe Entitäten
        # (SYSTEM/PUBLIC) werden abgewiesen, obwohl expat sie ohnehin nicht
        # nachlädt; gegen Entity-Expansion schützen expat (Amplification-
        # Grenze) und die Speicher-/CPU-Grenzen des Renderprozesses.
        if _EXTERNE_ENTITAET.search(daten):
            raise RessourceGesperrt("SVG mit externer Entität nicht erlaubt")
    return daten, mime


class _Fetcher:
    """``url_fetcher`` für WeasyPrint mit Gesamtbudget je Dokument."""

    _fail_on_errors = False     # abgewiesene Ressource → Warnung, Dokument entsteht ohne sie

    def __init__(self, max_bytes: int, max_gesamt: int):
        self.max_bytes = max_bytes
        self.rest = max_gesamt
        self.abgewiesen = 0

    def __call__(self, url):
        from weasyprint.urls import URLFetcherResponse
        try:
            daten, mime = ressource_holen(url, min(self.max_bytes, max(self.rest, 0)))
        except RessourceGesperrt:
            self.abgewiesen += 1
            raise
        self.rest -= len(daten)
        return URLFetcherResponse(url="data:", body=daten,
                                  headers={"Content-Type": mime})


# ── Audit-Hook ───────────────────────────────────────────────────────────────

_GESPERRTE_EREIGNISSE = (
    "socket.", "urllib.Request", "http.client.connect", "ftplib.connect",
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
    "os.fork", "os.forkpty", "pty.spawn", "webbrowser.open", "ctypes.dlopen",
    "os.chown", "os.mkfifo", "os.mknod", "os.chflags", "os.lchflags", "os.setxattr",
    "os.removexattr", "sqlite3.", "dbm.", "glob.glob", "os.kill", "os.killpg",
    "signal.pthread_kill",
)
# Dateisystem-Änderungen nur im eigenen Arbeitsverzeichnis (WeasyPrint legt
# dort z. B. Zwischendateien für Schriften an). Index = Pfadargumente.
_SCHREIB_EREIGNISSE = {
    "os.mkdir": (0,), "os.rmdir": (0,), "os.remove": (0,), "os.unlink": (0,),
    "os.truncate": (0,), "os.utime": (0,), "os.chmod": (0,), "shutil.rmtree": (0,),
    "os.rename": (0, 1), "os.link": (0, 1), "os.symlink": (0, 1),
}
# Verzeichnisinhalte nur innerhalb der Lesewurzeln (der Import-Mechanismus
# braucht das für nachgeladene Module)
_VERZEICHNIS_EREIGNISSE = ("os.listdir", "os.scandir")
# Ereignisse, die mit diesen Präfixen beginnen, aber harmlos sind
_ERLAUBTE_EREIGNISSE = ("socket.gethostname",)


def _lese_wurzeln() -> tuple[str, ...]:
    import site
    import sysconfig
    wurzeln = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix,
               "/usr/share/fonts", "/usr/local/share/fonts", "/usr/share/fontconfig",
               "/etc/fonts", "/usr/share/mime", "/usr/share/zoneinfo",
               "/usr/lib", "/usr/local/lib", "/dev/null", "/dev/urandom"}
    for schluessel in ("stdlib", "platstdlib", "purelib", "platlib"):
        p = sysconfig.get_paths().get(schluessel)
        if p:
            wurzeln.add(p)
    for p in site.getsitepackages() if hasattr(site, "getsitepackages") else []:
        wurzeln.add(p)
    return tuple(sorted(os.path.realpath(w) for w in wurzeln if w))


def sperren_einrichten(schreibverzeichnis: str, zusatz_lesen: tuple[str, ...] = ()) -> None:
    """Installiert den Audit-Hook. Danach nicht mehr aufhebbar."""
    lesen = _lese_wurzeln() + tuple(os.path.realpath(p) for p in zusatz_lesen)
    schreiben = os.path.realpath(schreibverzeichnis)

    def _unter(pfad: str, wurzeln) -> bool:
        return any(pfad == w or pfad.startswith(w.rstrip("/") + "/") for w in wurzeln)

    def hook(ereignis: str, argumente):
        if ereignis == "open":
            pfad = argumente[0]
            if isinstance(pfad, int):           # bereits offener Deskriptor
                return
            if isinstance(pfad, bytes):
                pfad = os.fsdecode(pfad)
            echt = os.path.realpath(str(pfad))
            modus = argumente[1] if len(argumente) > 1 else "r"
            schreibend = isinstance(modus, str) and any(z in modus for z in "wax+")
            flags = argumente[2] if len(argumente) > 2 else 0
            if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                schreibend = True
            if schreibend:
                if not _unter(echt, (schreiben,)):
                    raise PermissionError(f"Schreiben gesperrt: {echt}")
            elif not _unter(echt, lesen + (schreiben,)):
                raise PermissionError(f"Lesen gesperrt: {echt}")
            return
        if ereignis in _SCHREIB_EREIGNISSE:
            for i in _SCHREIB_EREIGNISSE[ereignis]:
                pfad = argumente[i] if len(argumente) > i else None
                if not isinstance(pfad, (str, bytes, os.PathLike)):
                    raise PermissionError(f"Im Renderprozess gesperrt: {ereignis}")
                echt = os.path.realpath(os.fsdecode(pfad))
                if not _unter(echt, (schreiben,)):
                    raise PermissionError(f"Im Renderprozess gesperrt: {ereignis} {echt}")
            return
        if ereignis in _VERZEICHNIS_EREIGNISSE:
            pfad = argumente[0] if argumente else "."
            if isinstance(pfad, int):
                raise PermissionError(f"Im Renderprozess gesperrt: {ereignis} (Deskriptor)")
            if isinstance(pfad, bytes):
                pfad = os.fsdecode(pfad)
            echt = os.path.realpath(str(pfad if pfad is not None else "."))
            if not _unter(echt, lesen + (schreiben,)):
                raise PermissionError(f"Verzeichnis gesperrt: {echt}")
            return
        if ereignis.startswith(_ERLAUBTE_EREIGNISSE):
            return
        if ereignis.startswith(_GESPERRTE_EREIGNISSE):
            raise PermissionError(f"Im Renderprozess gesperrt: {ereignis}")

    sys.addaudithook(hook)


# ── Hauptprogramm ────────────────────────────────────────────────────────────

def _anhang_finisher(auftrag: dict):
    """Finisher für die E-Rechnung (PDF/A-3 mit eingebettetem XML)."""
    e = auftrag.get("erechnung")
    if not e:
        return None
    import importlib.util
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erechnung", "pdf_anhang.py")
    spec = importlib.util.spec_from_file_location("_dz_pdf_anhang", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul.finisher(base64.b64decode(e["xml_b64"]), e["dateiname"],
                          titel=e.get("titel", ""), autor=e.get("autor", ""))


def grenzen_setzen(argv: list[str]) -> None:
    """rlimits — als Allererstes, bevor Eingaben gelesen werden."""
    import resource
    speicher = int(argv[1]) if len(argv) > 1 else 1024 * 1024 * 1024
    cpu = int(argv[2]) if len(argv) > 2 else 60
    resource.setrlimit(resource.RLIMIT_AS, (speicher, speicher))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    # Ausgabe geht über stdout; Dateien schreibt der Prozess nicht.
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if os.geteuid() == 0:
        # Der Elternprozess hätte die Rechte abgeben müssen — nie als root rendern.
        print("Renderprozess läuft als root — abgebrochen", file=sys.stderr)
        sys.exit(5)


def main() -> int:
    grenzen_setzen(sys.argv)
    try:
        auftrag = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        html = auftrag["html"]
        grenzen = auftrag.get("grenzen") or {}
        max_ressource = int(grenzen.get("max_ressource_bytes", 8 * 1024 * 1024))
        max_ressourcen_gesamt = int(grenzen.get("max_ressourcen_gesamt", 40 * 1024 * 1024))
        max_ausgabe = int(grenzen.get("max_ausgabe_bytes", 50 * 1024 * 1024))
        schreibverzeichnis = os.environ.get("TMPDIR") or os.getcwd()
    except Exception as e:                          # noqa: BLE001
        print(f"Ungültiger Renderauftrag: {type(e).__name__}", file=sys.stderr)
        return 2

    # Bibliotheken VOR dem Audit-Hook laden — sie lesen beim Import eigene
    # Dateien (Stylesheets, Schriftkonfiguration).
    from weasyprint import HTML
    import weasyprint.pdf  # noqa: F401
    finisher = _anhang_finisher(auftrag)

    sperren_einrichten(schreibverzeichnis)

    fetcher = _Fetcher(max_ressource, max_ressourcen_gesamt)
    puffer = io.BytesIO()
    try:
        dokument = HTML(string=html, base_url=None, url_fetcher=fetcher)
        optionen = {}
        if auftrag.get("pdf_variant"):
            optionen["pdf_variant"] = auftrag["pdf_variant"]
        if finisher is not None:
            optionen["finisher"] = finisher
        dokument.write_pdf(puffer, **optionen)
    except Exception as e:                          # noqa: BLE001
        print(f"Renderfehler: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        return 4

    daten = puffer.getvalue()
    if len(daten) > max_ausgabe:
        print("Ausgabe überschreitet die Größengrenze", file=sys.stderr)
        return 3
    if fetcher.abgewiesen:
        print(f"Hinweis: {fetcher.abgewiesen} Ressource(n) abgewiesen", file=sys.stderr)
    sys.stdout.buffer.write(daten)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
