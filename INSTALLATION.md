# DeineZeit – Installationsanleitung

---

## ⚡ Schnellinstallation (empfohlen)

Auf einem frischen Linux-Server reicht **ein einziger Befehl**:

```bash
curl -fsSL https://raw.githubusercontent.com/waehnero/deinezeit/main/install.sh | sudo bash
```

Das Skript fragt Sie dann interaktiv nach:
- Ihrer **Domain** (z.B. `deinezeit.firma.at`)
- Ihrer **E-Mail-Adresse** (für das SSL-Zertifikat)
- Dem **Namen und Passwort** des ersten Administrators

Alles andere — Docker, Code-Download, SSL-Zertifikat, Datenbank, erster Benutzer — wird vollautomatisch eingerichtet.

---

## Voraussetzungen

Auf Ihrem Linux-Server benötigen Sie:
- **Ubuntu 22.04 oder Debian 12** (empfohlen)
- Eine **Domain** (z.B. deinezeit.firma.at) die bereits auf den Server zeigt
- Port **80** und **443** müssen offen sein
- Mindestens **1 GB RAM** und **10 GB Speicher**

---

## Manuelle Installation (Schritt für Schritt)

Falls Sie die Installation lieber manuell durchführen möchten:

## Schritt 1: Docker installieren (einmalig)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Nach diesem Befehl kurz ab- und wieder einloggen.

---

## Schritt 2: Programm herunterladen

```bash
git clone https://github.com/waehnero/deinezeit.git
cd deinezeit
```

---

## Schritt 3: Einstellungen anpassen

```bash
cp .env.example .env
nano .env
```

Folgende Werte anpassen:
- `DB_PASSWORD` → Sicheres Datenbankpasswort wählen
- `SECRET_KEY` → Zufälligen langen Text eingeben (mind. 32 Zeichen)
- `FRONTEND_URL` → Ihre Domain (z.B. https://deinezeit.firma.at)
- `DOMAIN` → Ihre Domain (z.B. deinezeit.firma.at)

Auch in `nginx/conf.d/app.conf` die Domain anpassen:
```bash
sed -i 's/deine-domain.at/IHRE-DOMAIN.AT/g' nginx/conf.d/app.conf
```

---

## Schritt 4: SSL-Zertifikat holen (HTTPS)

```bash
# Zuerst nur HTTP starten
docker compose up -d nginx certbot

# Zertifikat anfordern
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --email ihre@email.at \
  --agree-tos \
  --no-eff-email \
  -d ihre-domain.at
```

### Automatische Erneuerung einrichten (wichtig!)

Ein Let's-Encrypt-Zertifikat gilt nur **90 Tage**. Läuft es ab, kommt niemand
mehr auf die Seite — der Browser zeigt statt der Anmeldung eine
Sicherheitswarnung. Dieser eine Befehl sorgt dafür, dass sich das Zertifikat
von selbst erneuert:

```bash
sudo bash scripts/install-ssl-timer.sh
```

Danach sichern **drei voneinander unabhängige Ebenen** das Zertifikat ab:

| Ebene | Was sie tut | Wenn sie ausfällt |
|-------|-------------|-------------------|
| certbot-Container | prüft alle 12 Stunden, nginx liest alle 6 Stunden neu ein | fängt der Timer ab |
| systemd-Timer am Server | prüft täglich, startet auch ausgefallene Container wieder | fängt die Anwendung ab |
| Anwendung | überwacht die Restlaufzeit, schreibt E-Mails an die Administratoren | — |

Den aktuellen Stand sehen Sie jederzeit in der Anwendung unter
**Einstellungen → System → HTTPS-Zertifikat**. Dort steht auch, ob die
automatische Erneuerung noch läuft.

Falls doch einmal etwas klemmt, repariert dieser Befehl alles auf einmal
(Zertifikat erneuern, ausgefallene Automatik starten, nginx neu einlesen
lassen):

```bash
sudo bash /opt/deinezeit/scripts/ssl-renew.sh
```

---

## Schritt 5: Programm starten

```bash
docker compose up -d
```

Datenbank-Tabellen automatisch anlegen:
```bash
docker compose exec backend alembic upgrade head
```

Ersten Admin-Benutzer anlegen:
```bash
docker compose exec backend python -c "
from app.db.base import SessionLocal
from app.services.auth_service import auth_service
db = SessionLocal()
auth_service.create_user(db, 'admin@firma.at', 'Administrator', 'IhrPasswort123!', role='admin')
print('Admin angelegt!')
"
```

---

## Schritt 6: Fertig!

Die App ist nun erreichbar unter: **https://ihre-domain.at**

---

## Updates einspielen

```bash
git pull
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

Das Skript erstellt automatisch ein Datenbank-Backup, führt Migrationen durch und startet die neue Version.

---

## Häufige Befehle

```bash
# Status prüfen
docker compose ps

# Logs anzeigen
docker compose logs -f backend

# Neustart
docker compose restart

# Alles stoppen
docker compose down
```

---

## GitHub Actions: Automatisches Deployment einrichten

Wenn du möchtest, dass nach jedem `git push` automatisch deployed wird:

**Schritt 1: SSH-Schlüssel für den Server erstellen** (einmalig, auf deinem PC)

```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/deinezeit_deploy
# Öffentlichen Schlüssel auf den Server kopieren:
ssh-copy-id -i ~/.ssh/deinezeit_deploy.pub root@DEIN-SERVER
```

**Schritt 2: Secrets in GitHub hinterlegen**

Gehe zu: `https://github.com/waehnero/deinezeit` → Settings → Secrets and variables → Actions

| Secret-Name       | Wert                                      |
|-------------------|-------------------------------------------|
| `SSH_HOST`        | IP-Adresse oder Domain deines Servers     |
| `SSH_USER`        | Linux-Benutzer (z.B. `root`)             |
| `SSH_PRIVATE_KEY` | Inhalt von `~/.ssh/deinezeit_deploy`      |
| `DEPLOY_PATH`     | Installationspfad (z.B. `/opt/deinezeit`) |

**Schritt 3: Fertig!**

Ab jetzt wird bei jedem `git push` auf den `main`-Branch:
1. ✅ Sicherheitsprüfung ausgeführt (pip-audit, bandit, Secret-Check)
2. 🔨 Docker-Images gebaut und getestet
3. 🚀 Automatisch auf deinen Server deployed

Du siehst den Status unter: `https://github.com/waehnero/deinezeit/actions`
