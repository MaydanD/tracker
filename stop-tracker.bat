@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-tracker.ps1" -Stop
if errorlevel 1 (
    pause
    exit /b 1
)
