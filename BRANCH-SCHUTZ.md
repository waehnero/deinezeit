# Branch-Schutz & Test-Workflow einrichten (GitHub)

> Ziel: Code kommt **nur über einen Pull Request** in `main`, und der PR lässt
> sich erst zusammenführen, wenn die automatischen Tests **grün** sind. So wird
> nichts mehr ungetestet deployed.
>
> Die folgenden Schritte sind **Einstellungen in GitHub** (Web-Oberfläche) und
> müssen einmalig von Oliver gemacht werden — sie lassen sich nicht im Code
> hinterlegen.

---

## Vorher: Was schon erledigt ist

- Der CI-Workflow (`.github/workflows/ci.yml`) hat jetzt einen Job
  **„Backend: Tests (pytest)"**. Er läuft bei jedem Push und jedem Pull Request
  und meldet rot/grün.
- Beim ersten Push, der diesen Workflow enthält, taucht der Check-Name in
  GitHub auf — den brauchst du in Schritt 2 unten.

---

## Schritt 1 – Neuer Arbeitsablauf (statt direkt auf `main`)

Ab jetzt **nicht mehr direkt auf `main`** committen, sondern:

```bash
git checkout -b feature/kurze-beschreibung   # neuer Branch
# ... entwickeln, lokal testen mit ./test.sh ...
git push -u origin feature/kurze-beschreibung
```

Dann auf GitHub einen **Pull Request** nach `main` öffnen. Die Tests laufen
automatisch am PR; mergen erst, wenn sie grün sind.

---

## Schritt 2 – Branch-Schutzregel für `main` aktivieren

1. GitHub öffnen: `https://github.com/waehnero/deinezeit`
2. **Settings** → links **Branches** → **Add branch ruleset**
   (oder klassisch: **Branch protection rules** → **Add rule**).
3. **Branch name pattern:** `main`
4. Folgende Optionen aktivieren:
   - ☑ **Require a pull request before merging**
     (verbietet direktes Pushen auf `main`)
   - ☑ **Require status checks to pass before merging**
     → in der Suche **`Backend: Tests (pytest)`** auswählen
     (optional zusätzlich: `Backend: Sicherheit & Abhängigkeiten`,
     `Docker-Images bauen`, `Konfiguration & Secrets`)
   - ☑ **Require branches to be up to date before merging** (empfohlen)
5. **Save / Create** klicken.

> Hinweis: Der Check-Name erscheint in der Auswahlliste erst, **nachdem** der
> Workflow mindestens einmal gelaufen ist (also nach dem ersten Push mit der
> neuen `ci.yml`).

---

## Schritt 3 (optional) – Deployment an grüne Tests koppeln

Aktuell startet `deploy.yml` bei jedem Push auf `main`, **ohne** auf die Tests
zu warten. Mit Branch-Schutz (Schritt 2) ist das meist schon ausreichend, weil
nur getesteter Code via PR nach `main` gelangt.

Wer zusätzlich absichern will, dass der Deploy nur nach grünen Tests läuft,
kann das später umsetzen (z. B. Deploy nur bei erfolgreichem CI-Workflow
auslösen). **Diese Änderung steht noch aus** und wird separat mit Oliver
abgestimmt, da sie den Deploy-Mechanismus betrifft.

---

## Ergebnis

- Direktes Pushen auf `main` ist gesperrt.
- Jede Änderung läuft über einen PR, an dem die Tests automatisch laufen.
- Merge nach `main` (und damit Deployment) ist erst möglich, wenn die Tests
  grün sind.
