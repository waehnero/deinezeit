"""
Anfragekennung (core/request_id.py, Audit OPS-006).

Geprüft wird das Verhalten, nicht das Format des Serverlogs:
- ohne Header erzeugt das Backend eine Kennung und gibt sie zurück,
- eine gültige Kennung von nginx wird unverändert übernommen,
- eine unbrauchbare (Leer-/Sonderzeichen, zu lang, leer) wird ersetzt statt durchgereicht,
- der Logging-Filter hängt die Kennung an LogRecords, außerhalb einer Anfrage "-".
"""
import logging
import re

from app.core.request_id import (
    RequestIdFilter,
    aktuelle_request_id,
    request_id_var,
)


def test_kennung_wird_erzeugt_und_zurueckgegeben(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    kennung = resp.headers.get("x-request-id")
    assert kennung and re.fullmatch(r"[0-9a-f]{16}", kennung)


def test_zwei_anfragen_zwei_kennungen(client):
    a = client.get("/api/health").headers["x-request-id"]
    b = client.get("/api/health").headers["x-request-id"]
    assert a != b


def test_kennung_von_nginx_wird_uebernommen(client):
    von_nginx = "a" * 32
    resp = client.get("/api/health", headers={"X-Request-ID": von_nginx})
    assert resp.headers["x-request-id"] == von_nginx


def test_unbrauchbare_kennung_wird_ersetzt(client):
    for schlecht in ["x" * 65, "", "leer zeichen", "semikolon;drin", "pfad/../x"]:
        resp = client.get("/api/health", headers={"X-Request-ID": schlecht})
        kennung = resp.headers["x-request-id"]
        assert kennung != schlecht
        assert re.fullmatch(r"[0-9a-f]{16}", kennung)


def test_filter_haengt_kennung_an_logrecord():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hallo", None, None)
    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "-"          # außerhalb einer Anfrage

    token = request_id_var.set("deadbeef")
    try:
        assert aktuelle_request_id() == "deadbeef"
        RequestIdFilter().filter(record)
        assert record.request_id == "deadbeef"
    finally:
        request_id_var.reset(token)


def test_kennung_ausserhalb_der_anfrage_zurueckgesetzt(client):
    client.get("/api/health", headers={"X-Request-ID": "b" * 20})
    assert aktuelle_request_id() == "-"
