"""Deterministic hidden-trip generator: realistic correlations, coverage quotas, only trips the corpus can serve."""

import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import yaml

from corpus.serving import check, feature, load as load_records
from trip import Catalog

from .hidden import EFFORT_SIGNALS, ROOT, AnchorTruth, Dates, HardRule, HiddenTrip, expected_hard, save

WHO = ("solo", "partner", "friends", "kids", "parents")
VEHICLES = ("motorbike", "car", "ride")
SIGNALS = ("knee", "elderly", "kids", "wheelchair", "vegetarian", "motion_sick", "height")
QUOTA = {"signal": 3, "companion": 5, "mobility": 8}
BUDGETS = (200_000, 250_000, 300_000, 400_000, 500_000, 700_000, 900_000, 1_200_000, 1_500_000, 2_000_000)


def settings() -> dict:
    return yaml.safe_load((ROOT / "config" / "bench.yaml").read_text(encoding="utf-8"))


def top_k() -> int:
    return yaml.safe_load((ROOT / "config" / "trip.yaml").read_text(encoding="utf-8"))["top_k"]


def passes(rec: dict, h: tuple[str, str, str]) -> str:
    """pass | fail | unknown of one hard rule; `ne` is corpus.serving.check, `eq` the same fail-closed reading."""
    fid, op, value = h
    if op == "ne":
        return check(rec, fid, value)
    f = feature(rec, fid)
    if f is None or f["status"] not in ("VERIFIED", "OUTDATED"):
        return "unknown"
    return "pass" if f["value"] == value else "fail"


def pick(rng: random.Random, weights: dict):
    keys = list(weights)
    return rng.choices(keys, [weights[k] for k in keys])[0]


def effort_for(rng: random.Random, signals: list[str]) -> str | None:
    s = set(signals)
    if not s & set(EFFORT_SIGNALS):
        return None
    if "wheelchair" in s:
        return "both"
    if "knee" in s:
        return pick(rng, {"steep": 6, "both": 4})
    if "elderly" in s:
        return pick(rng, {"steep": 4, "walk": 3, "both": 2, "none": 1})
    return pick(rng, {"walk": 1, "none": 1})


class Generator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.cfg = settings()
        self.k = top_k()
        self.records = load_records()
        catalog = Catalog.load(ROOT / "data", 1)
        self.loves = [x for x in self.cfg["love_keys"] if catalog.count(x) >= self.k]
        self.avoids = [x for x in self.cfg["avoid_keys"] if catalog.count(x) >= self.k]
        served = {r["id"] for r in self.records}
        popular = sorted((p for p in catalog.places if p.id in served), key=lambda p: (-p.weight, p.id))[:150]
        self.popular = [(p.id, p.name) for p in popular]
        self.by_id = {r["id"]: r for r in self.records}

    def companions(self, primary: str) -> list[str]:
        r = self.rng.random()
        if primary == "parents" and r < 0.3:
            return ["kids", "parents"]
        if primary == "partner" and r < 0.2:
            return ["kids", "partner"]
        return [primary]

    def people(self, who: list[str]) -> int:
        n = {"solo": 1, "partner": 2, "friends": self.rng.randint(3, 6), "parents": self.rng.randint(3, 4),
             "kids": self.rng.randint(3, 4)}
        return max(n[w] for w in who) + (1 if len(who) > 1 else 0)

    def dates(self) -> Dates:
        kind = pick(self.rng, {"start_date": 5, "month": 3, "undecided": 2})
        if kind == "start_date":
            start = pick(self.rng, {date(2026, 12, 12): 2, date(2027, 2, 5): 2, date(2026, 11, 20): 1})
            return Dates(kind=kind, start_date=start + timedelta(days=self.rng.randint(0, 20)))
        if kind == "month":
            return Dates(kind=kind, month=pick(self.rng, {12: 3, 2: 3, 11: 1, 1: 1, 4: 1, 6: 1}))
        return Dates(kind=kind)

    def one(self, tid: str, primary: str) -> HiddenTrip:
        rng = self.rng
        who = self.companions(primary)
        family = bool({"kids", "parents"} & set(who))
        mobility = pick(rng, {"car": 5, "ride": 4, "motorbike": 1} if family else {"motorbike": 6, "ride": 3, "car": 2})
        signals = (["elderly"] if "parents" in who else []) + (["kids"] if "kids" in who else [])
        if "parents" in who and rng.random() < 0.4:
            signals.append("knee")
        for kind, p in (("knee", 0.05), ("wheelchair", 0.04), ("vegetarian", 0.1), ("motion_sick", 0.08), ("height", 0.06)):
            if kind not in signals and rng.random() < p:
                signals.append(kind)
        purpose = pick(rng, {"relax": 4, "bond": 3, "nature": 2, "food_culture": 2, "photo": 1, "explore": 1, None: 2}
                       if family else {"photo": 3, "relax": 3, "explore": 2, "food_culture": 2, "nature": 2,
                                       "adventure": 2, "bond": 1, None: 2})
        if purpose == "relax":
            pace = pick(rng, {"slow": 8, "normal": 1, None: 1})
        elif purpose == "explore":
            pace = pick(rng, {"packed": 8, "normal": 1, None: 1})
        else:
            pace = pick(rng, {"slow": 4, "normal": 3, None: 2} if family else {"normal": 4, "packed": 2, "slow": 2, None: 2})
        experience = pick(rng, {"first": 7, "returning": 3})
        novelty = pick(rng, {"new": 4, "mix": 3, "familiar": 1, None: 2}) if experience == "returning" else None
        trip = dict(
            id=tid, experience=experience, days=pick(rng, {1: 2, 2: 5, 3: 8, 4: 5, 5: 2, 6: 1, 7: 1}),
            dates=self.dates(), companions=sorted(who), people=self.people(who), mobility=mobility,
            base=rng.choice(self.cfg["bases"]) if rng.random() < 0.4 else None,
            purpose=purpose, pace=pace,
            crowd_tolerance=pick(rng, {"avoid": 4, "ok_if_worth": 3, "fine": 1, None: 2}),
            novelty=novelty, budget_vnd=rng.choice(BUDGETS) if rng.random() < 0.75 else None,
            signals=signals, anchors=[])
        return self.finish(trip)

    def finish(self, trip: dict) -> HiddenTrip:
        """Fill what follows from the body (effort answer, hard filters), tastes, anchors and the indifferent list."""
        rng = self.rng
        trip["effort"] = trip.get("effort") or effort_for(rng, trip["signals"])
        if not set(trip["signals"]) & set(EFFORT_SIGNALS):
            trip["effort"] = None
        hard = expected_hard(trip["effort"], trip["signals"])
        trip["hard"] = [HardRule(feature=f, op=o, value=v) for f, o, v in hard]
        if "loves" not in trip:
            pool = [x for x in self.loves if not (trip["effort"] and x in self.cfg["effort_loves"])]
            trip["loves"] = sorted(rng.sample(pool, rng.randint(1, 3)))
            rest = [x for x in self.avoids if x not in trip["loves"]]
            trip["avoids"] = sorted(rng.sample(rest, pick(rng, {0: 5, 1: 3, 2: 1})))
        if trip["purpose"] == "adventure" and trip["effort"]:
            trip["purpose"] = "nature"
        if not trip["anchors"] and rng.random() < 0.4:
            ok = [(pid, name) for pid, name in self.popular if all(passes(self.by_id[pid], h) == "pass" for h in hard)]
            n = 1 if rng.random() < 0.75 else 2
            trip["anchors"] = [AnchorTruth(name=name, place_id=pid, priority=pick(rng, {"must": 6, "want": 4}))
                               for pid, name in rng.sample(ok, n)]
        dates = trip["dates"] = Dates.model_validate(trip["dates"]) if isinstance(trip["dates"], dict) else trip["dates"]
        trip["indifferent"] = [f for f in ("dates", "base", "purpose", "pace", "crowd_tolerance", "novelty", "budget_vnd")
                               if (dates.kind == "undecided" if f == "dates" else trip[f] is None)]
        return HiddenTrip.model_validate(trip)

    def servable(self, t: HiddenTrip) -> bool:
        rules = [(h.feature, h.op, h.value) for h in t.hard]
        return sum(1 for r in self.records if all(passes(r, h) == "pass" for h in rules)) >= self.k

    def run(self, n: int) -> list[HiddenTrip]:
        primaries = [w for w in WHO for _ in range(QUOTA["companion"])]
        weights = {"partner": 4, "friends": 3, "parents": 2, "kids": 2, "solo": 2}
        primaries += [pick(self.rng, weights) for _ in range(n - len(primaries))]
        self.rng.shuffle(primaries)
        trips = []
        for i, who in enumerate(primaries):
            t = self.one(f"t{i + 1:02d}", who)
            while not self.servable(t):
                t = self.one(t.id, who)
            trips.append(t)
        return self.repair(trips)

    def repair(self, trips: list[HiddenTrip]) -> list[HiddenTrip]:
        """Meet the quotas by changing trips that can take the change without breaking a correlation."""
        trips = list(trips)
        for v in VEHICLES:
            while sum(t.mobility == v for t in trips) < QUOTA["mobility"]:
                counts = Counter(t.mobility for t in trips)
                most = counts.most_common(1)[0][0]
                i = self.rng.choice([i for i, t in enumerate(trips) if t.mobility == most])
                trips[i] = trips[i].model_copy(update={"mobility": v})
        for kind in SIGNALS:
            tries = 0
            while sum(kind in t.signals for t in trips) < QUOTA["signal"] and tries < 200:
                tries += 1
                i = self.rng.randrange(len(trips))
                t = trips[i]
                if kind in t.signals or kind in ("elderly", "kids"):
                    continue
                raw = t.model_dump()
                raw.update(signals=raw["signals"] + [kind], effort=None, hard=None, anchors=[])
                if any(x in self.cfg["effort_loves"] for x in raw["loves"]) and kind in EFFORT_SIGNALS:
                    raw.pop("loves")
                new = self.finish(raw)
                if self.servable(new):
                    trips[i] = new
        return trips


def generate(seed: int, path: Path | None = None) -> list[HiddenTrip]:
    cfg = settings()
    trips = Generator(seed).run(cfg["trips"])
    header = (f"# Hidden trips for python -m bench (docs/plans/BENCH.md). Generated by: python -m bench generate "
              f"--seed {seed}. Frozen: edit only by regenerating.\n")
    if path is None:
        save(trips, header=header)
    else:
        save(trips, path, header)
    return trips


def quotas(trips: list[HiddenTrip]) -> dict:
    return {"signal": {k: sum(k in t.signals for t in trips) for k in SIGNALS},
            "companion": {k: sum(k in t.companions for t in trips) for k in WHO},
            "mobility": {k: sum(t.mobility == k for t in trips) for k in VEHICLES}}
