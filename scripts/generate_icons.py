# -*- coding: utf-8 -*-
"""
CIENTO IMMOBILIER — Générateur d'icônes Windows officielles.

Produit toutes les versions d'icônes à partir du logo officiel
(assets/splash.png) :
  - assets/app.ico         (16, 32, 48, 64, 128, 256) — icône exécutable
  - assets/installer.ico   (16, 32, 48, 64, 128, 256) — icône installateur
  - assets/icons/<N>.png   versions PNG individuelles
  - app/static/logo.png    logo carré 512 px (pages web / À propos)
  - app/static/favicon.ico (16, 32, 48, 64)            — favicon navigateur
  - assets/wizard_left.bmp  (164x314)                  — image assistant Inno
  - assets/wizard_small.bmp (55x58)                    — image petit assistant

Usage : python scripts/generate_icons.py
"""
import os
import sys
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_SOURCE = os.path.join(BASE_DIR, 'assets', 'splash.png')
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ICONS_DIR = os.path.join(ASSETS_DIR, 'icons')
STATIC_DIR = os.path.join(BASE_DIR, 'app', 'static')

ICO_SIZES = [16, 32, 48, 64, 128, 256]
FAVICON_SIZES = [16, 32, 48, 64]


def square_crop(img):
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def save_ico(path, source, sizes):
    """Enregistre un ICO multi-tailles Windows à partir d'une image source carrée.

    Pillow génère automatiquement chaque taille demandée à partir de l'image
    source (qui doit être au moins aussi grande que la plus grande taille).
    """
    source.save(path, format='ICO', sizes=sizes)


def main():
    if not os.path.exists(LOGO_SOURCE):
        print(f'[ERROR] Logo introuvable : {LOGO_SOURCE}')
        return 1

    os.makedirs(ICONS_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)

    source = Image.open(LOGO_SOURCE).convert('RGBA')
    square = square_crop(source)

    frames = []
    for size in ICO_SIZES:
        frame = square.resize((size, size), Image.LANCZOS)
        frames.append(frame)
        frame.save(os.path.join(ICONS_DIR, f'{size}.png'))

    icon_256 = square.resize((256, 256), Image.LANCZOS)
    save_ico(os.path.join(ASSETS_DIR, 'app.ico'), icon_256,
             [(s, s) for s in ICO_SIZES])
    save_ico(os.path.join(ASSETS_DIR, 'installer.ico'), icon_256,
             [(s, s) for s in ICO_SIZES])

    favicon_frames = []
    for size in FAVICON_SIZES:
        favicon_frames.append(square.resize((size, size), Image.LANCZOS))
    favicon_frames[-1].save(
        os.path.join(STATIC_DIR, 'favicon.ico'),
        format='ICO',
        sizes=[(s, s) for s in FAVICON_SIZES],
    )

    square.resize((512, 512), Image.LANCZOS).save(
        os.path.join(STATIC_DIR, 'logo.png'), format='PNG'
    )

    left_bmp = Image.new('RGB', (164, 314), 'white')
    left_bmp.paste(square.resize((164, 164), Image.LANCZOS), (0, 75))
    left_bmp.save(os.path.join(ASSETS_DIR, 'wizard_left.bmp'), format='BMP')

    small_bmp = Image.new('RGB', (55, 58), 'white')
    small_bmp.paste(square.resize((55, 55), Image.LANCZOS), (0, 1))
    small_bmp.save(os.path.join(ASSETS_DIR, 'wizard_small.bmp'), format='BMP')

    print('[OK] Icônes générées :')
    for rel in [
        'assets/app.ico',
        'assets/installer.ico',
        'app/static/favicon.ico',
        'app/static/logo.png',
        'assets/icons/16.png',
        'assets/icons/32.png',
        'assets/icons/48.png',
        'assets/icons/64.png',
        'assets/icons/128.png',
        'assets/icons/256.png',
        'assets/wizard_left.bmp',
        'assets/wizard_small.bmp',
    ]:
        path = os.path.join(BASE_DIR, rel)
        size = os.path.getsize(path)
        print(f'  {rel} ({size} octets)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
