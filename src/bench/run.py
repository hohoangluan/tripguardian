"""Run hidden trips through the real harness (Trip -> Decision -> Planning) and write the CSVs (docs/P2_TRIP_UNDERSTANDING.md §16).

Offline: the real serving data, no model, no network (travel is the rough estimate; holidays, events and advisories
come from the hand-entered files, weather is unknown).
"""

import csv
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import live
from corpus.serving import load as load_records
from decision import Tools as DecisionTools, create_engine as decision_engine
from harness import Harness, Request, Store
from planning import Engine as PlanningEngine, Tools as PlanningTools
from trip import Tools as TripTools, create_engine as trip_engine

from .generate import passes, settings
from .hidden import ROOT, HiddenTrip
from .score import NUMERIC, counts, score, summary
from .users import FORM, form_search_input, tap

CARD_LIMIT = 40
FIX_LIMIT = 8
RUN_COLUMNS = ("trip_id", "style", "tier", "status", *NUMERIC[:-1], "dropped_to_fit", "robustness", "ms_total",
               "asked", "typed_ms", "error")
FIELD_COLUMNS = ("trip_id", "style", "field", "truth", "got", "verdict")


def calendar(decision, by_id):
    """Weather unknown offline; holidays, events and advisories from the real hand-entered files."""
    ctx = decision["trip_context"]["context"]
    if not (ctx.get("start_date") and ctx.get("days")):
        return None, None
    first = date.fromisoformat(ctx["start_date"])
    ds = [first + timedelta(days=i) for i in range(ctx["days"])]
    hol, evs, adv = live.holidays(ds), live.events(ds), live.advisories(ds)
    return None, {d.isoformat(): {"holiday": hol.get(d), "events": evs.get(d, []), "advisories": adv.get(d, [])} for d in ds}


class Sim:
    def __init__(self, out: Path):
        self.cfg = settings()
        self.records = load_records()
        self.by_id = {r["id"]: r for r in self.records}

        def offline(*a, **k):
            raise live.Unavailable("benchmark is offline")
        data = ROOT / "data"
        self.trip = TripTools(trip_engine(data))
        self.decision = DecisionTools(decision_engine(data))
        self.planning = PlanningTools(PlanningEngine(self.records, geocode_fn=lambda t: None, matrix_fn=offline,
                                                     lodging_fn=lambda *a: [], background=False, conditions_fn=calendar))
        self.harness = Harness(self.trip, self.decision, self.planning, Store(out / "sessions"))


class Client:
    """One journey through the harness; a refused request is kept as the last error, never raised."""

    def __init__(self, sim: Sim, experience: str):
        self.sim = sim
        self.view = sim.harness.create(experience, "nothing")
        self.jid, self.rev = self.view["id"], self.view["revision"]
        self.events: list = []
        self.error: str | None = None
        self.n = 0

    def call(self, stage, op, payload=None):
        self.n += 1
        ev: list = []
        try:
            req = Request(request_id=f"b{self.n}", stage=stage, operation=op, expected_revision=self.rev,
                          payload=payload or {})
            self.view = self.sim.harness.request(self.jid, req, lambda e, d: ev.append((e, d)))
            self.rev, self.error = self.view["revision"], None
        except Exception as e:  # noqa: BLE001 -- a refused request is data for the run
            self.error = f"{type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"
        self.events = ev
        return self.error is None

    @property
    def result(self) -> dict:
        return self.view["result"]

    @property
    def card(self) -> dict | None:
        return self.result.get("card") if self.view["stage"] == "trip" else None

    @property
    def done(self) -> bool:
        return any(e == "done" for e, _ in self.events)


def select_rule(view: dict, si: dict, cfg: dict) -> list[str]:
    """The same pick for every style: per day, the first main experience and meal cards in display order."""
    days = si["context"]["days"] or cfg["default_days"]
    cards = [x for g in view["groups"] for x in g["cards"] if x["status"] == "main" and x["id"] not in view["selected"]]
    pick = []
    for role, k in cfg["per_day"].items():
        pick += [x["id"] for x in cards if x["role"] == role][:k * days]
    return pick


def settle(view: dict, act) -> int:
    """Until Decision would confirm: take a conflict's first "drop" fix, else drop the last selected place that is
    not locked. act(action) -> the new Decision view. Returns how many places were dropped."""
    for n in range(FIX_LIMIT):
        feas = view["feasibility"]
        if feas["status"] in ("feasible", "unknown"):
            return n
        fix = next((f["action"] for c in feas["conflicts"] for f in c["fixes"] if f["action"]["type"] == "drop"), None)
        if fix is None:
            free = [p for p in view["selected"] if p not in view["locked"]]
            if not free:
                return n
            fix = {"type": "drop", "place_id": free[-1]}
        view = act(fix)
    return FIX_LIMIT


def plan_note(pv: dict) -> str:
    """Why Planning offered nothing to confirm, in a few words for runs.csv."""
    if pv["ok"] and pv["variants"]:
        return ""
    back = pv.get("back_to_decision") or {}
    codes = [w.get("code", "") for w in pv.get("warnings", []) if isinstance(w, dict)]
    return f"plan not ok: {back.get('reason') or back.get('title') or ','.join(codes[:3]) or 'no variant'}"[:160]


def outcome(sim: Sim, t: HiddenTrip, decision: dict | None, plan: dict | None) -> dict:
    conf = (decision or {}).get("confirmed", [])
    bad = sum(1 for p in conf for h in t.hard if h.feature not in p["relaxed"]
              and passes(sim.by_id[p["id"]], (h.feature, h.op, h.value)) == "fail")
    unknown = [p for p in conf if (sim.by_id[p["id"]]["operation"].get("hours") is None)]
    return {"hard_violations": bad, "unknown_hours_share": round(len(unknown) / len(conf), 3) if conf else "",
            "robustness": (plan or {}).get("robustness", {}).get("level", ""), "warnings": len((plan or {}).get("warnings", [])),
            "reached_plan": int(bool(plan))}


def trip_style(sim: Sim, t: HiddenTrip, style: str, row: dict, tier: str) -> tuple[dict, list[dict]]:
    c = Client(sim, t.experience)
    turns = cards = typed = exits = unmapped = calls = 0
    base_card = False
    typed_ms: list[int] = []
    asked: list[str] = []

    def say(text: str) -> None:
        nonlocal turns, typed
        started = time.perf_counter()
        c.call("trip", "turn", {"kind": "text", "text": text})
        typed_ms.append(round((time.perf_counter() - started) * 1000))
        turns, typed = turns + 1, typed + 1

    if style == "brief":
        say(t.brief)
    seen: dict[str, int] = {}
    for _ in range(CARD_LIMIT):
        card = c.card
        if card is None or c.done or c.error:
            break
        seen[card["qid"]] = seen.get(card["qid"], 0) + 1
        if seen[card["qid"]] > 2:
            break                                            # the same card keeps coming back: stuck
        if tier == "live" and card["qid"] != "ready":
            from .live import reply                          # USER_SIM answers in prose, never told chip ids
            asked.append(card["qid"])
            cards += 1
            calls += 1
            say(reply(t, card))
            continue
        a = tap(card, t, c.result["understanding"])
        unmapped += a.unmapped
        exits += a.exit
        base_card |= card["qid"] == "base"
        asked.append(card["qid"])
        turns += 1
        cards += 1
        if a.kind == "show":
            c.call("trip", "turn", {"kind": "show"})
        else:
            c.call("trip", "turn", {"kind": "answer", "qid": card["qid"], "chips": a.chips, "value": a.value})
    row.update(turns_to_suggestion=turns, cards_asked=cards, typed_turns=typed, corrections=0, unmapped_chips=unmapped,
               unsure_skip_rate=round(exits / cards, 3) if cards else 0.0, typed_ms=" ".join(map(str, typed_ms)), asked=" ".join(asked))
    if not c.done:
        row.update(status="stuck", error=c.error or "no Search Input", model_calls=calls)
        return row, []
    si = c.view["outputs"]["trip"]
    understanding = c.result["understanding"]
    snap = sim.trip.snapshot(c.view["sessions"]["trip"])
    row["agent_fallbacks"] = sum("agent_fallback" in x["text"] for x in snap["transcript"] if x["role"] == "system")
    row["model_calls"] = calls + (typed - row["agent_fallbacks"] if tier == "live" else 0)
    derived = {k for k, f in snap["state"]["soft"].items()
               if any((e.get("tool") or "").startswith("chip:") and not (e.get("tool") or "").startswith(("chip:vibe:", "chip:clarify"))
                      for e in f["evidence"])}
    fields = score(t, style, si, understanding, derived, base_card, set(sim.cfg["chip_loves"]))
    c.call("trip", "advance")
    plan, note = None, ""
    if c.view["stage"] == "decision":
        for pid in select_rule(c.result["view"], si, sim.cfg):
            c.call("decision", "act", {"type": "select", "place_id": pid})

        def act(action):
            c.call("decision", "act", action)
            return c.result["view"]
        row["dropped_to_fit"] = settle(c.result["view"], act)
    if c.view["stage"] == "decision" and c.call("decision", "advance"):
        pv = c.result["view"]
        if pv["ok"] and pv["variants"]:
            c.call("planning", "act", {"type": "pick_variant", "id": pv["variants"][0]["id"]})
            if c.call("planning", "confirm"):
                plan = c.view["outputs"].get("planning")
        else:
            note = plan_note(pv)
    row.update(outcome(sim, t, c.view["outputs"].get("decision"), plan))
    row["error"] = c.error or note
    return row, fields


def baseline(sim: Sim, t: HiddenTrip, row: dict) -> tuple[dict, list[dict]]:
    si = form_search_input(t)
    fields = score(t, "baseline", si, None, set(), True, set(sim.cfg["chip_loves"]))
    row.update(turns_to_suggestion=len(FORM), cards_asked=len(FORM), typed_turns=0, corrections=0, unmapped_chips=0,
               unsure_skip_rate=0.0, model_calls=0, agent_fallbacks=0)
    def emit(*a):
        return None
    d = sim.decision.create({"search_input": si})
    view = d["view"]
    for pid in select_rule(d["view"], si, sim.cfg):
        view = sim.decision.apply(d["id"], "act", {"type": "select", "place_id": pid}, emit)["view"]
    row["dropped_to_fit"] = settle(view, lambda a: sim.decision.apply(d["id"], "act", a, emit)["view"])
    decision, plan, err = None, None, ""
    try:
        decision = sim.decision.apply(d["id"], "confirm", {}, emit)
        p = sim.planning.create({"decision_output": decision})
        pv = p["view"]
        if pv["ok"] and pv["variants"]:
            sim.planning.apply(p["id"], "act", {"type": "pick_variant", "id": pv["variants"][0]["id"]}, emit)
            plan = sim.planning.apply(p["id"], "confirm", {}, emit)
        else:
            err = plan_note(pv)
    except Exception as e:  # noqa: BLE001 -- refused downstream: the row shows it
        err = f"{type(e).__name__}: {str(e)[:160]}"
    row.update(outcome(sim, t, decision, plan))
    row["error"] = err
    return row, fields


def run_one(sim: Sim, t: HiddenTrip, style: str, tier: str) -> tuple[dict, list[dict]]:
    row = {k: "" for k in RUN_COLUMNS} | {"trip_id": t.id, "style": style, "tier": tier, "status": "ok"}
    started = time.perf_counter()
    if style == "brief" and not t.brief:
        return row | {"status": "no_brief"}, []
    try:
        row, fields = baseline(sim, t, row) if style == "baseline" else trip_style(sim, t, style, row, tier)
    except Exception as e:  # noqa: BLE001
        row.update(status="error", error=f"{type(e).__name__}: {e}"[:200])
        traceback.print_exc(limit=3)
        fields = []
    if fields:
        row.update(counts(fields))
    row["ms_total"] = round((time.perf_counter() - started) * 1000)
    return row, [{"trip_id": t.id, "style": style, **f} for f in fields]


def write(path: Path, rows: list[dict], columns) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _number(v: str):
    for kind in (int, float):
        try:
            return kind(v)
        except ValueError:
            pass
    return v


def read(path: Path, numeric: tuple = ()) -> list[dict]:
    """Rows an earlier (interrupted) run wrote, numbers back as numbers."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [{k: _number(v) if k in numeric and v != "" else v for k, v in r.items()} for r in csv.DictReader(f)]


def run(trips: list[HiddenTrip], styles: list[str], tier: str = "offline", out: Path | None = None,
        resume: bool = False) -> tuple[Path, list, list, list]:
    """resume: keep the rows already in out and run only the missing (trip, style) pairs. The CSVs are rewritten
    after every run, so a long live run that stops loses at most the run in progress."""
    out = out or ROOT / "data" / "bench" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    runs = read(out / "runs.csv", (*NUMERIC, "dropped_to_fit")) if resume else []
    fields = read(out / "fields.csv") if resume else []
    done = {(r["trip_id"], r["style"]) for r in runs}
    sim = Sim(out)
    for t in trips:
        for style in styles:
            if (t.id, style) in done:
                continue
            r, f = run_one(sim, t, style, tier)
            runs.append(r)
            fields += f
            write(out / "runs.csv", runs, RUN_COLUMNS)
            write(out / "fields.csv", fields, FIELD_COLUMNS)
    typed_ms: dict[str, list[int]] = {}
    for r in runs:
        if r["tier"] == "live":                              # offline typed turns never reach a model
            typed_ms.setdefault(r["style"], []).extend(int(x) for x in str(r.get("typed_ms") or "").split())
    summ = summary(runs, typed_ms)
    write(out / "summary.csv", summ, list(summ[0]) if summ else ["style"])
    return out, runs, fields, summ
