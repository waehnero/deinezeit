# DeineZeit – Backup einrichten

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  DeineZeit - Backup einrichten" -ForegroundColor Cyan
Write-Host ""

$configFile   = Join-Path $PSScriptRoot "backup.cfg"
$backupScript = Join-Path $PSScriptRoot "backup.ps1"

# ── Bestehende Konfiguration laden ────────────────────────────────────────────
$currentDir = ""
if (Test-Path $configFile) {
    Get-Content $configFile | ForEach-Object {
        if ($_ -match "^BACKUP_DIR=(.+)$") { $currentDir = $matches[1].Trim() }
    }
}

# ── Backup-Ordner abfragen ────────────────────────────────────────────────────
Write-Host "  Wo sollen die Backup-Dateien gespeichert werden?" -ForegroundColor White
Write-Host "  Beispiele:" -ForegroundColor Gray
Write-Host "    C:\Backups\DeineZeit" -ForegroundColor Gray
Write-Host "    C:\Users\Oliver\OneDrive\Backups\DeineZeit" -ForegroundColor Gray
Write-Host "    E:\Externe-Festplatte\DeineZeit-Backup" -ForegroundColor Gray
Write-Host ""

if ($currentDir -ne "") {
    Write-Host "  Aktueller Pfad: $currentDir" -ForegroundColor Yellow
    $inputDir = Read-Host "  Neuer Pfad (Enter = unveraendert lassen)"
    if ($inputDir.Trim() -eq "") { $backupDir = $currentDir } else { $backupDir = $inputDir.Trim() }
} else {
    $backupDir = ""
    while ($backupDir -eq "") {
        $backupDir = (Read-Host "  Backup-Ordner").Trim()
        if ($backupDir -eq "") { Write-Host "  Bitte einen Pfad eingeben." -ForegroundColor Yellow }
    }
}

# ── Ordner anlegen ────────────────────────────────────────────────────────────
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Write-Host "  Ordner erstellt: $backupDir" -ForegroundColor Green
} else {
    Write-Host "  Ordner gefunden: $backupDir" -ForegroundColor Green
}

# ── Konfiguration speichern ───────────────────────────────────────────────────
"BACKUP_DIR=$backupDir`nKEEP_DAYS=30" | Set-Content -Path $configFile -Encoding UTF8
Write-Host "  Konfiguration gespeichert (backup.cfg)" -ForegroundColor Green

# ── Uhrzeit abfragen ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Um wie viel Uhr soll das taegliche Backup laufen?" -ForegroundColor White
$timeInput = (Read-Host "  Uhrzeit HH:MM (Enter = 02:00)").Trim()
if ($timeInput -eq "") { $timeInput = "02:00" }

$timeParts = $timeInput -split ":"
$hour   = [int]$timeParts[0]
if ($timeParts.Count -gt 1) { $minute = [int]$timeParts[1] } else { $minute = 0 }
$timeStr = "$($hour.ToString('00')):$($minute.ToString('00'))"

# ── Aufgabenplaner registrieren ───────────────────────────────────────────────
Write-Host ""
Write-Host "  Registriere Windows-Aufgabenplaner Task..." -NoNewline

$taskName = "DeineZeit-Backup"
$argument = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$backupScript`" -Silent"

# Alten Task entfernen
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -Daily -At $timeStr
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

$result = Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Description "Automatisches DeineZeit Datenbank-Backup" `
    -RunLevel    Highest `
    -Force 2>&1

if ($LASTEXITCODE -eq 0 -or $result) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FEHLER" -ForegroundColor Red
    Write-Host "  $result" -ForegroundColor Red
    Write-Host "  Hinweis: Bitte als Administrator ausfuehren (Rechtsklick -> Als Administrator ausfuehren)" -ForegroundColor Yellow
    exit 1
}

# ── deinezeit:// URI-Scheme registrieren ─────────────────────────────────────
Write-Host "  Registriere deinezeit:// URI-Scheme..." -NoNewline
$vbsHandler = Join-Path $PSScriptRoot "backup-uri-handler.vbs"
$regPath    = "HKCU:\Software\Classes\deinezeit"
try {
    New-Item -Path $regPath -Force | Out-Null
    Set-ItemProperty -Path $regPath -Name "(Default)"      -Value "URL:DeineZeit Backup Protocol"
    Set-ItemProperty -Path $regPath -Name "URL Protocol"   -Value ""
    New-Item -Path "$regPath\DefaultIcon" -Force | Out-Null
    Set-ItemProperty -Path "$regPath\DefaultIcon" -Name "(Default)" -Value "wscript.exe,0"
    New-Item -Path "$regPath\shell\open\command" -Force | Out-Null
    Set-ItemProperty -Path "$regPath\shell\open\command" -Name "(Default)" `
        -Value "wscript.exe `"$vbsHandler`" `"%1`""
    Write-Host " OK" -ForegroundColor Green
} catch {
    Write-Host " FEHLER (nicht kritisch)" -ForegroundColor Yellow
}

# Einstellungen auch in der WebApp speichern
try {
    $body = '{"backup_dir":"' + $backupDir.Replace('\','\\') + '","backup_schedule_time":"' + $timeStr + '"}'
    Invoke-WebRequest -Uri "http://localhost/api/settings" -Method PUT -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Host "  Einstellungen in WebApp gespeichert." -ForegroundColor Green
} catch {
    Write-Host "  Hinweis: WebApp nicht erreichbar - Einstellungen werden dort nach dem naechsten Start sichtbar." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Einrichtung abgeschlossen!" -ForegroundColor Green
Write-Host ""
Write-Host "    Backup-Ordner : $backupDir" -ForegroundColor Gray
Write-Host "    Aufbewahrung  : 30 Tage" -ForegroundColor Gray
Write-Host "    Automatisch   : taeglich um $timeStr Uhr" -ForegroundColor Gray
Write-Host ""
Write-Host "  Tipp: Jetzt backup.bat ausfuehren um das erste Backup zu erstellen." -ForegroundColor Cyan
