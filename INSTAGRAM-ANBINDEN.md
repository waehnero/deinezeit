# Instagram an die Postecke anbinden

Mit dieser Anleitung verbindest du dein **Instagram-Professionell-Konto** mit der
Postecke. Danach kann DeineZeit Beiträge **direkt veröffentlichen** und geplante
Posts **automatisch** zur gewünschten Zeit posten – als einzelnes Foto, als
Foto-Serie (Carousel) oder als Reel (Video).

> **Wichtig:** Das funktioniert nur mit einem **Professionell-Konto** (Business
> oder Creator), das mit einer **Facebook-Seite** verknüpft ist. Ein normales
> privates Instagram-Konto lässt sich technisch nicht automatisch bespielen.
>
> **Kein App-Review nötig:** Es reicht dieselbe Meta-App im *Entwicklermodus*,
> die du schon für die Facebook-Seite nutzt – solange du nur dein eigenes Konto
> bespielst.

Du brauchst am Ende **zwei Angaben** für das Postecke-Profil:
die **Instagram-Konto-ID** und einen **Access-Token**.

---

## Schritt 1: Instagram auf „Professionell" umstellen (einmalig)

1. Öffne die Instagram-App → **Einstellungen** → **Konto** →
   **Zu Professionell-Konto wechseln** (Business oder Creator).
2. Folge den Schritten bis zum Ende.

## Schritt 2: Mit einer Facebook-Seite verknüpfen (einmalig)

1. Öffne deine **Facebook-Seite** → **Einstellungen** → **Verknüpfte Konten**
   (bzw. **Instagram**).
2. Verknüpfe dort dein Instagram-Professionell-Konto mit der Seite.

> Ohne diese Verknüpfung findet die Graph API dein Instagram-Konto nicht.

## Schritt 3: Meta-App verwenden (dieselbe wie bei der Facebook-Seite)

Du brauchst **keine neue App**. Verwende die App `DeineZeit Postecke` aus der
Anleitung `FACEBOOK-SEITE-ANBINDEN.md`. Sie bleibt im **Entwicklermodus**.

## Schritt 4: Access-Token mit den richtigen Berechtigungen holen

Am einfachsten über den **Graph API Explorer**
(https://developers.facebook.com/tools/explorer):

1. Wähle rechts oben deine App (`DeineZeit Postecke`) aus.
2. Klicke auf **Nutzer-Token generieren** und ergänze diese Berechtigungen:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
3. Bestätige das Facebook-Fenster (deine Seite auswählen und zulassen).
4. Kopiere den erzeugten **Access-Token**.

## Schritt 5: Instagram-Konto-ID herausfinden

Im Graph API Explorer nacheinander abfragen:

1. `me/accounts` → **Senden**. Kopiere die **`id`** deiner Facebook-Seite.
2. `<Seiten-ID>?fields=instagram_business_account` → **Senden**.
   In der Antwort steht:
   ```json
   { "instagram_business_account": { "id": "17841400000000000" } }
   ```
   Diese **`id`** ist deine **Instagram-Konto-ID** (kopieren!).

> Kommt `instagram_business_account` nicht zurück, ist die Verknüpfung aus
> Schritt 2 nicht aktiv – dort noch einmal prüfen.

## Schritt 6: In DeineZeit hinterlegen

1. **Postecke** → Zahnrad (Profile verwalten) → Profil vom Typ **Instagram**
   anlegen oder bearbeiten.
2. Im Kasten **Direktanbindung** die **Instagram-Konto-ID** und den
   **Access-Token** eintragen → **Speichern**. (Verschlüsselt gespeichert, die
   Daten verlassen den Server nicht.)
3. Profil erneut öffnen → **Verbindung testen** → es sollte
   „Verbunden mit @deinname" erscheinen.

---

## Fertig — so verhält sich die Postecke jetzt

- **Ein Foto** → einzelner Instagram-Beitrag.
- **Mehrere Fotos** (2–10) → automatisch als **Carousel** (Foto-Serie).
- **Ein Video** → als **Reel** (Instagram verarbeitet es kurz, dann geht es live).
- **Jetzt veröffentlichen** oder **Planen** wie bei der Facebook-Seite; der
  Server prüft geplante Posts alle 2 Minuten. Fehlermeldungen erscheinen am Post.

> **Technischer Hinweis:** Instagram lädt Medien nicht direkt hoch, sondern holt
> sie von einer öffentlichen Adresse deines Servers ab. DeineZeit erzeugt dafür
> beim Veröffentlichen automatisch eine **kurzlebige, signierte Abruf-URL** –
> es ist keine zusätzliche Einrichtung nötig, der Server muss nur (wie ohnehin)
> aus dem Internet erreichbar sein.
