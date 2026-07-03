"""
Tests für die Belegeinstellungen (Key-Value-Store unter /api/invoices/settings).

Hintergrund: Das Frontend (Einstellungen → Parameter → Belegeinstellungen) lädt
alle Werte über GET /api/invoices/settings/all und speichert einzelne Schlüssel
über PUT /api/invoices/settings/{key}. Werte sind beliebiges JSON (JSONB),
z.B. die Bankverbindung als Objekt {iban, bic, bank}.
"""
from tests.conftest import TEST_USER_PASSWORD

ADMIN_EMAIL = "admin@deinezeit.local"


def _admin_client(client, admin_user):
    """Loggt den Admin ein und setzt den Bearer-Token am Client."""
    resp = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin-Login fehlgeschlagen: {resp.text}"
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    return client


def test_get_settings_initial_leer(auth_client):
    """Ohne gespeicherte Werte liefert GET /settings/all ein leeres Dict."""
    resp = auth_client.get("/api/invoices/settings/all")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_put_setting_erfordert_admin(auth_client):
    """Normale Benutzer (employee) dürfen keine Belegeinstellungen speichern."""
    resp = auth_client.put(
        "/api/invoices/settings/bank",
        json={"key": "bank", "value": {"iban": "AT00", "bic": "X", "bank": "Y"}},
    )
    assert resp.status_code == 403


def test_put_und_get_roundtrip(client, admin_user):
    """Admin speichert Bankdaten (Objekt) + Zahl + Text; GET liefert alles typtreu zurück."""
    admin = _admin_client(client, admin_user)

    bank = {"iban": "AT12 3456 7890 1234 5678", "bic": "BKAUATWW", "bank": "Bank Austria"}
    r1 = admin.put("/api/invoices/settings/bank", json={"key": "bank", "value": bank})
    assert r1.status_code == 200
    assert r1.json() == {"key": "bank", "value": bank}

    r2 = admin.put("/api/invoices/settings/default_tax_rate",
                   json={"key": "default_tax_rate", "value": 20})
    assert r2.status_code == 200

    r3 = admin.put("/api/invoices/settings/kleinunternehmer_text",
                   json={"key": "kleinunternehmer_text", "value": "Gemäß § 6 Abs. 1 Z 27 UStG"})
    assert r3.status_code == 200

    resp = admin.get("/api/invoices/settings/all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bank"] == bank                      # Objekt bleibt Objekt
    assert data["default_tax_rate"] == 20            # Zahl bleibt Zahl
    assert data["kleinunternehmer_text"] == "Gemäß § 6 Abs. 1 Z 27 UStG"


def test_put_setting_update_ueberschreibt(client, admin_user):
    """Zweites PUT auf denselben Schlüssel überschreibt den Wert (Upsert)."""
    admin = _admin_client(client, admin_user)

    admin.put("/api/invoices/settings/bank", json={"key": "bank", "value": {"iban": "ALT"}})
    admin.put("/api/invoices/settings/bank", json={"key": "bank", "value": {"iban": "NEU"}})

    resp = admin.get("/api/invoices/settings/all")
    assert resp.json()["bank"] == {"iban": "NEU"}


def test_get_settings_ohne_login(client):
    """Ohne Token gibt es keinen Zugriff."""
    resp = client.get("/api/invoices/settings/all")
    assert resp.status_code in (401, 403)


def test_template_preview_liefert_html(auth_client):
    """Die Vorlagen-Vorschau liefert für alle 5 Vorlagen HTML mit Beispieldaten."""
    for n in (1, 2, 3, 4, 5):
        resp = auth_client.get(f"/api/invoices/template-preview/{n}")
        assert resp.status_code == 200, f"Vorlage {n}: {resp.text[:200]}"
        assert "text/html" in resp.headers["content-type"]
        assert "rechnung" in resp.text.lower()   # Vorlage 1: "Rechnung", übrige: "RECHNUNG"
        assert "Musterfirma GmbH" in resp.text


def test_template_preview_unbekannte_vorlage(auth_client):
    """Unbekannte Vorlagen-Nummern geben 404."""
    resp = auth_client.get("/api/invoices/template-preview/9")
    assert resp.status_code == 404


# ── Beleg-PDF & Beleg-Vorschau ────────────────────────────────────────────────

def _create_test_invoice(auth_client) -> str:
    """Legt eine minimale Rechnung mit einer Position an, gibt die ID zurück."""
    resp = auth_client.post("/api/invoices", json={
        "doc_type": "rechnung",
        "date": "2026-07-03",
        "title": "Testrechnung",
        "positions": [{
            "pos_type": "item", "description": "Testposition",
            "quantity": 2, "unit": "Std.", "unit_price": 100, "tax_rate": 20,
        }],
    })
    assert resp.status_code in (200, 201), f"Rechnung anlegen fehlgeschlagen: {resp.text}"
    return resp.json()["id"]


def test_invoice_pdf_download(auth_client):
    """GET /invoices/{id}/pdf liefert ein PDF des Belegs."""
    invoice_id = _create_test_invoice(auth_client)
    resp = auth_client.get(f"/api/invoices/{invoice_id}/pdf")
    assert resp.status_code == 200, resp.text[:300]
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content[:5] == b"%PDF-"
    assert ".pdf" in resp.headers.get("content-disposition", "")


def test_invoice_html_preview(auth_client):
    """GET /invoices/{id}/preview liefert die HTML-Vorschau des Belegs."""
    invoice_id = _create_test_invoice(auth_client)
    resp = auth_client.get(f"/api/invoices/{invoice_id}/preview")
    assert resp.status_code == 200, resp.text[:300]
    assert "text/html" in resp.headers["content-type"]
    assert "Testposition" in resp.text
    assert "rechnung" in resp.text.lower()


def test_invoice_pdf_unbekannter_beleg(auth_client):
    """PDF für nicht existierenden Beleg gibt 404."""
    resp = auth_client.get("/api/invoices/00000000-0000-0000-0000-000000000000/pdf")
    assert resp.status_code == 404
