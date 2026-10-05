"""judge dedup: two Maps entries of one real place -> decisions kind place_merge, which aggregate folds into one place
(the entry with more reviews is canonical; the other's evidence counts for it and it is not served on its own).

Candidates (code): pins within NEAR_M whose names share most distinctive words, or the same name within SAME_NAME_M.
The Judge (corpus.llm.SAME_PLACE) reads both entries with a few reviews each: same_place merges, and only when the
strong Judge agrees (otherwise its relation stands); part_of (a dock on a lake, a cafe in a zoo), branch and different
stay separate places. A pair is asked again only when the prompt changes (note.ph).
"""

import asyncio
import itertools
import json
import math
import re
import unicodedata

from ..crawl.common.files import data_dir, load_config, now, safe_name
from ..llm import SAME_PLACE, SAME_PLACE_STRONG
from ..review import decide, decision_records
from .audit import ask, guarded

NEAR_M, SAME_NAME_M = 300, 1500
NAME_JACCARD = 0.4
REVIEWS = 4  # review snippets per entry
PH = SAME_PLACE.prompt_hash
GENERIC = {"da", "lat", "dalat", "quan", "cafe", "coffee", "ca", "phe", "nha", "hang", "tiem", "the", "va", "and",
           "khu", "du", "lich", "cn", "chi", "nhanh", "co", "so", "spa", "massage", "goi", "dau", "duong", "sinh", "tri",
           "lieu", "thue", "xe", "may", "dac", "san", "store", "shop", "banh", "an", "vat", "com", "lau", "nuong", "tra",
           "sua", "vuon", "farm", "garden", "bar", "cocktail", "restaurant", "food", "chay", "bun", "pho", "mi"}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")


def words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(name))) - GENERIC


def meters(a: dict, b: dict) -> float:
    dy = (a["lat"] - b["lat"]) * 111_320
    dx = (a["lng"] - b["lng"]) * 111_320 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


def candidates(items: list[dict]) -> list[tuple[dict, dict, float]]:
    out = []
    for a, b in itertools.combinations(items, 2):
        if a.get("lat") is None or b.get("lat") is None:
            continue
        d = meters(a, b)
        if d > SAME_NAME_M:
            continue
        wa, wb = words(a["name"]), words(b["name"])
        if not wa or not wb:
            continue
        jac = len(wa & wb) / len(wa | wb)
        if (d <= NEAR_M and jac >= NAME_JACCARD) or wa == wb:
            out.append((a, b, d))
    return out


def card(item: dict) -> str:
    d = data_dir() / "gmaps" / "places" / safe_name(item["fid"])
    place = json.loads((d / "place.json").read_text(encoding="utf-8")) if (d / "place.json").exists() else {}
    revs = json.loads((d / "reviews.json").read_text(encoding="utf-8")) if (d / "reviews.json").exists() else []
    texts = [" ".join(r["text"].split())[:220] for r in revs if len((r.get("text") or "").strip()) >= 40][:REVIEWS]
    info = {"name": item["name"], "category": place.get("category") or item.get("category"),
            "address": place.get("address"), "rating": place.get("rating"), "reviews": item.get("reviews"),
            "description": place.get("description"), "website": place.get("website"), "phone": place.get("phone"),
            "review_snippets": texts}
    return json.dumps(info, ensure_ascii=False)


async def run(city: str) -> dict:
    name, _ = load_config(city)
    items = json.loads((data_dir() / "gmaps" / "list" / f"{city}.json").read_text(encoding="utf-8"))["items"]
    client, model = SAME_PLACE.role.client()
    client = client.with_options(timeout=300, max_retries=0)
    sem = asyncio.Semaphore(SAME_PLACE.parallel)
    strong_client, strong_model = SAME_PLACE_STRONG.role.client()
    strong_client = strong_client.with_options(timeout=300, max_retries=0)
    strong_sem = asyncio.Semaphore(SAME_PLACE_STRONG.parallel)
    done = decision_records("place_merge")

    async def one(a: dict, b: dict, d: float) -> str:
        pair = "|".join(sorted((a["fid"], b["fid"])))
        if pair in done and json.loads(done[pair].get("note") or "{}").get("ph") == PH:
            return "cached"
        fields = dict(city=name, a=card(a), b=card(b), meters=round(d))
        async with sem:
            ans = await ask(SAME_PLACE, client, model, **fields)
        relation, second = ans["relation"], None
        if relation == "same_place":  # a merge hides one entry: a second, stronger opinion must agree
            async with strong_sem:
                second = await ask(SAME_PLACE_STRONG, strong_client, strong_model, **fields)
            relation = second["relation"]
        canonical = max((a, b), key=lambda x: (x.get("reviews") or 0, x["fid"]))["fid"]
        decide("place_merge", pair, relation, json.dumps(
            {"reason": ans["reason"], "model": ans.get("_model", model), "canonical": canonical, "ph": PH,
             "strong": second and {"relation": second["relation"], "reason": second["reason"],
                                   "model": second.get("_model", strong_model)}}, ensure_ascii=False))
        return relation

    pairs = candidates(items)
    got = await asyncio.gather(*(guarded(one(a, b, d), f"{a['name']} | {b['name']}") for a, b, d in pairs))
    summary = {"at": now(), "candidates": len(pairs), "relation": {g: got.count(g) for g in sorted(set(got))}}
    print(f"judge dedup {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def merges() -> dict[str, str]:
    """fid -> canonical fid for every Judge same_place pair (chains resolved: a=b, b=c -> all to one)."""
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    canon: dict[str, str] = {}
    for pair, rec in decision_records("place_merge").items():
        if rec["decision"] != "same_place":
            continue
        a, b = pair.split("|")
        c = json.loads(rec.get("note") or "{}").get("canonical") or a
        ra, rb = root(a), root(b)
        keep = root(c) if root(c) in (ra, rb) else ra
        for r in (ra, rb):
            if r != keep:
                parent[r] = keep
        canon[keep] = keep
    return {x: root(x) for x in parent}
