# DeineZeit – Backup-Einrichtung reparieren
# Dieses Script behebt drei Probleme auf einmal:
#   1. Backup-Ordner anlegen
#   2. Aufgabenplaner-Task registrieren
#   3. Einstellungen in der WebApp aktualisieren (falls sie gerade läuft)
#
# AUSFÜHREN ALS ADMINISTRATOR (Rechtsklick → Als Administrator ausführen)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  DeineZeit - Backup-Einrichtung reparieren" -ForegroundColor Cyan
Write-Host ""

# ── Admin-Check ───────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "  FEHLER: Bitte als Administrator ausfuehren!" -ForegroundColor Red
    Write-Host "  Rechtsklick auf backup-reparieren.bat → Als Administrator ausfuehren" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# ── Konfiguration laden ───────────────────────────────────────────────────────
$configFile   = Join-Path $PSScriptRoot "backup.cfg"
$backupScript = Join-Path $PSScriptRoot "backup.ps1"

if (-not (Test-Path $configFile)) {
    Write-Host "  FEHLER: backup.cfg nicht gefunden." -ForegroundColor Red
    pause
    exit 1
}

$config = @{}
Get-Content $configFile | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") { $config[$matches[1].Trim()] = $matches[2].Trim() }
}

$backupDir = $config["BACKUP_DIR"]
$keepDays  = if ($config["KEEP_DAYS"]) { $config["KEEP_DAYS"] } else { "30" }

if (-not $backupDir) {
    Write-Host "  FEHLER: BACKUP_DIR nicht in backup.cfg gefunden." -ForegroundColor Red
    pause
    exit 1
}

Write-Host "  Konfiguration: $backupDir" -ForegroundColor Gray
Write-Host ""

# ── 1. Backup-Ordner anlegen ─────────────────────────────────────────────────
Write-Host "  [1/3] Backup-Ordner anlegen..." -NoNewline
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Write-Host " Erstellt" -ForegroundColor Green
    Write-Host "        $backupDir" -ForegroundColor Gray
} else {
    Write-Host " Bereits vorhanden" -ForegroundColor Green
    Write-Host "        $backupDir" -ForegroundColor Gray
}

# ── 2. Aufgabenplaner-Task registrieren ───────────────────────────────────────
Write-Host "  [2/3] Aufgabenplaner-Task registrieren..." -NoNewline

$taskName = "DeineZeit-Backup"
$argument = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$backupScript`" -Silent"

# Uhrzeit aus backup.cfg oder Standard 02:00
$scheduleTime = if ($config["BACKUP_SCHEDULE_TIME"]) { $config["BACKUP_SCHEDULE_TIME"] } else { "02:00" }
$timeParts = $scheduleTime -split ":"
$hour   = [int]$timeParts[0]
$minute = if ($timeParts.Count -gt 1) { [int]$timeParts[1] } else { 0 }
$timeStr = "$($hour.ToString('00')):$($minute.ToString('00'))"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument
$trigger  = New-ScheduledTaskTrigger -Daily -At $timeStr
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

$result = Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Description "Automatisches DeineZeit Datenbank-Backup" `
    -RunLevel    Highest `
    -Force 2>&1

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host " OK" -ForegroundColor Green
    Write-Host "        Laeuft taeglich um $timeStr Uhr" -ForegroundColor Gray
} else {
    Write-Host " FEHLER" -ForegroundColor Red
    Write-Host "        $result" -ForegroundColor Red
}

# ── 3. WebApp-Einstellungen aktualisieren (falls App läuft) ───────────────────
Write-Host "  [3/3] WebApp-Einstellungen aktualisieren..." -NoNewline
try {
    $body = '{"backup_dir":"' + $backupDir.Replace('\','\\') + '","backup_schedule_time":"' + $timeStr + '","backup_keep_days":"' + $keepDays + '"}'
    Invoke-WebRequest -Uri "http://localhost/api/settings" -Method PUT -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Host " OK" -ForegroundColor Green
} catch {
    Write-Host " Uebersprungen (App nicht aktiv – wird beim naechsten Start geladen)" -ForegroundColor Yellow
}

# ── Zusammenfassung ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ──────────────────────────────────────────────" -ForegroundColor Gray
Write-Host "  Reparatur abgeschlossen!" -ForegroundColor Green
Write-Host ""
Write-Host "    Backup-Ordner  : $backupDir" -ForegroundColor Gray
Write-Host "    Aufbewahrung   : $keepDays Tage" -ForegroundColor Gray
Write-Host "    Automatisch    : taeglich um $timeStr Uhr" -ForegroundColor Gray
Write-Host ""
Write-Host "  Naechster Schritt: backup.bat ausfuehren um das erste Backup zu erstellen." -ForegroundColor Cyan
Write-Host ""
pause
