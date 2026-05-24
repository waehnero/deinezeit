# DeineZeit – Datenbank-Backup

param(
    [switch]$Silent   # Kein Pause am Ende (fuer automatischen Aufruf)
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  DeineZeit - Datenbank-Backup" -ForegroundColor Cyan
Write-Host ""

# ── Konfiguration laden ───────────────────────────────────────────────────────
$configFile = Join-Path $PSScriptRoot "backup.cfg"
if (-not (Test-Path $configFile)) {
    Write-Host "  FEHLER: Backup noch nicht eingerichtet." -ForegroundColor Red
    Write-Host "  Bitte zuerst backup-einrichten.bat ausfuehren." -ForegroundColor Yellow
    exit 1
}

$config = @{}
Get-Content $configFile | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") {
        $config[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$backupDir = $config["BACKUP_DIR"]
if ($config["KEEP_DAYS"]) { $keepDays = [int]$config["KEEP_DAYS"] } else { $keepDays = 30 }
$container = "deinezeit_db"
$dbUser    = "deinezeit"
$dbName    = "deinezeit"

if (-not $backupDir) {
    Write-Host "  FEHLER: BACKUP_DIR nicht in backup.cfg gefunden." -ForegroundColor Red
    exit 1
}

# ── Backup-Ordner sicherstellen ───────────────────────────────────────────────
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

# ── Container prüfen ─────────────────────────────────────────────────────────
Write-Host "  Pruefe Docker-Container..." -NoNewline
$running = docker ps --filter "name=$container" --filter "status=running" -q 2>&1
if (-not $running) {
    Write-Host " FEHLER" -ForegroundColor Red
    Write-Host "  Container '$container' laeuft nicht." -ForegroundColor Red
    Write-Host "  Bitte zuerst start-lokal.bat ausfuehren." -ForegroundColor Yellow
    exit 1
}
Write-Host " OK" -ForegroundColor Green

# ── Backup erstellen ──────────────────────────────────────────────────────────
$timestamp  = Get-Date -Format "yyyy-MM-dd_HH-mm"
$backupFile = Join-Path $backupDir "deinezeit_backup_$timestamp.sql"

Write-Host "  Erstelle Backup..." -NoNewline
docker exec $container pg_dump -U $dbUser $dbName | Out-File -FilePath $backupFile -Encoding utf8

$fileOk = (Test-Path $backupFile) -and ((Get-Item $backupFile).Length -gt 100)
if (-not $fileOk) {
    Write-Host " FEHLER" -ForegroundColor Red
    Write-Host "  Backup-Datei fehlt oder ist leer." -ForegroundColor Red
    if (Test-Path $backupFile) { Remove-Item $backupFile }
    exit 1
}

$sizeMB = [math]::Round((Get-Item $backupFile).Length / 1MB, 2)
Write-Host " OK ($sizeMB MB)" -ForegroundColor Green
Write-Host "  Gespeichert: $backupFile" -ForegroundColor Gray

# ── Alte Backups löschen ──────────────────────────────────────────────────────
$cutoff = (Get-Date).AddDays(-$keepDays)
$old = Get-ChildItem -Path $backupDir -Filter "deinezeit_backup_*.sql" |
       Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old.Count -gt 0) {
    $old | Remove-Item -Force
    Write-Host "  $($old.Count) altes Backup(s) geloescht (aelter als $keepDays Tage)" -ForegroundColor Gray
}

$total = (Get-ChildItem -Path $backupDir -Filter "deinezeit_backup_*.sql").Count
Write-Host ""
Write-Host "  Backup erfolgreich! Gesamt im Ordner: $total Datei(en)" -ForegroundColor Green

# Backup-Zeitstempel an WebApp melden (damit die Einstellungsseite aktuell bleibt)
try {
    Invoke-WebRequest -Uri "http://localhost/api/settings/backup-ping" -Method POST -UseBasicParsing -TimeoutSec 5 | Out-Null
} catch {
    # Kein Fehler ausgeben wenn WebApp nicht läuft
}
