# DeineZeit – Datenbank wiederherstellen
# Zeigt vorhandene Backups und stellt das gewählte wieder her

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  DeineZeit – Datenbank wiederherstellen" -ForegroundColor Cyan
Write-Host ""
Write-Host "  ACHTUNG: Die aktuelle Datenbank wird vollstaendig durch das" -ForegroundColor Yellow
Write-Host "           ausgewaehlte Backup ersetzt!" -ForegroundColor Yellow
Write-Host ""

try {
    # ── Konfiguration laden ───────────────────────────────────────────────────
    $configFile = Join-Path $PSScriptRoot "backup.cfg"
    if (-not (Test-Path $configFile)) {
        Write-Host "  FEHLER: Backup noch nicht eingerichtet." -ForegroundColor Red
        Write-Host "  Bitte zuerst backup-einrichten.bat ausfuehren." -ForegroundColor Yellow
        exit 1
    }

    $config = @{}
    Get-Content $configFile | ForEach-Object {
        if ($_ -match "^(.+?)=(.*)$") { $config[$matches[1].Trim()] = $matches[2].Trim() }
    }
    $backupDir = $config["BACKUP_DIR"]

    # ── Container prüfen ──────────────────────────────────────────────────────
    $container = "deinezeit_db"
    $running = docker ps --filter "name=$container" --filter "status=running" -q
    if (-not $running) {
        Write-Host "  FEHLER: Container '$container' laeuft nicht." -ForegroundColor Red
        Write-Host "  Bitte zuerst start-lokal.bat ausfuehren." -ForegroundColor Yellow
        exit 1
    }

    # ── Backups auflisten ─────────────────────────────────────────────────────
    if (-not (Test-Path $backupDir)) {
        Write-Host "  Backup-Ordner nicht gefunden: $backupDir" -ForegroundColor Red
        exit 1
    }

    $backups = Get-ChildItem -Path $backupDir -Filter "deinezeit_backup_*.sql" |
               Sort-Object LastWriteTime -Descending

    if ($backups.Count -eq 0) {
        Write-Host "  Keine Backups gefunden in: $backupDir" -ForegroundColor Yellow
        Write-Host "  Bitte zuerst backup.bat ausfuehren." -ForegroundColor Gray
        exit 1
    }

    Write-Host "  Verfuegbare Backups:" -ForegroundColor White
    Write-Host ""

    for ($i = 0; $i -lt [Math]::Min($backups.Count, 20); $i++) {
        $b    = $backups[$i]
        $size = [math]::Round($b.Length / 1MB, 2)
        $date = $b.LastWriteTime.ToString("dd.MM.yyyy HH:mm")
        $nr   = ($i + 1).ToString().PadLeft(2)
        Write-Host "  [$nr] $date   $($b.Name)   ($size MB)" -ForegroundColor Gray
    }

    Write-Host ""
    $choice = Read-Host "  Nummer eingeben (oder Enter zum Abbrechen)"

    if ($choice.Trim() -eq "") {
        Write-Host "  Abgebrochen." -ForegroundColor Gray
        exit 0
    }

    $idx = [int]$choice - 1
    if ($idx -lt 0 -or $idx -ge $backups.Count) {
        Write-Host "  Ungueltige Auswahl." -ForegroundColor Red
        exit 1
    }

    $selected = $backups[$idx]
    Write-Host ""
    Write-Host "  Ausgewaehlt: $($selected.Name)" -ForegroundColor White
    Write-Host ""
    $confirm = Read-Host "  Wirklich wiederherstellen? Alle aktuellen Daten gehen verloren! [J/n]"
    if ($confirm.Trim() -eq "" -or $confirm -match "^[JjYy]") {
        # OK
    } else {
        Write-Host "  Abgebrochen." -ForegroundColor Gray
        exit 0
    }

    # ── Sicherheits-Backup vor Wiederherstellung ──────────────────────────────
    Write-Host ""
    Write-Host "  Erstelle Sicherheits-Backup des aktuellen Stands..." -NoNewline
    $safeFile = Join-Path $backupDir "deinezeit_backup_VOR-WIEDERHERSTELLUNG_$(Get-Date -Format 'yyyy-MM-dd_HH-mm').sql"
    docker exec $container pg_dump -U deinezeit deinezeit | Out-File -FilePath $safeFile -Encoding utf8
    Write-Host " OK" -ForegroundColor Green
    Write-Host "  Gespeichert als: $($safeFile | Split-Path -Leaf)" -ForegroundColor Gray

    # ── Datenbank wiederherstellen ────────────────────────────────────────────
    Write-Host ""
    Write-Host "  Stelle Datenbank wieder her..." -NoNewline

    # Bestehende Verbindungen trennen und DB leeren
    docker exec $container psql -U deinezeit -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'deinezeit' AND pid <> pg_backend_pid();" postgres | Out-Null
    docker exec $container psql -U deinezeit -c "DROP DATABASE IF EXISTS deinezeit;" postgres | Out-Null
    docker exec $container psql -U deinezeit -c "CREATE DATABASE deinezeit;" postgres | Out-Null

    # Backup einspielen
    Get-Content $selected.FullName | docker exec -i $container psql -U deinezeit deinezeit | Out-Null

    Write-Host " OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Wiederherstellung abgeschlossen!" -ForegroundColor Green
    Write-Host "  Bitte die Seite im Browser neu laden (F5)." -ForegroundColor Cyan

} catch {
    Write-Host ""
    Write-Host "  Fehler: $_" -ForegroundColor Red
}
