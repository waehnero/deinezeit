@echo off
PowerShell -ExecutionPolicy Bypass -File "%~dp0backup-watcher.ps1"
echo.
echo   Druecken Sie eine beliebige Taste zum Schliessen...
pause > nul
