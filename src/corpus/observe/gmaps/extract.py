"""gmaps observe: each crawled place's reviews -> data/gmaps/observations/<fid_dir>.json.

Structured details become observations by rule (details.py); review text goes to the Extractor in batches of one
place (corpus.llm.REVIEW_OBSERVE) and through the gate (gate.py). Reviews the qc phase flagged as owner reply, spam
or not a review are left out. A place is done again only when its reviews, the prompt or the ontology change; a
place whose batch fails twice gets no file (retried next run) and one line in data/gmaps/observe_errors.jsonl.
"""

import asyncio
import collections
import hashlib
import json
from pathlib import Path

from ...crawl.common.files import append_jsonl, data_dir, load_config, now, write_json
from ...llm import REVIEW_OBSERVE
from ...ontology import UNKNOWN, Ontology, load as load_ontology
from .. import observation
from .details import day_type, details_pairs
from .gate import BadAnswer, gate
from .prep import batches, keep_for_llm, observed_at, stars

DETAILS_EXTRACTOR = "details_rule@v1"
QC_DROP = {"owner_reply", "spam", "not_a_review"}
ATTEMPTS = 2


def _client():
    return REVIEW_OBSERVE.role.client()


async def ask_batch(client, model: str, city: str, place: dict, ontology_text: str, reviews_text: str,
                    note: str = "") -> dict:
    return await REVIEW_OBSERVE.ask(client, model, city=city, name=place.get("name"),
                                    category=place.get("category") or "none", ontology=ontology_text,
                                    reviews=reviews_text, note=note)


def input_hash(place_dir: Path) -> str:
    h = hashlib.sha256((place_dir / "reviews.json").read_bytes())
    h.update(json.loads((place_dir / "place.json").read_text(encoding="utf-8"))["fetched_at"].encode())
    return h.hexdigest()[:16]


def bad_review_ids(qc_file: Path) -> set[str]:
    if not qc_file.exists():
        return set()
    llm = json.loads(qc_file.read_text(encoding="utf-8")).get("llm") or {}
    return {b["review_id"] for b in llm.get("bad_reviews", []) if b.get("problem") in QC_DROP}


async def ask_checked(client, model, sem, city, place, ont: Ontology, batch: list[tuple[str, dict]]):
    refs = dict(batch)
    text = "\n".join(f"{ref}: {' '.join(r['text'].split())}" for ref, r in batch)
    note = ""
    for _ in range(ATTEMPTS):
        async with sem:
            try:
                return gate(await ask_batch(client, model, city, place, ont.prompt_text(), text, note), refs, ont)
            except Exception as e:
                note = (f"Your previous answer was rejected ({type(e).__name__}: {str(e).splitlines()[0][:200]}). "
                        "Answer again with JSON that matches the schema.")
    raise BadAnswer(note)


async def observe_place(client, model, sem, place_dir: Path, ont: Ontology, city: str, bad_ids: set[str]) -> dict:
    place = json.loads((place_dir / "place.json").read_text(encoding="utf-8"))
    reviews = json.loads((place_dir / "reviews.json").read_text(encoding="utf-8"))
    fid, fetched = place["fid"], place["fetched_at"]
    obs, proposed, ratings = [], [], []
    seq = collections.Counter()

    def add(r: dict, feature: str, value: str, context: dict, quote: str, field: str, extractor: str):
        rid = r["review_id"]
        obs.append(observation(
            id=f"gmaps:{rid}:{seq[rid]}", place_fid=fid, feature=feature, value=value, context=context,
            source_type="gmaps_review" if field == "text" else "gmaps_details", source_id=rid,
            author=r.get("author_hash"), observed_at=observed_at(r.get("published_text"), fetched), quote=quote,
            field=field, extractor=extractor, ontology_version=ont.version))
        seq[rid] += 1

    for r in reviews:
        s = stars(r.get("rating"))
        if s:
            ratings.append({"author": r.get("author_hash"), "observed_at": observed_at(r.get("published_text"), fetched),
                            "stars": s})
        ctx = {"time_of_day": UNKNOWN, "day_type": day_type(r), "weather": UNKNOWN}
        for feature, value, line in details_pairs(r):
            add(r, feature, value, ctx, line, "details", DETAILS_EXTRACTOR)

    to_llm = keep_for_llm(reviews, bad_ids)
    refs = {f"r{i}": r for i, r in enumerate(to_llm, 1)}
    parts = batches(list(refs.items()))
    results = await asyncio.gather(*(ask_checked(client, model, sem, city, place, ont, b) for b in parts))
    dropped = collections.Counter()
    for kept, prop, drop in results:
        dropped.update(drop)
        for ref, o in kept:
            r = refs[ref]
            ctx = dict(o["context"])
            if day_type(r) != UNKNOWN:  # Maps' own "Đã đến vào" wins over the model's reading
                ctx["day_type"] = day_type(r)
            add(r, o["feature"], o["value"], ctx, o["quote"], "text", f"review_observe@{REVIEW_OBSERVE.prompt_hash}")
        for ref, p in prop:
            proposed.append({"place_fid": fid, "source_id": refs[ref]["review_id"],
                             "author": refs[ref].get("author_hash"), **p})
    return {"place_fid": fid, "place_name": place.get("name"), "as_of": fetched[:10], "observations": obs,
            "proposed": proposed, "ratings": ratings,
            "stats": {"reviews": len(reviews), "to_llm": len(to_llm), "batches": len(parts), "dropped": dict(dropped)}}


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "gmaps"
    out = root / "observations"
    ont = load_ontology()
    dirs = sorted(p.parent for p in (root / "places").glob("*/place.json"))
    if limit is not None:
        dirs = dirs[:limit]
    client, model = _client()
    sem = asyncio.Semaphore(REVIEW_OBSERVE.parallel)
    key = (REVIEW_OBSERVE.prompt_hash, ont.version)

    async def one(d: Path) -> str:
        target = out / f"{d.name}.json"
        h = input_hash(d)
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("input_hash"), old.get("prompt_hash"), old.get("ontology_version")) == (h, *key):
                return "cached"
        try:
            res = await observe_place(client, model, sem, d, ont, name, bad_review_ids(root / "qc" / f"{d.name}.json"))
        except Exception as e:
            append_jsonl(root / "observe_errors.jsonl",
                         {"at": now(), "place": d.name, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"})
            return "failed"
        write_json(target, {**res, "input_hash": h, "prompt_hash": key[0], "ontology_version": key[1],
                            "model": model, "built_at": now()})
        return "done"

    status = collections.Counter(await asyncio.gather(*(one(d) for d in dirs)))
    files = [json.loads((out / f"{d.name}.json").read_text(encoding="utf-8")) for d in dirs if (out / f"{d.name}.json").exists()]
    summary = {
        "at": now(), "places": len(dirs), "status": dict(status),
        "observations": dict(collections.Counter(o["feature"] for f in files for o in f["observations"]).most_common()),
        "dropped": dict(sum((collections.Counter(f["stats"]["dropped"]) for f in files), collections.Counter())),
        "proposed_top": collections.Counter(p["label"].casefold() for f in files for p in f["proposed"]).most_common(30),
    }
    if dirs:
        write_json(root / "observe_summary.json", summary)
    print(f"observe {city}: {json.dumps({k: summary[k] for k in ('places', 'status', 'dropped')}, ensure_ascii=False)}")
    return summary
