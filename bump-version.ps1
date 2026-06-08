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
Write-Host "  DeineZeit  -  Version bump  →  $Version" -ForegroundColor Yellow
Write-Host "══════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""

$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

# ── 1. frontend/package.json ────────────────────────────────────────────────
Write-Step "frontend/package.json"
$pkgPath = Join-Path $Root "frontend\package.json"
$pkg = [System.IO.File]::ReadAllText($pkgPath, $Utf8NoBom)
$pkg = $pkg -replace '"version":\s*"[^"]+"', "`"version`": `"$Version`""
[System.IO.File]::WriteAllText($pkgPath, $pkg, $Utf8NoBom)

# ── 2. backend/app/core/config.py ───────────────────────────────────────────
Write-Step "backend/app/core/config.py"
$cfgPath = Join-Path $Root "backend\app\core\config.py"
$cfg = [System.IO.File]::ReadAllText($cfgPath, $Utf8NoBom)
$cfg = $cfg -replace 'APP_VERSION:\s*str\s*=\s*"[^"]+"', "APP_VERSION: str = `"$Version`""
[System.IO.File]::WriteAllText($cfgPath, $cfg, $Utf8NoBom)

# ── 3. docker-compose.yml ───────────────────────────────────────────────────
Write-Step "docker-compose.yml"
$dcPath = Join-Path $Root "docker-compose.yml"
$dc = [System.IO.File]::ReadAllText($dcPath, $Utf8NoBom)
$dc = $dc -replace 'APP_VERSION: \$\{APP_VERSION:-[^}]+\}', "APP_VERSION: `${APP_VERSION:-$Version}"
[System.IO.File]::WriteAllText($dcPath, $dc, $Utf8NoBom)

# ── 4. docker-compose.local.yml ─────────────────────────────────────────────
Write-Step "docker-compose.local.yml"
$dcLocalPath = Join-Path $Root "docker-compose.local.yml"
$dcLocal = [System.IO.File]::ReadAllText($dcLocalPath, $Utf8NoBom)
$dcLocal = $dcLocal -replace 'APP_VERSION: \$\{APP_VERSION:-[^}]+\}', "APP_VERSION: `${APP_VERSION:-$Version}"
[System.IO.File]::WriteAllText($dcLocalPath, $dcLocal, $Utf8NoBom)

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
[System.IO.File]::WriteAllText($clJsPath, $clJs, $Utf8NoBom)

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

## [$Version] - $date - $Titel
$neuSection$aktSection

---

"@

# Nach der Überschrift + ersten "---" einfügen
$clMd = $clMd -replace '(---\s*\n)', "`$1$newMdEntry"
# Aber nur einmal (erster Treffer reicht - PowerShell ersetzt alle, daher begrenzen)
# Lösung: nur den ersten Block ersetzen
$clMd = [regex]::Replace($clMd, '(---\s*\r?\n)', "$1$newMdEntry", [System.Text.RegularExpressions.RegexOptions]::None, [System.TimeSpan]::FromSeconds(5))
# Doppelt-Einfügen durch zweimaligen Match verhindern: Datei neu aufbauen
$clMd = Get-Content $clMdPath -Raw
$insertAfter = "---`n"
$insertIdx = $clMd.IndexOf($insertAfter) + $insertAfter.Length
$clMd = $clMd.Substring(0, $insertIdx) + $newMdEntry + $clMd.Substring($insertIdx)
[System.IO.File]::WriteAllText($clMdPath, $clMd, $Utf8NoBom)

# ── 7. Git commit & push ────────────────────────────────────────────────────
Write-Host ""
Write-Step "git add + commit + push"
git -C $Root add "frontend/package.json" "backend/app/core/config.py" "docker-compose.yml" "docker-compose.local.yml" "frontend/src/data/changelog.js" "CHANGELOG.md" "bump-version.ps1"

$commitMsg = "chore: Version $Version - $Titel"
git -C $Root commit -m $commitMsg
git -C $Root push

Write-Host ""
Write-Host "OK Version $Version erfolgreich gesetzt und gepusht." -ForegroundColor Green
Write-Host ""
