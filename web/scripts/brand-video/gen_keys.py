"""Generate illustrated keyframes for the brand video via 9router (cx/gpt-5.6-sol)."""
import base64, io, json, sys, concurrent.futures as cf, urllib.request, pathlib
from PIL import Image

env = {}
for line in open(pathlib.Path(__file__).parents[3] / '.env', encoding='utf-8'):
    if '=' in line and not line.startswith('#'):
        k, v = line.rstrip('\r\n').split('=', 1)
        env[k] = v.strip('"')
URL, KEY = env['9ROUTER_API_URL'].rstrip('/'), env['9ROUTER_API_KEY']
OUT = pathlib.Path(__file__).parent / 'keys'

STYLE = (
    'Risograph and screen-print woodblock illustration, matching a travel poster series: '
    'warm cream paper sky, layered misty teal-blue mountains, deep pine green forests, muted slate-blue lake, '
    'small accents of golden wild sunflowers (da quy). Fine paper grain, flat layered depth, soft morning mist, calm and premium. '
    'Wide cinematic 16:9 landscape composition with clear depth layers, suitable for slow camera motion. '
    'Absolutely no text, no letters, no numbers, no logos, no watermark, no UI.'
)
SCENES = {
    'k1-saved': 'Dozens of small instant-photo cards float and overlap in soft morning fog above a pine valley in the Vietnamese highlands. '
                'Each card shows a tiny illustrated highland scene: a pine hill, a lake with a jetty, a wooden cafe, a flower field, a waterfall, tea rows. '
                'Slightly overwhelming, too many to choose from; cards drift at different depths, some blurred in the foreground.',
    'k2-crossroads': 'A lone young traveler with a small backpack, seen from behind at mid distance, stands where a forest trail splits into many paths '
                     'through tall pine trees in thick morning fog. Small orange ribbons tied on trees mark every path. Contemplative, a little lost, quiet.',
    'k3-sunrise': 'Two friends on a motorbike, seen from behind at mid distance, ride a gently winding road on a hillside covered in golden wild sunflowers at sunrise. '
                  'Below, a misty pine valley and a calm lake; soft sun rays through the fog. Warm, hopeful, the feeling of a trip that went right.',
}

def gen(name, i):
    body = json.dumps({'model': 'cx/gpt-5.6-sol', 'prompt': f'{SCENES[name]} {STYLE}', 'size': '1536x1024', 'n': 1}).encode()
    req = urllib.request.Request(f'{URL}/images/generations', body, {'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)['data'][0]
    data = base64.b64decode(d['b64_json']) if d.get('b64_json') else urllib.request.urlopen(d['url']).read()
    p = OUT / f'{name}-{i}.jpg'
    Image.open(io.BytesIO(data)).convert('RGB').save(p, quality=93)
    return str(p)

jobs = [(n, i) for n in (sys.argv[1:] or SCENES) for i in (1, 2)]
with cf.ThreadPoolExecutor(3) as ex:
    for f in cf.as_completed([ex.submit(gen, n, i) for n, i in jobs]):
        try:
            print('ok', f.result(), flush=True)
        except Exception as e:
            print('fail', e, flush=True)
