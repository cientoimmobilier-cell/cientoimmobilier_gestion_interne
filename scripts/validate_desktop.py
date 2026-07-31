# -*- coding: utf-8 -*-
"""
CIENTO IMMOBILIER — Validation automatique des raccourcis Windows et du logo.

Vérifie :
  1. la génération multi-tailles des icônes (16..256) et du favicon ;
  2. l'absence de toute URL HTTP (localhost/127.0.0.1/0.0.0.0) dans les
     raccourcis configurés (Inno Setup, spec, scripts de build) ;
  3. la cible unique des raccourcis : CIENTO-IMMOBILIER.exe ;
  4. le logo officiel sur le splash, la fenêtre de connexion, la page
     À propos et le favicon ;
  5. le fonctionnement de l'instance unique, du port manager et du
     backend Flask (healthcheck) ;
  6. le flag --shutdown utilisé par l'installateur.

Usage : python scripts/validate_desktop.py
"""
import os
import re
import sys
import time
import struct
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

FAILURES = []
CHECKS = []


def check(name, ok, detail=''):
    status = 'PASS' if ok else 'FAIL'
    CHECKS.append((name, ok))
    print(f'[{status}] {name}' + (f' — {detail}' if detail else ''))
    if not ok:
        FAILURES.append(name)


def ico_frames(path):
    data = open(path, 'rb').read()
    count = struct.unpack('<H', data[4:6])[0]
    dims = set()
    for i in range(count):
        off = 6 + i * 16
        w_, h_, *_ = struct.unpack('<BBBBHHII', data[off:off + 16])
        dims.add((w_ or 256, h_ or 256))
    return dims


def main():
    print('=' * 60)
    print('  CIENTO IMMOBILIER — Validation desktop')
    print('=' * 60)

    # ── 1. Icônes multi-tailles ─────────────────────────────────────────
    expected = {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
    app_ico = os.path.join(BASE_DIR, 'assets', 'app.ico')
    inst_ico = os.path.join(BASE_DIR, 'assets', 'installer.ico')
    favicon = os.path.join(BASE_DIR, 'app', 'static', 'favicon.ico')
    check('app.ico contient 16..256',
          os.path.exists(app_ico) and ico_frames(app_ico) == expected)
    check('installer.ico contient 16..256',
          os.path.exists(inst_ico) and ico_frames(inst_ico) == expected)
    check('favicon.ico contient 16,32,48,64',
          os.path.exists(favicon) and ico_frames(favicon) ==
          {(16, 16), (32, 32), (48, 48), (64, 64)})
    pngs_ok = all(
        os.path.exists(os.path.join(BASE_DIR, 'assets', 'icons', f'{s}.png'))
        for s in (16, 32, 48, 64, 128, 256)
    )
    check('PNG 16..256 générés dans assets/icons', pngs_ok)
    check('logo.png 512 généré dans static',
          os.path.exists(os.path.join(BASE_DIR, 'app', 'static', 'logo.png')))

    # ── 2. Aucune URL HTTP dans les raccourcis / scripts ────────────────
    forbidden = ['http://localhost', 'http://127.0.0.1', 'http://0.0.0.0']
    files_to_scan = [
        os.path.join(BASE_DIR, 'installer', 'ciento_installer.iss'),
        os.path.join(BASE_DIR, 'CIENTO-IMMOBILIER.spec'),
        os.path.join(BASE_DIR, 'build.bat'),
        os.path.join(BASE_DIR, 'installer', 'build_installer.bat'),
    ]
    for path in files_to_scan:
        if not os.path.exists(path):
            check(f'{os.path.basename(path)} existe', False)
            continue
        content = open(path, 'r', encoding='utf-8', errors='ignore').read()
        hits = [tok for tok in forbidden if tok in content]
        check(f'Aucune URL HTTP dans {os.path.basename(path)}', not hits,
              ', '.join(hits) if hits else '')
        check(f'{os.path.basename(path)} cible CIENTO-IMMOBILIER.exe',
              'CIENTO-IMMOBILIER.exe' in content)

    iss = open(files_to_scan[0], 'r', encoding='utf-8').read()
    check('Raccourcis ISS pointent vers l\'exe uniquement',
          '#define MyAppExeName "CIENTO-IMMOBILIER.exe"' in iss and
          'Filename: "{app}\\{#MyAppExeName}"' in iss)
    check('Installateur n\'installe plus de .env factice',
          'DestName: ".env"' not in iss)

    # ── 3. Logo intégré (splash, connexion, À propos, favicon) ──────────
    sys.path.insert(0, BASE_DIR)
    import app_desktop
    check('Splash embeds le logo officiel',
          'data:image/png;base64' in app_desktop._splash_html())

    base_html = open(os.path.join(BASE_DIR, 'app', 'templates', 'base.html'),
                     encoding='utf-8').read()
    login_html = open(os.path.join(BASE_DIR, 'app', 'templates', 'auth', 'login.html'),
                      encoding='utf-8').read()
    check('base.html référence favicon.ico', 'favicon.ico' in base_html)
    check('login.html référence favicon.ico', 'favicon.ico' in login_html)
    check('base.html lien À propos', "url_for('dashboard.about')" in base_html)
    about_tpl = os.path.join(BASE_DIR, 'app', 'templates', 'dashboard', 'about.html')
    check('Template À propos existe avec logo',
          os.path.exists(about_tpl) and
          'logo.png' in open(about_tpl, encoding='utf-8').read())

    # ── 4. Fonctionnement de base (sans GUI) ────────────────────────────
    from desktop.single_instance import SingleInstance
    from desktop.port_manager import PortManager

    class TestSingleInstance(SingleInstance):
        _mutex_name = f'CIENTO_VALIDATION_{os.getpid()}'

    first = TestSingleInstance()
    second = TestSingleInstance()
    ok1 = first.acquire()
    ok2 = second.acquire()
    check('Instance unique : 2e acquisition refusée', ok1 and not ok2)
    first.release()

    pm = PortManager()
    port = pm.find_free_port(5005)
    check('PortManager trouve un port libre', port is not None and port > 0)

    from app import create_app, db
    from config import Config
    import urllib.request

    class DesktopConfig(Config):
        SESSION_COOKIE_SECURE = False
        REMEMBER_COOKIE_SECURE = False
        PREFERRED_URL_SCHEME = 'http'

    flask_app = create_app(DesktopConfig)

    @flask_app.route('/splash')
    def splash_route():
        return app_desktop._splash_html()

    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True

    about_resp = client.get('/a-propos', follow_redirects=True)
    check('Page /a-propos HTTP 200', about_resp.status_code == 200,
          str(about_resp.status_code))
    check('Page /a-propos affiche le logo',
          b'logo.png' in about_resp.data)
    splash_resp = client.get('/splash')
    check('Page /splash HTTP 200 avec logo',
          splash_resp.status_code == 200 and
          b'data:image/png;base64' in splash_resp.data)
    health_resp = client.get('/health')
    check('Endpoint /health OK', health_resp.status_code == 200 and
          health_resp.data == b'OK')

    # Backend réel démarré en thread (fallback dev server, waitress absent)
    def run_backend():
        try:
            from waitress import serve
            serve(flask_app, host='127.0.0.1', port=port, threads=2)
        except ImportError:
            flask_app.run(host='127.0.0.1', port=port, debug=False,
                          use_reloader=False)

    t = threading.Thread(target=run_backend, daemon=True)
    t.start()
    ready = False
    for _ in range(20):
        try:
            with urllib.request.urlopen(
                    f'http://127.0.0.1:{port}/health', timeout=2) as resp:
                if resp.status == 200 and resp.read() == b'OK':
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(0.5)
    check('Backend Flask démarre et répond /health', ready)

    # ── 5. Flag --shutdown de l'installateur ────────────────────────────
    check('app_desktop expose request_shutdown()',
          callable(getattr(app_desktop, 'request_shutdown', None)))
    check('main() accepte --shutdown', '--shutdown' in
          open(os.path.join(BASE_DIR, 'app_desktop.py'), encoding='utf-8').read())

    # ── 6. Aucune trace de l'ancien nom d'exe ───────────────────────────
    old_name = 'CientoImmobilier.exe'
    leftovers = [os.path.basename(p) for p in files_to_scan
                 if old_name in open(p, 'r', encoding='utf-8',
                                     errors='ignore').read()]
    check('Aucune référence résiduelle à CientoImmobilier.exe', not leftovers,
          ', '.join(leftovers) if leftovers else '')

    print('=' * 60)
    ok_count = sum(1 for _, ok in CHECKS if ok)
    print(f'Résultat : {ok_count}/{len(CHECKS)} vérifications réussies')
    print('=' * 60)
    return 0 if not FAILURES else 1


if __name__ == '__main__':
    sys.exit(main())
