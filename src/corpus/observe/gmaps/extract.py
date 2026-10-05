"""gmaps observe: each crawled place's reviews -> data/gmaps/observations/<fid_dir>.json.

Structured details become observations by rule (details.py); review text goes to the Extractor in batches of one
place (corpus.llm.REVIEW_OBSERVE) and through the gate (gate.py). Reviews the qc phase flagged as owner reply, spam
or not a review are left out entirely. Place attributes become observations of one authoritative source and
popular times / price / hours / closure go to place_facts and name / category / location to place (place_rules.py).
Reviews are reviews.json plus the "most relevant" ones of reviews_relevant.json not already there (any age; their
date stays in published_text). `voices` = authors whose review details or text were read: the denominator of a feature's mention rate. Review observations of features with `check: span` are read
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
from datetime import UTC, datetime
from pathlib import Path

import openai

from ...crawl.common.files import append_jsonl, data_dir, load_config, now, safe_name, write_json
from ...llm import REVIEW_OBSERVE, REVIEW_VERIFY
from ...ontology import UNKNOWN, Ontology, load as load_ontology
from .. import observation
from .details import day_type, details_pairs
from .gate import BadAnswer, gate, norm
from .place_rules import (AUTHOR, RULES_VERSION, attribute_pairs, parse_closure, parse_hours, parse_popular_times,
                          parse_price, parse_tickets)
from .prep import batches, clean_text, is_junk, keep_for_llm, observed_at, stars

DETAILS_EXTRACTOR = "details_rule@v2"
RELEVANT_FILE = "reviews_relevant.json"  # written by corpus.crawl.gmaps.relevant
EXTREMES_FILE = "reviews_extremes.json"  # written by corpus.crawl.gmaps.extremes
KEYWORDS_FILE = "reviews_keywords.json"  # written by corpus.crawl.gmaps.keywords
PASSAGE_CHARS = 1200  # review text shown to REVIEW_VERIFY around the quote
VERDICTS = ("supports", "contradicts", "insufficient")
SPAN_CHECK_VERSION = "span_check@v2"  # claim = ontology claims[value] + quote
QC_DROP = {"owner_reply", "spam", "not_a_review"}
ATTEMPTS = 2
CALL_TIMEOUT_S = 240  # a batch takes ~50 s, the longest ~150 s; a dropped connection must not hold a slot for long
BUSY_WAIT_S = 20  # after HTTP 429 (the key is shared): wait outside the slots, then try the same call again
BUSY_TRIES = 30
BAD_ANSWER = (BadAnswer, ValueError, TypeError, AttributeError, KeyError)  # JSONDecodeError is a ValueError


def first_line(e: BaseException) -> str:
    return f"{type(e).__name__}: {(str(e).splitlines() or [''])[0][:300]}"


class Slots:
    """Concurrent-call slots over every reachable endpoint: a call takes whichever slot frees first. How many may be
    in use adapts to a shared key: HTTP 429 cuts it to 3/4 (not below min_cap), `cap` calls in a row that went
    through add one back, up to all of them."""

    def __init__(self, providers: list[tuple], min_cap: int = 4):
        self.free = [(client, model) for client, model, parallel in providers for _ in range(parallel)]
        self.max = len(self.free)
        self.cap, self.min_cap = self.max, min(min_cap, self.max)
        self.in_use = self.streak = 0
        self.cond = asyncio.Condition()

    def busy(self):
        self.cap, self.streak = max(self.min_cap, int(self.cap * 0.75)), 0

    def ok(self):
        self.streak += 1
        if self.streak >= self.cap:
            self.cap, self.streak = min(self.max, self.cap + 1), 0

    @contextlib.asynccontextmanager
    async def take(self):
        async with self.cond:
            await self.cond.wait_for(lambda: self.in_use < self.cap and self.free)
            self.in_use += 1
            slot = self.free.pop()
        try:
            yield slot
        finally:
            async with self.cond:
                self.in_use -= 1
                self.free.append(slot)
                self.cond.notify_all()


async def call(slots: Slots, fn):
    """fn(client, model) on a free slot; HTTP 429 shrinks the slots and the call waits outside them, then retries."""
    for tries in range(1, BUSY_TRIES + 1):
        async with slots.take() as (client, model):
            try:
                out = await fn(client, model)
                slots.ok()
                return out
            except openai.RateLimitError:
                slots.busy()
                if tries == BUSY_TRIES:
                    raise
        await asyncio.sleep(BUSY_WAIT_S)


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
    client = client.with_options(timeout=CALL_TIMEOUT_S, max_retries=0)  # Task.ask retries with backoff
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
    try:
        answer = await call(slots, lambda client, model: verify_claim(client, model, place, passage(text, o["quote"]),
                                                                      claim))
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


def extremes_reviews(doc: dict) -> list[dict]:
    """Every review of a reviews_extremes.json, lowest first, de-duplicated by review_id."""
    rows = [r for name in ("lowest", "highest") for r in doc.get(name, {}).get("reviews", [])]
    return list({r["review_id"]: r for r in rows}.values())


def keywords_reviews(doc: dict) -> list[dict]:
    """Every review of a reviews_keywords.json, keyword by keyword, de-duplicated by review_id."""
    rows = [r for k in doc.get("keywords", {}).values() for r in k.get("reviews", [])]
    return list({r["review_id"]: r for r in rows}.values())


# reviews picked for what they say (corpus.observe.TARGETED), after the newest + most relevant ones
TARGETED_FILES = (("extremes", EXTREMES_FILE, extremes_reviews), ("keywords", KEYWORDS_FILE, keywords_reviews))


def load_samples(place_dir: Path) -> tuple[list[dict], dict[str, str]]:
    """reviews.json (newest) + reviews_relevant.json (Maps' most relevant, any age) + the targeted files (lowest /
    highest rated, keyword hits; any age) not already in them; and review_id -> sample for the targeted ones."""
    reviews = json.loads((place_dir / "reviews.json").read_text(encoding="utf-8"))
    extra = place_dir / RELEVANT_FILE
    if extra.exists():
        seen = {r["review_id"] for r in reviews}
        reviews += [r for r in json.loads(extra.read_text(encoding="utf-8"))["reviews"] if r["review_id"] not in seen]
    samples = {}
    for sample, name, read in TARGETED_FILES:
        if (place_dir / name).exists():
            seen = {r["review_id"] for r in reviews}
            more = [r for r in read(json.loads((place_dir / name).read_text(encoding="utf-8"))) if r["review_id"] not in seen]
            reviews += more
            samples |= {r["review_id"]: sample for r in more}
    return reviews, samples


def load_reviews(place_dir: Path) -> list[dict]:
    return load_samples(place_dir)[0]


def spoke(r: dict) -> bool:
    """A review whose words observe reads (details or text worth a call): its author is one of the place's voices."""
    return bool(r.get("details")) or not is_junk(clean_text(r.get("text")))


def tag_samples(doc: dict, reviews: list[dict], samples: dict[str, str], bad_ids: set[str]) -> dict:
    """The observation file with `sample` on the observations and star ratings of targeted reviews, and the voices
    split: `voices` = authors of the newest / relevant reviews read, `voices_targeted` = authors only a targeted
    review adds. Idempotent: the total of both is split again."""
    total = (doc.get("voices") or 0) + (doc.get("voices_targeted") or 0)
    who = lambda r: r.get("author_hash") or r["review_id"]  # noqa: E731
    read = [r for r in reviews if r["review_id"] not in bad_ids and spoke(r)]
    base = {who(r) for r in read if r["review_id"] not in samples}
    extra = {who(r) for r in read if r["review_id"] in samples} - base
    by_author = {r.get("author_hash"): samples[r["review_id"]] for r in reviews
                 if r["review_id"] in samples and r.get("author_hash") not in base}
    obs = []
    for o in doc["observations"]:
        o = {k: v for k, v in o.items() if k != "sample"}
        if o["source_type"] != "gmaps_attribute" and o["source_id"] in samples:
            o["sample"] = samples[o["source_id"]]
        obs.append(o)
    ratings = []
    for r in doc.get("ratings", []):
        r = {k: v for k, v in r.items() if k != "sample"}
        if r.get("author") in by_author:
            r["sample"] = by_author[r["author"]]
        ratings.append(r)
    vt = min(len(extra), total)
    return {**doc, "observations": obs, "ratings": ratings, "voices": total - vt, "voices_targeted": vt}


def input_hash(place_dir: Path, bad_ids: set[str]) -> str:
    h = hashlib.sha256((place_dir / "reviews.json").read_bytes())
    if (place_dir / RELEVANT_FILE).exists():
        h.update((place_dir / RELEVANT_FILE).read_bytes())
    for _, name, _ in TARGETED_FILES:
        if (place_dir / name).exists():
            h.update((place_dir / name).read_bytes())
    h.update(json.loads((place_dir / "place.json").read_text(encoding="utf-8"))["fetched_at"].encode())
    h.update(json.dumps(sorted(bad_ids)).encode())  # qc run after observe changes what goes to the model
    return h.hexdigest()[:16]


def prune(doc: dict, reviews: list[dict], bad_ids: set[str]) -> dict:
    """An observation file without the evidence of reviews qc flagged since it was built: their observations,
    star ratings, proposed features and voices go; attributes (not a review) stay."""
    gone = {r["review_id"] for r in reviews if r["review_id"] in bad_ids} - set(doc.get("qc_dropped") or [])
    authors = {r.get("author_hash") for r in reviews if r["review_id"] in gone} - {None}
    silenced = {r.get("author_hash") or r["review_id"] for r in reviews if r["review_id"] in gone and spoke(r)}
    total = (doc.get("voices") or 0) + (doc.get("voices_targeted") or 0)  # tag_samples splits it again
    return {**doc,
            "observations": [o for o in doc["observations"]
                             if o["source_type"] == "gmaps_attribute" or o["source_id"] not in gone],
            "ratings": [r for r in doc.get("ratings", []) if r.get("author") not in authors],
            "proposed": [x for x in doc.get("proposed", []) if x.get("source_id") not in gone],
            "voices": max(0, total - len(silenced)), "voices_targeted": 0,
            "qc_dropped": sorted(bad_ids),
            "stats": {**doc.get("stats", {}), "qc_dropped": len(bad_ids)}}


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
        try:
            answer = await call(slots, lambda client, model, note=note: ask_batch(client, model, city, place,
                                                                                ont.prompt_text(), text, note))
            return gate(answer, refs, ont)
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


def listed_category(item: dict) -> str | None:
    """The search list's category; Maps sometimes puts the street address there ("263 Đ. Bùi Thị Xuân")."""
    c = (item.get("category") or "").strip()
    return c if c and not c[0].isdigit() else None


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def read_before(place_dir: Path, previous: dict) -> dict[str, str]:
    """review_id -> text key of the reviews an older file already sent to the model: its `read`, or (files written
    before it) every review of the review files that existed when it was built, with its text as it is now."""
    if "read" in previous:
        return previous["read"]
    built = previous.get("built_at") or ""
    names = ("reviews.json", RELEVANT_FILE) + tuple(name for _, name, _ in TARGETED_FILES)
    old = [n for n in names if (place_dir / n).exists()
           and datetime.fromtimestamp((place_dir / n).stat().st_mtime, UTC).isoformat() <= built]
    reviews, _ = load_samples(place_dir)
    ids = set()
    for n in old:
        doc = json.loads((place_dir / n).read_text(encoding="utf-8"))
        ids |= {r["review_id"] for r in (doc if isinstance(doc, list) else doc.get("reviews") or
                                          extremes_reviews(doc) + keywords_reviews(doc))}
    return {r["review_id"]: text_key(clean_text(r.get("text"))) for r in reviews if r["review_id"] in ids}


async def observe_place(slots: Slots, place_dir: Path, ont: Ontology, city: str, bad_ids: set[str],
                        category: str | None = None, previous: dict | None = None) -> dict:
    """category: used when the place page has none (the search list's category). previous: this place's older file
    built with the same prompts and ontology; a review it already read with the same text keeps its observations and
    proposals (no model call, so the Judge's labels on those claims still apply); only new reviews go to the model."""
    place = json.loads((place_dir / "place.json").read_text(encoding="utf-8"))
    if not place.get("category") and category:
        place["category"] = category
    reviews, samples = load_samples(place_dir)
    fid, fetched = place["fid"], place["fetched_at"]
    obs, proposed, ratings = [], [], []
    seq = collections.Counter()
    voices = set()  # authors whose details or text were read

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
        if r.get("details"):
            voices.add(r.get("author_hash") or r["review_id"])
        for feature, value, line in details_pairs(r):
            add(r, feature, value, ctx, line, "details", DETAILS_EXTRACTOR)

    to_llm = keep_for_llm(reviews, bad_ids)
    voices |= {r.get("author_hash") or r["review_id"] for r in to_llm}
    read = {r["review_id"]: text_key(r["text"]) for r in to_llm}
    before = read_before(place_dir, previous) if previous else {}
    reuse = {rid for rid, k in read.items() if before.get(rid) == k}
    for r in to_llm:
        if r["review_id"] in reuse:
            for o in previous["observations"]:
                if o["source_type"] == "gmaps_review" and o["source_id"] == r["review_id"]:
                    add(r, o["feature"], o["value"], o["context"], o["span"]["quote"], "text", o["extractor"])
    proposed += [p for p in (previous or {}).get("proposed", []) if p.get("source_id") in reuse]
    refs = {f"r{i}": r for i, r in enumerate((r for r in to_llm if r["review_id"] not in reuse), 1)}
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
    return tag_samples({
            "place_fid": fid, "place_name": place.get("name"), "as_of": fetched[:10], "observations": obs,
            "proposed": proposed, "ratings": ratings,
            "place": {k: place.get(k) for k in ("category", "lat", "lng", "address")},
            "voices": len(voices),
            "place_facts": {"popular_times": parse_popular_times(place.get("popular_times")),
                            "price": parse_price(place.get("price")), "hours": parse_hours(place.get("hours")),
                            "closure": parse_closure(place.get("status")),
                            "tickets": parse_tickets(place.get("tickets"))},
            "read": read,
            "stats": {"reviews": len(reviews), "to_llm": len(to_llm), "reused": len(reuse), "batches": len(parts),
                      "dropped": dict(dropped)}},
        reviews, samples, bad_ids)


def relevant_pending(place_dir: Path) -> bool:
    """Maps shows more reviews than crawl kept and the relevant phase has not written its file yet."""
    place = json.loads((place_dir / "place.json").read_text(encoding="utf-8"))
    digits = "".join(ch for ch in (place.get("review_count") or "").split(" ")[0] if ch.isdigit())
    kept = len(json.loads((place_dir / "reviews.json").read_text(encoding="utf-8")))
    return bool(digits) and int(digits) > kept and not (place_dir / RELEVANT_FILE).exists()


async def run(city: str, limit: int | None = None, wait_relevant: bool = False) -> dict:
    """wait_relevant: leave out places still waiting for reviews_relevant.json (observing them now means again later)."""
    name, _ = load_config(city)
    root = data_dir() / "gmaps"
    out = root / "observations"
    ont = load_ontology()
    dirs = sorted(p.parent for p in (root / "places").glob("*/place.json"))
    listed = root / "list" / f"{city}.json"
    categories = {}
    if listed.exists():  # the list is the place inventory: places it dropped are not evidence for anything
        items = json.loads(listed.read_text(encoding="utf-8"))["items"]
        keep = {safe_name(r["fid"]) for r in items}
        categories = {safe_name(r["fid"]): listed_category(r) for r in items}
        dirs = [d for d in dirs if d.name in keep]
        for stale in out.glob("*.json") if out.exists() else []:
            if stale.stem not in keep:
                stale.unlink()
    if wait_relevant:
        dirs = [d for d in dirs if not relevant_pending(d)]
    if limit is not None:
        dirs = dirs[:limit]
    key = (cache_key(ont), ont.version)

    def offline(d: Path) -> str | None:
        """cached / tagged / pruned without the model, or None when the place needs the model."""
        target = out / f"{d.name}.json"
        bad_ids = bad_review_ids(root / "qc" / f"{d.name}.json")
        h = input_hash(d, bad_ids)
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("input_hash"), old.get("prompt_hash"), old.get("ontology_version")) == (h, *key):
                if "voices_targeted" in old:
                    return "cached"
                write_json(target, tag_samples(old, *load_samples(d), bad_ids))  # built before samples were tagged
                return "tagged"
            before = set(old.get("qc_dropped") or [])
            if (before <= bad_ids and (old.get("prompt_hash"), old.get("ontology_version")) == key
                    and old.get("input_hash") == input_hash(d, before)):
                # same reviews, only new qc flags: their evidence leaves without asking the model again
                reviews, samples = load_samples(d)
                write_json(target, {**tag_samples(prune(old, reviews, bad_ids), reviews, samples, bad_ids),
                                    "input_hash": h, "built_at": now()})
                return "pruned"
        return None

    status = collections.Counter()
    todo = []
    for d in dirs:
        s = offline(d)
        if s:
            status[s] += 1
        else:
            todo.append(d)
    if todo:  # only places that need the model need the network (UIT)
        providers = await _providers()
        if not providers:
            raise SystemExit("no LLM endpoint reachable (UIT needs the campus network)")
        slots = Slots(providers)
        in_flight = asyncio.Semaphore(sum(p[2] for p in providers))  # places in progress: they finish (and save) steadily
        model = ",".join(sorted({p[1] for p in providers}))
        print(f"observe {city}: endpoints {', '.join(f'{p[1]} x{p[2]}' for p in providers)}")

    async def one(d: Path) -> str:
        target = out / f"{d.name}.json"
        bad_ids = bad_review_ids(root / "qc" / f"{d.name}.json")
        h = input_hash(d, bad_ids)
        previous = None
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if (old.get("prompt_hash"), old.get("ontology_version")) == key:
                previous = old  # same prompts and ontology: reviews it already read are not asked again
        try:
            async with in_flight:
                res = await observe_place(slots, d, ont, name, bad_ids, categories.get(d.name), previous)
        except Exception as e:
            if isinstance(e, ExceptionGroup):  # from the TaskGroup: report the first real cause
                e = e.exceptions[0]
            append_jsonl(root / "observe_errors.jsonl", {"at": now(), "place": d.name, "error": first_line(e)})
            target.unlink(missing_ok=True)  # an older file would describe reviews that changed
            return "failed"
        write_json(target, {**res, "input_hash": h, "prompt_hash": key[0], "ontology_version": key[1],
                            "model": model, "built_at": now(), "qc_dropped": sorted(bad_ids)})
        return "done"

    status.update(await asyncio.gather(*(one(d) for d in todo)))
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
