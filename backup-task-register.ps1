# DeineZeit – Backup-Task registrieren (lautlos, kein Pause)
# Wird via backup-uri-handler.vbs mit Adminrechten aufgerufen.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$configFile   = Join-Path $PSScriptRoot "backup.cfg"
$backupScript = Join-Path $PSScriptRoot "backup.ps1"

if (-not (Test-Path $configFile)) { exit 1 }

$config = @{}
Get-Content $configFile | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") { $config[$matches[1].Trim()] = $matches[2].Trim() }
}

$backupDir    = $config["BACKUP_DIR"]
$scheduleTime = if ($config["BACKUP_SCHEDULE_TIME"]) { $config["BACKUP_SCHEDULE_TIME"] } else { "02:00" }

if (-not $backupDir) { exit 1 }

# Ordner anlegen
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

# Task registrieren
$taskName = "DeineZeit-Backup"
$argument = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$backupScript`" -Silent"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument $argument
$trigger  = New-ScheduledTaskTrigger -Daily -At $scheduleTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName    $taskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Description "Automatisches DeineZeit Datenbank-Backup" `
    -RunLevel    Highest `
    -Force | Out-Null
