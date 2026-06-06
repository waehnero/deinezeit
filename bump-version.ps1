# bump-version.ps1
# Aktualisiert alle Versions-Dateien auf einmal und committet.
#
# Verwendung:
#   .\bump-version.ps1 -Version 1.3.0 -Titel "Neues Feature" -Features "Feature A","Feature B" -Updates "Fix X","Fix Y"
#
# Pflichtparameter: -Version, -Titel
# Optional: -Features, -Updates (jeweils als String-Array)

param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$Titel,
    [string[]]$Features = @(),
    [string[]]$Updates  = @()
)

$Root = $PSScriptRoot

function Write-Step([string]$msg) {
    Write-Host "  → $msg" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  DeineZeit  –  Version bump  →  $Version" -ForegroundColor Yellow
Write-Host "══════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""

# ── 1. frontend/package.json ────────────────────────────────────────────────
Write-Step "frontend/package.json"
$pkgPath = Join-Path $Root "frontend\package.json"
$pkg = Get-Content $pkgPath -Raw
$pkg = $pkg -replace '"version":\s*"[^"]+"', "`"version`": `"$Version`""
Set-Content $pkgPath $pkg -NoNewline

# ── 2. backend/app/core/config.py ───────────────────────────────────────────
Write-Step "backend/app/core/config.py"
$cfgPath = Join-Path $Root "backend\app\core\config.py"
$cfg = Get-Content $cfgPath -Raw
$cfg = $cfg -replace 'APP_VERSION:\s*str\s*=\s*"[^"]+"', "APP_VERSION: str = `"$Version`""
Set-Content $cfgPath $cfg -NoNewline

# ── 3. docker-compose.yml ───────────────────────────────────────────────────
Write-Step "docker-compose.yml"
$dcPath = Join-Path $Root "docker-compose.yml"
$dc = Get-Content $dcPath -Raw
$dc = $dc -replace 'APP_VERSION: \$\{APP_VERSION:-[^}]+\}', "APP_VERSION: `${APP_VERSION:-$Version}"
Set-Content $dcPath $dc -NoNewline

# ── 4. docker-compose.local.yml ─────────────────────────────────────────────
Write-Step "docker-compose.local.yml"
$dcLocalPath = Join-Path $Root "docker-compose.local.yml"
$dcLocal = Get-Content $dcLocalPath -Raw
$dcLocal = $dcLocal -replace 'APP_VERSION: \$\{APP_VERSION:-[^}]+\}', "APP_VERSION: `${APP_VERSION:-$Version}"
Set-Content $dcLocalPath $dcLocal -NoNewline

# ── 5. frontend/src/data/changelog.js ───────────────────────────────────────
Write-Step "frontend/src/data/changelog.js"
$clJsPath = Join-Path $Root "frontend\src\data\changelog.js"
$clJs = Get-Content $clJsPath -Raw

$today = Get-Date
$day   = $today.Day.ToString("00")
$monthNames = @("","Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember")
$month = $monthNames[$today.Month]
$year  = $today.Year.ToString()

$featuresJs = ($Features | ForEach-Object { "      '$_'," }) -join "`n"
$updatesJs  = ($Updates  | ForEach-Object { "      '$_'," }) -join "`n"

$newEntry = @"
  {
    version: '$Version',
    day: '$day',
    month: '$month',
    year: '$year',
    features: [
$featuresJs
    ],
    updates: [
$updatesJs
    ],
  },
"@

# Eintrag ganz oben nach "export const changelog = [" einfügen
$clJs = $clJs -replace '(export const changelog = \[)', "`$1`n$newEntry"
Set-Content $clJsPath $clJs -NoNewline

# ── 6. CHANGELOG.md ─────────────────────────────────────────────────────────
Write-Step "CHANGELOG.md"
$clMdPath = Join-Path $Root "CHANGELOG.md"
$clMd = Get-Content $clMdPath -Raw

$featuresMd = ($Features | ForEach-Object { "- $_" }) -join "`n"
$updatesMd  = ($Updates  | ForEach-Object { "- $_" }) -join "`n"

$date = $today.ToString("yyyy-MM-dd")

$neuSection    = if ($Features.Count -gt 0) { "`n`n### Neu`n$featuresMd" } else { "" }
$aktSection    = if ($Updates.Count  -gt 0) { "`n`n### Aktualisierungen`n$updatesMd" } else { "" }

$newMdEntry = @"

## [$Version] – $date – $Titel
$neuSection$aktSection

---

"@

# Nach der Überschrift + ersten "---" einfügen
$clMd = $clMd -replace '(---\s*\n)', "`$1$newMdEntry"
# Aber nur einmal (erster Treffer reicht — PowerShell ersetzt alle, daher begrenzen)
# Lösung: nur den ersten Block ersetzen
$clMd = [regex]::Replace($clMd, '(---\s*\r?\n)', "$1$newMdEntry", [System.Text.RegularExpressions.RegexOptions]::None, [System.TimeSpan]::FromSeconds(5))
# Doppelt-Einfügen durch zweimaligen Match verhindern: Datei neu aufbauen
$clMd = Get-Content $clMdPath -Raw
$insertAfter = "---`n"
$insertIdx = $clMd.IndexOf($insertAfter) + $insertAfter.Length
$clMd = $clMd.Substring(0, $insertIdx) + $newMdEntry + $clMd.Substring($insertIdx)
Set-Content $clMdPath $clMd -NoNewline

# ── 7. Git commit & push ────────────────────────────────────────────────────
Write-Host ""
Write-Step "git add + commit + push"
git -C $Root add `
    frontend/package.json `
    backend/app/core/config.py `
    docker-compose.yml `
    docker-compose.local.yml `
    "frontend/src/data/changelog.js" `
    CHANGELOG.md

$commitMsg = "chore: Version $Version — $Titel"
git -C $Root commit -m $commitMsg
git -C $Root push

Write-Host ""
Write-Host "✓ Version $Version erfolgreich gesetzt und gepusht." -ForegroundColor Green
Write-Host ""
