"""judge status: places that reviewers say closed or changed -> decisions kind place_status (open | closed | changed |
unclear), read by serving (closed / changed: DISABLED; unclear: served with a warning).

A report is a `condition_change` observation whose quote says the place stopped or became something else (REPORT).
The Judge (corpus.llm.PLACE_STATUS) weighs the reports against the newest reviews and the Maps status, by date; a
closed / changed verdict takes a place out of serving, so the strong Judge is asked too and only agreement stands
(otherwise unclear). A place is asked again only when its reports, newest reviews or the prompt change (note.fp).
A place the Judge marked closed / changed / unclear whose reports are all gone now (observe re-ran, or qc pruned
the reviews) goes back to open; a person's decision is never undone.
"""

import asyncio
import hashlib
import json
import re

from ..crawl.common.files import data_dir, load_config, now
from ..llm import PLACE_STATUS, PLACE_STATUS_STRONG
from ..review import decide, decision_records
from .audit import ask, guarded

REPORT = re.compile(r"đóng cửa|ngừng hoạt động|ngưng hoạt động|không còn hoạt động|không còn kinh doanh|không còn bán|"
                    r"dẹp|giải thể|bỏ hoang|chuyển (?:thành|sang|đi|địa điểm|chỗ)|đổi thành|nghỉ bán|nghỉ luôn|"
                    r"closed|shut down|no longer", re.I)
NEWEST = 15  # reviews shown, newest first


def reports(doc: dict) -> list[dict]:
    return [o for o in doc["observations"] if o["feature"] == "condition_change" and REPORT.search(o["span"]["quote"])]


def newest_reviews(stem: str, dates: dict[str, str]) -> list[dict]:
    f = data_dir() / "gmaps" / "places" / stem / "reviews.json"
    rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    rows = [r for r in rows if (r.get("text") or "").strip()]
    rows.sort(key=lambda r: dates.get(r["review_id"], ""), reverse=True)
    return rows[:NEWEST]


async def run(city: str) -> dict:
    name, _ = load_config(city)
    client, model = PLACE_STATUS.role.client()
    client = client.with_options(timeout=300, max_retries=0)
    sem = asyncio.Semaphore(PLACE_STATUS.parallel)
    strong_client, strong_model = PLACE_STATUS_STRONG.role.client()
    strong_client = strong_client.with_options(timeout=300, max_retries=0)
    strong_sem = asyncio.Semaphore(PLACE_STATUS_STRONG.parallel)
    done = decision_records("place_status")
    root = data_dir() / "gmaps"

    async def one(f) -> str | None:
        doc = json.loads(f.read_text(encoding="utf-8"))
        reps = reports(doc)
        old = done.get(doc["place_fid"])
        if not reps:
            note = json.loads((old or {}).get("note") or "{}")
            if old and old["decision"] != "open" and "model" in note:  # the Judge's, not a person's: reports gone
                decide("place_status", doc["place_fid"], "open", json.dumps(
                    {"reason": "no closure report left in the observations", "model": "rule", "fp": None,
                     "reports": []}, ensure_ascii=False))
                return "open"
            return None
        dates = {o["source_id"]: o["observed_at"] or "" for o in doc["observations"]}
        revs = newest_reviews(f.stem, dates)
        fp = hashlib.sha256(json.dumps([[o["id"] for o in reps], [r["review_id"] for r in revs],
                                        PLACE_STATUS.prompt_hash]).encode()).hexdigest()[:12]
        if old and json.loads(old.get("note") or "{}").get("fp") == fp:
            return "cached"
        place = json.loads((root / "places" / f.stem / "place.json").read_text(encoding="utf-8"))
        fields = dict(city=name, today=now()[:10], name=place.get("name"),
                            category=place.get("category") or "unknown", address=place.get("address") or "unknown",
                            maps_status=place.get("status") or "none",
                            hours="; ".join(place.get("hours") or []) or "none",
                            reports="\n".join(f"- {o['observed_at']}: \"{o['span']['quote']}\"" for o in reps),
                            reviews="\n".join(f"- {dates.get(r['review_id']) or r.get('published_text')}, "
                                              f"{r.get('rating')}: {' '.join(r['text'].split())[:400]}" for r in revs))
        async with sem:
            ans = await ask(PLACE_STATUS, client, model, **fields)
        status, second = ans["status"], None
        if status in ("closed", "changed"):
            async with strong_sem:
                second = await ask(PLACE_STATUS_STRONG, strong_client, strong_model, **fields)
            if second["status"] != status:
                status = "unclear"
        decide("place_status", doc["place_fid"], status, json.dumps(
            {"reason": ans["reason"], "since": ans["since"], "model": ans.get("_model", model), "fp": fp,
             "reports": [o["id"] for o in reps],
             "strong": second and {"status": second["status"], "reason": second["reason"],
                                   "model": second.get("_model", strong_model)}}, ensure_ascii=False))
        return status

    files = sorted((root / "observations").glob("*.json"))
    got = [g for g in await asyncio.gather(*(guarded(one(f), f.stem) for f in files)) if g]
    summary = {"at": now(), "reported": len(got), "status": {s: got.count(s) for s in sorted(set(got))}}
    print(f"judge status {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def verdicts() -> dict[str, str]:
    """fid -> place status that may act: closed / changed only when the strong Judge agreed (or a person decided);
    a single Judge's closed / changed counts as unclear."""
    out = {}
    for fid, rec in decision_records("place_status").items():
        note = json.loads(rec.get("note") or "{}")
        d = rec["decision"]
        if d in ("closed", "changed") and "model" in note and (note.get("strong") or {}).get("status") != d:
            d = "unclear"
        out[fid] = d
    return out
