"""Generate the atmosphere / illustration images of the user web (hero, dusk, journey covers) through the 9router image endpoint.

Reads web/scripts/ui_image_prompts.json, calls POST {9ROUTER_API_URL}/images/generations (key from .env, never printed),
writes web/public/img/gen/<name>.webp and a manifest.json (model, prompt, time). Skips files that exist unless --force.
These images are atmosphere only: never the photo of a named place, never evidence.
Run: python web/scripts/gen_ui_images.py [--force] [name ...]
"""
import base64
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

WEB = Path(__file__).resolve().parent.parent
ROOT = WEB.parent
OUT = WEB / 'public/img/gen'
PROMPTS = json.loads((WEB / 'scripts/ui_image_prompts.json').read_text(encoding='utf-8'))


def env(name):
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if line.startswith(name + '='):
            return line.split('=', 1)[1].strip().strip('"\'')
    raise SystemExit(f'{name} missing in .env')


def call(url, key, model, prompt, size):
    body = json.dumps({'model': model, 'prompt': prompt, 'size': size, 'n': 1}).encode()
    req = urllib.request.Request(url.rstrip('/') + '/images/generations', body, {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'User-Agent': 'curl/8.5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=240) as r:
        return base64.b64decode(json.load(r)['data'][0]['b64_json'])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    url, key = env('9ROUTER_API_URL'), env('9ROUTER_API_KEY')
    OUT.mkdir(parents=True, exist_ok=True)
    mf_path = OUT / 'manifest.json'
    manifest = json.loads(mf_path.read_text(encoding='utf-8')) if mf_path.exists() else {}
    for name, spec in PROMPTS.items():
        if args and name not in args:
            continue
        dest = OUT / f'{name}.webp'
        if dest.exists() and not force:
            print('skip', name)
            continue
        for attempt in (1, 2):
            try:
                raw = call(url, key, spec['model'], spec['prompt'], spec['size'])
                img = Image.open(io.BytesIO(raw)).convert('RGB')
                if img.width > 1920:
                    img = img.resize((1920, round(img.height * 1920 / img.width)), Image.LANCZOS)
                img.save(dest, 'WEBP', quality=82, method=6)
                manifest[name] = {'model': spec['model'], 'prompt': spec['prompt'], 'size': list(img.size), 'at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
                print('ok  ', name, img.size, dest.stat().st_size // 1024, 'KB')
                break
            except Exception as e:  # network / model hiccup: one retry, then move on
                print('fail', name, attempt, type(e).__name__, str(e)[:120])
                time.sleep(3)
    mf_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
