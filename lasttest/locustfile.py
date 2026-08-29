"""
Lastprofil für DeineZeit
========================

Ein simulierter Benutzer macht das, was ein echter Mitarbeiter den Tag über
macht — mit Gewichten, die dem Alltag entsprechen. Das ist der wichtigste Teil
der Messung: Ein Profil, das ständig PDFs erzeugt, macht jede Anwendung
langsam und beweist gar nichts.

Gewichtung (``@task(n)`` — je höher, desto häufiger):

    Listen ansehen und blättern     häufig  — das ist die Grundlast
    Zeiterfassung starten/stoppen   mittel  — ein paar Mal am Tag
    Belege ansehen                  mittel
    Beleg anlegen                   selten
    PDF erzeugen                    selten  — der teuerste Vorgang
    Datei hoch-/herunterladen       selten

``wait_time`` zwischen einer und fünf Sekunden bildet die Denkpausen ab. Ohne
Pause misst man nicht 100 Menschen, sondern 100 Schleifen — und bekommt Zahlen,
die mit dem Betrieb nichts zu tun haben.

Vorbereitung: ``python3 lasttest/pruefdaten.py`` (legt Benutzer und Bestand an)
und ``RATE_LIMIT_AKTIV=false`` in der ``.env``, sonst misst man die Bremse.
Siehe README.md in diesem Ordner.
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

from locust import HttpUser, between, events, task

# ── Riegel ───────────────────────────────────────────────────────────────────
# Stillgelegt am 29.08.2026 (siehe docker-compose.lasttest.yml). Der Riegel
# sitzt zusätzlich hier, weil sich locust auch ohne Compose starten lässt —
# ein Profil allein wäre also nur ein halber Verschluss.
#
# WIEDER FREIGEBEN: STILLGELEGT auf False setzen.
STILLGELEGT = True

if STILLGELEGT and not os.environ.get("LASTTEST_TROTZDEM"):
    sys.exit(
        "\nDer Lasttest ist vorerst stillgelegt (29.08.2026).\n"
        "Die erste Erprobung war nicht brauchbar; das Thema wird später neu\n"
        "aufgesetzt. Zum Freigeben: STILLGELEGT in dieser Datei auf False\n"
        "setzen — oder für einen einmaligen Versuch LASTTEST_TROTZDEM=1\n"
        "setzen und wissen, was man tut.\n"
    )

PASSWORT = os.environ.get("LASTTEST_PASSWORT", "Zimt-Regenschirm-7719")
BENUTZER_ANZAHL = int(os.environ.get("LASTTEST_BENUTZER", "100"))

# Wird beim Start einmal gefüllt: IDs, auf die die Aufgaben zugreifen.
# Ohne das würde jeder simulierte Benutzer die Listen erst selbst abfragen —
# das verfälscht die Verteilung der Aufrufe.
BESTAND = {"kontakte": [], "belege": []}


@events.test_start.add_listener
def bestand_laden(environment, **_):
    """Einmal vor der Messung: Was gibt es zum Ansehen?"""
    import json
    import urllib.request

    basis = environment.host or "http://localhost"

    def hole(pfad, token):
        req = urllib.request.Request(
            basis + pfad, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as a:
            return json.loads(a.read().decode())

    try:
        req = urllib.request.Request(
            basis + "/api/auth/login",
            data=json.dumps({"email": "lasttest001@pruefung.local",
                             "password": PASSWORT}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as a:
            token = json.loads(a.read().decode())["access_token"]

        kontakte = hole("/api/masterdata/types/kontakte/records?page_size=50", token)
        BESTAND["kontakte"] = [k["id"] for k in kontakte.get("items", [])]
        belege = hole("/api/invoices", token)
        BESTAND["belege"] = [b["id"] for b in belege][:50]
        print(f"[Lasttest] Bestand: {len(BESTAND['kontakte'])} Kontakte, "
              f"{len(BESTAND['belege'])} Belege")
    except Exception as fehler:
        print(f"[Lasttest] Bestand konnte nicht geladen werden: {fehler}")
        print("[Lasttest] Läuft pruefdaten.py? Ohne Bestand misst der Test "
              "leere Listen.")


class Mitarbeiter(HttpUser):
    """Ein Mensch, der mit DeineZeit arbeitet."""

    wait_time = between(1, 5)

    def on_start(self):
        """Anmelden. Jeder simulierte Benutzer nimmt ein eigenes Konto —
        sonst messen wir hundertmal dieselbe Sitzung."""
        nummer = random.randint(1, BENUTZER_ANZAHL)
        antwort = self.client.post(
            "/api/auth/login",
            json={"email": f"lasttest{nummer:03d}@pruefung.local",
                  "password": PASSWORT},
            name="Anmelden")
        # Locust zählt einen Fehlschlag selbst als Fehler — hier wird nur der
        # Zustand sauber gehalten. (``antwort.failure()`` gäbe es ausschließlich
        # mit ``catch_response=True``, sonst ist es ein gewöhnliches
        # requests-Objekt und der Aufruf stürzt ab.)
        self.kopf = {}
        if antwort.status_code == 200 and antwort.json().get("access_token"):
            self.kopf = {"Authorization": f"Bearer {antwort.json()['access_token']}"}

    # ── Grundlast: ansehen und blättern ──────────────────────────────────────

    @task(10)
    def dashboard(self):
        self.client.get("/api/dashboard/kennzahlen", headers=self.kopf,
                        name="Dashboard")

    @task(8)
    def aufgabenliste(self):
        self.client.get("/api/aufgaben/", headers=self.kopf, name="Aufgaben")

    @task(8)
    def zeitenliste(self):
        seite = random.randint(1, 3)
        self.client.get(f"/api/zeiterfassung/entries?page={seite}",
                        headers=self.kopf, name="Zeiten (Liste)")

    @task(6)
    def kontaktliste(self):
        self.client.get("/api/masterdata/types/kontakte/records?page_size=50",
                        headers=self.kopf, name="Kontakte (Liste)")

    @task(4)
    def kontakt_suchen(self):
        """Suche geht über JSONB — eigener Eintrag, weil sie sich ganz anders
        verhält als das reine Blättern."""
        self.client.get(
            "/api/masterdata/types/kontakte/records?search=Lasttest&page_size=50",
            headers=self.kopf, name="Kontakte (Suche)")

    # ── Zeiterfassung ────────────────────────────────────────────────────────

    @task(5)
    def zeit_erfassen(self):
        """Timer starten und wieder stoppen — der häufigste Schreibvorgang."""
        jetzt = datetime.now(timezone.utc)
        antwort = self.client.post(
            "/api/zeiterfassung/start", headers=self.kopf,
            json={"started_at": jetzt.isoformat(),
                  "project_name": f"Lasttest Projekt {random.randint(1, 30):02d}",
                  "note": "Lasttest"},
            name="Zeit starten")
        if antwort.status_code not in (200, 201):
            return
        eintrag = antwort.json().get("id")
        if eintrag:
            self.client.post(f"/api/zeiterfassung/{eintrag}/stop",
                             headers=self.kopf, name="Zeit stoppen")

    # ── Belege ───────────────────────────────────────────────────────────────

    @task(5)
    def belegliste(self):
        self.client.get("/api/invoices", headers=self.kopf, name="Belege (Liste)")

    @task(3)
    def beleg_oeffnen(self):
        if not BESTAND["belege"]:
            return
        beleg = random.choice(BESTAND["belege"])
        self.client.get(f"/api/invoices/{beleg}", headers=self.kopf,
                        name="Beleg öffnen")

    @task(1)
    def beleg_anlegen(self):
        heute = datetime.now().date().isoformat()
        self.client.post("/api/invoices", headers=self.kopf, json={
            "doc_type": "rechnung",
            "title": "Lasttest Entwurf",
            "date": heute,
            "delivery_date": heute,
            "positions": [{"pos_type": "item", "description": "Leistung",
                           "quantity": "1", "unit_price": "100",
                           "tax_rate": "20"}],
        }, name="Beleg anlegen")

    @task(1)
    def pdf_erzeugen(self):
        """Der teuerste Vorgang (WeasyPrint). Bewusst selten — aber drin,
        weil genau hier die Antwortzeiten zuerst wegbrechen."""
        if not BESTAND["belege"]:
            return
        beleg = random.choice(BESTAND["belege"])
        self.client.get(f"/api/invoices/{beleg}/pdf", headers=self.kopf,
                        name="PDF erzeugen")

    # ── Dateien ──────────────────────────────────────────────────────────────

    @task(1)
    def datei_hochladen(self):
        """Kleine Datei an einen Kontakt hängen — prüft MinIO unter Last."""
        if not BESTAND["kontakte"]:
            return
        kontakt = random.choice(BESTAND["kontakte"])
        inhalt = b"Lasttest-Datei\n" * 200      # rund 3 kB
        self.client.post(
            f"/api/datacenter/kontakte/{kontakt}/upload",
            headers=self.kopf,
            files={"file": ("lasttest.txt", inhalt, "text/plain")},
            name="Datei hochladen")

    @task(2)
    def dateiliste(self):
        if not BESTAND["kontakte"]:
            return
        kontakt = random.choice(BESTAND["kontakte"])
        self.client.get(f"/api/datacenter/kontakte/{kontakt}",
                        headers=self.kopf, name="Dateien (Liste)")
