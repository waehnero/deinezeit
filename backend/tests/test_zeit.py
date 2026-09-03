"""
Ortszeit statt UTC für Kalenderdaten (Audit 02.09.2026, BUG-002).
"""
import ast
import pathlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core import zeit
from app.core.config import settings

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_prozess_zeitzone_ist_gesetzt():
    """config.py setzt TZ für den Prozess — date.today() liefert Ortszeit."""
    import os
    import time
    assert os.environ["TZ"] == settings.TZ
    assert time.tzname != ("UTC", "UTC") or settings.TZ == "UTC"


def test_heute_und_jetzt_folgen_der_zeitzone():
    erwartet = datetime.now(ZoneInfo(settings.TZ))
    assert zeit.heute() == erwartet.date()
    assert abs((zeit.jetzt() - erwartet.replace(tzinfo=None)).total_seconds()) < 5
    assert zeit.jetzt().tzinfo is None          # gleiches Verhalten wie datetime.now()


def test_spaeter_abend_ist_noch_derselbe_tag():
    """Der eigentliche Fehler: 23:30 Ortszeit am 31.12. war in UTC schon
    22:30 — und `date.today()` in UTC lieferte dort den Vortag, im Jänner
    sogar das falsche Jahr für den Nummernkreis."""
    utc_moment = datetime(2026, 12, 31, 22, 30, tzinfo=timezone.utc)
    assert utc_moment.astimezone(ZoneInfo("Europe/Vienna")).date().isoformat() == "2026-12-31"
    utc_moment = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
    assert utc_moment.astimezone(ZoneInfo("Europe/Vienna")).date().isoformat() == "2027-01-01"


def test_kein_nacktes_today_oder_now_im_fachcode():
    """Fachcode nimmt heute()/jetzt() — sonst ist die Absicht nicht sichtbar
    und ein Test kann die Uhr nicht stellen. (datetime.now(timezone.utc) für
    Zeitstempel bleibt erlaubt.)"""
    treffer = []
    for datei in list((APP / "api").glob("*.py")) + list((APP / "services").glob("*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call) or not isinstance(knoten.func, ast.Attribute):
                continue
            name = knoten.func.attr
            basis = getattr(knoten.func.value, "id", None)
            if (basis, name) == ("date", "today") or \
               ((basis, name) == ("datetime", "now") and not knoten.args and not knoten.keywords):
                treffer.append(f"{datei.name}:{knoten.lineno}")
    assert not treffer, "Bitte heute()/jetzt() aus app.core.zeit verwenden:\n  " + "\n  ".join(treffer)
