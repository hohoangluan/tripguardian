"""Pick the real places the landing shows and write web/src/user/landing/places.json (+ stats.json, points.json).

Reads web/public/data/snapshot.json + covers.json (both built offline); copies only values the
snapshot already has. Anything the snapshot lacks stays absent so the UI shows "Chưa có thông tin".
Run: python web/scripts/pick_landing_places.py
"""
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
SNAP = json.loads((WEB / 'public/data/snapshot.json').read_text(encoding='utf-8'))
COVERS = json.loads((WEB / 'public/data/covers.json').read_text(encoding='utf-8'))
ROOT_DATA = WEB.parent / 'data'

# (name match, exact?, short name, kind) 
PICKS = [
    ('Đỉnh đèo Ngoạn Mục', False, 'Đỉnh đèo Ngoạn Mục'),
    ('Thiên Đường Săn Mây', False, 'Thiên Đường Săn Mây Cầu Đất'),
    ('Euro Garden', False, 'Euro Garden Cầu Đất'),
    ('Hồ Tuyền Lâm', True, 'Hồ Tuyền Lâm'),
    ('Thung lũng Tình Yêu', True, 'Thung lũng Tình Yêu'),
    ('LANGBIANG LAND', False, 'Langbiang Land'),
    ('Khu du lịch Thác Datanla', True, 'Thác Datanla'),
    ('Hồ Xuân Hương', True, 'Hồ Xuân Hương'),
    ('Quảng trường Lâm Viên', True, 'Quảng trường Lâm Viên'),
    ('Dinh III Bảo Đại', True, 'Dinh III Bảo Đại'),
    ('Chợ Đêm Đà Lạt', True, 'Chợ Đêm Đà Lạt'),
    ('Tiệm cà phê Thênh Thang', True, 'Tiệm cà phê Thênh Thang'),
    ('Quán Của Thời Thanh Xuân', True, 'Quán Của Thời Thanh Xuân'),
    ('Hôm Nào Cà Phê?', True, 'Hôm Nào Cà Phê?'),
    ('Tiệm cà phê Vùng Ngoại Ô', True, 'Tiệm cà phê Vùng Ngoại Ô'),
    ('Nhà Bên Rừng', True, 'Nhà Bên Rừng'),
    ('An - Tuyền Lâm', True, 'An - Tuyền Lâm'),
    ('Nhà Lồng Coffee', True, 'Nhà Lồng Coffee'),
    ('Coffee Em và Trịnh', True, 'Coffee Em và Trịnh'),
    ('Nậm Nướng Đà Lạt', True, 'Nậm Nướng Đà Lạt'),
    ('Hoàng hôn 3000', True, 'Hoàng hôn 3000'),
    ('DEEM (ĐÊM) Cocktail Bar Đà Lạt', True, 'DEEM Cocktail Bar'),
    ('Củi Bakery', False, 'Củi Bakery'),
    ('CHẠM', True, 'CHẠM — kem bơ'),
]

DAYS = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật']


def area_of(lat, lng):
    if lat > 12.0:
        return 'Lạc Dương'
    if lng > 108.62:
        return 'Đèo Ngoạn Mục'
    if lng > 108.55:
        return 'Cầu Đất'
    if lat < 11.91 and lng < 108.46:
        return 'Tuyền Lâm'
    if lng > 108.465:
        return 'Trại Mát'
    return 'Trung tâm'


def hours_of(p):
    lines = p.get('hoursText') or []
    spans = {re.sub(r'^[^\d]*', '', ln) for ln in lines}
    if len(spans) == 1:
        return spans.pop() or None
    return None


def find(name, exact):
    pool = [p for p in SNAP['places'] if p['id'] in COVERS]
    if exact:
        hit = [p for p in pool if p['name'] == name]
    else:
        hit = [p for p in pool if name.lower() in p['name'].lower()]
    hit.sort(key=lambda p: -(p.get('reviewCount') or 0))
    return hit[0] if hit else None


MEDIA = {'/media/gmaps/': ROOT_DATA / 'gmaps/places', '/media/tiktok/': ROOT_DATA / 'tiktok/videos'}


def exists(src):
    for prefix, base in MEDIA.items():
        if src.startswith(prefix):
            return (base / src[len(prefix):]).exists()
    return False


def pack(p, short):
    quotes = []
    for f in sorted(p.get('features') or [], key=lambda f: -(f.get('n') or 0)):
        for q in f.get('quotes') or []:
            if 25 <= len(q['text']) <= 140 and len(quotes) < 2:
                quotes.append({'text': q['text'], 'date': q.get('date'), 'source': q.get('source')})
    vids = [
        {'url': v['url'], 'handle': v['handle'], 'desc': (v.get('desc') or '')[:140]}
        for v in (p.get('videos') or [])[:2]
    ]
    out = {
        'id': p['id'],
        'name': short,
        'group': p['group'],
        'category': p['category'],
        'area': area_of(p['lat'], p['lng']),
        'lat': p['lat'],
        'lng': p['lng'],
        'rating': round(p['rating'], 1) if p.get('rating') else None,
        'reviews': p.get('reviewCount'),
        'voices': p.get('voices'),
        'hours': hours_of(p),
        'price': p.get('priceRange'),
        'crowd': p.get('crowdByTime'),
        'photos': [ph for ph in COVERS[p['id']] if exists(ph['src'])][:4],
        'quotes': quotes,
        'videos': vids,
        'mapsUrl': p.get('mapsUrl'),
        'asof': p.get('asOf'),
    }
    return {k: v for k, v in out.items() if v not in (None, '', [], {})}


def main():
    out, missing = [], []
    for name, exact, short in PICKS:
        p = find(name, exact)
        if not p:
            missing.append(name)
            continue
        packed = pack(p, short)
        if not packed.get('photos'):
            missing.append(name + ' (no photo on disk)')
            continue
        out.append(packed)
    dest = WEB / 'src/user/landing/places.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    # numbers the landing may print: counted from the real build, never typed by hand
    stats = {'places': len(SNAP['places']), 'withPhotos': sum(1 for p in SNAP['places'] if p['id'] in COVERS), 'asOf': SNAP.get('asOf')}
    (WEB / 'src/user/landing/stats.json').write_text(json.dumps(stats, ensure_ascii=False), encoding='utf-8')
    # every place as a pin on the landing's 3D map: coordinates only, rounded to ~10 m
    points = [[round(p['lat'], 4), round(p['lng'], 4)] for p in SNAP['places'] if p.get('lat') and p.get('lng')]
    (WEB / 'src/user/landing/points.json').write_text(json.dumps(points, separators=(',', ':')), encoding='utf-8')
    print(f'{len(out)} places -> {dest}; stats {stats}; missing: {missing}')
    for p in out:
        print(f"  {p['name'][:34]:34} {p['area']:14} {p['group']:5} r={p.get('rating')} ph={len(p['photos'])} q={len(p.get('quotes', []))} v={len(p.get('videos', []))} h={p.get('hours')}")


if __name__ == '__main__':
    main()
