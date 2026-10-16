"""Real Đà Lạt trips over the served corpus (data/serving/places.json): the cases the realism checks and the bench
run on. Every case is a Decision Output with a compiled day frame (src/trip/domain/frame.py CompiledFrame), a booked
lodging and the places a real group would pick. No network: fake_matrix and a fixed sun."""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path

from plan_fixtures import CFG, FakeLive, fake_matrix, fixed_sun, no_geocode

ROOT = Path(__file__).resolve().parents[2]
SERVING = ROOT / "data" / "serving" / "places.json"
AIRPORT = {"text": "Sân bay Liên Khương", "lat": 11.7500, "lng": 108.3667}
BUS = {"text": "Bến xe liên tỉnh Đà Lạt", "lat": 11.9271, "lng": 108.4446}


@cache
def records() -> list[dict]:
    return json.loads(SERVING.read_text(encoding="utf-8"))["records"]


@cache
def by_id() -> dict[str, dict]:
    return {r["id"]: r for r in records()}


# Where and what a case's place was when the case was written: the corpus moves (a rebuild can drop a record), and a
# place it lost is replaced by the nearest served place of the same kind (the plan's "missing -> substitute" rule).
# Homestay Lily: data/backup/serving-places-20261016-before-categories.json (gone from the 2026-10-16 06:14Z build).
REFERENCE = {"Homestay Lily": ("stay", 12.0976711, 108.54954)}


@cache
def pid(name: str) -> str:
    """The served id of a place by its exact name (case-insensitive), else the first name containing it, else the
    nearest served place of the same category group as REFERENCE says it was (ties by id), said once."""
    key = name.casefold()
    exact = [r["id"] for r in records() if r["identity"]["name"].casefold() == key]
    if exact:
        return exact[0]
    loose = [r["id"] for r in records() if key in r["identity"]["name"].casefold()]
    if loose:
        return loose[0]
    if name not in REFERENCE:
        raise KeyError(name)
    group, lat, lng = REFERENCE[name]
    same = [r for r in records() if r["identity"].get("category_group") == group
            and r["identity"].get("lat") is not None and r["identity"].get("lng") is not None]
    if not same:
        raise KeyError(name)
    sub = min(same, key=lambda r: ((r["identity"]["lat"] - lat) ** 2 + (r["identity"]["lng"] - lng) ** 2, r["id"]))
    print(f"realistic_cases: {name!r} is not in the corpus; using {sub['identity']['name']!r} ({sub['id']}), "
          f"the nearest served {group} place")
    return sub["id"]


def frame(start_date: str, days: int, *, starts=None, ends=None, busy=(), arrive=None, leave=None, meals=None,
          rest=None, intensity=None, visit=None) -> dict:
    """A CompiledFrame as Trip dumps it into context.frame. busy: [{"day": i | None, "start", "end", "kind", "label",
    "where"}]."""
    d0 = date.fromisoformat(start_date)
    out = []
    for i in range(days):
        blocks = [{"start": b["start"], "end": b["end"], "kinds": [b["kind"]], "labels": [b["label"]],
                   "where": b.get("where")} for b in busy if b.get("day") in (None, i)]
        out.append({"date": (d0 + timedelta(days=i)).isoformat(),
                    "start": (starts or {}).get(i, "14:00" if i == 0 and days > 1 else "08:00"),
                    "end": (ends or {}).get(i, "12:00" if i == days - 1 and days > 1 else "21:00"),
                    "busy": blocks, "intensity": (intensity or {}).get(i, "normal")})
    return {"days": out, "arrive": arrive, "leave": leave, "drive_day_min": None, "periods": [], "visit": visit or {},
            "meals": meals or {"skip": [], "breakfast_at_lodging": False, "snacks": False, "shift_min": 0},
            "rest": rest, "pattern": None, "issues": []}


def case(cid, places, *, lodging="Homestay Lily", days=3, start="2026-11-06", pace="normal", mobility="car",
         companions=(), people=2, soft=(), entry=None, exit=None, edits=(), expect=None, must=(), **frame_kw):
    return {"id": cid, "places": list(places), "lodging": lodging, "days": days, "start": start, "pace": pace,
            "mobility": mobility, "companions": list(companions), "people": people, "soft": list(soft),
            "entry": entry, "exit": exit, "edits": list(edits), "expect": expect or {}, "must": list(must),
            "frame": frame(start, days, **frame_kw)}


CENTRE_SIGHTS = ["Ga Đà Lạt", "Chợ đà lạt", "Công Viên Yersin", "Chùa Linh Sơn", "XQ Đà Lạt Sử Quán"]
FOOD = ["Bánh Căn Nhỏ", "Lẩu gà lá é-gà nướng lu 668", "Nem nướng TÂN LONG", "Bánh Căn & Bò Né - PÉ TÒ VÒ",
        "Chả Ram Bắp Nem Nướng Tân Long"]
SWEET = ["Chạm cà phê & kem bơ Đà Lạt", "Kem bơ - Chè Huyền", "Coffee Em và Trịnh"]
FAR = ["Săn mây Panorama Cầu Đất", "Vườn Thú ZooDoo", "Đường Hầm Điêu Khắc", "Vườn dâu Chào Đà Lạt"]
FLIGHT_OUT = {"at": "2026-11-08T16:40", "how": "plane"}
FLIGHT_IN = {"at": "2026-11-06T10:00", "how": "plane"}

CASES = [
    # rhythm and time
    case("couple_slow_dawn", ["Săn mây Panorama Cầu Đất", "Coffee Em và Trịnh", "Chùa Linh Sơn", "Công Viên Yersin"],
         pace="slow", companions=["partner"], mobility="motorbike"),
    case("worker_meeting", CENTRE_SIGHTS[:3] + ["Bánh Căn Nhỏ"], days=2,
         busy=[{"day": 1, "start": "15:00", "end": "16:00", "kind": "work", "label": "Họp online", "where": "lodging"}]),
    case("night_bus_5am", CENTRE_SIGHTS[:4] + ["Bánh Căn Nhỏ"], days=2, starts={0: "05:00"}, entry=BUS,
         arrive={"at": "2026-11-06T05:00", "how": "bus"}),
    case("flight_1640", CENTRE_SIGHTS + ["Nem nướng TÂN LONG"], exit=AIRPORT, entry=AIRPORT, arrive=FLIGHT_IN,
         leave=FLIGHT_OUT, starts={0: "10:45"}, ends={2: "15:55"}),
    case("day_trip", ["Ga Đà Lạt", "Chợ đà lạt", "Bánh Căn Nhỏ"], days=1, starts={0: "08:00"}, ends={0: "20:00"}),
    case("seven_days", CENTRE_SIGHTS + FOOD + FAR + SWEET[:1], days=7, pace="slow"),
    # companions
    case("family_kid_nap", ["Vườn Thú ZooDoo", "Vườn dâu Chào Đà Lạt", "Thung lũng Tình Yêu", "Ga Đà Lạt",
                            "Bánh Căn Nhỏ", "Lẩu gà lá é-gà nướng lu 668"], companions=["kids", "partner"], people=4,
         busy=[{"day": None, "start": "12:30", "end": "14:00", "kind": "nap", "label": "Bé ngủ trưa", "where": "lodging"}],
         meals={"skip": [], "breakfast_at_lodging": False, "snacks": False, "shift_min": -30}),
    case("elderly_parents", ["Chùa Linh Sơn", "Ga Đà Lạt", "Công Viên Yersin", "Bánh Căn Nhỏ"], pace="slow",
         companions=["parents"], people=4, rest={"every_min": 90, "rest_min": 30}),
    case("friends_packed_bar", CENTRE_SIGHTS + ["Nem nướng TÂN LONG", "Lẩu gà lá é-gà nướng lu 668"], pace="packed",
         # Spec section 6: 2 main restaurants > 1 usable lunch+dinner slot (day 1 dinner).
         # This depends on the mains' 90-minute category-default length: day 2 ends at 12:00,
         # so lunch from 11:00 cannot hold either main, even before the road home.
         companions=["friends"], people=5, days=2, expect={"overload": True}),
    # food
    # Spec section 6: a dawn-pulled day 1 has 3 nominal slots (breakfast, lunch, dinner), plus day 2 breakfast/lunch.
    # The overload conclusion depends on the mains' 90-minute category-default length: only day 1 dinner
    # holds them; day 1 lunch ends at the 12:00-14:30 rest and day 2 ends at 12:00. Breakfast is not a main slot.
    # Dessert/cafe stops are light; they do not replace or create those slots.
    case("food_tour_8", FOOD + SWEET, days=2, soft=[{"feature": "local_specialty_food", "value": "present", "weight": 1}],
         expect={"overload": True}),
    case("zero_food", CENTRE_SIGHTS[:4], days=2),
    case("hotel_breakfast", CENTRE_SIGHTS[:3] + ["Lẩu gà lá é-gà nướng lu 668"], days=2,
         meals={"skip": ["breakfast"], "breakfast_at_lodging": True, "snacks": False, "shift_min": 0}),
    case("dessert_not_dinner", ["Chạm cà phê & kem bơ Đà Lạt", "Kem bơ - Chè Huyền", "Ga Đà Lạt"], days=1,
         starts={0: "09:00"}, ends={0: "21:00"}),
    # overload
    case("family_12_in_3", FAR + CENTRE_SIGHTS[:2] + ["Bánh Căn Nhỏ", "Lẩu gà lá é-gà nướng lu 668",
                                                      "Nem nướng TÂN LONG", "XQ Đà Lạt Sử Quán", "Chạm cà phê & kem bơ Đà Lạt"],
         companions=["kids", "partner"], people=4, expect={"overload": True}),
    case("twenty_in_2", CENTRE_SIGHTS + FOOD + FAR + SWEET + ["Thung lũng Tình Yêu", "Fresh Zoo"], days=2,
         expect={"overload": True}),
    case("short_by_40", CENTRE_SIGHTS + ["Thung lũng Tình Yêu", "Đường Hầm Điêu Khắc"], days=1, starts={0: "09:00"},
         ends={0: "19:00"}, expect={"overload": True, "extend": True}),
    case("must_go_kept", FAR + CENTRE_SIGHTS, days=1, must=["Săn mây Panorama Cầu Đất"], expect={"overload": True}),
    # missing data and weather
    case("rainy_month", ["Vườn dâu Chào Đà Lạt", "Thung lũng Tình Yêu", "Ga Đà Lạt", "Bánh Căn Nhỏ"], days=2,
         start="2026-08-14"),
    case("no_prices", ["Công Viên Yersin", "Chùa Linh Sơn", "Ga Đà Lạt"], days=1, starts={0: "08:00"}, ends={0: "18:00"}),
    # edits
    case("reorder_bad", CENTRE_SIGHTS[:4], days=1, starts={0: "08:00"}, ends={0: "20:00"},
         edits=[{"type": "reorder", "day": 0, "order": ["Chùa Linh Sơn", "Ga Đà Lạt", "Công Viên Yersin", "Chợ đà lạt"]}]),
    case("reorder_fine", CENTRE_SIGHTS[:3], days=1, starts={0: "08:00"}, ends={0: "20:00"},
         edits=[{"type": "reorder", "day": 0, "order": ["Ga Đà Lạt", "Chợ đà lạt", "Công Viên Yersin"]}]),
    case("add_to_full_day", CENTRE_SIGHTS, days=1, starts={0: "08:00"}, ends={0: "17:00"}),
]


@dataclass
class Run:
    case: dict
    view: dict
    days: list = field(default_factory=list)       # view itinerary days
    unplaced: set = field(default_factory=set)     # ids the plan shows as not placed / dropped
    ids: dict = field(default_factory=dict)        # case place name -> id
    home: tuple | None = None                      # (lat, lng) of the lodging
    seconds: float = 0.0
    errors: list = field(default_factory=list)     # edits the engine refused: "reorder: <reason>"
    ghosts: list = field(default_factory=list)     # view["ghosts"]: faded suggestions (day 0-based, minutes)


def decision(c: dict) -> dict:
    ids = {name: pid(name) for name in c["places"]}
    lodge = by_id()[pid(c["lodging"])]
    ident = lodge["identity"]
    roles = {ids[n]: "anchor" for n in c["must"]}
    return {
        "confirmed": [{"id": i, "name": n, "role": roles.get(i, "selected"), "visit": None, "flags": [], "relaxed": []}
                      for n, i in ids.items()],
        "backup_pool": [], "wishlist": [], "decision_log": [], "feasibility": {},
        "lodging": {"kind": "corpus", "id": lodge["id"], "lat": ident["lat"], "lng": ident["lng"], "text": ident["name"]},
        "trip_context": {
            "context": {"start_date": c["start"], "month": None, "days": c["days"], "base": None,
                        "entry_point": c["entry"], "exit_point": c["exit"], "mobility": c["mobility"],
                        "companions": c["companions"], "people": c["people"], "day_end": None, "budget_vnd": None,
                        "lodging_booked": "yes", "frame": c["frame"]},
            "hard_filters": [], "anchors": [{"place_id": ids[n], "priority": "must"} for n in c["must"]],
            "soft_weights": c["soft"], "pace": {"level": c["pace"], "max_leg_min": None, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []},
    }


def engine():
    from planning import Engine
    from planning.session import Store
    return Engine(records(), cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode,
                  matrix_fn=fake_matrix, sun_fn=fixed_sun, background=False)


def _unplaced(view: dict) -> set:
    out = {u["place_id"] for u in view.get("unplaced") or []}
    out |= set((view.get("state") or {}).get("plan_dropped") or [])
    chosen = (view.get("state") or {}).get("chosen_variant")
    for v in view.get("variants") or []:
        if v["id"] == chosen:
            out |= {d["place_id"] for d in v.get("dropped") or v.get("dropped_by_plan") or []}
    return out


def _visits(itinerary) -> int:
    return sum(i["kind"] == "visit" for d in itinerary or [] for i in d["items"])


def pick(eng, sid: str, view: dict) -> dict:
    """The view the user ends up reading after create: the plan itself, else the plan that keeps their list ("keep_all"
    when the engine offers it), else the confirmable variant with the most visits (never a 0-visit plan while another
    pickable plan has visits), else the unpicked variant with the most visits. The unpicked fallback carries
    "_pick_note", which run_case records in Run.errors."""
    if view.get("itinerary") or not (view.get("variants") or view.get("keep_all")):
        return view
    variants = view.get("variants") or []
    ready = sorted((v for v in variants if v.get("status", "available") == "available"),
                   key=lambda v: -_visits(v.get("itinerary")))
    order = (["keep_all"] if view.get("keep_all") else []) + [v["id"] for v in ready]
    from planning.session import ActionError
    best, best_visits = None, -1
    for vid in order:
        try:
            got = eng.act(sid, {"type": "pick_variant", "id": vid})["view"]
        except ActionError:         # the engine refuses to confirm this one
            continue
        n = _visits(got.get("itinerary"))
        if n > best_visits:
            best, best_visits = got, n
        if n:
            return got
    if best is not None:
        return best
    pool = ([view["keep_all"]] if view.get("keep_all") else []) + variants
    top = max(pool, key=lambda v: _visits(v.get("itinerary")), default=None)
    if top is None:
        return view
    return {**view, "itinerary": top.get("itinerary") or [], "unplaced": top.get("dropped_by_plan") or [],
            "_pick_note": f"pick: nothing confirmable, showing unpicked {top.get('id')}"}


def run_case(c: dict, eng=None) -> Run:
    import time
    from planning.session import ActionError
    eng = eng or engine()
    d = decision(c)
    started = time.perf_counter()
    out = eng.create(d)
    sid, view = out["id"], out["view"]
    view = pick(eng, sid, view)
    seconds = time.perf_counter() - started
    ids = {name: pid(name) for name in c["places"]}
    errors: list = [view["_pick_note"]] if view.get("_pick_note") else []
    for edit in c["edits"]:
        action = {**edit, "order": [ids[n] for n in edit["order"]]} if edit["type"] == "reorder" else edit
        try:
            view = eng.act(sid, action)["view"]
        except ActionError as e:        # a refused edit leaves the plan as it was; the checks judge what the user sees
            errors.append(f"{edit['type']}: {e}")
    lodge = by_id()[pid(c["lodging"])]["identity"]
    return Run(c, view, view.get("itinerary") or [], _unplaced(view), ids, (lodge["lat"], lodge["lng"]), seconds, errors,
               view.get("ghosts") or [])


def render(run: Run) -> str:
    """The plan as the lines a user reads, for a person to judge."""
    names = {i: n for n, i in run.ids.items()}
    out = [f"# {run.case['id']} · {len(run.case['places'])} nơi · {run.seconds:.2f}s"]
    for d in run.days:
        out.append(f"Ngày {d['day']} ({d['date']}) · {d['window'][0]}-{d['window'][1]}")
        for i in d["items"]:
            what = i.get("name") or names.get(i.get("place_id"), "") or i.get("note") or ""
            if i["kind"] == "travel":
                what = f"đi ({i.get('mode')}) tới {names.get(i.get('to'), i.get('to'))}" + (
                    f" [{i['note']}]" if i.get("note") else "")
            out.append(f"  {i['start']}-{i['end']}  {i['kind']:<9} {what}")
    for e in run.errors:
        out.append(f"Sửa bị từ chối: {e}")
    if run.unplaced:
        out.append("Chưa xếp: " + ", ".join(names.get(p, p) for p in sorted(run.unplaced)))
    if run.view.get("overload"):
        out.append("Quá tải: " + json.dumps(run.view["overload"], ensure_ascii=False)[:400])
    return "\n".join(out)
