# Facebook-Seite an die Postecke anbinden

Mit dieser Anleitung verbindest du deine Facebook-**Seite** mit der Postecke.
Danach kann DeineZeit Beiträge mit Fotos **direkt veröffentlichen** und
geplante Posts **automatisch** zur gewünschten Zeit posten.

> **Wichtig:** Das funktioniert nur für Facebook-**Seiten**, nicht für dein
> privates Profil (das verbietet Facebook technisch). Für das private Profil
> bleibt das assistierte Posten über das Teilen-Menü.
>
> **Kein App-Review nötig:** Solange deine Meta-App im *Entwicklermodus*
> bleibt und nur deine eigenen Seiten bespielt, verlangt Meta keine Prüfung.
> Genau so nutzen wir es.

Du brauchst am Ende **zwei Angaben** für das Postecke-Profil:
die **Seiten-ID** und einen **Page-Access-Token** (langlebig).

---

## Schritt 1: Meta-Entwicklerkonto anlegen (einmalig)

1. Öffne https://developers.facebook.com und melde dich mit deinem
   normalen Facebook-Konto an (dem Konto, das deine Seite verwaltet).
2. Klicke rechts oben auf **Loslegen** (bzw. „Get Started") und bestätige
   die Schritte (E-Mail bestätigen, Rolle „Entwickler" wählen).

## Schritt 2: App anlegen (einmalig)

1. Gehe zu **Meine Apps** → **App erstellen**.
2. Wähle als Anwendungsfall **Sonstiges** und als App-Typ **Business**.
3. Gib einen Namen ein, z. B. `DeineZeit Postecke`, und erstelle die App.
4. Die App bleibt im **Entwicklermodus** — nichts veröffentlichen,
   nichts zur Prüfung einreichen.

## Schritt 3: Page-Access-Token holen

Am einfachsten über den **Graph API Explorer**
(https://developers.facebook.com/tools/explorer):

1. Wähle rechts oben deine App (`DeineZeit Postecke`) aus.
2. Klicke auf **Nutzer-Token generieren** und ergänze diese Berechtigungen:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
3. Bestätige das Facebook-Fenster (deine Seite auswählen und zulassen).
4. **Wichtig beim Facebook-Bestätigungsfenster:** Es kommt ein Schritt, in dem
   du auswählst, auf **welche Seiten** die App zugreifen darf — dort deine
   Seite unbedingt **anhaken**. (Facebook zeigt diesen Dialog nur beim ersten
   Mal. Wurde die Seite vergessen: facebook.com → Einstellungen →
   **Geschäftsintegrationen** → die App entfernen → Token neu generieren,
   dann erscheint der Dialog wieder.)

## Schritt 4: Seiten-Token und Seiten-ID in einem Rutsch holen

Der zuverlässigste Weg (erprobt):

1. Im Graph API Explorer oben in die Abfragezeile eintragen: `me/accounts`
   → **Senden**.
2. In der Antwort erscheint deine Seite mit diesen Feldern:
   - **`access_token`** → das ist der **Page-Access-Token** (kopieren!).
     Er stammt aus deiner Sitzung und läuft praktisch **nicht ab**.
   - **`id`** → das ist die richtige **Seiten-ID** (kopieren!).
     Achtung: NICHT die ID aus der Business-Manager-Adresszeile verwenden —
     die bezeichnet oft ein anderes Objekt.
3. Kommt bei `me/accounts` nur `"data": []` zurück, fehlt die Seiten-Freigabe
   aus Schritt 3.4 — dann wie dort beschrieben die Geschäftsintegration
   entfernen und den Token mit Seiten-Auswahl neu erzeugen.

> **Häufigster Fehler:** Der Token oben im Explorer-Feld ist ein
> **Nutzer**-Token — damit meldet Facebook beim Posten
> „(#200) Unpublished posts must be posted to a page as the page itself".
> Es muss der `access_token` **aus der `me/accounts`-Antwort** sein.

## Schritt 5: In DeineZeit hinterlegen

1. **Postecke** → Zahnrad (Profile verwalten) → dein Profil vom Typ
   **Facebook-Seite** bearbeiten (oder neu anlegen).
2. Im Kasten **Direktanbindung** die **Seiten-ID** und den **Page-Access-Token**
   eintragen → **Speichern**. (Die Daten werden verschlüsselt gespeichert und
   verlassen den Server nicht.)
3. Profil erneut öffnen und auf **Verbindung testen** klicken — es sollte
   „Verbunden mit Seite …" erscheinen.

## Fertig — so verhält sich die Postecke jetzt

- **Jetzt veröffentlichen:** Der Beitrag geht mit Text, Hashtags und allen
  Fotos (im eingestellten Bildformat/Filter des Profils) direkt auf die Seite.
- **Planen:** Der Post wird zur geplanten Zeit **automatisch** veröffentlicht
  (der Server prüft alle 2 Minuten). Klappt etwas nicht, siehst du die
  Fehlermeldung am Post in der Postecke — es wird automatisch erneut versucht.
- Das assistierte Posten bleibt für alle anderen Kanäle unverändert.
