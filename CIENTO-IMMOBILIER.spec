# -*- mode: python ; coding: utf-8 -*-
# CIENTO IMMOBILIER — Spec PyInstaller (onefile, windowed)
# Compile : pyinstaller --noconfirm CIENTO-IMMOBILIER.spec
# Sortie  : dist\CIENTO-IMMOBILIER.exe

from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets'), ('.env', '.')]
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
    upx=True,
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
