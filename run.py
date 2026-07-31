#!/usr/bin/env python
"""
CIENTO IMMOBILIER — Entry point with desktop mode support.

Usage:
  python run.py                  # Web mode (browser)
  python run.py --desktop        # Desktop mode (PyWebView window)
  python run.py --port 5005      # Custom port
  python run.py --headless       # Server only, no window
"""
import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def run_web(port, debug):
    from app import create_app
    app = create_app()
    local_ip = get_local_ip()
    print(f"\n{'='*55}")
    print(f"  CIENTO IMMOBILIER — La Solution en Service Immobilier")
    print(f"{'='*55}")
    print(f"  Accès local     : http://127.0.0.1:{port}")
    print(f"  Accès réseau    : http://{local_ip}:{port}")
    print(f"  Mode debug      : {'Oui' if debug else 'Non'}")
    print(f"{'='*55}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)


def run_desktop_mode(port, debug, no_splash):
    from app_desktop import run_desktop
    run_desktop(port=port, no_splash=no_splash)


def run_headless(port):
    from app_desktop import run_desktop_headless
    run_desktop_headless(port=port)


def main():
    parser = argparse.ArgumentParser(description='CIENTO IMMOBILIER')
    parser.add_argument('--desktop', action='store_true', help='Desktop mode (native window)')
    parser.add_argument('--headless', action='store_true', help='Server only, no UI')
    parser.add_argument('--port', type=int, default=None, help='Port number')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--no-splash', action='store_true', help='Skip splash screen')
    args = parser.parse_args()

    port = args.port or int(os.environ.get('PORT', 5000))
    debug = args.debug or os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

    if args.headless:
        run_headless(port)
    elif args.desktop:
        run_desktop_mode(port, debug, args.no_splash)
    else:
        run_web(port, debug)


if __name__ == '__main__':
    main()
