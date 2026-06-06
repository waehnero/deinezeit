# DeineZeit – Lokal auf Windows testen

Diese Anleitung erklärt, wie Sie DeineZeit auf Ihrem Windows-Computer
ausprobieren können — ohne eigenen Server, ohne Domain, ohne Internet.

---

## Schritt 1: Docker Desktop installieren

Docker Desktop ist ein kostenloses Programm, das im Hintergrund ein
kleines Linux startet. DeineZeit läuft darin automatisch.

1. Öffnen Sie diese Seite im Browser:
   **https://www.docker.com/products/docker-desktop/**

2. Klicken Sie auf **„Download for Windows"**

3. Führen Sie die heruntergeladene Datei aus und folgen Sie der
   Installation (alle Voreinstellungen können so belassen werden)

4. Nach der Installation: Windows **neu starten** wenn gefragt

5. Docker Desktop öffnen — es erscheint ein Wal-Symbol in der Taskleiste

   > Beim ersten Start lädt Docker einige Dateien herunter — das dauert
   > je nach Internetverbindung 2–5 Minuten. Warten bis das Symbol
   > in der Taskleiste weiß/blau leuchtet (nicht mehr animiert).

---

## Schritt 2: DeineZeit starten

Sobald Docker Desktop läuft:

1. Öffnen Sie den Ordner mit dem Programm
   (dort wo diese Anleitung liegt)

2. Doppelklicken Sie auf **`start-lokal.bat`**

3. Ein schwarzes Fenster öffnet sich — das ist normal.
   Beim **ersten Start** werden alle notwendigen Dateien
   heruntergeladen und das Programm gebaut.
   **Das dauert 3–5 Minuten** — bitte warten.

4. Wenn alles fertig ist, öffnet sich der Browser automatisch
   und zeigt die Anmeldeseite von DeineZeit.

---

## Schritt 3: Einloggen

Beim ersten Start werden folgende Zugangsdaten automatisch angelegt:

| | |
|---|---|
| **E-Mail** | `admin@deinezeit.local` |
| **Passwort** | `Admin1234!` |

> Bitte das Passwort nach dem ersten Login unter **„Mein Profil"** ändern.

---

## Programm beenden

Wenn Sie fertig sind, doppelklicken Sie auf **`stopp-lokal.bat`**.

Ihre eingegebenen Daten bleiben gespeichert und sind
beim nächsten Start wieder da.

---

## Alles zurücksetzen

Falls Sie komplett neu starten möchten (alle Testdaten löschen):
Doppelklicken Sie auf **`reset-lokal.bat`**.

---

## Häufige Fragen

**„Docker Desktop ist nicht gestartet" — was tun?**
Öffnen Sie Docker Desktop über das Startmenü und warten Sie,
bis das Symbol in der Taskleiste erscheint. Dann nochmal
`start-lokal.bat` doppelklicken.

**Wie oft muss ich Docker Desktop starten?**
Docker Desktop startet normalerweise automatisch mit Windows.
Sie müssen nur `start-lokal.bat` doppelklicken.

**Beim zweiten Start geht es schnell?**
Ja — nur beim ersten Start werden alle Dateien aufgebaut.
Danach startet das Programm in etwa 30 Sekunden.

**Kann ich DeineZeit auch von einem anderen Gerät im Heimnetzwerk aufrufen?**
Ja — statt `http://localhost` die IP-Adresse Ihres Computers eingeben,
z.B. `http://192.168.1.100`. Die IP-Adresse finden Sie unter:
Windows-Taste → „cmd" → `ipconfig` → „IPv4-Adresse".

---

## Was kann ich testen?

Alles was in den Phasen 1–3 gebaut wurde:

- Einloggen mit E-Mail und Passwort
- 2FA (Zwei-Faktor) aktivieren mit Google Authenticator
- Kunden, Lieferanten und Projekte anlegen
- Eigene Stammdaten-Typen erstellen (z.B. „Mitarbeiter")
- Felder per Drag & Drop anordnen und Breite einstellen
- Daten als CSV exportieren und importieren
- Weitere Benutzer anlegen
- Sprache auf Englisch umschalten
