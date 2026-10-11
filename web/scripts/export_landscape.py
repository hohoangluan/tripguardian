"""Fetch the real Đà Lạt landscape for the landing's 3D model (docs/UI_SPEC_LANDING.md §2, §4).

Writes web/src/user/landing/dem.json (elevation grid) and osm.json (water, roads, land cover, town buildings).
Sources: OpenTopoData elevation (SRTM 30 m) and OpenStreetMap through Overpass (ODbL).

  python web/scripts/export_landscape.py dem
  python web/scripts/export_landscape.py osm
"""
import base64
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / 'landscape'
UA = 'tripguardian-landing/1.0 (landing 3D model)'
# the area the model draws: the map area (BOUNDS in terrain.ts) plus the hills around it
LAT0, LAT1, LNG0, LNG1 = 11.695, 12.195, 108.19, 108.79
STEP = 0.003  # degrees per elevation sample, ~330 m
LC = 2  # land-cover samples per elevation sample, per axis
MIRRORS = ['https://overpass-api.de/api/interpreter']


def get(url, data=None, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Accept': '*/*'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network flake: wait and retry
            print('  retry', i, str(e)[:80], flush=True)
            time.sleep(4 + 6 * i)
    raise SystemExit('gave up: ' + url)


def dem():
    cols = int(round((LNG1 - LNG0) / STEP)) + 1
    rows = int(round((LAT1 - LAT0) / STEP)) + 1
    pts = [(LAT1 - r * STEP, LNG0 + c * STEP) for r in range(rows) for c in range(cols)]  # row 0 = north
    out = []
    for i in range(0, len(pts), 100):
        chunk = pts[i:i + 100]
        q = '|'.join(f'{p[0]:.4f},{p[1]:.4f}' for p in chunk)
        res = json.loads(get('https://api.opentopodata.org/v1/srtm30m?locations=' + q))['results']
        out += [r['elevation'] if r['elevation'] is not None else 1400 for r in res]
        if (i // 100) % 20 == 0:
            print(f'dem {i}/{len(pts)}', flush=True)
        time.sleep(1.1)
    arr = np.array(out, dtype='<i2').reshape(rows, cols)
    print('elevation', arr.min(), arr.max())
    (OUT / 'dem.json').write_text(json.dumps({'lat0': LAT0, 'lat1': LAT1, 'lng0': LNG0, 'lng1': LNG1, 'cols': cols, 'rows': rows, 'data': base64.b64encode(arr.tobytes()).decode()}))


def overpass(query):
    body = urllib.parse.urlencode({'data': query}).encode()
    for i in range(10):
        url = MIRRORS[i % len(MIRRORS)]
        try:
            raw = get(url, body, tries=1)
            if raw.lstrip().startswith(b'{'):
                return json.loads(raw)
            print('  overpass busy', url, flush=True)
        except SystemExit:
            pass
        time.sleep(10 + 5 * i)
    raise SystemExit('overpass gave up')


def tiles(n=3):
    la = [LAT0 + (LAT1 - LAT0) * i / n for i in range(n + 1)]
    lo = [LNG0 + (LNG1 - LNG0) * i / n for i in range(n + 1)]
    return [f'({la[i]:.4f},{lo[j]:.4f},{la[i + 1]:.4f},{lo[j + 1]:.4f})' for i in range(n) for j in range(n)]


def tiled(body, n=3):
    """Run `body` (with {b} for the box) over a grid of tiles: the public servers drop big queries."""
    els, seen = [], set()
    for b in tiles(n):
        for e in overpass('[out:json][timeout:120];' + body.replace('{b}', b))['elements']:
            if (e['type'], e['id']) not in seen:
                seen.add((e['type'], e['id']))
                els.append(e)
        print('  tile', b, len(els), flush=True)
        time.sleep(2)
    return {'elements': els}


def rings(el):
    """Closed rings of a way or multipolygon relation, with their role (outer / inner)."""
    if el['type'] == 'way':
        g = [(p['lat'], p['lon']) for p in el.get('geometry', [])]
        return [('outer', g)] if len(g) > 3 else []
    out = []
    for role in ('outer', 'inner'):
        segs = [[(p['lat'], p['lon']) for p in m['geometry']] for m in el.get('members', []) if m.get('role') == role and m.get('geometry')]
        while segs:
            ring = segs.pop(0)
            grew = True
            while grew and ring[0] != ring[-1]:
                grew = False
                for s in segs:
                    if s[0] == ring[-1]: ring += s[1:]
                    elif s[-1] == ring[-1]: ring += s[::-1][1:]
                    elif s[-1] == ring[0]: ring = s[:-1] + ring
                    elif s[0] == ring[0]: ring = s[::-1][:-1] + ring
                    else: continue
                    segs.remove(s)
                    grew = True
                    break
            if len(ring) > 3: out.append((role, ring))
    return out


def simplify_ring(ring, tol):
    """A closed ring has no baseline to measure from: split it at the point farthest from the start."""
    far = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    return simplify(ring[:far + 1], tol)[:-1] + simplify(ring[far:], tol)


def simplify(pts, tol):
    if len(pts) < 3: return pts
    (y0, x0), (y1, x1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-12
    k, dmax = 0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][1] - x0) - dx * (pts[i][0] - y0)) / n
        if d > dmax: k, dmax = i, d
    if dmax <= tol: return [pts[0], pts[-1]]
    return simplify(pts[:k + 1], tol)[:-1] + simplify(pts[k:], tol)


def osm():
    water = tiled('(way["natural"="water"]{b};relation["natural"="water"]{b};way["waterway"="riverbank"]{b};);out geom;', 2)
    print('water', len(water['elements']), flush=True)
    land = tiled('(way["natural"~"wood|scrub"]{b};relation["natural"~"wood|scrub"]{b};way["landuse"~"forest|farmland|farmyard|orchard|plant_nursery|greenhouse_horticulture|residential|commercial|industrial|meadow|grass|recreation_ground"]{b};relation["landuse"~"forest|farmland|orchard|residential"]{b};way["building"="greenhouse"]{b};way["leisure"~"park|golf_course"]{b};);out geom;', 4)
    print('land', len(land['elements']), flush=True)
    roads = tiled('way["highway"~"^(trunk|primary|secondary|tertiary)$"]{b};out geom;', 2)
    print('roads', len(roads['elements']), flush=True)
    town = overpass('[out:json][timeout:120];way["building"](11.915,108.405,11.985,108.485);out center;')
    print('buildings', len(town['elements']), flush=True)
    named = {}
    cols = int(round((LNG1 - LNG0) / STEP)) + 1
    rows = int(round((LAT1 - LAT0) / STEP)) + 1
    W, H = (cols - 1) * LC + 1, (rows - 1) * LC + 1

    def px(lat, lng):
        return ((lng - LNG0) / (LNG1 - LNG0) * (W - 1), (LAT1 - lat) / (LAT1 - LAT0) * (H - 1))

    # land-cover classes: 0 open, 1 forest / scrub, 2 farmland and greenhouses, 3 town, 4 park / meadow
    cover = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(cover)

    def klass(t):
        if t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest': return 1
        if t.get('landuse') in ('farmland', 'farmyard', 'orchard', 'plant_nursery', 'greenhouse_horticulture') or t.get('building') == 'greenhouse': return 2
        if t.get('landuse') in ('residential', 'commercial', 'industrial'): return 3
        return 4

    for el in sorted(land['elements'], key=lambda e: klass(e.get('tags', {})) == 1 and -1 or 0):
        k = klass(el.get('tags', {}))
        for role, ring in rings(el):
            d.polygon([px(*p) for p in ring], fill=k if role == 'outer' else 0)
    lakes = []
    for el in water['elements']:
        t = el.get('tags', {})
        for role, ring in rings(el):
            if role != 'outer': continue
            lat = sum(p[0] for p in ring) / len(ring)
            lng = sum(p[1] for p in ring) / len(ring)
            area = abs(sum(ring[i][1] * ring[(i + 1) % len(ring)][0] - ring[(i + 1) % len(ring)][1] * ring[i][0] for i in range(len(ring)))) / 2 * 110.6 * 108.9
            if area < 0.04 and not t.get('name'): continue  # ponds under 4 ha
            lakes.append({'name': t.get('name'), 'area_km2': round(area, 3), 'ring': [[round(p[0], 5), round(p[1], 5)] for p in simplify_ring(ring, 0.00006)], 'lat': round(lat, 4), 'lng': round(lng, 4)})
    lakes.sort(key=lambda l: -l['area_km2'])
    print('lakes', [(l['name'], l['area_km2']) for l in lakes[:12]])
    rd = []
    for el in roads['elements']:
        g = [(p['lat'], p['lon']) for p in el.get('geometry', [])]
        g = simplify(g, 0.00012)
        if len(g) > 1: rd.append({'k': el['tags']['highway'], 'p': [[round(p[0], 5), round(p[1], 5)] for p in g]})
    pts = [(e['center']['lat'], e['center']['lon']) for e in town['elements'] if 'center' in e]
    step = max(1, len(pts) // 2200)
    houses = [[round(a, 5), round(b, 5)] for a, b in pts[::step]]
    (OUT / 'osm.json').write_text(json.dumps({
        'bounds': [LAT0, LAT1, LNG0, LNG1], 'cover': {'w': W, 'h': H, 'data': base64.b64encode(np.array(cover, dtype='u1').tobytes()).decode()},
        'lakes': lakes, 'roads': rd, 'houses': houses, 'named': named,
    }, separators=(',', ':')))
    print('houses', len(houses), 'roads', len(rd))


def water():
    """Re-fetch only the lakes into the existing osm.json."""
    data = json.loads((OUT / 'osm.json').read_text())
    w = tiled('(way["natural"="water"]["name"]{b};relation["natural"="water"]["name"]{b};way["natural"="water"]{b};);out geom;', 3)
    lakes = []
    for el in w['elements']:
        t = el.get('tags', {})
        for role, ring in rings(el):
            if role != 'outer': continue
            area = abs(sum(ring[i][1] * ring[(i + 1) % len(ring)][0] - ring[(i + 1) % len(ring)][1] * ring[i][0] for i in range(len(ring)))) / 2 * 110.6 * 108.9
            if area < 0.04 and not t.get('name'): continue
            lakes.append({'name': t.get('name'), 'area_km2': round(area, 3), 'ring': [[round(p[0], 5), round(p[1], 5)] for p in simplify_ring(ring, 0.00006)],
                          'lat': round(sum(p[0] for p in ring) / len(ring), 4), 'lng': round(sum(p[1] for p in ring) / len(ring), 4)})
    lakes.sort(key=lambda l: -l['area_km2'])
    data['lakes'] = lakes
    (OUT / 'osm.json').write_text(json.dumps(data, separators=(',', ':')))
    print('lakes', [(l['name'], l['area_km2'], len(l['ring'])) for l in lakes[:10]])


if __name__ == '__main__':
    {'dem': dem, 'osm': osm, 'water': water}[sys.argv[1]]()
