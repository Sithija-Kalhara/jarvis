@echo off
title J.A.R.V.I.S. - Complete Setup
color 0B
echo.
echo  ============================================================
echo    J.A.R.V.I.S.  Complete Setup  ^&  Launcher
echo  ============================================================
echo.

:: ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found!
    echo  Download from: https://www.python.org/downloads/
    pause & exit
)
echo  [✓] Python found

:: ── Install all packages ─────────────────────────────────────
echo.
echo  [1/3] Installing packages (first time only)...
pip install -r requirements.txt --quiet
echo  [✓] All packages installed

:: ── Check Ollama ─────────────────────────────────────────────
echo.
echo  [2/3] Starting Ollama...
start /min "" ollama serve
timeout /t 3 /nobreak >nul
echo  [✓] Ollama started

:: ── Run JARVIS ───────────────────────────────────────────────
echo.
echo  [3/3] Launching JARVIS Desktop App...
echo  ============================================================
echo.
python JARVIS_FULL.py

pause
