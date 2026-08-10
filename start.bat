@echo off
setlocal

set "ROOT=C:\Users\pierr\OneDrive - Fondation EPF\F\UCL\"

echo Demarrage du backend (FastAPI)...
start "UCL-Backend" cmd /c "cd /d "%ROOT%" && python -m uvicorn main:app --reload"

echo Demarrage du frontend (Angular)...
start "UCL-Frontend" cmd /c "cd /d "%ROOT%ucl-app" && ng serve"

echo Attente que le frontend soit pret sur http://localhost:4200 ...
:waitloop
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://localhost:4200' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto waitloop

echo Ouverture de Chrome...
set "CHROME="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined CHROME set "CHROME=chrome.exe"

start "" "%CHROME%" --new-window "http://localhost:4200"

echo Site ouvert dans Chrome.
echo Les serveurs s'arreteront automatiquement a la fermeture de Chrome.

:checkchrome
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if not errorlevel 1 goto checkchrome

echo Chrome ferme. Arret des serveurs...
taskkill /FI "WINDOWTITLE eq UCL-Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq UCL-Frontend*" /T /F >nul 2>&1

echo Termine.
endlocal
