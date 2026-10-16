"""Every written Google Maps review of each place in the web snapshot -> web/public/data/reviews/<id>.json.

The snapshot keeps at most three quotes per signal, so a place with 91 reviews shows ~20. The full list sits here, one
file per place (':' -> '_' like covers/), and the web fetches it only when the visitor opens the "Đánh giá" tab
(PlaceSheet.tsx, Reviews). Each review is [text, stars | null, when]; "when" is Google's own wording ("2 tuần trước").
Rating-only reviews (no text) are left out. Order is Google's.

Usage (repo root): python web/scripts/export_reviews.py [--ids a,b]
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "gmaps" / "places"
SNAPSHOT = ROOT / "web" / "public" / "data" / "snapshot-lite.json"
OUT = ROOT / "web" / "public" / "data" / "reviews"


def stars(r: str | None) -> int | None:
    m = re.match(r"\s*(\d)\s*/\s*5", r or "")
    return int(m.group(1)) if m else None


def when(s: str | None) -> str:
    return re.sub(r"\s*trên\s+Google\s*$", "", (s or "").strip()).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    args = ap.parse_args()
    ids = [i for i in args.ids.split(",") if i] or [p["id"] for p in json.loads(SNAPSHOT.read_text(encoding="utf-8"))["places"]]
    OUT.mkdir(parents=True, exist_ok=True)
    wrote = reviews = 0
    for pid in ids:
        src = DATA / pid.replace(":", "_") / "reviews.json"
        dst = OUT / f"{pid.replace(':', '_')}.json"
        if not src.exists():
            continue
        rows = [[(r["text"] or "").strip(), stars(r.get("rating")), when(r.get("published_text"))]
                for r in json.loads(src.read_text(encoding="utf-8")) if (r.get("text") or "").strip()]
        if not rows:
            dst.unlink(missing_ok=True)
            continue
        dst.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        wrote += 1
        reviews += len(rows)
    print(f"{wrote} places, {reviews} reviews -> {OUT}")


if __name__ == "__main__":
    main()
