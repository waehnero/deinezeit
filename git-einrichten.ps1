# ============================================================
# DeineZeit - Git Repository einrichten
# Einmalig ausfuehren: .\git-einrichten.ps1
# ============================================================

Write-Host ""
Write-Host "Git Repository einrichten..." -ForegroundColor Cyan

# Git initialisieren (falls noch nicht)
if (-not (Test-Path ".\.git")) {
    git init
    git branch -m main
    Write-Host "  OK: Git Repository initialisiert (Branch: main)" -ForegroundColor Green
} else {
    Write-Host "  Git bereits initialisiert" -ForegroundColor Gray
}

# Git-Konfiguration
git config user.name  "Oliver Waehner"
git config user.email "oliver@waehner.at"
Write-Host "  OK: Git-Benutzer gesetzt (oliver@waehner.at)" -ForegroundColor Green

# Dateien hinzufuegen
git add .
Write-Host ""
Write-Host "Folgende Dateien werden committed:" -ForegroundColor Gray
git status --short

Write-Host ""
$answer = Read-Host "Ersten Commit erstellen? (j/n)"
if ($answer -eq "j") {
    git commit -m "Initial commit - DeineZeit v0.4.0"
    Write-Host ""
    Write-Host "  OK: Erster Commit erstellt!" -ForegroundColor Green
}

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  NAECHSTE SCHRITTE" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  GitHub-Repository verknuepfen:" -ForegroundColor White
Write-Host "    git remote add origin https://github.com/waehnero/deinezeit.git" -ForegroundColor Yellow
Write-Host "    git push -u origin main" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Sicherheits-Check vor dem Deployment:" -ForegroundColor White
Write-Host "    .\sicherheits-check.ps1" -ForegroundColor Yellow
Write-Host ""
