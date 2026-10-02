"""Dev check, needs the UIT network: re-observe a few real places with the shipped prompt and print the effort /
booking / weather / visit_duration observations next to the stored ones. Nothing is written. From the repo root:
python scripts/observe_places_eval.py"""
import asyncio, glob, json, os, sys, collections, random
sys.path.insert(0, "src")
from corpus.observe.gmaps import extract
from corpus.ontology import load
NAMES = ["Đỉnh Langbiang", "Thác Dasar", "Thông Chill", "Tiệm Nướng Trạm Dừng Chill", "Vườn dâu 88", "Mountain Chill"]
FEATS = ["steep_or_stairs", "long_walk", "weather_exposed", "booking_needed", "visit_duration", "elderly", "rough_road_access"]
async def main():
    ont = load(); slots = extract.Slots(await extract._providers())
    dirs = {}
    for f in glob.glob("data/gmaps/places/*/place.json"):
        n = json.load(open(f, encoding="utf-8"))["name"]
        for k in NAMES:
            if n.startswith(k) and k not in dirs: dirs[k] = os.path.dirname(f)
    async def one(k, d):
        stem = os.path.basename(d)
        bad = extract.bad_review_ids(extract.data_dir() / "gmaps" / "qc" / f"{stem}.json")
        new = await extract.observe_place(slots, extract.Path(d), ont, "Đà Lạt", bad)
        oldf = f"data/gmaps/observations/{stem}.json"
        old = json.load(open(oldf, encoding="utf-8")) if os.path.exists(oldf) else {"observations": []}
        return k, old, new
    rows = []
    for k, d in dirs.items():
        try:
            rows.append(await one(k, d))
        except BaseException as e:
            print("skip", k, type(e).__name__)
    out = []
    for k, old, new in rows:
        def cnt(x): return collections.Counter((o["feature"], o["value"]) for o in x["observations"] if o["feature"] in FEATS and o["source_type"] == "gmaps_review")
        print(f"\n## {k}  voices={new['voices']} reviews={new['stats']['reviews']} dropped={new['stats']['dropped']}")
        print("  v4:", dict(cnt(old))); print("  v5:", dict(cnt(new)))
        out += [(k, o) for o in new["observations"] if o["feature"] in FEATS and o["source_type"] == "gmaps_review"]
    random.seed(3)
    print("\n### sample v5 effort/booking/weather/duration obs")
    for k, o in random.sample(out, min(30, len(out))):
        print(f"- [{k[:14]}] {o['feature']}={o['value']} «{o['span']['quote']}»")
asyncio.run(main())
