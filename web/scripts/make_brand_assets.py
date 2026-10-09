"""Derive the logo files from the generated mark (web/public/img/gen/app-logo.webp).

Cuts the cream page colour away from the outside of the shield (flood fill from the border, so the cream pine inside is kept),
crops to the shield and writes web/public/img/logo.webp (transparent, 256 px) plus favicon.png / apple-touch-icon.png.
Run: python web/scripts/make_brand_assets.py
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

WEB = Path(__file__).resolve().parent.parent
SRC = WEB / 'public/img/gen/app-logo.webp'
OUT = WEB / 'public/img'
CREAM = (255, 249, 248)


def hull(points):
    """Convex hull (monotone chain); the shield is convex, so it also covers the cream cut-outs that touch its edge."""
    pts = sorted(set(points))
    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(pts), half(reversed(pts))
    return lo[:-1] + up[:-1]


def cut_outside(img):
    """Alpha mask: the convex hull of everything that is not the page cream, edge softened by about 1 px."""
    flat = img.convert('RGB')
    diff = ImageChops.difference(flat, Image.new('RGB', flat.size, CREAM)).convert('L').point(lambda v: 255 if v > 22 else 0)
    w, h = flat.size
    px = diff.load()
    edge = []
    for y in range(0, h, 2):
        xs = [x for x in range(w) if px[x, y]]
        if xs:
            edge += [(xs[0], y), (xs[-1], y)]
    mask = Image.new('L', flat.size, 0)
    ImageDraw.Draw(mask).polygon(hull(edge), fill=255)
    out = flat.convert('RGBA')
    out.putalpha(mask.filter(ImageFilter.GaussianBlur(1.0)))
    return out


def main():
    mark = cut_outside(Image.open(SRC))
    box = mark.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    mark = mark.crop(box)
    side = max(mark.size)
    sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    sq.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    sq.resize((256, 256), Image.LANCZOS).save(OUT / 'logo.webp', 'WEBP', quality=90, method=6)
    sq.resize((64, 64), Image.LANCZOS).save(OUT / 'favicon.png', optimize=True)
    apple = Image.new('RGB', (180, 180), CREAM)  # iOS rounds and fills transparency with black, so give it the page cream
    inner = sq.resize((148, 148), Image.LANCZOS)
    apple.paste(inner, (16, 16), inner)
    apple.save(OUT / 'apple-touch-icon.png', optimize=True)
    for n in ('logo.webp', 'favicon.png', 'apple-touch-icon.png'):
        print(n, (OUT / n).stat().st_size, 'B')


if __name__ == '__main__':
    main()
