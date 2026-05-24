# DeineZeit - Backup Watcher
# Lauft im Hintergrund und erkennt Aenderungen an Backup-Einstellungen
# Aktualisiert automatisch backup.cfg und den Windows-Aufgabenplaner

param()
$ErrorActionPreference = "SilentlyContinue"

Set-Location $PSScriptRoot

$configFile   = Join-Path $PSScriptRoot "backup.cfg"
$backupScript = Join-Path $PSScriptRoot "backup.ps1"
$apiBase      = "http://localhost/api"

# ── Konfiguration aus backup.cfg lesen ───────────────────────────────────────
function Get-LocalConfig {
    $cfg = @{ BACKUP_DIR = ""; KEEP_DAYS = "30"; BACKUP_SCHEDULE_TIME = "02:00" }
    if (Test-Path $configFile) {
        Get-Content $configFile | ForEach-Object {
            if ($_ -match "^([^=]+)=(.*)$") {
                $cfg[$matches[1].Trim()] = $matches[2].Trim()
            }
        }
    }
    return $cfg
}

# ── backup.cfg schreiben ──────────────────────────────────────────────────────
function Save-LocalConfig($dir, $keepDays) {
    "BACKUP_DIR=$dir`nKEEP_DAYS=$keepDays" | Set-Content -Path $configFile -Encoding UTF8
}

# ── Windows Task Scheduler aktualisieren ──────────────────────────────────────
function Update-ScheduledTask($backupDir, $scheduleTime) {
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
        -Force 2>&1 | Out-Null
}

# ── Startwerte aus lokaler Konfiguration lesen ────────────────────────────────
$localCfg = Get-LocalConfig
$lastDir  = $localCfg["BACKUP_DIR"]
$lastTime = $localCfg["BACKUP_SCHEDULE_TIME"]
if (-not $lastTime) { $lastTime = "02:00" }

# ── Hauptschleife: alle 30 Sekunden pruefen ───────────────────────────────────
while ($true) {
    Start-Sleep -Seconds 30

    try {
        $resp = Invoke-RestMethod -Uri "$apiBase/settings" -Method Get -TimeoutSec 5 -ErrorAction Stop

        $newDir      = if ($resp.backup_dir)           { $resp.backup_dir.Trim() }           else { "" }
        $newTime     = if ($resp.backup_schedule_time) { $resp.backup_schedule_time.Trim() } else { "02:00" }
        $newKeepDays = if ($resp.backup_keep_days)     { $resp.backup_keep_days.Trim() }     else { "30" }

        $dirChanged  = ($newDir  -ne $lastDir)
        $timeChanged = ($newTime -ne $lastTime)

        if ($dirChanged -or $timeChanged) {

            # backup.cfg aktualisieren
            if ($newDir -ne "") {
                Save-LocalConfig $newDir $newKeepDays
            }

            # Backup-Ordner anlegen falls er noch nicht existiert
            if ($newDir -ne "" -and -not (Test-Path $newDir)) {
                New-Item -ItemType Directory -Path $newDir -Force | Out-Null
            }

            # Windows-Aufgabenplaner aktualisieren (nur wenn beides gesetzt)
            if ($newDir -ne "" -and $newTime -ne "") {
                Update-ScheduledTask $newDir $newTime
            }

            $lastDir  = $newDir
            $lastTime = $newTime
        }
    } catch {
        # API nicht erreichbar (z.B. Container noch nicht gestartet) - ignorieren
    }
}
