#!/usr/bin/env python3
"""
Prüfdaten für den Lasttest anlegen
==================================

Ein Lasttest gegen eine leere Datenbank misst nichts Brauchbares: Listen ohne
Zeilen sind immer schnell, und ohne Benutzer kann sich niemand anmelden. Dieses
Skript legt deshalb vorher an, was die Messung braucht.

Aufruf (gegen die lokale Umgebung):

    python3 lasttest/pruefdaten.py --admin admin@example.at

Nach dem Passwort wird gefragt — es gehört bewusst nicht auf die Kommandozeile:
Dort landet es in der Shell-History, und Sonderzeichen wie ``!`` lösen in zsh
eine History-Expansion aus. Das Passwort kommt dann still verändert an, und der
Fehlschlag sieht aus wie falsche Zugangsdaten.

Alles Angelegte trägt den Namenszusatz „Lasttest" und lässt sich damit
wiederfinden. Es wird **nicht** automatisch aufgeräumt — in einer Datenbank mit
echten Daten wäre ein Löschlauf über Namensmuster zu gefährlich.

Gegen die Produktivumgebung gehört das hier nicht. Deshalb warnt das Skript,
wenn die Adresse nicht auf localhost zeigt.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BENUTZER_PASSWORT = "Lasttest-Kaffee-42!"   # erfüllt die Passwortregeln
KONTAKT_ANZAHL = 200
PROJEKT_ANZAHL = 30
BELEG_ANZAHL = 50


def ruf(basis, pfad, token=None, daten=None, methode=None):
    kopf = {"Content-Type": "application/json"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    rumpf = json.dumps(daten).encode() if daten is not None else None
    req = urllib.request.Request(basis + pfad, data=rumpf, headers=kopf,
                                 method=methode or ("POST" if daten else "GET"))
    try:
        with urllib.request.urlopen(req) as antwort:
            text = antwort.read().decode()
            return antwort.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read().decode()[:400]


def anmelden(basis, email, passwort):
    status, antwort = ruf(basis, "/api/auth/login",
                          daten={"email": email, "password": passwort})
    if status != 200 or not isinstance(antwort, dict):
        print(f"  Anmeldung fehlgeschlagen ({status}): {antwort}")
        sys.exit(1)
    if not antwort.get("access_token"):
        print("  Anmeldung verlangt einen zweiten Faktor — bitte ein Konto "
              "ohne 2FA verwenden oder die Prüfdaten von Hand anlegen.")
        sys.exit(1)
    return antwort["access_token"]


def benutzer_anlegen(basis, token, anzahl):
    """Testbenutzer für die gleichzeitigen Sitzungen.

    Alle mit demselben Passwort — der Lasttest misst die Anwendung, nicht die
    Passwortverwaltung.
    """
    angelegt, vorhanden = 0, 0
    for i in range(1, anzahl + 1):
        email = f"lasttest{i:03d}@pruefung.local"
        status, antwort = ruf(basis, "/api/users/", token, {
            "email": email,
            "full_name": f"Lasttest Benutzer {i:03d}",
            "role": "employee",
            "language": "de",
            "password": BENUTZER_PASSWORT,
        })
        if status in (200, 201):
            angelegt += 1
        elif status == 400 and "bereits" in str(antwort).lower():
            vorhanden += 1
        else:
            print(f"  Benutzer {email}: {status} {antwort}")
    print(f"  Benutzer: {angelegt} neu, {vorhanden} schon vorhanden")


def stammdaten_anlegen(basis, token):
    """Kontakte und Projektzeiten über den Import-Endpunkt.

    Der schreibt in einer Transaktion und ist damit um ein Vielfaches schneller
    als 200 Einzelaufrufe.
    """
    kontakte = [{"name": f"Lasttest Kunde {i:03d}",
                 "typ": "Kunde"} for i in range(1, KONTAKT_ANZAHL + 1)]
    status, antwort = ruf(basis, "/api/masterdata/types/kontakte/records/import",
                          token, {"rows": kontakte, "dry_run": False})
    print(f"  Kontakte: {status} {antwort if status != 200 else antwort.get('angelegt')}")

    projekte = [{"name": f"Lasttest Projekt {i:02d}"}
                for i in range(1, PROJEKT_ANZAHL + 1)]
    status, antwort = ruf(basis, "/api/masterdata/types/projektzeiten/records/import",
                          token, {"rows": projekte, "dry_run": False})
    print(f"  Projekte: {status} {antwort if status != 200 else antwort.get('angelegt')}")


def belege_anlegen(basis, token, anzahl):
    """Ein paar Belege, damit die Verkaufsliste nicht leer ist und es etwas
    zum Drucken gibt."""
    heute = date.today()
    angelegt = 0
    for i in range(anzahl):
        tag = (heute - timedelta(days=i % 60)).isoformat()
        status, _ = ruf(basis, "/api/invoices", token, {
            "doc_type": "rechnung",
            "title": f"Lasttest Beleg {i:03d}",
            "date": tag,
            "delivery_date": tag,
            "positions": [
                {"pos_type": "item", "description": "Beratung",
                 "quantity": "3", "unit_price": "120", "tax_rate": "20"},
                {"pos_type": "item", "description": "Fahrtkosten",
                 "quantity": "1", "unit_price": "45", "tax_rate": "20"},
            ],
        })
        if status in (200, 201):
            angelegt += 1
    print(f"  Belege: {angelegt} von {anzahl}")


def main():
    p = argparse.ArgumentParser(description="Prüfdaten für den Lasttest anlegen")
    p.add_argument("--basis", default="http://localhost", help="Adresse der Anwendung")
    p.add_argument("--admin", required=True, help="E-Mail eines Administrators")
    p.add_argument("--benutzer", type=int, default=100,
                   help="Anzahl Testbenutzer (Vorgabe 100)")
    args = p.parse_args()

    # Passwort per Eingabeaufforderung oder aus der Umgebung — nie als
    # Kommandozeilen-Argument (Shell-History, History-Expansion bei „!").
    passwort = os.environ.get("DZ_ADMIN_PASSWORT") or getpass.getpass(
        f"Passwort für {args.admin}: ")
    if not passwort:
        sys.exit("Ohne Passwort geht es nicht.")

    basis = args.basis.rstrip("/")
    if "localhost" not in basis and "127.0.0.1" not in basis:
        antwort = input(f"ACHTUNG: {basis} ist nicht localhost. Wirklich dort "
                        f"Prüfdaten anlegen? [nein/ja] ")
        if antwort.strip().lower() != "ja":
            sys.exit("Abgebrochen.")

    print(f"Prüfdaten für {basis}")
    token = anmelden(basis, args.admin, passwort)
    benutzer_anlegen(basis, token, args.benutzer)
    stammdaten_anlegen(basis, token)
    belege_anlegen(basis, token, BELEG_ANZAHL)
    print(f"\nFertig. Anmeldung der Testbenutzer: "
          f"lasttest001@pruefung.local … / {BENUTZER_PASSWORT}")


if __name__ == "__main__":
    main()
