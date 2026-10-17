"""python -m bench latency: how long the corpus-backed steps take (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md
§7). Offline: no model, no network. Writes data/bench/latency/<timestamp>.json and prints a table."""

import json
import time
from datetime import datetime
from pathlib import Path

import orjson

ROOT = Path(__file__).resolve().parents[2]
SHIFT_DEG = 0.001  # each copy of a region moves this far east, so copies stay in the same city


def pct(xs: list[float]) -> dict:
    s = sorted(xs)
    at = lambda q: s[min(len(s) - 1, round(q * (len(s) - 1)))]  # noqa: E731
    ms = lambda v: round(v * 1000, 1)  # noqa: E731
    return {"n": len(s), "p50": ms(at(0.5)), "p95": ms(at(0.95)), "p99": ms(at(0.99)), "max": ms(s[-1])}


def timed(fn, *a, **k):
    t = time.perf_counter()
    out = fn(*a, **k)
    return out, time.perf_counter() - t


def replicate(records: list[dict], n: int) -> list[dict]:
    """n copies of a region's records: copy k has ids '<id>~k', its own areas and near-duplicate groups, points moved
    k * SHIFT_DEG east. Copy 0 is the original."""
    out = []
    for k in range(n):
        for r in records:
            c = orjson.loads(orjson.dumps(r))
            if k:
                c["id"] = f"{c['id']}~{k}"
                ident = c["identity"]
                if ident.get("area"):
                    ident["area"] = f"{ident['area']}~{k}"
                if ident.get("lng") is not None:
                    ident["lng"] = float(ident["lng"]) + k * SHIFT_DEG
                if c.get("near_duplicate_group") is not None:
                    c["near_duplicate_group"] = c["near_duplicate_group"] + k * 1_000_000
            out.append(c)
    return out


def decision_bench(data, cfg, trips_n: int = 30) -> dict:
    """create for each eval trip, then select x3, lock, drop, undo, page, why_not on its shortlist."""
    from corpus.ontology import load as load_ontology
    from decision import Engine, Store, eval_search_input, eval_trips

    eng = Engine(data, cfg, Store(None))
    version, trips = eval_trips()
    times: dict[str, list[float]] = {k: [] for k in ("create", "select", "lock", "drop", "undo", "page", "why_not")}
    for trip in trips[:trips_n]:
        si = eval_search_input(trip, version).model_dump(mode="json")
        si["ontology_version"] = load_ontology().version
        v, dt = timed(eng.create, si)
        times["create"].append(dt)
        sid = v["id"]
        cards = [c["id"] for g in v["view"]["groups"] for c in g["cards"]]
        for pid in cards[:3]:
            times["select"].append(timed(eng.act, sid, {"type": "select", "place_id": pid})[1])
        if len(cards) > 3:
            times["lock"].append(timed(eng.act, sid, {"type": "lock", "place_id": cards[3]})[1])
        if len(cards) > 4:
            times["drop"].append(timed(eng.act, sid, {"type": "drop", "place_id": cards[4], "reason": "far"})[1])
            times["undo"].append(timed(eng.act, sid, {"type": "undo"})[1])
        groups = [g["id"] for g in v["view"]["groups"] if g["id"] != "anchors"]
        if groups:
            times["page"].append(timed(eng.page, sid, groups[0])[1])
        if cards:
            times["why_not"].append(timed(eng.why_not, sid, cards[-1])[1])
    return {k: pct(v) for k, v in times.items() if v}


def replicate_intel(intel: list[dict], n: int) -> list[dict]:
    """The intel rows that go with replicate(): copy k has place_fid '<fid>~k'."""
    out = []
    for k in range(n):
        for i in intel:
            c = orjson.loads(orjson.dumps(i))
            if k:
                c["place_fid"] = f"{c['place_fid']}~{k}"
            out.append(c)
    return out


def startup_bench() -> dict:
    """Process-start costs, each measured once in this process (imports already warm)."""
    from corpus.serving import load as load_records
    from corpus.snapshot import Snapshot
    from decision import Data
    from planning import create_engine as planning_engine

    from trip import Catalog
    from trip.infrastructure.settings import load as trip_settings  # trip exports no settings loader; bench is tooling

    out = {}
    region, out["snapshot.region_s"] = timed(lambda: Snapshot.open().region())
    _, out["serving.load_s"] = timed(load_records)
    _, out["decision.Data.load_s"] = timed(Data.load)
    _, out["trip.Catalog.from_snapshot_s"] = timed(Catalog.from_snapshot, region, trip_settings().n_min)
    _, out["planning.create_engine_s"] = timed(planning_engine, ROOT / "data")
    return {k: round(v, 3) for k, v in out.items()}


def queries(records: list[dict]) -> list[str]:
    """Ten place names that exist (their first 20 characters) and five that match nothing."""
    return [r["identity"]["name"][:20] for r in records[:10]] + ["quán xyz", "qwerty asdf", "không có nơi này", "zzz", "abc 123"]


def tools_bench(catalog, qs: list[str]) -> dict:
    """search_places as the Trip agent calls it (Catalog search, top 5)."""
    from trip.domain.resolve import search  # bench reaches into trip on purpose, like bench.generate does

    xs = [timed(lambda q=q: search(q, catalog)[:5])[1] for q in qs for _ in range(20)]
    return {"search_places": pct(xs)}


def harness_bench(trips_n: int = 10) -> dict:
    """The Decision tools the harness calls (validation, engine, snapshot), no model, as bench run's baseline style
    drives them: create for each eval trip, then three selects. Harness.request itself needs a journey through Trip,
    whose bench trips (config/bench_trips.yaml) are not in the repository."""
    from corpus.ontology import load as load_ontology
    from decision import Tools, create_engine, eval_search_input, eval_trips

    tools = Tools(create_engine(ROOT / "data"))
    binding = tools.engine.corpus_binding       # Tools refuses a Search Input that is not bound to the engine's release
    version, trips = eval_trips()
    times: dict[str, list[float]] = {"decision.create": [], "decision.select": []}
    for trip in trips[:trips_n]:
        si = eval_search_input(trip, version).model_dump(mode="json")
        si["ontology_version"] = load_ontology().version
        si["corpus_binding"] = binding.model_dump(mode="json") if hasattr(binding, "model_dump") else binding
        d, dt = timed(tools.create, {"search_input": si})
        times["decision.create"].append(dt)
        cards = [c["id"] for g in d["view"]["groups"] for c in g["cards"]]
        for pid in cards[:3]:
            times["decision.select"].append(
                timed(tools.apply, d["id"], "act", {"type": "select", "place_id": pid}, lambda *a: None)[1])
    return {k: pct(v) for k, v in times.items() if v}


def lodging_bench(data, cfg, records: list[dict], trips_n: int = 10) -> dict:
    """Planning's lodging list (tab "Chỗ ở" of Lựa chọn) for the Decision Output of each eval trip after three selects:
    first call and the repeat (cached)."""
    import live
    from corpus.ontology import load as load_ontology
    from decision import Engine, Store, eval_search_input, eval_trips
    from planning import Engine as PlanningEngine

    def offline(*a, **k):
        raise live.Unavailable("benchmark is offline")  # Planning falls back to the rough estimate
    eng = Engine(data, cfg, Store(None))
    planning = PlanningEngine(records, geocode_fn=lambda t: None, matrix_fn=offline, background=False,
                              conditions_fn=lambda *a, **k: (None, None))
    version, trips = eval_trips()
    first, again, found = [], [], []
    for trip in trips[:trips_n]:
        si = eval_search_input(trip, version).model_dump(mode="json")
        si["ontology_version"] = load_ontology().version
        v = eng.create(si)
        for card in [c["id"] for g in v["view"]["groups"] for c in g["cards"]][:3]:
            eng.act(v["id"], {"type": "select", "place_id": card})
        decision = eng.draft(v["id"], any_state=True)
        out, dt = timed(planning.lodging_options, decision)
        first.append(dt)
        again.append(timed(planning.lodging_options, decision)[1])
        found.append(len(out.get("candidates") or []))
    return {"stays_in_region": len(data.region.stay), "candidates": found, "first": pct(first), "cached": pct(again)}


def main(scales: list[int], out: Path | None) -> Path:
    from corpus.serving import load as load_records
    from corpus.snapshot import Region, shared
    from decision import Data
    from decision.settings import default

    from trip import Catalog
    from trip.infrastructure.settings import load as trip_settings

    cfg = default()
    base = load_records()
    n_min = trip_settings().n_min
    result = {"at": datetime.now().isoformat(timespec="seconds"), "places": len(base), "startup": startup_bench(),
              "decision": {}, "tools": {}}
    intel = shared().region().intel()
    for n in scales:
        recs = replicate(base, n)
        region, region_s = timed(lambda: Region.from_records(recs).warm())
        data = Data(region=region)
        result["decision"][f"x{n}"] = {"places": len(recs), "region_s": round(region_s, 3), **decision_bench(data, cfg)}
        catalog = Catalog.from_snapshot(Region.from_records(recs, replicate_intel(intel, n)), n_min)
        result["tools"][f"x{n}"] = tools_bench(catalog, queries(base))
    result["lodging"] = lodging_bench(Data.load(), cfg, base)
    result["harness"] = harness_bench()
    out = out or ROOT / "data" / "bench" / "latency"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return path
