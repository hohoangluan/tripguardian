"""Self-host the fonts the user web uses (one-off, rerun to refresh): web/public/fonts/*.woff2 + fonts.css.

Why: the Google Fonts stylesheet and files sit on two other origins (two more DNS + TLS handshakes, and the CSS
blocks the first text). Same-origin files ride the connection the page already has, are cached for a year, and the
two the landing needs first are preloaded in index.html. Only the vietnamese and latin subsets are kept (a rare character outside them falls back to the system font).
usage: python web/scripts/self_host_fonts.py
"""
import hashlib
import re
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public" / "fonts"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
URL = ("https://fonts.googleapis.com/css2?family=Inter:wght@400..700&family=JetBrains+Mono:wght@400..600"
       "&family=Lora:ital,wght@0,500..700;1,500..700&family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap")
KEEP = {"vietnamese", "latin"}


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        old.unlink()
    css = get(URL).decode()
    blocks = re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S)
    out = []
    for subset, block in blocks:
        if subset not in KEEP:
            continue
        family = re.search(r"font-family: '([^']+)'", block).group(1)
        style = re.search(r"font-style: (\w+)", block).group(1)
        weight = re.search(r"font-weight: ([\d ]+);", block).group(1).replace(" ", "-")
        src = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        data = get(src)
        name = f"{family.replace(' ', '')}-{weight}-{style}-{subset}.{hashlib.sha1(data).hexdigest()[:8]}.woff2"
        (OUT / name).write_bytes(data)
        out.append(block.replace(src, f"/fonts/{name}"))
        print(name, len(data))
    (OUT / "fonts.css").write_text("\n".join(out) + "\n")
    # What the first screen needs goes into index.html as preloads: body text and the headline face, Vietnamese + Latin.
    first = [n for n in sorted(x.name for x in OUT.glob("*.woff2"))
             if re.match(r"(BeVietnamPro-400-normal|Lora-500-700-normal)-(vietnamese|latin)\.", n)]
    tags = "\n".join(f'    <link rel="preload" as="font" type="font/woff2" href="/fonts/{n}" crossorigin />' for n in first)
    page = OUT.parent.parent / "index.html"
    html = re.sub(r"(<!-- fonts:preload -->).*?(<!-- /fonts:preload -->)", lambda m: f"{m[1]}\n{tags}\n    {m[2]}", page.read_text(), flags=re.S)
    page.write_text(html)


main()
