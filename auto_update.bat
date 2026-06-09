@echo off
chcp 65001 > nul
cd /d "C:\Users\sithi\Desktop\jarvis"

git pull origin main --rebase

git add .
git commit -m "Auto update at startup: %date% %time%"
git push origin main

echo Done! Everything is up to date.
pause