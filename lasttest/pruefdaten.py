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

# Bewusst OHNE „Lasttest" im Passwort: Die Passwortregel lehnt ab, sobald ein
# Namensteil ab vier Zeichen darin vorkommt — und die Konten heißen „Lasttest
# Benutzer 001". Am 29.08.2026 scheiterten daran alle 100 Anlagen auf einmal.
BENUTZER_PASSWORT = "Zimt-Regenschirm-7719"
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


def _wert_fuer(feld, bezeichnung, nummer):
    """Einen zum Feldtyp passenden Wert erfinden.

    Jede Installation hat eigene Stammdaten-Felder — feste Spaltennamen wie
    „name" und „typ" gehen deshalb ins Leere. Am 29.08.2026 lief der Import
    genau deshalb mit Status 200 durch und legte trotzdem nichts an: Alle
    Zeilen wurden wegen fehlender Pflichtfelder beanstandet.
    """
    typ = feld.get("field_type")
    if typ in ("text", "textarea"):
        return bezeichnung
    if typ == "number":
        return str(100 + nummer)
    if typ == "date":
        return date.today().isoformat()
    if typ == "email":
        return f"lasttest{nummer:03d}@pruefung.local"
    if typ == "phone":
        return "+43 660 0000000"
    if typ == "url":
        return "https://beispiel.at"
    if typ == "checkbox":
        return "nein"
    if typ == "dropdown":
        optionen = feld.get("options") or []
        return str(optionen[0]) if optionen else ""
    # relation: braucht einen bestehenden Zieldatensatz — nicht raten.
    return ""


def _importieren(basis, token, slug, bezeichner, anzahl, was):
    status, typ = ruf(basis, f"/api/masterdata/types/{slug}", token)
    if status != 200 or not isinstance(typ, dict):
        print(f"  {was}: Typ „{slug}“ nicht gefunden ({status}) — übersprungen")
        return

    felder = typ.get("fields") or []
    # Pflichtfelder müssen gefüllt sein, dazu das erste Textfeld: Aus ihm bildet
    # der Server den Anzeigenamen, sonst heißen alle Datensätze gleich (nämlich
    # gar nicht) und man findet sie später nicht wieder.
    erstes_text = next((f for f in felder if f.get("field_type") == "text"), None)
    noetig = [f for f in felder if f.get("is_required")]
    if erstes_text and erstes_text not in noetig:
        noetig.insert(0, erstes_text)

    if not noetig:
        print(f"  {was}: „{slug}“ hat keine befüllbaren Felder — übersprungen")
        return

    zeilen = []
    for i in range(1, anzahl + 1):
        zeilen.append({f["key"]: _wert_fuer(f, f"{bezeichner} {i:03d}", i)
                       for f in noetig})

    status, antwort = ruf(basis, f"/api/masterdata/types/{slug}/records/import",
                          token, {"rows": zeilen, "dry_run": False})
    if status != 200 or not isinstance(antwort, dict):
        print(f"  {was}: {status} {antwort}")
        return

    angelegt = antwort.get("angelegt", 0)
    beanstandet = antwort.get("beanstandungen") or []
    print(f"  {was}: {angelegt} angelegt"
          + (f", {len(beanstandet)} beanstandet" if beanstandet else ""))
    # Den Grund zeigen, sonst steht da nur eine Null und niemand weiß warum.
    for b in beanstandet[:3]:
        print(f"      Zeile {b['zeile']}, {b.get('feld') or '—'}: {b['grund']}")


def stammdaten_anlegen(basis, token):
    """Kontakte und Projektzeiten über den Import-Endpunkt.

    Der schreibt in einer Transaktion und ist damit um ein Vielfaches schneller
    als 200 Einzelaufrufe. Welche Felder gefüllt werden, fragt das Skript vorher
    beim Server ab — feste Spaltennamen passen nicht zu jeder Installation.
    """
    _importieren(basis, token, "kontakte", "Lasttest Kunde",
                 KONTAKT_ANZAHL, "Kontakte")
    _importieren(basis, token, "projektzeiten", "Lasttest Projekt",
                 PROJEKT_ANZAHL, "Projekte")


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


# ── Riegel ───────────────────────────────────────────────────────────────────
# Stillgelegt am 29.08.2026 auf Olivers Wunsch. Das Skript hat bei der ersten
# Erprobung Prüfdaten in der Produktivinstallation hinterlassen (50 Belege je
# Lauf), während Benutzer und Stammdaten an der Passwortregel und an fest
# verdrahteten Feldnamen scheiterten. Bis das Thema neu aufgesetzt ist, darf es
# nirgends mehr laufen — auch nicht lokal, damit niemand aus Gewohnheit den
# falschen Befehl erwischt.
#
# WIEDER FREIGEBEN: STILLGELEGT auf False setzen.
STILLGELEGT = True

HINWEIS = """
Der Lasttest ist vorerst stillgelegt (29.08.2026).

Grund: Die erste Erprobung war nicht brauchbar — der Generator scheiterte an
der Passwortregel und an fest verdrahteten Stammdatenfeldern, und die Läufe
hinterließen Prüfdaten in echten Beständen.

Das Thema wird zu einem späteren Zeitpunkt neu aufgesetzt. Wer weiß, was er
tut: STILLGELEGT in dieser Datei auf False setzen, den Riegel in
lasttest/locustfile.py lösen und in docker-compose.lasttest.yml die Zeile
`profiles:` entfernen.
"""


def main():
    if STILLGELEGT:
        sys.exit(HINWEIS)

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
