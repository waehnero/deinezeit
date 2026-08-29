#!/usr/bin/env python3
"""
Prüfdaten des Lasttests wieder entfernen
========================================

Die Läufe vom 29.08.2026 haben in der Produktivinstallation Belege
hinterlassen. Dieses Skript räumt auf — und zwar **nur** das, was eindeutig
vom Lasttest stammt.

Zwei Durchgänge, wie beim Import: Ohne ``--loeschen`` wird nichts angefasst,
sondern nur aufgelistet, was gefunden wurde. Erst mit ``--loeschen`` und einer
getippten Bestätigung wird gelöscht. In einer Datenbank mit echten Daten ist
ein Löschlauf ohne vorherige Sicht schlicht zu gefährlich.

    python3 lasttest/aufraeumen.py --admin office@example.at
    python3 lasttest/aufraeumen.py --admin office@example.at --loeschen

Erkannt wird ausschließlich nach diesen Mustern:

    Belege        Titel beginnt mit „Lasttest Beleg"
    Stammdaten    Anzeigename beginnt mit „Lasttest Kunde"/„Lasttest Projekt"
    Benutzer      E-Mail wie lasttest001@pruefung.local

Alles andere bleibt unberührt. Ausgestellte Belege lassen sich ohnehin nicht
löschen — falls einer dabei ist, meldet das Skript ihn und lässt ihn stehen.
"""
import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request

BELEG_MUSTER = "Lasttest Beleg"
SATZ_MUSTER = ("Lasttest Kunde", "Lasttest Projekt")
BENUTZER_MUSTER = re.compile(r"^lasttest\d{3}@pruefung\.local$")
STAMMDATEN_TYPEN = ("kontakte", "projektzeiten")


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
        return fehler.code, fehler.read().decode()[:300]


def anmelden(basis, email, passwort):
    status, antwort = ruf(basis, "/api/auth/login",
                          daten={"email": email, "password": passwort})
    if status != 200 or not isinstance(antwort, dict) or not antwort.get("access_token"):
        sys.exit(f"Anmeldung fehlgeschlagen ({status}): {antwort}")
    return antwort["access_token"]


# ── Suchen ───────────────────────────────────────────────────────────────────

def belege_finden(basis, token):
    status, liste = ruf(basis, "/api/invoices", token)
    if status != 200 or not isinstance(liste, list):
        print(f"  Belege: konnten nicht gelesen werden ({status})")
        return []
    return [b for b in liste
            if str(b.get("title") or "").startswith(BELEG_MUSTER)]


def saetze_finden(basis, token):
    gefunden = []
    for slug in STAMMDATEN_TYPEN:
        status, antwort = ruf(
            basis, f"/api/masterdata/types/{slug}/records?search=Lasttest"
                   f"&page_size=500", token)
        if status != 200 or not isinstance(antwort, dict):
            continue
        for satz in antwort.get("items", []):
            name = str(satz.get("display_name") or "")
            if name.startswith(SATZ_MUSTER):
                gefunden.append((slug, satz))
    return gefunden


def benutzer_finden(basis, token):
    status, liste = ruf(basis, "/api/users/", token)
    if status != 200 or not isinstance(liste, list):
        print(f"  Benutzer: konnten nicht gelesen werden ({status})")
        return []
    return [b for b in liste
            if BENUTZER_MUSTER.match(str(b.get("email") or ""))]


# ── Löschen ──────────────────────────────────────────────────────────────────

def loeschen(basis, token, pfade, was):
    weg, blieb = 0, []
    for pfad, bezeichnung in pfade:
        status, antwort = ruf(basis, pfad, token, methode="DELETE")
        if status in (200, 204):
            weg += 1
        else:
            blieb.append((bezeichnung, status, antwort))
    print(f"  {was}: {weg} gelöscht"
          + (f", {len(blieb)} nicht löschbar" if blieb else ""))
    for bezeichnung, status, antwort in blieb[:5]:
        grund = antwort if isinstance(antwort, str) else json.dumps(antwort)
        print(f"      {bezeichnung}: {status} {grund[:120]}")


def main():
    p = argparse.ArgumentParser(
        description="Prüfdaten des Lasttests finden und entfernen")
    p.add_argument("--basis", default="http://localhost")
    p.add_argument("--admin", required=True, help="E-Mail eines Administrators")
    p.add_argument("--loeschen", action="store_true",
                   help="Wirklich löschen (ohne dieses Kennzeichen wird nur gezeigt)")
    args = p.parse_args()

    passwort = os.environ.get("DZ_ADMIN_PASSWORT") or getpass.getpass(
        f"Passwort für {args.admin}: ")
    basis = args.basis.rstrip("/")
    token = anmelden(basis, args.admin, passwort)

    print(f"\nSuche Lasttest-Daten in {basis} …\n")
    belege = belege_finden(basis, token)
    saetze = saetze_finden(basis, token)
    benutzer = benutzer_finden(basis, token)

    print(f"  Belege:     {len(belege)}")
    for b in belege[:5]:
        print(f"      {b.get('number') or 'Entwurf'} — {b.get('title')}")
    if len(belege) > 5:
        print(f"      … und {len(belege) - 5} weitere")
    print(f"  Stammdaten: {len(saetze)}")
    print(f"  Benutzer:   {len(benutzer)}")

    if not (belege or saetze or benutzer):
        print("\nNichts gefunden — es ist bereits alles aufgeräumt.")
        return

    if not args.loeschen:
        print("\nEs wurde NICHTS gelöscht. Zum Aufräumen denselben Aufruf mit "
              "--loeschen wiederholen.")
        return

    print(f"\nAchtung: {len(belege)} Belege, {len(saetze)} Stammdatensätze und "
          f"{len(benutzer)} Benutzer werden endgültig gelöscht.")
    if input("Zum Bestätigen „loeschen“ eintippen: ").strip() != "loeschen":
        sys.exit("Abgebrochen — es wurde nichts verändert.")

    print()
    loeschen(basis, token,
             [(f"/api/invoices/{b['id']}", str(b.get('title'))) for b in belege],
             "Belege")
    loeschen(basis, token,
             [(f"/api/masterdata/types/{slug}/records/{s['id']}",
               str(s.get('display_name'))) for slug, s in saetze],
             "Stammdaten")
    loeschen(basis, token,
             [(f"/api/users/{b['id']}", str(b.get('email'))) for b in benutzer],
             "Benutzer")
    print("\nFertig. Zur Sicherheit denselben Aufruf ohne --loeschen "
          "wiederholen — dann muss „Nichts gefunden“ erscheinen.")


if __name__ == "__main__":
    main()
