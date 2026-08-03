# -*- mode: python ; coding: utf-8 -*-
# CIENTO IMMOBILIER — Spec PyInstaller (onefile, windowed)
# Compile : pyinstaller --noconfirm CIENTO-IMMOBILIER.spec
# Sortie  : dist\CIENTO-IMMOBILIER.exe

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

# PyInstaller exécute le .spec avec un sys.path réduit (sans le répertoire
# courant) : sans ceci, collect_all/collect_data_files('app') ne trouvent pas
# le package et retournent SILENCIEUSEMENT une liste vide. Résultat : aucun
# template Jinja2, CSS ou JS n'était empaqueté (app inutilisable en figé).
# On ajoute donc le dossier du .spec au sys.path pour la collecte.
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))

# Dossier assets uniquement : le fichier .env (secrets) ne doit JAMAIS être
# empaqueté dans l'exécutable. Il est lu depuis BASE_DIR (à côté du .exe)
# à l'exécution, chaque poste ayant sa propre configuration.
datas = [('assets', 'assets')]
binaries = []
hiddenimports = [
    'app',
    'app.models',
    'app.routes',
    'app.utils',
    'app.services',
    'desktop',
    'sqlalchemy',
    'flask',
    'flask_login',
    'flask_sqlalchemy',
    'flask_bcrypt',
    'flask_wtf',
    'psycopg2',
    'reportlab',
    'openpyxl',
    'dotenv',
    'cryptography',
    'google.auth',
    'google.auth.transport',
    'google.oauth2',
    'google_auth_oauthlib',
    'googleapiclient',
    'googleapiclient.discovery',
    'googleapiclient.http',
    'httplib2',
    'webview',
    'waitress',
    'pythonnet',
    'clr_loader',
    'bottle',
    'proxy_tools',
    'win32api',
    'win32event',
    'win32gui',
    'win32con',
    'winerror',
]

for pkg in ('app', 'desktop'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# Ne JAMAIS empaqueter les données utilisateur dans l'exécutable :
# app/static/uploads/* contient photos et contrats (données personnelles).
# collect_all('app') les collecte sinon. Le .env (secrets) est exclu de datas
# et n'est pas sous app/, il n'est donc jamais empaqueté.
def _is_upload_data(source):
    parts = str(source).replace('/', os.sep).split(os.sep)
    return 'uploads' in parts

datas = [d for d in datas if not _is_upload_data(d[0])]

# Templates Jinja2 : ajout explicite sous app/templates (dossier de recherche
# par défaut de Flask). Redondant avec collect_all('app') ci-dessus (dédoublonné
# par PyInstaller) mais garanti par construction.
datas += collect_data_files('app', subdir='templates')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide2', 'PyQt5', 'PyQt6', 'matplotlib', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CIENTO-IMMOBILIER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX désactivé : il provoque de nombreux faux positifs antivirus.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
)
