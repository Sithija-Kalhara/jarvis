@echo off
chcp 65001 >nul
title J.A.R.V.I.S. EXE Builder
color 0B
cd /d "%~dp0"
echo.
echo  ============================================================
echo    Building JARVIS.exe  (v5)
echo  ============================================================
echo.

echo  [1/3] Installing requirements...
pip install -r requirements.txt --quiet
echo  [OK] Requirements ready

echo.
echo  [2/3] Building EXE (2-4 minutes, please wait)...
echo.

set ICON=
if exist jarvis.ico set ICON=--icon=jarvis.ico

pyinstaller --noconfirm --onefile --noconsole --name "JARVIS" %ICON% ^
    --collect-data speech_recognition ^
    --collect-all sounddevice ^
    --collect-all edge_tts ^
    --collect-data certifi ^
    --collect-submodules comtypes ^
    --collect-submodules pycaw ^
    --hidden-import=pyttsx3.drivers ^
    --hidden-import=pyttsx3.drivers.sapi5 ^
    --hidden-import=pygetwindow ^
    --hidden-import=PIL.ImageGrab ^
    JARVIS_FULL.py

echo.
echo  [3/3] Finishing...
if exist "dist\JARVIS.exe" (
    copy "dist\JARVIS.exe" "%USERPROFILE%\Desktop\JARVIS.exe" /Y >nul
    echo.
    echo  ============================================================
    echo   [OK] SUCCESS!  JARVIS.exe is on your Desktop
    echo   Make sure "ollama serve" is running, then double-click it.
    echo   Settings + log are saved next to the EXE.
    echo  ============================================================
) else (
    echo.
    echo  BUILD FAILED - scroll up for the PyInstaller error.
)
echo.
pause
