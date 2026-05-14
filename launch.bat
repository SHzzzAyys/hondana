@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" desktop.py
) else (
    python desktop.py
)

if errorlevel 1 (
    echo.
    echo Launch failed.
    pause
)
