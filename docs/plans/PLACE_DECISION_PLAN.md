# Backend Place Decision — Plan triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Module `src/decision/` chạy Place Decision ① → ⑩ trên serving record, có agent Gemma cho câu gõ chữ, HTTP + SSE, và web Shortlist / Compare / CurateBar / Feasibility đọc từ backend.

**Architecture:** Các bước ③–⑨ là hàm thuần trên `Cand` (một ứng viên + kết quả từng bước); `pipeline.run(session)` chạy lại toàn bộ sau mỗi thao tác. Phiên (`Session`, pydantic) giữ Search Input + thao tác + phiên bản để hoàn tác, lưu `data/decision/sessions/<id>.json`. Chip / nút bấm đi `POST /act` (tất định); câu gõ chữ đi một call `DECISION_TURN` → guard → cùng các thao tác đó.

**Tech Stack:** Python 3.12, pydantic 2, PyYAML, `http.server` (như `src/trip`), openai client qua `corpus.llm`; React + TypeScript + Vite ở `web/`.

**Spec:** `docs/plans/PLACE_DECISION_SPEC.md` (hành vi tham chiếu: `docs/PLACE_DECISION.md`).

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, commit message tiếng Anh (`RULE.md` §0).
- `decision` chỉ import `trip`, `corpus.serving`, `corpus.llm`, `corpus.ontology` qua public API; `corpus` và `trip` không import `decision` (`RULE.md` §2).
- Chỉ đọc `data/serving/places.json`; chỉ ghi `data/decision/`. Không ghi Place Intelligence.
- Fail-closed: danh sách chính không có hard filter nào khác `pass`; thiếu bằng chứng ≠ an toàn.
- Nơi đã chọn / khóa / anchor không bao giờ bị loại âm thầm; chỉ ứng viên chưa chọn được xếp lại.
- Thẻ ứng viên dựng bằng template từ field serving record; agent chỉ nói `say`, mọi thay đổi đi qua thao tác có validate.
- Server chỉ bind `127.0.0.1`, cổng mặc định 8767; Vite proxy `/api/decision`.
- Số liệu ngưỡng nằm trong `config/decision.yaml`, không hardcode trong code.
- Chạy test: `python -m pytest -q tests/decision` (từ thư mục `tripguardian/`); test live: `python -m pytest -m live tests/decision/test_live.py -s`.

## Review Focus

- Search Input chỉ có `month` (không có `start_date`) hoặc thiếu `days`: không được crash, không kiểm giờ theo thứ, khả thi trả `unknown` khi không có conflict (Task 7, Task 10 có test).
- Anchor không có trong serving (đã đóng cửa hoặc chưa crawl): giữ lại dưới dạng thẻ "chưa có trong dữ liệu", không crash, không bị loại (Task 10 có test).
- Thao tác gửi id lạ, lý do lạ, `swap` sang nơi không phải phương án thay thế, `answer` không khớp câu đang hỏi: trả 400, state không đổi (Task 8, Task 12 có test).
- Agent trả quote không có trong tin nhắn, alias không có, hoặc `say` có số / tên nơi ngoài view: update bị bỏ, `say` bị thay (Task 11 có test).
- Hai request cùng phiên chạy song song (double click): mỗi request giữ lock của phiên, history không mất bước (Task 12 có test).

---

## Cấu trúc file

```text
config/decision.yaml                 ngưỡng, trọng số, nhãn (spec §18)
src/decision/
  __init__.py                        public: Engine, Data, Settings, Store, load_settings, run_pipeline
  __main__.py                        python -m decision {serve|evaluate}
  settings.py                        Settings + load()
  geo.py                             km, minutes, to_min, fmt, point
  trip_days.py                       TripDay, trip_days(), month_of()
  model.py                           Cand, role_of(), value(), FIRM
  screen.py                          ③ hard_result(), closed_all_days(), screen()
  fit.py                             ④ centers(), radius(), fit()
  rank.py                            ⑤ conf(), wants(), preference(), score()
  cards.py                           thẻ: card(), phrase(), feature_label()
  diversify.py                       ⑥ display_group(), sizes(), pick()
  feasibility.py                     ⑨ evaluate(), need_buckets(), supply()
  session.py                         State, Profile, Pending, Session, Store
  curation.py                        ⑧ apply(), pending(), ActionError
  scope.py                           replan_scope(), input_scope()
  compare.py                         ⑦ compare()
  pipeline.py                        Data, Result, run(), why_not()
  output.py                          ⑩ build()
  agent.py                           SayStream, run_agent(), AgentError
  guard.py                           TurnPlan, guard()
  policy.py                          policy()
  engine.py                          Engine
  server.py                          handler(), run()
  evaluate.py                        mô phỏng offline
tests/decision/
  conftest.py, fixtures.py, test_*.py
src/corpus/llm/tasks.py, __init__.py DECISION_TURN
src/trip/state.py, compile.py, __init__.py   Context.budget_vnd, Context.experience; export squash, contains
web/src/user/pd/{types,api}.ts       client API decision
web/src/user/screens/{Shortlist,Compare,Curate,Feasibility,Understand}.tsx, trip.tsx, planner.ts
web/vite.config.ts
```

---

### Task 1: Search Input mang `budget_vnd`, `experience`; export text helper của trip

**Files:**
- Modify: `src/trip/state.py` (class `Context`)
- Modify: `src/trip/compile.py`
- Modify: `src/trip/__init__.py`
- Modify: `web/src/user/tu/types.ts` (interface `SearchInput.context`)
- Test: `tests/trip/test_compile.py`

**Interfaces:**
- Produces: `trip.SearchInput.context.budget_vnd: int | None`, `trip.SearchInput.context.experience: Literal["first","returning"] | None`; `trip.squash(s) -> str`, `trip.contains(haystack, needle) -> bool`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào cuối `tests/trip/test_compile.py`:

```python
def test_context_carries_budget_and_experience():
    from trip.state import Meta
    s = TripState(meta=Meta(experience="returning"))
    s = up(s, "budget_vnd", 500000)
    si = compile_search_input(s)
    assert si.context.budget_vnd == 500000 and si.context.experience == "returning"
    assert "budget_vnd" not in si.unknowns


def test_trip_exports_text_helpers():
    from trip import contains, squash
    assert squash("Đồi Chè Cầu Đất!") == "doi che cau dat" and contains("tới đồi chè cầu đất", "Cầu Đất")
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/trip/test_compile.py -k "budget or text_helpers"`
Expected: FAIL (`Context` không có `budget_vnd`; `ImportError: cannot import name 'contains'`).

- [ ] **Step 3: Cài đặt**

`src/trip/state.py`, class `Context` thêm hai field cuối:

```python
class Context(Frozen):
    start_date: date | None
    month: int | None
    days: int | None
    base: Base | None
    mobility: Vehicle | None
    companions: tuple[Who, ...]
    people: int | None
    arrive_at: str | None
    leave_at: str | None
    day_end: str | None
    budget_vnd: int | None = None
    experience: Literal["first", "returning"] | None = None
```

`src/trip/compile.py`, dòng `context=Context(...)` thành:

```python
        context=Context(start_date=v("start_date"), month=v("month"), days=v("days"), base=v("base"),
                        mobility=v("mobility"), companions=tuple(sorted(v("companions") or ())), people=v("people"),
                        arrive_at=v("arrive_at"), leave_at=v("leave_at"), day_end=v("day_end"),
                        budget_vnd=v("budget_vnd"), experience=state.meta.experience),
```

`src/trip/__init__.py`:

```python
"""Trip Understanding: understand what the user needs for this trip -> Search Input (docs/TRIP_UNDERSTANDING.md)."""

from .catalog import Catalog
from .compile import UnhandledSignal, compile_search_input
from .engine import Engine, TurnInput
from .sessions import SessionStore
from .settings import Settings
from .state import SearchInput, TripState
from .text import contains, squash

__all__ = ["Catalog", "Engine", "SearchInput", "SessionStore", "Settings", "TripState", "TurnInput", "UnhandledSignal",
           "compile_search_input", "contains", "squash"]
```

`web/src/user/tu/types.ts`, trong `SearchInput.context` sau `day_end`:

```ts
    day_end: string | null
    budget_vnd: number | null
    experience: 'first' | 'returning' | null
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/trip`
Expected: PASS toàn bộ (95 test cũ + 2 mới).

- [ ] **Step 5: Commit**

```bash
git add src/trip/state.py src/trip/compile.py src/trip/__init__.py web/src/user/tu/types.ts tests/trip/test_compile.py
git commit -m "feat(trip): Search Input context carries budget and experience; export text helpers"
```

---

### Task 2: Khung module: config, Settings, geo, ngày của chuyến, fixture test

**Files:**
- Create: `config/decision.yaml`
- Create: `src/decision/__init__.py` (tạm rỗng phần export, Task 12 điền đủ)
- Create: `src/decision/settings.py`, `src/decision/geo.py`, `src/decision/trip_days.py`, `src/decision/model.py`
- Create: `tests/decision/__init__.py` (rỗng), `tests/decision/conftest.py`, `tests/decision/fixtures.py`
- Test: `tests/decision/test_basics.py`

**Interfaces:**
- Produces:
  - `decision.settings.Settings` (dataclass đóng băng, field = key của yaml), `load(path=PATH) -> Settings`, `default() -> Settings` (cache).
  - `decision.geo.km(a: tuple[float,float], b: tuple[float,float]) -> float`, `minutes(d_km: float, mobility: str|None, cfg) -> int`, `to_min("HH:MM") -> int`, `fmt(int) -> "HH:MM"`, `point(rec) -> tuple[float,float] | None`.
  - `decision.trip_days.TripDay(index, date, weekday, day_type, start, end)`, `trip_days(ctx, cfg) -> list[TripDay]`, `month_of(ctx) -> int | None`.
  - `decision.model.Cand`, `role_of(rec) -> str | None`, `value(rec, fid) -> str | None`, `FIRM = ("VERIFIED", "OUTDATED")`.
  - Test fixture: `fixtures.feat(...)`, `fixtures.srec(...)`, `fixtures.si(**over) -> SearchInput`, `fixtures.ALL_DAY`, `fixtures.MONDAY = date(2026, 12, 14)`.

- [ ] **Step 1: Viết config**

`config/decision.yaml`:

```yaml
# Place Decision thresholds (docs/plans/PLACE_DECISION_SPEC.md §18). Starting values; tune after the pilot.
version: 1
center: {name: "trung tâm Đà Lạt", lat: 11.9404, lng: 108.4583}
speed_kmh: {motorbike: 25, car: 25, ride: 22}
road_factor: 1.4            # straight line -> road distance
radius_km: {motorbike: 12, car: 15, ride: 10}
area_bonus: 0.2             # same area as an anchor
crowd_busy_pct: 70          # Google popular times at or above this = busy
crowd_penalty: 0.2
rainy_months: [5, 6, 7, 8, 9, 10]
min_context_fit: 0.1        # below: stays in the pool, never in the shortlist
weights: {ctx: 1.0, pref: 2.0, nov: 1.0, exp: 0.3, pop: 0.2, unc: 0.5, price: 0.5}
price_ref_vnd: 300000       # price per person that counts as "expensive" (1.0) for price sensitivity
near_min: 12                # minutes: "Gần <tâm>" on a card
per_day: {slow: 3, normal: 4, packed: 6}
per_day_max: {slow: 4, normal: 5, packed: 7}
meals_per_day: 2
spare_factor: 1.6
pool_factor: 5
default_days: 2
day_start: "08:00"
day_end: "21:00"
leave_at: "15:00"
buffer_min: {slow: 30, normal: 20, packed: 10}
intra_leg_min: 10
far_km: 8
buckets: {early_morning: ["05:00", "07:00"], morning: ["07:00", "11:00"], noon: ["11:00", "13:00"],
          afternoon: ["13:00", "17:00"], evening: ["17:00", "19:00"], night: ["19:00", "22:00"]}
narrow_buckets: [early_morning, evening, night]
timed_features: [cloud_hunting, sunset_view, live_music]
timed_share: 0.6
night_open: "16:00"
infeasible_ratio: 1.35
budget_slack: 1.0
far_step: 0.8
travel_mult_min: 0.4
price_step: 0.5
pattern_min: 3
gap_min: 90
rethink_drops: 6
history_max: 50
unverified_show: 12
first_token_s: 8
total_s: 30
display_groups:
  nature: [nature, garden_farm, camping]
  sights: [attraction, museum, religious, amusement, market, tour, golf, other]
  chill: [cafe, spa, bar, dessert]
polarity:                   # good first, bad last
  crowd: [low, medium, high]
  noise: [quiet, moderate, loud]
  cleanliness: [clean, dirty]
  toilet: [clean, dirty]
  parking: [easy, hard]
  food_quality: [good, mixed, poor]
  drink_quality: [good, mixed, poor]
  service_attitude: [good, poor]
  service_quality: [good, mixed, poor]
  value_for_money: [good, poor]
  wait_time: [none, short, long]
  portion_size: [generous, small]
  tourist_trap: [absent, present]
  weather_exposed: [sheltered, present]
  entry_fee: [free, paid]
  rough_road_access: [absent, present]
  steep_or_stairs: [absent, present]
  long_walk: [absent, present]
labels:                     # same words as web/src/data/labels.ts
  group: {anchors: "Nơi bạn muốn đến", nature: "Thiên nhiên và view", sights: "Điểm tham quan",
          chill: "Cà phê và thư giãn", meal: "Ăn uống"}
  reason: {far: "Quá xa", crowded: "Quá đông", pricey: "Quá đắt", dislike: "Không thích", visited: "Đã đi rồi"}
  pace: {slow: "thong thả", normal: "cân bằng", packed: "đi nhiều"}
  time: {early_morning: "sáng sớm", morning: "buổi sáng", noon: "buổi trưa", afternoon: "buổi chiều",
         evening: "buổi tối", night: "đêm", weekday: "ngày thường", weekend: "cuối tuần"}
  feature:
    scenic_view: "View đẹp"
    cloud_hunting: "Săn mây"
    sunset_view: "Ngắm hoàng hôn"
    photo_spot: "Nhiều góc chụp"
    nature: "Thiên nhiên"
    flower_garden: "Vườn hoa"
    heritage_architecture: "Kiến trúc, di tích"
    cozy_decor: "Không gian xinh"
    laptop_friendly: "Ngồi làm việc được"
    long_stay_chill: "Ngồi lâu, chill"
    live_music: "Nhạc sống"
    adventure_activity: "Trò mạo hiểm"
    hiking: "Leo núi, trekking"
    animals: "Có thú để chơi"
    local_specialty_food: "Món đặc sản"
    food_quality: "Đồ ăn"
    drink_quality: "Đồ uống"
    hands_on_workshop: "Workshop tự làm"
    pick_your_own: "Tự hái tại vườn"
    cultural_show: "Biểu diễn văn hóa"
    camping: "Cắm trại"
    tasting_available: "Được nếm thử"
    costume_rental: "Thuê trang phục chụp ảnh"
    crowd: "Độ đông"
    noise: "Độ ồn"
    setting: "Trong nhà hay ngoài trời"
    cleanliness: "Sạch sẽ"
    weather_exposed: "Phụ thuộc thời tiết"
    parking: "Gửi xe"
    outdoor_seating: "Chỗ ngồi ngoài trời"
    spacious: "Rộng, thoáng"
    small_space: "Không gian nhỏ"
    toilet: "Nhà vệ sinh"
    mosquitoes: "Nhiều muỗi"
    service_attitude: "Thái độ phục vụ"
    service_quality: "Chất lượng dịch vụ"
    value_for_money: "Đáng tiền"
    tourist_trap: "Chặt chém"
    wait_time: "Thời gian chờ"
    booking_needed: "Cần đặt trước"
    portion_size: "Khẩu phần"
    entry_fee: "Vé vào cửa"
    vegetarian_options: "Món chay"
    cash_only: "Chỉ nhận tiền mặt"
    condition_change: "So với trước đây"
    rough_road_access: "Đường vào xấu"
    steep_or_stairs: "Dốc, nhiều bậc"
    long_walk: "Phải đi bộ xa"
    kids: "Trẻ em"
    elderly: "Người lớn tuổi"
    wheelchair: "Xe lăn"
    couples: "Cặp đôi"
    groups: "Nhóm đông"
  value: {present: "có", absent: "không", good: "tốt", mixed: "lẫn lộn", poor: "kém", low: "vắng", medium: "vừa",
          high: "đông", quiet: "yên tĩnh", moderate: "hơi ồn", loud: "ồn", indoor: "trong nhà", outdoor: "ngoài trời",
          both: "cả hai", clean: "sạch", dirty: "chưa sạch", sheltered: "có mái che", easy: "dễ", hard: "khó",
          none: "không phải chờ", short: "chờ chút", long: "chờ lâu", "yes": "có", "no": "không", generous: "nhiều",
          small: "ít", free: "miễn phí", paid: "có thu phí", declined: "xuống cấp", suitable: "hợp",
          unsuitable: "không hợp"}
```

- [ ] **Step 2: Viết fixture + test hỏng**

`tests/decision/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # fixtures.py next to the tests
```

`tests/decision/fixtures.py`:

```python
"""Serving-record and Search Input builders for decision tests (shape: src/corpus/serving/record.py build())."""

from datetime import date

from corpus.ontology import load

from trip import SearchInput

ONT = load()
MONDAY = date(2026, 12, 14)
ALL_DAY = {d: [["07:00", "22:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


def feat(value, n=3, status="VERIFIED", dist=None, by_context=None, rate=0.1, agreement=1.0):
    return {"value": value, "distribution": dist or {value: n}, "status": status,
            "reason": None if status == "VERIFIED" else "unmeasured_precision", "n": n, "mention_rate": rate,
            "confidence": {"independent_sources": n, "agreement": agreement, "freshness_days": 10,
                           "source_types": ["provider"]},
            "by_context": by_context or {}, "precision": None, "evidence": ["x:1"]}


def srec(fid, name=None, features=None, group="cafe", category="Quán cà phê", lat=11.94, lng=108.44, area="area-1",
         hours=ALL_DAY, hours_status="VERIFIED", usable=("experience", "meal", "backup"), voices=30,
         crowd_by_time=None, price=None, visit=(45, 75, 150), dup=None, entry_fee=None, rating_trend=None):
    rec = {"id": fid, "status": "VERIFIED", "status_reason": None,
           "identity": {"name": name or f"Nơi {fid}", "kind": "POI", "category": category, "category_group": group,
                        "lat": lat, "lng": lng, "address": "Đà Lạt", "area": area},
           "operation": {"hours": {"value": hours, "status": hours_status, "as_of": "2026-09-30"} if hours else None,
                         "price_per_person": {"value": price, "status": "VERIFIED", "as_of": "2026-09-30"} if price else None,
                         "entry_fee": entry_fee,
                         "visit_minutes": {"short": visit[0], "typical": visit[1], "long": visit[2],
                                           "source": "category_default", "n": 0, "kind": "estimate"},
                         "booking": None, "crowd_by_time": crowd_by_time},
           "experience": {}, "environment": {}, "service": {}, "effort": {}, "suitability": {},
           "effort_hint": {"value": "unknown", "kind": "estimate"}, "usable_as": list(usable),
           "provenance": {"as_of": "2026-09-30", "coverage": {}, "voices": voices, "rating_trend": rating_trend,
                          "inputs": []},
           "near_duplicate_group": dup}
    for f, v in (features or {}).items():
        rec[ONT.features[f].group][f] = feat(v) if isinstance(v, str) else v
    return rec


def si(**over) -> SearchInput:
    """A valid Search Input; keyword args replace top-level keys, context / pace / novelty are merged."""
    base = {"ontology_version": ONT.version,
            "context": {"start_date": MONDAY.isoformat(), "month": None, "days": 2, "base": None,
                        "mobility": "motorbike", "companions": [], "people": 2, "arrive_at": None, "leave_at": None,
                        "day_end": None, "budget_vnd": None, "experience": None},
            "hard_filters": [], "anchors": [], "soft_weights": [],
            "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []}
    for k, v in over.items():
        if k in ("context", "pace", "novelty"):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return SearchInput.model_validate(base)


def hard(feature, value, op="ne", policy="exclude"):
    return {"feature": feature, "op": op, "value": value, "unknown_policy": policy}


def love(feature, value="present", weight=1, context=None):
    return {"feature": feature, "value": value, "context": context, "weight": weight, "source": "user"}
```

`tests/decision/test_basics.py`:

```python
from datetime import date

from fixtures import MONDAY, si, srec

from decision.geo import fmt, km, minutes, point, to_min
from decision.model import Cand, role_of, value
from decision.settings import default
from decision.trip_days import month_of, trip_days

CFG = default()


def test_settings_load_every_key():
    assert CFG.per_day["normal"] == 4 and CFG.narrow_buckets == ("early_morning", "evening", "night")
    assert CFG.labels["feature"]["steep_or_stairs"] == "Dốc, nhiều bậc"


def test_geo():
    assert round(km((11.94, 108.44), (11.94, 108.45)), 2) == 1.09
    assert minutes(10, "motorbike", CFG) == 34 and minutes(10, None, CFG) == 34
    assert to_min("07:30") == 450 and fmt(450) == "07:30"
    assert point(srec("A")) == (11.94, 108.44) and point(srec("B", lat=None)) is None


def test_trip_days_windows_and_weekdays():
    days = trip_days(si(context={"days": 3, "arrive_at": "10:00", "leave_at": "14:00"}).context, CFG)
    assert [d.weekday for d in days] == ["mon", "tue", "wed"] and days[0].day_type == "weekday"
    assert (days[0].start, days[1].start, days[1].end, days[2].end) == (600, 480, 1260, 840)
    assert days[0].date == MONDAY


def test_trip_days_without_dates():
    ctx = si(context={"start_date": None, "month": 12, "days": None}).context
    days = trip_days(ctx, CFG)
    assert len(days) == CFG.default_days and days[0].weekday is None and month_of(ctx) == 12


def test_model_helpers():
    r = srec("A", features={"crowd": "high"}, usable=("meal",))
    assert role_of(r) == "meal" and role_of(srec("B", usable=())) is None
    assert value(r, "crowd") == "high" and value(r, "noise") is None
    assert Cand(r, "meal").name == "Nơi A"
```

- [ ] **Step 3: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_basics.py`
Expected: FAIL `ModuleNotFoundError: No module named 'decision'`.

- [ ] **Step 4: Cài đặt**

`src/decision/__init__.py`:

```python
"""Place Decision: Search Input + serving records -> confirmed places (docs/PLACE_DECISION.md)."""
```

`src/decision/settings.py`:

```python
"""Place Decision thresholds (config/decision.yaml)."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "decision.yaml"


@dataclass(frozen=True)
class Settings:
    version: int
    center: dict
    speed_kmh: dict
    road_factor: float
    radius_km: dict
    area_bonus: float
    crowd_busy_pct: int
    crowd_penalty: float
    rainy_months: tuple
    min_context_fit: float
    weights: dict
    price_ref_vnd: int
    near_min: int
    per_day: dict
    per_day_max: dict
    meals_per_day: int
    spare_factor: float
    pool_factor: int
    default_days: int
    day_start: str
    day_end: str
    leave_at: str
    buffer_min: dict
    intra_leg_min: int
    far_km: float
    buckets: dict
    narrow_buckets: tuple
    timed_features: tuple
    timed_share: float
    night_open: str
    infeasible_ratio: float
    budget_slack: float
    far_step: float
    travel_mult_min: float
    price_step: float
    pattern_min: int
    gap_min: int
    rethink_drops: int
    history_max: int
    unverified_show: int
    first_token_s: float
    total_s: float
    display_groups: dict
    polarity: dict
    labels: dict


def load(path: Path = PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for k in ("rainy_months", "narrow_buckets", "timed_features"):
        raw[k] = tuple(raw[k])
    return Settings(**raw)


@cache
def default() -> Settings:
    return load()
```

`src/decision/geo.py`:

```python
"""Rough distances and times: straight line × road factor at a city speed. Never a real route (that is Planning)."""

import math


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def minutes(d_km: float, mobility: str | None, cfg) -> int:
    return max(1, round(d_km * cfg.road_factor / cfg.speed_kmh[mobility or "motorbike"] * 60))


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def point(rec: dict) -> tuple[float, float] | None:
    lat, lng = rec["identity"].get("lat"), rec["identity"].get("lng")
    return None if lat is None or lng is None else (float(lat), float(lng))
```

`src/decision/trip_days.py`:

```python
"""The days of the trip: date, weekday, day type and the usable window of each day (minutes after midnight)."""

from dataclasses import dataclass
from datetime import date, timedelta

from .geo import to_min

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class TripDay:
    index: int
    date: date | None
    weekday: str | None  # None when only the month is known
    day_type: str | None  # weekday | weekend
    start: int
    end: int


def trip_days(ctx, cfg) -> list[TripDay]:
    """ctx: trip.SearchInput.context. Missing days -> cfg.default_days (the caller flags it)."""
    n = ctx.days or cfg.default_days
    start, end = to_min(cfg.day_start), to_min(ctx.day_end or cfg.day_end)
    first = max(start, to_min(ctx.arrive_at)) if ctx.arrive_at else start
    last_end = min(end, to_min(ctx.leave_at or cfg.leave_at))
    out = []
    for i in range(n):
        d = ctx.start_date + timedelta(days=i) if ctx.start_date else None
        wd = DAYS[d.weekday()] if d else None
        out.append(TripDay(i, d, wd, ("weekend" if wd in ("sat", "sun") else "weekday") if wd else None,
                           first if i == 0 else start, last_end if i == n - 1 else end))
    return out


def month_of(ctx) -> int | None:
    return ctx.start_date.month if ctx.start_date else ctx.month
```

`src/decision/model.py`:

```python
"""One candidate place and what each Place Decision step found about it."""

from dataclasses import dataclass, field

from corpus.serving import feature

FIRM = ("VERIFIED", "OUTDATED")


def role_of(rec: dict) -> str | None:
    """experience | meal | None (a place no plan can use, e.g. a scooter rental)."""
    u = rec.get("usable_as") or []
    return "experience" if "experience" in u else "meal" if "meal" in u else None


def value(rec: dict, fid: str) -> str | None:
    """Top value of an ontology feature, or None without evidence."""
    f = feature(rec, fid)
    return f["value"] if f else None


@dataclass
class Cand:
    rec: dict
    role: str  # experience | meal
    keep: bool = False  # anchor, chosen or locked: never dropped silently
    missing: bool = False  # kept place that has no serving record
    status: str = "main"  # main | unverified | excluded
    checks: list[dict] = field(default_factory=list)  # {kind, feature, value, op, result, reason, policy}
    warnings: list[str] = field(default_factory=list)  # codes, see cards.WARNING
    fit: float = 0.0
    flags: list[dict] = field(default_factory=list)  # {code, text, sid}
    km: float | None = None
    minutes: int | None = None
    center: str = ""
    parts: dict = field(default_factory=dict)
    score: float = 0.0
    matches: list[tuple] = field(default_factory=list)  # (feature, value, contribution, n)

    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def name(self) -> str:
        return self.rec["identity"].get("name") or self.rec["id"]
```

- [ ] **Step 5: Chạy lại**

Run: `python -m pytest -q tests/decision/test_basics.py`
Expected: PASS (5 test).

- [ ] **Step 6: Commit**

```bash
git add config/decision.yaml src/decision tests/decision
git commit -m "feat(decision): module skeleton, settings, rough geo and trip days"
```

---

### Task 3: ③ Sàng lọc

**Files:**
- Create: `src/decision/screen.py`
- Test: `tests/decision/test_screen.py`

**Interfaces:**
- Consumes: `Cand`, `FIRM` (Task 2), `TripDay`, `trip_days` (Task 2), `corpus.serving.check`, `corpus.serving.feature`.
- Produces: `hard_result(rec, h) -> tuple[str, str | None]`; `closed_all_days(rec, days) -> bool`; `screen(c: Cand, si, days, relaxed: set[tuple[str, str]]) -> None` (điền `c.status`, `c.checks`, `c.warnings`). Mã cảnh báo: `hours_unknown`, `hours_outdated`, `uncertain_value:<feature>`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_screen.py`:

```python
from fixtures import feat, hard, si, srec

from decision.model import Cand
from decision.screen import closed_all_days, hard_result, screen
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()


def h(feature, value, op="ne", policy="exclude"):
    return si(hard_filters=[hard(feature, value, op, policy)]).hard_filters[0]


def test_ne_uses_fail_closed_check():
    assert hard_result(srec("A", features={"steep_or_stairs": "absent"}), h("steep_or_stairs", "present"))[0] == "pass"
    assert hard_result(srec("A", features={"steep_or_stairs": "present"}), h("steep_or_stairs", "present"))[0] == "fail"
    assert hard_result(srec("A"), h("steep_or_stairs", "present"))[0] == "unknown"


def test_eq_needs_a_firm_undisputed_value():
    ok = srec("A", features={"setting": "indoor"})
    disputed = srec("B", features={"setting": feat("indoor", dist={"indoor": 3, "outdoor": 1})})
    assert hard_result(ok, h("setting", "indoor", "eq"))[0] == "pass"
    assert hard_result(disputed, h("setting", "indoor", "eq"))[0] == "unknown"
    assert hard_result(srec("C", features={"setting": "outdoor"}), h("setting", "indoor", "eq"))[0] == "fail"


def test_uncertain_value_passes_with_warning_only_outside_safety_groups():
    noise = srec("A", features={"noise": feat("quiet", status="UNCERTAIN")})
    steep = srec("B", features={"steep_or_stairs": feat("absent", status="UNCERTAIN")})
    assert hard_result(noise, h("noise", "loud")) == ("pass", "uncertain_value")
    assert hard_result(steep, h("steep_or_stairs", "present")) == ("unknown", None)


def test_closed_every_trip_day_is_physical_and_needs_known_weekdays():
    mon_tue_closed = {"wed": [["08:00", "17:00"]]}
    days = trip_days(si(context={"days": 2}).context, CFG)  # Monday, Tuesday
    assert closed_all_days(srec("A", hours=mon_tue_closed), days)
    no_dates = trip_days(si(context={"start_date": None, "month": 12}).context, CFG)
    assert not closed_all_days(srec("A", hours=mon_tue_closed), no_dates)
    assert not closed_all_days(srec("A", hours=mon_tue_closed, hours_status="OUTDATED"), days)


def test_screen_statuses_relax_and_warnings():
    s = si(hard_filters=[hard("steep_or_stairs", "present"), hard("noise", "loud")])
    days = trip_days(s.context, CFG)
    good = Cand(srec("G", features={"steep_or_stairs": "absent", "noise": feat("quiet", status="UNCERTAIN")}), "experience")
    bad = Cand(srec("X", features={"steep_or_stairs": "present", "noise": "quiet"}), "experience")
    unk = Cand(srec("U", features={"noise": "quiet"}, hours=None), "experience")
    for c in (good, bad, unk):
        screen(c, s, days, set())
    assert (good.status, bad.status, unk.status) == ("main", "excluded", "unverified")
    assert "uncertain_value:noise" in good.warnings and "hours_unknown" in unk.warnings
    screen(bad, s, days, {("X", "steep_or_stairs")})
    assert bad.status == "main" and [c["feature"] for c in bad.checks if c["kind"] == "hard"] == ["noise"]
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_screen.py`
Expected: FAIL `ModuleNotFoundError: No module named 'decision.screen'`.

- [ ] **Step 3: Cài đặt**

`src/decision/screen.py`:

```python
"""③ Constraint screen (docs/PLACE_DECISION.md §6): physical first, then each hard filter, pass | fail | unknown."""

from functools import cache

from corpus.ontology import load
from corpus.serving import check, feature

from .model import FIRM, Cand

SAFETY = {"effort", "suitability"}  # access / safety: an UNCERTAIN value is never a pass here


@cache
def _ontology():
    return load()


def hard_result(rec: dict, h) -> tuple[str, str | None]:
    """(pass | fail | unknown, warning code) for one trip.HardFilter."""
    f = feature(rec, h.feature)
    if h.op == "eq":
        if f is None or f["status"] not in FIRM:
            return "unknown", None
        if f["value"] != h.value:
            return "fail", None
        return ("pass", None) if set(f["distribution"]) <= {h.value} else ("unknown", None)
    r = check(rec, h.feature, h.value)
    if (r == "unknown" and f is not None and f["status"] == "UNCERTAIN" and f["value"] != h.value
            and h.value not in f["distribution"] and _ontology().features[h.feature].group not in SAFETY):
        return "pass", "uncertain_value"
    return r, None


def closed_all_days(rec: dict, days) -> bool:
    """True only when the weekdays are known and VERIFIED hours open on none of them."""
    hours = rec["operation"].get("hours")
    if not hours or hours["status"] != "VERIFIED" or not hours["value"] or any(d.weekday is None for d in days):
        return False
    return all(not hours["value"].get(d.weekday) for d in days)


def screen(c: Cand, si, days, relaxed: set[tuple[str, str]]) -> None:
    checks, warnings = [], []
    hours = c.rec["operation"].get("hours")
    if not hours:
        warnings.append("hours_unknown")
    elif hours["status"] == "OUTDATED":
        warnings.append("hours_outdated")
    if closed_all_days(c.rec, days):
        checks.append({"kind": "physical", "feature": "hours", "value": None, "op": None, "result": "fail",
                       "reason": "closed_all_trip_days", "policy": None})
    for h in si.hard_filters:
        if (c.id, h.feature) in relaxed:
            continue
        r, warn = hard_result(c.rec, h)
        if warn:
            warnings.append(f"{warn}:{h.feature}")
        checks.append({"kind": "hard", "feature": h.feature, "value": h.value, "op": h.op, "result": r,
                       "reason": f"hard:{h.feature}", "policy": h.unknown_policy})
    results = {x["result"] for x in checks}
    c.checks, c.warnings = checks, warnings
    c.status = "excluded" if "fail" in results else "unverified" if "unknown" in results else "main"
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_screen.py`
Expected: PASS (5 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/screen.py tests/decision/test_screen.py
git commit -m "feat(decision): fail-closed constraint screen with relax per place"
```

---

### Task 4: ④ Hợp bối cảnh

**Files:**
- Create: `src/decision/fit.py`
- Test: `tests/decision/test_fit.py`

**Interfaces:**
- Consumes: `Cand`, `value` (Task 2), `km`, `minutes`, `point` (Task 2), `month_of` (Task 2), `Profile` — Task 8 định nghĩa; ở task này `fit()` chỉ đọc `profile.travel_mult` và `profile.crowd_tolerance`, test truyền `SimpleNamespace`.
- Produces: `centers(si, by_id: dict, cfg) -> list[tuple[str, tuple[float,float]]]` (phần tử đầu là base hoặc tâm Đà Lạt, sau đó các anchor); `radius(si, profile, cfg) -> float`; `fit(c, si, days, ctrs, anchor_areas: set[str], profile, cfg) -> None` (điền `c.fit`, `c.flags`, `c.km`, `c.minutes`, `c.center`). Mã cờ: `crowded`, `rain`, `rough_road`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_fit.py`:

```python
from types import SimpleNamespace

from fixtures import si, srec

from decision.fit import centers, fit, radius
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
P = SimpleNamespace(travel_mult=1.0, crowd_tolerance=None)
BUSY = {"weekday": {"morning": 80, "noon": 40, "afternoon": 30, "evening": 20, "night": 10},
        "weekend": {"morning": 95, "noon": 60, "afternoon": 50, "evening": 40, "night": 20}}


def run(c, s, profile=P, anchor_areas=frozenset()):
    by_id = {c.id: c.rec}
    fit(c, s, trip_days(s.context, CFG), centers(s, by_id, CFG), set(anchor_areas), profile, CFG)
    return c


def test_centers_base_then_anchors_else_city_center():
    base, anc = srec("B", lat=11.95, lng=108.45), srec("A", lat=11.90, lng=108.40)
    s = si(context={"base": {"place_id": "B", "text": "ks"}}, anchors=[{"place_id": "A", "priority": "must"}])
    assert [n for n, _ in centers(s, {"B": base, "A": anc}, CFG)] == ["Nơi B", "Nơi A"]
    assert centers(si(), {}, CFG)[0][0] == "trung tâm Đà Lạt"


def test_distance_and_radius_shrink_with_travel_tolerance():
    near = run(Cand(srec("N", lat=11.9404, lng=108.4583), "experience"), si())
    far = run(Cand(srec("F", lat=12.03, lng=108.4583), "experience"), si())
    assert near.fit == 1.0 and near.minutes == 1 and near.center == "trung tâm Đà Lạt"
    assert 0 < far.fit < 0.5
    assert radius(si(pace={"max_leg_min": 20}), P, CFG) < radius(si(), P, CFG)
    assert radius(si(), SimpleNamespace(travel_mult=0.5, crowd_tolerance=None), CFG) == CFG.radius_km["motorbike"] / 2


def test_crowd_penalty_only_when_avoiding_and_day_type_known():
    rec = srec("C", lat=11.9404, lng=108.4583, crowd_by_time=BUSY)
    c = run(Cand(rec, "experience"), si(pace={"crowd_tolerance": "avoid"}))
    assert c.fit == 1.0 - CFG.crowd_penalty and c.flags[0]["code"] == "crowded"
    no_dates = run(Cand(rec, "experience"), si(context={"start_date": None, "month": 12}, pace={"crowd_tolerance": "avoid"}))
    assert no_dates.fit == 1.0 and no_dates.flags[0]["code"] == "crowded"
    assert run(Cand(rec, "experience"), si()).flags == []


def test_area_bonus_rain_and_rough_road_flags():
    rec = srec("R", lat=12.02, features={"weather_exposed": "present", "rough_road_access": "present"}, area="area-9")
    s = si(context={"start_date": "2026-07-06", "mobility": "ride"})
    c = run(Cand(rec, "experience"), s, anchor_areas={"area-9"})
    plain = run(Cand(srec("R2", lat=12.02, area="area-1"), "experience"), s)
    assert round(c.fit - plain.fit, 3) == CFG.area_bonus
    assert {f["code"] for f in c.flags} == {"rain", "rough_road"}
    assert any("xe công nghệ" in f["text"] for f in c.flags)
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_fit.py`
Expected: FAIL `No module named 'decision.fit'`.

- [ ] **Step 3: Cài đặt**

`src/decision/fit.py`:

```python
"""④ Context fit (docs/PLACE_DECISION.md §7): rough, cheap, before the shortlist; no route service."""

from .geo import km, minutes, point
from .model import Cand, value
from .trip_days import month_of

DAYTIME = ("morning", "noon", "afternoon", "evening")


def centers(si, by_id: dict, cfg) -> list[tuple[str, tuple[float, float]]]:
    """Base (when resolved) or the city center first, then every anchor that has a location."""
    out = []
    base = si.context.base
    if base and base.place_id and (r := by_id.get(base.place_id)) and point(r):
        out.append((r["identity"]["name"], point(r)))
    if not out:
        out.append((cfg.center["name"], (cfg.center["lat"], cfg.center["lng"])))
    for a in si.anchors:
        r = by_id.get(a.place_id)
        if r and point(r):
            out.append((r["identity"]["name"], point(r)))
    return out


def radius(si, profile, cfg) -> float:
    mob = si.context.mobility or "motorbike"
    r = cfg.radius_km[mob] * profile.travel_mult
    if si.pace.max_leg_min:
        r = min(r, si.pace.max_leg_min * cfg.speed_kmh[mob] / 60 / cfg.road_factor)
    return r


def fit(c: Cand, si, days, ctrs, anchor_areas: set[str], profile, cfg) -> None:
    t = cfg.labels["time"]
    mob = si.context.mobility
    flags = []
    p = point(c.rec)
    dist = 0.0
    if p:
        name, d = min(((n, km(p, q)) for n, q in ctrs), key=lambda x: x[1])
        c.km, c.minutes, c.center = round(d, 1), minutes(d, mob, cfg), name
        dist = 1 - min(1.0, d / radius(si, profile, cfg))
    area = cfg.area_bonus if c.rec["identity"].get("area") in anchor_areas else 0.0
    crowd = 0.0
    cbt = c.rec["operation"].get("crowd_by_time")
    if (profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid" and cbt:
        known = sorted({d.day_type for d in days if d.day_type})
        busy = [(dt, b) for dt in (known or ["weekday", "weekend"]) for b in DAYTIME
                if (cbt.get(dt) or {}).get(b, 0) >= cfg.crowd_busy_pct]
        if busy:
            dt, b = busy[0]
            flags.append({"code": "crowded", "text": f"Đông {t[b]} {t[dt]} (Google)", "sid": None})
            if known:
                crowd = -cfg.crowd_penalty
    m = month_of(si.context)
    exposed = value(c.rec, "weather_exposed") == "present"
    if m in cfg.rainy_months and (exposed or value(c.rec, "setting") == "outdoor"):
        flags.append({"code": "rain", "text": f"Ngoài trời, tháng {m} hay mưa: cần phương án dự phòng",
                      "sid": "weather_exposed" if exposed else "setting"})
    if value(c.rec, "rough_road_access") == "present":
        flags.append({"code": "rough_road", "sid": "rough_road_access",
                      "text": "Đường vào xấu, xe công nghệ khó vào" if mob == "ride" else "Đường vào xấu, đi xe cẩn thận"})
    c.flags = flags
    c.fit = round(max(0.0, min(1.0, dist + area + crowd)), 4)
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_fit.py`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/fit.py tests/decision/test_fit.py
git commit -m "feat(decision): rough context fit with crowd, rain and road flags"
```

---

### Task 5: ⑤ Xếp hạng

**Files:**
- Create: `src/decision/rank.py`
- Test: `tests/decision/test_rank.py`

**Interfaces:**
- Consumes: `Cand` (Task 2), `corpus.serving.feature`; `profile` có `soft` (list phần tử có `.feature .value .weight`), `visited`, `price_sensitivity` (Task 8 định nghĩa `Profile`; test dùng `SimpleNamespace`).
- Produces: `conf(f) -> float`; `wants(si, profile) -> list[tuple[str, str, dict|None, int]]`; `preference(rec, ws) -> tuple[float, float, list[tuple]]`; `score(cands: list[Cand], si, profile, cfg) -> None` (điền `c.parts` với key `ctx pref nov exp pop unc price`, `c.score`, `c.matches` giảm dần theo đóng góp).

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_rank.py`:

```python
from types import SimpleNamespace

from fixtures import feat, love, si, srec

from decision.model import Cand
from decision.rank import conf, preference, score, wants
from decision.settings import default

CFG = default()


def prof(**kw):
    return SimpleNamespace(**{"soft": [], "visited": [], "price_sensitivity": 0.0, **kw})


def test_conf_scales_with_authors_agreement_and_status():
    assert conf(feat("present", n=3)) == 1.0
    assert conf(feat("present", n=1)) == 1 / 3
    assert conf(feat("present", n=3, status="UNCERTAIN", agreement=0.8)) == 0.4


def test_preference_matches_context_and_counts_missing_wanted_features():
    s = si(soft_weights=[love("crowd", "low", context={"time_of_day": "morning"}), love("scenic_view")])
    rec = srec("A", features={"crowd": feat("high", by_context={"time_of_day=morning": {"low": 3, "high": 1}})})
    pref, unc, matches = preference(rec, wants(s, prof()))
    assert pref == 0.5 and unc == 0.5 and matches[0][:2] == ("crowd", "low")


def test_avoid_weight_is_negative_and_profile_soft_counts():
    s = si(soft_weights=[love("live_music", weight=-1)])
    p = prof(soft=[SimpleNamespace(feature="scenic_view", value="present", weight=1)])
    pref, _, _ = preference(srec("A", features={"live_music": "present", "scenic_view": "present"}), wants(s, p))
    assert pref == 0.0


def test_score_parts_novelty_experience_price():
    a = Cand(srec("A", voices=100, price={"min_vnd": 300000, "max_vnd": 300000}), "experience")
    b = Cand(srec("B", voices=10), "experience")
    a.fit = b.fit = 1.0
    s = si(context={"experience": "first"}, novelty={"level": "new", "visited": ["A"]})
    score([a, b], s, prof(price_sensitivity=1.0), CFG)
    assert a.parts["nov"] == -1.0 and b.parts["nov"] == 0.0
    assert a.parts["pop"] == 1.0 and b.parts["pop"] == 0.0 and a.parts["exp"] == 1.0
    assert a.parts["price"] == -1.0
    assert a.score == round(sum(CFG.weights[k] * v for k, v in a.parts.items()), 4)
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_rank.py`
Expected: FAIL `No module named 'decision.rank'`.

- [ ] **Step 3: Cài đặt**

`src/decision/rank.py`:

```python
"""⑤ Ranking (docs/PLACE_DECISION.md §8). Every part is kept on the candidate to explain and debug the score."""

from bisect import bisect_left

from corpus.serving import feature

from .model import Cand

STATUS_W = {"VERIFIED": 1.0, "OUTDATED": 0.7, "UNCERTAIN": 0.5}
FULL_N = 3  # authors for full confidence in a feature


def conf(f: dict) -> float:
    return f["confidence"]["agreement"] * min(1.0, f["n"] / FULL_N) * STATUS_W[f["status"]]


def wants(si, profile) -> list[tuple[str, str, dict | None, int]]:
    """(feature, value, context, weight) the ranking looks for: Search Input, then the session's own additions."""
    out = [(w.feature, w.value, w.context, w.weight) for w in si.soft_weights if w.weight != 0]
    return out + [(s.feature, s.value, None, s.weight) for s in profile.soft]


def _contextual(f: dict, ctx: dict | None) -> str:
    for k, v in (ctx or {}).items():
        d = f["by_context"].get(f"{k}={v}")
        if d:
            return max(d, key=d.get)
    return f["value"]


def preference(rec: dict, ws) -> tuple[float, float, list[tuple]]:
    """(preference fit, uncertainty, matches). No evidence adds 0, never a minus; it counts as uncertainty."""
    total = sum(abs(w) for *_, w in ws)
    if not total:
        return 0.0, 0.0, []
    fit = missing = 0.0
    matches = []
    for fid, val, ctx, w in ws:
        f = feature(rec, fid)
        if (f is None or f["status"] == "UNCERTAIN") and w > 0:
            missing += w
        if f is None:
            continue
        if _contextual(f, ctx) == val:
            contrib = w * conf(f)
            fit += contrib
            matches.append((fid, val, round(contrib, 4), f["n"]))
    return fit / total, missing / total, matches


def _price_norm(rec: dict, cfg) -> float:
    p = rec["operation"].get("price_per_person")
    if not p:
        return 0.0
    v = p["value"]
    lo = v.get("min_vnd") or 0
    mid = (lo + (v.get("max_vnd") or lo)) / 2
    return min(1.0, mid / cfg.price_ref_vnd)


def score(cands: list[Cand], si, profile, cfg) -> None:
    ws = wants(si, profile)
    voices = sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
    top = max(1, len(voices) - 1)
    visited = set(si.novelty.visited) | set(profile.visited)
    nov_of = {"new": -1.0, "familiar": 0.3}
    for c in cands:
        pref, unc, matches = preference(c.rec, ws)
        pop = min(1.0, bisect_left(voices, c.rec["provenance"].get("voices") or 0) / top)
        exp = si.context.experience
        c.parts = {"ctx": c.fit, "pref": round(pref, 4),
                   "nov": nov_of.get(si.novelty.level, 0.0) if c.id in visited else 0.0,
                   "exp": pop if exp == "first" else 1 - pop if exp == "returning" else 0.0,
                   "pop": round(pop, 4), "unc": -round(unc, 4),
                   "price": -round(profile.price_sensitivity * _price_norm(c.rec, cfg), 4)}
        c.score = round(sum(cfg.weights[k] * v for k, v in c.parts.items()), 4)
        c.matches = sorted(matches, key=lambda m: (-m[2], m[0]))
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_rank.py`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/rank.py tests/decision/test_rank.py
git commit -m "feat(decision): ranking with stored score parts"
```

---
### Task 6: Thẻ ứng viên (template) và ⑥ Đa dạng

**Files:**
- Create: `src/decision/cards.py`, `src/decision/diversify.py`
- Test: `tests/decision/test_cards.py`, `tests/decision/test_diversify.py`

**Interfaces:**
- Consumes: `Cand`, `FIRM`, `value` (Task 2), `corpus.serving.feature`, `corpus.serving.mmr`.
- Produces:
  - `cards.feature_label(fid, cfg) -> str`, `cards.value_label(v, cfg) -> str`, `cards.phrase(fid, val, cfg) -> str`, `cards.warning_text(code, cfg) -> str`, `cards.price_text(rec) -> str | None`.
  - `cards.card(c, si, cfg, *, wanted=(), chosen=False, locked=False, anchor=False, alternatives=(), suggested=False, group="") -> dict` với key: `id name category area role group status score parts why tradeoffs visit location price confidence declined depends_on_unknown warnings unverified failed chosen locked anchor alternatives suggested`. `why`/`tradeoffs`: list `{text, sid}`; `confidence`: `{level: high|medium|low, reason}`; `alternatives`: list `{id, name}`.
  - `diversify.display_group(c, cfg) -> str` (`meal` hoặc key của `cfg.display_groups`, mặc định `sights`); `diversify.sizes(si, days_n, n_anchor_exp, cfg) -> {"experience": int, "meal": int}`; `diversify.pick(pool, k, cfg) -> tuple[list[Cand], dict[str, list[Cand]]]` (đại diện, phương án thay thế theo id đại diện, tối đa 3).

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_cards.py`:

```python
from fixtures import feat, si, srec

from decision.cards import card, phrase, price_text
from decision.model import Cand
from decision.settings import default

CFG = default()


def cand(rec, **kw):
    c = Cand(rec, "experience")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_why_comes_from_matches_anchor_and_nearness():
    c = cand(srec("A"), matches=[("scenic_view", "present", 1.0, 7), ("crowd", "low", 0.5, 4)], minutes=8,
             center="trung tâm Đà Lạt")
    got = card(c, si(), CFG, anchor=True)["why"]
    assert [w["text"] for w in got] == ["Nơi bạn muốn đến", "View đẹp, 7 người nhắc", "Độ đông: vắng, 4 người nhắc"]
    assert got[1]["sid"] == "scenic_view"
    near = card(cand(srec("B"), minutes=8, center="trung tâm Đà Lạt"), si(), CFG)["why"]
    assert near == [{"text": "Gần trung tâm Đà Lạt, ≈8 phút (ước tính)", "sid": None}]


def test_tradeoffs_flags_avoided_matches_and_bad_firm_values():
    rec = srec("A", features={"noise": feat("loud", n=5), "parking": feat("hard", n=1)})
    c = cand(rec, flags=[{"code": "rain", "text": "Ngoài trời", "sid": "setting"}],
             matches=[("live_music", "present", -1.0, 3)])
    texts = [t["text"] for t in card(c, si(), CFG)["tradeoffs"]]
    assert texts == ["Ngoài trời", "Nhạc sống, điều bạn muốn tránh", "Độ ồn: ồn, theo 5 người"]


def test_confidence_levels_follow_wanted_features():
    rec = srec("A", voices=50, features={"scenic_view": "present", "noise": feat("quiet", status="UNCERTAIN")})
    assert card(cand(rec), si(), CFG, wanted=["scenic_view"])["confidence"]["level"] == "high"
    assert card(cand(rec), si(), CFG, wanted=["scenic_view", "noise"])["confidence"]["level"] == "medium"
    low = card(cand(rec), si(), CFG, wanted=["hiking", "noise", "scenic_view"])["confidence"]
    assert low["level"] == "low" and "chưa có bằng chứng về leo núi, trekking" in low["reason"]
    assert card(cand(rec), si(), CFG)["confidence"]["level"] == "high"  # nothing wanted: by voices


def test_price_unknown_budget_warnings_failed_and_declined():
    rec = srec("A", price={"min_vnd": 100000, "max_vnd": 200000}, rating_trend={"direction": "falling"})
    c = cand(rec, warnings=["hours_outdated", "uncertain_value:noise"],
             checks=[{"kind": "hard", "feature": "steep_or_stairs", "value": "present", "op": "ne", "result": "fail",
                      "reason": "hard:steep_or_stairs", "policy": "exclude"},
                     {"kind": "hard", "feature": "long_walk", "value": "present", "op": "ne", "result": "unknown",
                      "reason": "hard:long_walk", "policy": "flag"}])
    got = card(c, si(unknowns=["budget_vnd"]), CFG)
    assert price_text(rec) == "100k–200k/người"
    assert got["depends_on_unknown"] == "Chưa biết ngân sách của bạn; giá khoảng 100k–200k/người"
    assert got["warnings"] == ["Giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến", "Độ ồn: chưa xác nhận chắc"]
    assert got["failed"] == ["Dốc, nhiều bậc: có"] and got["unverified"] == ["Chưa xác minh được: phải đi bộ xa"]
    assert got["declined"] is True and phrase("crowd", "high", CFG) == "Độ đông: đông"


def test_missing_record_card():
    c = Cand(srec("Z", name=None, hours=None, voices=0), "experience", keep=True, missing=True)
    got = card(c, si(), CFG)
    assert got["confidence"]["level"] == "low" and "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)" in got["warnings"]
```

`tests/decision/test_diversify.py`:

```python
from fixtures import si, srec

from decision.diversify import display_group, pick, sizes
from decision.model import Cand
from decision.settings import default

CFG = default()


def c(fid, score, dup=None, group="cafe", role="experience"):
    x = Cand(srec(fid, dup=dup, group=group), role)
    x.score = score
    return x


def test_sizes_follow_days_pace_and_anchors():
    assert sizes(si(), 2, 1, CFG) == {"experience": 12, "meal": 7}
    assert sizes(si(pace={"level": "slow"}), 1, 5, CFG)["experience"] == 2  # never below one slot


def test_display_group():
    assert display_group(c("A", 1, role="meal"), CFG) == "meal"
    assert display_group(c("A", 1, group="garden_farm"), CFG) == "nature"
    assert display_group(c("A", 1, group="cafe"), CFG) == "chill"
    assert display_group(c("A", 1, group="unheard"), CFG) == "sights"


def test_pick_one_per_near_duplicate_group_rest_are_alternatives():
    a, b, cc, d = c("A", 3.0, dup=1), c("B", 2.0, dup=1), c("C", 1.5), c("D", 1.0)
    reps, alts = pick([d, cc, b, a], 2, CFG)
    assert [r.id for r in reps] == ["A", "C"] and [x.id for x in alts["A"]] == ["B"]
    assert pick([a], 0, CFG) == ([], {})
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_cards.py tests/decision/test_diversify.py`
Expected: FAIL `No module named 'decision.cards'` / `'decision.diversify'`.

- [ ] **Step 3: Cài đặt**

`src/decision/cards.py`:

```python
"""Candidate cards (docs/PLACE_DECISION.md §11) from templates: every line comes from a serving record field or a
rule result, so a card cannot say what the data does not hold."""

from corpus.serving import feature

from .model import FIRM, Cand, value

WARNING = {"hours_unknown": "Chưa có giờ mở cửa",
           "hours_outdated": "Giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến",
           "missing_record": "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)"}


def feature_label(fid: str, cfg) -> str:
    return cfg.labels["feature"].get(fid, fid.replace("_", " "))


def value_label(v: str, cfg) -> str:
    return cfg.labels["value"].get(v, v)


def phrase(fid: str, val: str, cfg) -> str:
    return feature_label(fid, cfg) if val == "present" else f"{feature_label(fid, cfg)}: {value_label(val, cfg)}"


def warning_text(code: str, cfg) -> str:
    if code.startswith("uncertain_value:"):
        return f"{feature_label(code.split(':', 1)[1], cfg)}: chưa xác nhận chắc"
    return WARNING.get(code, code)


def price_text(rec: dict) -> str | None:
    p = rec["operation"].get("price_per_person")
    lo = p["value"].get("min_vnd") if p else None
    if lo is None:
        return None
    hi = p["value"].get("max_vnd") or lo
    return f"{lo // 1000}k/người" if hi == lo else f"{lo // 1000}k–{hi // 1000}k/người"


def _why(c: Cand, anchor: bool, cfg) -> list[dict]:
    out = [{"text": "Nơi bạn muốn đến", "sid": None}] if anchor else []
    out += [{"text": f"{phrase(f, v, cfg)}, {n} người nhắc", "sid": f} for f, v, contrib, n in c.matches if contrib > 0]
    if c.minutes is not None and c.minutes <= cfg.near_min:
        out.append({"text": f"Gần {c.center}, ≈{c.minutes} phút (ước tính)", "sid": None})
    return out[:3]


def _tradeoffs(c: Cand, cfg) -> list[dict]:
    out = [{"text": f["text"], "sid": f["sid"]} for f in c.flags]
    out += [{"text": f"{phrase(f, v, cfg)}, điều bạn muốn tránh", "sid": f} for f, v, contrib, _ in c.matches
            if contrib < 0]
    seen = {x["sid"] for x in out if x["sid"]}
    for fid, order in cfg.polarity.items():
        f = feature(c.rec, fid)
        if fid in seen or not f or f["status"] not in FIRM or f["n"] < 2 or f["value"] != order[-1]:
            continue
        out.append({"text": f"{phrase(fid, f['value'], cfg)}, theo {f['n']} người", "sid": fid})
    return out[:3]


def _confidence(c: Cand, wanted, cfg) -> dict:
    if c.missing:
        return {"level": "low", "reason": "Chưa có dữ liệu về nơi này."}
    voices = c.rec["provenance"].get("voices") or 0
    wanted = list(dict.fromkeys(wanted))
    missing = [f for f in wanted if feature(c.rec, f) is None]
    shaky = [f for f in wanted if (x := feature(c.rec, f)) and x["status"] != "VERIFIED"]
    reason = f"{voices} người đã viết về nơi này"
    if missing:
        reason += "; chưa có bằng chứng về " + ", ".join(feature_label(f, cfg).lower() for f in missing)
    if shaky:
        reason += "; chưa chắc: " + ", ".join(feature_label(f, cfg).lower() for f in shaky)
    if not wanted:
        level = "high" if voices >= 40 else "medium" if voices >= 10 else "low"
    else:
        bad = len(missing) + len(shaky)
        level = "high" if bad == 0 else "low" if bad * 2 > len(wanted) else "medium"
    return {"level": level, "reason": reason + "."}


def _fail_text(x: dict, cfg) -> str:
    if x["kind"] == "physical":
        return "Đóng cửa mọi ngày của chuyến"
    if x["op"] == "eq":
        return f"{feature_label(x['feature'], cfg)}: không phải {value_label(x['value'], cfg)}"
    return f"{feature_label(x['feature'], cfg)}: {value_label(x['value'], cfg)}"


def card(c: Cand, si, cfg, *, wanted=(), chosen=False, locked=False, anchor=False, alternatives=(), suggested=False,
         group="") -> dict:
    rec = c.rec
    vm = rec["operation"].get("visit_minutes")
    price = price_text(rec)
    trend = (rec["provenance"].get("rating_trend") or {}).get("direction")
    return {
        "id": c.id, "name": c.name, "category": rec["identity"].get("category"), "area": rec["identity"].get("area"),
        "role": c.role, "group": group, "status": c.status, "score": c.score, "parts": c.parts,
        "why": _why(c, anchor, cfg), "tradeoffs": _tradeoffs(c, cfg),
        "visit": {k: vm.get(k) for k in ("short", "typical", "long", "source")} if vm else None,
        "location": {"center": c.center, "km": c.km, "minutes": c.minutes},
        "price": price,
        "confidence": _confidence(c, wanted, cfg),
        "declined": value(rec, "condition_change") == "declined" or trend == "falling",
        "depends_on_unknown": f"Chưa biết ngân sách của bạn; giá khoảng {price}"
        if price and "budget_vnd" in si.unknowns else None,
        "warnings": [warning_text(w, cfg) for w in c.warnings] + ([WARNING["missing_record"]] if c.missing else []),
        "unverified": [f"Chưa xác minh được: {feature_label(x['feature'], cfg).lower()}" for x in c.checks
                       if x["result"] == "unknown"],
        "failed": [_fail_text(x, cfg) for x in c.checks if x["result"] == "fail"],
        "chosen": chosen, "locked": locked, "anchor": anchor,
        "alternatives": [{"id": i, "name": n} for i, n in alternatives], "suggested": suggested,
    }
```

`src/decision/diversify.py`:

```python
"""⑥ Diversity and shortlist size (docs/PLACE_DECISION.md §9): one representative per near-duplicate group, picked by
MMR; the group's other places become its alternatives."""

import math

from corpus.serving import mmr

from .model import Cand


def display_group(c: Cand, cfg) -> str:
    if c.role == "meal":
        return "meal"
    g = c.rec["identity"].get("category_group")
    return next((k for k, gs in cfg.display_groups.items() if g in gs), "sights")


def sizes(si, days_n: int, n_anchor_exp: int, cfg) -> dict[str, int]:
    pace = si.pace.level or "normal"
    exp = max(1, days_n * cfg.per_day[pace] - n_anchor_exp)
    return {"experience": math.ceil(exp * cfg.spare_factor),
            "meal": math.ceil(days_n * cfg.meals_per_day * cfg.spare_factor)}


def pick(pool: list[Cand], k: int, cfg) -> tuple[list[Cand], dict[str, list[Cand]]]:
    if k <= 0 or not pool:
        return [], {}
    ranked = sorted(pool, key=lambda c: (-c.score, c.id))
    head = ranked[: k * cfg.pool_factor]
    order = mmr([c.rec for c in head], {c.id: c.score for c in head}, min(len(head), 2 * k))
    by = {c.id: c for c in pool}
    reps, alts, leader = [], {}, {}
    for i in order:
        g = by[i].rec.get("near_duplicate_group")
        if g is not None and g in leader:
            continue
        if len(reps) < k:
            reps.append(by[i])
            if g is not None:
                leader[g] = i
    for c in ranked:
        g = c.rec.get("near_duplicate_group")
        if g in leader and c.id != leader[g]:
            alts.setdefault(leader[g], []).append(c)
    return reps, {i: v[:3] for i, v in alts.items()}
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_cards.py tests/decision/test_diversify.py`
Expected: PASS (8 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/cards.py src/decision/diversify.py tests/decision/test_cards.py tests/decision/test_diversify.py
git commit -m "feat(decision): template cards and MMR shortlist with near-duplicate alternatives"
```

---

### Task 7: ⑨ Khả thi tổ hợp (gồm khung giờ từ corpus)

**Files:**
- Create: `src/decision/feasibility.py`
- Test: `tests/decision/test_feasibility.py`

**Interfaces:**
- Consumes: `Cand` (Task 2), `km`, `minutes`, `point`, `to_min`, `fmt` (Task 2), `feature_label`, `value_label` (Task 6), `corpus.serving.feature`.
- Produces:
  - `need_buckets(c, wanted_timed: set[str], is_anchor: bool, days, cfg) -> frozenset[str] | None`
  - `supply(days, arrive: int | None, cfg) -> dict[str, int]`
  - `evaluate(chosen: list[Cand], si, days, known_days: bool, anchors: set[str], locked: set[str], ctrs, wanted_timed: set[str], cfg) -> dict` với key `status` (`feasible|partial|infeasible|unknown`), `known_days`, `totals{places, visit, buffer, travel, needed, available}`, `slack` (int hoặc None), `conflicts` (list `{id, check, physical, title, rule, places, fixes[{label, effect, action}]}`), `warnings` (list str).

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_feasibility.py`:

```python
from fixtures import feat, si, srec

from decision.feasibility import evaluate, need_buckets, supply
from decision.fit import centers
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
CLOUD = feat("present", n=6, by_context={"time_of_day=early_morning": {"present": 5}, "time_of_day=morning": {"present": 1}})


def cands(*recs, score=0.0):
    out = []
    for i, r in enumerate(recs):
        c = Cand(r, "meal" if r["usable_as"] == ["meal"] else "experience")
        c.score = score + i
        out.append(c)
    return out


def run(chosen, s, anchors=(), locked=(), wanted_timed=frozenset()):
    days = trip_days(s.context, CFG)
    return evaluate(chosen, s, days, s.context.days is not None, set(anchors), set(locked),
                    centers(s, {}, CFG), set(wanted_timed), CFG)


def checks(res):
    return [c["check"] for c in res["conflicts"]]


def test_two_places_two_days_is_feasible_with_slack():
    res = run(cands(srec("A"), srec("B")), si())
    assert res["status"] == "feasible" and res["slack"] > 0 and res["totals"]["places"] == 2


def test_too_much_for_one_day_is_infeasible_and_fix_drops_lowest_score():
    chosen = cands(*[srec(f"P{i}") for i in range(6)])
    res = run(chosen, si(context={"days": 1}))
    assert res["status"] == "infeasible" and "time" in checks(res)
    fix = next(c for c in res["conflicts"] if c["check"] == "time")["fixes"][0]
    assert fix["action"] == {"type": "drop", "place_id": "P0"} and fix["label"] == "Bỏ Nơi P0"


def test_closed_every_day_conflict_offers_wishlist_for_locked():
    c = cands(srec("A"))[0]
    c.checks = [{"kind": "physical", "feature": "hours", "value": None, "op": None, "result": "fail",
                 "reason": "closed_all_trip_days", "policy": None}]
    res = run([c], si(), locked={"A"})
    conflict = next(x for x in res["conflicts"] if x["check"] == "hours")
    assert conflict["physical"] and conflict["fixes"][0]["action"] == {"type": "wishlist", "place_id": "A"}


def test_cloud_hunting_competes_for_early_mornings():
    clouds = [srec(f"C{i}", features={"cloud_hunting": CLOUD}) for i in range(3)]
    s = si(context={"days": 2})
    days = trip_days(s.context, CFG)
    assert need_buckets(cands(clouds[0])[0], {"cloud_hunting"}, False, days, CFG) == frozenset({"early_morning"})
    assert need_buckets(cands(clouds[0])[0], set(), False, days, CFG) is None  # not wanted, not an anchor
    assert need_buckets(cands(clouds[0])[0], set(), True, days, CFG) == frozenset({"early_morning"})  # anchor's top
    assert supply(days, None, CFG)["early_morning"] == 1 and supply(days, 300, CFG)["early_morning"] == 2
    res = run(cands(*clouds), s, wanted_timed={"cloud_hunting"})
    tw = next(c for c in res["conflicts"] if c["check"] == "time_windows")
    assert tw["title"] == "3 nơi cần sáng sớm, chuyến chỉ có 1 buổi như vậy" and tw["fixes"][-1]["action"] is None
    assert any("không trùng sáng sớm" in w for w in res["warnings"])  # open 07:00, best before 07:00
    assert "time_windows" not in checks(run(cands(clouds[0]), s, wanted_timed={"cloud_hunting"}))


def test_night_only_places_need_evenings():
    night = {d: [["18:00", "23:00"]] for d in ("mon", "tue")}
    s = si(context={"days": 2})
    two = cands(srec("N1", hours=night), srec("N2", hours=night))
    assert "time_windows" not in checks(run(two, s))
    three = cands(srec("N1", hours=night), srec("N2", hours=night), srec("N3", hours=night))
    assert "time_windows" in checks(run(three, s))


def test_far_areas_per_day_budget_and_relax():
    far = cands(srec("F1", lat=12.05, area="area-7"), srec("F2", lat=11.82, area="area-8"))
    assert "far_areas" in checks(run(far, si(context={"days": 1})))
    many = cands(*[srec(f"E{i}", visit=(10, 15, 20)) for i in range(6)])
    assert "per_day" in checks(run(many, si(context={"days": 1})))
    pricey = cands(srec("M", price={"min_vnd": 200000, "max_vnd": 200000}, usable=("meal",)))
    assert "budget" in checks(run(pricey, si(context={"days": 1, "budget_vnd": 100000})))
    assert "Chưa biết ngân sách của bạn nên chưa kiểm chi phí" in run(pricey, si())["warnings"]
    kept = cands(srec("K"))[0]
    kept.checks = [{"kind": "hard", "feature": "steep_or_stairs", "value": "present", "op": "ne", "result": "fail",
                    "reason": "hard:steep_or_stairs", "policy": "exclude"}]
    relax = next(c for c in run([kept], si(), locked={"K"})["conflicts"] if c["check"] == "relax")
    assert relax["fixes"][0]["action"] == {"type": "relax", "place_id": "K", "feature": "steep_or_stairs"}


def test_unknown_days_skips_day_checks():
    res = run(cands(*[srec(f"P{i}") for i in range(9)]), si(context={"days": None}))
    assert res["status"] == "unknown" and res["slack"] is None and checks(res) == []
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_feasibility.py`
Expected: FAIL `No module named 'decision.feasibility'`.

- [ ] **Step 3: Cài đặt**

`src/decision/feasibility.py`:

```python
"""⑨ Combination feasibility (docs/PLACE_DECISION.md §13, spec §11): the chosen places as one group, rough and
deterministic. Every conflict carries fixes whose `action` is a POST /act payload (None: shown, not clickable)."""

from collections import defaultdict
from itertools import combinations

from corpus.serving import feature

from .cards import feature_label, value_label
from .geo import fmt, km, minutes, point, to_min
from .model import Cand


def _visit(c: Cand) -> int:
    vm = c.rec["operation"].get("visit_minutes")
    return vm["typical"] if vm else 60


def _cost_vnd(c: Cand) -> int:
    op = c.rec["operation"]
    p = op.get("price_per_person")
    lo = (p["value"].get("min_vnd") or 0) if p else 0
    hi = (p["value"].get("max_vnd") or lo) if p else 0
    fee = (op.get("entry_fee") or {}).get("typical_vnd") or 0
    return int((lo + hi) / 2 + fee)


def _areas(chosen: list[Cand]) -> dict[str, tuple[tuple[float, float], list[Cand]]]:
    acc = defaultdict(list)
    for c in chosen:
        if p := point(c.rec):
            acc[c.rec["identity"].get("area") or c.id].append((c, p))
    return {a: ((sum(p[0] for _, p in xs) / len(xs), sum(p[1] for _, p in xs) / len(xs)), [c for c, _ in xs])
            for a, xs in acc.items()}


def _top_experience(rec: dict) -> str | None:
    exp = rec.get("experience") or {}
    return max(exp, key=lambda f: (exp[f]["n"], f)) if exp else None


def _timed(c: Cand, wanted_timed: set[str], is_anchor: bool, cfg) -> set[str]:
    """Buckets that hold timed_share of the time-of-day mentions of a timed feature the user wants (or the anchor's
    top experience)."""
    top, out = _top_experience(c.rec), set()
    for fid in cfg.timed_features:
        f = feature(c.rec, fid)
        if not f or f["value"] != "present" or not (fid in wanted_timed or (is_anchor and fid == top)):
            continue
        counts = defaultdict(float)
        for k, d in f["by_context"].items():
            if k.startswith("time_of_day="):
                counts[k.split("=", 1)[1]] += sum(d.values())
        total, acc = sum(counts.values()), 0.0
        for b, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            out.add(b)
            acc += n
            if acc / total >= cfg.timed_share:
                break
    return out


def _windows_on(rec: dict, days) -> list[tuple[int, int]]:
    h = rec["operation"].get("hours")
    if not h or not h["value"]:
        return []
    keys = [d.weekday for d in days if d.weekday] or list(h["value"])
    return sorted({(to_min(a), to_min(b)) for k in keys for a, b in h["value"].get(k, [])})


def _night_only(rec: dict, days, cfg) -> bool:
    ws = _windows_on(rec, days)
    return bool(ws) and all(a >= to_min(cfg.night_open) for a, _ in ws)


def need_buckets(c: Cand, wanted_timed: set[str], is_anchor: bool, days, cfg) -> frozenset[str] | None:
    need = _timed(c, wanted_timed, is_anchor, cfg)
    if _night_only(c.rec, days, cfg):
        need |= {"evening", "night"}
    return frozenset(need) if need and need <= set(cfg.narrow_buckets) else None


def supply(days, arrive: int | None, cfg) -> dict[str, int]:
    """One slot per narrow bucket per day, except before the arrival on day 1 and after leaving on the last day."""
    out = {b: 0 for b in cfg.narrow_buckets}
    for d in days:
        for b in cfg.narrow_buckets:
            s, e = map(to_min, cfg.buckets[b])
            if d.index == 0 and e <= (arrive if arrive is not None else d.start):
                continue
            if d.index == len(days) - 1 and s >= d.end:
                continue
            out[b] += 1
    return out


def _drop_fix(c: Cand, effect: str) -> dict:
    return {"label": f"Bỏ {c.name}", "effect": effect, "action": {"type": "drop", "place_id": c.id}}


def _window_conflict(chosen, needs, days, arrive, removable, cfg) -> list[dict]:
    sup, worst = supply(days, arrive, cfg), None
    for r in range(1, len(cfg.narrow_buckets) + 1):
        for bs in combinations(cfg.narrow_buckets, r):
            who = [c for c in chosen if c.id in needs and needs[c.id] <= set(bs)]
            cap = sum(sup[b] for b in bs)
            if len(who) > cap and (worst is None or len(who) - cap > worst[0]):
                worst = (len(who) - cap, bs, who, cap)
    if worst is None:
        return []
    _, bs, who, cap = worst
    ids = {c.id for c in who}
    label = " hoặc ".join(cfg.labels["time"][b] for b in bs)
    fixes = [_drop_fix(c, f"Còn {len(who) - 1} nơi cho {cap} buổi") for c in removable if c.id in ids][:1]
    fixes.append({"label": "Thêm 1 ngày cho chuyến", "effect": "Sửa số ngày ở bước Hiểu chuyến đi", "action": None})
    return [{"id": "time_windows:" + "+".join(bs), "check": "time_windows", "physical": True,
             "title": f"{len(who)} nơi cần {label}, chuyến chỉ có {cap} buổi như vậy",
             "rule": "Săn mây, hoàng hôn, nhạc sống hay nơi chỉ mở buổi tối chỉ đi được đúng buổi đó.",
             "places": sorted(ids), "fixes": fixes}]


def _window_warnings(chosen, wanted_timed, anchors, days, cfg) -> list[str]:
    out = []
    for c in chosen:
        timed = _timed(c, wanted_timed, c.id in anchors, cfg)
        ws = _windows_on(c.rec, days)
        if not timed or not ws:
            continue
        spans = [tuple(map(to_min, cfg.buckets[b])) for b in timed]
        if not any(a < e and s < b for a, b in ws for s, e in spans):
            hours = "; ".join(f"{fmt(a)}–{fmt(b)}" for a, b in ws[:2])
            label = " hoặc ".join(cfg.labels["time"][b] for b in sorted(timed))
            out.append(f"{c.name}: giờ mở cửa ({hours}) không trùng {label}")
    return out


def evaluate(chosen: list[Cand], si, days, known_days: bool, anchors: set[str], locked: set[str], ctrs,
             wanted_timed: set[str], cfg) -> dict:
    pace = si.pace.level or "normal"
    mob = si.context.mobility
    center = ctrs[0][1]
    conflicts, warnings = [], []
    removable = sorted((c for c in chosen if c.id not in locked and c.id not in anchors), key=lambda c: (c.score, c.id))

    areas = _areas(chosen)
    area_min = {a: minutes(km(center, cen), mob, cfg) for a, (cen, _) in areas.items()}
    visit = sum(_visit(c) for c in chosen)
    buffer = cfg.buffer_min[pace] * len(chosen)
    travel = cfg.intra_leg_min * len(chosen) + sum(2 * m for m in area_min.values())
    needed = visit + buffer + travel
    available = sum(max(0, d.end - d.start) for d in days)
    if known_days and needed > available:
        conflicts.append({"id": "time", "check": "time", "physical": True,
                          "title": f"Cần khoảng {needed} phút, chuyến có {available} phút",
                          "rule": "Tổng thời gian tham quan, đi lại (ước tính) và nghỉ vượt thời gian của chuyến.",
                          "places": [], "fixes": [_drop_fix(c, f"Bớt khoảng {_visit(c) + cfg.buffer_min[pace] + cfg.intra_leg_min} phút")
                                                  for c in removable[:2]]})

    for c in chosen:
        if any(x["reason"] == "closed_all_trip_days" and x["result"] == "fail" for x in c.checks):
            fixes = [_drop_fix(c, "Giải phóng thời gian cho nơi khác")]
            if c.id in locked or c.id in anchors:
                fixes.insert(0, {"label": "Chuyển vào danh sách mong muốn",
                                 "effect": "Giữ để đi dịp khác, không xếp vào chuyến này",
                                 "action": {"type": "wishlist", "place_id": c.id}})
            conflicts.append({"id": f"hours:{c.id}", "check": "hours", "physical": True,
                              "title": f"{c.name} đóng cửa mọi ngày của chuyến", "rule": "Theo giờ mở cửa trên Google.",
                              "places": [c.id], "fixes": fixes})
        if "hours_unknown" in c.warnings:
            warnings.append(f"{c.name}: chưa có giờ mở cửa, kiểm tra trước khi đi")
        elif "hours_outdated" in c.warnings:
            warnings.append(f"{c.name}: giờ mở cửa có thể đã đổi, kiểm tra lại trước chuyến")
        if c.missing:
            warnings.append(f"{c.name}: chưa có trong dữ liệu, mọi thông tin chưa xác minh")

    if known_days:
        needs = {c.id: n for c in chosen if (n := need_buckets(c, wanted_timed, c.id in anchors, days, cfg))}
        arrive = to_min(si.context.arrive_at) if si.context.arrive_at else None
        conflicts += _window_conflict(chosen, needs, days, arrive, removable, cfg)
    warnings += _window_warnings(chosen, wanted_timed, anchors, days, cfg)

    far = {a: m for a, m in area_min.items() if km(center, areas[a][0]) > cfg.far_km}
    if known_days and len(far) > len(days):
        worst = max(far, key=lambda a: (far[a], a))
        conflicts.append({"id": "far_areas", "check": "far_areas", "physical": False,
                          "title": f"{len(far)} khu cách xa cho {len(days)} ngày",
                          "rule": f"Mỗi ngày nên đi nhiều nhất một khu cách điểm xuất phát hơn {cfg.far_km} km.",
                          "places": sorted(c.id for a in far for c in areas[a][1]),
                          "fixes": [_drop_fix(c, f"Bớt khoảng {2 * far[worst]} phút đi lại nếu bỏ hết khu này")
                                    for c in removable if c in areas[worst][1]][:2]})

    exp = [c for c in chosen if c.role == "experience"]
    cap = len(days) * cfg.per_day_max[pace]
    if known_days and len(exp) > cap:
        conflicts.append({"id": "per_day", "check": "per_day", "physical": False,
                          "title": f"{len(exp)} nơi trải nghiệm, nhịp {cfg.labels['pace'][pace]} hợp với tối đa {cap}",
                          "rule": "Số nơi mỗi ngày theo nhịp độ bạn chọn.", "places": [c.id for c in exp],
                          "fixes": [_drop_fix(c, "Bớt một nơi") for c in removable if c.role == "experience"][:2]})

    budget = si.context.budget_vnd
    priced = [(c, v) for c in chosen if (v := _cost_vnd(c))]
    if budget and priced:
        per_day = sum(v for _, v in priced) / len(days)
        if per_day > budget * cfg.budget_slack:
            top = sorted(((c, v) for c, v in priced if c in removable), key=lambda x: (-x[1], x[0].id))
            conflicts.append({"id": "budget", "check": "budget", "physical": False,
                              "title": f"Chi phí ước tính khoảng {round(per_day / 1000)}k/người/ngày, ngân sách {budget // 1000}k",
                              "rule": "Tính từ khoảng giá trên Google và giá vé ước tính.",
                              "places": [c.id for c, _ in priced],
                              "fixes": [_drop_fix(c, f"Bớt khoảng {v // 1000}k/người") for c, v in top[:2]]})
    elif priced:
        warnings.append("Chưa biết ngân sách của bạn nên chưa kiểm chi phí")

    for c in chosen:
        for x in c.checks:
            if x["kind"] != "hard" or x["result"] == "pass":
                continue
            fl, vl = feature_label(x["feature"], cfg).lower(), value_label(x["value"], cfg)
            if x["result"] == "unknown":
                warnings.append(f"{c.name}: chưa xác minh được {fl}, tự kiểm tra trước chuyến")
                continue
            conflicts.append({"id": f"relax:{c.id}:{x['feature']}", "check": "relax", "physical": False,
                              "title": f"{c.name}: {fl} ({vl})" if x["op"] == "ne" else f"{c.name}: không phải {vl}",
                              "rule": f"Bạn đặt điều kiện {fl} khác {vl}." if x["op"] == "ne" else f"Bạn cần {fl} là {vl}.",
                              "places": [c.id],
                              "fixes": [{"label": "Vẫn giữ, bỏ điều kiện này cho riêng nơi này",
                                         "effect": "Chỉ áp cho nơi này trong chuyến này",
                                         "action": {"type": "relax", "place_id": c.id, "feature": x["feature"]}},
                                        _drop_fix(c, "Giữ đúng điều kiện của bạn")]})

    if known_days and needed > available * cfg.infeasible_ratio:
        status = "infeasible"
    elif conflicts:
        status = "partial"
    elif not known_days:
        status = "unknown"
    else:
        status = "feasible"
    return {"status": status, "known_days": known_days,
            "totals": {"places": len(chosen), "visit": visit, "buffer": buffer, "travel": travel, "needed": needed,
                       "available": available},
            "slack": available - needed if known_days else None, "conflicts": conflicts, "warnings": warnings}
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_feasibility.py`
Expected: PASS (7 test). Nếu `test_too_much_for_one_day...` không ra `infeasible`, in `res["totals"]` để xem: 6 nơi × (75 + 20 + 10) + đi lại ≥ 644 > 420 × 1,35.

- [ ] **Step 5: Commit**

```bash
git add src/decision/feasibility.py tests/decision/test_feasibility.py
git commit -m "feat(decision): combination feasibility with time windows from corpus hours and time-of-day evidence"
```

---

### Task 8: Phiên và ⑧ Tuyển chọn

**Files:**
- Create: `src/decision/session.py`, `src/decision/curation.py`
- Test: `tests/decision/test_session.py`, `tests/decision/test_curation.py`

**Interfaces:**
- Consumes: `trip.SearchInput`, `corpus.ontology.load`, `corpus.serving.feature`, `FIRM` (Task 2), `phrase` (Task 6).
- Produces:
  - `session.Reason = Literal["far","crowded","pricey","dislike","visited"]`; models `SoftAdd(feature, value, weight)`, `Profile(travel_mult, crowd_tolerance, price_sensitivity, soft, visited)`, `Drop(place_id, reason)`, `Chip(id, label)`, `Pending(qid, text, reason, chips, data)`, `State(selected, locked, dropped, relaxed, wishlist, profile, answered, unmapped, suggest_group, last)`, `Session(id, trip_session, search_input, state, history, log, first_shortlist, output)`.
  - `session.Store(root: Path | None)`: `new(si, trip_session, state) -> Session`, `get(sid) -> Session` (KeyError), `save(s)`, `lock(sid) -> threading.Lock`.
  - `curation.ActionError(ValueError)`; `curation.REASONS`; `curation.apply(state, act: dict, known, alternatives: dict[str, list[str]], pending: Pending | None, cfg) -> State` (bản sao mới; `known(pid) -> bool`); `curation.pending(state, by_id, si, feas: dict, first_shortlist: int, group_of: dict[str, str], cfg) -> Pending | None`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_session.py`:

```python
import json

import pytest
from fixtures import si

from decision.session import Drop, State, Store


def test_store_roundtrip_and_ids(tmp_path):
    store = Store(tmp_path)
    s = store.new(si(), "abcdef012345", State(selected=["A"]))
    s.state.dropped.append(Drop(place_id="B", reason="far"))
    store.save(s)
    again = Store(tmp_path).get(s.id)
    assert again.state.dropped[0].reason == "far" and again.search_input == s.search_input
    assert json.loads((tmp_path / f"{s.id}.json").read_text(encoding="utf-8"))["trip_session"] == "abcdef012345"
    with pytest.raises(KeyError):
        store.get("../etc")
    with pytest.raises(KeyError):
        store.get("0123456789ab")
    assert store.lock(s.id) is store.lock(s.id)


def test_memory_only_store():
    store = Store(None)
    s = store.new(si(), None, State())
    store.save(s)
    assert store.get(s.id) is s
```

`tests/decision/test_curation.py`:

```python
import pytest
from fixtures import si, srec

from decision.curation import ActionError, apply, pending
from decision.session import Chip, Drop, Pending, State
from decision.settings import default

CFG = default()
KNOWN = {"A", "B", "C", "D", "E", "F", "G"}


def act(state, a, alternatives=None, pend=None):
    return apply(state, a, KNOWN.__contains__, alternatives or {}, pend, CFG)


def test_select_lock_unlock_drop_and_reasons_update_profile():
    s = act(State(), {"type": "select", "place_id": "A"})
    s = act(s, {"type": "lock", "place_id": "B"})
    assert s.selected == ["A", "B"] and s.locked == ["B"]
    s = act(s, {"type": "unlock", "place_id": "B"})
    assert s.locked == [] and s.selected == ["A", "B"]
    s = act(s, {"type": "drop", "place_id": "A", "reason": "far"})
    s = act(s, {"type": "drop", "place_id": "C", "reason": "crowded"})
    s = act(s, {"type": "drop", "place_id": "D", "reason": "pricey"})
    s = act(s, {"type": "drop", "place_id": "E", "reason": "visited"})
    assert s.selected == ["B"] and [d.place_id for d in s.dropped] == ["A", "C", "D", "E"]
    assert s.profile.travel_mult == CFG.far_step and s.profile.crowd_tolerance == "avoid"
    assert s.profile.price_sensitivity == CFG.price_step and s.profile.visited == ["E"]
    s = act(s, {"type": "select", "place_id": "A"})
    assert "A" not in [d.place_id for d in s.dropped] and s.last == "select"


def test_original_state_is_not_changed():
    s = State()
    act(s, {"type": "select", "place_id": "A"})
    assert s.selected == []


def test_swap_relax_wishlist_feedback_prefer_note():
    s = act(State(selected=["A"]), {"type": "swap", "place_id": "A", "with_id": "B"}, alternatives={"A": ["B"]})
    assert s.selected == ["B"] and s.dropped == [Drop(place_id="A", reason=None)]
    s = act(s, {"type": "relax", "place_id": "B", "feature": "steep_or_stairs"})
    s = act(s, {"type": "wishlist", "place_id": "B"})
    assert s.relaxed == [("B", "steep_or_stairs")] and s.wishlist == ["B"] and s.selected == []
    s = act(s, {"type": "feedback", "reason": "far"})
    s = act(s, {"type": "prefer", "feature": "noise", "value": "quiet", "weight": 1})
    s = act(s, {"type": "note", "phrase": "nhạc nhẹ"})
    assert s.profile.travel_mult == CFG.far_step and s.profile.soft[0].feature == "noise" and s.unmapped == ["nhạc nhẹ"]


@pytest.mark.parametrize("a", [
    {"type": "select", "place_id": "nope"},
    {"type": "drop", "place_id": "A", "reason": "ugly"},
    {"type": "swap", "place_id": "A", "with_id": "C"},
    {"type": "relax", "place_id": "A"},
    {"type": "feedback", "reason": "dislike"},
    {"type": "prefer", "feature": "noise", "value": "purple", "weight": 1},
    {"type": "answer", "qid": "rethink", "chip": "back"},
    {"type": "explode"},
])
def test_bad_actions_raise(a):
    with pytest.raises(ActionError):
        act(State(selected=["A"]), a, alternatives={"A": ["B"]})


def test_pattern_question_after_three_drops_sharing_a_bad_value():
    by_id = {k: srec(k, features={"crowd": "high"}) for k in "ABC"}
    s = State(dropped=[Drop(place_id=k) for k in "ABC"], last="drop")
    p = pending(s, by_id, si(), {"slack": 0}, 20, {}, CFG)
    assert p.qid == "pattern:crowd=high" and [c.id for c in p.chips] == ["yes", "no"]
    s2 = act(s, {"type": "answer", "qid": p.qid, "chip": "yes"}, pend=p)
    assert (s2.profile.soft[0].feature, s2.profile.soft[0].value, s2.profile.soft[0].weight) == ("crowd", "high", -1)
    assert pending(s2, by_id, si(), {"slack": 0}, 20, {}, CFG) is None
    s3 = act(s, {"type": "answer", "qid": p.qid, "chip": "no"}, pend=p)
    assert s3.profile.soft == [] and pending(s3, by_id, si(), {"slack": 0}, 20, {}, CFG) is None


def test_rethink_and_gap_questions():
    by_id = {k: srec(k) for k in KNOWN}
    many = State(dropped=[Drop(place_id=k) for k in "ABCDEF"], last="drop")
    assert pending(many, by_id, si(), {"slack": 0}, 10, {}, CFG).qid == "rethink"
    one = State(dropped=[Drop(place_id="A")], last="drop")
    gap = pending(one, by_id, si(), {"slack": 200}, 10, {"A": "nature"}, CFG)
    assert gap.qid == "gap:1" and gap.data == {"group": "nature"}
    s = act(one, {"type": "answer", "qid": "gap:1", "chip": "similar"}, pend=gap)
    assert s.suggest_group == "nature"
    assert pending(State(dropped=[Drop(place_id="A")], last="select"), by_id, si(), {"slack": 200}, 10, {}, CFG) is None
    assert pending(one, by_id, si(), {"slack": None}, 10, {}, CFG) is None
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_session.py tests/decision/test_curation.py`
Expected: FAIL `No module named 'decision.session'`.

- [ ] **Step 3: Cài đặt**

`src/decision/session.py`:

```python
"""A Place Decision session: Search Input + what the user did, versioned for undo; in memory, mirrored to
data/decision/sessions/<id>.json so a reload or a restart resumes."""

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from trip import SearchInput

Reason = Literal["far", "crowded", "pricey", "dislike", "visited"]
SID = re.compile(r"[0-9a-f]{12}")


class SoftAdd(BaseModel):
    feature: str
    value: str
    weight: Literal[1, -1]


class Profile(BaseModel):
    """Session Profile (docs/Project_Context.md §8): this trip only, never the long-term profile."""
    travel_mult: float = 1.0
    crowd_tolerance: Literal["avoid", "ok_if_worth", "fine"] | None = None
    price_sensitivity: float = 0.0
    soft: list[SoftAdd] = Field(default_factory=list)
    visited: list[str] = Field(default_factory=list)


class Drop(BaseModel):
    place_id: str
    reason: Reason | None = None


class Chip(BaseModel):
    id: str
    label: str


class Pending(BaseModel):
    qid: str
    text: str
    reason: str
    chips: list[Chip]
    data: dict = Field(default_factory=dict)


class State(BaseModel):
    selected: list[str] = Field(default_factory=list)  # includes locked and anchors still in the trip
    locked: list[str] = Field(default_factory=list)
    dropped: list[Drop] = Field(default_factory=list)
    relaxed: list[tuple[str, str]] = Field(default_factory=list)  # (place id, feature) the user agreed to relax
    wishlist: list[str] = Field(default_factory=list)
    profile: Profile = Field(default_factory=Profile)
    answered: list[str] = Field(default_factory=list)  # question ids answered or declined
    unmapped: list[str] = Field(default_factory=list)
    suggest_group: str | None = None  # "Gợi ý nơi tương tự" was answered for this display group
    last: str | None = None  # type of the last action


class Session(BaseModel):
    id: str
    trip_session: str | None = None
    search_input: SearchInput
    state: State = Field(default_factory=State)
    history: list[State] = Field(default_factory=list)
    log: list[dict] = Field(default_factory=list)
    first_shortlist: int = 0
    output: dict | None = None


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def new(self, si: SearchInput, trip_session: str | None, state: State) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], trip_session=trip_session, search_input=si, state=state)
        with self._guard:
            self._mem[s.id] = s
        return s

    def get(self, sid: str) -> Session:
        if not SID.fullmatch(sid):
            raise KeyError(sid)
        with self._guard:
            if sid in self._mem:
                return self._mem[sid]
            path = self.root / f"{sid}.json" if self.root else None
            if not path or not path.exists():
                raise KeyError(sid)
            s = Session.model_validate_json(path.read_text(encoding="utf-8"))
            self._mem[sid] = s
            return s

    def save(self, s: Session) -> None:
        if not self.root:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"{s.id}.json.tmp"
        tmp.write_text(json.dumps(s.model_dump(mode="json"), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / f"{s.id}.json")

    def lock(self, sid: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(sid, threading.Lock())
```

`src/decision/curation.py`:

```python
"""⑧ Curation (docs/PLACE_DECISION.md §12): typed actions on the session state, the Session Profile they teach, and
the one question the rules may open (pattern, gap, rethink). Pure: apply() returns a new State."""

from collections import Counter
from functools import cache

from corpus.ontology import load
from corpus.serving import feature

from .cards import phrase
from .model import FIRM
from .session import Drop, Pending, SoftAdd, State, Chip

REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PLACE_ACTIONS = {"select", "drop", "lock", "unlock", "swap", "relax", "wishlist"}


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed."""


@cache
def _ontology():
    return load()


def _select(s: State, pid: str) -> None:
    if pid not in s.selected:
        s.selected.append(pid)
    s.dropped = [d for d in s.dropped if d.place_id != pid]
    s.wishlist = [w for w in s.wishlist if w != pid]


def _remove(s: State, pid: str) -> None:
    s.selected = [x for x in s.selected if x != pid]
    s.locked = [x for x in s.locked if x != pid]


def _feedback(s: State, reason: str | None, pid: str | None, cfg) -> None:
    p = s.profile
    if reason == "far":
        p.travel_mult = max(cfg.travel_mult_min, round(p.travel_mult * cfg.far_step, 3))
    elif reason == "crowded":
        p.crowd_tolerance = "avoid"
    elif reason == "pricey":
        p.price_sensitivity = round(p.price_sensitivity + cfg.price_step, 3)
    elif reason == "visited" and pid and pid not in p.visited:
        p.visited.append(pid)


def apply(state: State, act: dict, known, alternatives: dict[str, list[str]], pending: Pending | None, cfg) -> State:
    t, pid = act.get("type"), act.get("place_id")
    if t in PLACE_ACTIONS and not (isinstance(pid, str) and known(pid)):
        raise ActionError(f"unknown place {pid!r}")
    s = state.model_copy(deep=True)
    if t != "answer":
        s.suggest_group = None
    if t == "select":
        _select(s, pid)
    elif t == "lock":
        _select(s, pid)
        if pid not in s.locked:
            s.locked.append(pid)
    elif t == "unlock":
        s.locked = [x for x in s.locked if x != pid]
    elif t == "drop":
        reason = act.get("reason")
        if reason not in (None, *REASONS):
            raise ActionError(f"unknown reason {reason!r}")
        _remove(s, pid)
        s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid, reason=reason)]
        _feedback(s, reason, pid, cfg)
    elif t == "swap":
        w = act.get("with_id")
        if w not in alternatives.get(pid, []):
            raise ActionError(f"{w!r} is not an alternative of {pid!r}")
        _remove(s, pid)
        s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid)]
        _select(s, w)
    elif t == "relax":
        f = act.get("feature")
        if not isinstance(f, str) or f not in _ontology().features:
            raise ActionError(f"unknown feature {f!r}")
        if (pid, f) not in s.relaxed:
            s.relaxed.append((pid, f))
    elif t == "wishlist":
        _remove(s, pid)
        if pid not in s.wishlist:
            s.wishlist.append(pid)
    elif t == "feedback":
        if act.get("reason") not in ("far", "crowded", "pricey"):
            raise ActionError(f"unknown feedback {act.get('reason')!r}")
        _feedback(s, act["reason"], None, cfg)
    elif t == "prefer":
        f, v, w = act.get("feature"), act.get("value"), act.get("weight")
        if not _ontology().valid(f, v) or w not in (1, -1):
            raise ActionError(f"bad preference {f!r}={v!r} weight {w!r}")
        s.profile.soft = [x for x in s.profile.soft if (x.feature, x.value) != (f, v)] + [SoftAdd(feature=f, value=v, weight=w)]
    elif t == "note":
        phrase_ = (act.get("phrase") or "").strip()
        if not phrase_:
            raise ActionError("empty note")
        s.unmapped.append(phrase_[:120])
    elif t == "answer":
        qid, chip = act.get("qid"), act.get("chip")
        if not pending or qid != pending.qid or chip not in [c.id for c in pending.chips]:
            raise ActionError(f"no open question {qid!r} with chip {chip!r}")
        s.answered.append(qid)
        if qid.startswith("pattern:") and chip == "yes":
            f, v = qid[len("pattern:"):].split("=", 1)
            s.profile.soft.append(SoftAdd(feature=f, value=v, weight=-1))
        elif qid.startswith("gap:") and chip == "similar":
            s.suggest_group = pending.data.get("group")
    else:
        raise ActionError(f"unknown action {t!r}")
    s.last = t
    return s


def pending(state: State, by_id: dict, si, feas: dict, first_shortlist: int, group_of: dict[str, str], cfg) -> Pending | None:
    """The one question the rules open now, most important first: pattern, rethink, gap."""
    avoided = {(w.feature, w.value) for w in si.soft_weights if w.weight < 0}
    avoided |= {(x.feature, x.value) for x in state.profile.soft if x.weight < 0}
    counts = Counter()
    for d in state.dropped:
        r = by_id.get(d.place_id)
        if not r or d.reason == "visited":
            continue
        for fid, order in cfg.polarity.items():
            f = feature(r, fid)
            if f and f["status"] in FIRM and f["value"] == order[-1]:
                counts[(fid, order[-1])] += 1
    for (fid, v), n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        qid = f"pattern:{fid}={v}"
        if n >= cfg.pattern_min and qid not in state.answered and (fid, v) not in avoided:
            return Pending(qid=qid, text=f"Mấy nơi bạn bỏ đều có điểm “{phrase(fid, v, cfg)}”. Bạn muốn tránh kiểu nơi này?",
                           reason=f"{n} nơi bạn bỏ có chung điểm này",
                           chips=[Chip(id="yes", label="Đúng, tránh giúp mình"), Chip(id="no", label="Không phải")])
    if (len(state.dropped) >= cfg.rethink_drops and len(state.dropped) * 2 >= first_shortlist
            and "rethink" not in state.answered):
        return Pending(qid="rethink", text="Bạn đã bỏ khá nhiều gợi ý. Mình hỏi lại một chút về mục đích chuyến đi nhé?",
                       reason="Gợi ý có vẻ chưa đúng gu của bạn",
                       chips=[Chip(id="back", label="Hỏi lại giúp mình"), Chip(id="stay", label="Không, mình tự chọn tiếp")])
    slack = feas.get("slack")
    qid = f"gap:{len(state.dropped)}"
    if state.last == "drop" and slack is not None and slack >= cfg.gap_min and qid not in state.answered:
        return Pending(qid=qid, text=f"Bỏ nơi này, chuyến còn dư khoảng {slack} phút. Bạn muốn làm gì?",
                       reason="Thời gian trống sau khi bỏ",
                       chips=[Chip(id="similar", label="Gợi ý nơi tương tự"), Chip(id="free", label="Để thời gian tự do")],
                       data={"group": group_of.get(state.dropped[-1].place_id)})
    return None
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_session.py tests/decision/test_curation.py`
Expected: PASS (2 + 13 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/session.py src/decision/curation.py tests/decision/test_session.py tests/decision/test_curation.py
git commit -m "feat(decision): versioned sessions and curation actions with the Session Profile they teach"
```

---

### Task 9: Phạm vi chạy lại và ⑦ So sánh

**Files:**
- Create: `src/decision/scope.py`, `src/decision/compare.py`
- Test: `tests/decision/test_scope.py`, `tests/decision/test_compare.py`

**Interfaces:**
- Consumes: `Cand`, `FIRM` (Task 2), `feature_label`, `value_label` (Task 6), `corpus.serving.feature`.
- Produces:
  - `scope.STEPS = ("resolve", "screen", "fit", "rank", "diversify", "feasibility")`; `scope.replan_scope(action: dict) -> {"from": str, "keep": list[str]}`; `scope.input_scope(old: SearchInput, new: SearchInput) -> {"from": str | None, "keep": list[str]}`.
  - `compare.compare(a: Cand, b: Cand, wanted: list[str], days, cfg) -> {"a": {id, name}, "b": {id, name}, "rows": [...], "sacrifice": [...]}`; mỗi dòng `{aspect, label, a, b, better: a|b|none|unknown}`; khác vai trò → `ValueError`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_scope.py`:

```python
import pytest
from fixtures import hard, love, si

from decision.scope import input_scope, replan_scope


@pytest.mark.parametrize("action,step", [
    ({"type": "select", "place_id": "A"}, "diversify"),
    ({"type": "drop", "place_id": "A"}, "diversify"),
    ({"type": "drop", "place_id": "A", "reason": "far"}, "fit"),
    ({"type": "drop", "place_id": "A", "reason": "pricey"}, "rank"),
    ({"type": "relax", "place_id": "A", "feature": "steep_or_stairs"}, "screen"),
    ({"type": "feedback", "reason": "crowded"}, "fit"),
    ({"type": "prefer", "feature": "noise", "value": "quiet", "weight": 1}, "rank"),
    ({"type": "answer", "qid": "pattern:crowd=high", "chip": "yes"}, "rank"),
    ({"type": "answer", "qid": "gap:1", "chip": "free"}, "diversify"),
    ({"type": "undo"}, "screen"),
])
def test_action_scope(action, step):
    got = replan_scope(action)
    assert got["from"] == step and step not in got["keep"]


def test_input_scope_follows_place_decision_table():
    base = si()
    assert input_scope(base, si(hard_filters=[hard("long_walk", "present")]))["from"] == "screen"
    assert input_scope(base, si(anchors=[{"place_id": "A", "priority": "must"}]))["from"] == "resolve"
    assert input_scope(base, si(soft_weights=[love("noise", "quiet")]))["from"] == "rank"
    assert input_scope(base, si(pace={"level": "slow"}))["from"] == "diversify"
    assert input_scope(base, si())["from"] is None
```

`tests/decision/test_compare.py`:

```python
import pytest
from fixtures import feat, si, srec

from decision.compare import compare
from decision.model import Cand
from decision.settings import default
from decision.trip_days import trip_days

CFG = default()
DAYS = trip_days(si().context, CFG)


def cand(rec, minutes=None, role="experience"):
    c = Cand(rec, role)
    c.minutes, c.center = minutes, "trung tâm Đà Lạt"
    return c


def test_rows_only_where_both_have_evidence_and_differ():
    a = cand(srec("A", features={"crowd": "low", "noise": "quiet", "scenic_view": "present"}), minutes=5)
    b = cand(srec("B", features={"crowd": "high", "noise": "quiet", "parking": feat("hard", n=1)}), minutes=20)
    got = compare(a, b, ["scenic_view"], DAYS, CFG)
    rows = {r["aspect"]: r for r in got["rows"]}
    assert rows["crowd"]["better"] == "a" and rows["crowd"]["a"] == "vắng (3 người)"
    assert "noise" not in rows and "parking" not in rows
    assert rows["scenic_view"]["better"] == "unknown" and rows["scenic_view"]["b"] == "chưa biết"
    dist = next(r for r in got["sacrifice"] if r["aspect"] == "distance")
    assert dist["better"] == "a" and dist["b"] == "≈20 phút"


def test_price_crowd_by_time_and_visit_in_sacrifice():
    cbt = lambda v: {"weekday": {"morning": v, "noon": v, "afternoon": v, "evening": v}}
    a = cand(srec("A", price={"min_vnd": 50000, "max_vnd": 50000}, crowd_by_time=cbt(80), visit=(30, 60, 90)))
    b = cand(srec("B", price={"min_vnd": 150000, "max_vnd": 150000}, crowd_by_time=cbt(20), visit=(30, 90, 120)))
    rows = {r["aspect"]: r for r in compare(a, b, [], DAYS, CFG)["sacrifice"]}
    assert rows["price"]["better"] == "a" and rows["crowd_by_time"]["better"] == "b"
    assert rows["visit"]["better"] == "none"


def test_different_roles_cannot_be_compared():
    with pytest.raises(ValueError):
        compare(cand(srec("A")), cand(srec("B"), role="meal"), [], DAYS, CFG)
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_scope.py tests/decision/test_compare.py`
Expected: FAIL `No module named 'decision.scope'`.

- [ ] **Step 3: Cài đặt**

`src/decision/scope.py`:

```python
"""replan_scope (docs/PLACE_DECISION.md §14): the earliest step a change must re-run from, and what stays as is.
The pipeline re-runs everything (cheap); the scope explains the change and is what the table promises."""

STEPS = ("resolve", "screen", "fit", "rank", "diversify", "feasibility")
DROP_STEP = {"far": "fit", "crowded": "fit", "pricey": "rank", "visited": "rank"}
FEEDBACK_STEP = {"far": "fit", "crowded": "fit", "pricey": "rank"}


def _out(step: str | None) -> dict:
    return {"from": step, "keep": list(STEPS[:STEPS.index(step)]) if step else list(STEPS)}


def replan_scope(action: dict) -> dict:
    t = action.get("type")
    if t == "drop":
        return _out(DROP_STEP.get(action.get("reason"), "diversify"))
    if t == "feedback":
        return _out(FEEDBACK_STEP.get(action.get("reason"), "rank"))
    if t == "relax" or t == "undo":
        return _out("screen")
    if t == "prefer" or (t == "answer" and str(action.get("qid", "")).startswith("pattern:") and action.get("chip") == "yes"):
        return _out("rank")
    return _out("diversify")


def input_scope(old, new) -> dict:
    """Search Input changed (the user edited the understanding)."""
    a, b = old.context, new.context
    if old.anchors != new.anchors or a.base != b.base:
        return _out("resolve")
    if (old.hard_filters != new.hard_filters or (a.start_date, a.month, a.days, a.mobility)
            != (b.start_date, b.month, b.days, b.mobility)):
        return _out("screen")
    if old.soft_weights != new.soft_weights or old.novelty != new.novelty:
        return _out("rank")
    if old.pace != new.pace or old.model_dump() != new.model_dump():
        return _out("diversify")
    return _out(None)
```

`src/decision/compare.py`:

```python
"""⑦ Compare two candidates (docs/PLACE_DECISION.md §10): only aspects with evidence on both sides; a side without
evidence is "chưa biết", never a loss; the trip-level sacrifice is a rough estimate."""

from corpus.serving import feature

from .cards import feature_label, value_label
from .model import FIRM, Cand

DAYTIME = ("morning", "noon", "afternoon", "evening")


def _firm(f) -> bool:
    return bool(f) and f["status"] in FIRM and f["n"] >= 2


def _cell(f, cfg) -> str:
    return f"{value_label(f['value'], cfg)} ({f['n']} người)"


def _crowd(c: Cand, days) -> int | None:
    cbt = c.rec["operation"].get("crowd_by_time")
    if not cbt:
        return None
    types = sorted({d.day_type for d in days if d.day_type}) or ["weekday", "weekend"]
    vals = [v for t in types for b in DAYTIME if (v := (cbt.get(t) or {}).get(b)) is not None]
    return round(sum(vals) / len(vals)) if vals else None


def _price(c: Cand) -> int | None:
    p = c.rec["operation"].get("price_per_person")
    lo = p["value"].get("min_vnd") if p else None
    return None if lo is None else int((lo + (p["value"].get("max_vnd") or lo)) / 2)


def _lower(label, aspect, x, y, text) -> dict | None:
    if x is None or y is None or x == y:
        return None
    return {"aspect": aspect, "label": label, "a": text(x), "b": text(y), "better": "a" if x < y else "b"}


def compare(a: Cand, b: Cand, wanted: list[str], days, cfg) -> dict:
    if a.role != b.role:
        raise ValueError("places of different roles are not alternatives")
    rows = []
    for fid, order in cfg.polarity.items():
        fa, fb = feature(a.rec, fid), feature(b.rec, fid)
        if not (_firm(fa) and _firm(fb)) or fa["value"] == fb["value"] or fa["value"] not in order or fb["value"] not in order:
            continue
        rows.append({"aspect": fid, "label": feature_label(fid, cfg), "a": _cell(fa, cfg), "b": _cell(fb, cfg),
                     "better": "a" if order.index(fa["value"]) < order.index(fb["value"]) else "b"})
    for fid in dict.fromkeys(wanted):
        if fid in cfg.polarity:
            continue
        fa, fb = feature(a.rec, fid), feature(b.rec, fid)
        if bool(fa) == bool(fb):
            continue
        rows.append({"aspect": fid, "label": feature_label(fid, cfg), "a": _cell(fa, cfg) if fa else "chưa biết",
                     "b": _cell(fb, cfg) if fb else "chưa biết", "better": "unknown"})
    sacrifice = [r for r in (
        _lower(f"Đi từ {a.center or 'điểm xuất phát'} (ước tính)", "distance", a.minutes, b.minutes, lambda m: f"≈{m} phút"),
        _lower("Độ đông ban ngày (Google)", "crowd_by_time", _crowd(a, days), _crowd(b, days), lambda v: f"{v}%"),
        _lower("Giá mỗi người", "price", _price(a), _price(b), lambda v: f"{v // 1000}k"),
    ) if r]
    ta = (a.rec["operation"].get("visit_minutes") or {}).get("typical")
    tb = (b.rec["operation"].get("visit_minutes") or {}).get("typical")
    if ta and tb and ta != tb:
        sacrifice.append({"aspect": "visit", "label": "Thời gian tham quan (ước tính)", "a": f"{ta} phút",
                          "b": f"{tb} phút", "better": "none"})
    return {"a": {"id": a.id, "name": a.name}, "b": {"id": b.id, "name": b.name}, "rows": rows, "sacrifice": sacrifice}
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_scope.py tests/decision/test_compare.py`
Expected: PASS (10 + 1 + 3 test).

- [ ] **Step 5: Commit**

```bash
git add src/decision/scope.py src/decision/compare.py tests/decision/test_scope.py tests/decision/test_compare.py
git commit -m "feat(decision): replan scope table and evidence-only comparison"
```

---
### Task 10: Pipeline, view, `why_not`, ⑩ Decision Output

**Files:**
- Create: `src/decision/pipeline.py`, `src/decision/output.py`
- Test: `tests/decision/test_pipeline.py`

**Interfaces:**
- Consumes: mọi module của Task 2–9; `corpus.serving.load`.
- Produces:
  - `pipeline.Data(records)` có `.records`, `.by_id`; `Data.load() -> Data` (đọc `data/serving/places.json`, `FileNotFoundError` khi thiếu).
  - `pipeline.Result(view, cands: dict[str, Cand], alternatives: dict[str, list[str]], group_of: dict[str, str], days)`.
  - `pipeline.run(s: Session, data: Data, cfg) -> Result`. `view` có key: `version groups shortlist selected locked unverified{count, open, cards} excluded{by_rule[{rule, label, count}]} wishlist[{id, name, reason}] dropped[{id, name, reason}] feasibility pending profile known_days days unknowns unmapped`. Mỗi group: `{id, label, cards}`; group `anchors` đứng đầu khi có anchor.
  - `pipeline.why_not(res, pid, si, cfg) -> {id, name, known, status, reasons: list[str], score, parts}`.
  - `pipeline.wanted(si, profile) -> list[str]`.
  - `output.build(s: Session, res: Result, cfg) -> {confirmed, backup_pool, wishlist, trip_context, decision_log, feasibility}`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_pipeline.py`:

```python
from fixtures import hard, love, si, srec

from decision.output import build
from decision.pipeline import Data, run, why_not
from decision.session import Drop, Session, State
from decision.settings import default

CFG = default()
FLAT = {"steep_or_stairs": "absent", "scenic_view": "present"}


def data():
    return Data([
        srec("FLAT1", group="nature", features=FLAT),
        srec("FLAT2", group="nature", features=FLAT, lat=11.95),
        srec("STEEP", group="nature", features={"steep_or_stairs": "present", "scenic_view": "present"}),
        srec("UNK", group="nature", features={"scenic_view": "present"}),
        srec("FAR", group="attraction", features={"steep_or_stairs": "absent"}, lat=12.4),
        *[srec(f"CAFE{i}", features={"steep_or_stairs": "absent", "cozy_decor": "present"}, lng=108.44 + i / 1000)
          for i in range(4)],
        srec("MEAL", usable=("meal",), features={"steep_or_stairs": "absent"}),
        srec("RENT", usable=()),
    ])


def trip(**over):
    return si(hard_filters=[hard("steep_or_stairs", "present")], soft_weights=[love("scenic_view")], **over)


def session(search=None, state=None):
    return Session(id="0" * 12, search_input=search or trip(), state=state or State())


def test_shortlist_is_fail_closed_and_grouped():
    v = run(session(), data(), CFG).view
    assert set(v["shortlist"]) == {"FLAT1", "FLAT2", "CAFE0", "CAFE1", "CAFE2", "CAFE3", "MEAL"}
    assert [g["id"] for g in v["groups"]] == ["nature", "chill", "meal"]
    assert all(not c["failed"] and not c["unverified"] for g in v["groups"] for c in g["cards"])
    assert v["unverified"]["count"] == 1 and v["unverified"]["cards"][0]["id"] == "UNK" and not v["unverified"]["open"]
    assert v["excluded"]["by_rule"] == [{"rule": "hard:steep_or_stairs", "label": "Điều kiện “dốc, nhiều bậc ≠ có”", "count": 1}]
    assert v["groups"][0]["cards"][0]["why"][0]["text"] == "View đẹp, 3 người nhắc"


def test_anchors_are_kept_even_when_missing_or_violating():
    s = session(trip(anchors=[{"place_id": "STEEP", "priority": "must"}, {"place_id": "GHOST", "priority": "want"}]),
                State(selected=["STEEP", "GHOST"], locked=["STEEP"]))
    v = run(s, data(), CFG).view
    anchors = v["groups"][0]
    assert anchors["id"] == "anchors" and [c["id"] for c in anchors["cards"]] == ["STEEP", "GHOST"]
    assert anchors["cards"][0]["failed"] == ["Dốc, nhiều bậc: có"]
    assert "Chưa có trong dữ liệu đang phục vụ (có thể đã đóng cửa)" in anchors["cards"][1]["warnings"]
    assert "relax" in [c["check"] for c in v["feasibility"]["conflicts"]]
    s.state.selected.remove("GHOST")
    s.state.dropped.append(Drop(place_id="GHOST"))
    assert [c["id"] for c in run(s, data(), CFG).view["groups"][0]["cards"]] == ["STEEP"]  # a dropped anchor is gone


def test_chosen_stay_first_dropped_leave_and_why_not_explains():
    s = session(state=State(selected=["CAFE3"], dropped=[Drop(place_id="FLAT1", reason="far")]))
    res = run(s, data(), CFG)
    chill = next(g for g in res.view["groups"] if g["id"] == "chill")
    assert chill["cards"][0]["id"] == "CAFE3" and chill["cards"][0]["chosen"]
    assert "FLAT1" not in res.view["shortlist"] and res.view["dropped"][0]["reason"] == "far"
    assert why_not(res, "FLAT1", s.search_input, CFG)["reasons"] == ["Bạn đã bỏ nơi này"]
    assert why_not(res, "STEEP", s.search_input, CFG)["reasons"] == ["Bị loại: Dốc, nhiều bậc: có"]
    assert why_not(res, "FAR", s.search_input, CFG)["reasons"][0].startswith("Xa so với")
    assert why_not(res, "NOPE", s.search_input, CFG)["known"] is False


def test_month_only_trip_without_days_runs():
    v = run(session(trip(context={"start_date": None, "month": 12, "days": None})), data(), CFG).view
    assert v["feasibility"]["status"] == "feasible" or v["feasibility"]["status"] == "unknown"
    assert v["known_days"] is False and v["days"][0]["weekday"] is None


def test_suggested_card_after_gap_answer():
    s = session(state=State(suggest_group="chill"))
    cards = [c for g in run(s, data(), CFG).view["groups"] for c in g["cards"]]
    assert [c["id"] for c in cards if c["suggested"]] == [next(c["id"] for c in cards if c["group"] == "chill")]


def test_output_roles_backup_and_context():
    s = session(trip(anchors=[{"place_id": "FLAT1", "priority": "must"}]),
                State(selected=["FLAT1", "CAFE0"], locked=["FLAT1"], relaxed=[("CAFE0", "noise")]))
    s.log.append({"version": 1, "action": {"type": "select", "place_id": "CAFE0"}})
    out = build(s, run(s, data(), CFG), CFG)
    assert [(c["id"], c["role"]) for c in out["confirmed"]] == [("FLAT1", "anchor"), ("CAFE0", "selected")]
    assert out["confirmed"][1]["relaxed"] == ["noise"]
    assert {b["id"] for b in out["backup_pool"]} >= {"FLAT2"} and out["trip_context"]["context"]["days"] == 2
    assert out["decision_log"][0]["action"]["place_id"] == "CAFE0"
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_pipeline.py`
Expected: FAIL `No module named 'decision.pipeline'`.

- [ ] **Step 3: Cài đặt**

`src/decision/pipeline.py`:

```python
"""Runs ③–⑨ on a session (docs/PLACE_DECISION.md §3) and builds the view the web shows. Everything re-runs on each
change (~1.4k records are cheap); the session state (chosen / locked / dropped) is what keeps the invariants."""

from collections import Counter
from dataclasses import dataclass, field

from corpus.serving import load as load_records

from .cards import card, feature_label, value_label
from .curation import pending
from .diversify import display_group, pick, sizes
from .feasibility import evaluate
from .fit import centers, fit
from .model import Cand, role_of
from .rank import score
from .screen import screen
from .trip_days import trip_days

MISSING_NAME = "Địa điểm chưa có trong dữ liệu"


@dataclass
class Data:
    records: list[dict]
    by_id: dict = field(init=False)

    def __post_init__(self):
        self.by_id = {r["id"]: r for r in self.records}

    @classmethod
    def load(cls) -> "Data":
        return cls(load_records())


@dataclass
class Result:
    view: dict
    cands: dict[str, Cand]
    alternatives: dict[str, list[str]]
    group_of: dict[str, str]
    days: list


def stub(pid: str) -> dict:
    """A kept place without a serving record: every aspect unknown."""
    return {"id": pid, "status": "VERIFIED", "status_reason": None,
            "identity": {"name": MISSING_NAME, "kind": "POI", "category": None, "category_group": None, "lat": None,
                         "lng": None, "address": None, "area": None},
            "operation": {"hours": None, "price_per_person": None, "entry_fee": None, "visit_minutes": None,
                          "booking": None, "crowd_by_time": None},
            "experience": {}, "environment": {}, "service": {}, "effort": {}, "suitability": {},
            "effort_hint": {"value": "unknown", "kind": "estimate"}, "usable_as": [],
            "provenance": {"as_of": None, "coverage": {}, "voices": 0, "rating_trend": None, "inputs": []},
            "near_duplicate_group": None}


def wanted(si, profile) -> list[str]:
    return list(dict.fromkeys([w.feature for w in si.soft_weights if w.weight > 0]
                              + [x.feature for x in profile.soft if x.weight > 0]))


def _rule_label(reason: str, si, cfg) -> str:
    if reason == "closed_all_trip_days":
        return "Đóng cửa mọi ngày của chuyến"
    f = reason.split(":", 1)[1]
    h = next((x for x in si.hard_filters if x.feature == f), None)
    op = "=" if h and h.op == "eq" else "≠"
    return f"Điều kiện “{feature_label(f, cfg).lower()} {op} {value_label(h.value, cfg) if h else '?'}”"


def run(s, data: Data, cfg) -> Result:
    si, st = s.search_input, s.state
    days = trip_days(si.context, cfg)
    known_days = si.context.days is not None
    wish = set(st.wishlist)
    dropped = {d.place_id for d in st.dropped}
    anchors = [a.place_id for a in si.anchors if a.place_id not in wish | dropped]  # a dropped anchor is gone
    keep = (set(anchors) | set(st.selected)) - wish

    cands: dict[str, Cand] = {}
    for r in data.records:
        role = role_of(r)
        if role or r["id"] in keep:
            cands[r["id"]] = Cand(r, role or "experience", keep=r["id"] in keep)
    for pid in sorted(keep - cands.keys()):
        cands[pid] = Cand(stub(pid), "experience", keep=True, missing=True)
    relaxed = {tuple(x) for x in st.relaxed}
    for c in cands.values():
        screen(c, si, days, relaxed)

    ctrs = centers(si, data.by_id, cfg)
    anchor_areas = {a for pid in anchors if (a := cands[pid].rec["identity"].get("area"))}
    live = [c for c in cands.values() if c.status != "excluded" or c.keep]
    for c in live:
        fit(c, si, days, ctrs, anchor_areas, st.profile, cfg)
    score(live, si, st.profile, cfg)
    group_of = {c.id: display_group(c, cfg) for c in live}

    visited = set(si.novelty.visited) | set(st.profile.visited)
    pool = [c for c in live if not c.keep and c.status == "main" and c.id not in dropped and c.id not in wish
            and c.fit >= cfg.min_context_fit and not (si.novelty.level == "new" and c.id in visited)]
    chosen = [cands[i] for i in st.selected if i in cands]
    size = sizes(si, len(days), sum(1 for a in anchors if cands[a].role == "experience"), cfg)
    reps, alts = [], {}
    for role in ("experience", "meal"):
        k = size[role] - sum(1 for c in chosen if c.role == role and c.id not in anchors)
        r_, a_ = pick([c for c in pool if c.role == role], k, cfg)
        reps += r_
        alts.update(a_)
    for c in chosen:
        g = c.rec.get("near_duplicate_group")
        if g is not None and c.id not in alts:
            same = sorted((x for x in pool if x.rec.get("near_duplicate_group") == g), key=lambda x: (-x.score, x.id))
            if same:
                alts[c.id] = same[:3]

    suggested = next((c.id for c in reps if group_of[c.id] == st.suggest_group), None) if st.suggest_group else None
    want = wanted(si, st.profile)
    labels = cfg.labels["group"]

    def mk(c: Cand) -> dict:
        return card(c, si, cfg, wanted=want, chosen=c.id in st.selected, locked=c.id in st.locked,
                    anchor=c.id in anchors, alternatives=[(x.id, x.name) for x in alts.get(c.id, [])],
                    suggested=c.id == suggested, group=group_of.get(c.id, "sights"))

    groups = []
    if anchors:
        groups.append({"id": "anchors", "label": labels["anchors"], "cards": [mk(cands[a]) for a in anchors]})
    for gid in [*cfg.display_groups, "meal"]:
        here = [c for c in chosen if c.id not in anchors and group_of.get(c.id) == gid]
        here += [c for c in reps if group_of[c.id] == gid]
        if here:
            groups.append({"id": gid, "label": labels[gid], "cards": [mk(c) for c in here]})

    unverified = sorted((c for c in live if not c.keep and c.status == "unverified" and c.id not in dropped),
                        key=lambda c: (-c.score, c.id))
    excluded = Counter(x["reason"] for c in cands.values() if c.status == "excluded" and not c.keep
                       for x in c.checks if x["result"] == "fail")
    feas = evaluate(chosen, si, days, known_days, set(anchors), set(st.locked), ctrs,
                    {f for f in want if f in cfg.timed_features}, cfg)
    pend = pending(st, data.by_id, si, feas, s.first_shortlist, group_of, cfg)

    def name(pid: str) -> str:
        c = cands.get(pid)
        return c.name if c else (data.by_id.get(pid) or stub(pid))["identity"]["name"]

    def wish_reason(pid: str) -> str:
        c = cands.get(pid)
        if c and any(x["kind"] == "physical" and x["result"] == "fail" for x in c.checks):
            return "Đóng cửa mọi ngày của chuyến"
        return "Bạn để dành cho dịp khác"

    view = {
        "version": len(s.history),
        "groups": groups,
        "shortlist": [x["id"] for g in groups for x in g["cards"]],
        "selected": list(st.selected), "locked": list(st.locked),
        "unverified": {"count": len(unverified), "open": any(h.unknown_policy == "flag" for h in si.hard_filters),
                       "cards": [mk(c) for c in unverified[:cfg.unverified_show]]},
        "excluded": {"by_rule": [{"rule": r, "label": _rule_label(r, si, cfg), "count": n}
                                 for r, n in sorted(excluded.items())]},
        "wishlist": [{"id": p, "name": name(p), "reason": wish_reason(p)} for p in st.wishlist],
        "dropped": [{"id": d.place_id, "name": name(d.place_id), "reason": d.reason} for d in st.dropped],
        "feasibility": feas,
        "pending": pend.model_dump() if pend else None,
        "profile": st.profile.model_dump(),
        "known_days": known_days,
        "days": [{"index": d.index, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday} for d in days],
        "unknowns": list(si.unknowns),
        "unmapped": [*si.unmapped, *st.unmapped],
    }
    return Result(view, cands, {k: [x.id for x in v] for k, v in alts.items()}, group_of, days)


def why_not(res: Result, pid: str, si, cfg) -> dict:
    """Why a place is not in the shortlist (tool explain_exclusion, docs/PLACE_DECISION.md §6.4)."""
    c = res.cands.get(pid)
    if c is None:
        return {"id": pid, "name": None, "known": False, "status": None, "score": None, "parts": {},
                "reasons": ["Nơi này không có trong dữ liệu đang phục vụ hoặc không dùng được cho lịch trình"]}
    v = res.view
    reasons = []
    if pid in v["shortlist"]:
        reasons.append("Nơi này đang có trong gợi ý")
    elif any(d["id"] == pid for d in v["dropped"]):
        reasons.append("Bạn đã bỏ nơi này")
    elif any(w["id"] == pid for w in v["wishlist"]):
        reasons.append("Bạn để nơi này trong danh sách mong muốn")
    else:
        info = card(c, si, cfg)
        reasons += [f"Bị loại: {t}" for t in info["failed"]]
        reasons += [f"{t} (bạn có thể xem trong mục chưa xác minh)" for t in info["unverified"]]
        if not reasons:
            if c.fit < cfg.min_context_fit:
                reasons.append(f"Xa so với {c.center}" + (f" (≈{c.minutes} phút)" if c.minutes else ""))
            elif si.novelty.level == "new" and pid in si.novelty.visited:
                reasons.append("Bạn đã đi nơi này và muốn thử nơi mới")
            elif any(pid in alts for alts in res.alternatives.values()):
                reasons.append("Giống một nơi đang gợi ý; nằm trong phương án thay thế của nơi đó")
            else:
                reasons.append("Điểm phù hợp thấp hơn các nơi đang gợi ý")
    return {"id": pid, "name": c.name, "known": True, "status": c.status, "reasons": reasons, "score": c.score,
            "parts": c.parts}
```

`src/decision/output.py`:

```python
"""⑩ Decision Output (docs/PLACE_DECISION.md §15): the input of Planning & Validation."""

from .cards import warning_text


def build(s, res, cfg) -> dict:
    st, si = s.state, s.search_input
    anchors = {a.place_id for a in si.anchors}
    relaxed: dict[str, list[str]] = {}
    for p, f in st.relaxed:
        relaxed.setdefault(p, []).append(f)
    confirmed = []
    for pid in st.selected:
        c = res.cands.get(pid)
        if c is None:
            continue
        confirmed.append({"id": pid, "name": c.name,
                          "role": "anchor" if pid in anchors else "locked" if pid in st.locked else "selected",
                          "visit": c.rec["operation"].get("visit_minutes"),
                          "flags": [f["text"] for f in c.flags] + [warning_text(w, cfg) for w in c.warnings],
                          "relaxed": relaxed.get(pid, [])})
    backup, seen = [], set(st.selected)
    for pid in st.selected:
        for alt in res.alternatives.get(pid, []):
            if alt not in seen:
                seen.add(alt)
                backup.append({"id": alt, "name": res.cands[alt].name, "for": pid, "reason": "same_kind"})
    for g in res.view["groups"]:
        for x in g["cards"]:
            if x["id"] in seen:
                continue
            seen.add(x["id"])
            codes = [f["code"] for f in res.cands[x["id"]].flags if f["code"] in ("rain", "crowded")]
            backup.append({"id": x["id"], "name": x["name"], "for": None,
                           "reason": f"context:{codes[0]}" if codes else "next_best"})
    return {"confirmed": confirmed, "backup_pool": backup, "wishlist": res.view["wishlist"],
            "trip_context": si.model_dump(mode="json"), "decision_log": list(s.log),
            "feasibility": res.view["feasibility"]}
```

- [ ] **Step 4: Chạy lại**

Run: `python -m pytest -q tests/decision/test_pipeline.py`
Expected: PASS (6 test).

- [ ] **Step 5: Chạy cả thư mục**

Run: `python -m pytest -q tests/decision`
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add src/decision/pipeline.py src/decision/output.py tests/decision/test_pipeline.py
git commit -m "feat(decision): pipeline view, why-not and Decision Output"
```

---

### Task 11: Agent: task `DECISION_TURN`, guard, policy

**Files:**
- Modify: `src/corpus/llm/tasks.py` (thêm `DECISION_TURN` sau `TRIP_TURN`), `src/corpus/llm/__init__.py`
- Create: `src/decision/guard.py`, `src/decision/policy.py`, `src/decision/agent.py`
- Test: `tests/decision/test_guard.py`, `tests/decision/test_agent.py`

**Interfaces:**
- Consumes: `corpus.llm.AGENT`, `Task`; `trip.contains`, `trip.squash` (Task 1); `corpus.ontology.load`.
- Produces:
  - `corpus.llm.DECISION_TURN` (field prompt: `features places profile feasibility pending text`).
  - `guard.TurnPlan(say: str, updates: tuple[PlanUpdate, ...])`, `guard.PlanUpdate(op, place, value, quote)`, `guard.Guarded(actions: list[dict], say: str, log: list[str])`, `guard.names_in(text, name) -> bool`, `guard.guard(plan, text, aliases: dict[str, dict], screen_text: str, name_keys: list[tuple[str, str]]) -> Guarded`.
  - `policy.policy(text, aliases) -> tuple[list[dict], str]`.
  - `agent.AgentError`, `agent.SayStream`, `agent.run_agent(fields, on_say, cfg, open_stream=gemma_stream) -> TurnPlan` (async), `agent.features_text() -> str`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_guard.py`:

```python
from decision.guard import PlanUpdate, TurnPlan, guard, names_in
from decision.policy import policy

ALIASES = {"P1": {"id": "A", "name": "Đồi Chè Cầu Đất"}, "P2": {"id": "B", "name": "Quán Mộc Lan Viên"}}
KEYS = [("doi che cau dat", "A"), ("quan moc lan vien", "B"), ("thac datanla dalat", "Z")]


def plan(*updates, say="Mình đã bỏ nơi đó."):
    return TurnPlan(say=say, updates=tuple(PlanUpdate(op=o, place=p, value=v, quote=q) for o, p, v, q in updates))


def test_names_in_full_or_last_two_words():
    assert names_in("bỏ cầu đất đi", "Đồi Chè Cầu Đất") and names_in("đồi chè cầu đất", "Đồi Chè Cầu Đất")
    assert not names_in("bỏ đồi chè", "Đồi Chè Cầu Đất")


def test_updates_become_actions():
    text = "Cầu Đất xa quá, thêm Lan Viên, muốn chỗ yên tĩnh, tìm chỗ có nhạc nhẹ"
    g = guard(plan(("drop", "P1", "far", "Cầu Đất xa quá"), ("select", "P2", "", "thêm Lan Viên"),
                   ("soft", "", "noise=quiet:love", "muốn chỗ yên tĩnh"), ("unmapped", "", "nhạc nhẹ", "nhạc nhẹ"),
                   ("crowd", "", "", "chỗ yên tĩnh")), text, ALIASES, "", KEYS)
    assert g.actions == [{"type": "drop", "place_id": "A", "reason": "far"}, {"type": "select", "place_id": "B"},
                         {"type": "prefer", "feature": "noise", "value": "quiet", "weight": 1},
                         {"type": "note", "phrase": "nhạc nhẹ"}, {"type": "feedback", "reason": "crowded"}]
    assert g.say == "Mình đã bỏ nơi đó." and g.log == []


def test_bad_updates_are_dropped_and_logged():
    text = "bỏ nơi thứ hai đi"
    g = guard(plan(("drop", "P9", "", "bỏ nơi thứ hai"), ("drop", "P1", "", "không có câu này"),
                   ("select", "P2", "", "bỏ nơi thứ hai"), ("drop", "", "", "bỏ nơi thứ hai"),
                   ("soft", "", "noise=purple:love", "bỏ nơi thứ hai")), text, ALIASES, "", KEYS)
    assert g.actions == [{"type": "note", "phrase": "bỏ nơi thứ hai"}] and len(g.log) == 5


def test_say_with_unseen_numbers_or_places_is_replaced():
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, "", KEYS).say == ""
    assert guard(plan(say="Còn 45 phút trống."), "bỏ đi", ALIASES, "dư 45 phút", KEYS).say == "Còn 45 phút trống."
    assert guard(plan(say="Thử Thác Datanla Dalat nhé"), "bỏ đi", ALIASES, "", KEYS).say == ""
    assert guard(plan(say="Đồi Chè Cầu Đất đã bỏ"), "bỏ đi", ALIASES, "", KEYS).say == "Đồi Chè Cầu Đất đã bỏ"


def test_policy_keywords_and_names():
    assert policy("Cầu Đất xa quá", ALIASES)[0] == [{"type": "drop", "place_id": "A", "reason": "far"}]
    assert policy("Lan Viên mình đi rồi", ALIASES)[0] == [{"type": "drop", "place_id": "B", "reason": "visited"}]
    assert policy("muốn chỗ ít người hơn", ALIASES)[0] == [{"type": "feedback", "reason": "crowded"}]
    actions, say = policy("ừm", ALIASES)
    assert actions == [] and "chưa hiểu" in say
```

`tests/decision/test_agent.py`:

```python
import asyncio
import json

import pytest

from decision.agent import AgentError, SayStream, run_agent
from decision.settings import default

CFG = default()
PLAN = {"say": "Mình đã bỏ Cầu Đất.", "updates": [{"op": "drop", "place": "P1", "value": "far", "quote": "xa"}]}


def stream_of(chunks, delay=0.0, first_delay=0.0):
    async def gen():
        await asyncio.sleep(first_delay)
        for c in chunks:
            await asyncio.sleep(delay)
            yield c
    return lambda fields: gen()


def chunks(obj, n=7):
    s = json.dumps(obj, ensure_ascii=False)
    return [s[i:i + n] for i in range(0, len(s), n)]


def test_say_stream_extracts_text_as_it_arrives():
    s = SayStream()
    got = "".join(s.feed(c) for c in chunks(PLAN, 3))
    assert got == "Mình đã bỏ Cầu Đất."


def test_run_agent_streams_say_and_returns_plan():
    said = []
    p = asyncio.run(run_agent({}, said.append, CFG, stream_of(chunks(PLAN))))
    assert "".join(said) == PLAN["say"] and p.updates[0].place == "P1"


def test_errors_become_agent_error():
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of(['{"say": "x"'])))  # broken JSON
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, CFG, stream_of([" " * 40, " " * 40])))  # whitespace loop twice
    slow = type(CFG)(**{**CFG.__dict__, "first_token_s": 0.05})
    with pytest.raises(AgentError):
        asyncio.run(run_agent({}, lambda s: None, slow, stream_of(chunks(PLAN), first_delay=0.3)))
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_guard.py tests/decision/test_agent.py`
Expected: FAIL `No module named 'decision.guard'`.

- [ ] **Step 3: Thêm task LLM**

`src/corpus/llm/tasks.py`, ngay sau khối `TRIP_TURN = Task(...)`:

```python
DECISION_OPS = ["select", "drop", "lock", "travel", "crowd", "price", "soft", "visited", "unmapped"]

DECISION_TURN = Task(
    name="decision_turn",
    role=AGENT,
    max_tokens=700,
    temperature=0.2,
    parallel=4,
    # `say` first: the server streams it before the updates arrive (src/decision/agent.py).
    schema={
        "type": "object",
        "properties": {
            "say": {"type": "string"},
            "updates": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": DECISION_OPS},
                    "place": {"type": "string"},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["op", "place", "value", "quote"],
                "additionalProperties": False,
            }},
        },
        "required": ["say", "updates"],
        "additionalProperties": False,
    },
    prompt="""You help a traveller choose the places for a trip to Đà Lạt, Vietnam. The places on screen are listed
under PLACES with an alias (P1, P2, ...). In this turn: understand the user's latest message, turn what it asks
into updates, and reply.

`say` (Vietnamese): 1-2 short sentences, warm but not chummy, "mình" for yourself and "bạn" for the user, no slang,
no emoji. Say what you changed or understood. Name a place only with a name from PLACES. Never state a number or a
fact that is not in PLACES or in the user's message. If OPEN QUESTION is not "none", end by pointing the user to it.

`updates`: one entry per request in the message.
- select | lock: the user wants place `place` in the trip (lock: must keep it). value "".
- drop: the user does not want `place`; value = the reason if stated: far | crowded | pricey | dislike | visited,
  else "".
- visited: the user has been to `place` already. value "".
- travel | crowd | price: the user wants places closer | less crowded | cheaper in general, no single place. value "".
- soft: a wish about the kind of place: value "feature=value:love" or "feature=value:avoid", ids from FEATURES only.
- unmapped: a wish FEATURES cannot express; value = the user's words.
- place: an alias from PLACES, or "" when the update is about no single place.
- quote: the exact words from the user's message that support the update, copied, not paraphrased.
- When unsure, leave it out. Never invent a place.

FEATURES (id: values)
{features}

PLACES (alias | name | group | chosen | notes)
{places}

SESSION PROFILE: {profile}
FEASIBILITY: {feasibility}
OPEN QUESTION: {pending}

USER MESSAGE:
{text}""",
)
```

`src/corpus/llm/__init__.py`: thêm `DECISION_TURN` vào dòng import từ `.tasks` và vào `__all__`:

```python
from .tasks import (ASR_CHECK, DECISION_TURN, PLACE_FILTER, PLACE_QC, PLACE_VIDEO_FILTER, PHOTO_OBSERVE, PHOTO_VERIFY,
                    PLACE_VIDEO_VERIFY, REVIEW_OBSERVE, REVIEW_VERIFY,
                    TRIP_TURN, VIDEO_FILTER, VIDEO_OBSERVE, VIDEO_VERIFY, Task)

__all__ = ["AGENT", "ASR_CHECK", "DECISION_TURN", "EXTRACTOR", "JUDGE", "PLACE_FILTER", "PLACE_QC", "PLACE_VIDEO_FILTER",
           "PHOTO_OBSERVE", "PHOTO_VERIFY", "PLACE_VIDEO_VERIFY", "REVIEW_OBSERVE", "REVIEW_VERIFY", "Role", "TRIP_TURN",
           "Task", "VIDEO_FILTER", "VIDEO_OBSERVE", "VIDEO_VERIFY"]
```

- [ ] **Step 4: Cài đặt guard, policy, agent**

`src/decision/guard.py`:

```python
"""Checks an agent TurnPlan before it touches the session (spec §14): quotes come from the message, aliases are on
screen, values are in the allowed sets; `say` holds no number or place name the user and the screen do not hold."""

import re
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from corpus.ontology import load
from trip import contains, squash

Op = Literal["select", "drop", "lock", "travel", "crowd", "price", "soft", "visited", "unmapped"]
FEEDBACK = {"travel": "far", "crowd": "crowded", "price": "pricey"}
REASONS = ("far", "crowded", "pricey", "dislike", "visited")
PLACE_OPS = {"select", "lock", "drop", "visited"}


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlanUpdate(Frozen):
    op: Op
    place: str
    value: str
    quote: str


class TurnPlan(Frozen):
    say: str
    updates: tuple[PlanUpdate, ...] = ()


@dataclass
class Guarded:
    actions: list[dict]
    say: str
    log: list[str] = field(default_factory=list)


@cache
def _ontology():
    return load()


def names_in(text: str, name: str) -> bool:
    """The user named this place: its whole name, or its last two words (the distinctive part of most names)."""
    words = squash(name).split()
    return contains(text, name) or (len(words) >= 2 and contains(text, " ".join(words[-2:])))


def guard(plan: TurnPlan, text: str, aliases: dict[str, dict], screen_text: str,
          name_keys: list[tuple[str, str]]) -> Guarded:
    """aliases: "P1" -> {"id", "name", ...}; screen_text: what the user sees (its numbers may be repeated);
    name_keys: (squashed name, id) of every place whose name is long enough to recognise in text."""
    log, actions = [], []
    for u in plan.updates:
        if not contains(text, u.quote):
            log.append(f"drop {u.op}: quote {u.quote!r} not in the message")
            continue
        place = aliases.get(u.place) if u.place else None
        if u.place and place is None:
            log.append(f"drop {u.op}: unknown alias {u.place!r}")
            continue
        if u.op in PLACE_OPS and place is None:
            log.append(f"drop {u.op}: needs a place")
            continue
        if u.op in ("select", "lock") and not names_in(text, place["name"]):
            log.append(f"drop {u.op}: the user did not name {place['name']!r}")
            continue
        if u.op in ("select", "lock"):
            actions.append({"type": u.op, "place_id": place["id"]})
        elif u.op == "drop":
            actions.append({"type": "drop", "place_id": place["id"], "reason": u.value if u.value in REASONS else None})
        elif u.op == "visited":
            actions.append({"type": "drop", "place_id": place["id"], "reason": "visited"})
        elif u.op in FEEDBACK:
            actions.append({"type": "feedback", "reason": FEEDBACK[u.op]})
        elif u.op == "soft":
            m = re.fullmatch(r"([a-z_]+)=([a-z_]+):(love|avoid)", u.value.strip())
            if m and _ontology().valid(m[1], m[2]):
                actions.append({"type": "prefer", "feature": m[1], "value": m[2], "weight": 1 if m[3] == "love" else -1})
            else:
                log.append(f"unmapped soft {u.value!r}")
                actions.append({"type": "note", "phrase": u.quote})
        elif u.op == "unmapped" and u.value.strip():
            actions.append({"type": "note", "phrase": u.value.strip()})
    say = plan.say.strip()
    why = _bad_say(say, f"{text} {screen_text}", aliases, name_keys)
    if why:
        log.append(f"say replaced: {why}")
        say = ""
    return Guarded(actions, say, log)


def _bad_say(say: str, heard: str, aliases: dict[str, dict], name_keys) -> str | None:
    said = set(re.findall(r"\d+", heard))
    extra = [n for n in re.findall(r"\d+", say) if n not in said]
    if extra:
        return f"numbers {extra} not said or shown"
    shown = {a["id"] for a in aliases.values()}
    s = f" {squash(say)} "
    for key, pid in name_keys:
        if pid not in shown and f" {key} " in s:
            return f"names place {pid}"
    return None
```

> Ghi chú cho test `test_bad_updates_are_dropped_and_logged`: 5 log = alias lạ, quote lạ, `select` không nêu tên, `drop` thiếu nơi, soft sai (soft sai vẫn thành `note` với quote).

`src/decision/policy.py`:

```python
"""Fallback when the agent fails (docs/ARCHITECTURE.md §18.4): keywords + names on screen -> the same actions."""

from trip import contains

from .guard import names_in

KEYWORDS = (("visited", ("di roi", "den roi", "toi roi", "da di")),
            ("pricey", ("dat qua", "mac qua", "gia cao", "dat do")),
            ("crowded", ("dong qua", "dong nguoi", "it nguoi", "vang hon")),
            ("far", ("xa qua", "xa", "gan hon")),
            ("dislike", ("khong thich", "chan")))
DONE = "Mình đã ghi nhận, danh sách đã cập nhật."
NONE = "Mình chưa hiểu ý bạn. Bạn bấm Bỏ qua hoặc Thêm trên thẻ giúp mình nhé."


def policy(text: str, aliases: dict[str, dict]) -> tuple[list[dict], str]:
    reason = next((r for r, keys in KEYWORDS if any(contains(text, k) for k in keys)), None)
    place = next((a for a in aliases.values() if names_in(text, a["name"])), None)
    if place and reason:
        return [{"type": "drop", "place_id": place["id"], "reason": reason}], DONE
    if reason in ("far", "crowded", "pricey"):
        return [{"type": "feedback", "reason": reason}], DONE
    return [], NONE
```

> Từ khóa khớp theo cụm từ nguyên vẹn sau `squash` ("đi rồi" → "di roi"), nên "mình đi Lan Viên rồi" không khớp; câu test dùng "Lan Viên mình đi rồi".

`src/decision/agent.py`:

```python
"""One agent call per typed message on the curation screen (spec §14): prompt from the current view, streamed `say`,
typed plan. Same streaming guards as src/trip/agent.py, kept here: modules only meet through public APIs."""

import asyncio
import functools
import json
import re
from typing import AsyncIterator, Callable

from pydantic import ValidationError

from corpus.llm import AGENT, DECISION_TURN
from corpus.ontology import load

from .guard import TurnPlan

LOOP_WS = 32  # guided decoding now and then emits whitespace until max_tokens; this many in a row means it started


class AgentError(Exception):
    """No usable plan in time; the turn falls back to the policy."""


class SayStream:
    """Pulls the "say" string out of a JSON object while it streams in."""

    def __init__(self):
        self.buf = ""
        self.sent = 0

    def feed(self, delta: str) -> str:
        self.buf += delta
        m = re.search(r'"say"\s*:\s*"', self.buf)
        if not m:
            return ""
        raw = self.buf[m.end():]
        end = _closing_quote(raw)
        raw = raw[:end] if end is not None else _trim_partial_escape(raw)
        try:
            text = json.loads('"' + raw + '"')
        except json.JSONDecodeError:
            return ""
        new, self.sent = text[self.sent:], max(self.sent, len(text))
        return new


def _closing_quote(raw: str) -> int | None:
    i = 0
    while i < len(raw):
        if raw[i] == "\\":
            i += 2
            continue
        if raw[i] == '"':
            return i
        i += 1
    return None


def _trim_partial_escape(raw: str) -> str:
    m = re.search(r"\\u[0-9a-fA-F]{0,3}$", raw)
    if m:
        return raw[:m.start()]
    tail = len(raw) - len(raw.rstrip("\\"))
    return raw[:-1] if tail % 2 else raw


@functools.cache
def features_text() -> str:
    return "\n".join(f"{f.id}: {'|'.join(f.values)}" for f in load().features.values())


def gemma_stream(fields: dict) -> AsyncIterator[str]:
    async def gen():
        client, model = AGENT.client()
        try:
            async for d in DECISION_TURN.stream(client, model, **fields):
                yield d
        finally:
            await client.close()
    return gen()


class _Looping(AgentError):
    pass


async def run_agent(fields: dict, on_say: Callable[[str], None], cfg,
                    open_stream: Callable[[dict], AsyncIterator[str]] = gemma_stream) -> TurnPlan:
    """One call, or two when the first loops on whitespace; the second does not stream its say again."""
    deadline = asyncio.get_running_loop().time() + cfg.total_s
    try:
        return await _attempt(fields, on_say, cfg, open_stream, deadline)
    except _Looping:
        try:
            return await _attempt(fields, lambda s: None, cfg, open_stream, deadline)
        except _Looping as e:
            raise AgentError("output looped on whitespace twice") from e


async def _attempt(fields, on_say, cfg, open_stream, deadline) -> TurnPlan:
    loop = asyncio.get_running_loop()
    it = open_stream(fields).__aiter__()
    say, buf, first = SayStream(), [], True
    try:
        while True:
            timeout = cfg.first_token_s if first else deadline - loop.time()
            if timeout <= 0:
                raise AgentError(f"no complete answer in {cfg.total_s:.0f} s")
            try:
                delta = await asyncio.wait_for(it.__anext__(), timeout)
            except StopAsyncIteration:
                break
            first = False
            buf.append(delta)
            if new := say.feed(delta):
                on_say(new)
            tail = "".join(buf[-LOOP_WS:])[-LOOP_WS:]
            if len(tail) == LOOP_WS and not tail.strip():
                raise _Looping("whitespace loop")
    except asyncio.TimeoutError as e:
        raise AgentError("first token too slow" if first else "answer too slow") from e
    except AgentError:
        raise
    except Exception as e:  # openai errors, and httpx / OS errors a dropped stream raises unwrapped
        raise AgentError(f"{type(e).__name__}: {e}") from e
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    try:
        return TurnPlan.model_validate_json("".join(buf))
    except ValidationError as e:
        raise AgentError(f"bad plan: {str(e).splitlines()[0]}") from e
```

- [ ] **Step 5: Chạy lại**

Run: `python -m pytest -q tests/decision/test_guard.py tests/decision/test_agent.py tests/test_llm_task.py`
Expected: PASS. (`tests/test_llm_task.py` là test cũ của các task, phải vẫn pass.)

- [ ] **Step 6: Commit**

```bash
git add src/corpus/llm/tasks.py src/corpus/llm/__init__.py src/decision/guard.py src/decision/policy.py src/decision/agent.py tests/decision/test_guard.py tests/decision/test_agent.py
git commit -m "feat(decision): DECISION_TURN agent with quote and alias guard and keyword fallback"
```

---

### Task 12: Engine, HTTP + SSE, `python -m decision serve`

**Files:**
- Create: `src/decision/engine.py`, `src/decision/server.py`, `src/decision/__main__.py`
- Modify: `src/decision/__init__.py`
- Test: `tests/decision/test_engine.py`, `tests/decision/test_server.py`

**Interfaces:**
- Consumes: Task 2–11.
- Produces:
  - `engine.Engine(data, cfg, store, agent=None)`; `agent(fields, on_say) -> Awaitable[TurnPlan]`.
  - Methods: `create(search_input: dict, trip_session=None) -> {id, view}`, `load(sid) -> {id, view}`, `act(sid, action) -> {view, diff, goto?}`, `turn(sid, text, emit)`, `compare(sid, a, b) -> dict`, `why_not(sid, pid) -> dict`, `confirm(sid) -> dict`.
  - Exceptions: `engine.NoSession`, `engine.VersionMismatch`, `engine.NotConfirmable`; `curation.ActionError` (400).
  - `engine.diff(before_view, after_view, scope) -> {added, removed, status: [before, after], delta{places, visit, travel}, text, scope}`.
  - `server.handler(engine)`, `server.run(engine, port=8767)`.
  - `decision.__init__`: `Data, Engine, Settings, Store, load_settings, run_pipeline`.

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_engine.py`:

```python
import threading

import pytest
from fixtures import hard, love, si, srec

from decision.agent import AgentError
from decision.curation import ActionError
from decision.engine import Engine, NoSession, NotConfirmable, VersionMismatch
from decision.guard import PlanUpdate, TurnPlan
from decision.pipeline import Data
from decision.session import Store
from decision.settings import default

CFG = default()


def data():
    recs = [srec(f"C{i}", name=f"Quán Cà Phê Số {i}", features={"scenic_view": "present", "steep_or_stairs": "absent"},
                 lng=108.44 + i / 1000) for i in range(6)]
    return Data(recs + [srec("M", name="Quán Ăn Bình Dân", usable=("meal",))])


def trip(**over):
    return si(hard_filters=[hard("steep_or_stairs", "present")], soft_weights=[love("scenic_view")], **over).model_dump(mode="json")


class FakeAgent:
    def __init__(self, plan=None, error=None):
        self.plan, self.error, self.calls = plan, error, []

    async def __call__(self, fields, on_say):
        self.calls.append(fields)
        if self.error:
            raise self.error
        on_say(self.plan.say)
        return self.plan


def engine(agent=None):
    return Engine(data(), CFG, Store(None), agent)


def test_create_selects_anchors_and_counts_first_shortlist():
    e = engine()
    out = e.create(trip(anchors=[{"place_id": "C0", "priority": "must"}]))
    s = e.store.get(out["id"])
    assert s.state.selected == ["C0"] and s.state.locked == ["C0"] and s.first_shortlist == len(out["view"]["shortlist"])
    with pytest.raises(VersionMismatch):
        e.create({**trip(), "ontology_version": 1})


def test_act_versions_diff_and_undo():
    e = engine()
    sid = e.create(trip())["id"]
    r = e.act(sid, {"type": "select", "place_id": "C1"})
    assert r["view"]["selected"] == ["C1"] and r["diff"]["delta"]["places"] == 1 and r["diff"]["scope"]["from"] == "diversify"
    assert r["diff"]["text"].startswith("+1 nơi")
    r = e.act(sid, {"type": "undo"})
    assert r["view"]["selected"] == [] and len(e.store.get(sid).log) == 2
    with pytest.raises(ActionError):
        e.act(sid, {"type": "undo"})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "select", "place_id": "NOPE"})
    assert e.store.get(sid).history == []
    with pytest.raises(NoSession):
        e.act("0123456789ab", {"type": "undo"})


def test_parallel_acts_keep_every_step():
    e = engine()
    sid = e.create(trip())["id"]
    ts = [threading.Thread(target=e.act, args=(sid, {"type": "select", "place_id": f"C{i}"})) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    s = e.store.get(sid)
    assert sorted(s.state.selected) == ["C0", "C1", "C2", "C3"] and len(s.history) == 4


def test_turn_with_agent_applies_guarded_actions():
    plan = TurnPlan(say="Mình đã bỏ quán đó.", updates=(PlanUpdate(op="drop", place="P1", value="far", quote="xa quá"),))
    agent = FakeAgent(plan)
    e = engine(agent)
    sid = e.create(trip())["id"]
    first = e.load(sid)["view"]["shortlist"][0]
    events = []
    e.turn(sid, "quán đầu xa quá", lambda ev, d: events.append((ev, d)))
    assert [ev for ev, _ in events] == ["say", "view", "done"]
    view = events[1][1]["view"]
    assert view["dropped"] == [{"id": first, "name": view["dropped"][0]["name"], "reason": "far"}]
    assert "P1 |" in agent.calls[0]["places"] and e.store.get(sid).state.profile.travel_mult == CFG.far_step


def test_turn_falls_back_to_policy():
    e = engine(FakeAgent(error=AgentError("down")))
    sid = e.create(trip())["id"]
    events = []
    e.turn(sid, "Quán Cà Phê Số 2 xa quá", lambda ev, d: events.append((ev, d)))
    assert events[0] == ("say", {"replace": "Mình đã ghi nhận, danh sách đã cập nhật."})
    assert e.store.get(sid).state.dropped[0].place_id == "C2"


def test_compare_why_not_confirm():
    e = engine()
    sid = e.create(trip(context={"days": 1}))["id"]
    assert e.compare(sid, "C0", "C1")["a"]["id"] == "C0"
    with pytest.raises(ActionError):
        e.compare(sid, "C0", "NOPE")
    assert e.why_not(sid, "NOPE")["known"] is False
    e.act(sid, {"type": "select", "place_id": "C0"})
    out = e.confirm(sid)
    assert out["confirmed"][0]["id"] == "C0" and e.store.get(sid).output == out
    for i in range(1, 6):
        e.act(sid, {"type": "select", "place_id": f"C{i}"})
    with pytest.raises(NotConfirmable):
        e.confirm(sid)


def test_rethink_back_sends_the_user_to_understanding():
    e = engine()
    sid = e.create(trip())["id"]
    s = e.store.get(sid)
    s.first_shortlist = 2
    for i in range(6):
        e.act(sid, {"type": "drop", "place_id": f"C{i}"})
    view = e.load(sid)["view"]
    assert view["pending"]["qid"] == "rethink"
    assert e.act(sid, {"type": "answer", "qid": "rethink", "chip": "back"})["goto"] == "understand"
```

`tests/decision/test_server.py`:

```python
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from test_engine import engine, trip

from decision.server import handler


@pytest.fixture
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(engine()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/decision/sessions"
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


def get(url):
    return json.load(urllib.request.urlopen(url, timeout=10))


def code(fn):
    with pytest.raises(urllib.error.HTTPError) as e:
        fn()
    return e.value.code


def test_session_flow(base):
    v = json.load(post(base, {"search_input": trip()}))
    sid = v["id"]
    assert get(f"{base}/{sid}")["view"]["shortlist"] == v["view"]["shortlist"]
    r = json.load(post(f"{base}/{sid}/act", {"type": "select", "place_id": "C0"}))
    assert r["view"]["selected"] == ["C0"]
    assert get(f"{base}/{sid}/compare?a=C0&b=C1")["b"]["id"] == "C1"
    assert get(f"{base}/{sid}/why-not/C0")["reasons"] == ["Nơi này đang có trong gợi ý"]
    t = post(f"{base}/{sid}/turn", {"text": "Quán Cà Phê Số 1 xa quá"})
    assert t.headers["Content-Type"].startswith("text/event-stream")
    events = [l[7:] for l in t.read().decode().splitlines() if l.startswith("event: ")]
    assert events == ["say", "view", "done"]
    assert json.load(post(f"{base}/{sid}/confirm", {}))["confirmed"][0]["id"] == "C0"


def test_errors(base):
    sid = json.load(post(base, {"search_input": trip()}))["id"]
    assert code(lambda: post(base, {"search_input": {"bad": 1}})) == 400
    assert code(lambda: post(base, {"search_input": {**trip(), "ontology_version": 1}})) == 409
    assert code(lambda: get(f"{base}/0123456789ab")) == 404
    assert code(lambda: post(f"{base}/{sid}/act", {"type": "drop", "place_id": "C0", "reason": "ugly"})) == 400
    assert code(lambda: post(f"{base}/{sid}/turn", {"text": ""})) == 400
    assert code(lambda: get(f"{base}/../../etc")) == 404
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_engine.py tests/decision/test_server.py`
Expected: FAIL `No module named 'decision.engine'`.

- [ ] **Step 3: Cài đặt engine**

`src/decision/engine.py`:

```python
"""Place Decision sessions for the web (spec §13-16): create, act (chips / buttons, no model), turn (typed text, one
agent call), compare, why-not, confirm. One lock per session; each change is one version that undo restores."""

import asyncio
import json
from datetime import datetime, timezone
from functools import cache
from typing import Awaitable, Callable

from corpus.ontology import load as load_ontology
from trip import SearchInput, squash

from . import output
from .agent import AgentError, features_text
from .compare import compare as compare_cands
from .curation import ActionError, apply
from .guard import TurnPlan, guard
from .pipeline import Data, Result, run, wanted, why_not
from .policy import policy
from .scope import STEPS, replan_scope
from .session import Pending, Session, State, Store
from .settings import Settings

Emit = Callable[[str, dict], None]
Agent = Callable[[dict, Callable[[str], None]], Awaitable[TurnPlan]]


class NoSession(Exception):
    pass


class VersionMismatch(Exception):
    pass


class NotConfirmable(Exception):
    pass


@cache
def _ontology_version() -> int:
    return load_ontology().version


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def diff(before: dict, after: dict, scope: dict | None) -> dict:
    b, a = set(before["shortlist"]), set(after["shortlist"])
    tb, ta = before["feasibility"]["totals"], after["feasibility"]["totals"]
    delta = {k: ta[k] - tb[k] for k in ("places", "visit", "travel")}

    def sign(n: int) -> str:
        return f"+{n}" if n > 0 else str(n)

    return {"added": sorted(a - b), "removed": sorted(b - a),
            "status": [before["feasibility"]["status"], after["feasibility"]["status"]], "delta": delta,
            "text": f"{sign(delta['places'])} nơi, {sign(delta['visit'])} phút tham quan, {sign(delta['travel'])} phút đi lại",
            "scope": scope}


def _earliest(actions: list[dict]) -> dict:
    scopes = [replan_scope(a) for a in actions]
    return min(scopes, key=lambda s: STEPS.index(s["from"]))


class Engine:
    def __init__(self, data: Data, cfg: Settings, store: Store, agent: Agent | None = None):
        self.data, self.cfg, self.store, self.agent = data, cfg, store, agent
        self._results: dict[str, Result] = {}
        self.name_keys = [(k, r["id"]) for r in data.records
                          if len((k := squash(r["identity"].get("name") or "")).split()) >= 3]

    # ---------- helpers ----------

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _result(self, s: Session) -> Result:
        if s.id not in self._results:
            self._results[s.id] = run(s, self.data, self.cfg)
        return self._results[s.id]

    def _apply(self, s: Session, actions: list[dict], before: Result, strict: bool) -> tuple[State, list[dict], list[str]]:
        pend = Pending.model_validate(before.view["pending"]) if before.view["pending"] else None
        known = lambda p: p in before.cands or p in self.data.by_id  # noqa: E731
        st, done, log = s.state, [], []
        for a in actions:
            try:
                st = apply(st, a, known, before.alternatives, pend, self.cfg)
                done.append(a)
            except ActionError as e:
                if strict:
                    raise
                log.append(f"skip {a}: {e}")
        return st, done, log

    def _commit(self, s: Session, before: Result, logged: dict, scope: dict | None) -> dict:
        s.log.append({"version": len(s.history), "action": logged, "scope": scope, "at": _now()})
        self._results.pop(s.id, None)
        after = self._result(s)
        self.store.save(s)
        return {"view": after.view, "diff": diff(before.view, after.view, scope)}

    def _push(self, s: Session, new: State) -> None:
        s.history = (s.history + [s.state])[-self.cfg.history_max:]
        s.state = new

    # ---------- API ----------

    def create(self, search_input: dict, trip_session: str | None = None) -> dict:
        si = SearchInput.model_validate(search_input)
        if si.ontology_version != _ontology_version():
            raise VersionMismatch(f"Search Input ontology v{si.ontology_version}, corpus v{_ontology_version()}")
        st = State(selected=[a.place_id for a in si.anchors],
                   locked=[a.place_id for a in si.anchors if a.priority == "must"])
        s = self.store.new(si, trip_session, st)
        res = self._result(s)
        s.first_shortlist = len(res.view["shortlist"])
        self.store.save(s)
        return {"id": s.id, "view": res.view}

    def load(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return {"id": s.id, "view": self._result(s).view}

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            before = self._result(s)
            if action.get("type") == "undo":
                if not s.history:
                    raise ActionError("nothing to undo")
                s.state = s.history.pop()
            else:
                new, _, _ = self._apply(s, [action], before, strict=True)
                self._push(s, new)
            out = self._commit(s, before, action, replan_scope(action))
            if action.get("type") == "answer" and action.get("qid") == "rethink" and action.get("chip") == "back":
                out["goto"] = "understand"
            return out

    def turn(self, sid: str, text: str, emit: Emit) -> None:
        s = self._get(sid)
        with self.store.lock(sid):
            before = self._result(s)
            aliases = self._aliases(before.view)
            fields = self._fields(before.view, aliases, text)
            streamed: list[str] = []

            def on_say(d: str) -> None:
                streamed.append(d)
                emit("say", {"delta": d})

            try:
                if self.agent is None:
                    raise AgentError("no agent configured")
                g = guard(asyncio.run(self.agent(fields, on_say)), text, aliases,
                          f"{fields['places']} {fields['feasibility']} {fields['pending']}", self.name_keys)
                actions, say, log = g.actions, g.say, g.log
            except AgentError as e:
                (actions, say), log = policy(text, aliases), [f"agent_fallback: {e}"]
            if say != "".join(streamed):
                emit("say", {"replace": say})
            new, done, skipped = self._apply(s, actions, before, strict=False)
            logged = {"type": "turn", "text": text, "actions": done, "log": log + skipped}
            if done:
                self._push(s, new)
                out = self._commit(s, before, logged, _earliest(done))
            else:
                s.log.append({"version": len(s.history), "action": logged, "scope": None, "at": _now()})
                self.store.save(s)
                out = {"view": before.view, "diff": diff(before.view, before.view, None)}
            emit("view", out)
            emit("done", {})

    def compare(self, sid: str, a: str, b: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            res = self._result(s)
            ca, cb = res.cands.get(a), res.cands.get(b)
            if ca is None or cb is None:
                raise ActionError(f"unknown place {a if ca is None else b!r}")
            out = compare_cands(ca, cb, wanted(s.search_input, s.state.profile), res.days, self.cfg)
            s.log.append({"version": len(s.history), "action": {"type": "compare", "a": a, "b": b}, "scope": None,
                          "at": _now()})
            self.store.save(s)
            return out

    def why_not(self, sid: str, pid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return why_not(self._result(s), pid, s.search_input, self.cfg)

    def confirm(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            res = self._result(s)
            status = res.view["feasibility"]["status"]
            if status not in ("feasible", "unknown"):
                raise NotConfirmable(status)
            s.output = output.build(s, res, self.cfg)
            self.store.save(s)
            return s.output

    # ---------- agent prompt ----------

    @staticmethod
    def _aliases(view: dict) -> dict[str, dict]:
        out, seen = {}, set()
        for g in view["groups"]:
            for c in g["cards"]:
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                notes = "; ".join(t["text"] for t in (c["why"] + c["tradeoffs"])[:3])
                out[f"P{len(out) + 1}"] = {"id": c["id"], "name": c["name"], "group": g["label"],
                                           "chosen": c["chosen"], "notes": notes}
        for d in view["dropped"][-5:]:
            if d["id"] not in seen:
                seen.add(d["id"])
                out[f"P{len(out) + 1}"] = {"id": d["id"], "name": d["name"], "group": "-", "chosen": False,
                                           "notes": "đã bỏ"}
        return out

    @staticmethod
    def _fields(view: dict, aliases: dict, text: str) -> dict:
        f = view["feasibility"]
        places = "\n".join(f"{k} | {a['name']} | {a['group']} | {'chosen' if a['chosen'] else '-'} | {a['notes']}"
                           for k, a in aliases.items())
        t = f["totals"]
        return {"features": features_text(), "places": places or "none",
                "profile": json.dumps(view["profile"], ensure_ascii=False),
                "feasibility": f"{f['status']}; {t['places']} nơi; " + "; ".join(c["title"] for c in f["conflicts"][:3]),
                "pending": view["pending"]["text"] if view["pending"] else "none", "text": text}
```

- [ ] **Step 4: Cài đặt server, CLI, public API**

`src/decision/server.py`:

```python
"""HTTP API for the web (spec §16). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from .curation import ActionError
from .engine import Engine, NoSession, NotConfirmable, VersionMismatch

BASE = "/api/decision/sessions"
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
SUB = re.compile(BASE + r"/([0-9a-f]{12})/(act|turn|compare|confirm)")
WHY = re.compile(BASE + r"/([0-9a-f]{12})/why-not/([^/]+)")
MAX_TEXT = 1000


def handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise json.JSONDecodeError("not an object", "", 0)
            return body

        def _call(self, fn) -> None:
            try:
                return self._json(200, fn())
            except NoSession:
                return self._json(404, {"error": "no such session"})
            except (ActionError, ValidationError, ValueError) as e:
                return self._json(400, {"error": str(e).splitlines()[0]})
            except (VersionMismatch, NotConfirmable) as e:
                return self._json(409, {"error": str(e)})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if m := SESSION.fullmatch(url.path):
                return self._call(lambda: engine.load(m[1]))
            if (m := SUB.fullmatch(url.path)) and m[2] == "compare":
                return self._call(lambda: engine.compare(m[1], q.get("a", [""])[0], q.get("b", [""])[0]))
            if m := WHY.fullmatch(url.path):
                return self._call(lambda: engine.why_not(m[1], unquote(m[2])))
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not a JSON object"})
            if path == BASE:
                return self._call(lambda: engine.create(body.get("search_input") or {}, body.get("trip_session")))
            m = SUB.fullmatch(path)
            if m and m[2] == "act":
                return self._call(lambda: engine.act(m[1], body))
            if m and m[2] == "confirm":
                return self._call(lambda: engine.confirm(m[1]))
            if m and m[2] == "turn":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                    return self._json(400, {"error": f"text must be 1-{MAX_TEXT} characters"})
                try:
                    engine.store.get(m[1])
                except KeyError:
                    return self._json(404, {"error": "no such session"})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def emit(event: str, data: dict) -> None:
                    self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()

                try:
                    engine.turn(m[1], text.strip(), emit)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def run(engine: Engine, port: int = 8767) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
```

`src/decision/__main__.py`:

```python
"""python -m decision serve (http://127.0.0.1:8767) | python -m decision evaluate (data/decision/eval.json)."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import run_agent
from .engine import Engine
from .pipeline import Data
from .server import run
from .session import Store
from .settings import ROOT, default


def data_root() -> Path:
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m decision")
    sub = ap.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API the web shortlist / feasibility screens talk to")
    serve.add_argument("--port", type=int, default=8767)
    sub.add_parser("evaluate", help="offline Place Decision check on the serving records")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = default()
    if args.cmd == "evaluate":
        from .evaluate import run as evaluate
        evaluate()
        return
    try:
        data = Data.load()
    except FileNotFoundError:
        sys.exit("no data/serving/places.json: run python -m corpus serving first")
    missing = [k for k in ("AGENT_API_KEY", "AGENT_BASE_URL", "AGENT_MODEL") if not os.environ.get(k)]
    agent = None
    if missing:
        print(f"warning: {', '.join(missing)} missing in .env: typed messages use the keyword fallback", file=sys.stderr)
    else:
        agent = lambda fields, on_say: run_agent(fields, on_say, cfg)  # noqa: E731
    engine = Engine(data, cfg, Store(data_root() / "decision" / "sessions"), agent)
    print(f"Place Decision: http://127.0.0.1:{args.port} ({len(data.records)} places, "
          f"agent {os.environ.get('AGENT_MODEL') if agent else 'off'})")
    run(engine, args.port)


if __name__ == "__main__":
    main()
```

`src/decision/__init__.py`:

```python
"""Place Decision: Search Input + serving records -> confirmed places (docs/PLACE_DECISION.md)."""

from .engine import Engine
from .pipeline import Data
from .pipeline import run as run_pipeline
from .session import Store
from .settings import Settings
from .settings import load as load_settings

__all__ = ["Data", "Engine", "Settings", "Store", "load_settings", "run_pipeline"]
```

- [ ] **Step 5: Chạy lại**

Run: `python -m pytest -q tests/decision`
Expected: PASS toàn bộ. Nếu `test_compare_why_not_confirm` không ném `NotConfirmable` với 6 nơi trong 1 ngày, in `e.load(sid)["view"]["feasibility"]`: 6 × (75 + 20 + 10) + đi lại > 420 phút → `partial`/`infeasible`.

- [ ] **Step 6: Commit**

```bash
git add src/decision tests/decision/test_engine.py tests/decision/test_server.py
git commit -m "feat(decision): engine with versioned actions, agent turns, HTTP and SSE API"
```

---

### Task 13: `python -m decision evaluate` thay `corpus evaluate`; đo trên dữ liệu thật

**Files:**
- Create: `src/decision/evaluate.py`
- Delete: `src/corpus/serving/evaluate.py`
- Modify: `src/corpus/__main__.py` (docstring dòng 1, import dòng 15, parser dòng 79, nhánh dòng 103–104)
- Modify: `tests/serving/test_serving.py` (xóa `test_evaluate_counts_violations_unknowns_and_fill`)
- Test: `tests/decision/test_evaluate.py`

**Interfaces:**
- Consumes: `pipeline.Data`, `pipeline.run`, `session.Session`, `State`; `corpus.serving.check`, `feature`.
- Produces: `evaluate.trips() -> (shortlist_k, list[dict])`, `evaluate.search_input(trip, version) -> SearchInput`, `evaluate.violates(rec, fid, forbidden) -> bool`, `evaluate.evaluate(records=None, cfg=None) -> {summary, trips}`, `evaluate.run() -> dict` (ghi `data/decision/eval.json`).

- [ ] **Step 1: Viết test hỏng**

`tests/decision/test_evaluate.py`:

```python
from fixtures import feat, srec

from decision import evaluate as ev


def test_evaluate_counts_violations_unknowns_and_fill(monkeypatch):
    monkeypatch.setattr(ev, "trips", lambda: (2, [
        {"id": "flat", "role": "experience", "hard": {"steep_or_stairs": "present"}, "soft": {"scenic_view": 1.0}}]))
    safe = srec("S", group="nature", features={"steep_or_stairs": "absent", "scenic_view": "present"})
    disputed = srec("D", group="nature", features={"steep_or_stairs": feat("absent", dist={"absent": 3, "present": 1})})
    steep = srec("X", group="nature", features={"steep_or_stairs": "present"})
    meal = srec("M", features={"steep_or_stairs": "absent"}, usable=("meal",))
    res = ev.evaluate([safe, disputed, steep, meal])
    row = res["trips"][0]
    assert row["shortlist"] == ["S"] and (row["unverified"], row["excluded"]) == (1, 1)
    assert res["summary"]["violations"] == 0 and res["summary"]["unknown_in_main"] == 0
    assert res["summary"]["unfilled_trips"] == ["flat"] and res["summary"]["ms_max"] >= 0
    assert ev.violates(disputed, "steep_or_stairs", "present")


def test_search_input_from_hidden_trip():
    si = ev.search_input({"id": "x", "role": "meal", "hard": {"kids": "unsuitable"}, "soft": {"noise": 1.0}}, 7)
    assert si.hard_filters[0].feature == "kids" and si.soft_weights[0].value == "quiet"
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `python -m pytest -q tests/decision/test_evaluate.py`
Expected: FAIL `cannot import name 'evaluate' from 'decision'`.

- [ ] **Step 3: Cài đặt**

`src/decision/evaluate.py`:

```python
"""Offline check of Place Decision on the serving records (docs/PLACE_DECISION.md §17).

python -m decision evaluate  ->  data/decision/eval.json

Each hidden trip of config/eval_trips.yaml becomes a Search Input (hard -> "!=", soft -> love the feature's first,
good value) and the real pipeline runs. Measured on the shortlist of the trip's role:
- violations: shortlist places whose evidence has ANY author naming a forbidden value, read from the raw
  distribution, not from check() (target 0);
- unknown_in_main: shortlist places with a hard filter not `pass` (target 0, fail-closed);
- near_duplicate_rate, filled (shortlist reached the trip's size), unverified, excluded, ms (pipeline time).
"""

import itertools
import json
import os
import time
from datetime import date
from functools import cache
from pathlib import Path

import yaml

from corpus.ontology import load as load_ontology
from corpus.serving import check, feature
from trip import SearchInput

from .pipeline import Data
from .pipeline import run as run_pipeline
from .session import Session, State
from .settings import ROOT, default

TRIPS = ROOT / "config" / "eval_trips.yaml"
START = date(2026, 12, 14)  # a Monday


@cache
def trips() -> tuple[int, list[dict]]:
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    out = list(raw["trips"])
    for i, (hard, soft) in enumerate(itertools.product(raw["cross"]["filters"], raw["cross"]["prefs"])):
        out.append({"id": f"cross_{i}", "role": "experience", "hard": hard, "soft": soft})
    return raw["shortlist"], out


def search_input(trip: dict, version: int) -> SearchInput:
    ont = load_ontology()
    return SearchInput.model_validate({
        "ontology_version": version,
        "context": {"start_date": START.isoformat(), "month": None, "days": 2, "base": None, "mobility": "motorbike",
                    "companions": [], "people": 2, "arrive_at": None, "leave_at": None, "day_end": None,
                    "budget_vnd": None, "experience": None},
        "hard_filters": [{"feature": f, "op": "ne", "value": v, "unknown_policy": "exclude"}
                         for f, v in trip["hard"].items()],
        "anchors": [],
        "soft_weights": [{"feature": f, "value": ont.features[f].values[0], "context": None, "weight": 1,
                          "source": "user"} for f in trip["soft"]],
        "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
        "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})


def violates(rec: dict, fid: str, forbidden: str) -> bool:
    f = feature(rec, fid)
    return bool(f) and f["distribution"].get(forbidden, 0) > 0


def evaluate(records: list[dict] | None = None, cfg=None) -> dict:
    data = Data(records) if records is not None else Data.load()
    cfg = cfg or default()
    k, all_trips = trips()
    version = load_ontology().version
    rows = []
    for trip in all_trips:
        s = Session(id="0" * 12, search_input=search_input(trip, version), state=State())
        t0 = time.perf_counter()
        res = run_pipeline(s, data, cfg)
        ms = round((time.perf_counter() - t0) * 1000)
        picked = [c["id"] for g in res.view["groups"] if g["id"] != "anchors" for c in g["cards"]
                  if c["role"] == trip["role"]]
        recs = [data.by_id[i] for i in picked]
        violations = [r["id"] for r in recs for f, v in trip["hard"].items() if violates(r, f, v)]
        unknown = [r["id"] for r in recs if any(check(r, f, v) != "pass" for f, v in trip["hard"].items())]
        pairs = list(itertools.combinations(recs, 2))
        dup = sum(1 for a, b in pairs if a.get("near_duplicate_group") is not None
                  and a.get("near_duplicate_group") == b.get("near_duplicate_group"))
        rows.append({"trip": trip["id"], "shortlist": picked, "names": [r["identity"]["name"] for r in recs],
                     "unverified": res.view["unverified"]["count"],
                     "excluded": sum(x["count"] for x in res.view["excluded"]["by_rule"]),
                     "violations": violations, "unknown_in_main": unknown,
                     "near_duplicate_rate": round(dup / len(pairs), 3) if pairs else 0.0,
                     "filled": len(picked) >= k, "ms": ms})
    n = len(rows)
    summary = {"trips": n, "shortlist": k,
               "violations": sum(len(r["violations"]) for r in rows),
               "unknown_in_main": sum(len(r["unknown_in_main"]) for r in rows),
               "near_duplicate_rate": round(sum(r["near_duplicate_rate"] for r in rows) / n, 3) if n else 0.0,
               "filled_rate": round(sum(r["filled"] for r in rows) / n, 3) if n else 0.0,
               "unfilled_trips": [r["trip"] for r in rows if not r["filled"]],
               "ms_max": max((r["ms"] for r in rows), default=0)}
    return {"summary": summary, "trips": rows}


def run() -> dict:
    res = evaluate()
    d = Path(os.environ.get("DATA_DIR", "data"))
    out = (d if d.is_absolute() else ROOT / d) / "decision" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evaluate: {json.dumps(res['summary'], ensure_ascii=False)}")
    return res
```

- [ ] **Step 4: Gỡ bản cũ ở corpus**

```bash
git rm src/corpus/serving/evaluate.py
```

`src/corpus/__main__.py`:
- dòng 1: `"""python -m corpus {login <source> | <source> <phase> | review | aggregate | serving} --city <key> [--headed]`
- xóa dòng `from .serving.evaluate import run as evaluate_run`
- xóa dòng `sub.add_parser("evaluate", help="offline Place Decision check on the serving records").add_argument("--city", default="dalat")`
- xóa hai dòng:

```python
        elif args.cmd == "evaluate":
            evaluate_run(args.city)
```

`tests/serving/test_serving.py`: xóa nguyên hàm `test_evaluate_counts_violations_unknowns_and_fill` (đã chuyển sang `tests/decision/test_evaluate.py`).

- [ ] **Step 5: Chạy test**

Run: `python -m pytest -q tests/decision tests/serving tests/trip`
Expected: PASS toàn bộ.

- [ ] **Step 6: Đo trên dữ liệu thật**

Run: `python -m decision evaluate`
Expected: dòng `evaluate: {...}` có `"violations": 0`, `"unknown_in_main": 0`. Ghi lại `filled_rate`, `near_duplicate_rate`, `ms_max` vào DEV_LOG ở Task 16. Nếu `ms_max` > 1500, đo bước nào chậm bằng `python -X importtime` không cần; dùng:

```bash
python -c "import cProfile,pstats; from decision import evaluate as e; cProfile.run('e.evaluate()', 'prof.out'); pstats.Stats('prof.out').sort_stats('cumtime').print_stats(15)"
```

và báo lại trước khi tối ưu (spec §13: chỉ chạy từng phần nếu đo thấy chậm).

- [ ] **Step 7: Commit**

```bash
git add src/decision/evaluate.py src/corpus/__main__.py tests/serving/test_serving.py tests/decision/test_evaluate.py
git commit -m "feat(decision): offline evaluate runs the real pipeline; drop corpus evaluate"
```

---
### Task 14: Web: client API, provider phiên, chuyển từ Understand sang Place Decision

**Files:**
- Create: `web/src/user/pd/types.ts`, `web/src/user/pd/api.ts`, `web/src/user/pd/decision.tsx`
- Modify: `web/src/user/trip.tsx` (field `decisionId`), `web/src/user/UserApp.tsx`, `web/src/user/screens/Understand.tsx` (handler `done`), `web/vite.config.ts`

**Interfaces:**
- Consumes: HTTP API Task 12; `SearchInput` (`web/src/user/tu/types.ts`, Task 1).
- Produces: `DecisionProvider`, `useDecision() -> { view, diff, error, busy, act(a), say(text, onSay), reload() }`; `api.createDecision`, `loadDecision`, `act`, `compare`, `whyNot`, `confirm`, `sendText`, `DecisionError`; type `Card, Group, View, Diff, Action, Feasibility, Conflict, Fix, Pending, CompareResult, WhyNot, DecisionOutput, DropReason`.

- [ ] **Step 1: Type của API**

`web/src/user/pd/types.ts`:

```ts
// Shapes of the Place Decision API (src/decision/engine.py, pipeline.py, cards.py, feasibility.py).

export type DropReason = 'far' | 'crowded' | 'pricey' | 'dislike' | 'visited'

export interface Claim {
  text: string
  sid: string | null
}

export interface Card {
  id: string
  name: string
  category: string | null
  area: string | null
  role: 'experience' | 'meal'
  group: string
  status: 'main' | 'unverified' | 'excluded'
  score: number
  parts: Record<string, number>
  why: Claim[]
  tradeoffs: Claim[]
  visit: { short: number; typical: number; long: number; source: string } | null
  location: { center: string; km: number | null; minutes: number | null }
  price: string | null
  confidence: { level: 'high' | 'medium' | 'low'; reason: string }
  declined: boolean
  depends_on_unknown: string | null
  warnings: string[]
  unverified: string[]
  failed: string[]
  chosen: boolean
  locked: boolean
  anchor: boolean
  alternatives: { id: string; name: string }[]
  suggested: boolean
}

export interface Group {
  id: string
  label: string
  cards: Card[]
}

export type Action =
  | { type: 'select' | 'lock' | 'unlock' | 'wishlist'; place_id: string }
  | { type: 'drop'; place_id: string; reason?: DropReason | null }
  | { type: 'swap'; place_id: string; with_id: string }
  | { type: 'relax'; place_id: string; feature: string }
  | { type: 'answer'; qid: string; chip: string }
  | { type: 'undo' }

export interface Fix {
  label: string
  effect: string
  action: Action | null
}

export interface Conflict {
  id: string
  check: string
  physical: boolean
  title: string
  rule: string
  places: string[]
  fixes: Fix[]
}

export interface Feasibility {
  status: 'feasible' | 'partial' | 'infeasible' | 'unknown'
  known_days: boolean
  totals: { places: number; visit: number; buffer: number; travel: number; needed: number; available: number }
  slack: number | null
  conflicts: Conflict[]
  warnings: string[]
}

export interface Pending {
  qid: string
  text: string
  reason: string
  chips: { id: string; label: string }[]
  data: Record<string, unknown>
}

export interface View {
  version: number
  groups: Group[]
  shortlist: string[]
  selected: string[]
  locked: string[]
  unverified: { count: number; open: boolean; cards: Card[] }
  excluded: { by_rule: { rule: string; label: string; count: number }[] }
  wishlist: { id: string; name: string; reason: string }[]
  dropped: { id: string; name: string; reason: DropReason | null }[]
  feasibility: Feasibility
  pending: Pending | null
  profile: Record<string, unknown>
  known_days: boolean
  days: { index: number; date: string | null; weekday: string | null }[]
  unknowns: string[]
  unmapped: string[]
}

export interface Diff {
  added: string[]
  removed: string[]
  status: [string, string]
  delta: { places: number; visit: number; travel: number }
  text: string
  scope: { from: string | null; keep: string[] } | null
}

export interface ActResult {
  view: View
  diff: Diff
  goto?: 'understand'
}

export interface CompareRow {
  aspect: string
  label: string
  a: string
  b: string
  better: 'a' | 'b' | 'none' | 'unknown'
}

export interface CompareResult {
  a: { id: string; name: string }
  b: { id: string; name: string }
  rows: CompareRow[]
  sacrifice: CompareRow[]
}

export interface WhyNot {
  id: string
  name: string | null
  known: boolean
  status: string | null
  reasons: string[]
}

export interface DecisionOutput {
  confirmed: { id: string; name: string; role: 'anchor' | 'locked' | 'selected'; flags: string[]; relaxed: string[] }[]
  backup_pool: { id: string; name: string; for: string | null; reason: string }[]
  wishlist: { id: string; name: string; reason: string }[]
}

export interface TurnHandlers {
  say?: (d: { delta?: string; replace?: string }) => void
  view?: (d: ActResult) => void
  done?: () => void
  error?: (d: { message: string }) => void
}
```

- [ ] **Step 2: Client API**

`web/src/user/pd/api.ts`:

```ts
import type { SearchInput } from '../tu/types'
import type { Action, ActResult, CompareResult, DecisionOutput, TurnHandlers, View, WhyNot } from './types'

const BASE = '/api/decision/sessions'

export class DecisionError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`Decision API ${status}: ${detail}`)
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = ''
    try {
      detail = ((await res.json()) as { error?: string }).error ?? ''
    } catch {
      /* not JSON */
    }
    throw new DecisionError(res.status, detail)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const createDecision = (searchInput: SearchInput, tripSession: string | null) =>
  post(BASE, { search_input: searchInput, trip_session: tripSession }).then((r) => json<{ id: string; view: View }>(r))

export const loadDecision = (id: string) => fetch(`${BASE}/${id}`).then((r) => json<{ id: string; view: View }>(r))

export const act = (id: string, a: Action) => post(`${BASE}/${id}/act`, a).then((r) => json<ActResult>(r))

export const compare = (id: string, a: string, b: string) =>
  fetch(`${BASE}/${id}/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`).then((r) => json<CompareResult>(r))

export const whyNot = (id: string, place: string) =>
  fetch(`${BASE}/${id}/why-not/${encodeURIComponent(place)}`).then((r) => json<WhyNot>(r))

export const confirm = (id: string) => post(`${BASE}/${id}/confirm`, {}).then((r) => json<DecisionOutput>(r))

// POST + server-sent events: EventSource cannot POST, so the stream is read by hand (as in tu/api.ts).
export async function sendText(id: string, text: string, h: TurnHandlers): Promise<void> {
  const res = await post(`${BASE}/${id}/turn`, { text })
  if (!res.ok || !res.body) throw new DecisionError(res.status, '')
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    let cut: number
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      dispatch(buf.slice(0, cut), h)
      buf = buf.slice(cut + 2)
    }
  }
}

function dispatch(block: string, h: TurnHandlers) {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return
  const fn = (h as Record<string, ((d: unknown) => void) | undefined>)[event]
  fn?.(JSON.parse(data))
}
```

- [ ] **Step 3: Provider phiên**

`web/src/user/pd/decision.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { navigate } from '../../router'
import { useTrip } from '../trip'
import * as api from './api'
import type { Action, Diff, View } from './types'

interface DecisionCtx {
  view: View | null
  diff: Diff | null
  error: string | null
  busy: boolean
  act: (a: Action) => Promise<void>
  say: (text: string, onSay: (soFar: string) => void) => Promise<void>
  reload: () => void
}

const Ctx = createContext<DecisionCtx | null>(null)
const OFFLINE = 'Không kết nối được máy chủ chọn nơi (python -m decision serve).'

// One Place Decision session per trip: the backend holds the state, the page only shows its view.
export function DecisionProvider({ children }: { children: ReactNode }) {
  const { trip, dispatch } = useTrip()
  const id = trip.decisionId
  const [view, setView] = useState<View | null>(null)
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    setView(null)
    if (!id) return
    let live = true
    api.loadDecision(id).then(
      (r) => {
        if (!live) return
        setView(r.view)
        setError(null)
      },
      (e) => {
        if (!live) return
        if (e instanceof api.DecisionError && e.status === 404) {
          dispatch({ type: 'set', patch: { decisionId: null } })
          setError('Phiên chọn nơi đã hết. Quay lại bước Hiểu chuyến đi để bắt đầu lại.')
        } else setError(OFFLINE)
      },
    )
    return () => {
      live = false
    }
  }, [id, tick, dispatch])

  const act = useCallback(
    async (a: Action) => {
      if (!id) return
      setBusy(true)
      try {
        const r = await api.act(id, a)
        setView(r.view)
        setDiff(r.diff)
        setError(null)
        if (r.goto === 'understand') navigate('/app/understand')
      } catch (e) {
        setError(e instanceof api.DecisionError ? `Không thực hiện được: ${e.detail || e.status}` : OFFLINE)
      } finally {
        setBusy(false)
      }
    },
    [id],
  )

  const say = useCallback(
    async (text: string, onSay: (soFar: string) => void) => {
      if (!id) return
      setBusy(true)
      let acc = ''
      try {
        await api.sendText(id, text, {
          say: (d) => {
            acc = d.replace !== undefined ? d.replace : acc + (d.delta ?? '')
            onSay(acc)
          },
          view: (r) => {
            setView(r.view)
            setDiff(r.diff)
          },
          error: (d) => setError(d.message),
        })
      } catch {
        setError(OFFLINE)
      } finally {
        setBusy(false)
      }
    },
    [id],
  )

  return (
    <Ctx.Provider value={{ view, diff, error, busy, act, say, reload: () => setTick((t) => t + 1) }}>{children}</Ctx.Provider>
  )
}

export function useDecision() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useDecision outside DecisionProvider')
  return c
}
```

- [ ] **Step 4: Trip state, UserApp, Understand, proxy**

`web/src/user/trip.tsx`:
- trong `interface TripState`, sau dòng `searchInput?: SearchInput ...` thêm:

```ts
  decisionId: string | null // Place Decision session (src/decision); the backend holds the curation state
```

- trong `initialTrip`, sau `feedback: {},` thêm `decisionId: null,`

`web/src/user/UserApp.tsx`:
- thêm import `import { DecisionProvider, useDecision } from './pd/decision'`
- `UserApp` bọc thêm provider:

```tsx
export function UserApp({ path, onHome }: { path: string; onHome: () => void }) {
  return (
    <TripProvider>
      <DecisionProvider>
        <Shell path={path} onHome={onHome} />
      </DecisionProvider>
    </TripProvider>
  )
}
```

- trong `Shell`: thêm `const { view } = useDecision()` sau `const account = useAccount()`; dòng `showCurate` thành:

```tsx
  const showCurate = ['/app/shortlist', '/app/place', '/app/compare'].includes(base) && (view?.selected.length ?? 0) > 0
```

- dòng render thanh tuyển chọn thành `{showCurate && <CurateBar />}`.

`web/src/user/screens/Understand.tsx`:
- thêm import `import { createDecision } from '../pd/api'`
- handler `done` thành:

```tsx
          done: (d) => {
            dispatch({ type: 'set', patch: fromSearchInput(d.search_input) })
            write(null)
            createDecision(d.search_input, null).then(
              (r) => {
                dispatch({ type: 'set', patch: { decisionId: r.id } })
                navigate('/app/shortlist')
              },
              () => setNotice('Chưa tạo được gợi ý. Kiểm tra máy chủ chọn nơi (python -m decision serve) rồi thử lại.'),
            )
          },
```

`web/vite.config.ts`, dòng `server:` thành (khóa `/api/decision` phải đứng trước `/api`):

```ts
  // /api/decision: `python -m decision serve` (src/decision/server.py, Place Decision).
  // /api/trip: `python -m trip serve` (src/trip/server.py, Trip Understanding).
  // /api: `python -m corpus review` (src/corpus/review/server.py): decisions and gold labels.
  server: {
    proxy: { '/api/decision': 'http://127.0.0.1:8767', '/api/trip': 'http://127.0.0.1:8766', '/api': 'http://127.0.0.1:8765' },
  },
```

- [ ] **Step 5: Build**

Run: `cd web && npm run build`
Expected: build thành công (các màn cũ vẫn dùng `planner.ts`, chưa đổi).

- [ ] **Step 6: Commit**

```bash
git add web/src/user/pd web/src/user/trip.tsx web/src/user/UserApp.tsx web/src/user/screens/Understand.tsx web/vite.config.ts
git commit -m "feat(web): Place Decision client, session provider and handoff from Trip Understanding"
```

---

### Task 15: Web: Shortlist, Compare, CurateBar, Feasibility đọc từ backend; chạy thật trên trình duyệt

**Files:**
- Modify (viết lại): `web/src/user/screens/Shortlist.tsx`, `Compare.tsx`, `Curate.tsx`, `Feasibility.tsx`
- Modify: `web/src/user/planner.ts` (bỏ phần shortlist và `deltaLine`), `web/src/user/user.css` (cuối file)
- Regenerate: `web/public/data/snapshot.json`
- Create (tạm, scratchpad): `pd_check.py`

**Interfaces:**
- Consumes: `useDecision`, `api.*`, type `pd/types` (Task 14); `placeById`, `signal`, `fmtDuration` (`data/store`); `searchPlaces` (`tu/api`).
- Produces: `PlaceCard`, `flyToTray` (export từ `Shortlist.tsx`, như trước).

- [ ] **Step 1: Shortlist**

`web/src/user/screens/Shortlist.tsx` (thay toàn bộ):

```tsx
import gsap from 'gsap'
import { useRef, useState, type FormEvent, type PointerEvent } from 'react'
import { placeById, signal } from '../../data/store'
import type { Place } from '../../data/types'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Chip, ClipCover, ConfidenceTag, Icon, Page, SectionArt, Sheet } from '../../ui/bits'
import { whyNot } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { Card, Claim, DropReason, WhyNot } from '../pd/types'
import { searchPlaces } from '../tu/api'
import { DROP_LABEL, useTrip } from '../trip'

const ART: Record<string, 'sight' | 'nature' | 'food' | 'shop'> = { anchors: 'sight', nature: 'nature', sights: 'sight', chill: 'food', meal: 'food' }
export const CONF = { high: 'Cao', medium: 'Trung bình', low: 'Thấp' } as const

export function Shortlist() {
  const { trip } = useTrip()
  const { view, error, act, busy } = useDecision()
  const [tab, setTab] = useState<string | null>(null)
  const [compare, setCompare] = useState<string[]>([])
  const [dropping, setDropping] = useState<Card | null>(null)

  if (!trip.decisionId)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>{error ?? 'Chưa có gợi ý. Bắt đầu từ bước hiểu chuyến đi.'}</p>
          <button className="btn" onClick={() => navigate('/app/understand')}>
            Hiểu chuyến đi
          </button>
        </div>
      </Page>
    )
  if (!view)
    return (
      <div className="loading" role="status">
        {error ?? 'Đang chuẩn bị gợi ý'}
      </div>
    )

  const anchors = view.groups.find((g) => g.id === 'anchors')
  const groups = view.groups.filter((g) => g.id !== 'anchors')
  const current = groups.find((g) => g.id === tab) ?? groups[0]
  const toggleCompare = (id: string) =>
    setCompare((c) => (c.includes(id) ? c.filter((x) => x !== id) : c.length >= 2 ? [c[1], id] : [...c, id]))
  const cardProps = { comparing: compare, onCompare: toggleCompare, onDrop: setDropping }

  return (
    <Page className="page--wide">
      <header className="phead phead--split">
        <div>
          <h1>Gợi ý cho chuyến của bạn</h1>
          <p>Một tập nhỏ đáng cân nhắc, kèm lý do và cái giá phải đánh đổi. Bạn chốt, mình không chọn thay.</p>
        </div>
      </header>

      {error && (
        <p className="notice" role="alert">
          <Icon name="alert" size={16} /> {error}
        </p>
      )}
      <Question />

      {anchors && (
        <section className="block">
          <h2 className="block__title">{anchors.label}</h2>
          <div className="cards">
            {anchors.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </section>
      )}

      <div className="tabs" role="tablist" aria-label="Nhóm địa điểm">
        {groups.map((g) => (
          <button key={g.id} role="tab" aria-selected={current?.id === g.id} className={current?.id === g.id ? 'is-on' : ''} onClick={() => setTab(g.id)}>
            <SectionArt section={ART[g.id] ?? 'sight'} />
            <span className="tabs__label">{g.label}</span>
            <span className="tabs__n">{g.cards.length}</span>
          </button>
        ))}
      </div>

      {view.excluded.by_rule.map((r) => (
        <div className="notice" key={r.rule}>
          <Icon name="lock" size={16} />
          <span>
            {r.label} đã loại {r.count} nơi.
          </span>
        </div>
      ))}

      {current ? (
        <div className="cards">
          {current.cards.map((c) => (
            <PlaceCard key={c.id} c={c} {...cardProps} />
          ))}
        </div>
      ) : (
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có nơi nào qua được điều kiện của bạn.</p>
        </div>
      )}

      {view.unverified.count > 0 && (
        <details className="extra" open={view.unverified.open}>
          <summary>{view.unverified.count} nơi chưa xác minh được điều kiện của bạn</summary>
          <p className="block__hint">Chưa đủ bằng chứng để nói các nơi này hợp với điều kiện bạn đặt. Tự kiểm tra trước nếu muốn chọn.</p>
          <div className="cards">
            {view.unverified.cards.map((c) => (
              <PlaceCard key={c.id} c={c} {...cardProps} />
            ))}
          </div>
        </details>
      )}

      {view.unmapped.length > 0 && <p className="notice notice--soft">Chưa kiểm được trong dữ liệu: {view.unmapped.join(', ')}.</p>}
      <WhyNotBox />
      <Chat />

      {compare.length === 2 && (
        <button className="fab" onClick={() => navigate(`/app/compare/${compare.join(',')}`)}>
          <Icon name="compare" /> So sánh 2 nơi
        </button>
      )}

      <Sheet open={!!dropping} onClose={() => setDropping(null)} label="Bỏ địa điểm">
        {dropping && (
          <div className="dropwhy">
            <h2>Bỏ {dropping.name}?</h2>
            <p className="block__hint">Cho mình biết lý do để gợi ý sau sát hơn. Không bắt buộc.</p>
            <div className="chips">
              {(Object.keys(DROP_LABEL) as DropReason[]).map((r) => (
                <Chip
                  key={r}
                  onClick={() => {
                    act({ type: 'drop', place_id: dropping.id, reason: r })
                    setDropping(null)
                  }}
                >
                  {DROP_LABEL[r]}
                </Chip>
              ))}
            </div>
            <button
              className="btn btn--ghost"
              disabled={busy}
              onClick={() => {
                act({ type: 'drop', place_id: dropping.id })
                setDropping(null)
              }}
            >
              Bỏ, không cần lý do
            </button>
          </div>
        )}
      </Sheet>
    </Page>
  )
}

// The one question the rules opened (pattern, free time, rethink); the user answers with a chip.
function Question() {
  const { view, act, busy } = useDecision()
  const q = view?.pending
  if (!q) return null
  return (
    <section className="followup" aria-live="polite">
      <p className="bubble bubble--q">{q.text}</p>
      <p className="block__hint">{q.reason}</p>
      <div className="chips">
        {q.chips.map((c) => (
          <Chip key={c.id} onClick={() => !busy && act({ type: 'answer', qid: q.qid, chip: c.id })}>
            {c.label}
          </Chip>
        ))}
      </div>
    </section>
  )
}

function Chat() {
  const { say, busy } = useDecision()
  const [text, setText] = useState('')
  const [reply, setReply] = useState<string | null>(null)
  const send = async (e: FormEvent) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setText('')
    setReply('')
    await say(t, setReply)
  }
  return (
    <section className="pdchat">
      <form onSubmit={send}>
        <label className="pdchat__label" htmlFor="pdchat">
          Nói với mình, ví dụ “quán này xa quá” hay “muốn chỗ ít người hơn”
        </label>
        <div className="pdchat__row">
          <input id="pdchat" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder="Gõ ở đây" />
          <button className="btn btn--small" disabled={busy || !text.trim()}>
            Gửi
          </button>
        </div>
      </form>
      {reply !== null && (
        <p className="bubble bubble--a" aria-live="polite">
          {reply || '…'}
        </p>
      )}
    </section>
  )
}

function WhyNotBox() {
  const { trip } = useTrip()
  const [q, setQ] = useState('')
  const [res, setRes] = useState<WhyNot | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const ask = async (e: FormEvent) => {
    e.preventDefault()
    if (!q.trim() || !trip.decisionId) return
    setRes(null)
    setMsg(null)
    try {
      const hits = await searchPlaces(q.trim())
      if (!hits.length) return setMsg('Không tìm thấy nơi này trong dữ liệu.')
      setRes(await whyNot(trip.decisionId, hits[0].id))
    } catch {
      setMsg('Chưa tra được, thử lại sau.')
    }
  }
  return (
    <details className="extra whynot">
      <summary>Vì sao không thấy một nơi?</summary>
      <form onSubmit={ask} className="pdchat__row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tên địa điểm" aria-label="Tên địa điểm" />
        <button className="btn btn--small btn--ghost">Tra</button>
      </form>
      {msg && <p className="block__hint">{msg}</p>}
      {res && (
        <div>
          <b>{res.name ?? q}</b>
          <ul>
            {res.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </details>
  )
}

export function PlaceCard({ c, comparing, onCompare, onDrop }: { c: Card; comparing: string[]; onCompare: (id: string) => void; onDrop: (c: Card) => void }) {
  const { act, busy } = useDecision()
  const ref = useRef<HTMLElement>(null)
  const p = placeById(c.id) // clips and evidence quotes come from the snapshot when it has this place

  // A soft 3D tilt under the pointer; off for touch and reduced motion.
  const tilt = (e: PointerEvent) => {
    if (e.pointerType !== 'mouse' || story.reducedMotion || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    gsap.to(ref.current, { rotateY: x * 7, rotateX: -y * 7, duration: 0.4, ease: 'power2.out' })
  }
  const untilt = () => ref.current && gsap.to(ref.current, { rotateX: 0, rotateY: 0, duration: 0.6, ease: 'power3.out' })
  const add = (e: React.MouseEvent) => {
    act({ type: 'select', place_id: c.id })
    flyToTray(e.currentTarget as HTMLElement)
  }
  const notes = [...c.failed.map((t) => `Không hợp điều kiện của bạn: ${t}`), ...c.unverified, ...c.warnings]

  return (
    <article ref={ref} className={`pcard${c.chosen ? ' is-chosen' : ''}`} onPointerMove={tilt} onPointerLeave={untilt}>
      {p && p.videos.length > 0 && <ClipCover videos={p.videos} />}
      <header className="pcard__head">
        <button className="pcard__name" onClick={() => navigate(`/app/place/${encodeURIComponent(c.id)}`)}>
          {c.name}
        </button>
        <span className="pcard__meta">{c.category}</span>
        {c.suggested && <span className="pcard__keep">Gợi ý thêm</span>}
        {c.locked && (
          <span className="pcard__lock" title="Đã khóa">
            <Icon name="lock" size={14} />
          </span>
        )}
      </header>

      {c.why.length > 0 && (
        <ul className="pcard__why" aria-label="Vì sao phù hợp">
          {c.why.map((w) => (
            <ClaimRow key={w.text} claim={w} place={p} icon="check" />
          ))}
        </ul>
      )}
      {c.tradeoffs.length > 0 && (
        <ul className="pcard__cost" aria-label="Đánh đổi">
          {c.tradeoffs.map((w) => (
            <ClaimRow key={w.text} claim={w} place={p} icon="alert" />
          ))}
        </ul>
      )}
      {notes.map((t) => (
        <p key={t} className="pcard__basic">
          {t}
        </p>
      ))}
      {c.depends_on_unknown && <p className="pcard__basic">{c.depends_on_unknown}</p>}

      <div className="pcard__facts">
        {c.visit && (
          <span title="Ước tính">
            <Icon name="clock" size={14} /> {c.visit.short}–{c.visit.long} phút
          </span>
        )}
        {c.location.minutes !== null && (
          <span title="Ước tính">
            <Icon name="route" size={14} /> ≈{c.location.minutes} phút từ {c.location.center}
          </span>
        )}
        {c.price && <span>{c.price}</span>}
      </div>
      <ConfidenceTag level={CONF[c.confidence.level]} reason={c.confidence.reason + (c.declined ? ' Có dấu hiệu xuống cấp gần đây.' : '')} />

      {c.alternatives.length > 0 && (
        <p className="pcard__alts">
          Nơi tương tự:{' '}
          {c.alternatives.map((a) => (
            <button
              key={a.id}
              className="link"
              disabled={busy}
              title={c.chosen ? `Đổi sang ${a.name}` : `Xem ${a.name}`}
              onClick={() => (c.chosen ? act({ type: 'swap', place_id: c.id, with_id: a.id }) : navigate(`/app/place/${encodeURIComponent(a.id)}`))}
            >
              {a.name}
            </button>
          ))}
        </p>
      )}

      <div className="pcard__tools">
        <button className={`tbtn${c.locked ? ' is-on' : ''}`} aria-pressed={c.locked} title="Khóa: không bao giờ bị bỏ tự động" disabled={busy} onClick={() => act({ type: c.locked ? 'unlock' : 'lock', place_id: c.id })}>
          <Icon name={c.locked ? 'lock' : 'unlock'} size={15} /> {c.locked ? 'Đã khóa' : 'Khóa'}
        </button>
        <button className={`tbtn${comparing.includes(c.id) ? ' is-on' : ''}`} aria-pressed={comparing.includes(c.id)} onClick={() => onCompare(c.id)}>
          <Icon name="compare" size={15} /> So sánh
        </button>
        {!c.chosen && (
          <button className="tbtn" onClick={() => onDrop(c)}>
            <Icon name="x" size={15} /> Bỏ qua
          </button>
        )}
      </div>

      <footer className="pcard__actions">
        {c.chosen ? (
          <button className="btn btn--small btn--chosen" disabled={busy} onClick={() => onDrop(c)}>
            <Icon name="check" size={16} /> Đã chọn
          </button>
        ) : (
          <button className="btn btn--small" disabled={busy} onClick={add}>
            <Icon name="plus" size={16} /> Thêm vào chuyến
          </button>
        )}
        {p && (
          <button className="pcard__more" onClick={() => navigate(`/app/place/${encodeURIComponent(c.id)}`)}>
            Bằng chứng <Icon name="next" size={15} />
          </button>
        )}
      </footer>
    </article>
  )
}

// Each claim opens its own evidence when the snapshot has it: sample size, agreement, one quote (UX brief §3.3).
function ClaimRow({ claim, place, icon }: { claim: Claim; place: Place | undefined; icon: string }) {
  const [open, setOpen] = useState(false)
  const s = claim.sid && place ? signal(place, claim.sid) : undefined
  if (!s || !place)
    return (
      <li>
        <Icon name={icon} size={14} /> <span>{claim.text}</span>
      </li>
    )
  return (
    <li className="claim">
      <Icon name={icon} size={14} />
      <span>
        <button className="claim__btn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {claim.text}
        </button>
        {open && (
          <span className="claim__ev">
            <small>
              {s.n} người nhắc, {Math.round(s.agreement * 100)}% đồng ý{s.freshnessDays !== null ? `, mới nhất ${s.freshnessDays} ngày trước` : ''}
            </small>
            {s.quotes[0] && <q>{s.quotes[0].text}</q>}
            <button className="link" onClick={() => navigate(`/app/place/${encodeURIComponent(place.id)}`)}>
              Xem đủ bằng chứng
            </button>
          </span>
        )}
      </span>
    </li>
  )
}

// A yellow diamond arcs from the button into the curation bar.
export function flyToTray(from: HTMLElement) {
  if (story.reducedMotion) return
  const target = document.querySelector('.curate__count')
  const a = from.getBoundingClientRect()
  const gem = document.createElement('i')
  gem.className = 'gem'
  document.body.appendChild(gem)
  const b = target?.getBoundingClientRect() ?? { left: innerWidth / 2, top: innerHeight - 40, width: 0, height: 0 }
  gsap.set(gem, { x: a.left + a.width / 2, y: a.top + a.height / 2, scale: 0.6, rotate: 45 })
  gsap
    .timeline({ onComplete: () => gem.remove() })
    .to(gem, { x: b.left + b.width / 2, duration: 0.7, ease: 'power1.inOut' }, 0)
    .to(gem, { y: Math.min(a.top, b.top) - 80, duration: 0.35, ease: 'power2.out' }, 0)
    .to(gem, { y: b.top + b.height / 2, duration: 0.35, ease: 'power2.in' }, 0.35)
    .to(gem, { scale: 1.1, rotate: 225, duration: 0.7 }, 0)
    .to(gem, { scale: 0, opacity: 0, duration: 0.2 }, 0.65)
}
```

- [ ] **Step 2: Compare**

`web/src/user/screens/Compare.tsx` (thay toàn bộ):

```tsx
import { useEffect, useState } from 'react'
import { navigate } from '../../router'
import { Icon, Page } from '../../ui/bits'
import { compare, DecisionError } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { CompareResult } from '../pd/types'
import { useTrip } from '../trip'

export function Compare({ ids }: { ids: string[] }) {
  const { trip } = useTrip()
  const { view, act, busy } = useDecision()
  const [res, setRes] = useState<CompareResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [a, b] = ids

  useEffect(() => {
    if (!trip.decisionId || !a || !b) return
    let live = true
    compare(trip.decisionId, a, b).then(
      (r) => live && setRes(r),
      (e) =>
        live &&
        setErr(
          e instanceof DecisionError && e.status === 400
            ? 'Hai nơi này khác loại (một chỗ ăn, một nơi tham quan) nên không đặt cạnh nhau.'
            : 'Chưa so sánh được, thử lại sau.',
        ),
    )
    return () => {
      live = false
    }
  }, [trip.decisionId, a, b])

  if (ids.length < 2) return <div className="loading">Cần 2 nơi để so sánh.</div>
  if (err) return <div className="loading">{err}</div>
  if (!res) return <div className="loading">Đang so sánh</div>

  const cols = [res.a, res.b]
  const rows = [...res.sacrifice, ...res.rows]
  return (
    <Page className="page--wide">
      <button className="back" onClick={() => history.back()}>
        <Icon name="back" size={16} /> Quay lại
      </button>
      <header className="phead">
        <h1>So sánh nhanh</h1>
        <p>Chỉ hiện điểm khác nhau có bằng chứng. Số trong ngoặc là số người nhắc tới; “chưa biết” không có nghĩa là kém hơn.</p>
      </header>

      <div className="cmp" style={{ ['--cols' as string]: 2 }}>
        <div className="cmp__row cmp__row--head">
          <span />
          {cols.map((p) => (
            <div key={p.id} className="cmp__col">
              <button className="link cmp__name" onClick={() => navigate(`/app/place/${encodeURIComponent(p.id)}`)}>
                {p.name}
              </button>
            </div>
          ))}
        </div>
        {rows.length === 0 && <p className="block__hint">Hai nơi này không khác nhau ở điểm nào có bằng chứng.</p>}
        {rows.map((r) => (
          <div className="cmp__row" key={r.aspect}>
            <span className="cmp__label">{r.label}</span>
            {(['a', 'b'] as const).map((k) => (
              <span key={k} className={`cmp__cell${r.better === k ? ' is-best' : ''}`}>
                {r[k]}
              </span>
            ))}
          </div>
        ))}
        <div className="cmp__row cmp__row--act">
          <span />
          {cols.map((p) => {
            const on = view?.selected.includes(p.id) ?? false
            return (
              <div key={p.id}>
                <button className={`btn btn--small${on ? ' btn--chosen' : ''}`} disabled={busy} onClick={() => act(on ? { type: 'drop', place_id: p.id } : { type: 'select', place_id: p.id })}>
                  {on ? 'Đã chọn' : 'Chọn nơi này'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </Page>
  )
}
```

- [ ] **Step 3: CurateBar**

`web/src/user/screens/Curate.tsx` (thay toàn bộ):

```tsx
import gsap from 'gsap'
import { useEffect, useRef, useState } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Sheet } from '../../ui/bits'
import { useDecision } from '../pd/decision'
import type { Diff, Feasibility } from '../pd/types'

const VERDICT: Record<Feasibility['status'], string> = {
  feasible: 'Đi kịp',
  partial: 'Có chỗ cần sửa',
  infeasible: 'Quá sức',
  unknown: 'Chưa biết số ngày',
}

// Live curation summary (§2.8): never blocks, always one line of difference with an undo.
export function CurateBar() {
  const { view, diff, act, busy } = useDecision()
  const [shown, setShown] = useState<Diff | null>(null)
  const [open, setOpen] = useState(false)
  const bar = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!diff) return
    setShown(diff)
    if (!story.reducedMotion && bar.current) gsap.fromTo(bar.current, { y: 6 }, { y: 0, duration: 0.5, ease: 'elastic.out(1, 0.5)' })
    const t = setTimeout(() => setShown(null), 5200)
    return () => clearTimeout(t)
  }, [diff])

  if (!view) return null
  const f = view.feasibility
  const t = f.totals
  const names = new Map(view.groups.flatMap((g) => g.cards).map((c) => [c.id, c.name]))
  const warnings = f.conflicts.length + f.warnings.length

  return (
    <>
      <div className="curate" ref={bar}>
        {shown && (
          <p className={`curate__delta${shown.status[1] !== 'feasible' ? ' is-warn' : ''}`} role="status">
            {shown.text}.{' '}
            <button className="link" disabled={busy} onClick={() => act({ type: 'undo' })}>
              Hoàn tác
            </button>
          </p>
        )}
        <button className="curate__main" onClick={() => setOpen(true)} aria-label="Mở danh sách đã chọn">
          <span className="curate__count">{t.places}</span>
          <span className="curate__nums">
            <b>{t.places} nơi đã chọn</b>
            <small>
              {fmtDuration(t.visit)} tham quan, ≈{fmtDuration(t.travel)} đi lại
            </small>
          </span>
          <span className={`verdict verdict--${f.status === 'unknown' ? 'partial' : f.status}`}>
            {VERDICT[f.status]}
            {warnings > 0 && <em>{warnings} lưu ý</em>}
          </span>
        </button>
        <button className="btn btn--small" onClick={() => navigate('/app/feasibility')}>
          Kiểm tra
        </button>
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} label="Danh sách đã chọn">
        <h2>Danh sách đã chọn</h2>
        <dl className="totals">
          <div>
            <dt>Tham quan</dt>
            <dd>{fmtDuration(t.visit)}</dd>
          </div>
          <div>
            <dt>Di chuyển, ước tính</dt>
            <dd>{fmtDuration(t.travel)}</dd>
          </div>
          <div>
            <dt>Thời gian có</dt>
            <dd>{f.known_days ? fmtDuration(t.available) : 'Chưa biết số ngày'}</dd>
          </div>
        </dl>
        <ul className="picked">
          {view.selected.map((id) => {
            const locked = view.locked.includes(id)
            const name = names.get(id) ?? id
            return (
              <li key={id}>
                <button className="link picked__name" onClick={() => (setOpen(false), navigate(`/app/place/${encodeURIComponent(id)}`))}>
                  {name}
                </button>
                <button className={`iconbtn${locked ? ' is-on' : ''}`} aria-pressed={locked} aria-label={locked ? 'Mở khóa' : 'Khóa'} disabled={busy} onClick={() => act({ type: locked ? 'unlock' : 'lock', place_id: id })}>
                  <Icon name={locked ? 'lock' : 'unlock'} size={16} />
                </button>
                <button className="iconbtn" aria-label={`Bỏ ${name}`} disabled={busy} onClick={() => act({ type: 'drop', place_id: id })}>
                  <Icon name="x" size={16} />
                </button>
              </li>
            )
          })}
        </ul>
        <button className="btn" onClick={() => (setOpen(false), navigate('/app/feasibility'))}>
          Kiểm tra khả thi
        </button>
      </Sheet>
    </>
  )
}
```

- [ ] **Step 4: Feasibility**

`web/src/user/screens/Feasibility.tsx` (thay toàn bộ):

```tsx
import gsap from 'gsap'
import { useLayoutEffect, useRef, useState } from 'react'
import { fmtDuration } from '../../data/store'
import { navigate } from '../../router'
import { story } from '../../scene/story'
import { Icon, Page } from '../../ui/bits'
import { confirm } from '../pd/api'
import { useDecision } from '../pd/decision'
import type { Feasibility as F } from '../pd/types'
import { useTrip } from '../trip'

const HEAD: Record<F['status'], { title: string; tone: 'ok' | 'warn' | 'bad' }> = {
  feasible: { title: 'Đi kịp. Sẵn sàng xếp lịch.', tone: 'ok' },
  partial: { title: 'Gần được rồi, còn vài chỗ cần bạn chọn cách sửa.', tone: 'warn' },
  infeasible: { title: 'Kế hoạch này quá sức so với thời gian có.', tone: 'bad' },
  unknown: { title: 'Chưa biết chuyến đi mấy ngày nên chưa kiểm được thời gian.', tone: 'warn' },
}

export function Feasibility() {
  const { trip, dispatch } = useTrip()
  const { view, act, busy, error } = useDecision()
  const list = useRef<HTMLDivElement>(null)
  const [sending, setSending] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const status = view?.feasibility.status
  const nConflicts = view?.feasibility.conflicts.length ?? 0

  // Background: a red route while conflicts remain, the golden one once clear.
  useLayoutEffect(() => {
    story.appScene = status === 'feasible' ? 0.96 : 0.8
  }, [status])

  useLayoutEffect(() => {
    if (story.reducedMotion || !list.current) return
    const ctx = gsap.context(() => {
      gsap.from('.conflict', { opacity: 0, x: -24, rotateY: -12, duration: 0.6, stagger: 0.08, ease: 'power3.out' })
    }, list)
    return () => ctx.revert()
  }, [nConflicts])

  if (!view) return <div className="loading">{error ?? 'Đang tải'}</div>
  if (!view.selected.length)
    return (
      <Page className="page--narrow">
        <div className="empty">
          <img src="/img/empty.webp" alt="" />
          <p>Chưa có nơi nào được chọn để kiểm tra.</p>
          <button className="btn" onClick={() => navigate('/app/shortlist')}>
            Chọn địa điểm
          </button>
        </div>
      </Page>
    )

  const f = view.feasibility
  const t = f.totals
  const head = f.status === 'feasible' && f.warnings.length ? { title: `Đi kịp, nếu ${f.warnings.length} điều chưa chắc dưới đây đúng như dự kiến.`, tone: 'ok' as const } : HEAD[f.status]
  const confirmable = f.status === 'feasible' || f.status === 'unknown'

  const go = async () => {
    if (!trip.decisionId) return
    setSending(true)
    setMsg(null)
    try {
      const out = await confirm(trip.decisionId)
      // The schedule screen is still the client prototype (Planning comes next); it reads the confirmed places.
      dispatch({ type: 'set', patch: { selected: out.confirmed.map((c) => c.id), locked: out.confirmed.filter((c) => c.role !== 'selected').map((c) => c.id) } })
      navigate('/app/plan')
    } catch {
      setMsg('Chưa xác nhận được, thử lại.')
    } finally {
      setSending(false)
    }
  }

  return (
    <Page className="page--narrow">
      <header className={`verdict-head verdict-head--${head.tone}`}>
        <h1>{head.title}</h1>
        {f.known_days && (
          <>
            <div className="meter" aria-label={`Cần ${fmtDuration(t.needed)} trên ${fmtDuration(t.available)}`}>
              <div className="meter__fill" style={{ width: `${Math.min(100, (t.needed / Math.max(1, t.available)) * 100)}%` }} />
              {t.needed > t.available && <div className="meter__over" style={{ width: `${Math.min(40, ((t.needed - t.available) / Math.max(1, t.available)) * 100)}%` }} />}
            </div>
            <p className="meter__legend">
              Cần khoảng {fmtDuration(t.needed)} cho {t.places} nơi, chuyến đi có {fmtDuration(t.available)}. Thời gian di chuyển là ước tính.
            </p>
          </>
        )}
      </header>

      {f.warnings.length > 0 && (
        <section className="block">
          <h2 className="block__title">
            <Icon name="info" size={16} /> Kiểm tra trước khi đi
          </h2>
          <ul className="checks">
            {f.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="conflicts" ref={list}>
        {f.conflicts.map((c) => (
          <article key={c.id} className={`conflict${c.physical ? ' conflict--hard' : ' conflict--rule'}`}>
            <p className="conflict__what">
              <Icon name={c.physical ? 'alert' : 'lock'} size={16} /> {c.title}
            </p>
            <p>{c.rule}</p>
            <p className="conflict__kind">{c.physical ? 'Giới hạn thật: không đi kịp. Chỉ có cách đổi lựa chọn.' : 'Quy tắc của bạn: bạn có thể nới nếu muốn.'}</p>
            <div className="fixes">
              {c.fixes.map((x) => (
                <button key={x.label} className="fix" disabled={busy} onClick={() => (x.action ? act(x.action) : navigate('/app/understand'))}>
                  <b>{x.label}</b>
                  <small>{x.effect}</small>
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>

      {view.wishlist.length > 0 && (
        <section className="block">
          <h2 className="block__title">Để dành cho dịp khác</h2>
          <ul className="checks">
            {view.wishlist.map((w) => (
              <li key={w.id}>
                <b>{w.name}</b>: {w.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      {(msg || error) && (
        <p className="notice" role="alert">
          {msg ?? error}
        </p>
      )}
      <div className="pfoot">
        <button className="link" onClick={() => navigate('/app/shortlist')}>
          Sửa danh sách
        </button>
        {/* No button turns a plan that cannot be done into a "feasible" one (UX brief §3.6). */}
        <button className="btn" disabled={!confirmable || sending} onClick={go}>
          {confirmable ? 'Xác nhận và xếp lịch' : 'Chọn cách sửa ở trên trước'}
        </button>
      </div>
    </Page>
  )
}
```

- [ ] **Step 5: Gọn `planner.ts`, thêm CSS**

`web/src/user/planner.ts`:
- Xóa từ dòng `// ---------- shortlist ----------` tới hết hàm `sharedTraits` (gồm `Claim`, `Candidate`, `Shortlist`, `SECTIONS`, `evaluate`, `buildShortlist`, `similarGroups`, `keepPick`, `sharedTraits`).
- Xóa hàm `deltaLine` và comment `// One-line difference after a curation change (§2.8).` phía trên nó.
- Hai dòng import đầu thành:

```ts
import { featureLabel } from '../data/labels'
import { CENTER, DAYS, fmtDuration, fmtTime, has, openWindows, placeById, travelMin, visible, visitRange } from '../data/store'
```

- Giữ nguyên `anchorOf`, `toMin`, `Stop`, `Day`, `Fix`, `Conflict`, `Plan`, `paceVisit`, `nearestOrder`, `dayWindows`, `plan`, `closedConflict`, `rainBackup` (Lịch trình và admin `Sessions.tsx` còn dùng).

Cuối `web/src/user/user.css` thêm:

```css
/* Place Decision: typed message box, alternatives line, why-not lookup */
.pdchat {
  margin: 24px 0;
}
.pdchat__label {
  display: block;
  margin-bottom: 6px;
  color: var(--ink-soft);
  font-size: 0.875rem;
}
.pdchat__row {
  display: flex;
  gap: 8px;
}
.pdchat__row input {
  flex: 1;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--glass-edge);
  border-radius: 10px;
  background: var(--glass);
  color: var(--ink);
  font: inherit;
}
.pcard__alts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  color: var(--ink-soft);
  font-size: 0.8125rem;
}
.whynot ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
```

- [ ] **Step 6: Build**

Run: `cd web && npm run build`
Expected: thành công, không lỗi TypeScript. Nếu tsc báo import thừa trong `planner.ts`, bỏ đúng tên bị báo.

- [ ] **Step 7: Export lại snapshot cho id khớp serving**

Run: `python web/scripts/export_snapshot.py`
Rồi kiểm: `python -c "import json;s={p['id'] for p in json.load(open('web/public/data/snapshot.json',encoding='utf-8'))['places']};r={x['id'] for x in json.load(open('data/serving/places.json',encoding='utf-8'))['records']};print(len(s),len(r),len(r-s))"`
Expected: số nơi serving không có trong snapshot (`len(r-s)`) nhỏ hơn trước (trước: 377). Nơi còn thiếu vẫn hiện thẻ đầy đủ, chỉ không có clip / trích dẫn bằng chứng (PlaceCard đã xử lý `p` rỗng).

- [ ] **Step 8: Chạy thật trên trình duyệt**

Mở 3 terminal (từ `tripguardian/`): `python -m trip serve`, `python -m decision serve`, `cd web && npm run dev`.

Ghi script vào scratchpad `pd_check.py`:

```python
"""Drive /app/shortlist -> drop with a reason -> add -> /app/feasibility -> confirm, collect console errors."""
import asyncio
import json
import urllib.request

import yaml
from playwright.async_api import async_playwright

WEB, API = "http://127.0.0.1:5173", "http://127.0.0.1:8767/api/decision/sessions"
VERSION = yaml.safe_load(open("config/ontology.yaml", encoding="utf-8"))["version"]
SI = {"ontology_version": VERSION,
      "context": {"start_date": "2026-12-14", "month": None, "days": 3, "base": None, "mobility": "car",
                  "companions": ["parents"], "people": 4, "arrive_at": "10:00", "leave_at": "15:00", "day_end": None,
                  "budget_vnd": None, "experience": "first"},
      "hard_filters": [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "flag"}],
      "anchors": [], "soft_weights": [
          {"feature": "scenic_view", "value": "present", "context": None, "weight": 1, "source": "user"},
          {"feature": "cloud_hunting", "value": "present", "context": None, "weight": 1, "source": "user"}],
      "pace": {"level": "slow", "max_leg_min": None, "crowd_tolerance": "avoid"},
      "novelty": {"level": "new", "visited": []}, "unknowns": ["budget_vnd"], "unmapped": ["nhạc nhẹ"]}


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


async def main():
    sid = post(API, {"search_input": SI})["id"]
    errors = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 900})
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        await pg.goto(WEB + "/")
        await pg.evaluate("id => localStorage.setItem('tg.trip.v1', JSON.stringify({decisionId: id, startDate: '2026-12-14', days: 3}))", sid)
        await pg.goto(WEB + "/app/shortlist")
        await pg.wait_for_selector(".pcard", timeout=30000)
        cards = await pg.locator(".pcard").count()
        await pg.locator(".pcard .tbtn", has_text="Bỏ qua").first.click()
        await pg.get_by_role("button", name="Quá xa").click()
        await pg.locator(".pcard button", has_text="Thêm vào chuyến").first.click()
        await pg.wait_for_selector(".curate__count", timeout=15000)
        await pg.screenshot(path="pd_shortlist.png", full_page=True)
        await pg.goto(WEB + "/app/feasibility")
        await pg.wait_for_selector(".verdict-head h1", timeout=15000)
        head = await pg.locator(".verdict-head h1").inner_text()
        btn = pg.get_by_role("button", name="Xác nhận và xếp lịch")
        if await btn.is_enabled():
            await btn.click()
            await pg.wait_for_url("**/app/plan", timeout=15000)
        await pg.screenshot(path="pd_after.png", full_page=True)
        print(json.dumps({"cards": cards, "head": head, "url": pg.url, "errors": errors}, ensure_ascii=False))
        await b.close()

asyncio.run(main())
```

Run (từ `tripguardian/`): `python <scratchpad>/pd_check.py`
Expected: `cards` > 0, `head` là một tiêu đề khả thi, `url` kết thúc bằng `/app/plan`, `errors` rỗng. Mở `pd_shortlist.png`, `pd_after.png` bằng Read để xem: thẻ có "vì sao phù hợp", mục "chưa xác minh" mở sẵn (vì `unknown_policy = flag`), thông báo "Chưa kiểm được trong dữ liệu: nhạc nhẹ", thanh tuyển chọn có dòng chênh lệch + "Hoàn tác". Thử thêm bằng tay ô "Nói với mình" với câu "chỗ đầu tiên xa quá" để thấy agent trả lời (cần Gemma).

- [ ] **Step 9: Commit**

```bash
git add web/src/user/screens/Shortlist.tsx web/src/user/screens/Compare.tsx web/src/user/screens/Curate.tsx web/src/user/screens/Feasibility.tsx web/src/user/planner.ts web/src/user/user.css web/public/data/snapshot.json
git commit -m "feat(web): shortlist, compare, curation bar and feasibility read the Place Decision backend"
```

(Nếu `web/public/data/snapshot.json` không được git theo dõi — kiểm bằng `git ls-files web/public/data` — bỏ nó khỏi lệnh `git add`.)

---

### Task 16: Test live, tài liệu chính thức, xóa spec/plan làm việc

**Files:**
- Create: `tests/decision/test_live.py`
- Modify: `docs/PLACE_DECISION.md` (§3 bảng phân vai, thêm §18 "Bản chạy hiện tại"), `docs/TRIP_UNDERSTANDING.md` (§11 Context, §17), `docs/log/DEV_LOG.md` (mục `place-decision` mới, sửa `corpus-serving`), `docs/LLM_PROVIDER.md` (task `DECISION_TURN`), `docs/Role_Web_Functional_Design.md` (màn chọn nơi / khả thi), `README.md` (lệnh chạy)
- Delete: `docs/plans/PLACE_DECISION_SPEC.md`, `docs/plans/PLACE_DECISION_PLAN.md`

- [ ] **Step 1: Test live**

`tests/decision/test_live.py`:

```python
import pytest
from test_engine import data, trip

from decision.agent import run_agent
from decision.engine import Engine
from decision.session import Store
from decision.settings import default


@pytest.mark.live
def test_one_real_turn_drops_the_named_place():
    cfg = default()
    e = Engine(data(), cfg, Store(None), lambda f, on_say: run_agent(f, on_say, cfg))
    sid = e.create(trip())["id"]
    events = []
    e.turn(sid, "Quán Cà Phê Số 1 xa quá, bỏ giúp mình", lambda ev, d: events.append((ev, d)))
    s = e.store.get(sid)
    print(events[0], s.log[-1])
    assert not any("agent_fallback" in x for x in s.log[-1]["action"]["log"])
    assert [(d.place_id, d.reason) for d in s.state.dropped] == [("C1", "far")]
```

Run: `python -m pytest -m live tests/decision/test_live.py -s` (mạng UIT, `AGENT_*` trong `.env`)
Expected: PASS; ghi lại thời gian lượt (in ra) cho DEV_LOG. Nếu Gemma trả `place` sai hoặc không có `reason`, sửa prompt `DECISION_TURN` (không nới test), chạy lại.

- [ ] **Step 2: Toàn bộ test**

Run: `python -m pytest -q`
Expected: PASS toàn bộ (mặc định bỏ `live`).

- [ ] **Step 3: Viết tài liệu**

Viết tiếng Việt, mô tả đúng code hiện tại, không ghi lịch sử (`RULE.md` §0.1):

- `docs/PLACE_DECISION.md`
  - §3 bảng phân vai: dòng "Diễn đạt 'vì sao phù hợp', 'đánh đổi', lý do bỏ thành câu | LLM" đổi thành "Thẻ ứng viên ('vì sao phù hợp', 'đánh đổi') | Template | Chỉ từ field serving record và kết quả rule; agent chỉ nói phần diễn giải kèm (`say`)".
  - Thêm `## 18. Bản chạy hiện tại`: lệnh (`python -m decision serve` → `127.0.0.1:8767`, web qua proxy `/api/decision`; `python -m decision evaluate`), bảng file `src/decision/` (một dòng mỗi file, như spec §3), các route HTTP + event SSE, khung giờ từ corpus (`time_windows`: buổi hẹp, suất mỗi ngày, `timed_features`), câu hỏi do rule mở (pattern / gap / rethink), ngưỡng nằm ở `config/decision.yaml`, số đo thật từ Task 13 Step 6 và Task 16 Step 1, giới hạn đã biết: chưa có giờ hẹn của anchor (Trip State không có field), không gọi route service (khoảng cách chim bay × `road_factor`), `recent_interest = 0` (chưa có User Profile).
- `docs/TRIP_UNDERSTANDING.md`: §11 cây Search Input, dòng `context` thêm `budget_vnd, experience`; §17 câu "Web: ... Search Input map sang `TripState` cũ" sửa thành: sau `done`, web tạo phiên Place Decision (`POST /api/decision/sessions`).
- `docs/log/DEV_LOG.md`: mục mới `## place-decision — Search Input → địa điểm đã xác nhận` theo mẫu (file, cách kiểm chứng, Hiện tại 2026-10-0x với số đo, Trước đó = _không có_). Mục `corpus-serving`: chuyển Hiện tại → Trước đó, Hiện tại mới nói `evaluate` đã chuyển sang `python -m decision evaluate` (chạy pipeline thật), file mục này chỉ còn `record.py`, `groups.py`, `run.py`.
- `docs/LLM_PROVIDER.md`: thêm dòng task `DECISION_TURN` (role `AGENT`, một call stream mỗi tin nhắn gõ chữ ở màn chọn nơi, `src/decision/agent.py`).
- `docs/Role_Web_Functional_Design.md`: màn Chọn nơi / So sánh / Khả thi đọc từ backend Place Decision; thêm ô "Nói với mình", câu hỏi do rule mở, "Vì sao không thấy một nơi?", nút "Xác nhận và xếp lịch" (chỉ khi khả thi hoặc chưa biết số ngày).
- `README.md`: thêm lệnh `python -m decision serve` cạnh `python -m trip serve`.

- [ ] **Step 4: Xóa spec/plan làm việc**

```bash
git rm docs/plans/PLACE_DECISION_SPEC.md docs/plans/PLACE_DECISION_PLAN.md
```

- [ ] **Step 5: Commit cẩn thận (cây làm việc dùng chung)**

Các file tài liệu ở trên có thể đang chứa thay đổi chưa commit của một phiên khác. Trước khi `git add` từng file, chạy `git diff <file>` và xem: nếu diff chỉ gồm phần vừa viết → add. Nếu có phần không phải của task này → **không add file đó**, ghi tên nó lại để báo người dùng.

```bash
git add tests/decision/test_live.py <các file tài liệu chỉ có thay đổi của task này>
git commit -m "docs(decision): Place Decision as built; live agent test; drop the working spec and plan"
```

- [ ] **Step 6: Báo cáo**

Báo người dùng: số test, kết quả `decision evaluate` (vi phạm, unknown, `filled_rate`, `ms_max`), một lượt Gemma thật (thời gian), ảnh chụp trình duyệt, file tài liệu chưa commit được vì lẫn thay đổi của phiên khác (nếu có), và việc tiếp theo: Planning & Validation + Live Context.
