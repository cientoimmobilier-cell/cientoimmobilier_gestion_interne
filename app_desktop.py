# -*- coding: utf-8 -*-
"""
CIENTO IMMOBILIER — Lanceur Desktop Windows.

Ce module est le point d'entrée de l'application de bureau.
Il orchestre :
  1. la vérification d'instance unique (mutex Windows) ;
  2. la vérification de l'environnement (répertoires, PostgreSQL) ;
  3. la détection d'un port libre ;
  4. le démarrage du backend Flask en arrière-plan (127.0.0.1, waitress) ;
  5. l'ouverture de la fenêtre native PyWebView (EdgeChromium).

Aucun navigateur externe n'est jamais ouvert : l'utilisateur ne voit
aucune URL HTTP. Les raccourcis Windows pointent exclusivement vers
CIENTO-IMMOBILIER.exe.
"""
import os
import sys
import json
import time
import logging
import threading
import urllib.request
import urllib.error

APP_NAME = 'CIENTO IMMOBILIER'
APP_VERSION = '1.0.0'
APP_EXE = 'CIENTO-IMMOBILIER.exe'
APP_PUBLISHER = 'Ciento Immobilier'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
os.chdir(BASE_DIR)

from desktop.logger_config import setup_logging, log_security
startup_logger = setup_logging(BASE_DIR)
logger = logging.getLogger(__name__)

from desktop.single_instance import SingleInstance
from desktop.port_manager import PortManager
from desktop.startup_checks import StartupChecker
from desktop.notification_manager import NotificationManager

_startup_port = None


def _resource_dir():
    """Répertoire des ressources empaquetées.

    En mode PyInstaller onefile, les fichiers ajoutés via ``datas`` sont
    extraits dans ``sys._MEIPASS`` ; en mode source, on utilise BASE_DIR.
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', BASE_DIR)
    return BASE_DIR


def _resource_path(*parts):
    return os.path.join(_resource_dir(), *parts)


def _embed_logo_base64(max_width=300, max_height=200):
    """Encode le logo officiel en data-URI PNG pour l'écran de chargement."""
    import base64
    from PIL import Image
    import io

    logo_path = _resource_path('assets', 'splash.png')
    if not os.path.exists(logo_path):
        logger.warning('Splash logo not found: %s', logo_path)
        return ''
    try:
        img = Image.open(logo_path)
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        return (
            f'<img src="data:image/png;base64,{b64}" alt="{APP_NAME}" '
            f'style="max-width:{max_width}px;max-height:{max_height}px;'
            f'object-fit:contain;">'
        )
    except Exception as e:
        logger.warning('Could not embed splash logo: %s', e)
        return ''


def _splash_html():
    color_primary = '#0d6efd'
    color_bg = '#1a1a2e'
    color_accent = '#e94560'
    logo_html = _embed_logo_base64()
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="2;url=/">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family:'Segoe UI',system-ui,sans-serif;
  background:{color_bg}; color:#fff;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  height:100vh; overflow:hidden; user-select:none;
}}
.container {{ text-align:center; padding:40px; }}
.logo-area {{ margin-bottom:24px; min-height:180px; display:flex; align-items:center; justify-content:center; }}
h1 {{ font-size:28px; font-weight:300; letter-spacing:2px; margin-bottom:8px; }}
.subtitle {{ font-size:13px; color:#8899aa; letter-spacing:4px; text-transform:uppercase; margin-bottom:40px; }}
.spinner {{ margin-top:24px; }}
.spinner::after {{ content:''; display:inline-block; width:20px; height:20px; border:2px solid #2a2a4a; border-top-color:{color_accent}; border-radius:50%; animation:spin 0.8s linear infinite; }}
@keyframes spin {{ to {{ transform:rotate(360deg); }} }}
.footer {{ position:absolute; bottom:20px; font-size:11px; color:#445566; }}
</style></head><body>
<div class="container">
  <div class="logo-area">{logo_html}</div>
  <h1>{APP_NAME}</h1>
  <div class="subtitle">Enterprise Desktop</div>
  <p style="color:#99aabb;font-size:14px;">Chargement en cours...</p>
  <div class="spinner"></div>
</div>
<div class="footer">Version {APP_VERSION} &copy; {APP_PUBLISHER}</div>
</body></html>'''


def _run_flask(port):
    startup_logger.info('Starting Flask server on port %s...', port)
    from config import Config
    from app import create_app

    class DesktopConfig(Config):
        """Configuration locale du bureau.

        La fenêtre PyWebView communique en HTTP sur 127.0.0.1 (loopback).
        Les cookies de session doivent donc être acceptés en HTTP, sinon la
        connexion échouerait silencieusement dans la fenêtre native.
        """
        SESSION_COOKIE_SECURE = False
        REMEMBER_COOKIE_SECURE = False
        PREFERRED_URL_SCHEME = 'http'

    app = create_app(DesktopConfig)

    @app.route('/splash')
    def splash_page():
        return _splash_html()

    host = '127.0.0.1'
    try:
        from waitress import serve
        startup_logger.info('Flask serving on %s:%s with waitress', host, port)
        serve(app, host=host, port=port, threads=8, channel_timeout=30)
    except ImportError:
        startup_logger.warning('waitress not available, using Flask dev server')
        app.run(host=host, port=port, debug=False, use_reloader=False)


def _wait_for_flask(port, timeout=30):
    url = f'http://127.0.0.1:{port}/health'
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    startup_logger.info('Flask server ready after %ss', attempt)
                    return True
        except Exception:
            pass
        attempt += 1
        time.sleep(1)
    startup_logger.error('Flask server did not start in time')
    return False


def run_desktop(port=None, no_splash=False):
    global _startup_port

    logger.info('=== %s ENTERPRISE DESKTOP ===', APP_NAME)
    logger.info('Base directory: %s', BASE_DIR)
    logger.info('Python: %s', sys.version)

    instance = SingleInstance()
    if not instance.acquire():
        logger.info('Another instance is running — exiting')
        return

    try:
        startup_logger.info('Phase 1/4 — Environment checks')
        checker = StartupChecker(BASE_DIR)
        checker.check_all()
        for err in checker.errors:
            startup_logger.error('CHECK: %s', err)
        for warn in checker.warnings:
            startup_logger.warning('CHECK: %s', warn)

        startup_logger.info('Phase 2/4 — Port detection')
        port_mgr = PortManager()
        port = port_mgr.find_free_port(port)
        _startup_port = port
        if port_mgr.is_already_running:
            logger.info('Already running on port %s', port)
            _open_desktop_window(port, no_splash)
            return

        _write_port_file(port)

        startup_logger.info('Phase 3/4 — Starting Flask on port %s', port)
        flask_thread = threading.Thread(
            target=_run_flask, args=(port,), daemon=True
        )
        flask_thread.start()

        if not _wait_for_flask(port):
            logger.error('Flask server failed to start')
            _show_error_dialog(
                'Erreur de démarrage',
                'Le serveur Flask n\'a pas démarré dans les 30 secondes.\n'
                'Consultez les logs dans le dossier logs/.'
            )
            return

        startup_logger.info('Phase 4/4 — Opening desktop window')
        notification_mgr = NotificationManager()
        notification_mgr.start()
        notification_mgr.send('success', APP_NAME, 'L\'application est prête.')

        _open_desktop_window(port, no_splash)

    except Exception as e:
        logger.error('Fatal error: %s', e, exc_info=True)
        log_security('system', 'FATAL_ERROR', str(e))
        _show_error_dialog('Erreur fatale', str(e))
    finally:
        instance.release()
        logger.info('%s shutdown complete', APP_NAME)


def _open_desktop_window(port, no_splash=False):
    import webview

    icon_path = _resource_path('assets', 'app.ico')
    if not os.path.exists(icon_path):
        icon_path = None
    url = (
        f'http://127.0.0.1:{port}/splash'
        if not no_splash
        else f'http://127.0.0.1:{port}/'
    )

    startup_logger.info('Opening native desktop window (PyWebView)')

    webview.create_window(
        APP_NAME,
        url,
        width=1400,
        height=900,
        min_size=(1200, 800),
        resizable=True,
        fullscreen=False,
        text_select=True,
        confirm_close=True,
    )

    startup_logger.info('Starting webview GUI loop (edgechromium)')
    webview.start(
        gui='edgechromium',
        debug=False,
        private_mode=False,
        http_server=False,
        icon=icon_path,
    )
    startup_logger.info('Webview GUI loop ended')


def _show_error_dialog(title, message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        logger.error('%s: %s', title, message)


def _write_port_file(port):
    try:
        temp_dir = os.environ.get('TEMP', os.path.join(BASE_DIR, 'temp'))
        port_file = os.path.join(temp_dir, 'ciento_port.txt')
        with open(port_file, 'w') as f:
            f.write(str(port))
        startup_logger.info('Port written to %s', port_file)
    except Exception as e:
        logger.warning('Could not write port file: %s', e)


def get_startup_url():
    global _startup_port
    if _startup_port:
        return f'http://127.0.0.1:{_startup_port}/'
    return None


def request_shutdown():
    """Ferme proprement l'instance en cours d'exécution (désinstallation).

    Utilisé par l'installateur via ``CIENTO-IMMOBILIER.exe --shutdown``.
    """
    try:
        import win32gui
        import win32con
        hwnd = win32gui.FindWindow(None, APP_NAME)
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.info('Shutdown requested for running window')
            return True
        logger.info('No running window found for shutdown')
        return False
    except Exception as e:
        logger.error('Failed to request shutdown: %s', e)
        return False


def run_desktop_headless(port=None):
    port_mgr = PortManager()
    port = port_mgr.find_free_port(port)
    print(f'Starting CIENTO server on port {port}...')
    _run_flask(port)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=f'{APP_NAME} Enterprise Desktop')
    parser.add_argument('--port', type=int, default=None, help='Port to use')
    parser.add_argument('--no-splash', action='store_true', help='Skip splash screen')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument(
        '--shutdown', action='store_true',
        help='Ferme une instance en cours d\'exécution (installateur)'
    )
    args = parser.parse_args()

    if args.shutdown:
        return 0 if request_shutdown() else 1

    if args.debug:
        setup_logging(BASE_DIR, debug=True)

    run_desktop(port=args.port, no_splash=args.no_splash)
    return 0


if __name__ == '__main__':
    sys.exit(main())
