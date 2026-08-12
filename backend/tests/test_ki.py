"""
Tests für den gemeinsamen KI-Service (services/ki.py) — Diagnose-Etappe.

Hintergrund: Die KI-Anbindung schlug auf dem Server sporadisch fehl, im Log
stand aber nur ein nacktes "400 Bad Request". Weder die Rohantwort noch der
Abbruchgrund (``stop_reason``) wurden protokolliert, und der stille Rückfall
auf unverkleinerte Originalfotos war von außen unsichtbar.

Diese Tests sichern die Instrumentierung ab — sie prüfen also, dass im
Fehlerfall überhaupt etwas Verwertbares im Log landet. Sie treffen bewusst
KEINE Aussage darüber, welche Ursache am Ende die richtige war.

Der echte HTTP-Aufruf wird durchgehend gemockt; es wird kein API-Key benötigt.
"""
import logging

import pytest

from app.services import ki as ki_service


class _FakeResponse:
    """Minimaler httpx.Response-Ersatz für die Provider-Antwort."""

    def __init__(self, daten, status_code=200, text=""):
        self._daten = daten
        self.status_code = status_code
        self.text = text or ""

    def json(self):
        return self._daten

    def raise_for_status(self):
        return None


def _ki_einstellungen(monkeypatch, provider="anthropic", model="test-modell"):
    """KI-Konfiguration ohne echte Verschlüsselung."""
    monkeypatch.setattr(ki_service, "decrypt_secret", lambda enc: "test-key")
    return {"provider": provider, "api_key_enc": "verschluesselt", "model": model}


def _antwort_mit(monkeypatch, daten):
    """httpx.post so mocken, dass der Provider ``daten`` zurückgibt."""
    monkeypatch.setattr(ki_service.httpx, "post",
                        lambda url, **kw: _FakeResponse(daten))


# ── Abbruchgrund (der eigentliche blinde Fleck) ───────────────────────────────
def test_stop_reason_wird_protokolliert(monkeypatch, caplog):
    """Eine normale Antwort hinterlässt eine [KI-AUFRUF]-Zeile mit stop_reason."""
    ki = _ki_einstellungen(monkeypatch)
    _antwort_mit(monkeypatch, {
        "content": [{"type": "text", "text": '{"text": "ok"}'}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 120, "output_tokens": 15},
    })

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        text = ki_service.call_ki(ki, "Hallo", kontext="test")

    assert text == '{"text": "ok"}'
    zeile = "\n".join(caplog.messages)
    assert "[KI-AUFRUF]" in zeile
    assert "stop_reason=end_turn" in zeile
    assert "120 rein / 15 raus" in zeile


def test_abgeschnittene_antwort_wird_als_warnung_gemeldet(monkeypatch, caplog):
    """
    Kernfall der Diagnose: Reißt die Antwort am Token-Limit ab, ist ein
    nachgelagerter Parser-Fehler nur die Folge. Das muss als Warnung sichtbar
    sein, sonst sucht man an der falschen Stelle.
    """
    ki = _ki_einstellungen(monkeypatch)
    _antwort_mit(monkeypatch, {
        "content": [{"type": "text", "text": '{"titel": "abgeschn'}],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 4000, "output_tokens": 2000},
    })

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        ki_service.call_ki(ki, "Hallo", max_tokens=2000)

    treffer = [r for r in caplog.records if "[KI-AUFRUF]" in r.getMessage()]
    assert treffer, "keine Diagnose-Zeile geschrieben"
    assert treffer[-1].levelno == logging.WARNING
    assert "abgeschnitten" in treffer[-1].getMessage()


def test_openai_finish_reason_wird_ebenso_erfasst(monkeypatch, caplog):
    """Beim zweiten Provider heißt das Feld anders — auch das muss greifen."""
    ki = _ki_einstellungen(monkeypatch, provider="openai", model="gpt-test")
    _antwort_mit(monkeypatch, {
        "choices": [{"finish_reason": "length",
                     "message": {"content": "halbe Antwort"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 800},
    })

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        ki_service.call_ki(ki, "Hallo")

    treffer = [r for r in caplog.records if "[KI-AUFRUF]" in r.getMessage()]
    assert treffer[-1].levelno == logging.WARNING
    assert "stop_reason=length" in treffer[-1].getMessage()


# ── Provider-Fehler (der zweite 400er-Pfad) ──────────────────────────────────
def test_http_fehler_landet_mit_originaltext_im_log(monkeypatch, caplog):
    """
    Antwortet der Provider selbst mit einem Fehlerstatus, muss sein
    Originaltext ins Log — die Nutzermeldung bleibt bewusst kurz. Ohne diese
    Unterscheidung sahen beide 400er-Pfade im Log identisch aus.
    """
    import httpx

    ki = _ki_einstellungen(monkeypatch)
    fehler_body = '{"error": {"message": "image exceeds 5 MB maximum"}}'

    def _post(url, **kw):
        resp = _FakeResponse({"error": {"message": "image exceeds 5 MB maximum"}},
                             status_code=400, text=fehler_body)

        def _raise():
            raise httpx.HTTPStatusError("400", request=None, response=resp)

        resp.raise_for_status = _raise
        return resp

    monkeypatch.setattr(ki_service.httpx, "post", _post)

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        with pytest.raises(RuntimeError):
            ki_service.call_ki(ki, "Hallo")

    treffer = [r for r in caplog.records if "[KI-HTTP]" in r.getMessage()]
    assert treffer, "Provider-Fehler wurde nicht protokolliert"
    assert "image exceeds 5 MB maximum" in treffer[-1].getMessage()
    assert "HTTP 400" in treffer[-1].getMessage()


# ── Bild-Aufbereitung ────────────────────────────────────────────────────────
def test_fehlgeschlagenes_verkleinern_wird_gemeldet(caplog):
    """
    Bisher schluckte _bild_verkleinern jeden Fehler und gab das Original
    zurück — genau dann geht ein unverkleinertes Foto an den Provider.
    """
    kaputt = b"das ist kein bild"

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        daten, mimetype = ki_service._bild_verkleinern(kaputt, "image/jpeg")

    # Verhalten unverändert: Original wird durchgereicht ...
    assert daten == kaputt
    assert mimetype == "image/jpeg"
    # ... aber nicht mehr stillschweigend
    treffer = [r for r in caplog.records if "[KI-BILD]" in r.getMessage()]
    assert treffer
    assert "Original" in treffer[-1].getMessage()


def test_bildgroessen_stehen_nach_dem_verkleinern_im_log(monkeypatch, caplog):
    """Die protokollierte Größe ist die TATSÄCHLICH gesendete (nach Verkleinern)."""
    import io

    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGB", (4000, 3000), (10, 20, 30)).save(puffer, format="JPEG")
    grosses_foto = puffer.getvalue()

    ki = _ki_einstellungen(monkeypatch)
    _antwort_mit(monkeypatch, {
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {},
    })

    with caplog.at_level(logging.INFO, logger="app.services.ki"):
        ki_service.call_ki(ki, "Hallo", images=[(grosses_foto, "image/jpeg")])

    zeile = [r.getMessage() for r in caplog.records if "[KI-AUFRUF]" in r.getMessage()][-1]
    assert "image/jpeg" in zeile
    # verkleinert -> deutlich kleiner als das Original
    gesendet = int(zeile.split("image/jpeg ")[1].split("B")[0])
    assert gesendet < len(grosses_foto)
