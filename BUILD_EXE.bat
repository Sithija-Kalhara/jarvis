@echo off
title J.A.R.V.I.S. EXE Builder
color 0B
echo.
echo  ============================================================
echo    Building JARVIS.exe
echo  ============================================================
echo.

:: Install pyinstaller
echo  [1/3] Installing PyInstaller...
pip install pyinstaller --quiet
echo  [✓] PyInstaller ready

:: Build
echo.
echo  [2/3] Building EXE (2-4 minutes, please wait)...
echo.

if exist jarvis.ico (
    pyinstaller --onefile --noconsole --name "JARVIS" --icon=jarvis.ico ^
        --hidden-import=speech_recognition ^
        --hidden-import=pyttsx3 ^
        --hidden-import=pyttsx3.drivers ^
        --hidden-import=pyttsx3.drivers.sapi5 ^
        --hidden-import=pyautogui ^
        --hidden-import=pygetwindow ^
        --hidden-import=PIL ^
        --hidden-import=PIL.ImageGrab ^
        --hidden-import=psutil ^
        --hidden-import=ollama ^
        --hidden-import=sounddevice ^
        --hidden-import=comtypes ^
        --hidden-import=pycaw ^
        --hidden-import=winreg ^
        JARVIS_FULL.py
) else (
    pyinstaller --onefile --noconsole --name "JARVIS" ^
        --hidden-import=speech_recognition ^
        --hidden-import=pyttsx3 ^
        --hidden-import=pyttsx3.drivers ^
        --hidden-import=pyttsx3.drivers.sapi5 ^
        --hidden-import=pyautogui ^
        --hidden-import=pygetwindow ^
        --hidden-import=PIL ^
        --hidden-import=PIL.ImageGrab ^
        --hidden-import=psutil ^
        --hidden-import=ollama ^
        --hidden-import=sounddevice ^
        --hidden-import=comtypes ^
        --hidden-import=pycaw ^
        --hidden-import=winreg ^
        JARVIS_FULL.py
)

:: Copy to Desktop
echo.
echo  [3/3] Finishing...
if exist "dist\JARVIS.exe" (
    copy "dist\JARVIS.exe" "%USERPROFILE%\Desktop\JARVIS.exe" /Y
    echo.
    echo  ============================================================
    echo   [✓] SUCCESS!  JARVIS.exe is on your Desktop
    echo   Double-click it to launch (make sure ollama serve is running)
    echo  ============================================================
) else (
    echo.
    echo  BUILD FAILED. Try running as Administrator.
)
echo.
pause
