"""judge audit: the Judge model labels what the Extractor claimed, in place of a person (docs/CORPUS.md §6).

Which model-made observations it reads (rule-made ones from Maps details / attributes are not labelled, nor a
targeted sample's opinions, which aggregate leaves out):
- every observation of a risky feature: effort, suitability and every `check: span` feature (hard filters, values
  that warn or widen a choice);
- a sample per (feature, value, source folder) of every other feature, grown step by step (SAMPLE_STEPS) while its
  precision is undecided: a stratum stops once its Wilson lower bound reaches GATE_LOWER (it passes);
- all observations of a stratum whose Wilson upper bound is below GATE_LOWER (it fails), or still undecided at the
  last step: that stratum is checked one by one, so only claims the Judge confirmed are left. Sample labels count
  there too, so growing a sample before failing costs no extra call.
Calls of up to CHUNK items, a place's items together: the places, the features' definitions and claims from the
ontology, and each item as its own closed block with its passage (review text, transcript, caption) or picture (Maps photo, video frame). Values that widen a choice
(`verify: always`, not a caution value) go to the strong Judge. Labels append to data/review/judge_labels.jsonl as
they arrive (corpus.review.judge_label), so a stopped run resumes; claims already labelled are skipped.
JUDGE_ENGINE=gemma (.env) runs the whole audit on the Extractor's Gemma instead (OBS_AUDIT_GEMMA, strict prompt, 8 items
per call, one round, no first reader, no strong Judge, no second look). Its wrong and unsure drop the claim now; once
the engine is back to the Codex Judge, those labels count as not done and the Judge reads those claims again.
"""

import asyncio
import collections
import json
import os
import random

import openai

from ..crawl.common.files import ROOT, data_dir, load_config, now
from ..llm import OBS_AUDIT, OBS_AUDIT_FIRST, OBS_AUDIT_GEMMA, OBS_AUDIT_STRONG, OutOfQuota
from ..observe import TARGETED, targeted_ok
from ..ontology import load as load_ontology
from ..review import evidence, judge_label, label_key, label_records

# model-made observations per source folder (rule-made gmaps_details / gmaps_attribute are not labelled)
SOURCES = {"gmaps": ("gmaps", "observations", {"gmaps_review"}),
           "tiktok": ("tiktok", "observations", {"tiktok_segment", "tiktok_caption", "tiktok_frame"}),
           "gmaps_photo": ("gmaps", "photo_observations", {"gmaps_photo"})}
RISKY_GROUPS = {"effort", "suitability"}
# labels a stratum of a feature that is not risky grows to while undecided; a 90%-precise stratum passes by 100
# (Wilson lower 0.826) instead of being checked in full
SAMPLE_STEPS = (30, 60, 100)
GATE_LOWER = 0.8  # same bar as the label gate (corpus.review.labels)
GATE_MIN_N = 30  # labelled items before a stratum can be judged from its sample (the label gate's min_n)
CHUNK, CHUNK_IMAGES = 24, 8  # items per call; 16 text matched 8 on a 161-claim re-ask (2026-10-05); 24 / 8 pictures
# raised 2026-10-06 to save Codex quota, not yet measured -- spot-check the labels they produce
CHUNK_GEMMA = 8  # Gemma's items per call: 8 measured best (16 and 24 let more wrong claims stand)
PASSAGE_GEMMA = 500  # chars around the quote on the Gemma audit: with its compact items -22% tokens, same precision
PASSAGE = None  # chars of source text around the quote an item shows (None: the whole passage evidence() gives)
BY_FEATURE = False  # calls group a feature's items (its definition once per call) instead of a place's
WAIT_S, TRIES = 30, 20  # 9router busy / unreachable: wait, do not fail the run
MAX_ROUNDS = 5
QUOTA_WAIT_S = 120
NL = chr(10)


def wilson_lower(correct: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = correct / n
    return (p + z * z / (2 * n) - z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)


def wilson_upper(correct: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 1.0
    p = correct / n
    return (p + z * z / (2 * n) + z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)


def verdict(correct: int, n: int, labelled: int) -> str | int:
    """A sampled stratum's state: "pass", "fail" (check every item) or the labels to grow its sample to."""
    if n >= GATE_MIN_N and wilson_lower(correct, n) >= GATE_LOWER:
        return "pass"
    if n >= GATE_MIN_N and wilson_upper(correct, n) < GATE_LOWER:
        return "fail"
    return next((s for s in SAMPLE_STEPS if s > labelled), "fail")


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
                     if o["source_type"] in types and ont.valid(o["feature"], o["value"])
                     and (o.get("sample") not in TARGETED or targeted_ok(ont.features[o["feature"]]))]
    return rows


def current(records: dict[str, dict], local: bool = False) -> dict[str, str]:
    """content key -> label that still stands: a person's, or the Judge's unless it said wrong under an older audit
    prompt (a wrong verdict drops evidence, so a changed prompt gives it a second look). Off the Gemma audit (local
    False), Gemma's wrong and unsure do not stand either: the Codex Judge reads those claims again. On Gemma (local)
    every label stands: Gemma never relabels what the Codex Judge decided, even under an older prompt."""
    prompts = {OBS_AUDIT.prompt_hash, OBS_AUDIT_GEMMA.prompt_hash}

    def stands(r):
        if not r.get("by", "").startswith("judge:"):
            return True
        if r.get("ph") == OBS_AUDIT_GEMMA.prompt_hash and r["label"] != "correct" and not local:
            return False
        if local:  # Gemma only adds labels: a claim the Codex Judge labelled is never asked again on Gemma
            return True
        return not (r["label"] == "wrong" and r.get("ph") not in prompts)
    return {k: r["label"] for k, r in records.items() if stands(r)}


def gemma() -> bool:
    """JUDGE_ENGINE=gemma in .env: the audit runs on the Extractor's Gemma (no Codex quota needed)."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return os.environ.get("JUDGE_ENGINE", "").strip().lower() == "gemma"


def claim_text(feat, value: str) -> str:
    """A value's claim as one sentence: the ontology's claims, else the hint's part for this value."""
    if feat.claims and value in feat.claims:
        return feat.claims[value]
    parts = [p.strip() for p in feat.hint.split(" / ")]
    if len(parts) == len(feat.values) > 1:
        return f"nơi này: {parts[feat.values.index(value)]}"
    return f"nơi này có: {feat.hint}"


def select(rows: list[tuple], ont, done: dict[str, str], seed: int = 7) -> list[tuple]:
    """Rows to label now: risky features in full, samples elsewhere grown to their next step, and in full every
    stratum that fails the gate. Rows already labelled (by anyone) and repeats of one claim are left out."""
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
        state = verdict(labels["correct"], labels["correct"] + labels["wrong"], sum(labels.values()))
        if risky(ont.features[fid]) or state == "fail":
            out += todo
        elif state != "pass":
            rng.shuffle(todo)
            out += todo[:max(0, state - sum(labels.values()))]
    return out


def picture(r: tuple) -> bool:
    return r[0] == "gmaps_photo" or r[3]["source_type"] == "tiktok_frame"


def chunks(rows: list[tuple], ont, size: int | None = None) -> list[list[tuple]]:
    """Calls of up to size (default CHUNK) items (CHUNK_IMAGES pictures), a place's (BY_FEATURE: a feature's) items together,
    strong-Judge items apart."""
    by = collections.defaultdict(list)
    for r in rows:
        by[(strong(ont.features[r[3]["feature"]], r[3]["value"]), r[3]["feature"] if BY_FEATURE else r[1])].append(r)
    out, cur, images, kind = [], [], 0, None
    for (is_strong, _), items in sorted(by.items()):
        for r in sorted(items, key=lambda r: (r[3]["feature"], r[0])):
            pic = picture(r)
            if cur and (len(cur) >= (size or CHUNK) or (pic and images >= CHUNK_IMAGES) or kind != is_strong):
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


def around(text: str, quote: str, n: int | None) -> str:
    """At most n chars of text centred on the quote (its first 40 chars), cut at word boundaries."""
    if n is None or len(text) <= n:
        return text
    at = text.casefold().find(" ".join(quote.split()).casefold()[:40])
    lo = max(0, min((at if at >= 0 else 0) - n // 3, len(text) - n))
    lo = text.rfind(" ", 0, lo) + 1 if lo else 0
    hi = text.find(" ", lo + n)
    return ("… " if lo else "") + text[lo: hi if hi > 0 else len(text)].strip() + (" …" if 0 < hi < len(text) else "")


def render(chunk: list[tuple], ont, claim: bool = False) -> tuple[dict, list[bytes], dict]:
    """A call's fields (places, features, items), its pictures and ref -> (source, place stem, observation).
    claim: the Gemma audit's compact items, each with its value's claim sentence and PASSAGE_GEMMA chars of source."""
    places, feats = {}, {}
    lines, images, refs = [], [], {}
    for i, (source, st, h, o) in enumerate(chunk, 1):
        pref = places.setdefault(st, (f"P{len(places) + 1}", h["place_name"]))[0]
        feat = ont.features[o["feature"]]
        fref = feats.setdefault(feat.id, f"F{len(feats) + 1}")
        ev = evidence(st, o, source)
        ev["text"] = around(ev["text"], o["span"]["quote"], PASSAGE_GEMMA if claim else PASSAGE)
        ref = f"i{i}"
        refs[ref] = (source, st, o)
        pic = ""
        if ev["image"] is not None:
            images.append(ev["image"].read_bytes())
            pic = f" [picture {len(images)} attached]"
        meta = ", ".join(x for x in (ev["date"] and f"date {ev['date']}", ev["rating"] and f"rating {ev['rating']}") if x)
        if claim:
            lines.append(f"<{ref}> {pref} {fref}={o['value']}{f' ({meta})' if meta else ''}" + NL
                         + f"claim: {claim_text(feat, o['value'])}" + NL
                         + f"quote: \"{o['span']['quote']}\"{pic}" + NL + f"src: {ev['text']}")
            continue
        # each item a closed block with its own source, so a long call does not mix one item's words into another's
        lines.append(f"<{ref}> place {pref} | {fref} {feat.id} = {o['value']}{f' | {meta}' if meta else ''}" + NL
                     + f"  quote: \"{o['span']['quote']}\"{pic}" + NL
                     + f"  source of {ref} only: {ev['text']}" + NL + f"</{ref}>")
    place_lines = []
    for st, (pref, pname) in places.items():
        info = place_info(st)
        place_lines.append(f"{pref}: {pname} ({info['category']}), {info['address']}")
    feat_lines = []
    for fid, fref in feats.items():
        f = ont.features[fid]
        claims = "; ".join(f"{v}: {c}" for v, c in f.claims.items()) if f.claims else ", ".join(f.values)
        feat_lines.append(f"{fref} {fid}: {f.hint}. Values: {claims}")
    return ({"places": NL.join(place_lines), "features": NL.join(feat_lines), "items": (NL + NL).join(lines)},
            images, refs)


async def label_with(task, chunk: list[tuple], ont, city: str, clients: dict, sems: dict, look: int = 1,
                     keep=None) -> tuple[collections.Counter, list[tuple]]:
    """One call of task over chunk. Verdicts in keep (all when None) are written as labels; the rows of the other
    verdicts and of items the answer left out are returned for another reader. On the Gemma audit an unsure is
    written as look 2 so aggregate drops it until the Codex Judge reads it again (current)."""
    client, model = clients[task.role.name]
    single = task is OBS_AUDIT_GEMMA
    fields, images, refs = render(chunk, ont, claim=single)
    async with sems[task.role.name]:
        ans = await ask(task, client, model, images=images, city=city, **fields)
    got, rest = collections.Counter(), []
    by = f"judge:{ans.get('_model', model)}"
    row_of = {f"i{i}": r for i, r in enumerate(chunk, 1)}
    for it in ans["items"]:
        ref = it["ref"].strip("<>/ ")  # small models now and then echo the item's tag
        if ref not in refs:
            continue
        source, st, o = refs.pop(ref)
        if keep is None or it["verdict"] in keep:
            verdict, note = it["verdict"], it.get("reason", it.get("doubt", ""))[:300]
            if single and verdict == "correct" and picture(row_of[ref]):
                # Gemma passed 35% of wrong picture claims (2026-10-06): its "correct" on a picture is a first-look
                # unsure (kept like an unlabelled claim) that the Codex Judge reads again (current)
                verdict, note = "unsure", f"gemma: correct (pictures need the strong Judge) {note}"[:300]
                got["gemma_picture_correct"] += 1
            judge_label(o, st, source, verdict, note, by, task.prompt_hash,
                        2 if single and it["verdict"] == "unsure" else look)
            got[verdict] += 1
        else:
            rest.append(row_of[ref])
    rest += [row_of[ref] for ref in refs]
    return got, rest


async def audit_chunk(chunk: list[tuple], ont, city: str, clients: dict, sems: dict, look: int = 1) -> collections.Counter:
    """The Judge's labels for one chunk. With a first reader (JUDGE_FIRST_MODEL) on a plain text chunk, its "correct"
    stands and the Judge reads only what it called wrong or unsure: a wrong drops evidence, so the Judge confirms it."""
    is_strong = look > 1 or strong(ont.features[chunk[0][3]["feature"]], chunk[0][3]["value"])
    if OBS_AUDIT_GEMMA.role.name in clients:  # the Gemma audit: one strict reader for every claim
        got, rest = await label_with(OBS_AUDIT_GEMMA, chunk, ont, city, clients, sems, look)
    elif is_strong:
        got, rest = await label_with(OBS_AUDIT_STRONG, chunk, ont, city, clients, sems, look)
    elif OBS_AUDIT_FIRST.role.name in clients and not any(picture(r) for r in chunk):  # measured on text only
        got, rest = await label_with(OBS_AUDIT_FIRST, chunk, ont, city, clients, sems, look, keep={"correct"})
        if rest:
            more, rest = await label_with(OBS_AUDIT, rest, ont, city, clients, sems, look)
            got.update(more)
            got["to_judge"] += len(rest) + sum(more.values())
    else:
        got, rest = await label_with(OBS_AUDIT, chunk, ont, city, clients, sems, look)
    got["missing"] += len(rest)
    return got


def first_reader() -> str:
    """JUDGE_FIRST_MODEL from .env, empty when the audit has no first reader."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return os.environ.get(OBS_AUDIT_FIRST.role.model_env, "").strip()


def unsure_rows(rows: list[tuple], records: dict[str, dict]) -> list[tuple]:
    """Rows whose latest label is a first-look Judge "unsure" (a person's unsure stands)."""
    out = []
    for r in rows:
        rec = records.get(label_key(r[3]["source_id"], r[3]["feature"], r[3]["value"], r[3]["span"]["quote"]))
        if rec and rec["label"] == "unsure" and rec.get("by", "").startswith("judge:") and rec.get("look", 1) == 1:
            out.append(r)
    return list({label_key(r[3]["source_id"], r[3]["feature"], r[3]["value"], r[3]["span"]["quote"]): r
                 for r in out}.values())


async def second_look(ont, name: str, clients: dict, sems: dict) -> collections.Counter:
    """The strong Judge reads again every claim the first Judge was unsure of; still unsure there = not enough
    evidence, and aggregate drops it like a wrong one (review.labels.verdicts)."""
    todo = unsure_rows(load_rows(ont), label_records())
    parts = chunks(todo, ont)
    print(f"judge audit {name}: second look, {len(todo)} unsure claims in {len(parts)} calls", flush=True)
    got = collections.Counter()

    async def one(c):
        try:
            return await audit_chunk(c, ont, name, clients, sems, look=2)
        except Exception as e:  # its claims keep the first look's unsure; asked again next run
            print(f"  error second look {c[0][1]}: {type(e).__name__}: {str(e)[:200]}", flush=True)
            return collections.Counter(error=1)

    for g in await asyncio.gather(*(one(c) for c in parts)):
        got.update(g)
    return got


async def run(city: str, limit: int | None = None) -> dict:
    name, _ = load_config(city)
    ont = load_ontology()
    local = gemma()
    tasks = (OBS_AUDIT_GEMMA,) if local else (OBS_AUDIT, OBS_AUDIT_STRONG) + ((OBS_AUDIT_FIRST,) if first_reader() else ())
    clients = {t.role.name: t.role.client() for t in tasks}
    clients = {k: (c.with_options(timeout=300, max_retries=0), m) for k, (c, m) in clients.items()}
    sems = {t.role.name: asyncio.Semaphore(t.parallel)
            for t in (OBS_AUDIT, OBS_AUDIT_STRONG, OBS_AUDIT_FIRST, OBS_AUDIT_GEMMA)}
    size = CHUNK_GEMMA if local else None
    total, rounds = collections.Counter(), 0
    while True:  # a sample that misses the gate pulls its whole stratum into the next round
        rows = load_rows(ont)
        todo = select(rows, ont, current(label_records(), local))
        parts = chunks(todo, ont, size)[:limit] if limit is not None else chunks(todo, ont, size)
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
        if limit is not None or not labelled or rounds >= (1 if local else MAX_ROUNDS):  # Gemma: one round
            break
    second = await second_look(ont, name, clients, sems) if limit is None and not local else collections.Counter()
    summary = {"at": now(), "rounds": rounds, "labels": dict(total), "second_look": dict(second)}
    print(f"judge audit {city}: {json.dumps(summary, ensure_ascii=False)}")
    return summary
