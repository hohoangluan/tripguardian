"""gmaps observe: each crawled place's reviews -> data/gmaps/observations/<fid_dir>.json.

Structured details become observations by rule (details.py); review text goes to the Extractor in batches of one
place (corpus.llm.REVIEW_OBSERVE) and through the gate (gate.py). Reviews the qc phase flagged as owner reply, spam
or not a review are left out entirely. Place attributes become observations of one authoritative source and
popular times / price go to place_facts (place_rules.py). Review observations of features with `check: span` are read
again one by one (corpus.llm.REVIEW_VERIFY); only "supports" is kept.
A place is done again only when its reviews, qc flags, the prompts, the ontology or the rules change; a
place that fails gets no file (retried next run; an older file is removed) and one line in
data/gmaps/observe_errors.jsonl. Only a bad answer is split / retried; a network or API error fails the place at once.
"""

import asyncio
import collections
import contextlib
import hashlib
import json
from pathlib import Path

import openai

from ...crawl.common.files import append_jsonl, data_dir, load_config, now, safe_name, write_json
from ...llm import REVIEW_OBSERVE, REVIEW_VERIFY
from ...ontology import UNKNOWN, Ontology, load as load_ontology
from .. import observation
from .details import day_type, details_pairs
from .gate import BadAnswer, gate, norm
from .place_rules import AUTHOR, RULES_VERSION, attribute_pairs, parse_popular_times, parse_price
from .prep import batches, keep_for_llm, observed_at, stars

DETAILS_EXTRACTOR = "details_rule@v2"
PASSAGE_CHARS = 1200  # review text shown to REVIEW_VERIFY around the quote
VERDICTS = ("supports", "contradicts", "insufficient")
SPAN_CHECK_VERSION = "span_check@v2"  # claim = ontology claims[value] + quote
QC_DROP = {"owner_reply", "spam", "not_a_review"}
ATTEMPTS = 2
BAD_ANSWER = (BadAnswer, ValueError, TypeError, AttributeError, KeyError)  # JSONDecodeError is a ValueError


def first_line(e: BaseException) -> str:
    return f"{type(e).__name__}: {(str(e).splitlines() or [''])[0][:300]}"


class Slots:
    """Concurrent-call slots over every reachable endpoint: a call takes whichever slot frees first."""

    def __init__(self, providers: list[tuple]):
        self.q = asyncio.Queue()
        for client, model, parallel in providers:
            for _ in range(parallel):
                self.q.put_nowait((client, model))

    @contextlib.asynccontextmanager
    async def take(self):
        slot = await self.q.get()
        try:
            yield slot
        finally:
            self.q.put_nowait(slot)


async def healthy(client, model: str) -> bool:
    """A tiny call answers; off campus the UIT proxy returns a redirect page instead of a completion."""
    try:
        r = await client.chat.completions.create(model=model, messages=[{"role": "user", "content": "OK"}],
                                                 max_tokens=3, timeout=30)
        return bool(r.choices)
    except Exception:
        return False


async def _providers() -> list[tuple]:
    client, model = REVIEW_OBSERVE.role.client()
    found = [(client, model, REVIEW_OBSERVE.parallel)]
    ok = await asyncio.gather(*(healthy(c, m) for c, m, _ in found))
    return [p for p, good in zip(found, ok) if good]


async def ask_batch(client, model: str, city: str, place: dict, ontology_text: str, reviews_text: str,
                    note: str = "") -> dict:
    return await REVIEW_OBSERVE.ask(client, model, city=city, name=place.get("name"),
                                    category=place.get("category") or "none", ontology=ontology_text,
                                    reviews=reviews_text, note=note)


async def verify_claim(client, model: str, place: dict, passage: str, claim: str) -> dict:
    return await REVIEW_VERIFY.ask(client, model, name=place.get("name"), category=place.get("category") or "none",
                                   claim=claim, passage=passage)


def passage(text: str, quote: str) -> str:
    if len(text) <= PASSAGE_CHARS:
        return text
    at = max(0, norm(text).find(norm(quote)[:40]))  # norm keeps length close enough for a window
    start = max(0, at - PASSAGE_CHARS // 2)
    return text[start:start + PASSAGE_CHARS]


async def check_span(slots: Slots, place: dict, text: str, ont: Ontology, o: dict) -> str:
    claim = f'{ont.features[o["feature"]].claims[o["value"]]} (quote: "{o["quote"]}")'
    async with slots.take() as (client, model):
        try:
            answer = await verify_claim(client, model, place, passage(text, o["quote"]), claim)
            verdict = answer.get("verdict")
        except openai.APIError:
            raise
        except BAD_ANSWER:
            return "error"
    return verdict if verdict in VERDICTS else "error"


def cache_key(ont: Ontology) -> str:
    checked = json.dumps({f.id: f.claims for f in ont.features.values() if f.span_check}, sort_keys=True,
                         ensure_ascii=False)
    parts = (REVIEW_OBSERVE.prompt_hash, REVIEW_VERIFY.prompt_hash, ont.prompt_text(), checked, DETAILS_EXTRACTOR,
             RULES_VERSION, SPAN_CHECK_VERSION, str(PASSAGE_CHARS), ",".join(sorted(QC_DROP)))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def input_hash(place_dir: Path, bad_ids: set[str]) -> str:
    h = hashlib.sha256((place_dir / "reviews.json").read_bytes())
    h.update(json.loads((place_dir / "place.json").read_text(encoding="utf-8"))["fetched_at"].encode())
    h.update(json.dumps(sorted(bad_ids)).encode())  # qc run after observe changes what goes to the model
    return h.hexdigest()[:16]


def bad_review_ids(qc_file: Path) -> set[str]:
    if not qc_file.exists():
        return set()
    llm = json.loads(qc_file.read_text(encoding="utf-8")).get("llm") or {}
    return {b["review_id"] for b in llm.get("bad_reviews", []) if b.get("problem") in QC_DROP}


async def ask_checked(slots: Slots, city, place, ont: Ontology, batch: list[tuple[str, dict]], note: str = ""):
    """A failed batch is split in halves (shorter answers, other context); a single review gets ATTEMPTS tries."""
    refs = dict(batch)
    text = "\n".join(f"{ref}: {' '.join(r['text'].split())}" for ref, r in batch)
    for attempt in range(1 if len(batch) > 1 else ATTEMPTS):
        async with slots.take() as (client, model):
            try:
                return gate(await ask_batch(client, model, city, place, ont.prompt_text(), text, note), refs, ont)
            except openai.APIError:
                raise  # splitting cannot fix the network or the API
            except BAD_ANSWER as e:
                note = (f"Your previous answer was rejected ({first_line(e)[:200]}). "
                        "Answer again with JSON that matches the schema.")
    if len(batch) == 1:
        raise BadAnswer(note)
    mid = len(batch) // 2
    halves = await asyncio.gather(*(ask_checked(slots, city, place, ont, b, note)
                                    for b in (batch[:mid], batch[mid:])))
    return ([x for h in halves for x in h[0]], [x for h in halves for x in h[1]],
            sum((h[2] for h in halves), collections.Counter()))


async def observe_place(slots: Slots, place_dir: Path, ont: Ontology, city: str, bad_ids: set[str]) -> dict:
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

    for i, (feature, value, label) in enumerate(attribute_pairs(place.get("attributes"))):
        obs.append(observation(
            id=f"gmaps:attr:{i}", place_fid=fid, feature=feature, value=value,
            context=dict.fromkeys(("time_of_day", "day_type", "weather"), UNKNOWN), source_type="gmaps_attribute",
            source_id=fid, author=AUTHOR, observed_at=fetched[:10], quote=label, field="attributes",
            extractor=RULES_VERSION, ontology_version=ont.version))

    for r in reviews:
        if r["review_id"] in bad_ids:  # spam / owner reply / not a review: no evidence at all
            continue
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
    async with asyncio.TaskGroup() as tg:  # the first failed batch cancels its siblings
        tasks = [tg.create_task(ask_checked(slots, city, place, ont, b)) for b in parts]
    results = [t.result() for t in tasks]
    dropped = collections.Counter()
    kept_all = [(ref, o) for kept, _, drop in results for ref, o in kept]
    for _, _, drop in results:
        dropped.update(drop)
    checks = [(ref, o) for ref, o in kept_all if ont.features[o["feature"]].span_check]
    async with asyncio.TaskGroup() as tg:
        verdicts = [tg.create_task(check_span(slots, place, refs[ref]["text"], ont, o)) for ref, o in checks]
    rejected = set()
    for (ref, o), v in zip(checks, verdicts):
        if v.result() != "supports":
            rejected.add(id(o))
            dropped[f"span_check_{v.result()}"] += 1
    for kept, prop, _ in results:
        for ref, o in kept:
            if id(o) in rejected:
                continue
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
            "place_facts": {"popular_times": parse_popular_times(place.get("popular_times")),
                            "price": parse_price(place.get("price"))},
            "stats": {"reviews": len(reviews), "to_llm": len(to_llm), "batches": len(parts), "dropped": dict(dropped)}}


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    root = data_dir() / "gmaps"
    out = root / "observations"
    ont = load_ontology()
    dirs = sorted(p.parent for p in (root / "places").glob("*/place.json"))
    listed = root / "list" / f"{city}.json"
    if listed.exists():  # the list is the place inventory: places it dropped are not evidence for anything
        keep = {safe_name(r["fid"]) for r in json.loads(listed.read_text(encoding="utf-8"))["items"]}
        dirs = [d for d in dirs if d.name in keep]
        for stale in out.glob("*.json") if out.exists() else []:
            if stale.stem not in keep:
                stale.unlink()
    if limit is not None:
        dirs = dirs[:limit]
    providers = await _providers()
    if not providers:
        raise SystemExit("no LLM endpoint reachable (UIT needs the campus network)")
    slots = Slots(providers)
    in_flight = asyncio.Semaphore(sum(p[2] for p in providers))  # places in progress: they finish (and save) steadily
    model = ",".join(sorted({p[1] for p in providers}))
    print(f"observe {city}: endpoints {', '.join(f'{p[1]} x{p[2]}' for p in providers)}")
    key = (cache_key(ont), ont.version)

    async def one(d: Path) -> str:
        target = out / f"{d.name}.json"
        bad_ids = bad_review_ids(root / "qc" / f"{d.name}.json")
        h = input_hash(d, bad_ids)
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("input_hash"), old.get("prompt_hash"), old.get("ontology_version")) == (h, *key):
                return "cached"
        try:
            async with in_flight:
                res = await observe_place(slots, d, ont, name, bad_ids)
        except Exception as e:
            if isinstance(e, ExceptionGroup):  # from the TaskGroup: report the first real cause
                e = e.exceptions[0]
            append_jsonl(root / "observe_errors.jsonl", {"at": now(), "place": d.name, "error": first_line(e)})
            target.unlink(missing_ok=True)  # an older file would describe reviews that changed
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
