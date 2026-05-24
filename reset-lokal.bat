@echo off
chcp 65001 >nul
title DeineZeit – Zurücksetzen

echo.
echo  ACHTUNG: Alle lokalen Testdaten werden gelöscht!
echo.
set /p CONFIRM="Wirklich zurücksetzen? (J/N): "
if /i not "%CONFIRM%"=="J" (
    echo Abgebrochen.
    pause
    exit /b 0
)

cd /d "%~dp0"
echo.
echo  Stoppe und lösche alle Container und Daten...
docker compose -f docker-compose.local.yml down -v
echo.
echo  ✓ Zurückgesetzt. Beim nächsten Start mit start-lokal.bat
echo    wird alles neu eingerichtet.
echo.
pause
