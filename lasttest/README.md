# Lasttest — VORERST STILLGELEGT (29.08.2026)

> **Diese Anleitung ist außer Kraft.** Der Lasttest ist auf Olivers Wunsch
> stillgelegt, weil die erste Erprobung nicht überzeugte:
>
> * Der Prüfdaten-Generator scheiterte an der Passwortregel (das Passwort
>   enthielt einen Teil des Kontonamens) und an fest verdrahteten
>   Stammdatenfeldern, die es so nicht in jeder Installation gibt.
> * Beide Läufe hinterließen je 50 Belege in einer **Produktivinstallation**.
>   Die Warnung des Skripts greift nicht, wenn man es auf dem Server selbst
>   aufruft — von dort aus ist die Adresse `localhost`.
>
> Das Thema wird zu einem späteren Zeitpunkt neu aufgesetzt. Bis dahin sind
> drei Riegel gesetzt: `profiles:` in `docker-compose.lasttest.yml`,
> `STILLGELEGT` in `pruefdaten.py` und in `locustfile.py`. Der Reiter in den
> Einstellungen ist ausgegraut.
>
> Der folgende Text beschreibt den Stand vor der Stilllegung und bleibt als
> Ausgangspunkt für die Neufassung stehen.

---

Antwortet DeineZeit noch brauchbar, wenn 5, 10, 20 oder 100 Leute gleichzeitig
arbeiten? Diese Messung beantwortet das mit Zahlen statt mit Gefühl.

Gemessen wird über nginx, also auf demselben Weg, den auch ein Benutzer nimmt.

---

## Einmal vorbereiten

**1. Bremse für den Messlauf abschalten.** Ein Lasttest kommt von *einer*
Adresse. Die Anfragebremse würde nach 200 Anfragen je Minute abriegeln — dann
misst man die Bremse und nicht die Anwendung. In die `.env`:

```
RATE_LIMIT_AKTIV=false
```

Danach `docker compose -f docker-compose.local.yml up -d backend`. Im Log muss
die Warnung stehen, dass die Bremse aus ist. **Nach der Messung wieder auf
`true` setzen.**

**2. Prüfdaten anlegen.** Ohne Bestand misst man leere Listen:

```bash
python3 lasttest/pruefdaten.py --admin DEINE-ADMIN-MAIL
```

Das Passwort wird abgefragt. Es gehört bewusst nicht auf die Kommandozeile —
dort landet es in der Shell-History, und ein `!` im Passwort löst in zsh eine
History-Expansion aus: Das Passwort kommt still verändert an, und der Fehlschlag
sieht aus wie falsche Zugangsdaten.

Das legt 100 Testbenutzer (`lasttest001@pruefung.local` …), 200 Kontakte,
30 Projekte und 50 Belege an. Alles trägt „Lasttest" im Namen und lässt sich
darüber wiederfinden. Aufgeräumt wird **nicht** automatisch — ein Löschlauf
über Namensmuster wäre in einer Datenbank mit echten Daten zu gefährlich.

> Das Konto für den Aufruf darf keine Zwei-Faktor-Anmeldung haben, sonst
> kommt das Skript nicht durch.

---

## Messen

```bash
docker compose -f docker-compose.local.yml up -d      # Anwendung
docker compose -f docker-compose.lasttest.yml up      # Messwerkzeug
```

Dann http://localhost:8089 öffnen und eintragen:

| Feld | Bedeutung | Werte für die Reihe |
|---|---|---|
| Number of users | gleichzeitige Benutzer | 5, dann 10, 20, 100 |
| Ramp up | wie schnell sie dazukommen | 1 pro Sekunde |

Je Stufe **mindestens drei Minuten** laufen lassen. Die ersten Sekunden sind
nicht aussagekräftig: Verbindungen werden aufgebaut, Zwischenspeicher füllen
sich. Zwischen den Stufen neu starten, damit die Zahlen sauber getrennt sind.

### Was notieren

Aus dem Reiter *Statistics*, je Stufe:

- **Median** und **95 %** der Antwortzeit (die 95 % sind die interessante
  Zahl — sie beschreibt, was der unglücklichste Benutzer erlebt)
- **Failures** (jeder Fehler zählt, auch 429 und 500)
- **RPS** — Anfragen pro Sekunde insgesamt

Getrennt ansehen lohnt sich bei `PDF erzeugen`: Der Vorgang ist um
Größenordnungen teurer als alles andere und zieht jeden Durchschnitt nach oben.

### Anhaltspunkte

| Antwortzeit (95 %) | Einschätzung |
|---|---|
| unter 300 ms | flüssig, keine Beschwerden |
| 300 – 1000 ms | spürbar, aber arbeitsfähig |
| über 1 s | zäh; über 3 s hält das niemand aus |

Fehler sind wichtiger als Zeiten: Eine langsame Anwendung ist ärgerlich, eine
fehlerhafte kostet Daten.

---

## Danach

1. `RATE_LIMIT_AKTIV` in der `.env` wieder auf `true`, Backend neu starten.
2. Prüfdaten aufräumen, wenn die Umgebung weiterverwendet wird (Suche nach
   „Lasttest" in Stammdaten, Belegen und Benutzern).

Die Ergebnisse gehören in `docs/systemvoraussetzungen.md` — dort steht, welche
Maschine für wie viele Benutzer reicht.
