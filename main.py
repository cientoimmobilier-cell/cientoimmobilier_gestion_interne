#!/usr/bin/env python
"""
CIENTO IMMOBILIER Enterprise Desktop
Production entry point — no console, PyInstaller-ready.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.chdir(BASE_DIR)

if __name__ == '__main__':
    from app_desktop import main
    sys.exit(main())
