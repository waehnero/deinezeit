"""
Kleine HTTP-Helfer.
"""
from urllib.parse import quote


def content_disposition(art: str, dateiname: str) -> str:
    """``Content-Disposition`` nach RFC 6266/5987 mit Umlauten und Anführungszeichen.

    Bis 03.09.2026 stand der Dateiname roh im Header (``filename="{name}"``):
    Ein ``"`` im Namen zerriss den Header, Umlaute kamen je nach Browser
    verstümmelt oder gar nicht an (Audit BUG-005). Jetzt gibt es einen
    ASCII-Ersatz für alte Clients und ``filename*`` mit UTF-8 für alle anderen.
    """
    art = "inline" if art == "inline" else "attachment"
    name = (dateiname or "datei").replace("\r", " ").replace("\n", " ").strip() or "datei"
    ascii_name = (name.encode("ascii", "replace").decode("ascii")
                  .replace('"', "'").replace("\\", "_").replace("?", "_"))
    return (f'{art}; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(name, safe='')}")
