@echo off
cd /d "%~dp0"
echo Lancement du serveur Ciento Immobilier...
echo Veuillez patienter, votre navigateur va s'ouvrir.
start "" http://127.0.0.1:5000/
.\venv\Scripts\python.exe run.py
