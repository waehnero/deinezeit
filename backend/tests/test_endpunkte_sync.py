"""
Endpunkte dürfen den Event-Loop nicht blockieren (Audit 02.09.2026, PERF-001).

FastAPI führt ``async def``-Endpunkte direkt im Event-Loop aus. Wer darin
synchron auf die Datenbank wartet, ein PDF rendert oder eine E-Mail schickt,
hält damit **alle** anderen Anfragen an — bei einem Arbeitsprozess spürt das
jeder Benutzer. Gewöhnliche ``def``-Endpunkte laufen dagegen im Threadpool.

Regel: Ein Endpunkt ist nur dann ``async``, wenn er tatsächlich ``await``
benutzt — und dann gehören blockierende Aufrufe darin in
``run_in_threadpool``. Dieser Test hält die erste Hälfte der Regel fest.
"""
import ast
import pathlib

import pytest

API = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"

# Endpunkte, die bewusst async sind und deren blockierende Teile im
# Threadpool laufen. Wer hier etwas einträgt, muss das im Endpunkt so
# umgesetzt haben.
BEWUSST_ASYNC = {
    ("auth.py", "login"),                 # asyncio.sleep in _bremsen; bcrypt im Threadpool
    ("system.py", "get_version_info"),    # httpx
    ("system.py", "get_changelog"),       # httpx
    ("period.py", "download_package"),    # Endpunkte laufen im Threadpool (period_service)
}


def _endpunkte():
    for datei in sorted(API.glob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            ist_route = any(
                isinstance(d, ast.Call)
                and getattr(getattr(d, "func", None), "attr", "") in
                ("get", "post", "put", "patch", "delete")
                for d in knoten.decorator_list)
            if ist_route:
                yield datei.name, knoten


def test_kein_async_endpunkt_ohne_await():
    """``async def`` ohne ``await`` bringt nichts — außer Blockade."""
    verstoesse = []
    for datei, fn in _endpunkte():
        if not isinstance(fn, ast.AsyncFunctionDef) or (datei, fn.name) in BEWUSST_ASYNC:
            continue
        hat_await = any(isinstance(x, (ast.Await, ast.AsyncFor, ast.AsyncWith))
                        for x in ast.walk(fn))
        if not hat_await:
            verstoesse.append(f"{datei}:{fn.lineno} {fn.name}")
    assert not verstoesse, (
        "async-Endpunkte ohne await (bitte auf 'def' umstellen):\n  "
        + "\n  ".join(verstoesse))


def test_async_endpunkte_sind_bekannt():
    """Jeder verbleibende async-Endpunkt steht bewusst in der Liste oben."""
    unbekannt = [f"{datei} {fn.name}" for datei, fn in _endpunkte()
                 if isinstance(fn, ast.AsyncFunctionDef)
                 and (datei, fn.name) not in BEWUSST_ASYNC]
    assert not unbekannt, ("Neue async-Endpunkte — blockierende Aufrufe in "
                           "run_in_threadpool und in BEWUSST_ASYNC eintragen:\n  "
                           + "\n  ".join(unbekannt))


@pytest.mark.parametrize("pfad", ["/api/system/version", "/api/system/changelog"])
def test_versionsabfrage_nur_angemeldet(client, pfad):
    """OPS-004: Versionsprüfung (GitHub-Anfrage, git fetch) nicht mehr anonym."""
    assert client.get(pfad).status_code in (401, 403)
