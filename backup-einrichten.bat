@echo off
PowerShell -ExecutionPolicy Bypass -File "%~dp0backup-einrichten.ps1"
echo.
echo   Druecken Sie eine beliebige Taste zum Schliessen...
pause > nul
