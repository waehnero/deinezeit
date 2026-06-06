Write-Host ""
Write-Host "  DeineZeit - Migration: Kunden + Lieferanten -> Kontakte" -ForegroundColor Cyan
Write-Host "  Bitte stelle sicher, dass DeineZeit laeuft (start-lokal.bat)." -ForegroundColor Yellow
Write-Host ""

Set-Location $PSScriptRoot

$container = "deinezeit_backend"

try {
    # Pruefen ob Container laeuft
    $running = docker ps --filter "name=$container" --filter "status=running" -q
    if (-not $running) {
        Write-Host "  FEHLER: Container '$container' laeuft nicht." -ForegroundColor Red
        Write-Host "  Bitte zuerst start-lokal.bat ausfuehren." -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    Write-Host "  Starte Migration im Container '$container'..." -ForegroundColor White
    Write-Host ""

    docker exec $container python migrate_kontakte.py

    Write-Host ""
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Migration erfolgreich abgeschlossen!" -ForegroundColor Green
        Write-Host "  Bitte die Seite im Browser neu laden (F5)." -ForegroundColor Cyan
    } else {
        Write-Host "  Es gab einen Fehler bei der Migration (siehe Ausgabe oben)." -ForegroundColor Red
    }
} catch {
    Write-Host ""
    Write-Host "  Unerwarteter Fehler: $_" -ForegroundColor Red
} finally {
    Write-Host ""
    Read-Host "  Enter zum Beenden"
}
