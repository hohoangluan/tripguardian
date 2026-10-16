# Planning thực tế — lõi engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lõi xếp lịch của `src/planning` cho ra một lịch trình người thật dùng được (không giờ chết, bữa là quán thật đúng vai, đúng giờ trải nghiệm, theo khung ngày của user, không bỏ nơi âm thầm), có 3 hướng bỏ nơi khi quá tải, và dựng < 2 s.

**Architecture:** Giữ vỏ (`engine.py` phiên/act/preview/undo/replay, `validate.py`, Live Context, chỗ ở). Sửa đồng hồ một ngày (`schedule.simulate`) cho đúng vai ăn và hết "chờ" dài; thay bước chia ngày (`cluster` + `days.assign_days`) bằng chèn rẻ nhất vào sức chứa phút của từng ngày (`layout.py`); thay `composer` dò tập nơi bằng 3 thứ tự bỏ (`overload.py`). Bộ ca thật từ corpus Đà Lạt + 12 kiểm thực tế dẫn đường cho từng task.

**Tech Stack:** Python 3.12, pytest, dataclasses, pydantic (State), corpus serving JSON.

**Spec:** `docs/superpowers/specs/2026-10-15-planning-realistic-redesign-design.md` (§4–§8, §11, §13). Kế hoạch này là phần 1/3; Web §9 và gỡ phần sau chốt §10 là kế hoạch riêng, viết khi lõi xong (dùng tên dữ liệu thật của task 6–8).

**Ngoài kế hoạch này (chuyển sang kế hoạch 2, cùng Plan Output §9):** `days[i].header`, `risk`, `rain_swap`, `frame_report`; phí buổi đông khi `crowd_tolerance: avoid` và luật "tháng mưa: nơi ngoài trời ưu tiên sáng" (§5); xen kẽ nơi cho bé `interleave_kids` và trần 60′ nơi người lớn (§6); nghỉ tại quán gần thay khối nghỉ (§6); "Tự chọn nơi bỏ" dùng act có sẵn (`pick_variant` + `drop_place` / khôi phục) do Web nối. Học từ việc sửa lịch (§12 việc 10) là kế hoạch 3.

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0).
- Module chỉ giao tiếp qua public API (`__init__.py`); không deep import giữa module (`AGENTS.md`).
- Không bịa nơi, giá, giờ: thiếu dữ liệu → cờ / `None`, không đoán (`RULE.md` §3).
- Physical constraint không có đường nới; validator là nơi duy nhất kết luận đạt.
- Lựa chọn không chặn: thiếu chỗ → báo và cho user chọn, không tự bỏ âm thầm.
- Ngân sách không vào điểm của nơi nào; giá chỉ dùng trong hướng `cost` khi user chọn.
- Không sửa / nới test cũ chỉ để pass. Test khẳng định hành vi spec đã đổi (item `buffer`, `wait` dài, `v1/v2` theo mục tiêu, preset `diverse/least_travel/low_cost`) được viết lại theo hành vi mới, ghi rõ trong commit.
- Chạy pytest luôn kèm `--collect-in-virtualenv` (NFS `.browser` treo khi thu thập): `.venv/bin/python -m pytest --collect-in-virtualenv ...`.
- Không commit / push nếu user chưa bảo; working tree dùng chung nhiều phiên. Bước "Commit" dưới đây chỉ chạy khi user đã cho phép commit; nếu chưa, dừng ở bước kiểm và báo.
- Config mới nằm trong khối `realistic:` của `config/planning.yaml` (giá trị ở Task 1).

## Review Focus

- Chuyến không có ngày (`frame` thiếu, `start_date` None): `trip_days` rơi về config cũ, lõi mới vẫn chạy, không `KeyError` — test ở Task 4 (`test_trip_days_without_frame_keeps_the_config_window`).
- Ngày `intensity: free` hoặc bị khung bận ăn hết: sức chứa 0, không nơi nào được xếp vào, bữa vẫn có — test ở Task 5 (`test_a_free_day_takes_no_place`).
- Mọi nơi đều là "nhất định đi" mà vẫn không vừa: không hướng nào bỏ được; `overload` trả các hướng `available: False` với lý do, không vòng lặp vô hạn — test ở Task 6 (`test_all_protected_cannot_drop`).
- Quán chưa có giá ở hướng `cost`: không bị bỏ, thẻ ghi số nơi chưa có giá — test ở Task 6 (`test_cost_never_drops_unknown_price`).
- Phiên khôi phục sau restart (`_ensure_base` replay) với `chosen_variant` = `fit|travel|cost|main` và act `add_from_backup` của gợi ý: dựng lại đúng lịch — test ở Task 7 (`test_replay_rebuilds_an_accepted_suggestion`).

---

## File structure

| File | Trách nhiệm |
|---|---|
| `tests/planning/realistic_cases.py` (mới) | đọc corpus serving, ~24 chuyến thật, `run_case()` chạy Engine không mạng, `render()` ra chữ |
| `tests/planning/realistic_checks.py` (mới) | 12 kiểm thực tế, oracle độc lập với code engine |
| `tests/planning/test_planning_realism.py` (mới) | chạy 12 kiểm trên mọi ca; `PENDING` thu hẹp dần theo task |
| `tests/planning/bench_realistic.py` (mới) | p50 / p95 dựng + từng act; `--render DIR` |
| `src/planning/roles.py` (mới) | `meal_kind(rec, cfg)`, `pin_order(pins, wants)` |
| `src/planning/layout.py` (mới) | `capacity(cx)`, `assign(trip, ctxs, ids)` chèn rẻ nhất |
| `src/planning/overload.py` (mới) | 3 hướng bỏ, `extend`, `render_variant`, `plan_or_directions(trip)` |
| `src/planning/ghosts.py` (mới) | ô bữa / khoảng trống → ứng viên thật từ corpus |
| `src/planning/model.py` | `Place.meal_kind`, `Day.busy`, `Day.intensity`, `Item.kind` thêm `free`, `busy` |
| `src/planning/schedule.py` | vai ăn trong ô bữa, bữa bỏ, chặng gộp đệm, khoảng chờ dài → tự do / về nghỉ, khung bận |
| `src/planning/frame.py` | đọc `busy`, `intensity`, nơi tới / rời từ `context.frame` |
| `src/planning/build.py` | `schedule_trip` dùng `layout.assign`; `Schedule.leftover`; nút `@entry` / `@exit` |
| `src/planning/engine.py` | `_build_base` dùng `overload.plan_or_directions`; chọn sẵn `main`; ghost ids là backup |
| `src/planning/session.py` | `State.dismissed`, `State.keep_order_days`; act `dismiss_suggestion`, `keep_my_order`, `extend_days` |
| `src/planning/validate.py` | item mới, khung bận, mốc rời physical, trần lái ngày |
| `src/planning/timefit.py` | luật `light_snack` (ăn nhẹ buổi chiều) |
| `src/planning/settings.py`, `config/planning.yaml` | khối `realistic`, `meal_windows` mới |

---

### Task 1: Bộ ca thật + 12 kiểm + bench (mốc trước khi sửa)

**Files:**
- Create: `tests/planning/realistic_cases.py`, `tests/planning/realistic_checks.py`, `tests/planning/test_planning_realism.py`, `tests/planning/bench_realistic.py`
- Modify: `config/planning.yaml` (thêm khối `realistic`), `src/planning/settings.py` (field `realistic`)

**Interfaces:**
- Produces: `realistic_cases.CASES: list[dict]`, `run_case(case) -> Run`, `render(run) -> str`, `SERVING: Path`; `realistic_checks.CHECKS: dict[str, Callable[[Run], list[str]]]`; `Settings.realistic: dict`.

- [ ] **Step 1: Thêm config `realistic`**

Thêm vào cuối `config/planning.yaml`:

```yaml
# Realistic itinerary (docs/superpowers/specs/2026-10-15-planning-realistic-redesign-design.md). Minutes unless noted.
realistic:
  wait_max: 20               # a wait longer than this becomes free time or a rest at the lodging
  rest_home_min: 90          # free time at least this long, with the lodging near, is spent resting there
  rest_home_road_max: 15     # "near": each leg to and from the lodging at most this
  fill_min_gap: 60           # free time at least this long gets a suggestion
  light_factor: 0.5          # a light day holds this share of a normal day
  early_day_factor: 0.6      # a dawn day's capacity after its midday rest
  luggage_radius_min: 20     # last day by motorbike / bus after checkout: places this close to the exit only
  arrive_buffer_min: 45      # landing / getting off the bus to ready to go
  leave_buffer_min: 45       # at the airport / station before departure
  drop_bags_min: 15          # day one, arriving before check-in: stop at the lodging first
  breakfast_dishes: ["bánh căn", "phở", "bánh mì", "bún", "xôi", "hủ tiếu", "cháo", "bánh cuốn", "bánh ướt"]
  light_groups: ["dessert", "cafe"]
  meal_detour_max: 15
  suggest_radius_min: 15
  suggest_pool_max: 60
  extend_max_min: 60
  better_order_min: 15
  event_early_min: 15
```

Trong `src/planning/settings.py`, thêm field cuối dataclass `Settings` (sau `composer`):

```python
    realistic: dict = field(default_factory=dict)
```

- [ ] **Step 2: Kiểm config nạp được**

Run: `.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from planning.settings import load; print(load().realistic['wait_max'])"`
Expected: `20`

- [ ] **Step 3: Viết `tests/planning/realistic_cases.py`**

```python
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


def pid(name: str) -> str:
    """The served id of a place by its exact name (case-insensitive), else the first name containing it."""
    key = name.casefold()
    exact = [r["id"] for r in records() if r["identity"]["name"].casefold() == key]
    if exact:
        return exact[0]
    loose = [r["id"] for r in records() if key in r["identity"]["name"].casefold()]
    if not loose:
        raise KeyError(name)
    return loose[0]


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
         companions=["friends"], people=5, days=2),
    # food
    case("food_tour_8", FOOD + SWEET, days=2, soft=[{"feature": "local_specialty_food", "value": "present", "weight": 1}]),
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
    chosen = (view.get("state") or {}).get("chosen_variant")
    for v in view.get("variants") or []:
        if v["id"] == chosen:
            out |= {d["place_id"] for d in v.get("dropped") or v.get("dropped_by_plan") or []}
    return out


def run_case(c: dict, eng=None) -> Run:
    import time
    eng = eng or engine()
    d = decision(c)
    started = time.perf_counter()
    out = eng.create(d)
    sid, view = out["id"], out["view"]
    if not view.get("itinerary") and view.get("variants"):
        view = eng.act(sid, {"type": "pick_variant", "id": view["variants"][0]["id"]})["view"]
    seconds = time.perf_counter() - started
    ids = {name: pid(name) for name in c["places"]}
    for edit in c["edits"]:
        action = {**edit, "order": [ids[n] for n in edit["order"]]} if edit["type"] == "reorder" else edit
        view = eng.act(sid, action)["view"]
    lodge = by_id()[pid(c["lodging"])]["identity"]
    return Run(c, view, view.get("itinerary") or [], _unplaced(view), ids, (lodge["lat"], lodge["lng"]), seconds)


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
    if run.unplaced:
        out.append("Chưa xếp: " + ", ".join(names.get(p, p) for p in sorted(run.unplaced)))
    if run.view.get("overload"):
        out.append("Quá tải: " + json.dumps(run.view["overload"], ensure_ascii=False)[:400])
    return "\n".join(out)
```

- [ ] **Step 4: Viết `tests/planning/realistic_checks.py`**

```python
"""The 12 realism checks (spec §11). Each takes a Run and returns failure messages. The oracle here is independent of
the engine's own code: it reads the served records and the itinerary the user would see."""

from datetime import date

from realistic_cases import by_id
from plan_fixtures import CFG

R = CFG.realistic
SUNRISE, SUNSET = 6 * 60, 17 * 60 + 30          # plan_fixtures.fixed_sun
MAIN_MEALS = {"lunch": (11 * 60, 13 * 60 + 30), "dinner": (17 * 60 + 30, 20 * 60)}


def m(clock: str) -> int:
    h, mi = clock.split(":")
    return int(h) * 60 + int(mi)


def group(pid: str) -> str:
    return by_id()[pid]["identity"].get("category_group")


def present(pid: str, fid: str) -> bool:
    rec = by_id()[pid]
    for g in ("experience", "environment", "service", "effort", "suitability"):
        f = (rec.get(g) or {}).get(fid)
        if f and f.get("value") == "present":
            return True
    return False


def visits(run):
    for d in run.days:
        for i in d["items"]:
            if i["kind"] == "visit":
                yield d, i


def no_long_wait(run):
    return [f"day {d['day']} waits {m(i['end']) - m(i['start'])}′ at {i['start']}"
            for d in run.days for i in d["items"] if i["kind"] == "wait" and m(i["end"]) - m(i["start"]) > R["wait_max"]]


def _needed(run, d) -> list[str]:
    meals = run.case["frame"]["meals"]
    lo, hi = m(d["window"][0]), m(d["window"][1])
    return [n for n, (a, b) in MAIN_MEALS.items() if n not in meals["skip"] and lo <= b and max(lo, a) + 60 <= hi]


def meals(run):
    out = []
    for d in run.days:
        if not any(i["kind"] == "visit" for i in d["items"]):
            continue
        for name in _needed(run, d):
            a, b = MAIN_MEALS[name]
            covered = any(i["kind"] == "meal_free" and i.get("name") == name for i in d["items"]) or any(
                i["kind"] == "visit" and group(i["place_id"]) in {"restaurant", "market"} and a <= m(i["start"]) <= b
                for i in d["items"])
            if not covered:
                out.append(f"day {d['day']} has no {name}")
        for i in d["items"]:
            if i["kind"] == "visit" and group(i["place_id"]) in R["light_groups"] and \
                    MAIN_MEALS["dinner"][0] <= m(i["start"]) <= MAIN_MEALS["dinner"][1] and \
                    not any(j["kind"] == "meal_free" and j.get("name") == "dinner" or
                            j["kind"] == "visit" and group(j["place_id"]) == "restaurant" and
                            MAIN_MEALS["dinner"][0] <= m(j["start"]) <= MAIN_MEALS["dinner"][1] for j in d["items"]):
                out.append(f"day {d['day']}: {i['name']} stands in for dinner")
    return out


def every_pick_accounted(run):
    seen = {i["place_id"] for _, i in visits(run)}
    return [f"{n} is neither on the plan nor in the unplaced tray" for n, p in run.ids.items()
            if p not in seen and p not in run.unplaced]


def timed(run):
    out = []
    wants_sunset = any(w["feature"] == "sunset_view" for w in run.case["soft"])
    for d, i in visits(run):
        s = m(i["start"])
        if present(i["place_id"], "cloud_hunting") and not wants_sunset and not SUNRISE - 30 <= s <= SUNRISE + 60:
            out.append(f"{i['name']} (cloud hunting) at {i['start']}")
        if group(i["place_id"]) == "bar" and s < 17 * 60:
            out.append(f"{i['name']} (bar) at {i['start']}")
    return out


def open_hours(run):
    from planning.places import parse_hours, windows_on
    out = []
    for d, i in visits(run):
        h = (by_id()[i["place_id"]]["operation"].get("hours") or {}).get("value")
        if not h or not d.get("date"):
            continue
        wd = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[date.fromisoformat(d["date"]).weekday()]
        spans = windows_on(parse_hours(h), wd) or []
        if not any(o <= m(i["start"]) and m(i["end"]) <= c for o, c in spans):
            out.append(f"{i['name']} at {i['start']}-{i['end']} outside its hours on {wd}")
    return out


def frame_kept(run):
    out = []
    days = run.case["frame"]["days"]
    for d, fd in zip(run.days, days):
        lo, hi = m(fd["start"]), m(fd["end"])
        dawn = any(present(i["place_id"], "cloud_hunting") for i in d["items"] if i["kind"] == "visit")
        for i in d["items"]:
            if m(i["end"]) > hi or (m(i["start"]) < lo and not dawn):
                out.append(f"day {d['day']}: {i['kind']} {i['start']}-{i['end']} outside {fd['start']}-{fd['end']}")
            for b in fd["busy"]:
                if i["kind"] in {"visit", "travel"} and m(i["start"]) < m(b["end"]) and m(b["start"]) < m(i["end"]):
                    out.append(f"day {d['day']}: {i['kind']} {i['start']} overlaps {b['labels'][0]}")
    leave = run.case["frame"].get("leave")
    if leave and run.days:
        last = run.days[-1]["items"]
        limit = m(leave["at"][11:]) - R["leave_buffer_min"]
        if last and m(last[-1]["end"]) > limit:
            out.append(f"last day ends {last[-1]['end']}, needs to be at the {leave['how']} by {limit // 60:02d}:{limit % 60:02d}")
    return out


def kids(run):
    if "kids" not in run.case["companions"]:
        return []
    out = []
    for d in run.days:
        stops = [i for i in d["items"] if i["kind"] == "visit"]
        if len(stops) >= 3 and not any(i["kind"] in {"rest", "busy"} for i in d["items"]):
            out.append(f"day {d['day']}: {len(stops)} stops with kids and no rest")
        for i in d["items"]:
            if (i["kind"] == "meal_free" and i.get("name") == "dinner" or i["kind"] == "visit" and
                    group(i["place_id"]) == "restaurant" and m(i["start"]) >= 17 * 60) and m(i["start"]) > 19 * 60:
                out.append(f"day {d['day']}: dinner at {i['start']} with kids")
    return out


def no_idle_with_leftover(run):
    if not run.unplaced:
        return []
    out = []
    for d in run.days:
        items = d["items"]
        for a, b in zip(items, items[1:]):
            gap = m(b["start"]) - m(a["end"])
            if gap >= R["fill_min_gap"]:
                out.append(f"day {d['day']}: {gap}′ empty at {a['end']} while places are unplaced")
        for i in items:
            if i["kind"] in {"wait", "free"} and m(i["end"]) - m(i["start"]) >= R["fill_min_gap"]:
                out.append(f"day {d['day']}: {i['kind']} {i['start']}-{i['end']} while places are unplaced")
    return out


def travel_vs_nn(run):
    from planning.travel import km
    def leg(a, b):
        return max(1, round(km(a, b) * 1.4 / 25 * 60))
    out = []
    for d in run.days:
        stops = [i["place_id"] for i in d["items"] if i["kind"] == "visit"]
        pts = {p: (by_id()[p]["identity"]["lat"], by_id()[p]["identity"]["lng"]) for p in stops}
        def tour(order):
            seq = [run.home, *(pts[p] for p in order), run.home]
            return sum(leg(a, b) for a, b in zip(seq, seq[1:]))
        left, nn, here = set(stops), [], run.home
        while left:
            nxt = min(sorted(left), key=lambda p: leg(here, pts[p]))
            nn.append(nxt)
            left.remove(nxt)
            here = pts[nxt]
        if stops and tour(stops) > tour(nn) * 1.15 + 5:
            out.append(f"day {d['day']}: {tour(stops)}′ on the road, nearest-neighbour does {tour(nn)}′")
    return out


def overload_explained(run):
    exp = run.case["expect"]
    ov = run.view.get("overload")
    if not exp.get("overload"):
        return [] if not ov else ["overload shown for a trip that fits"]
    if not ov:
        return ["no overload shown"]
    out = []
    dirs = ov.get("directions") or []
    if not {x["id"] for x in dirs} <= {"fit", "travel", "cost"} or not dirs:
        out.append(f"directions are {[x.get('id') for x in dirs]}")
    for x in dirs:
        for dropped in x.get("dropped") or []:
            if not any(ch.isdigit() for ch in dropped.get("reason", "")) and x["id"] != "fit":
                out.append(f"{x['id']}: reason without a number: {dropped.get('reason')}")
        if any(p in {d["place_id"] for d in x.get("dropped") or []} for p in (run.ids[n] for n in run.case["must"])):
            out.append(f"{x['id']} drops a must-go place")
    if exp.get("extend") and not ov.get("extend"):
        out.append("short by under an hour a day and no extend line")
    return out


def user_said_kept(run):
    out = []
    for d, fd in zip(run.days, run.case["frame"]["days"]):
        dawn = any(present(i["place_id"], "cloud_hunting") for i in d["items"] if i["kind"] == "visit")
        if d["window"][1] != fd["end"] or (d["window"][0] != fd["start"] and not dawn):
            out.append(f"day {d['day']}: window {d['window']} but the user's day is {fd['start']}-{fd['end']}")
    return out


def reorder_kept(run):
    out = []
    for e in run.case["edits"]:
        if e["type"] != "reorder":
            continue
        want = [run.ids[n] for n in e["order"]]
        got = [i["place_id"] for i in run.days[e["day"]]["items"] if i["kind"] == "visit" and i["place_id"] in want]
        if got != want:
            out.append(f"day {e['day']}: user order {e['order']} became {got}")
    return out


CHECKS = {f.__name__: f for f in (no_long_wait, meals, every_pick_accounted, timed, open_hours, frame_kept, kids,
                                  no_idle_with_leftover, travel_vs_nn, overload_explained, user_said_kept, reorder_kept)}
```

- [ ] **Step 5: Viết `tests/planning/test_planning_realism.py` với `PENDING` rỗng**

```python
"""Spec §11: every realistic case passes the 12 checks. PENDING lists the checks a later task of
docs/superpowers/plans/2026-10-15-planning-realistic-core.md turns green; each task deletes its entries."""

import pytest

from realistic_cases import CASES, SERVING, run_case
from realistic_checks import CHECKS

pytestmark = pytest.mark.skipif(not SERVING.exists(), reason="needs data/serving/places.json")

PENDING: dict[str, str] = {}


@pytest.fixture(scope="module")
def runs():
    return {c["id"]: run_case(c) for c in CASES}


def test_every_case_resolves_to_real_places():
    from realistic_cases import pid
    for c in CASES:
        for name in c["places"] + [c["lodging"]]:
            assert pid(name)


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_realism(check, runs, request):
    if check in PENDING:
        request.applymarker(pytest.mark.xfail(strict=True, reason=PENDING[check]))
    failures = [f"{cid}: {msg}" for cid, run in runs.items() for msg in CHECKS[check](run)]
    assert not failures, "\n".join(failures[:40])
```

- [ ] **Step 6: Chạy trên engine cũ để lấy mốc**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_realism.py -q 2>&1 | tail -40`
Expected: `test_every_case_resolves_to_real_places` PASS (nếu một tên không có trong corpus: thay bằng nơi cùng loại có trong `data/serving/places.json`, không bỏ ca). Phần lớn `test_realism[...]` FAIL. Ghi lại danh sách kiểm FAIL.

- [ ] **Step 7: Đặt `PENDING` đúng bằng các kiểm đang FAIL, gán task sửa**

Dùng bảng này; chỉ giữ dòng nào Step 6 thật sự FAIL (kiểm đã PASS thì không đưa vào):

```python
PENDING: dict[str, str] = {
    "meals": "task 2",
    "timed": "task 2",
    "no_long_wait": "task 3",
    "frame_kept": "task 4",
    "user_said_kept": "task 4",
    "kids": "task 4",
    "every_pick_accounted": "task 5",
    "no_idle_with_leftover": "task 5",
    "travel_vs_nn": "task 5",
    "open_hours": "task 5",
    "overload_explained": "task 6",
    "reorder_kept": "task 8",
}
```

Run lại Step 6. Expected: mọi test PASS hoặc XFAIL; không XPASS.

- [ ] **Step 8: Viết `tests/planning/bench_realistic.py`**

```python
"""p50 / p95 of building each realistic case and of the edits (spec §8), no network. --render DIR writes each case's
plan as text, so a person can read the old and the new engine side by side.

    .venv/bin/python tests/planning/bench_realistic.py --runs 3 --render logs/planning_realistic/before
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from realistic_cases import CASES, decision, engine, render, run_case  # noqa: E402

TARGET_P95 = {"create": 2.0, "reorder": 0.05, "drop_place": 0.05, "move_place": 0.1}


def p95(xs):
    return sorted(xs)[max(0, int(len(xs) * 0.95) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--render", type=Path)
    a = ap.parse_args()
    times: dict[str, list[float]] = {k: [] for k in TARGET_P95}
    eng = engine()
    for _ in range(a.runs):
        for c in CASES:
            run = run_case(c, eng)
            times["create"].append(run.seconds)
            if a.render:
                a.render.mkdir(parents=True, exist_ok=True)
                (a.render / f"{c['id']}.txt").write_text(render(run), encoding="utf-8")
            day = next((d for d in run.days if sum(i["kind"] == "visit" for i in d["items"]) >= 2), None)
            if day is None:
                continue
            sid = eng.create(decision(c))["id"]
            view = eng.load(sid)["view"]
            if not view.get("itinerary"):
                view = eng.act(sid, {"type": "pick_variant", "id": view["variants"][0]["id"]})["view"]
            stops = [i["place_id"] for i in view["itinerary"][day["day"] - 1]["items"] if i["kind"] == "visit"]
            for kind, action in (("reorder", {"type": "reorder", "day": day["day"] - 1, "order": stops[::-1]}),
                                 ("move_place", {"type": "move_place", "place": stops[0],
                                                 "day": (day["day"]) % len(view["itinerary"])}),
                                 ("drop_place", {"type": "drop_place", "place": stops[-1]})):
                t = time.perf_counter()
                try:
                    eng.act(sid, action)
                except Exception as e:      # an act the plan refuses still counts its time
                    print(f"{c['id']} {kind}: {e}")
                times[kind].append(time.perf_counter() - t)
    bad = 0
    for k, xs in times.items():
        if not xs:
            continue
        line = f"{k:<11} n={len(xs):<4} p50={statistics.median(xs):.3f}s p95={p95(xs):.3f}s target<{TARGET_P95[k]}s"
        bad += p95(xs) > TARGET_P95[k]
        print(line + ("  FAIL" if p95(xs) > TARGET_P95[k] else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9: Chạy bench mốc + render bản cũ**

Run: `.venv/bin/python tests/planning/bench_realistic.py --runs 1 --render logs/planning_realistic/before`
Expected: in bảng p50/p95 (create đang vượt 2 s ở các ca nhiều nơi → FAIL, exit 1); `logs/planning_realistic/before/*.txt` có ~22 file. Mở `family_12_in_3.txt` xem có "chờ" dài / kem bơ làm bữa tối như spec §2 mô tả.

- [ ] **Step 10: Commit**

```bash
git add config/planning.yaml src/planning/settings.py tests/planning/realistic_cases.py tests/planning/realistic_checks.py tests/planning/test_planning_realism.py tests/planning/bench_realistic.py
git commit -m "test(planning): realistic Da Lat cases, 12 realism checks and speed bench as the baseline"
```

---

### Task 2: Vai ăn và giờ bình minh

**Files:**
- Create: `src/planning/roles.py`, `tests/planning/test_planning_roles.py`
- Modify: `src/planning/model.py` (`Place.meal_kind`), `src/planning/places.py:build_places`, `src/planning/build.py:prepare` (lọc pin), `src/planning/schedule.py` (`_meal_slots`, vi phạm `meal_window`), `src/planning/validate.py` (nơi ăn nhẹ), `src/planning/timefit.py` (luật `light_snack`), `config/planning.yaml` (`meal_windows`)

**Interfaces:**
- Produces: `roles.meal_kind(rec: dict, cfg: Settings) -> str | None` ∈ {`main`, `breakfast`, `light`, `night_meal`, `None`}; `roles.pin_order(pins: tuple[str, ...], wants: set[str]) -> tuple[str, ...]`; `Place.meal_kind: str | None = None`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_roles.py
from plan_fixtures import CFG, day_ctx, rec

from planning.roles import meal_kind, pin_order
from planning.schedule import simulate


def eat(pid, group, name=None, dishes=(), hours="open"):
    r = rec(pid, 1, 1, usable=("meal", "backup"), group=group, name=name, hours=hours)
    if dishes:
        r["menu"] = {"dishes": [{"name": d} for d in dishes]}
    return r


def test_meal_kind_by_group_and_dishes():
    assert meal_kind(eat("a", "restaurant", "Lẩu gà 668"), CFG) == "main"
    assert meal_kind(eat("b", "restaurant", "Bánh Căn Nhỏ"), CFG) == "breakfast"
    assert meal_kind(eat("c", "restaurant", "Quán X", dishes=["Phở bò"]), CFG) == "breakfast"
    assert meal_kind(eat("d", "dessert", "Kem bơ"), CFG) == "light"
    assert meal_kind(eat("e", "cafe", "Coffee"), CFG) == "light"
    assert meal_kind(eat("f", "market", "Chợ đêm", hours={d: [["17:00", "23:00"]] for d in
                                                         ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}), CFG) == "night_meal"
    assert meal_kind(rec("g", 1, 1, group="attraction"), CFG) is None


def test_dawn_wins_over_sunset_unless_the_user_wants_sunset():
    assert pin_order(("sunset_view", "cloud_hunting"), set()) == ("cloud_hunting", "sunset_view")
    assert pin_order(("sunset_view", "cloud_hunting"), {"sunset_view"}) == ("sunset_view",)


def test_a_dessert_shop_never_takes_the_dinner_slot():
    cx = day_ctx([eat("kem", "dessert", "Kem bơ"), rec("ga", 1, 1)], start=900, end=1260,
                 start_node="h", end_node="h", extra_nodes=["h"])
    r = simulate(["ga", "kem"], cx)
    dinner = [i for i in r.items if i.kind == "meal_free" and i.name == "dinner"]
    kem = next(i for i in r.items if i.kind == "visit" and i.place_id == "kem")
    assert dinner, "dinner stays a free meal block"
    assert not (dinner[0].start <= kem.start < dinner[0].end)
    assert not [v for v in r.violations if v.kind == "meal_window"]
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_roles.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'planning.roles'`.

- [ ] **Step 3: Viết `src/planning/roles.py`**

```python
"""What an eating place is for (a main meal, breakfast, a snack, dinner at a market) and which time of day a place
known for several is visited for. Read from the served record only; nothing is guessed."""

from .places import parse_hours

DAWN_FIRST = ("cloud_hunting",)


def _text(rec: dict) -> str:
    dishes = " ".join(d.get("name") or "" for d in (rec.get("menu") or {}).get("dishes") or [])
    return f"{rec['identity'].get('name') or ''} {dishes}".casefold()


def _open_evening(rec: dict) -> bool:
    hours = (rec.get("operation") or {}).get("hours")
    if not hours:
        return False
    return any(o <= 18 * 60 < c for spans in parse_hours(hours["value"]).values() for o, c in spans)


def meal_kind(rec: dict, cfg) -> str | None:
    """main | breakfast | light | night_meal | None (not an eating place)."""
    group = rec["identity"].get("category_group")
    if group == "market":
        return "night_meal" if _open_evening(rec) else "light"
    if group in cfg.realistic["light_groups"]:
        return "light"
    if "meal" not in (rec.get("usable_as") or []):
        return None
    text = _text(rec)
    return "breakfast" if any(d in text for d in cfg.realistic["breakfast_dishes"]) else "main"


def pin_order(pins: tuple[str, ...], wants: set[str]) -> tuple[str, ...]:
    """The timed features in the order the plan tries them: the ones the user asked for only; else dawn first (a
    cloud-hunting hill is a dawn place even when it also has a sunset view)."""
    if wants & set(pins):
        return tuple(f for f in pins if f in wants)
    return tuple(sorted(pins, key=lambda f: (f not in DAWN_FIRST, pins.index(f))))
```

- [ ] **Step 4: Nối vào model, places, prepare**

`src/planning/model.py`, cuối `Place`:

```python
    meal_kind: str | None = None    # roles.meal_kind: main | breakfast | light | night_meal
```

`src/planning/places.py`, trong `build_places` lúc tạo `Place(...)`, thêm đối số:

```python
                activity_explicit=pid in (decision.get("trip_context", {}).get("activities") or {}),
                meal_kind=meal_kind(rec, cfg)))
```

và import ở đầu file `from .roles import meal_kind` — `roles` import `parse_hours` từ `places`, nên đặt import này **bên trong** `build_places` (`from .roles import meal_kind`) để tránh vòng import.

`src/planning/build.py` trong `prepare`, thay dòng lọc pin:

```python
    placed = [replace(p, pins=tuple(f for f in p.pins if f in wants)) if wants & set(p.pins) else p for p in placed]
```

bằng:

```python
    placed = [replace(p, pins=pin_order(p.pins, wants)) for p in placed]
```

với `from .roles import pin_order` ở đầu file.

- [ ] **Step 5: Ô bữa chỉ cho đúng vai**

`src/planning/schedule.py` `_meal_slots`: đổi dòng chọn nơi ăn và điều kiện `fits`:

```python
    meal_ids = [p for p in order if ctx.places[p].kind == 'meal' and ctx.places[p].meal_kind != 'light']
```

```python
        fits = [n for n in slots if n not in claimed.values() and _role_fits(p, n)
                and any(max(lo, o, ctx.cfg.meal_windows[n][0]) <= min(hi, ctx.cfg.meal_windows[n][1], c - need)
                        for o, c in (cache.intervals[pid] if cache else intervals_for(p, ctx)))]
```

thêm hàm (trên `_meal_slots`):

```python
ROLE_SLOTS = {"breakfast": {"breakfast", "lunch"}, "main": {"lunch", "dinner"}, "night_meal": {"dinner"}, None: {"breakfast", "lunch", "dinner"}}


def _role_fits(place: Place, slot: str) -> bool:
    """A breakfast place takes breakfast or lunch, a hot-pot place lunch or dinner, a night market dinner."""
    return slot in ROLE_SLOTS.get(place.meal_kind, ROLE_SLOTS[None])
```

Trong `_simulate`, vi phạm `meal_window` chỉ cho nơi ăn có vai bữa:

```python
        elif p.kind == 'meal' and p.meal_kind != 'light':
            viol.append(Violation('meal_window', day.index, pid, 0, False, 'no available meal window'))
```

`src/planning/validate.py`, chỗ `if p.kind == 'meal':` (khoảng dòng 91) đổi thành `if p.kind == 'meal' and p.meal_kind != 'light':`.

- [ ] **Step 6: Ăn nhẹ nghiêng về buổi chiều**

`src/planning/timefit.py`: thêm vào `REASON_TEXT` `"light_snack": "Ăn nhẹ buổi chiều"`; trong `windows_for`, ngay trước `elif place.kind == "meal":` thêm:

```python
    elif place.meal_kind == "light":
        reason, periods = "light_snack", ["afternoon"]
```

- [ ] **Step 7: `meal_windows` theo spec**

`config/planning.yaml`:

```yaml
meal_windows: {breakfast: ["06:30", "09:00"], lunch: ["11:00", "13:30"], dinner: ["17:30", "20:00"]}
```

- [ ] **Step 8: Chạy test mới + bộ planning**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_roles.py -q` → PASS.
Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q -x --deselect tests/planning/test_planning_realism.py 2>&1 | tail -30`
Expected: test cũ khẳng định giờ bữa cũ (07:00 / 11:30 / 18:00) FAIL ở `test_planning_schedule.py`, `test_planning_meal_timing.py`, golden. Với mỗi FAIL: nếu nó khẳng định giờ bữa / pin hoàng hôn cũ → sửa số mong đợi theo `meal_windows` mới và `pin_order` (giải thích trong commit); nếu nó hỏng vì lý do khác → sửa code. Golden: `tests/planning/golden` tái sinh bằng lệnh tái sinh có trong `test_planning_golden.py` (đọc docstring), rồi `git diff tests/planning/golden` xem từng thay đổi chỉ là giờ bữa / thứ tự pin.

- [ ] **Step 9: Gỡ `meals`, `timed` khỏi `PENDING`, chạy bộ thực tế**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_realism.py -q`
Expected: `meals`, `timed` PASS; còn lại XFAIL. Nếu `meals` còn lỗi ở ca có `free`/`zero_food` do bữa nằm ngoài `meal_free`: đó là phần Task 3 (khoảng trống) — để `meals` lại `PENDING` với lý do `"task 3"` và ghi chú.

- [ ] **Step 10: Commit**

```bash
git add src/planning/roles.py src/planning/model.py src/planning/places.py src/planning/build.py src/planning/schedule.py src/planning/validate.py src/planning/timefit.py config/planning.yaml tests/planning
git commit -m "feat(planning): eating roles keep snacks out of meal slots; dawn pins win for cloud hunting"
```

---

### Task 3: Dòng thời gian đọc được: chặng gộp đệm, hết "chờ" dài

**Files:**
- Modify: `src/planning/model.py` (`Item.kind` thêm `free`), `src/planning/schedule.py` (đệm vào chặng; `humanize`), `src/planning/schedule.py:DayCtx` (`home`), `src/planning/build.py:prepare` (truyền `home`), `src/planning/validate.py` (chặng có đệm), `src/planning/objectives.py`, `src/planning/recommendations.py` (đọc `free`), `src/planning/build.py:render_text`
- Test: `tests/planning/test_planning_humanize.py`

**Interfaces:**
- Consumes: `Settings.realistic` (Task 1).
- Produces: `DayCtx.home: str | None = None`; `schedule.humanize(items: list[Item], ctx: DayCtx) -> list[Item]`; item `travel` có `note="+N"` khi gồm N phút đệm; item `free` (`note` = id nơi trước, hoặc `None`); item `rest` với `note="home"` khi về chỗ ở nghỉ.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_humanize.py
from dataclasses import replace

from plan_fixtures import all_days, day_ctx, rec

from planning.schedule import simulate


def kinds(r):
    return [i.kind for i in r.items]


def test_no_buffer_rows_the_buffer_rides_on_the_leg():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    assert "buffer" not in kinds(r)
    leg = next(i for i in r.items if i.kind == "travel" and i.from_id == "a")
    assert leg.end - leg.start == 10 + cx.cfg.buffer_min["normal"] and leg.note == f"+{cx.cfg.buffer_min['normal']}"
    assert r.travel_min == 30                       # the matrix minutes only, never the buffer


def test_a_long_wait_near_the_lodging_is_a_rest_there():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    cx = day_ctx([rec("a", 1, 1), late], start_node="h", end_node="h", extra_nodes=["h"])
    cx = replace(cx, home="h")
    r = simulate(["a", "b"], cx)
    assert not [i for i in r.items if i.kind == "wait" and i.end - i.start > cx.cfg.realistic["wait_max"]]
    rest = [i for i in r.items if i.kind == "rest" and i.note == "home"]
    assert rest and rest[0].end - rest[0].start >= 60


def test_a_long_wait_far_from_the_lodging_is_free_time_before_leaving():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    from plan_fixtures import flat_travel
    cx = day_ctx([rec("a", 1, 1), late], start_node="h", end_node="h", extra_nodes=["h"],
                 travel=flat_travel(["a", "b", "h"], 10, a_h=40, b_h=40))
    cx = replace(cx, home="h")
    r = simulate(["a", "b"], cx)
    free = [i for i in r.items if i.kind == "free"]
    assert free and free[0].note == "a"
    arrive = next(i for i in r.items if i.kind == "travel" and i.to_id == "b")
    assert arrive.start >= free[0].end
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_humanize.py -q`
Expected: FAIL (`buffer` còn trong items; `DayCtx` không có `home`).

- [ ] **Step 3: `DayCtx.home` và truyền từ `prepare`**

`schedule.py` `DayCtx`, field cuối: `home: str | None = None       # the lodging node; None = not known`.
`build.py` `prepare`, trong list comprehension tạo `DayCtx(...)` thêm `home=home`. `with_home` cập nhật: `ctxs = [replace(cx, day=d, home=home_id) for cx, d in zip(trip.ctxs, days)]`.

- [ ] **Step 4: Đệm đi cùng chặng**

Trong `_simulate`, bỏ `items.append(Item("buffer", t, t + buffer))` và `t += buffer`; thay bằng giữ đệm chờ chặng kế:

```python
            pending_buffer = buffer
```

Khai báo `pending_buffer = 0` cạnh `travel_min = wait_min = 0`, và sửa `move`:

```python
    def move(frm: str | None, to: str | None):
        nonlocal t, active, travel_min, pending_buffer
        extra, pending_buffer = pending_buffer, 0
        if frm is None or to is None or frm == to:
            t += extra
            return
        m, mode = leg(frm, to)
        items.append(Item("travel", t, t + m + extra, from_id=frm, to_id=to, mode=mode,
                          note=f"+{extra}" if extra else None))
        t, active, travel_min = t + m + extra, active + m, travel_min + m
```

`validate.py` chỗ kiểm `travel` không đổi (chặng dài hơn ma trận là hợp lệ); `long_leg` phải so phút ma trận, không phải phút có đệm:

```python
                if max_leg_min and need > max_leg_min:
                    out.append(Violation("long_leg", d.index, it.to_id, need - max_leg_min, False,
                                         f"longer than {max_leg_min} min"))
```

- [ ] **Step 5: `humanize` — khoảng chờ dài thành tự do hoặc về nghỉ**

Thêm vào `schedule.py`:

```python
def humanize(items: list[Item], ctx: DayCtx) -> list[Item]:
    """A wait longer than wait_max is not a plan. Before a leg that ends in one: rest at the lodging when the
    free time is long and the lodging is near; else stay free around the previous stop and leave later."""
    r = ctx.cfg.realistic
    out: list[Item] = []
    k = 0
    while k < len(items):
        it = items[k]
        nxt = items[k + 1] if k + 1 < len(items) else None
        if it.kind == "travel" and nxt is not None and nxt.kind == "wait" and nxt.end - nxt.start > r["wait_max"]:
            leg_min = it.end - it.start
            slack = nxt.end - it.start - leg_min           # minutes with nothing to do
            home = ctx.home
            to_home = ctx.travel.leg(it.from_id, home)[0] if home and it.from_id else None
            from_home = ctx.travel.leg(home, it.to_id)[0] if home else None
            if (home and to_home is not None and slack >= r["rest_home_min"] and to_home <= r["rest_home_road_max"]
                    and from_home <= r["rest_home_road_max"] and it.from_id != home):
                t = it.start
                out.append(Item("travel", t, t + to_home, from_id=it.from_id, to_id=home, mode=it.mode))
                back = nxt.end - from_home
                out.append(Item("rest", t + to_home, back, note="home"))
                out.append(Item("travel", back, nxt.end, from_id=home, to_id=it.to_id, mode=it.mode))
            else:
                leave = nxt.end - leg_min
                out.append(Item("free", it.start, leave, note=it.from_id))
                out.append(Item("travel", leave, nxt.end, from_id=it.from_id, to_id=it.to_id, mode=it.mode,
                                note=it.note))
            k += 2
            continue
        out.append(it)
        k += 1
    return out
```

Gọi ở cuối `_simulate`, trước khi dựng `DayResult`:

```python
    items = humanize(items, ctx)
    travel_min = sum(ctx.travel.leg(i.from_id, i.to_id)[0] for i in items if i.kind == "travel")
    wait_min = sum(i.end - i.start for i in items if i.kind == "wait")
```

- [ ] **Step 6: Người đọc lịch thấy đúng tên**

`build.py` `render_text`: nhánh `else` đổi thành

```python
            else:
                label = {"rest": "về chỗ ở nghỉ" if i.get("note") == "home" else "nghỉ", "free": "tự do quanh đây",
                         "busy": i.get("name") or "việc cố định"}.get(i["kind"])
                out.append(span + (WAIT_TEXT.get(i.get("note"), "chờ") if i["kind"] == "wait" else label or i["kind"]))
```

`recommendations.py` dòng 22: thêm `"free"` vào tập kind được coi là khoảng trống:

```python
        if item.kind in {"wait", "meal_free", "free"} or item.end <= a or item.start >= b:
```

`objectives.py`: không đổi (đếm `visit` / `meal_free`).

- [ ] **Step 7: Chạy test mới + bộ planning**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_humanize.py -q` → PASS.
Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q --deselect tests/planning/test_planning_realism.py 2>&1 | tail -40`
Expected: các test khẳng định `("buffer", a, b)` trong `test_planning_schedule.py`, `test_planning_route.py`, `test_planning_repair.py`, golden FAIL. Viết lại kỳ vọng theo hành vi mới: không item `buffer`; chặng có `note="+N"` và dài thêm N; khoảng chờ > 20′ thành `free` / `rest(home)`. Không xóa test, không nới assert ngoài các điểm đó. Tái sinh golden và xem `git diff`.

- [ ] **Step 8: Gỡ `no_long_wait` khỏi `PENDING`, chạy bộ thực tế**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_realism.py -q` → `no_long_wait` PASS.

- [ ] **Step 9: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): buffers ride on legs; long waits become free time or a rest at the lodging"
```

---

### Task 4: Khung ngày của user: khoảng bận, nơi tới / rời, gửi đồ

**Files:**
- Modify: `src/planning/model.py` (`Day.busy`, `Day.intensity`), `src/planning/frame.py:trip_days`, `src/planning/build.py:prepare` (`@entry` / `@exit`, `meal_skip`, `rest`), `src/planning/schedule.py` (`DayCtx.meal_skip`, `DayCtx.rest`, khoảng bận, gửi đồ), `src/planning/validate.py` (khoảng bận, mốc rời physical, `drive_day_min`)
- Test: `tests/planning/test_planning_frame.py` (thêm)

**Interfaces:**
- Consumes: `context.frame` (CompiledFrame JSON: `days[i].{date,start,end,busy[{start,end,kinds,labels,where}],intensity}`, `arrive`, `leave`, `meals`, `rest`, `drive_day_min`, `visit`).
- Produces: `Day.busy: tuple[tuple[int, int, str, str, str | None], ...] = ()` (start, end, kind, label, where); `Day.intensity: str = "normal"`; `DayCtx.meal_skip: frozenset = frozenset()`; `DayCtx.rest: tuple[int, int] | None = None`; item `busy` (`name` = nhãn, `note` = kind); nút `"@entry"`, `"@exit"`; `Violation.kind` thêm `busy`, `departure` (physical), `drive_day`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/planning/test_planning_frame.py`:

```python
from dataclasses import replace

from plan_fixtures import CFG, all_days, day_ctx, rec

from planning.frame import trip_days
from planning.model import Day
from planning.schedule import simulate


def compiled(**kw):
    day = {"date": "2026-11-07", "start": "08:00", "end": "21:00", "busy": [], "intensity": "normal", **kw}
    return {"frame": {"days": [day], "arrive": None, "leave": None, "meals": {"skip": [], "breakfast_at_lodging": False,
                                                                            "snacks": False, "shift_min": 0}}}


def test_trip_days_reads_busy_blocks_and_intensity():
    ctx = compiled(busy=[{"start": "15:00", "end": "16:00", "kinds": ["work"], "labels": ["Họp"], "where": "lodging"}],
                   intensity="light")
    d = trip_days(ctx, CFG, "h")[0]
    assert d.busy == ((900, 960, "work", "Họp", "lodging"),) and d.intensity == "light"


def test_trip_days_without_frame_keeps_the_config_window():
    d = trip_days({"days": 1, "start_date": None}, CFG, None)[0]
    assert (d.start, d.end, d.busy, d.intensity) == (CFG.day_start, CFG.leave_at, (), "normal")


def test_a_meeting_at_the_lodging_sends_the_day_home_and_back():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"], start=840)
    cx = replace(cx, home="h", day=Day(0, None, "mon", 840, 1260, "h", "h", busy=((900, 960, "work", "Họp", "lodging"),)))
    r = simulate(["a", "b"], cx)
    busy = next(i for i in r.items if i.kind == "busy")
    assert (busy.start, busy.end, busy.name) == (900, 960, "Họp")
    assert all(not (i.start < 960 and 900 < i.end) for i in r.items if i.kind in {"visit", "travel"})
    before = [i for i in r.items if i.kind == "travel" and i.end <= 900]
    assert before and before[-1].to_id == "h"


def test_a_skipped_breakfast_is_not_planned():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    cx = replace(cx, meal_skip=frozenset({"breakfast"}))
    r = simulate(["a"], cx)
    assert not [i for i in r.items if i.kind == "meal_free" and i.name == "breakfast"]
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_frame.py -q`
Expected: FAIL (`Day` không có `busy`).

- [ ] **Step 3: `Day` và `trip_days`**

`model.py` `Day`, thêm cuối:

```python
    busy: tuple = ()                # (start, end, kind, label, where): what the user does at fixed times
    intensity: str = "normal"       # light | normal | full | free (Trip frame)
```

`frame.py` nhánh `if frame := ctx.get("frame"):` thay thân vòng lặp:

```python
        for i, day in enumerate(frame["days"]):
            d = date.fromisoformat(day["date"]) if isinstance(day["date"], str) else day["date"]
            start = to_min(day["start"])
            free = day.get("intensity") == "free"
            busy = tuple((to_min(b["start"]), to_min(b["end"]), b["kinds"][0], b["labels"][0], b.get("where"))
                         for b in day.get("busy") or ())
            first, last = i == 0, i == len(frame["days"]) - 1
            out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()], start=start,
                           end=start if free else to_min(day["end"]),
                           start_node=entry if first and entry else home, end_node=exit_ if last and exit_ else home,
                           busy=busy, intensity=day.get("intensity") or "normal"))
        return out
```

và đổi chữ ký: `def trip_days(ctx: dict, cfg: Settings, home: str | None, entry: str | None = None, exit_: str | None = None) -> list[Day]:`.

- [ ] **Step 4: `prepare`: nơi tới / rời, bữa bỏ, nhịp nghỉ**

`build.py` `prepare`, sau khi tính `points[HOME]`:

```python
    frame = ctx.get("frame") or {}
    for node, key, moment in (("@entry", "entry_point", "arrive"), ("@exit", "exit_point", "leave")):
        if frame.get(moment) and ctx.get(key):
            points[node], _ = pl.resolve_point(ctx[key], by_id, geocode_fn)
    entry = "@entry" if points.get("@entry") else None
    exit_ = "@exit" if points.get("@exit") else None
```

đổi `days = trip_days(ctx, cfg, home)` thành `days = trip_days(ctx, cfg, home, entry, exit_)`; với `exit_` thì ngày cuối kết thúc ở mốc rời trừ đệm sân bay (đường ra đã là một chặng):

```python
    if exit_ and frame["leave"]["at"][:10] == (days[-1].date.isoformat() if days[-1].date else None):
        days[-1] = replace(days[-1], end=to_min(frame["leave"]["at"][11:]) - cfg.realistic["leave_buffer_min"])
    if entry and frame["arrive"]["at"][:10] == (days[0].date.isoformat() if days[0].date else None):
        days[0] = replace(days[0], start=to_min(frame["arrive"]["at"][11:]) + cfg.realistic["arrive_buffer_min"])
```

(import `to_min` từ `.settings`). Trong comprehension `DayCtx(...)` thêm:

```python
                   meal_skip=frozenset(_skips(frame)), rest=_rest(frame),
```

với hai hàm cấp module:

```python
def _skips(frame: dict) -> set[str]:
    meals = frame.get("meals") or {}
    return set(meals.get("skip") or ()) | ({"breakfast"} if meals.get("breakfast_at_lodging") else set())


def _rest(frame: dict) -> tuple[int, int] | None:
    rest = frame.get("rest")
    return (rest["every_min"], rest["rest_min"]) if rest else None
```

`with_home`: truyền lại entry / exit: `days = trip_days(ctx, trip.cfg, home_id, *(n if n in trip.points and trip.points[n] else None for n in ("@entry", "@exit")))` và giữ `end`/`start` đã chỉnh của ngày đầu / cuối: `days = [replace(d, start=old.start, end=old.end) for d, old in zip(days, trip.days)]`.

- [ ] **Step 5: `DayCtx` và đồng hồ đọc khung bận, bữa bỏ, nhịp nghỉ**

`schedule.py` `DayCtx` thêm:

```python
    meal_skip: frozenset = frozenset()       # meals the user skips (or eats at the lodging)
    rest: tuple[int, int] | None = None      # (every_min, rest_min) the user said; None = the pace's
```

`_meal_slots`: `names = [n for n in list(ctx.cfg.meal_windows)[: ctx.cfg.meals_per_day] if n not in ctx.meal_skip]`.
`_breaks`: dùng nhịp của user khi có:

```python
    every, rest = ctx.rest or (cfg.max_consecutive_min[ctx.pace], cfg.rest_min[ctx.pace])
    if active >= every:
        items.append(Item("rest", t, t + rest))
        t, active = t + rest, 0
```

Khoảng bận: thêm hàm và gọi đầu mỗi vòng `for idx, pid in enumerate(order)` (trước `move(here, pid)`) và một lần sau vòng lặp (trước chặng về):

```python
def _busy_due(t: int, here: str | None, need: int, ctx: DayCtx, items: list, done: set, leg) -> tuple[int, str | None]:
    """Go to each fixed-time block that would start before the next stop is done; travel home for one at the
    lodging and resume from there. A block with no known place is kept at the lodging (spec §4)."""
    for k, (a, b, kind, label, where) in enumerate(ctx.day.busy):
        if k in done or t + need <= a:
            continue
        done.add(k)
        at = ctx.home if where in (None, "lodging") else None
        if at and here and here != at:
            m, mode = leg(here, at)
            go = max(t, a - m)
            items.append(Item("travel", go, go + m, from_id=here, to_id=at, mode=mode))
            here = at
        items.append(Item("busy", a, b, name=label, note=kind))
        t = max(t, b)
    return t, here
```

Trong `_simulate`: khai báo `done_busy: set = set()`; trong vòng lặp, trước `move(here, pid)`:

```python
        need = (leg(here, pid)[0] if here else 0) + visit_minutes(p, cfg, ctx.pace, ctx.prefs)
        t, here = _busy_due(t, here, need, ctx, items, done_busy, leg)
```

sau vòng lặp, trước `move(here, day.end_node)`: `t, here = _busy_due(t, here, 10**6, ctx, items, done_busy, leg)` chỉ với khối có `a < day.end` (điều kiện `t + need <= a` đã loại khối sau giờ về khi `need` lớn — giữ như vậy để khối bận cuối ngày vẫn hiện).

Gửi đồ ngày đầu: ngay đầu `_simulate`, sau khi khởi tạo `t, here`:

```python
    if day.index == 0 and day.start_node == "@entry" and ctx.home and order:
        m, mode = leg("@entry", ctx.home)
        stop = cfg.realistic["drop_bags_min"]
        items.append(Item("travel", t, t + m, from_id="@entry", to_id=ctx.home, mode=mode))
        items.append(Item("rest", t + m, t + m + stop, note="drop_bags"))
        t, here = t + m + stop, ctx.home
```

- [ ] **Step 5b: Thời lượng user đã nói thắng ước tính**

Test (thêm vào `test_planning_frame.py`):

```python
def test_a_duration_the_user_said_wins_over_the_estimate():
    from plan_fixtures import decision, prepared, spot, CENTRE
    recs = [spot("c1", CENTRE, 0, group="cafe", usable=("experience", "meal", "backup"))]
    d = decision(["c1"], days=1)
    d["trip_context"]["context"]["frame"] = {"days": [{"date": "2026-12-12", "start": "08:00", "end": "21:00",
                                                       "busy": [], "intensity": "normal"}],
                                             "arrive": None, "leave": None, "visit": {"cafe": 120}, "meals": {}}
    p = prepared(d, recs).by_place["c1"]
    assert (p.visit["short"], p.visit["typical"], p.visit["long"], p.visit["source"]) == (120, 120, 120, "user")
```

`build.py` `prepare`, ngay sau `placed, unplaced = pl.build_places(...)`:

```python
    said = (ctx.get("frame") or {}).get("visit") or {}
    if said:
        placed = [replace(p, visit={**p.visit, "short": m, "typical": m, "long": m, "source": "user"})
                  if (m := said.get(p.rec["identity"].get("category_group"))) else p for p in placed]
```

- [ ] **Step 6: Validator**

`validate.py`, trong vòng mỗi ngày (sau kiểm `overlap`):

```python
        for a, b, kind, label, _ in d.busy:
            for it in items:
                if it.kind in {"visit", "travel"} and it.start < b and a < it.end:
                    out.append(Violation("busy", d.index, it.place_id or it.to_id, min(b, it.end) - max(a, it.start),
                                         False, f"overlaps {label}"))
        if d.end_node == "@exit" and items and items[-1].end > d.end:
            out.append(Violation("departure", d.index, None, items[-1].end - d.end, True, "misses the departure"))
        cap = (cx.cfg.realistic or {}).get("drive_day_min")
        drive = sum(cx.travel.leg(i.from_id, i.to_id)[0] for i in items if i.kind == "travel")
        if cap and drive > cap:
            out.append(Violation("drive_day", d.index, None, drive - cap, False, f"over {cap} min of driving"))
```

`drive_day_min` lấy từ frame: trong `prepare` đặt `cfg = replace(cfg, realistic={**cfg.realistic, "drive_day_min": frame.get("drive_day_min")})` trước khi tạo `DayCtx`.

- [ ] **Step 7: Chạy test frame + bộ planning**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_frame.py -q` → PASS.
Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q --deselect tests/planning/test_planning_realism.py 2>&1 | tail -30` → test cũ PASS (field mới có mặc định). Lỗi nào do `trip_days` đổi chữ ký: sửa chỗ gọi.

- [ ] **Step 8: Gỡ `frame_kept`, `user_said_kept`, `kids` khỏi `PENDING`; chạy bộ thực tế**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_realism.py -q`
Expected: ba kiểm PASS. `kids` cần ăn tối sớm: `shift_min` (-30 ở ca `family_kid_nap`) — nếu còn FAIL vì bữa tối > 19:00, áp `shift_min` trong `_meal_slots` / `_breaks`: cửa sổ bữa dịch `ctx.meal_shift` phút (thêm `DayCtx.meal_shift: int = 0`, gán từ `frame["meals"]["shift_min"]`) và lặp lại kiểm.

- [ ] **Step 9: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): plan inside the user's day frame: busy blocks, arrival and departure points, skipped meals"
```

---

### Task 5: Chia ngày bằng chèn rẻ nhất vào sức chứa phút

**Files:**
- Create: `src/planning/layout.py`, `tests/planning/test_planning_layout.py`
- Modify: `src/planning/build.py:schedule_trip` (dùng `layout.assign`), `src/planning/build.py:Schedule` (`leftover`)

**Interfaces:**
- Consumes: `Day.busy`, `Day.intensity`, `DayCtx.meal_skip` (Task 4); `Place.meal_kind` (Task 2); `schedule.meal_minutes`, `traits.visit_minutes`, `places.windows_on`.
- Produces: `layout.capacity(cx: DayCtx) -> int`; `layout.assign(trip: Trip, ctxs: list[DayCtx], ids: list[str]) -> tuple[list[list[str]], list[str]]` (ids theo ngày, nơi không vừa); `Schedule.leftover: tuple[str, ...] = ()`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_layout.py
from dataclasses import replace

from plan_fixtures import CENTRE, SOUTH, prepared, decision, spot, rec

from planning.build import schedule_trip
from planning.layout import assign, capacity


def trip_of(recs, **kw):
    d = decision([r["id"] for r in recs], base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 **kw)
    return prepared(d, recs)


def test_near_places_share_a_day_and_far_ones_get_their_own():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("s1", SOUTH, 0), spot("s2", SOUTH, 1)]
    trip = trip_of(recs, days=2)
    per_day, left = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert not left
    assert {frozenset(d) for d in per_day} == {frozenset({"c1", "c2"}), frozenset({"s1", "s2"})}


def test_more_than_fits_leaves_the_rest_over_and_no_day_is_empty():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 180, 240)) for i in range(12)]
    trip = trip_of(recs, days=2)
    per_day, left = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert left and all(per_day)


def test_a_free_day_takes_no_place():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1)]
    trip = trip_of(recs, days=2)
    ctxs = [trip.ctxs[0], replace(trip.ctxs[1], day=replace(trip.ctxs[1].day, intensity="free"))]
    per_day, _ = assign(trip, ctxs, sorted(trip.by_place))
    assert per_day[1] == [] and capacity(ctxs[1]) == 0


def test_a_place_closed_that_weekday_goes_to_another_day():
    closed_sat = {d: [["08:00", "21:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sun")}
    closed_sat["sat"] = []
    recs = [spot("c1", CENTRE, 0, hours=closed_sat), spot("c2", CENTRE, 1)]
    trip = trip_of(recs, days=2)                     # 2026-12-12 is a Saturday
    per_day, _ = assign(trip, trip.ctxs, sorted(trip.by_place))
    assert "c1" in per_day[1]


def test_schedule_trip_reports_leftover_instead_of_dropping_silently():
    recs = [spot(f"c{i}", CENTRE, i, visit=(120, 180, 240)) for i in range(12)]
    s = schedule_trip(trip_of(recs, days=2))
    placed = {pid for r in s.results for pid in r.order}
    assert s.leftover and placed | set(s.leftover) == {f"c{i}" for i in range(12)}
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_layout.py -q`
Expected: FAIL `No module named 'planning.layout'`.

- [ ] **Step 3: Viết `src/planning/layout.py`**

```python
"""Places -> days (spec §6): each day holds the minutes left after its fixed blocks, meals and rests; hard places go
first (a timed feature, far away, few open days), every place takes the day and position that add the fewest
minutes, then single moves between days improve it. Whatever cannot fit is returned, never dropped silently."""

from .places import windows_on
from .schedule import DayCtx, meal_minutes
from .traits import visit_minutes

MEAL_ROLES = {"main", "breakfast", "night_meal"}
ROLE_SLOTS = {"breakfast": ("breakfast", "lunch"), "main": ("lunch", "dinner"), "night_meal": ("dinner",)}


def needed_meals(cx: DayCtx) -> list[str]:
    d, cfg = cx.day, cx.cfg
    return [n for n in list(cfg.meal_windows)[: cfg.meals_per_day] if n not in cx.meal_skip
            and cfg.meal_windows[n][1] >= d.start and max(d.start, cfg.meal_windows[n][0]) + meal_minutes(n, cx) <= d.end]


def capacity(cx: DayCtx) -> int:
    """Minutes a day has for visits and the legs between them."""
    d, cfg = cx.day, cx.cfg
    if d.intensity == "free" or d.end <= d.start:
        return 0
    span = d.end - d.start - sum(b - a for a, b, *_ in d.busy) - sum(meal_minutes(n, cx) for n in needed_meals(cx))
    every, rest = cx.rest or (cfg.max_consecutive_min[cx.pace], cfg.rest_min[cx.pace])
    span -= (span // max(1, every)) * rest
    factor = cfg.realistic["light_factor"] if d.intensity == "light" else 1.0
    return max(0, int(span * factor))


def _load(p, cx: DayCtx) -> int:
    if p.kind == "meal" and p.meal_kind in MEAL_ROLES:
        return 0                                   # a meal place takes a meal slot, already reserved
    return visit_minutes(p, cx.cfg, cx.pace, cx.prefs) + cx.cfg.intra_leg_min


def _open(p, cx: DayCtx) -> bool:
    w = windows_on(p.hours, cx.day.weekday)
    return w is None or bool(w)


def _leg(travel, a, b) -> int:
    return travel.leg(a, b)[0] if a and b else 0


def _insert_cost(travel, seq: list, pid: str) -> tuple[int, int]:
    """(added minutes, position) of the cheapest place for pid in seq = [start, *stops, end]."""
    best = None
    for k in range(1, len(seq)):
        a, b = seq[k - 1], seq[k]
        add = _leg(travel, a, pid) + _leg(travel, pid, b) - _leg(travel, a, b)
        if best is None or add < best[0]:
            best = (add, k)
    return best


def assign(trip, ctxs: list[DayCtx], ids: list[str]) -> tuple[list[list[str]], list[str]]:
    by_place, travel = trip.by_place, trip.travel
    home = ctxs[0].home if ctxs else None
    days = [[cx.day.start_node, cx.day.end_node] for cx in ctxs]
    free = [capacity(cx) for cx in ctxs]
    slots = [list(needed_meals(cx)) for cx in ctxs]

    def hardness(pid):
        p = by_place[pid]
        open_days = sum(_open(p, cx) for cx in ctxs)
        return (not p.pins, open_days, -_leg(travel, home, pid), pid)

    left: list[str] = []
    for pid in sorted(ids, key=hardness):
        p = by_place[pid]
        best = None
        for k, cx in enumerate(ctxs):
            if not _open(p, cx) or free[k] <= 0 and _load(p, cx) > 0:
                continue
            load = _load(p, cx)
            if p.kind == "meal" and p.meal_kind in MEAL_ROLES:
                if not any(s in slots[k] for s in ROLE_SLOTS[p.meal_kind]):
                    continue
            add, pos = _insert_cost(travel, [n for n in days[k] if n is not None] or [None, None], pid)
            if load + add > free[k]:
                continue
            if best is None or add < best[0]:
                best = (add, k, pos, load)
        if best is None:
            left.append(pid)
            continue
        add, k, pos, load = best
        seq = days[k]
        real = [n for n in seq if n is not None]
        anchor = real[pos - 1] if real else None
        at = seq.index(anchor) + 1 if anchor in seq else 1
        seq.insert(at, pid)
        free[k] -= load + add
        if p.kind == "meal" and p.meal_kind in MEAL_ROLES:
            slots[k].remove(next(s for s in ROLE_SLOTS[p.meal_kind] if s in slots[k]))
    per_day = [[n for n in seq[1:-1] if n is not None] for seq in days]
    return _improve(trip, ctxs, per_day, free), left


def _improve(trip, ctxs, per_day, free) -> list[list[str]]:
    """Move one place to another day while that shortens the trip and fits; ties keep the first layout."""
    travel = trip.travel

    def tour(k, ids):
        seq = [n for n in (ctxs[k].day.start_node, *ids, ctxs[k].day.end_node) if n is not None]
        return sum(_leg(travel, a, b) for a, b in zip(seq, seq[1:]))

    for _ in range(trip.cfg.improve_passes):
        moved = False
        for a in range(len(per_day)):
            for pid in list(per_day[a]):
                p = trip.by_place[pid]
                if p.kind == "meal" and p.meal_kind in MEAL_ROLES:
                    continue
                base = tour(a, per_day[a])
                for b in range(len(per_day)):
                    if b == a or not _open(p, ctxs[b]):
                        continue
                    load = _load(p, ctxs[b])
                    _, pos = _insert_cost(travel, [n for n in (ctxs[b].day.start_node, *per_day[b],
                                                               ctxs[b].day.end_node) if n is not None] or [None, None], pid)
                    trial_b = per_day[b][:max(0, pos - 1)] + [pid] + per_day[b][max(0, pos - 1):]
                    trial_a = [x for x in per_day[a] if x != pid]
                    gain = base + tour(b, per_day[b]) - tour(a, trial_a) - tour(b, trial_b)
                    if gain > 0 and load + max(0, tour(b, trial_b) - tour(b, per_day[b])) <= free[b]:
                        free[a] += load
                        free[b] -= load + max(0, tour(b, trial_b) - tour(b, per_day[b]))
                        per_day[a], per_day[b] = trial_a, trial_b
                        moved = True
                        break
        if not moved:
            break
    return per_day
```

- [ ] **Step 4: `schedule_trip` dùng `assign`, báo `leftover`**

`build.py` `Schedule`, thêm field cuối: `leftover: tuple = ()`.

Trong `schedule_trip`, thay hàm lồng `split` bằng:

```python
    def split(day_ids, day_ctxs):
        per_day, left = assign(trip, day_ctxs, day_ids)
        leftover.extend(left)
        return per_day, None
```

khai báo `leftover: list = []` trước nó; import `from .layout import assign`. Sau vòng `results` (đã có `order_day` từng ngày): ngày nào validate ra `hours` / `day_window` cho một nơi thì chuyển nơi đó sang `leftover` và dựng lại ngày đó (tối đa số nơi của ngày):

```python
    for k, (day_ids, cx) in enumerate(zip(per_day, ctxs)):
        r = results[k]
        while True:
            bad = [v.place_id for v in validate([cx], [r], hard, set(), budget, max_leg)
                   if v.kind in {"hours", "day_window"} and v.place_id in day_ids and v.place_id not in anchors]
            late = bad or ([day_ids[-1]] if any(v.kind == "day_window" for v in validate([cx], [r], hard, set(), budget,
                                                                                         max_leg)) and day_ids else [])
            late = [p for p in late if p not in anchors]
            if not late:
                break
            day_ids = [p for p in day_ids if p != late[0]]
            leftover.append(late[0])
            r = order_day(day_ids, cx)
        per_day[k], results[k] = day_ids, r
```

(đặt khối này sau khi `anchors` được tính; dời dòng tính `anchors` lên trước vòng này). Trả về `Schedule(per_day, results, ctxs, violations, warnings, tuple(sorted(set(leftover))))`.

Xóa import `cluster_places`, `split_to_fit`, `assign_days`, `day_load`, `isolate_constrained`, `split_competing` khỏi `build.py` nếu không còn dùng.

Ngày cuối đi xe máy / xe buýt sau trả phòng (spec §4 "mang theo hành lý"): trong `assign`, với ngày cuối có `end_node == "@exit"` và `trip.decision["trip_context"]["context"].get("mobility") in {"motorbike", "walk"}`, bỏ qua nơi có `_leg(travel, pid, "@exit") > cfg.realistic["luggage_radius_min"]` và `_leg(travel, home, pid) > cfg.realistic["luggage_radius_min"]`. Thêm test:

```python
def test_last_day_by_motorbike_keeps_places_near_the_way_out():
    far = (11.80, 108.45)                         # ~15 km south: ~50 rough minutes
    recs = [spot("c1", CENTRE, 0), rec("f1", *far)]
    d = decision(["c1", "f1"], days=1, mobility="motorbike",
                 base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 exit={"text": "bến xe", "lat": CENTRE[0], "lng": CENTRE[1]})
    d["trip_context"]["context"]["frame"] = {
        "days": [{"date": "2026-12-12", "start": "08:00", "end": "21:00", "busy": [], "intensity": "normal"}],
        "arrive": None, "leave": {"at": "2026-12-12T20:00", "how": "bus"}, "meals": {}}
    trip = prepared(d, recs)
    per_day, left = assign(trip, trip.ctxs, ["c1", "f1"])
    assert per_day[0] == ["c1"] and left == ["f1"]
```

- [ ] **Step 4b: Ngày bình minh có nghỉ trưa bù**

Test (thêm vào `test_planning_layout.py`):

```python
def test_a_dawn_day_gets_a_midday_rest_at_the_lodging():
    recs = [spot("c1", CENTRE, 0, features={"cloud_hunting": "present"}), spot("c2", CENTRE, 1)]
    s = schedule_trip(trip_of(recs, days=2))
    day = next(k for k, r in enumerate(s.results) if "c1" in r.order)
    assert s.ctxs[day].day.start < 8 * 60
    assert any(b[2] == "rest" and b[0] >= 11 * 60 for b in s.ctxs[day].day.busy)
```

Trong `schedule_trip`, ở vòng `pull_early` (khi `pid` khác `None`), thêm khối nghỉ trưa ở chỗ ở nếu ngày đó chưa có khối `rest` / `nap`, và giảm sức chứa buổi chiều bằng cách để vòng "chuyển nơi sang leftover" của Step 4 xử lý phần tràn:

```python
        if pid and not any(b[2] in {"rest", "nap"} for b in ctxs[k].day.busy):
            nap = (12 * 60, 14 * 60 + 30, "rest", "Nghỉ trưa bù dậy sớm", "lodging")
            ctxs[k] = replace(ctxs[k], day=replace(ctxs[k].day, busy=ctxs[k].day.busy + (nap,)))
```

- [ ] **Step 5: Chạy test layout + bộ planning**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_layout.py -q` → PASS.
Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q --deselect tests/planning/test_planning_realism.py 2>&1 | tail -40`
Expected: `test_planning_cluster.py`, `test_planning_days.py` vẫn PASS (module chưa xóa). Test của `schedule_trip` / composer khẳng định cách chia cụm cũ có thể FAIL → viết lại theo hành vi mới (nơi gần chung ngày, thừa thì `leftover`), ghi trong commit. Engine composer vẫn chạy (task 6 thay).

- [ ] **Step 6: Gỡ `every_pick_accounted`, `no_idle_with_leftover`, `travel_vs_nn`, `open_hours` khỏi `PENDING`**

Engine chưa đưa `leftover` ra view (task 6). Để kiểm 3 dùng được ngay: trong `engine._view` thêm khóa `"unplaced"`:

```python
               "unplaced": [{"place_id": pid, "name": base.trip.by_place[pid].name}
                            for pid in (getattr(base, "leftover", ()) or ())],
```

và trong `_build_base` nhánh composer gán `base.leftover = ()` (task 6 gán thật). Run bộ thực tế; với ca không quá tải, `every_pick_accounted` phải PASS; ca quá tải còn FAIL cho tới task 6 → để `every_pick_accounted: "task 6"` nếu vậy.

- [ ] **Step 7: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): split days by cheapest insertion into each day's free minutes; report what does not fit"
```

---

### Task 6: Quá tải: 3 hướng bỏ nơi, thêm giờ, một lịch chính

**Files:**
- Create: `src/planning/overload.py`, `tests/planning/test_planning_overload.py`
- Modify: `src/planning/engine.py:_build_base`, `src/planning/engine.py:create` (chọn sẵn `main`), `src/planning/session.py` (act `extend_days`)

**Interfaces:**
- Consumes: `schedule_trip(trip, kept=...) -> Schedule` có `leftover` (Task 5); `composer.selection_utilities`, `composer.must_places`, `composer.profile_metrics`.
- Produces: `overload.plan_or_directions(trip) -> dict` với khóa `variants: list[dict]`, `overload: dict | None`, `ok: bool`, `warnings: list`, `back_to_decision: dict | None`, `comparison: list`, `leftover: tuple`; mỗi variant có `id ∈ {"main","fit","travel","cost"}`, `label`, `kept`, `dropped: [{"place_id","name","reason","value"}]`, `compare: {"travel_min","cost_known_vnd","cost_unknown_n","fit"}`, `stars: list[str]`, `available: bool`, cùng các khóa engine đã đọc (`objective`, `metrics`, `itinerary`, `travel_load`, `time_suitability`, `robustness`, `backups`, `warnings`, `violations`, `confirmable`, `lodging`, `_results`, `_ctxs`, `_home`); `overload = {"missing_min", "places", "directions": [variant không có khóa `_`], "extend": {"side","per_day_min"} | None}`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_overload.py
from plan_fixtures import CENTRE, SOUTH, decision, prepared, spot

from planning.build import schedule_trip
from planning.overload import plan_or_directions


def trip_of(recs, **kw):
    d = decision([r["id"] for r in recs], base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]},
                 **kw)
    return prepared(d, recs)


def heavy(n, **kw):
    return [spot(f"c{i}", CENTRE, i, visit=(120, 150, 180), price={"typical_vnd": 10_000 * (i + 1)}, **kw)
            for i in range(n)]


def test_a_trip_that_fits_has_one_main_plan_and_no_overload():
    out = plan_or_directions(trip_of(heavy(3), days=2))
    assert [v["id"] for v in out["variants"]] == ["main"] and out["overload"] is None


def test_overload_gives_three_directions_each_dropping_just_enough():
    trip = trip_of(heavy(10), days=2)
    out = plan_or_directions(trip)
    ov = out["overload"]
    assert ov and {d["id"] for d in ov["directions"]} <= {"fit", "travel", "cost"}
    for v in out["variants"]:
        kept = set(v["kept"])
        assert not schedule_trip(trip, kept=kept).leftover
        for d in v["dropped"]:                    # just enough: adding any dropped place back does not fit
            assert schedule_trip(trip, kept=kept | {d["place_id"]}).leftover


def test_cost_drops_the_priciest_first_with_the_price_as_reason():
    out = plan_or_directions(trip_of(heavy(10), days=2))
    cost = next(v for v in out["variants"] if v["id"] == "cost" or "cost" in v.get("merged", []))
    prices = [d["value"] for d in cost["dropped"]]
    assert prices == sorted(prices, reverse=True) and all("k" in d["reason"] or "đ" in d["reason"] for d in cost["dropped"])


def test_cost_never_drops_unknown_price():
    recs = heavy(10)
    recs[9]["operation"]["entry_fee"] = None      # the priciest has no price now
    out = plan_or_directions(trip_of(recs, days=2))
    cost = next(v for v in out["variants"] if v["id"] == "cost" or "cost" in v.get("merged", []))
    assert "c9" not in {d["place_id"] for d in cost["dropped"]} and cost["compare"]["cost_unknown_n"] >= 1


def test_must_go_is_never_dropped():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={"c0": "anchor"}))
    assert all("c0" in v["kept"] for v in out["variants"])


def test_all_protected_cannot_drop():
    recs = heavy(10)
    out = plan_or_directions(trip_of(recs, days=2, roles={r["id"]: "anchor" for r in recs}))
    assert out["overload"] and all(not d["available"] for d in out["overload"]["directions"])


def test_short_by_a_little_offers_an_earlier_start():
    recs = heavy(5)
    out = plan_or_directions(trip_of(recs, days=1))
    ext = out["overload"] and out["overload"]["extend"]
    if ext:
        assert ext["side"] in {"start", "end"} and 0 < ext["per_day_min"] <= 60
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_overload.py -q`
Expected: FAIL `No module named 'planning.overload'`.

- [ ] **Step 3: Viết `src/planning/overload.py`**

```python
"""One main plan; when the trip's days cannot hold every pick, three plans that each drop places by one criterion
the user understands (spec §7): Giữ nơi hợp gu nhất, Ít đi lại, Tiết kiệm. A direction is a drop ORDER: drop the
next place until everything fits, then give back any dropped place that still fits. Must-go places never drop."""

from dataclasses import asdict, replace

from .backup import backups
from .build import Schedule, itinerary, schedule_trip, travel_load
from .composer import must_places, profile_metrics, selection_utilities
from .robustness import robustness
from .timefit import describe as time_description
from .traits import visit_minutes

LABEL = {"main": "Lịch của bạn", "fit": "Giữ nơi hợp gu nhất", "travel": "Ít đi lại", "cost": "Tiết kiệm"}
GAIN = {"fit": "giữ những nơi khớp gu bạn nhất", "travel": "ít ngồi xe nhất", "cost": "rẻ nhất"}


def _vnd(v: int) -> str:
    return f"~{v // 1000}k/người" if v < 1_000_000 else f"~{v / 1_000_000:.1f}tr/người".replace(".", ",")


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}" if minutes >= 60 else f"{minutes}′"


def _saving(trip, sched: Schedule, pid: str) -> int:
    """Minutes on the road saved by not going to pid, in the day order it has now."""
    leg = lambda a, b: trip.travel.leg(a, b)[0] if a and b else 0
    for cx, r in zip(sched.ctxs, sched.results):
        order = list(r.order)
        if pid in order:
            k = order.index(pid)
            prev = order[k - 1] if k else cx.day.start_node
            nxt = order[k + 1] if k + 1 < len(order) else cx.day.end_node
            return leg(prev, pid) + leg(pid, nxt) - leg(prev, nxt)
    home = sched.ctxs[0].home if sched.ctxs else None
    return 2 * leg(home, pid)                     # not placed: the round trip it would need


def _next(trip, sched, candidates, direction, values, ranks):
    if direction == "fit":
        pid = min(candidates, key=lambda p: (values[p], -_saving(trip, sched, p), p))
        n = ranks.index(pid) + 1
        return pid, values[pid], "ít khớp gu nhất" if n == 1 else f"khớp gu thứ {n} từ dưới lên"
    if direction == "travel":
        pid = max(candidates, key=lambda p: (_saving(trip, sched, p), -values[p], p))
        s = _saving(trip, sched, pid)
        return pid, s, f"bớt {_hm(s)} đi xe"
    priced = [p for p in candidates if trip.by_place[p].cost_vnd is not None]
    if not priced:
        return None
    pid = max(priced, key=lambda p: (trip.by_place[p].cost_vnd, p))
    v = trip.by_place[pid].cost_vnd
    return pid, v, f"đắt nhất {_vnd(v)}" if v else "miễn phí"


def _direction(trip, direction, protected, values):
    kept = set(trip.by_place)
    sched = schedule_trip(trip, kept=kept)
    ranks = sorted(set(trip.by_place) - protected, key=lambda p: (values[p], p))
    dropped = []
    while sched.leftover:
        candidates = kept - protected
        pick = _next(trip, sched, candidates, direction, values, ranks) if candidates else None
        if pick is None:
            break
        pid, value, reason = pick
        dropped.append({"place_id": pid, "name": trip.by_place[pid].name, "reason": reason, "value": value})
        kept.discard(pid)
        sched = schedule_trip(trip, kept=kept)
    for d in list(reversed(dropped)):                # give back what still fits, last dropped first
        trial = schedule_trip(trip, kept=kept | {d["place_id"]})
        if not trial.leftover:
            kept.add(d["place_id"])
            dropped.remove(d)
            sched = trial
    return kept, dropped, sched


def render_variant(trip, sched: Schedule, vid: str, dropped=(), available=True) -> dict:
    m = profile_metrics(trip, sched)
    kept = sorted({pid for r in sched.results for pid in r.order})
    days = [cx.day for cx in sched.ctxs]
    values = selection_utilities(trip)
    known = [trip.by_place[p].cost_vnd for p in kept if trip.by_place[p].cost_vnd is not None]
    violations = [asdict(v) for v in sched.violations]
    return {"id": vid, "objective": "least_travel", "preset": None, "label": LABEL[vid], "gain": GAIN.get(vid),
            "kept": kept, "dropped": list(dropped), "available": available,
            "compare": {"travel_min": m["travel_min"], "cost_known_vnd": sum(known),
                        "cost_unknown_n": len(kept) - len(known),
                        "fit": round(sum(values.get(p, 0) for p in kept) / max(1e-9, sum(values.values())), 3)},
            "metrics": m, "violations": violations, "status": "available" if available and not violations else "unavailable",
            "confirmable": available and not violations, "itinerary": itinerary(days, sched.results),
            "travel_load": travel_load(days, sched.results), "time_suitability": time_description(sched.ctxs, sched.results),
            "recommendations": [], "robustness": robustness(sched.ctxs, sched.results, trip.travel.source),
            "backups": backups(sched.ctxs, sched.results, trip.decision, trip.by_id), "warnings": sched.warnings,
            "lodging": {"id": None, "name": None, "price_vnd": None}, "score": [m["travel_min"]],
            "_results": sched.results, "_ctxs": sched.ctxs, "_home": trip.days[0].start_node if trip.days else None}


def _extend(trip) -> dict | None:
    last = len(trip.ctxs) - 1
    for minutes in range(15, trip.cfg.realistic["extend_max_min"] + 1, 15):
        for side in ("start", "end"):
            ctxs = [replace(cx, day=replace(cx.day, start=cx.day.start - minutes)) if side == "start" and
                    not (k == 0 and cx.day.start_node == "@entry") else
                    replace(cx, day=replace(cx.day, end=cx.day.end + minutes)) if side == "end" and
                    not (k == last and cx.day.end_node == "@exit") else cx
                    for k, cx in enumerate(trip.ctxs)]
            if not schedule_trip(replace(trip, ctxs=ctxs)).leftover:
                return {"side": side, "per_day_min": minutes}
    return None


def plan_or_directions(trip) -> dict:
    main = schedule_trip(trip)
    if not main.leftover:
        v = render_variant(trip, main, "main")
        return {"variants": [v], "overload": None, "ok": v["confirmable"], "warnings": [], "back_to_decision": None,
                "comparison": [], "leftover": ()}
    protected = must_places(trip)
    values = selection_utilities(trip)
    out, seen = [], {}
    for direction in ("fit", "travel", "cost"):
        kept, dropped, sched = _direction(trip, direction, protected, values)
        available = not sched.leftover
        key = frozenset(kept)
        if key in seen:
            seen[key].setdefault("merged", []).append(direction)
            seen[key]["label"] += " · " + LABEL[direction]
            continue
        v = render_variant(trip, sched, direction, dropped, available)
        seen[key] = v
        out.append(v)
    for field, better in (("travel_min", min), ("cost_known_vnd", min), ("fit", max)):
        best = better(v["compare"][field] for v in out)
        for v in out:
            v.setdefault("stars", [])
            if v["compare"][field] == best:
                v["stars"].append(field)
    missing = sum(visit_minutes(trip.by_place[p], trip.cfg, trip.pace) for p in main.leftover)
    overload = {"missing_min": missing, "places": len(trip.by_place),
                "directions": [{k: x for k, x in v.items() if not k.startswith("_")} for v in out],
                "extend": _extend(trip)}
    ok = any(v["confirmable"] for v in out)
    return {"variants": out, "overload": overload, "ok": ok, "warnings": [], "comparison": [],
            "back_to_decision": None if ok else {"reason": "required_places_do_not_fit", "places": sorted(protected)},
            "leftover": main.leftover}
```

- [ ] **Step 4: Chạy test overload**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_overload.py -q` → PASS. Nếu `test_cost_drops_the_priciest_first...` FAIL vì `fixture rec(price=...)` không ra `cost_vnd`: kiểm `places.cost_of` đọc `entry_fee.typical_vnd` — `heavy()` đã truyền đúng dạng đó.

- [ ] **Step 5: Engine dùng `plan_or_directions`**

`engine.py` `_build_base`, thay toàn thân bằng:

```python
    def _build_base(self, decision: dict) -> _Base:
        trip = self._prepare(decision)
        from .overload import plan_or_directions
        out = plan_or_directions(trip)
        base = _Base(trip, out["variants"], out["comparison"], out["ok"], list(trip.warnings) + out["warnings"],
                     out["back_to_decision"])
        base.overload, base.keep_all, base.leftover = out["overload"], None, out["leftover"]
        return base
```

`_Base.__init__` thêm `self.leftover: tuple = ()`. Trong `create`, sau khi có `base` và trước `self.store.save(s)`:

```python
        if base.overload is None and base.variants:
            s.states[0] = s.states[0].model_copy(update={"chosen_variant": base.variants[0]["id"]})
```

`_view` khóa `"unplaced"` (Task 5): khi `chosen_variant` thuộc một hướng, `unplaced` = `dropped` của hướng đó cộng `base.trip.unplaced`; khi chưa chọn hướng (đang hiện 3 thẻ), `unplaced` = `base.leftover`:

```python
        chosen = next((v for v in base.variants if v["id"] == s.state.chosen_variant), None)
        dropped = chosen["dropped"] if chosen else [{"place_id": p, "name": base.trip.by_place[p].name}
                                                    for p in base.leftover]
        unplaced = [{"place_id": d["place_id"], "name": d["name"], "reason": d.get("reason")} for d in dropped] + \
                   [{"place_id": p.id, "name": p.name, "reason": p.reason} for p in base.trip.unplaced]
```

`ActCtx(... objective_names=set(LABEL) | {"keep_all"} ...)`: giữ; `variant_ids` đã lấy từ `base.variants` nên có `main/fit/travel/cost`.

- [ ] **Step 6: Act `extend_days`**

`session.py` `_apply`, thêm nhánh:

```python
    elif t == "extend_days":
        side, minutes = action.get("side"), action.get("per_day_min")
        if side not in {"start", "end"} or not isinstance(minutes, int) or not 0 < minutes <= 60:
            raise ActionError("extend_days needs side start|end and 1..60 minutes")
        for day, (lo, hi) in enumerate(ctx.day_windows):
            s.day_window_override[day] = (lo - minutes, hi) if side == "start" else (lo, hi + minutes)
```

`ActCtx` thêm `day_windows: list = field(default_factory=list)`; engine điền `day_windows=[(cx.day.start, cx.day.end) for cx in base.trip.ctxs]` ở hai chỗ tạo `ActCtx`. Act này chạy lại từ ⓑ như `set_day_window`: thêm `"extend_days"` vào tập act có phạm vi VARIANT trong `_compute_results` (tìm chỗ xử lý `"set_day_window"` và thêm cùng nhánh).

Test thêm vào `test_planning_overload.py`:

```python
def test_extend_days_widens_every_day_window():
    from planning.session import ActCtx, State, _apply
    ctx = ActCtx({}, 2, set(), {}, [], set(), {"normal"}, day_windows=[(480, 1260), (480, 1260)])
    s = _apply(State(), {"type": "extend_days", "side": "start", "per_day_min": 45}, ctx)
    assert s.day_window_override == {0: (435, 1260), 1: (435, 1260)}
```

- [ ] **Step 7: Bộ planning — viết lại test của composer cũ**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q --deselect tests/planning/test_planning_realism.py 2>&1 | tail -60`
Expected FAIL ở `test_planning_composer.py`, `test_planning_objectives.py`, `test_planning_overload_edits.py`, `test_planning_engine.py`, `test_planning_session_golden.py` vì chúng khẳng định `profile-*`, `keep_all`, `v1/v2`. Xử lý:
- Test của `composer._select` / `compose` / `PRESETS`: hành vi bị spec thay → chuyển sang khẳng định tương đương trên `plan_or_directions` (ba hướng, bỏ vừa đủ, must không bỏ) hoặc xóa khi đã có test tương đương trong `test_planning_overload.py`; ghi tên từng test đã xóa và test thay thế trong commit message.
- Test engine/session chỉ dùng id `v1` để chọn phương án: đổi sang `view["variants"][0]["id"]` (= `main`).
- Golden phiên: tái sinh, xem `git diff`.

- [ ] **Step 8: Gỡ `overload_explained` (và `every_pick_accounted` nếu còn) khỏi `PENDING`**

`run_case` đã chọn biến thể đầu khi chưa có itinerary. Run bộ thực tế → PASS.

- [ ] **Step 9: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): one main plan; on overload three drop-order directions with reasons, plus extend"
```

---

### Task 7: Gợi ý mờ cho ô bữa và khoảng trống, từ corpus

**Files:**
- Create: `src/planning/ghosts.py`, `tests/planning/test_planning_ghosts.py`
- Modify: `src/planning/engine.py` (`_view` khóa `ghosts`; `_active_place` và `ActCtx.backup_ids` nhận id gợi ý), `src/planning/session.py` (`State.dismissed`, act `dismiss_suggestion`)

**Interfaces:**
- Consumes: item `meal_free`, `free` (Task 3); `Place.meal_kind` (Task 2); `lodging.sieve`, `traits.preference`, `places.build_places`, `places.windows_on`, `travel.km`, `travel.rough_minutes`.
- Produces: `ghosts.pool(records, decision, cfg) -> list[Place]`; `ghosts.fill(ctxs, results, pool, taken: set[str], dismissed: set[str], soft: list, points: dict) -> list[dict]` (`points` = `Trip.points`, nút → `Point`) mỗi phần tử `{"day", "kind": "breakfast|lunch|dinner|free", "start", "end", "items": [{"place_id","name","price_vnd","detour_min"}]}` (tối đa 3, đầu tiên là gợi ý mờ); `State.dismissed: list[str]`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_ghosts.py
from plan_fixtures import CENTRE, CFG, decision, prepared, spot

from planning.build import schedule_trip
from planning.ghosts import fill, pool


def setup():
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1),
            spot("r1", CENTRE, 2, usable=("meal", "backup"), group="restaurant", name="Lẩu A"),
            spot("r2", CENTRE, 3, usable=("meal", "backup"), group="restaurant", name="Bánh căn B"),
            spot("k1", CENTRE, 4, usable=("meal", "backup"), group="dessert", name="Kem C")]
    d = decision(["c1", "c2"], days=1, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    trip = prepared(d, recs)
    return trip, recs, d


def test_an_empty_meal_slot_gets_a_real_open_place_never_a_snack_shop():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, set(), [], trip.points)
    lunch = next(x for x in slots if x["kind"] == "lunch")
    assert lunch["items"] and lunch["items"][0]["place_id"] in {"r1", "r2"}
    assert "k1" not in {i["place_id"] for x in slots if x["kind"] in {"lunch", "dinner"} for i in x["items"]}


def test_breakfast_prefers_a_breakfast_dish_and_dismissed_places_stay_hidden():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, {"r2"}, [], trip.points)
    assert all(i["place_id"] != "r2" for x in slots for i in x["items"])


def test_no_place_is_suggested_twice_in_a_day():
    trip, recs, d = setup()
    s = schedule_trip(trip)
    slots = fill(s.ctxs, s.results, pool(recs, d, CFG), {"c1", "c2"}, set(), [], trip.points)
    firsts = [x["items"][0]["place_id"] for x in slots if x["items"]]
    assert len(firsts) == len(set(firsts))
```

- [ ] **Step 2: Chạy, xác nhận FAIL**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning/test_planning_ghosts.py -q`
Expected: FAIL `No module named 'planning.ghosts'`.

- [ ] **Step 3: Viết `src/planning/ghosts.py`**

```python
"""Faded suggestions (spec §6): every empty meal slot and every long free time shows one real place, open then,
near the stops around it, that fits the trip's taste; "xem thêm" opens the next two. Not on the timeline until the
user taps it (then it is an add_from_backup of that id)."""

from .lodging import sieve
from .places import build_places, windows_on
from .travel import km, rough_minutes
from .traits import preference

SLOT_ROLES = {"breakfast": {"breakfast"}, "lunch": {"main", "breakfast"}, "dinner": {"main", "night_meal"},
              "free": {"light", None}}


def pool(records: list[dict], decision: dict, cfg) -> list:
    """Places the suggestions may come from: eating places and sights the hard filters allow, nearest the trip first."""
    chosen = {c["id"] for c in decision["confirmed"]}
    hard = decision["trip_context"].get("hard_filters") or []
    usable = [r for r in records if r["id"] not in chosen and r["identity"].get("category_group") != "stay"
              and (r.get("usable_as") or []) and r["identity"].get("lat") is not None]
    usable = sieve(usable, hard, min_reviews=0)
    by_id = {r["id"]: r for r in records}
    pts = [(by_id[i]["identity"]["lat"], by_id[i]["identity"]["lng"]) for i in chosen if i in by_id]
    if pts:
        c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        usable.sort(key=lambda r: km(c, (r["identity"]["lat"], r["identity"]["lng"])))
    usable = usable[: cfg.realistic["suggest_pool_max"] * 4]
    places, _ = build_places({"confirmed": [{"id": r["id"]} for r in usable], "trip_context": decision["trip_context"]},
                             {r["id"]: r for r in usable}, cfg)
    return places


def _where(cx, node, points: dict):
    if node is None:
        return None
    p = cx.places.get(node)
    if p:
        return (p.lat, p.lng)
    pt = points.get(node)
    return (pt.lat, pt.lng) if pt else None


def fill(ctxs, results, places: list, taken: set, dismissed: set, soft: list, points: dict) -> list[dict]:
    out = []
    for cx, r in zip(ctxs, results):
        used = set(taken)
        items = list(r.items)
        for k, it in enumerate(items):
            if it.kind == "meal_free":
                kind = it.name
            elif it.kind == "free" and it.end - it.start >= cx.cfg.realistic["fill_min_gap"]:
                kind = "free"
            else:
                continue
            prev = next((i.place_id or i.to_id for i in reversed(items[:k]) if i.place_id or i.to_id), cx.day.start_node)
            nxt = next((i.place_id or i.to_id for i in items[k + 1:] if i.place_id or i.to_id), cx.day.end_node)
            here = [q for q in (_where(cx, prev, points), _where(cx, nxt, points)) if q]
            ranked = []
            for p in places:
                if p.id in used or p.id in dismissed or p.meal_kind not in SLOT_ROLES[kind]:
                    continue
                if kind == "free" and p.kind == "meal" and p.meal_kind not in (None, "light"):
                    continue
                spans = windows_on(p.hours, cx.day.weekday)
                if spans is not None and not any(o <= it.start and it.start + 30 <= c for o, c in spans):
                    continue
                detour = min((rough_minutes(km(q, (p.lat, p.lng)), cx.mobility, cx.cfg) for q in here), default=0)
                if detour > cx.cfg.realistic["suggest_radius_min"]:
                    continue
                ranked.append((-(preference(p, soft)) + detour / 15, detour, p))
            ranked.sort(key=lambda x: (x[0], x[2].id))
            top = [{"place_id": p.id, "name": p.name, "price_vnd": p.cost_vnd, "detour_min": d}
                   for _, d, p in ranked[:3]]
            if top:
                used.add(top[0]["place_id"])
            out.append({"day": cx.day.index, "kind": kind, "start": it.start, "end": it.end, "items": top})
    return out
```

- [ ] **Step 4: Chạy test ghosts** → PASS.

- [ ] **Step 5: Nối vào engine**

`_Base` thêm `self.pool: list | None = None`. Trong `_view`, sau khi có `active`:

```python
        if base.pool is None:
            from .ghosts import pool
            base.pool = pool(self.records, s.decision, self.cfg)
        from .ghosts import fill
        ghosts = fill(active["ctxs"], active["results"], base.pool, set(self._places_for(s, base)),
                      set(s.state.dismissed), s.decision["trip_context"].get("soft_weights") or [],
                      base.trip.points) if active else []
```

và thêm `"ghosts": ghosts` vào dict trả về. Id gợi ý được thêm như backup: `ActCtx.backup_ids` gộp `{p.id: {"id": p.id, "for": None, "reason": "suggestion"} for p in base.pool or []}`; `_active_place` điều kiện `pid in {b["id"] for b in s.decision.get("backup_pool") or []}` mở rộng thành `... or pid in {p.id for p in base.pool or []}` (dựng `base.pool` trước nếu `None`, dùng chung hàm như trên).

`session.py`: `State.dismissed: list[str] = Field(default_factory=list)`; `_apply` nhánh:

```python
    elif t == "dismiss_suggestion":
        pid = action.get("place")
        if not isinstance(pid, str):
            raise ActionError("dismiss_suggestion needs a place id")
        if pid not in s.dismissed:
            s.dismissed.append(pid)
```

`dismiss_suggestion` không đổi lịch: thêm vào tập act phạm vi "không chạy lại" trong `_compute_results` (cùng nhánh với `pick_variant`).

- [ ] **Step 6: Test replay gợi ý đã nhận**

Thêm vào `tests/planning/test_planning_ghosts.py`:

```python
def test_replay_rebuilds_an_accepted_suggestion(tmp_path):
    from plan_fixtures import FakeLive, fake_matrix, no_geocode
    from planning import Engine
    from planning.session import Store
    trip, recs, d = setup()
    kw = dict(cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (360, 1050), background=False)
    e = Engine(recs, store=Store(tmp_path), **kw)
    out = e.create(d)
    ghost = next(x for x in out["view"]["ghosts"] if x["items"])["items"][0]["place_id"]
    view = e.act(out["id"], {"type": "add_from_backup", "place": ghost, "day": 0})["view"]
    assert ghost in {i.get("place_id") for day in view["itinerary"] for i in day["items"]}
    fresh = Engine(recs, store=Store(tmp_path), **kw)
    again = fresh.act(out["id"], {"type": "dismiss_suggestion", "place": "nothing"})["view"]
    assert ghost in {i.get("place_id") for day in again["itinerary"] for i in day["items"]}
```

Run → PASS (nếu `Store(path)` cần thư mục khác, đọc chữ ký `Store` trong `session.py`).

- [ ] **Step 7: Bộ planning + bộ thực tế**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q 2>&1 | tail -20` → PASS / XFAIL (chỉ `reorder_kept` nếu còn).

- [ ] **Step 8: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): faded suggestions for empty meals and free time, from the corpus, accepted as a backup add"
```

---

### Task 8: Sửa lịch nhanh và gợi ý thứ tự tốt hơn

**Files:**
- Modify: `src/planning/session.py` (`State.keep_order_days`, act `keep_my_order`), `src/planning/engine.py` (`_view` khóa `better_order`)
- Test: `tests/planning/test_planning_better_order.py`; bench `tests/planning/bench_realistic.py`

**Interfaces:**
- Consumes: `route.order_day(ids, ctx) -> DayResult`; `State.order_override`.
- Produces: `view["better_order"]: list[{"day", "order", "saved_min", "fixes": list[str]}]`; act `keep_my_order(day:int)`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/planning/test_planning_better_order.py
from plan_fixtures import CENTRE, SOUTH, CFG, FakeLive, decision, fake_matrix, no_geocode, spot

from planning import Engine
from planning.session import Store


def eng(recs):
    return Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                  sun_fn=lambda *a: (360, 1050), background=False)


def setup():
    recs = [spot("c1", CENTRE, 0), spot("s1", SOUTH, 0), spot("c2", CENTRE, 1), spot("s2", SOUTH, 1)]
    d = decision([r["id"] for r in recs], days=1, base={"place_id": None, "text": "home", "lat": CENTRE[0], "lng": CENTRE[1]})
    return recs, d


def test_reorder_keeps_the_user_order_and_offers_a_shorter_one():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    zigzag = ["c1", "s1", "c2", "s2"]
    view = e.act(sid, {"type": "reorder", "day": 0, "order": zigzag})["view"]
    got = [i["place_id"] for i in view["itinerary"][0]["items"] if i["kind"] == "visit"]
    assert got == zigzag
    hint = view["better_order"]
    assert hint and hint[0]["day"] == 0 and hint[0]["saved_min"] >= CFG.realistic["better_order_min"]


def test_a_fine_reorder_gets_no_hint_and_keep_my_order_silences_it():
    recs, d = setup()
    e = eng(recs)
    sid = e.create(d)["id"]
    view = e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "c2", "s1", "s2"]})["view"]
    assert not view["better_order"]
    e.act(sid, {"type": "reorder", "day": 0, "order": ["c1", "s1", "c2", "s2"]})
    view = e.act(sid, {"type": "keep_my_order", "day": 0})["view"]
    assert not view["better_order"]
```

- [ ] **Step 2: Chạy, xác nhận FAIL** (`better_order` không có trong view).

- [ ] **Step 3: State + act**

`session.py`: `State.keep_order_days: list[int] = Field(default_factory=list)`; `_apply`:

```python
    elif t == "keep_my_order":
        day = action.get("day")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        if day not in s.keep_order_days:
            s.keep_order_days.append(day)
```

`keep_my_order` không đổi lịch: cùng nhánh "không chạy lại" với `dismiss_suggestion`.

- [ ] **Step 4: `better_order` trong `_view`**

```python
    def _better_order(self, s: Session, active: dict | None) -> list[dict]:
        """For each day the user reordered: the best order of the same places, shown only when it saves at least
        better_order_min minutes on the road or fixes a problem. Never applied."""
        if not active:
            return []
        from .route import order_day
        out = []
        for day, order in s.state.order_override.items():
            if day in s.state.keep_order_days or day >= len(active["results"]):
                continue
            mine, cx = active["results"][day], active["ctxs"][day]
            best = order_day(list(order), cx)
            saved = mine.travel_min - best.travel_min
            fixes = sorted({v.kind for v in mine.violations} - {v.kind for v in best.violations})
            if list(best.order) != list(order) and (saved >= self.cfg.realistic["better_order_min"] or fixes):
                out.append({"day": day, "order": list(best.order), "saved_min": saved, "fixes": fixes})
        return out
```

gọi trong `_view`: `"better_order": self._better_order(s, active)`. (Nếu `active` không có khóa `ctxs` / `results`: dùng tên thật trong `_active_itinerary` — đọc nó và khớp.)

- [ ] **Step 5: Chạy test** → PASS. Gỡ `reorder_kept` khỏi `PENDING`; `PENDING` giờ rỗng. Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q` → toàn bộ PASS.

- [ ] **Step 6: Đo tốc độ**

Run: `.venv/bin/python tests/planning/bench_realistic.py --runs 3`
Expected: `create p95 < 2.0s`, `reorder < 0.05s`, `drop_place < 0.05s`, `move_place < 0.1s`, exit 0.
Nếu một dòng FAIL: `.venv/bin/python -m cProfile -o /tmp/claude-2420/bench.prof tests/planning/bench_realistic.py --runs 1` rồi `python -c "import pstats; pstats.Stats('/tmp/claude-2420/bench.prof').sort_stats('cumulative').print_stats(25)"`; sửa đúng hàm nóng nhất (thường là `order_day` vét cạn: hạ `exact_n` khi ngày có > 6 nơi, hoặc dùng cache `trip.routes` cho `repair_day`), chạy lại tới khi đạt. Ghi số trước / sau vào commit message.

- [ ] **Step 7: Commit**

```bash
git add src/planning tests/planning
git commit -m "feat(planning): keep the user's order, hint a shorter one only when it is worth it; edit latency within targets"
```

---

### Task 9: Gỡ phần cũ, đo trước / sau, cho user đọc

**Files:**
- Delete: `src/planning/cluster.py`, `tests/planning/test_planning_cluster.py`; trong `src/planning/days.py` các hàm chỉ `schedule_trip` cũ dùng (`assign_days`, `_greedy`, `isolate_constrained`, `day_cost` nếu không còn ai gọi); trong `src/planning/composer.py` `_select`, `_quality`, `_detour`, `compose`, `render_profile`, `profile_violations`, `PRESETS`/`LABELS`/`DEFINITIONS`/`TRADEOFFS` nếu không còn ai gọi
- Modify: `src/planning/engine.py` (bỏ nhánh objectives `choose(...)` không còn dùng), `docs/superpowers/specs/2026-10-15-planning-realistic-redesign-design.md` §3 (sửa câu "vòng K+1 chỗ ở trong create": thực tế vòng này chỉ ở CLI `lodging`)

- [ ] **Step 1: Tìm chỗ còn gọi**

Run: `grep -rn "cluster_places\|split_to_fit\|assign_days\|isolate_constrained\|day_cost\|compose(\|_select(\|render_profile\|PRESETS" src tests | grep -v "^src/planning/cluster.py\|^src/planning/days.py\|^src/planning/composer.py"`
Expected: chỉ còn test của chính các hàm đó (và `variants.py` CLI nếu có). Hàm nào còn người gọi ngoài test của nó thì giữ.

- [ ] **Step 2: Xóa hàm / file không còn ai gọi và test riêng của chúng**

Xóa; rồi Run: `.venv/bin/python -m pytest --collect-in-virtualenv tests/planning -q` → PASS. `test_planning_boundaries.py` (2 lỗi cũ `[engine.py]`, `[tools.py]` có từ trước, xem `docs/plans/TRIP_REDESIGN_HANDOFF.md`) không được tăng thêm lỗi.

- [ ] **Step 3: Toàn bộ repo**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -q 2>&1 | tail -15`
Expected: không lỗi mới so với 3 lỗi cũ đã biết. Harness / web contract test đọc `variants[0]["id"] == "v1"` → sửa sang id thật.

- [ ] **Step 4: Render bản mới + bench**

Run: `.venv/bin/python tests/planning/bench_realistic.py --runs 3 --render logs/planning_realistic/after`
Expected: exit 0. So `logs/planning_realistic/before/family_12_in_3.txt` với `after/`: không còn "chờ" dài, kem bơ không làm bữa tối, Cầu Đất lúc bình minh, mọi nơi có trên lịch hoặc trong "Chưa xếp".

- [ ] **Step 5: Sửa spec §3 cho đúng code**

Trong spec, bảng "Bỏ khỏi đường tạo phiên": đổi dòng `vòng K+1 chỗ ở × 3 mục tiêu (variants.py)` thành `objectives 2–3 phương án (engine._build_base, objectives.choose)`.

- [ ] **Step 6: Đưa user đọc**

Báo user đường dẫn `logs/planning_realistic/before/` và `after/`, kèm bảng p50/p95, và đề nghị đọc 5–10 ca (gợi ý: `family_12_in_3`, `couple_slow_dawn`, `flight_1640`, `family_kid_nap`, `food_tour_8`, `reorder_bad`). Chưa deploy; deploy cần lệnh rõ của user.

- [ ] **Step 7: Commit**

```bash
git add -A src/planning tests/planning docs/superpowers/specs/2026-10-15-planning-realistic-redesign-design.md
git commit -m "refactor(planning): remove the cluster split and composer subset search the realistic core replaced"
```
