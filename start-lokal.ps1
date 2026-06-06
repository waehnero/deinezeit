# DeineZeit - Lokaler Teststart
$Host.UI.RawUI.WindowTitle = "DeineZeit - Lokaler Test"

Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host "       DeineZeit - Lokaler Teststart" -ForegroundColor Cyan
Write-Host "  ====================================================" -ForegroundColor Cyan
Write-Host ""

# Pruefen ob Docker Desktop laeuft
Write-Host "  Pruefe ob Docker Desktop laeuft..." -NoNewline
$dockerCheck = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " FEHLER!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Docker Desktop ist nicht gestartet!" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Bitte:"
    Write-Host "    1. Docker Desktop oeffnen (im Startmenue suchen)"
    Write-Host "    2. Warten bis das Symbol in der Taskleiste erscheint"
    Write-Host "    3. Dieses Skript nochmal starten"
    Write-Host ""
    Read-Host "  Druecken Sie Enter zum Beenden"
    exit 1
}
Write-Host " OK" -ForegroundColor Green

# In den Projektordner wechseln
Set-Location $PSScriptRoot

# .env.local verwenden
if (-not (Test-Path ".env.local")) {
    Write-Host "  FEHLER: .env.local nicht gefunden!" -ForegroundColor Red
    Read-Host "  Druecken Sie Enter zum Beenden"
    exit 1
}
Copy-Item ".env.local" ".env" -Force
Write-Host "  OK: Konfiguration geladen" -ForegroundColor Green

# Container bauen und starten
Write-Host ""
Write-Host "  Container werden gestartet (beim ersten Mal: ca. 3-5 Minuten)..." -ForegroundColor Yellow
Write-Host "  (Bitte warten - der Fortschritt erscheint unten)"
Write-Host ""

docker compose -f docker-compose.local.yml up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  FEHLER: Container konnten nicht gestartet werden." -ForegroundColor Red
    Write-Host "  Bitte stopp-lokal.bat ausfuehren und dann erneut versuchen."
    Read-Host "  Druecken Sie Enter zum Beenden"
    exit 1
}

# Warten bis Datenbank bereit ist
Write-Host ""
Write-Host "  Warte bis die Datenbank bereit ist..." -NoNewline
do {
    Start-Sleep -Seconds 2
    $dbReady = docker compose -f docker-compose.local.yml exec -T db pg_isready -U deinezeit 2>&1
} while ($LASTEXITCODE -ne 0)
Write-Host " OK" -ForegroundColor Green

# Datenbank-Tabellen anlegen
Write-Host "  Datenbank wird eingerichtet..." -NoNewline
docker compose -f docker-compose.local.yml exec -T backend alembic upgrade head 2>&1 | Out-Null
Write-Host " OK" -ForegroundColor Green

# Admin-Benutzer pruefen und anlegen
Write-Host "  Pruefe Admin-Benutzer..." -NoNewline
$checkUser = docker compose -f docker-compose.local.yml exec -T backend python3 -c "import sys; sys.path.insert(0,'/app'); from app.db.base import SessionLocal; from app.services.auth_service import auth_service; db=SessionLocal(); u=auth_service.get_user_by_email(db,'admin@deinezeit.local'); print('EXISTS' if u else 'NEW')" 2>&1

if ($checkUser -match "NEW") {
    Write-Host ""
    Write-Host "  Lege ersten Administrator an..." -NoNewline
    docker compose -f docker-compose.local.yml exec -T backend python3 -c "import sys; sys.path.insert(0,'/app'); from app.db.base import SessionLocal; from app.services.auth_service import auth_service; db=SessionLocal(); auth_service.create_user(db,'admin@deinezeit.local','Administrator','Admin1234!',role='admin',language='de'); print('OK')" 2>&1 | Out-Null
    Write-Host " OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "  --------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  Erste Login-Daten:" -ForegroundColor Yellow
    Write-Host "    E-Mail:    admin@deinezeit.local" -ForegroundColor Yellow
    Write-Host "    Passwort:  Admin1234!" -ForegroundColor Yellow
    Write-Host "  (Bitte nach dem ersten Login aendern!)" -ForegroundColor Yellow
    Write-Host "  --------------------------------------------------" -ForegroundColor Yellow
} else {
    Write-Host " OK (bereits vorhanden)" -ForegroundColor Green
}

# Warten bis nginx bereit ist
Write-Host ""
Write-Host "  Warte bis die Weboberflaeche erreichbar ist..." -NoNewline
do {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -Uri "http://localhost" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $ready = $true
    } catch {
        $ready = $false
    }
} while (-not $ready)
Write-Host " OK" -ForegroundColor Green

# Fertig!
Write-Host ""
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host "    DeineZeit laeuft unter: http://localhost" -ForegroundColor Green
Write-Host "    Browser wird geoeffnet..." -ForegroundColor Green
Write-Host "  ====================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 2
Start-Process "http://localhost"


Write-Host "  Zum Beenden: stopp-lokal.bat doppelklicken"
Write-Host "  (Dieses Fenster kann minimiert werden)"
Write-Host ""
Read-Host "  Druecken Sie Enter zum Beenden"
