# ============================================================
# DeineZeit – Sicherheits- & Qualitäts-Check
# Ausführen vor jedem Deployment: .\sicherheits-check.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$Passed  = 0
$Failed  = 0
$Warnings = 0

function Write-Header($text) {
    Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
}

function Write-Ok($text)   { Write-Host "  ✅ $text" -ForegroundColor Green;  $script:Passed++ }
function Write-Fail($text) { Write-Host "  ❌ $text" -ForegroundColor Red;    $script:Failed++ }
function Write-Warn($text) { Write-Host "  ⚠️  $text" -ForegroundColor Yellow; $script:Warnings++ }

Write-Host "`n🔒 DeineZeit Sicherheits-Check" -ForegroundColor White
Write-Host "   $(Get-Date -Format 'dd.MM.yyyy HH:mm')" -ForegroundColor Gray

# ── 1. Secrets & Konfiguration ───────────────────────────────────────────────
Write-Header "1. Secrets & Konfiguration"

# .env vorhanden?
if (Test-Path ".\.env") {
    Write-Ok ".env Datei vorhanden"

    # SECRET_KEY stark genug?
    $envContent = Get-Content ".\.env" -Raw
    if ($envContent -match "SECRET_KEY=(.+)") {
        $key = $Matches[1].Trim()
        if ($key.Length -ge 32 -and $key -notmatch "changeme|secret|example|test|1234") {
            Write-Ok "SECRET_KEY ist stark ($($key.Length) Zeichen)"
        } else {
            Write-Fail "SECRET_KEY ist zu schwach oder Standard-Wert!"
        }
    }

    # Standard-Passwörter?
    if ($envContent -match "DB_PASSWORD=(password|123456|admin|test|changeme)") {
        Write-Fail "DB_PASSWORD ist ein unsicheres Standard-Passwort!"
    } else {
        Write-Ok "DB_PASSWORD ist kein Standard-Passwort"
    }

} else {
    Write-Fail ".env Datei fehlt!"
}

# .env in .gitignore?
if (Test-Path ".\.gitignore") {
    $gitignore = Get-Content ".\.gitignore" -Raw
    if ($gitignore -match "\.env") {
        Write-Ok ".env ist in .gitignore eingetragen"
    } else {
        Write-Fail ".env fehlt in .gitignore – Secrets könnten committed werden!"
    }
} else {
    Write-Warn ".gitignore fehlt"
}

# ── 2. Python Abhängigkeiten auf bekannte Schwachstellen prüfen ───────────────
Write-Header "2. Python Abhängigkeiten (pip-audit)"

$pipAudit = Get-Command "pip-audit" -ErrorAction SilentlyContinue
if ($pipAudit) {
    Write-Host "  Prüfe Python-Pakete auf CVEs..." -ForegroundColor Gray
    $result = & pip-audit -r .\backend\requirements.txt --format=text 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Keine bekannten Schwachstellen in Python-Abhängigkeiten"
    } else {
        Write-Fail "Schwachstellen gefunden:`n$result"
    }
} else {
    Write-Warn "pip-audit nicht installiert. Installation: pip install pip-audit"
    Write-Host "  Übersprungen." -ForegroundColor Gray
}

# ── 3. Python Code Sicherheitsscan (Bandit) ───────────────────────────────────
Write-Header "3. Python Code-Scan (Bandit)"

$bandit = Get-Command "bandit" -ErrorAction SilentlyContinue
if ($bandit) {
    Write-Host "  Scanne Backend-Code..." -ForegroundColor Gray
    $result = & bandit -r .\backend\app\ -ll -q 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Keine kritischen Sicherheitsprobleme im Backend-Code"
    } else {
        Write-Fail "Bandit hat Probleme gefunden:`n$($result | Select-Object -First 20)"
    }
} else {
    Write-Warn "Bandit nicht installiert. Installation: pip install bandit"
    Write-Host "  Übersprungen." -ForegroundColor Gray
}

# ── 4. Konfigurationsprüfungen ────────────────────────────────────────────────
Write-Header "4. Konfiguration & Deployment-Sicherheit"

# APP_ENV gesetzt?
if (Test-Path ".\.env") {
    $envContent = Get-Content ".\.env" -Raw
    if ($envContent -match "APP_ENV=production") {
        Write-Ok "APP_ENV=production gesetzt (API-Docs deaktiviert)"
    } else {
        Write-Warn "APP_ENV nicht auf 'production' gesetzt – API-Docs sind öffentlich sichtbar"
    }
}

# Dockerfile vorhanden und kein Root-User?
if (Test-Path ".\backend\Dockerfile") {
    $dockerfile = Get-Content ".\backend\Dockerfile" -Raw
    if ($dockerfile -match "USER\s+(?!root)") {
        Write-Ok "Backend läuft nicht als root"
    } else {
        Write-Warn "Backend Dockerfile: kein unprivilegierter User konfiguriert"
    }
} else {
    Write-Warn "Backend Dockerfile nicht gefunden"
}

# nginx security headers vorhanden?
$nginxConf = Get-ChildItem ".\nginx\" -Recurse -Filter "*.conf" | Select-Object -First 1
if ($nginxConf) {
    $nginxContent = Get-Content $nginxConf.FullName -Raw
    $headers = @("X-Frame-Options", "X-Content-Type-Options", "Strict-Transport-Security")
    $allPresent = $true
    foreach ($h in $headers) {
        if ($nginxContent -notmatch $h) { $allPresent = $false }
    }
    if ($allPresent) {
        Write-Ok "nginx Security-Header konfiguriert"
    } else {
        Write-Warn "Nicht alle Security-Header in nginx konfiguriert"
    }
}

# ── 5. Git-Status ─────────────────────────────────────────────────────────────
Write-Header "5. Git-Status"

$git = Get-Command "git" -ErrorAction SilentlyContinue
if ($git -and (Test-Path ".\.git")) {
    # Uncommitted changes?
    $status = & git status --porcelain 2>&1
    if ($status) {
        Write-Warn "Uncommitted Änderungen vorhanden – bitte committen vor dem Deployment"
        $status | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    } else {
        Write-Ok "Alle Änderungen committed"
    }

    # Secrets versehentlich committed?
    $secrets = & git log --all --full-history --format="%H" -- "*.env" ".env*" 2>&1
    if ($secrets) {
        Write-Fail "ACHTUNG: .env Dateien wurden möglicherweise in Git committed! Prüfen!"
    } else {
        Write-Ok "Keine .env Dateien in Git-History"
    }
} else {
    Write-Warn "Git nicht initialisiert oder git nicht installiert"
}

# ── Zusammenfassung ───────────────────────────────────────────────────────────
Write-Host "`n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
Write-Host "  ERGEBNIS" -ForegroundColor White
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
Write-Host "  ✅ Bestanden:  $Passed" -ForegroundColor Green
Write-Host "  ⚠️  Warnungen:  $Warnings" -ForegroundColor Yellow
Write-Host "  ❌ Fehler:     $Failed" -ForegroundColor Red

if ($Failed -gt 0) {
    Write-Host "`n  🚫 DEPLOYMENT NICHT EMPFOHLEN — bitte Fehler beheben!" -ForegroundColor Red
    exit 1
} elseif ($Warnings -gt 0) {
    Write-Host "`n  ⚠️  Deployment möglich, aber Warnungen beachten." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "`n  🚀 Alle Checks bestanden — Deployment freigegeben!" -ForegroundColor Green
    exit 0
}
