Write-Host ""
Write-Host "  DeineZeit - Frontend & Backend neu bauen" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

if (-not (Test-Path ".env.local")) {
    Write-Host "  FEHLER: .env.local nicht gefunden!" -ForegroundColor Red
    Read-Host "  Enter zum Beenden"
    exit 1
}
Copy-Item ".env.local" ".env" -Force

Write-Host "  Stoppe laufende Container..." -ForegroundColor Yellow
docker compose -f docker-compose.local.yml down

Write-Host "  Baue Frontend neu (ohne Cache)..." -ForegroundColor Yellow
docker compose -f docker-compose.local.yml build --no-cache frontend

Write-Host "  Baue Backend neu..." -ForegroundColor Yellow
docker compose -f docker-compose.local.yml build --no-cache backend

Write-Host "  Starte Container..." -ForegroundColor Yellow
docker compose -f docker-compose.local.yml up -d

Write-Host ""
Write-Host "  Warte bis Datenbank bereit ist..." -NoNewline
do {
    Start-Sleep -Seconds 2
    $ready = docker compose -f docker-compose.local.yml exec -T db pg_isready -U deinezeit 2>&1
} while ($LASTEXITCODE -ne 0)
Write-Host " OK" -ForegroundColor Green

Write-Host "  Datenbank-Migration..." -NoNewline
docker compose -f docker-compose.local.yml exec -T backend alembic upgrade head 2>&1 | Out-Null
Write-Host " OK" -ForegroundColor Green

Write-Host ""
Write-Host "  Warte bis Webseite erreichbar ist..." -NoNewline
do {
    Start-Sleep -Seconds 2
    try {
        Invoke-WebRequest -Uri "http://localhost" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null
        $ready = $true
    } catch {
        $ready = $false
    }
} while (-not $ready)
Write-Host " OK" -ForegroundColor Green

Write-Host ""
Write-Host "  Fertig! DeineZeit laeuft unter http://localhost" -ForegroundColor Green
Write-Host ""
Write-Host "  Naechster Schritt: migriere-kontakte.bat ausfuehren" -ForegroundColor Yellow
Write-Host ""
Read-Host "  Enter zum Beenden"
