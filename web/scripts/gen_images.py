"""Generate the web prototype's illustrations through the local 9router proxy.

Illustrations only (category art, share image, empty states): never a picture presented as a real place.
Usage: python web/scripts/gen_images.py [name ...]   (default: all missing)
"""

import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "img"
MODELS = ["cx/gpt-5.6-sol", "ag/gemini-3.8-flash", "ag/gemini-3.7-flash-high"]  # cx/gpt-image-1 is rejected; cx/gpt-5.6-sol draws

STYLE = (
    "Low-poly 3D illustration with flat-shaded facets, calm and premium, soft volumetric morning mist, "
    "Da Lat Vietnam highlands. Strict palette: misty blue-grey #D5DEE0, deep pine green #1E3A34, lake teal #2F5D6B, "
    "a single warm accent of wild-sunflower yellow #F2B31B. No text, no letters, no logos, no people, no watermark. "
)

# User Web screen headers: vintage travel-poster look, separate from the landing's low-poly 3D world.
POSTER = (
    "Vintage screen-printed travel poster illustration, flat layered shapes with soft gradients, subtle risograph grain, "
    "Da Lat Vietnam highlands. Strict palette: warm cream #F4F0E6, deep pine green #1D3B33, lake teal #2F5D6B, "
    "misty blue-grey #D5DEE0, one warm accent of wild-sunflower yellow #F2B31B. Wide panoramic composition, calm, generous sky. "
    "No text, no letters, no logos, no people, no watermark, no border. "
)

IMAGES = {
    "cat-sight": ("1536x1024", "A small wooden lookout pavilion on a grassy hilltop above layered pine ridges, a valley of fog below."),
    "cat-nature": ("1536x1024", "A slender waterfall falling through a pine forest into a teal pool, mist rising, a few yellow wild sunflowers at the edge."),
    "cat-food": ("1536x1024", "A steaming ceramic coffee cup on a wooden balcony ledge overlooking pine hills in fog, warm light from inside a cafe."),
    "cat-shop": ("1536x1024", "A cozy night market stall with lanterns, baskets of strawberries and jars of artichoke tea, pine hills silhouetted behind."),
    "share": ("1536x1024", "Wide panorama of pine-covered hills around a teal lake, five glowing yellow diamond-shaped markers on the hills "
              "connected by one thin golden path, fog lifting at sunrise, generous empty mist in the left third for a title."),
    "empty": ("1536x1024", "A single small glowing lantern standing on a mossy stone in thick fog, a faint pine silhouette, lots of negative space."),
    "poster-start": ("1536x1024", "A misty pine valley at dawn, layered ridges fading into fog, a winding road, wild sunflowers in the foreground.", POSTER),
    "poster-setup": ("1536x1024", "A vintage motorbike with a backpack parked on a curving hill road, pine ridges and a far valley behind.", POSTER),
    "poster-discover": ("1536x1024", "View from inside a wooden cafe: a coffee cup on the window sill, pine hills in morning fog outside.", POSTER),
    "poster-shortlist": ("1536x1024", "Rolling pine-covered hills with a few small yellow diamond-shaped markers on hilltops, fog in the valleys.", POSTER),
    "poster-feasibility": ("1536x1024", "A dotted golden route line winding across terraced tea hills between pine forests, a pale sun.", POSTER),
    "poster-plan": ("1536x1024", "Sunrise over a calm lake ringed by pine trees, a small wooden pier, soft clouds.", POSTER),
    "poster-profile": ("1536x1024", "A traveler's notebook, a folded paper map and dried wild sunflowers on a wooden table by a window with pine hills.", POSTER),
    "poster-close": ("1536x1024", "Grand panorama of pine ridges under warm early light rays, a field of wild sunflowers in the foreground.", POSTER),
    "admin-mark": ("1536x1024", "A minimal emblem: one low-poly pine tree inside a softly glowing yellow diamond outline on deep pine green background."),
}


def env() -> tuple[str, str]:
    vals = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals["9ROUTER_API_URL"].rstrip("/"), vals["9ROUTER_API_KEY"]


def generate(url: str, key: str, model: str, size: str, prompt: str, style: str = STYLE) -> bytes:
    body = json.dumps({"model": model, "prompt": style + prompt, "size": size, "n": 1}).encode()
    req = urllib.request.Request(f"{url}/images/generations", body,
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    item = data["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    with urllib.request.urlopen(item["url"], timeout=120) as r:
        return r.read()


def main() -> None:
    url, key = env()
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or [n for n in IMAGES if not (OUT / f"{n}.webp").exists()]
    for name in names:
        size, prompt, *style = IMAGES[name]
        for model in MODELS:
            try:
                raw = generate(url, key, model, size, prompt, *style)
            except Exception as e:  # noqa: BLE001 - try the next model, report at the end
                print(f"{name}: {model} failed: {str(e)[:160]}")
                continue
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((1600, 1600))
            img.save(OUT / f"{name}.webp", quality=80)
            print(f"{name}: {model} -> {name}.webp {img.size} ({(OUT / f'{name}.webp').stat().st_size // 1024} KB)")
            break


if __name__ == "__main__":
    main()
