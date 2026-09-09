Write-Host ""
Write-Host "  DeineZeit wird gestoppt..." -ForegroundColor Yellow
Write-Host ""

# Repo-Wurzel: dieses Skript liegt seit K-26 in scripts\windows\ (zwei Ebenen tiefer).
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

# Backup-Watcher stoppen
$pidFile = Join-Path $Root ".watcher-pid"
if (Test-Path $pidFile) {
    $watcherPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
    if ($watcherPid -gt 0) {
        Stop-Process -Id $watcherPid -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "  Backup-Watcher gestoppt." -ForegroundColor Gray
}

docker compose -f docker-compose.local.yml down

Write-Host ""
Write-Host "  DeineZeit wurde gestoppt." -ForegroundColor Green
Write-Host "  Daten bleiben erhalten und sind beim naechsten Start wieder da."
Write-Host ""
Write-Host "Druecken Sie Enter zum Beenden..."
Read-Host
