"""Build four flat Muta collateral canvases from the approved vector masters.

Run after build_assets.py with the same Python/runtime dependencies. All lettering
is outlined, so exported SVGs remain self-contained. Edit the copy/layout below
to make future variants; do not distort or separately redraw the logo.
"""

from build_assets import PALETTE, mark, nested, save_svg, text_path


F = PALETTE['forest']
I = PALETTE['ivory']
P = PALETTE['paper']
K = PALETTE['ink']
T = PALETTE['terracotta']
L = PALETTE['terracottaLight']


def logo(kind, theme, x, y, width):
    """Place the unmodified master at its original aspect ratio."""
    w, h, body = mark(kind, theme)
    return nested(x, y, width, width * h / w, f'0 0 {w} {h}', body)


def line(x1, y1, x2, y2, color, opacity=1):
    return f'<path d="M{x1} {y1}H{x2}" stroke="{color}" stroke-opacity="{opacity}"/>' if y1 == y2 else f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-opacity="{opacity}"/>'


def center_text(text, center, baseline, size, color, font='InstrumentSans-Regular.ttf'):
    from build_assets import outlined
    _, bounds, _ = outlined(text, font)
    visual_width = (bounds[2] - bounds[0]) * size / 1000
    x = center - visual_width / 2 - bounds[0] * size / 1000
    return text_path(text, x, baseline, size, color, font)


def share_card():
    # A calm split editorial composition. Stacked lockup remains one whole logo.
    body = logo('stacked', 'on-dark', 83, 71, 402)
    body += line(555, 122, 555, 508, I, .22)
    body += text_path('MATHS & SCIENCE', 621, 183, 19, L, 'InstrumentSans-Bold.ttf')
    body += text_path('Offline-first', 619, 289, 50, I, 'LibreBaskerville-Regular.ttf')
    body += text_path('AI tutoring.', 619, 355, 50, I, 'LibreBaskerville-Regular.ttf')
    body += text_path('A learning companion.', 621, 432, 25, I)
    save_svg('social/share-card-1200x630.svg', 1200, 630, body,
             'Muta — offline-first AI tutoring for maths and science', F, 1200)


def social_square():
    # Spacious, logo-led square: no extra illustration or repeated dot motif.
    body = center_text('MATHS & SCIENCE', 540, 110, 22, T, 'InstrumentSans-Bold.ttf')
    body += logo('stacked', 'on-light', 232, 191, 616)
    body += line(392, 893, 688, 893, T, .32)
    body += center_text('Offline-first AI tutoring.', 540, 963, 33, K)
    save_svg('social/social-square-1080x1080.svg', 1080, 1080, body,
             'Muta — square brand identity card', P, 1080)


def header():
    # The identity and descriptor are kept inboard; this is a general-purpose
    # 3:1 header, not a claim about any platform's changing overlay safe zones.
    body = logo('horizontal', 'on-dark', 121, 123, 687)
    body += line(896, 160, 896, 338, I, .26)
    body += text_path('Offline-first AI tutor', 959, 237, 32, I)
    body += text_path('for maths & science.', 959, 283, 32, I)
    save_svg('social/header-1500x500.svg', 1500, 500, body,
             'Muta — general-purpose horizontal brand header', F, 1500)


def title_background():
    # Intentionally leave the large central area empty for a deck title/subtitle.
    # The logo, footer and unobtrusive rule stay fixed as a reusable title master.
    body = logo('horizontal', 'on-light', 103, 61, 525)
    body += line(120, 284, 1800, 284, F, .18)
    body += f'<rect x="120" y="338" width="78" height="6" fill="{T}"/>'
    body += text_path('Offline-first AI tutor for maths & science.', 121, 968, 30, K)
    body += f'<rect x="0" y="1032" width="1920" height="48" fill="{F}"/>'
    save_svg('social/title-background-1920x1080.svg', 1920, 1080, body,
             'Muta — presentation title background with open central writing area', P, 1920)


def main():
    share_card()
    social_square()
    header()
    title_background()
    print('Built four outlined SVG collateral canvases and exact-size PNGs.')


if __name__ == '__main__':
    main()
