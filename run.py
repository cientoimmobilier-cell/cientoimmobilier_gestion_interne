import os
import socket

from app import create_app

app = create_app()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    local_ip = get_local_ip()

    print(f"\n{'='*55}")
    print(f"  CIENTO IMMOBILIER — La Solution en Service Immobilier")
    print(f"{'='*55}")
    print(f"  Accès local     : http://127.0.0.1:{port}")
    print(f"  Accès réseau    : http://{local_ip}:{port}")
    print(f"  Mode debug      : {'Oui' if debug else 'Non'}")
    print(f"{'='*55}")
    print(f"  Les autres appareils du réseau peuvent accéder")
    print(f"  au logiciel via : http://{local_ip}:{port}")
    print(f"{'='*55}\n")

    app.run(host='0.0.0.0', port=port, debug=debug)
