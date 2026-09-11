"""
Anfragekennung (Request-ID) für das Logging — Audit-Befund OPS-006.

Problem vorher: Im Serverlog standen die Zeilen einer Anfrage (nginx-Zugriff,
unsere Meldungen, ein Traceback) ohne gemeinsamen Schlüssel untereinander.
Bei zehn gleichzeitigen Benutzern lässt sich dann nicht mehr sagen, welche
Meldung zu welchem Aufruf gehört — genau das Problem bei der sporadisch
scheiternden Postecke-KI.

Lösung: Jede Anfrage bekommt eine Kennung.
- nginx erzeugt sie (``$request_id``, 32 Hex-Zeichen) und reicht sie als
  ``X-Request-ID`` weiter; sie steht damit auch im nginx-Zugriffslog.
- Fehlt der Header (direkter Aufruf, Tests, lokale Entwicklung), erzeugen wir
  selbst eine kurze Kennung.
- Die Kennung liegt in einer ``ContextVar``; der Logging-Filter hängt sie an
  jede Logzeile unterhalb von ``app`` (Format in ``main.py``).
- Die Antwort trägt denselben ``X-Request-ID``-Header, damit ein Benutzer die
  Kennung aus den Entwicklerwerkzeugen melden kann.

Fremde Werte werden begrenzt und gefiltert (nur ``[A-Za-z0-9_.-]``, max. 64
Zeichen), damit niemand über den Header Steuerzeichen ins Log schreibt.
"""
import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

HEADER = "x-request-id"
_ERLAUBT = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_log = logging.getLogger("app.zugriff")


def aktuelle_request_id() -> str:
    """Kennung der laufenden Anfrage, ``"-"`` außerhalb einer Anfrage."""
    return request_id_var.get()


def _neue_kennung() -> str:
    return uuid.uuid4().hex[:16]


def _kennung_aus_header(scope: Scope) -> str:
    for name, wert in scope.get("headers", ()):
        if name == HEADER.encode():
            kandidat = wert.decode("latin-1", "replace").strip()
            if _ERLAUBT.match(kandidat):
                return kandidat
            break
    return _neue_kennung()


class RequestIdMiddleware:
    """Reines ASGI-Middleware (kein BaseHTTPMiddleware: das würde Streaming-
    Antworten puffern und ist deutlich langsamer)."""

    # Ab dieser Dauer wird eine Anfrage als langsam protokolliert.
    LANGSAM_AB_SEKUNDEN = 5.0

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        kennung = _kennung_aus_header(scope)
        token = request_id_var.set(kennung)
        start = time.monotonic()
        status_code = 0

        async def send_mit_header(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", kennung.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_mit_header)
        except Exception:
            # Unbehandelte Ausnahme: hier einmal MIT Kennung protokollieren.
            # Uvicorn loggt den Traceback separat (ohne Kennung); diese Zeile
            # ist die Brücke zwischen beiden.
            _log.error(
                "Unbehandelter Fehler: %s %s",
                scope.get("method"), scope.get("path"),
            )
            raise
        finally:
            dauer = time.monotonic() - start
            if status_code >= 500:
                _log.warning(
                    "%s %s -> %s (%.2fs)",
                    scope.get("method"), scope.get("path"), status_code, dauer,
                )
            elif dauer >= self.LANGSAM_AB_SEKUNDEN:
                _log.info(
                    "Langsame Anfrage: %s %s -> %s (%.1fs)",
                    scope.get("method"), scope.get("path"), status_code, dauer,
                )
            request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Hängt ``request_id`` an jeden LogRecord (für das Format in main.py)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
