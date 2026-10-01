"""Generate the web prototype's illustrations through the local 9router proxy.

Illustrations only (category art, share image, empty states): never a picture presented as a real place.
Usage: python web/scripts/gen_images.py [name ...]   (default: all missing)
"""

import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "img"
MODELS = ["ag/gemini-3.8-flash", "ag/gemini-3.7-flash-high", "ag/gemini-3.6-flash-high"]  # cx/gpt-image-1 is rejected for ChatGPT-account Codex

STYLE = (
    "Low-poly 3D illustration with flat-shaded facets, calm and premium, soft volumetric morning mist, "
    "Da Lat Vietnam highlands. Strict palette: misty blue-grey #D5DEE0, deep pine green #1E3A34, lake teal #2F5D6B, "
    "a single warm accent of wild-sunflower yellow #F2B31B. No text, no letters, no logos, no people, no watermark. "
)

IMAGES = {
    "cat-sight": ("1536x1024", "A small wooden lookout pavilion on a grassy hilltop above layered pine ridges, a valley of fog below."),
    "cat-nature": ("1536x1024", "A slender waterfall falling through a pine forest into a teal pool, mist rising, a few yellow wild sunflowers at the edge."),
    "cat-food": ("1536x1024", "A steaming ceramic coffee cup on a wooden balcony ledge overlooking pine hills in fog, warm light from inside a cafe."),
    "cat-shop": ("1536x1024", "A cozy night market stall with lanterns, baskets of strawberries and jars of artichoke tea, pine hills silhouetted behind."),
    "share": ("1536x1024", "Wide panorama of pine-covered hills around a teal lake, five glowing yellow diamond-shaped markers on the hills "
              "connected by one thin golden path, fog lifting at sunrise, generous empty mist in the left third for a title."),
    "empty": ("1536x1024", "A single small glowing lantern standing on a mossy stone in thick fog, a faint pine silhouette, lots of negative space."),
    "admin-mark": ("1536x1024", "A minimal emblem: one low-poly pine tree inside a softly glowing yellow diamond outline on deep pine green background."),
}


def env() -> tuple[str, str]:
    vals = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"')
    return vals["9ROUTER_API_URL"].rstrip("/"), vals["9ROUTER_API_KEY"]


def generate(url: str, key: str, model: str, size: str, prompt: str) -> bytes:
    body = json.dumps({"model": model, "prompt": STYLE + prompt, "size": size, "n": 1}).encode()
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
    names = sys.argv[1:] or [n for n in IMAGES if not any(OUT.glob(f"{n}.*"))]
    for name in names:
        size, prompt = IMAGES[name]
        for model in MODELS:
            try:
                raw = generate(url, key, model, size, prompt)
            except Exception as e:  # noqa: BLE001 - try the next model, report at the end
                print(f"{name}: {model} failed: {str(e)[:160]}")
                continue
            ext = "png" if raw[:4] == b"\x89PNG" else "jpg"
            (OUT / f"{name}.{ext}").write_bytes(raw)
            print(f"{name}: {model} -> {name}.{ext} ({len(raw) // 1024} KB)")
            break


if __name__ == "__main__":
    main()
