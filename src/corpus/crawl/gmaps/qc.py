"""Phase 5, qc: rule checks, a Judge-role look at every listed place (corpus.llm.PLACE_QC) and an Extractor screen of
every review (corpus.llm.REVIEW_QC), one file per place.

REVIEW_QC reads all reviews of a place (newest, most relevant and extremes, in batches) and flags owner replies,
spam / reward-for-review and non-reviews; observe drops them (llm.bad_reviews, corpus.observe.gmaps). Results go to
data/gmaps/qc/<fid_dir>.json and data/gmaps/qc/summary.json. A place is checked again only when its place.json was
re-fetched, its reviews changed or a prompt changed. When only reviews were added (relevant / extremes / keywords) and
place.json is the same, the place verdict stands and the Extractor screens just the reviews not screened before
(`screened`), so the Judge is not needed.
"""

import asyncio
import collections
import hashlib
import json
from datetime import UTC, datetime

import openai

from ...llm import PLACE_QC, REVIEW_QC, OutOfQuota
from ..common.files import data_dir, load_config, now, safe_name, write_json
from .crawl import count

CORE = ("name", "category", "address", "rating", "review_count")
SAMPLE = 12  # reviews shown to PLACE_QC per place
BATCH, BATCH_CHARS = 25, 9000  # reviews per REVIEW_QC call
MIN_TEXT = 15  # shorter texts carry no claim worth screening (observe skips them too)
BUSY_WAIT_S, BUSY_TRIES = 20, 45  # shared Gemma key (HTTP 429) or a dropped campus link: wait, do not fail
FILES = ("reviews.json", "reviews_relevant.json", "reviews_extremes.json", "reviews_keywords.json")


def checks(place: dict, reviews: list[dict], cfg: dict) -> list[str]:
    """Rule checks that need no model."""
    issues = [f"missing:{k}" for k in CORE if not place.get(k)]
    area = cfg.get("area")
    if area and not (place.get("lat") is not None and area[0] <= place["lat"] <= area[2] and area[1] <= place["lng"] <= area[3]):
        issues.append("out_of_area")
    want = min(count(place.get("review_count")) or 0, cfg["gmaps"].get("min_reviews_per_place", 0))
    if len(reviews) < want:
        issues.append(f"reviews_short:{len(reviews)}/{want}")
    cut = sum((r.get("text") or "").rstrip().endswith("…") for r in reviews)
    if cut:
        issues.append(f"truncated_reviews:{cut}")
    return issues


def all_reviews(place_dir) -> list[dict]:
    """Every review the place's files hold (newest, most relevant, lowest / highest rated), once per review_id."""
    out = {}
    for name in FILES:
        f = place_dir / name
        if not f.exists():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        rows = doc if isinstance(doc, list) else doc.get("reviews") or [
            r for k in ("lowest", "highest") for r in doc.get(k, {}).get("reviews", [])] + [
            r for hits in doc.get("keywords", {}).values() for r in hits.get("reviews", [])]
        for r in rows:
            out.setdefault(r["review_id"], r)
    return list(out.values())


def screened_before(place_dir, old: dict) -> set[str]:
    """Review ids an older qc record already screened: its `screened` list, or (records written before it) every
    review of the files that existed when it was checked."""
    if "screened" in old:
        return set(old["screened"])
    out = set()
    for name in FILES:
        f = place_dir / name
        if f.exists() and datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat() <= old.get("checked_at", ""):
            doc = json.loads(f.read_text(encoding="utf-8"))
            rows = doc if isinstance(doc, list) else doc.get("reviews") or [
                r for k in ("lowest", "highest") for r in doc.get(k, {}).get("reviews", [])] + [
                r for hits in doc.get("keywords", {}).values() for r in hits.get("reviews", [])]
            out |= {r["review_id"] for r in rows}
    return out


def batches(reviews: list[dict]) -> list[list[dict]]:
    out, cur, size = [], [], 0
    for r in reviews:
        n = len(r["text"])
        if cur and (len(cur) >= BATCH or size + n > BATCH_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += n
    return out + ([cur] if cur else [])


async def _ask(task, *args, **kwargs) -> dict:
    for tries in range(1, BUSY_TRIES + 1):
        try:
            return await task.ask(*args, **kwargs)
        except OutOfQuota:  # every Judge model resting: wait for an account to reset
            await asyncio.sleep(120)
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError):
            if tries == BUSY_TRIES:
                raise
            await asyncio.sleep(BUSY_WAIT_S)


async def screen(client, model: str, place: dict, reviews: list[dict], city: str, sem: asyncio.Semaphore) -> list[dict]:
    """REVIEW_QC over every review with text: [{review_id, problem, reason}]."""
    texts = [r for r in reviews if len((r.get("text") or "").strip()) >= MIN_TEXT]

    async def one(batch: list[dict]) -> list[dict]:
        refs = {f"r{i}": r for i, r in enumerate(batch, 1)}
        lines = "\n".join(f"{ref} ({r.get('rating') or '?'}): {' '.join(r['text'].split())}" for ref, r in refs.items())
        async with sem:
            ans = await _ask(REVIEW_QC, client, model, city=city, name=place.get("name"),
                             category=place.get("category") or "unknown", reviews=lines)
        return [{"review_id": refs[b["ref"]]["review_id"], "problem": b["problem"], "reason": b["reason"]}
                for b in ans["bad"] if b["ref"] in refs]

    return [b for part in await asyncio.gather(*(one(b) for b in batches(texts))) for b in part]


async def judge(client, model: str, place: dict, reviews: list[dict], city: str = "Đà Lạt") -> dict:
    keep = ("name", "category", "address", "description", "rating", "review_count", "price", "hours", "status", "website", "phone")
    sample = [{k: r.get(k) for k in ("review_id", "rating", "text", "details")} for r in reviews if r.get("text")][:SAMPLE]
    return await _ask(PLACE_QC, client, model, city=city, place=json.dumps({k: place.get(k) for k in keep}, ensure_ascii=False),
                      reviews=json.dumps(sample, ensure_ascii=False))


def reviews_hash(reviews: list[dict]) -> str:
    h = hashlib.sha256(json.dumps(sorted((r["review_id"], r.get("text") or "") for r in reviews),
                                  ensure_ascii=False).encode())
    h.update((PLACE_QC.prompt_hash + REVIEW_QC.prompt_hash).encode())
    return h.hexdigest()[:16]


async def run(city: str) -> dict:
    name, cfg = load_config(city)
    root = data_dir() / "gmaps"
    out = root / "qc"
    judge_client, judge_model = PLACE_QC.role.client()
    ex_client, ex_model = REVIEW_QC.role.client()
    ex_client = ex_client.with_options(timeout=240, max_retries=0)
    judge_sem, ex_sem = asyncio.Semaphore(PLACE_QC.parallel), asyncio.Semaphore(REVIEW_QC.parallel)
    listed = root / "list" / f"{city}.json"
    keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]} if listed.exists() else None

    async def one(p):
        place = json.loads(p.read_text(encoding="utf-8"))
        target = out / f"{p.parent.name}.json"
        reviews = all_reviews(p.parent)
        h = reviews_hash(reviews)
        old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
        if old and (old.get("fetched_at"), old.get("reviews_hash")) == (place["fetched_at"], h) and old.get("llm")                 and "review_qc" in old:
            return old
        res = {"fid": place["fid"], "name": place.get("name"), "fetched_at": place["fetched_at"], "checked_at": now(),
               "model": judge_model, "review_model": ex_model, "reviews_hash": h,
               "checks": checks(place, json.loads((p.parent / "reviews.json").read_text(encoding="utf-8")), cfg),
               "llm": None, "screened": sorted(r["review_id"] for r in reviews)}
        # same place page, only more reviews (relevant / extremes / keywords): the place verdict stands and only the
        # new reviews are screened, so this needs the Extractor alone, not the Judge
        same_place = bool(old and old.get("fetched_at") == place["fetched_at"] and old.get("llm") and "review_qc" in old)
        try:
            if same_place:
                done = screened_before(p.parent, old)
                fresh = [r for r in reviews if r["review_id"] not in done]
                flagged = await screen(ex_client, ex_model, place, fresh, name, ex_sem)
                res["llm"], res["model"] = dict(old["llm"]), old.get("model", judge_model)
                kept = [b for b in old["llm"]["bad_reviews"] if b["review_id"] not in {f["review_id"] for f in flagged}]
                res["llm"]["bad_reviews"] = flagged + kept
                res["review_qc"] = {"reviews": len(reviews), "flagged": old["review_qc"]["flagged"] + len(flagged),
                                    "screened_now": len(fresh)}
                write_json(target, res)
                return res
            async with judge_sem:
                res["llm"] = await judge(judge_client, judge_model, place, reviews, name)
            flagged = await screen(ex_client, ex_model, place, reviews, name, ex_sem)
        except Exception as e:
            res["llm_error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300] if str(e) else ''}"
            if not same_place:
                write_json(target, res)  # an older complete record is kept: the next run screens again
            return old if same_place else res
        res["review_qc"] = {"reviews": len(reviews), "flagged": len(flagged)}
        seen = {b["review_id"] for b in flagged}
        res["llm"]["bad_reviews"] = flagged + [b for b in res["llm"]["bad_reviews"] if b["review_id"] not in seen]
        write_json(target, res)
        return res

    places = sorted(p for p in (root / "places").glob("*/place.json") if keep is None or p.parent.name in keep)
    results = await asyncio.gather(*(one(p) for p in places))
    llm = [r["llm"] for r in results if r["llm"]]
    summary = {
        "at": now(), "places": len(results),
        "verdict": dict(collections.Counter(x["verdict"] for x in llm)),
        "not_tourism": sorted(r["name"] for r in results if r["llm"] and not r["llm"]["tourism_relevant"]),
        "not_in_city": sorted(r["name"] for r in results if r["llm"] and not r["llm"]["in_city"]),
        "checks": dict(collections.Counter(i.split(":")[0] for r in results for i in r["checks"])),
        "bad_reviews": dict(collections.Counter(b["problem"] for x in llm for b in x["bad_reviews"])),
        "llm_errors": sum("llm_error" in r for r in results),
    }
    write_json(out / "summary.json", summary)
    print(f"qc {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
