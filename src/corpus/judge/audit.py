"""judge audit: the Judge model labels what the Extractor claimed, in place of a person (docs/CORPUS.md §6).

Which model-made observations it reads (rule-made ones from Maps details / attributes are not labelled):
- every observation of a risky feature: effort, suitability and every `check: span` feature (hard filters, values
  that warn or widen a choice);
- a sample of `SAMPLE` observations per (feature, value, source folder) of every other feature;
- then all observations of a (feature, value, source) whose sampled precision misses the gate (Wilson lower bound
  below GATE_LOWER): that stratum is checked one by one, so only claims the Judge confirmed are left.
Calls of up to CHUNK items, a place's items together: the places, the features' definitions and claims from the
ontology, and each item's passage (review text, transcript, caption) or picture (Maps photo, video frame). Values that widen a choice
(`verify: always`, not a caution value) go to the strong Judge. Labels append to data/review/judge_labels.jsonl as
they arrive (corpus.review.judge_label), so a stopped run resumes; claims already labelled are skipped.
"""

import asyncio
import collections
import json
import random

import openai

from ..crawl.common.files import data_dir, load_config, now
from ..llm import OBS_AUDIT, OBS_AUDIT_STRONG, OutOfQuota
from ..ontology import load as load_ontology
from ..review import evidence, judge_label, label_key, label_records

# model-made observations per source folder (rule-made gmaps_details / gmaps_attribute are not labelled)
SOURCES = {"gmaps": ("gmaps", "observations", {"gmaps_review"}),
           "tiktok": ("tiktok", "observations", {"tiktok_segment", "tiktok_caption", "tiktok_frame"}),
           "gmaps_photo": ("gmaps", "photo_observations", {"gmaps_photo"})}
RISKY_GROUPS = {"effort", "suitability"}
SAMPLE = 30  # per (feature, value, source) for features that are not risky
GATE_LOWER = 0.8  # same bar as the label gate (corpus.review.labels)
GATE_MIN_N = 20  # labelled items before a stratum can be judged from its sample
CHUNK, CHUNK_IMAGES = 8, 4  # items per call
WAIT_S, TRIES = 30, 20  # 9router busy / unreachable: wait, do not fail the run
MAX_ROUNDS = 5
QUOTA_WAIT_S = 120
NL = chr(10)


def wilson_lower(correct: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = correct / n
    return (p + z * z / (2 * n) - z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)


def risky(feat) -> bool:
    return feat.group in RISKY_GROUPS or feat.span_check


def strong(feat, value: str) -> bool:
    return feat.verify == "always" and value not in feat.caution_values


def load_rows(ont) -> list[tuple]:
    """(source, place stem, place doc header, observation) of every model-made observation the ontology still has."""
    rows = []
    for source, (top, sub, types) in SOURCES.items():
        root = data_dir() / top / sub
        for f in sorted(root.glob("*.json")) if root.exists() else []:
            doc = json.loads(f.read_text(encoding="utf-8"))
            head = {"place_fid": doc["place_fid"], "place_name": doc.get("place_name")}
            rows += [(source, f.stem, head, o) for o in doc["observations"]
                     if o["source_type"] in types and ont.valid(o["feature"], o["value"])]
    return rows


def current(records: dict[str, dict]) -> dict[str, str]:
    """content key -> label that still stands: a person's, or the Judge's unless it said wrong under an older audit
    prompt (a wrong verdict drops evidence, so a changed prompt gives it a second look)."""
    return {k: r["label"] for k, r in records.items()
            if not (r.get("by", "").startswith("judge:") and r["label"] == "wrong" and r.get("ph") != OBS_AUDIT.prompt_hash)}


def select(rows: list[tuple], ont, done: dict[str, str], seed: int = 7) -> list[tuple]:
    """Rows to label now: risky features in full, samples elsewhere, and in full every stratum whose labels so far
    miss the gate. Rows already labelled (by anyone) and repeats of one claim are left out."""
    rng = random.Random(seed)
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r[3]["feature"], r[3]["value"], r[0])].append(r)
    out = []
    for (fid, value, source), items in strata.items():
        keyed = {label_key(o["source_id"], o["feature"], o["value"], o["span"]["quote"]): (s, st, h, o)
                 for s, st, h, o in items}
        labels = collections.Counter(done[k] for k in keyed if k in done)
        todo = [r for k, r in keyed.items() if k not in done]
        n = labels["correct"] + labels["wrong"]
        failing = n >= GATE_MIN_N and wilson_lower(labels["correct"], n) < GATE_LOWER
        if risky(ont.features[fid]) or failing:
            out += todo
        else:
            rng.shuffle(todo)
            out += todo[:max(0, SAMPLE - sum(labels.values()))]
    return out


def chunks(rows: list[tuple], ont) -> list[list[tuple]]:
    """Calls of up to CHUNK items (CHUNK_IMAGES pictures), a place's items together, strong-Judge items apart."""
    by = collections.defaultdict(list)
    for r in rows:
        by[(strong(ont.features[r[3]["feature"]], r[3]["value"]), r[1])].append(r)
    out, cur, images, kind = [], [], 0, None
    for (is_strong, _), items in sorted(by.items()):
        for r in sorted(items, key=lambda r: (r[3]["feature"], r[0])):
            pic = r[0] == "gmaps_photo" or r[3]["source_type"] == "tiktok_frame"
            if cur and (len(cur) >= CHUNK or (pic and images >= CHUNK_IMAGES) or kind != is_strong):
                out.append(cur)
                cur, images = [], 0
            cur.append(r)
            images += pic
            kind = is_strong
    return out + ([cur] if cur else [])


def place_info(stem: str) -> dict:
    f = data_dir() / "gmaps" / "places" / stem / "place.json"
    p = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return {"category": p.get("category") or "unknown", "address": p.get("address") or "unknown"}


async def ask(task, client, model, **kw) -> dict:
    """task.ask, waiting out a busy proxy and spent accounts (every model of the pool resting) instead of failing."""
    tries = 0
    while True:
        try:
            return await task.ask(client, model, **kw)
        except OutOfQuota:
            print(f"  waiting for quota {now()}", flush=True)
            await asyncio.sleep(QUOTA_WAIT_S)  # accounts reset on their own; the run just waits
        except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
            tries += 1
            if tries == TRIES:
                raise
            await asyncio.sleep(WAIT_S)


async def guarded(coro, what: str):
    """One failed Judge call must not stop a run: it is reported and its item stays undecided (asked next run)."""
    try:
        return await coro
    except Exception as e:
        print(f"  error {what}: {type(e).__name__}: {str(e)[:200]}", flush=True)
        return "error"


async def audit_chunk(chunk: list[tuple], ont, city: str, clients: dict, sems: dict) -> collections.Counter:
    is_strong = strong(ont.features[chunk[0][3]["feature"]], chunk[0][3]["value"])
    task = OBS_AUDIT_STRONG if is_strong else OBS_AUDIT
    client, model = clients[task.role.name]
    places, feats = {}, {}
    lines, images, refs = [], [], {}
    for i, (source, st, h, o) in enumerate(chunk, 1):
        pref = places.setdefault(st, (f"P{len(places) + 1}", h["place_name"]))[0]
        feat = ont.features[o["feature"]]
        fref = feats.setdefault(feat.id, f"F{len(feats) + 1}")
        ev = evidence(st, o, source)
        ref = f"i{i}"
        refs[ref] = (source, st, o)
        pic = ""
        if ev["image"] is not None:
            images.append(ev["image"].read_bytes())
            pic = f" [picture {len(images)} attached]"
        meta = ", ".join(x for x in (ev["date"] and f"date {ev['date']}", ev["rating"] and f"rating {ev['rating']}") if x)
        lines.append(f"{ref}: {pref} {fref} {feat.id} = {o['value']}; quote \"{o['span']['quote']}\"{pic}"
                     f"{f' ({meta})' if meta else ''}" + NL + "    source: " + ev["text"])
    place_lines = []
    for st, (pref, pname) in places.items():
        info = place_info(st)
        place_lines.append(f"{pref}: {pname} ({info['category']}), {info['address']}")
    feat_lines = []
    for fid, fref in feats.items():
        f = ont.features[fid]
        claims = "; ".join(f"{v}: {c}" for v, c in f.claims.items()) if f.claims else ", ".join(f.values)
        feat_lines.append(f"{fref} {fid}: {f.hint}. Values: {claims}")
    async with sems[task.role.name]:
        ans = await ask(task, client, model, images=images, city=city, places=NL.join(place_lines),
                        features=NL.join(feat_lines), items=NL.join(lines))
    got = collections.Counter()
    by = f"judge:{ans.get('_model', model)}"
    for it in ans["items"]:
        if it["ref"] in refs:
            source, st, o = refs.pop(it["ref"])
            judge_label(o, st, source, it["verdict"], it["reason"][:300], by, task.prompt_hash)
            got[it["verdict"]] += 1
    got["missing"] += len(refs)
    return got


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    ont = load_ontology()
    clients = {t.role.name: t.role.client() for t in (OBS_AUDIT, OBS_AUDIT_STRONG)}
    clients = {k: (c.with_options(timeout=300, max_retries=0), m) for k, (c, m) in clients.items()}
    sems = {OBS_AUDIT.role.name: asyncio.Semaphore(OBS_AUDIT.parallel),
            OBS_AUDIT_STRONG.role.name: asyncio.Semaphore(OBS_AUDIT_STRONG.parallel)}
    total, rounds = collections.Counter(), 0
    while True:  # a sample that misses the gate pulls its whole stratum into the next round
        rows = load_rows(ont)
        todo = select(rows, ont, current(label_records()))
        parts = chunks(todo, ont)[:limit] if limit is not None else chunks(todo, ont)
        if not parts:
            break
        rounds += 1
        print(f"judge audit {city}: round {rounds}, {len(todo)} claims in {len(parts)} calls", flush=True)
        done = 0

        async def one(c):
            nonlocal done
            try:
                got = await audit_chunk(c, ont, name, clients, sems)
            except Exception as e:  # one bad call must not stop the run; its claims stay unlabelled
                got = collections.Counter(error=1)
                print(f"  error {c[0][1]} {c[0][3]['feature']}: {type(e).__name__}: {str(e)[:200]}", flush=True)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(parts)} calls {now()}", flush=True)
            return got

        this = collections.Counter()
        for got in await asyncio.gather(*(one(c) for c in parts)):
            this.update(got)
        total.update(this)
        labelled = this["correct"] + this["wrong"] + this["unsure"]
        if limit is not None or not labelled or rounds >= MAX_ROUNDS:
            break
    summary = {"at": now(), "rounds": rounds, "labels": dict(total)}
    print(f"judge audit {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
