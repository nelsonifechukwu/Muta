"""Verify the local brand kit and inventory every deliverable with a checksum.

Run after build_assets.py and build_collateral.py. This script reads the finished
assets and writes manifest.json; it does not modify logo or raster artwork.
"""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
THEMES = ['on-light', 'on-dark', 'black', 'white']
KINDS = ['stacked', 'horizontal', 'wordmark', 'symbol', 'dot']
SOCIAL = {'share-card-1200x630': (1200, 630),
          'social-square-1080x1080': (1080, 1080),
          'header-1500x500': (1500, 500),
          'title-background-1920x1080': (1920, 1080)}


def expect(condition, message):
    if not condition:
        raise ValueError(message)


class LinkReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src', 'href') and value:
                self.links.append(value)


def verify_links():
    reader = LinkReader()
    reader.feed((ROOT / 'index.html').read_text())
    candidates = [(ROOT, url) for url in reader.links]
    for doc in ['README.md', 'BRAND-GUIDE.md']:
        candidates.extend((ROOT, url) for url in re.findall(r'\[[^\]]*\]\(([^)]+)\)', (ROOT / doc).read_text()))
    # CSS font references are not represented as HTML links.
    candidates.extend((ROOT, url) for url in re.findall(r"url\(['\"]([^'\"]+)['\"]\)", (ROOT / 'index.html').read_text()))
    for base, url in candidates:
        parsed = urlsplit(url)
        if parsed.scheme or not parsed.path:
            continue
        target = (base / unquote(parsed.path)).resolve()
        if target == ROOT / 'manifest.json':
            continue  # This file is the final output of this script.
        expect(target.exists(), f'Broken local link: {url}')
    return len(candidates)


def verify_assets():
    for kind in KINDS:
        for theme in THEMES:
            for ext in ['svg', 'png']:
                expect((ROOT / f'logos/muta-{kind}-{theme}.{ext}').is_file(), f'Missing {kind}/{theme}/{ext}')
    expect(len(list((ROOT / 'logos').glob('*.svg'))) == 20, 'Expected 20 logo SVGs')
    for path in list((ROOT / 'logos').glob('*.svg')) + list((ROOT / 'icons').glob('*.svg')) + list((ROOT / 'social').glob('*.svg')) + [ROOT / 'brand-board.svg']:
        root = ET.parse(path).getroot()
        for node in root.iter():
            localname = node.tag.rsplit('}', 1)[-1]
            expect(localname not in ('text', 'image', 'script', 'foreignObject'), f'Non-path artwork in {path.name}: {localname}')
            for attr, value in node.attrib.items():
                if attr.rsplit('}', 1)[-1] == 'href':
                    expect(value.startswith('#'), f'External SVG dependency in {path.name}')
        png = path.with_suffix('.png')
        if png.exists():
            with Image.open(png) as img:
                view = [float(n) for n in root.attrib['viewBox'].split()]
                expect(abs(img.height - img.width * view[3] / view[2]) <= 1, f'Aspect ratio mismatch: {png.name}')
    for path in (ROOT / 'logos').glob('*.png'):
        with Image.open(path) as img:
            alpha = img.convert('RGBA').getchannel('A')
            box = alpha.getbbox()
            expect(box is not None, f'Empty logo: {path.name}')
            expect(alpha.getextrema() == (0, 255), f'Logo missing transparent surroundings: {path.name}')
            expect(0 < box[0] < box[2] < img.width and 0 < box[1] < box[3] < img.height,
                   f'Logo reaches canvas boundary: {path.name}')
    for name, dimensions in SOCIAL.items():
        with Image.open(ROOT / f'social/{name}.png') as img:
            expect(img.size == dimensions, f'Wrong social dimensions: {name}')
    for name, width in [('muta-app-master', 1024), ('muta-touch', 180), ('muta-android-192', 192), ('muta-android-512', 512)]:
        with Image.open(ROOT / f'icons/{name}.png') as img:
            expect(img.size == (width, width), f'Wrong icon dimensions: {name}')
            expect(img.convert('RGBA').getchannel('A').getextrema() == (255, 255), f'App icon not opaque: {name}')
    with Image.open(ROOT / 'icons/favicon.ico') as ico:
        expect(ico.ico.sizes() == {(16, 16), (32, 32), (48, 48), (64, 64)}, 'Wrong ICO sizes')
        for size in [16, 32, 48, 64]:
            with Image.open(ROOT / f'icons/muta-favicon-{size}.png') as png:
                frame = ico.ico.getimage((size, size)).convert('RGBA')
                expect(ImageChops.difference(frame, png.convert('RGBA')).getbbox() is None,
                       f'ICO {size}px does not match optical PNG')


def entry(path):
    result = {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if path.suffix == '.png':
        with Image.open(path) as img:
            result.update(width=img.width, height=img.height, mode=img.mode,
                          transparent=img.convert('RGBA').getchannel('A').getextrema()[0] < 255)
    elif path.suffix == '.svg':
        root = ET.parse(path).getroot()
        result.update(viewBox=root.attrib['viewBox'], live_text=False, external_dependencies=False)
    elif path.suffix == '.ico':
        with Image.open(path) as img:
            result['sizes'] = sorted([list(size) for size in img.ico.sizes()])
    return result


def main():
    verify_assets()
    link_count = verify_links()
    files = [path for path in ROOT.rglob('*') if path.is_file()
             and path.name not in ('manifest.json', '.DS_Store')
             and '__pycache__' not in path.parts and path.suffix != '.pyc']
    entries = [entry(path) for path in sorted(files)]
    export_count = sum(path.suffix in ('.svg', '.png', '.ico') and 'reference' not in path.parts for path in files)
    manifest = {'brand': 'Muta', 'edition': 1, 'date': '2026-09-12',
                'direction': 'Open book + speaking dot (approved concept D)',
                'reference': 'reference/approved-concept.png',
                'source': 'Optically redrawn, font-free vector masters',
                'production_integration': False,
                'counts': {'inventoried_files': len(entries), 'artwork_exports': export_count,
                           'logo_arrangements': 5, 'color_treatments': 4, 'collateral_layouts': 4},
                'verified': ['SVG XML and self-contained path artwork', 'Transparent logo PNGs and unclipped alpha bounds',
                             'Social export dimensions', 'Opaque app PNGs', 'Exact optical ICO frame matches',
                             f'{link_count} local gallery/document/font links'],
                'files': entries}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Verified {export_count} artwork exports and {link_count} local links; inventoried {len(entries)} files.')


if __name__ == '__main__':
    main()
