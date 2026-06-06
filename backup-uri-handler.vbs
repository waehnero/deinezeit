' DeineZeit – URI-Handler fuer deinezeit://update-task
' Wird automatisch ausgefuehrt wenn der Browser deinezeit:// oeffnet.
' Startet backup-task-register.ps1 mit UAC-Elevation (Adminrechte).

Dim scriptDir, psScript, shell

' Pfad dieses Scripts ermitteln
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
psScript  = scriptDir & "backup-task-register.ps1"

Set shell = CreateObject("Shell.Application")

' Mit "runas" = UAC-Aufforderung erscheint
shell.ShellExecute "PowerShell.exe", _
    "-ExecutionPolicy Bypass -WindowStyle Hidden -File """ & psScript & """", _
    "", "runas", 0

Set shell = Nothing
