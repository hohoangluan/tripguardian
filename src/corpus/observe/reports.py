"""Observe for travellers' reports (corpus.review.reports): what several different people report becomes evidence.

Each report is read once by the Extractor with the Maps-review prompt (corpus.llm.REVIEW_OBSERVE: the same ontology
and rules, a quote must be words of the report) and the result is cached in data/reports/extracted.jsonl per (report,
prompt hash, ontology version). A (place, feature, value) that REPORTS_MIN different reporters said is written to
data/reports/observations/<fid_dir>.json, one observation per reporter, source_type "traveller_report". aggregate
takes that source as authoritative: undisputed, the reported value is served; against what reviews say, the feature is
served uncertain with both sides kept, so a fact travellers dispute is no longer served as settled. Below REPORTS_MIN
nothing is written -- one person's word does not change the corpus.
"""

import asyncio
import collections
import json

import openai

from ..crawl.common.files import append_jsonl, data_dir, load_config, now, safe_name, write_json
from ..llm import EXTRACTOR, REVIEW_OBSERVE
from ..ontology import load as load_ontology
from ..review.reports import load as load_reports
from . import observation
from .gmaps.gate import BadAnswer, gate

# Different reporters saying the same (feature, value) of a place before it becomes evidence. Measured 2026-10-06 on
# the nearest proxy, independent Maps reviewers stating the same (place, feature, value), against the accurate labels:
# share right by number of people 1: 70%, 2: 69%, 3: 76%, 4: 78%, 5: 81%, 6: 80%, 7: 84%, 8+: 89%; the Wilson lower
# bound first reaches the label gate's 0.80 at 8 (0.87). Same bar as the corpus gate, so 8. Measure again on real
# reports once they come in (do reports that crossed the bar agree with evidence found later?).
REPORTS_MIN = 8
SOURCE_TYPE = "traveller_report"
PARALLEL = 8
TRIES = 2


def _root():
    return data_dir() / "reports"


def _cache() -> dict[str, list[dict]]:
    f = _root() / "extracted.jsonl"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["key"]] = rec["observations"]
    return out


def _place(place_id: str) -> dict:
    f = data_dir() / "gmaps" / "places" / safe_name(place_id) / "place.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


async def _read(client, model: str, city: str, rep: dict, ont) -> list[dict]:
    """The (feature, value, quote, context) a report states, as the gate keeps them."""
    place = _place(rep["place_id"])
    refs = {"r1": {"text": rep["text"]}}
    note = ""
    for _ in range(TRIES):
        try:
            answer = await REVIEW_OBSERVE.ask(client, model, city=city, name=place.get("name") or rep["place_id"],
                                              category=place.get("category") or "none", ontology=ont.prompt_text(),
                                              reviews=f"r1: {rep['text']}", note=note)
            kept, _, _ = gate(answer, refs, ont)
            return [o for _, o in kept]
        except openai.APIError:
            raise
        except (BadAnswer, ValueError, TypeError, KeyError) as e:
            note = f"Your previous answer was rejected ({type(e).__name__}). Answer again with JSON that matches the schema."
    return []


def group(reports: list[dict], said: dict[str, list[dict]]) -> dict[str, list[tuple[dict, dict]]]:
    """place_id -> (report, observation) of every (feature, value) that REPORTS_MIN different reporters said; a
    reporter counts once per (feature, value), with their newest report."""
    by = collections.defaultdict(dict)  # (place, feature, value) -> reporter -> (report, observation)
    for rep in sorted(reports, key=lambda r: r["at"]):
        for o in said.get(rep["id"], []):
            by[(rep["place_id"], o["feature"], o["value"])][rep["reporter"]] = (rep, o)
    out = collections.defaultdict(list)
    for (place_id, _, _), people in by.items():
        if len(people) >= REPORTS_MIN:
            out[place_id] += list(people.values())
    return out


async def _run(city: str) -> dict:
    name, _ = load_config(city)
    ont = load_ontology()
    reports = load_reports()
    cache = _cache()
    key = lambda rep: f"{rep['id']}|{REVIEW_OBSERVE.prompt_hash}|{ont.version}"  # noqa: E731
    todo = [r for r in reports if key(r) not in cache]
    status = collections.Counter(cached=len(reports) - len(todo))
    if todo:
        client, model = EXTRACTOR.client()
        client = client.with_options(timeout=240, max_retries=0)
        sem = asyncio.Semaphore(PARALLEL)

        async def one(rep):
            async with sem:
                try:
                    obs = await _read(client, model, name, rep, ont)
                except openai.APIError as e:  # asked again next run
                    print(f"  report {rep['id']}: {type(e).__name__}", flush=True)
                    status["failed"] += 1
                    return
            cache[key(rep)] = obs
            append_jsonl(_root() / "extracted.jsonl", {"key": key(rep), "report_id": rep["id"], "observations": obs})
            status["read"] += 1

        await asyncio.gather(*(one(r) for r in todo))
    said = {r["id"]: cache.get(key(r), []) for r in reports}
    out = _root() / "observations"
    written = set()
    for place_id, items in group(reports, said).items():
        observations = [observation(
            id=f"report:{rep['id']}:{i}", place_fid=place_id, feature=o["feature"], value=o["value"],
            context=o["context"], source_type=SOURCE_TYPE, source_id=rep["id"], author=f"traveller:{rep['reporter']}",
            observed_at=rep["at"][:10], quote=o["quote"], field="text",
            extractor=f"review_observe@{REVIEW_OBSERVE.prompt_hash}", ontology_version=ont.version)
            for i, (rep, o) in enumerate(items)]
        target = out / f"{safe_name(place_id)}.json"
        write_json(target, {"place_fid": place_id, "place_name": _place(place_id).get("name"),
                            "as_of": max(rep["at"][:10] for rep, _ in items), "ontology_version": ont.version,
                            "source": "reports", "voices": 0, "observations": observations, "built_at": now()})
        written.add(target.name)
    removed = 0
    for p in out.glob("*.json") if out.exists() else []:
        if p.name not in written:  # no (feature, value) of this place has enough reporters any more
            p.unlink()
            removed += 1
    summary = {"at": now(), "reports": len(reports), "status": dict(status), "places": len(written),
               "removed": removed}
    print(f"reports observe {city}: {json.dumps(summary, ensure_ascii=False)}", flush=True)
    return summary


def run(city: str) -> dict:
    return asyncio.run(_run(city))
