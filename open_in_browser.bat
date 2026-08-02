@echo off
REM CIENTO IMMOBILIER - Ouvre l'application dans le navigateur par defaut.
REM Utilitaire de developpement : demarrer d'abord le serveur avec :
REM     python run.py
REM Usage : open_in_browser.bat [port]   (defaut : 5000)
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=5000"
start "" "http://127.0.0.1:%PORT%/"
endlocal
