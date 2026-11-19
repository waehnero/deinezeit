# Prüfbericht – NGINX2Root: nginx-Lücken vom 18.11.2026

**Datum:** 19.11.2026 · **Anlass:** Warnung CERT.at / F5 zu fünf nginx-Lücken
(„NGINX2Root") · **Basis:** `main`, Version 2.1.3 · **Migration:** keine

---

## 1. Zusammenfassung

1. **Der Server ist nach der Konfiguration betroffen.** `nginx/conf.d/app.conf` schaltet
   HTTP/2 ein (`http2 on`) und leitet an Backend und Frontend weiter. Das sind genau die
   Voraussetzungen der beiden schwersten Lücken (CVE-2026-123007, CVE-2026-123633). Beide sind
   ohne Anmeldung aus dem Internet erreichbar.
2. **Die laufende nginx-Version am Server ist nicht belegt.** `image: nginx:alpine` ist ein
   loses Etikett; weder `docker compose build` noch `up -d --force-recreate` holen es neu.
   Der Server läuft daher mit dem Stand, der irgendwann zuerst geladen wurde — mit an
   Sicherheit grenzender Wahrscheinlichkeit unter 1.31.9. Aus dieser Sitzung war der Server
   nicht erreichbar; der Nachweis steht in der Abnahme-Checkliste (Punkt 6).
3. **Lokal (Mac) ist keine der fünf Lücken erreichbar** (nur Port 80, kein HTTP/2, kein
   HTTP/3, kein Mail-Proxy, kein `mirror`). Das Image wird trotzdem mit angehoben.
4. **Behebung:** nginx an allen drei Stellen fest auf `nginx:1.31.9-alpine`. Der nächste
   Deploy lädt dieses Image zwangsläufig (es liegt am Server noch nicht vor) und erstellt die
   Container neu. Ein neuer CI-Schritt verhindert den Rückfall.
5. **Zusatz am Server-Host:** Kernel-Modul `sctp` sperren. Die Forscher haben die nginx-Lücken
   mit einem noch ungepatchten Kernel-Fehler in SCTP verkettet und kamen so aus dem Container
   auf den Host. DeineZeit braucht SCTP nicht.

## 2. Die fünf Lücken gegen unsere Konfiguration

| CVE | Voraussetzung | Server (`app.conf`) | Lokal (`local.conf`) | Frontend-Container |
|---|---|---|---|---|
| CVE-2026-123007 | HTTP/2 | **betroffen** (`http2 on`) | nein (nur HTTP/1.1, Port 80) | nein |
| CVE-2026-123633 | HTTP/2 + Weiterleitung an Backend | **betroffen** | nein | nein |
| CVE-2026-123634 | `resolver` + `proxy_pass` mit Variable + `mirror` | nein — `resolver` und Variable ja, aber kein `mirror` | nein | nein |
| CVE-2026-121810 | HTTP/3 (QUIC) | nein — kein `listen … quic` | nein | nein |
| CVE-2026-113425 | nginx als Mail-Proxy | nein — kein `mail {}`-Block | nein | nein |

Betroffene Versionen: bis 1.30.6 (stable) bzw. 1.31.0–1.31.8 (mainline). Behoben in
**1.30.7** und **1.31.9**. F5 nennt für die HTTP/2-Lücken keinen Workaround; HTTP/2
abzuschalten nimmt die beiden HTTP/2-Lücken aus der Schusslinie, ist aber nur eine Notlösung.

Der Frontend-Container (nginx hinter dem Proxy, nur intern auf Port 80) ist von außen nicht
direkt erreichbar und erfüllt keine der Voraussetzungen. Er wird aus Gleichstandsgründen mit
angehoben.

## 3. Umfang

| Datei | Änderung |
|---|---|
| `docker-compose.yml` | `nginx:alpine` → `nginx:1.31.9-alpine` |
| `docker-compose.local.yml` | dito |
| `frontend/Dockerfile` | `FROM nginx:alpine` → `FROM nginx:1.31.9-alpine` |
| `.github/workflows/ci.yml` | neuer Schritt „nginx-Version fest und nicht verwundbar?" |
| `CLAUDE.md`, `STATUS.md` | Konvention und Logbuch |

**Bewusst nicht angefasst:** `nginx/nginx.conf`, `nginx/conf.d/*.conf` (HTTP/2 bleibt an —
mit 1.31.9 ist es nicht mehr nötig, es abzuschalten), `scripts/deploy.sh` (holt das feste
Image von selbst), certbot, Backend, Datenbank. Kein Anwendungscode geändert.

**Warum mainline (1.31.9) und nicht stable (1.30.7):** `nginx:alpine` war schon bisher der
mainline-Zweig; so bleibt der Sprung am kleinsten. Der CI-Schritt lässt stable derzeit nicht
zu (Mindestversion 1.31.9) — bei einem Wechsel müsste er angepasst werden.

## 4. Prüfungen

CI-Schritt lokal ausgeführt (aus `ci.yml` herausgelöst, `bash -e`):

```
aktueller Stand          ✓ nginx:1.31.9-alpine (mindestens 1.31.9)            rc=0
alle auf nginx:alpine    ✗ nginx ohne feste Versionsnummer: nginx:alpine      rc=1
alle auf 1.31.8-alpine   ✗ nginx 1.31.8 liegt unter der Mindestversion 1.31.9 rc=1
eine Datei abweichend    ✗ nginx-Versionen laufen auseinander                 rc=1
alle auf 1.31.10-alpine  ✓ nginx:1.31.10-alpine (mindestens 1.31.9)           rc=0
```

`ci.yml` und beide Compose-Dateien sind gültiges YAML (mit PyYAML geladen).

## 5. Nicht geprüft

- **Laufende Version am Server** — kein Zugriff aus der Sitzung (SSH, HTTPS gesperrt).
- **Ob `nginx:1.31.9-alpine` auf Docker Hub abrufbar ist** — Docker Hub war nicht erreichbar.
  Mehrere Berichte nennen die Tags 1.31.9 als am 18.11. veröffentlicht; die Alpine-Variante
  zeigt sich beim ersten `docker pull` (Abnahme Punkt 1).
- **Lokaler Build, `./test.sh`, Vitest** — Docker läuft nicht in der Sitzung.
- **Spuren eines Angriffs am Server.** Bisher ist keine Ausnutzung in freier Wildbahn
  gemeldet; für CVE-2026-123007 gibt es einen öffentlichen Beispiel-Exploit.

## 6. Risiko und Rückweg

| Risiko | Einschätzung | Rückweg |
|---|---|---|
| Tag `1.31.9-alpine` existiert nicht | gering; fiele schon lokal beim Pull auf, am Server bräche der Deploy vor dem Umschalten ab | Tag auf `1.31.9-alpine-slim` oder `mainline-alpine` prüfen |
| Verhalten ändert sich zwischen altem und neuem nginx | gering; `deploy.sh` prüft `nginx -t` vor dem Neustart | Version in den drei Dateien zurücksetzen (nur auf ≥ 1.31.9) |
| Feste Version veraltet künftig | sicher — das ist der Preis | bei der nächsten nginx-Meldung Nummer an drei Stellen + `min` in `ci.yml` anheben |

## 7. Abnahme-Checkliste

1. **Lokal am Mac:** `docker pull nginx:1.31.9-alpine` — Image wird gefunden.
2. **Lokal am Mac:** `docker compose -f docker-compose.local.yml up -d --build`, dann
   `docker compose -f docker-compose.local.yml exec nginx nginx -v` → `nginx/1.31.9`;
   dasselbe mit `exec frontend`.
3. **Lokal am Mac:** http://localhost öffnen, anmelden, eine Seite mit API-Zugriff laden.
4. **Lokal am Mac:** `./test.sh` grün.
5. Branch, PR, CI grün (inkl. neuem Schritt), Merge → Deploy.
6. **Am Server:** `docker compose exec nginx nginx -v` und
   `docker compose exec frontend nginx -v` → beide `nginx/1.31.9`.
7. **Am Server:** `lsmod | grep sctp` → keine Ausgabe; Datei
   `/etc/modprobe.d/disable-sctp.conf` vorhanden.
8. https://dz.wwinterface.online öffnen, anmelden — läuft, weiterhin über HTTP/2.

## Quellen

- CERT.at-Warnung: https://www.cert.at/de/warnungen/2026/11/kritische-sicherheitslucken-in-nginx-plus-und-nginx-open-source-updates-verfugbar
- CERT-EU Security Advisory 2026-022: https://cert.europa.eu/publications/security-advisories/2026-022/
- Help Net Security, 19.11.2026: https://www.helpnetsecurity.com/2026/11/19/nginx2root-nginx-vulnerabilities/
- nginx-Sicherheitshinweise: https://nginx.org/en/security_advisories.html
