# Plan P3 — Planning lõi: từ Decision Output tới lịch trình đã kiểm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng `src/planning` tới hết phase P3: `places` → `travel` → `cluster` → `days` → `route` → `schedule` → `validate` → `build`, và lệnh `python -m planning build <decision_output.json>` in ra lịch trình đã kiểm. Chưa có web, chưa có agent, chưa có chỗ ở live, chưa có phương án / độ vững / dự phòng (P4–P5).

**Architecture:** Một đường duy nhất, không random: các địa điểm đã xác nhận → một ma trận thời gian (OSRM, rơi về ước lượng thô có gắn nhãn) → cụm → chia ngày (DP trên tập con) → thứ tự trong ngày (vét cạn tới `exact_n`, sau đó nearest-neighbour + 2-opt + or-opt) → đồng hồ từng ngày (chờ, đệm, nghỉ, bữa ăn, giờ ghim) → `validate` kết luận đạt / không đạt từ chính dòng thời gian cuối cùng. `planning` chỉ đọc dữ liệu ngoài qua `live`, `corpus.serving`, `corpus.ontology` (public API) và không import `decision` / `trip`: Decision Output vào dưới dạng JSON.

**Tech Stack:** Python 3.12, stdlib, `pyyaml`, `pytest`. Không thêm dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Thuật toán ⓑ–ⓔ, §Plan Output, bảng phase P3). Plan trước: `docs/plans/PLANNING_P1_LIVE_CONTEXT.md` (đã xong: `src/live`, `entry_point` / `exit_point`).

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0). Chuỗi hiển thị cho người dùng (cảnh báo, dòng lịch) tiếng Việt, như `src/decision/cards.py`.
- Module chỉ giao tiếp qua public API (`__init__.py`). `planning` dùng: `live` (`travel_matrix`, `geocode`, `sun_times`, `load_settings`, `Unavailable`), `corpus.serving` (`feature`, `check`, `load`), `corpus.ontology` (`load`). Không deep import; không import `decision`, `trip` (`RULE.md` §2).
- `src/planning` không ghi `data/intel`, `data/serving`, `data/gmaps`, `data/tiktok`, `data/review`. Plan này không ghi gì dưới `data/`; lệnh `--out` ghi đúng file người dùng chỉ định.
- Mọi bước tất định: không `random`, không đọc đồng hồ. Cùng input → cùng output (`PLANNING_SPEC.md` §Nguyên tắc 3).
- Không bịa: thiếu dữ liệu → bỏ trống kèm lý do hoặc cảnh báo (`Unplaced`, `None`, cờ), không điền giá trị (`RULE.md` §3). Thời gian di chuyển luôn mang `source` (`osrm` | `rough`).
- Không thêm dependency vào `pyproject.toml`.
- Thay đổi tối thiểu: không refactor, đổi tên, format lại code không liên quan (`RULE.md` §4). `decision`, `trip`, `live` không đổi trong plan này.
- Mọi file test dưới `tests/planning/` có tên duy nhất toàn repo (tiền tố `test_planning_`) vì `tests/` không có `__init__.py`; không tạo `tests/planning/__init__.py`.
- Chạy test: `python -m pytest -q` ở gốc repo (`pythonpath = ["src"]` đã có).
- Giờ trong code là số phút sau nửa đêm; `HH:MM` chỉ ở config (đổi sang phút khi nạp) và ở Plan Output.
- `config/planning.yaml` không chứa endpoint hay TTL của nguồn live: chúng ở `config/live.yaml` (`src/live` không được đọc config của `planning`).

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| Rơi về ước lượng thô của `decision/geo.py` khi OSRM chết | `planning/travel.py` tự có `rough_minutes` | `decision/geo.py` không nằm trong public API của `decision`; spec cũng nói `decision` không đổi. Công thức giống nhau. |
| `timed_features` "dùng lại của `decision`" | `pins` trong `config/planning.yaml`, khoá theo feature id | Không cần import `decision` chỉ để lấy ba tên feature; mỗi feature kèm quy tắc giờ của nó. |
| `rest_per_day` theo pace | `rest_min` và `max_consecutive_min` theo pace | Quy tắc "đi liên tục quá `max_consecutive_min` phải nghỉ" đã là cách chèn nghỉ; số lần nghỉ mỗi ngày là hệ quả, không phải tham số. |
| Thời gian tham quan `min` / `typical` / `long` | Khoá của serving record là `short` / `typical` / `long`; `visit_key` ánh xạ pace → khoá | Theo dữ liệu thật trong `data/serving/places.json`. |
| Decision Output có "ghim ngày" cho `locked` | Chưa có ghim ngày | Decision Output không mang ngày nào cho nơi `locked`; ghim theo giờ mở cửa (nơi đóng cả ngày, hoặc chỉ mở sau giờ kết thúc ngày) có làm: `days.blocked`. |
| `validate` kiểm hard constraint | Chỉ kiểm hard filter `op = ne` (`feature != value`) bằng `corpus.serving.check` | `check` chỉ định nghĩa cho dạng này; `eq` do Place Decision xử lý. Một nơi người dùng đã nới (`relaxed`) không bị tính vi phạm. |
| "kèm cái giá đã tính của từng cách sửa" cho mỗi vi phạm | Chưa có | Cái giá của cách sửa thuộc `repair_day` (P6). |
| Plan Output đầy đủ | P3 trả: `ok`, `itinerary`, `travel_load`, `violations`, `warnings`, `unplaced`, `uncertainty`, `provenance`, `reasons`, `tradeoffs`, `trip_context` | `variants`, `chosen`, `route`, `lodging`, `cost`, `robustness`, `backups` đến ở P4–P6. |

## Review Focus

Năm lớp input spec hàm ý nhưng dễ bị bỏ; mỗi dòng đã có test ở task sở hữu code:

1. **Giờ mở cửa qua nửa đêm, 24 giờ, nhiều khoảng một ngày** — dữ liệu thật có đủ ba dạng (338 khoảng qua nửa đêm, 862 khoảng 00:00–23:59, 238 ngày nhiều khoảng). Mong đợi: nạp đúng, chọn khoảng khả thi đầu tiên, không crash. → Task 2 (`test_hours_become_minutes...`), Task 5 (`test_the_second_opening_interval...`).
2. **Chuyến không có ngày đi hoặc không có số ngày** — không có thứ → không kiểm giờ mở cửa theo thứ, không ghim hoàng hôn; gắn cờ, không đoán. → Task 4 (`test_days_and_dates_the_user_never_gave...`), Task 5 (`test_a_place_closed_that_weekday...`, `test_without_a_known_sun...`), Task 10 (`test_a_trip_without_dates...`).
3. **OSRM chết, hoặc không có đường cho một cặp** — ma trận thô có nhãn `rough`, một cặp thiếu đường thì thô riêng cặp đó và được đếm; plan vẫn dựng được. → Task 3, Task 10 (`test_without_osrm...`).
4. **Nơi chỉ mở sau giờ kết thúc ngày** (quán ăn mở 18:00 vào ngày cuối kết thúc 15:00) — không được đưa vào ngày đó khi còn ngày khác. → Task 8 (`test_a_cluster_with_an_evening_only_place...`, `test_the_greedy_fallback_also_keeps...`).
5. **Địa điểm đã xác nhận mà không xếp được** (không có record, không toạ độ, không dùng được cho lịch) — báo `unplaced` kèm lý do, không rơi lặng lẽ; nếu là anchor thì plan không hợp lệ. → Task 2, Task 10 (`test_a_place_that_cannot_be_scheduled...`).

## Cấu trúc file

| File | Việc |
|---|---|
| `config/planning.yaml` | ngưỡng; `settings.py` nạp, đổi `HH:MM` sang phút |
| `src/planning/model.py` | kiểu dữ liệu chung: `Place`, `Day`, `Item`, `DayResult`, `Violation`, ... |
| `src/planning/places.py` | Decision Output + serving record → `Place`; giờ mở cửa; điểm vào / ra / ở |
| `src/planning/travel.py` | một ma trận cho cả chuyến, đi bộ chặng ngắn, đường lui thô |
| `src/planning/frame.py` | các ngày của chuyến: ngày, thứ, khung giờ, điểm mở / đóng ngày |
| `src/planning/schedule.py` | `simulate`: đồng hồ một ngày theo thứ tự cho trước |
| `src/planning/route.py` | thứ tự trong ngày: vét cạn hoặc heuristic |
| `src/planning/cluster.py` | gom cụm, tách cụm quá lớn |
| `src/planning/days.py` | chia cụm vào ngày (DP), đường lui tham lam |
| `src/planning/validate.py` | kết luận đạt / không đạt |
| `src/planning/build.py` | nối tất cả; `render_text` |
| `src/planning/__main__.py` | `python -m planning build` |
| `tests/planning/plan_fixtures.py` | record, Decision Output, ma trận giả cho test |

---

### Task 1: Config, settings, kiểu dữ liệu

**Files:**
- Create: `config/planning.yaml`
- Create: `src/planning/__init__.py`
- Create: `src/planning/settings.py`
- Create: `src/planning/model.py`
- Test: `tests/planning/test_planning_settings.py`

**Interfaces:**
- Consumes: không có (task đầu).
- Produces:
  - `planning.settings.Settings` (frozen dataclass), `planning.settings.load(path=PATH) -> Settings`, `PATH`, `to_min("HH:MM") -> int`, `fmt(minutes) -> "HH:MM"`; giờ trong `Settings` đã là phút, `meal_windows` là `{tên: (sớm nhất, muộn nhất)}`, `pins` có `from` / `to` đã đổi sang phút cho `anchor: clock`
  - `planning.model`: `Place`, `Unplaced`, `Point`, `Day`, `Item`, `Violation`, `DayResult` (với `.key`)

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_settings.py`:

```python
from planning import settings


def test_the_shipped_config_loads_with_minutes_not_clock_strings():
    cfg = settings.load(settings.PATH)
    assert cfg.version == 1
    assert (cfg.day_start, cfg.day_end, cfg.leave_at) == (480, 1260, 900)
    assert cfg.meal_windows["lunch"] == (690, 810)
    assert cfg.pins["live_music"]["from"] == 1080 and cfg.pins["sunset_view"]["anchor"] == "sunset"
    assert cfg.visit_key == {"slow": "long", "normal": "typical", "packed": "short"}
    assert cfg.exact_n == 7 and cfg.max_days == 7 and cfg.max_clusters == 8


def test_fmt_and_to_min_round_trip():
    assert settings.to_min("08:30") == 510
    assert settings.fmt(510) == "08:30"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_settings.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning'`

- [ ] **Step 3: Viết config**

Tạo `config/planning.yaml`:

```yaml
# Planning & Validation thresholds (docs/specs/PLANNING_SPEC.md §Cấu hình). Starting values; tune after the pilot.
# Live endpoints and TTLs live in config/live.yaml: src/live may not read this file.
version: 1

# Rough travel, used only when OSRM is down or has no road for a pair. Every number built on it is an estimate.
road_factor: 1.4            # straight line -> road distance
rough_speed_kmh: {motorbike: 25, car: 25, ride: 22}
walk_km: 0.4                # a leg shorter than this is walked
walk_kmh: 4.5

# The trip frame when the user did not say.
default_days: 2
day_start: "08:00"
day_end: "21:00"
leave_at: "15:00"

# Pace. visit_key picks which of the record's visit minutes (short / typical / long) a pace uses.
visit_key: {slow: long, normal: typical, packed: short}
per_day: {slow: 3, normal: 4, packed: 6}
buffer_min: {slow: 30, normal: 20, packed: 10}
long_leg_min: 30            # a leg longer than this adds buffer_extra_long
buffer_extra_long: 10
buffer_extra_uncertain: 10  # a place whose opening hours are UNCERTAIN / OUTDATED
rest_min: {slow: 20, normal: 15, packed: 10}
max_consecutive_min: {slow: 90, normal: 120, packed: 180}   # active minutes (visit + travel) before a rest is forced

# Meals. A confirmed meal place takes a window; a window nobody takes gets a free block, never an invented place.
meals_per_day: 2
meal_min: 60
meal_windows: {lunch: ["11:30", "13:30"], dinner: ["18:00", "20:30"]}   # earliest and latest start

# Timed features: where in the day a place that is known for it has to start.
# anchor sunrise / sunset: minutes from it; anchor clock: absolute times.
pins:
  sunset_view: {anchor: sunset, from_min: -75, to_min: -20}
  cloud_hunting: {anchor: sunrise, from_min: -30, to_min: 60}
  live_music: {anchor: clock, from: "18:00", to: "20:00"}

# Grouping and day assignment.
cluster_max_min: 25         # complete-link diameter of one cluster, in minutes of real travel
cluster_merge_min: 8        # clusters of different areas merge only when this close
fill_ratio: 0.8             # a cluster whose load exceeds this share of a day is split
intra_leg_min: 10           # minutes charged per place for moving inside a cluster when sizing a day
max_days: 7
max_clusters: 8
exact_n: 7                  # up to this many stops a day the order is found by trying every permutation
improve_passes: 5
weights: {travel: 1.0, overflow: 3.0, count: 15.0, closed: 1000.0}
```

- [ ] **Step 4: Viết code**

Tạo `src/planning/__init__.py` (mọc dần ở Task 10):

```python
"""Planning & Validation: confirmed places -> a checked itinerary (docs/specs/PLANNING_SPEC.md)."""
```

Tạo `src/planning/settings.py`:

```python
"""Planning thresholds (config/planning.yaml)."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "planning.yaml"


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Settings:
    version: int
    road_factor: float
    rough_speed_kmh: dict
    walk_km: float
    walk_kmh: float
    default_days: int
    day_start: int          # minutes after midnight
    day_end: int
    leave_at: int
    visit_key: dict
    per_day: dict
    buffer_min: dict
    long_leg_min: int
    buffer_extra_long: int
    buffer_extra_uncertain: int
    rest_min: dict
    max_consecutive_min: dict
    meals_per_day: int
    meal_min: int
    meal_windows: dict      # name -> (earliest start, latest start) in minutes
    pins: dict
    cluster_max_min: int
    cluster_merge_min: int
    fill_ratio: float
    intra_leg_min: int
    max_days: int
    max_clusters: int
    exact_n: int
    improve_passes: int
    weights: dict


@cache
def load(path: Path = PATH) -> Settings:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for k in ("day_start", "day_end", "leave_at"):
        raw[k] = to_min(raw[k])
    raw["meal_windows"] = {name: (to_min(a), to_min(b)) for name, (a, b) in raw["meal_windows"].items()}
    raw["pins"] = {f: {**p, **({"from": to_min(p["from"]), "to": to_min(p["to"])} if p["anchor"] == "clock" else {})}
                   for f, p in raw["pins"].items()}
    return Settings(**raw)
```

Tạo `src/planning/model.py`:

```python
"""The values Planning passes between its steps. All times are minutes after midnight."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: str                       # experience | meal
    role: str                       # anchor | locked | selected (from Place Decision)
    lat: float
    lng: float
    area: str | None
    dup_group: int | None           # places sharing it are near duplicates
    hours: dict | None              # weekday -> [(open, close)]; None = the record has no hours
    hours_status: str | None
    visit: dict                     # short / typical / long minutes
    cost_vnd: int | None            # estimated per person; None = unknown, never guessed
    pins: tuple[str, ...]           # timed features the place is known for
    flags: tuple[str, ...]          # warning texts Place Decision attached
    relaxed: tuple[str, ...]        # hard filters the user relaxed for this place
    rec: dict                       # the serving record, for the hard-constraint check


@dataclass(frozen=True)
class Unplaced:
    id: str
    name: str
    reason: str                     # no_record | not_plannable | no_coordinates | no_visit_time


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float
    text: str
    source: str                     # corpus | nominatim
    fetched_at: str | None


@dataclass(frozen=True)
class Day:
    index: int
    date: date | None
    weekday: str | None             # None when the trip has no dates
    start: int
    end: int
    start_node: str | None          # where the day opens: home, or the entry point on day one
    end_node: str | None            # where it closes: home, or the exit point on the last day


@dataclass(frozen=True)
class Item:
    kind: str                       # visit | travel | wait | buffer | rest | meal_free
    start: int
    end: int
    place_id: str | None = None
    name: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    mode: str | None = None         # travel: walk | motorbike | car | ride
    note: str | None = None


@dataclass(frozen=True)
class Violation:
    kind: str                       # hours | timed | overlap | day_window | travel | long_leg | anchor | budget
    day: int | None                 #        | hard | duplicate
    place_id: str | None
    minutes: int
    physical: bool                  # a physical constraint is never relaxed
    detail: str


@dataclass(frozen=True)
class DayResult:
    items: tuple[Item, ...]
    order: tuple[str, ...]
    violations: tuple[Violation, ...]   # what the simulation tripped over; validate.py decides pass / fail
    travel_min: int
    wait_min: int
    end: int
    notes: tuple[str, ...] = ()
    method: str = ""                # exact | heuristic | single

    @property
    def key(self) -> tuple[int, int]:
        """Fewer violations first, then the earlier the day ends."""
        return (len(self.violations), self.end)
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_settings.py -q`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add config/planning.yaml src/planning/__init__.py src/planning/settings.py src/planning/model.py tests/planning/test_planning_settings.py
git commit -m "feat(planning): settings and shared types"
```


### Task 2: Địa điểm đã xác nhận → `Place`

**Files:**
- Create: `src/planning/places.py`
- Create: `tests/planning/plan_fixtures.py`
- Test: `tests/planning/test_planning_places.py`

**Interfaces:**
- Consumes: `planning.settings.Settings`, `planning.model.Place/Unplaced/Point`, `corpus.serving.feature`, `live.Unavailable`.
- Produces:
  - `planning.places.parse_hours(value: dict) -> dict` (weekday → `[(open, close)]` phút; đóng cửa sau nửa đêm → `close + 1440`)
  - `planning.places.windows_on(hours, weekday) -> list | None` (`[]` = đóng cả ngày, `None` = không biết)
  - `planning.places.kind_of(rec) -> "experience" | "meal" | None`, `cost_of(op) -> int | None`
  - `planning.places.build_places(decision: dict, by_id: dict, cfg) -> (list[Place], list[Unplaced])`
  - `planning.places.resolve_point(base: dict | None, by_id: dict, geocode) -> (Point | None, str | None)`
  - `tests/planning/plan_fixtures.py`: `rec`, `decision`, `all_days`, `fake_matrix`, `no_geocode`, `fixed_sun`, `flat_travel`, `line_travel`, `day_ctx`, `CFG` — dùng ở mọi task sau

- [ ] **Step 1: Viết fixture và test**

Tạo `tests/planning/plan_fixtures.py` (các helper cần module của task sau thì import trong hàm, nên file này dùng được từ task này):

```python
"""Synthetic serving records, Decision Outputs and travel matrices that need no network, for the planning tests.

Helpers that need a module a later task creates import it inside the function, so this file works from task 2 on.
"""

from functools import cache

from planning import settings

from corpus.ontology import load as _load_ontology

load_ontology = cache(_load_ontology)       # rec() runs once per place, so the ontology file is read once
CFG = settings.load(settings.PATH)
DAYS7 = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def all_days(a="08:00", b="21:00"):
    return {d: [[a, b]] for d in DAYS7}


def rec(pid, lat, lng, *, area="area-1", usable=("experience", "backup"), hours="open", visit=(30, 60, 90),
        features=None, price=None, dup=None, name=None, status="VERIFIED"):
    """A serving record. hours: "open" = 08:00-21:00 every day, None = no hours, or a {weekday: [[open, close]]} dict.
    features: {feature id: value}, filed under the feature's group."""
    ontology = load_ontology()
    groups: dict = {}
    for fid, value in (features or {}).items():
        groups.setdefault(ontology.features[fid].group, {})[fid] = {
            "value": value, "distribution": {value: 3}, "status": "VERIFIED", "n": 3}
    h = all_days() if hours == "open" else hours
    return {"id": pid, "status": "VERIFIED", "status_reason": None,
            "identity": {"name": name or pid, "kind": "POI", "category": "x", "category_group": "x", "lat": lat,
                         "lng": lng, "address": None, "area": area},
            "operation": {"hours": None if h is None else {"value": h, "status": status, "as_of": "2026-09-30"},
                          "price_per_person": None, "entry_fee": price,
                          "visit_minutes": {"short": visit[0], "typical": visit[1], "long": visit[2],
                                            "source": "category_default", "n": 0, "kind": "estimate"},
                          "booking": None, "crowd_by_time": None},
            "experience": groups.get("experience", {}), "environment": {}, "service": {},
            "effort": groups.get("effort", {}), "suitability": {}, "usable_as": list(usable),
            "near_duplicate_group": dup}


def decision(ids, *, roles=None, days=2, start_date="2026-12-12", pace="normal", mobility="motorbike", base=None,
             entry=None, exit=None, hard=(), budget=None, max_leg=None, relaxed=None, arrive_at=None, leave_at=None,
             flags=None, log=()):
    """A Decision Output (docs/PLACE_DECISION.md §15) as the JSON a session would write."""
    roles = roles or {}
    return {
        "confirmed": [{"id": i, "name": i, "role": roles.get(i, "selected"), "visit": None,
                       "flags": (flags or {}).get(i, []), "relaxed": (relaxed or {}).get(i, [])} for i in ids],
        "backup_pool": [], "wishlist": [], "decision_log": list(log), "feasibility": {},
        "trip_context": {
            "context": {"start_date": start_date, "month": None, "days": days, "base": base, "entry_point": entry,
                        "exit_point": exit, "mobility": mobility, "companions": [], "people": 2,
                        "arrive_at": arrive_at, "leave_at": leave_at, "day_end": None, "budget_vnd": budget},
            "hard_filters": list(hard),
            "anchors": [{"place_id": i, "priority": "must"} for i in roles if roles[i] == "anchor"],
            "soft_weights": [], "pace": {"level": pace, "max_leg_min": max_leg, "crowd_tolerance": None},
            "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []},
    }


def fake_matrix(points, mode, cfg):
    """Straight line x 1.4 at 25 km/h: what live.travel_matrix would answer, with no OSRM."""
    from planning.travel import km
    n = len(points)
    return {"minutes": [[0 if i == j else max(1, round(km(points[i], points[j]) * 1.4 / 25 * 60)) for j in range(n)]
                        for i in range(n)], "source": "osrm", "fetched_at": "2026-10-02T00:00:00+00:00"}


def no_geocode(text):
    return None


def fixed_sun(d, lat, lng, tz):
    return (6 * 60, 17 * 60 + 30)


def flat_travel(ids, minutes=10, **pairs):
    """Every pair `minutes` apart, except the pairs given as a_b=minutes (either direction)."""
    from planning.travel import Travel

    def m(a, b):
        return pairs.get(f"{a}_{b}", pairs.get(f"{b}_{a}", minutes))

    return Travel(list(ids), [[(0, "none") if a == b else (m(a, b), "motorbike") for b in ids] for a in ids],
                  "osrm", "t")


def line_travel(positions: dict, scale=5):
    """Nodes on a line: |difference of positions| x scale minutes, so every distance is easy to read."""
    from planning.travel import Travel
    ids = list(positions)
    return Travel(ids, [[(0, "none") if a == b else (max(1, round(abs(positions[a] - positions[b]) * scale)),
                                                      "motorbike") for b in ids] for a in ids], "osrm", "t")


def day_ctx(recs, *, minutes=10, pace="normal", weekday="mon", start=480, end=1260, start_node=None, end_node=None,
            sun=None, roles=None, travel=None, hard=(), extra_nodes=()):
    """A DayCtx over the given rec(...) places with a flat travel matrix."""
    from planning.model import Day
    from planning.places import build_places
    from planning.schedule import DayCtx
    d = decision([r["id"] for r in recs], roles=roles, hard=hard)
    places, unplaced = build_places(d, {r["id"]: r for r in recs}, CFG)
    assert not unplaced, unplaced
    by_id = {p.id: p for p in places}
    day = Day(0, None, weekday, start, end, start_node, end_node)
    return DayCtx(day, by_id, travel or flat_travel([*by_id, *extra_nodes], minutes), CFG, pace, sun)
```

Tạo `tests/planning/test_planning_places.py`:

```python

import pytest
from plan_fixtures import all_days, decision, rec

from live import Unavailable
from planning import places as pl
from planning import settings

CFG = settings.load(settings.PATH)


def test_hours_become_minutes_and_a_close_after_midnight_runs_into_the_next_day():
    got = pl.parse_hours({"mon": [["09:00", "21:00"]], "fri": [["18:00", "02:00"]], "sat": [["00:00", "23:59"]]})
    assert got["mon"] == [(540, 1260)] and got["fri"] == [(1080, 1560)] and got["sat"] == [(0, 1439)]


def test_windows_on_tells_closed_from_unknown():
    hours = pl.parse_hours({**all_days(), "mon": []})
    assert pl.windows_on(hours, "mon") == []                       # closed that day
    assert pl.windows_on(hours, "tue") == [(480, 1260)]
    assert pl.windows_on(None, "tue") is None                      # the record has no hours
    assert pl.windows_on(hours, None) is None                      # days differ and the weekday is unknown
    assert pl.windows_on(pl.parse_hours(all_days()), None) == [(480, 1260)]   # the same every day: weekday not needed


def test_a_confirmed_place_becomes_a_place_with_its_record_facts():
    r = rec("a", 11.94, 108.45, usable=("experience", "backup"), features={"sunset_view": "present"},
            price={"min_vnd": 50000, "typical_vnd": 60000, "max_vnd": 70000})
    d = decision(["a"], roles={"a": "anchor"}, flags={"a": ["giờ mở cửa chưa chắc"]}, relaxed={"a": ["long_walk"]})
    places, unplaced = pl.build_places(d, {"a": r}, CFG)
    p = places[0]
    assert unplaced == []
    assert (p.id, p.kind, p.role, p.visit["typical"], p.cost_vnd) == ("a", "experience", "anchor", 60, 60000)
    assert p.pins == ("sunset_view",) and p.flags == ("giờ mở cửa chưa chắc",) and p.relaxed == ("long_walk",)


def test_a_place_that_cannot_be_scheduled_is_reported_with_its_reason_not_dropped_silently():
    no_coord = rec("c", None, None)
    meal_less = rec("d", 11.9, 108.4, usable=("backup",))
    d = decision(["missing", "c", "d"])
    places, unplaced = pl.build_places(d, {"c": no_coord, "d": meal_less}, CFG)
    assert places == []
    assert {u.id: u.reason for u in unplaced} == {"missing": "no_record", "c": "no_coordinates", "d": "not_plannable"}


def test_a_meal_only_place_is_a_meal_and_a_place_with_both_is_an_experience():
    both = rec("a", 11.9, 108.4, usable=("experience", "meal", "backup"))
    meal = rec("b", 11.9, 108.4, usable=("meal", "backup"))
    places, _ = pl.build_places(decision(["a", "b"]), {"a": both, "b": meal}, CFG)
    assert {p.id: p.kind for p in places} == {"a": "experience", "b": "meal"}


def test_cost_comes_from_the_fee_then_the_price_range_and_is_none_when_unknown():
    assert pl.cost_of({"entry_fee": {"typical_vnd": 40000}, "price_per_person": None}) == 40000
    assert pl.cost_of({"entry_fee": None, "price_per_person": {"value": {"min_vnd": 100000, "max_vnd": 200000}}}) == 150000
    assert pl.cost_of({"entry_fee": None, "price_per_person": None}) is None


def test_a_base_in_the_corpus_resolves_without_geocoding():
    by_id = {"x": rec("x", 11.95, 108.44, name="Quán X")}
    point, why = pl.resolve_point({"place_id": "x", "text": "Quán X"}, by_id, geocode=lambda t: pytest.fail("no call"))
    assert (point.lat, point.lng, point.source, why) == (11.95, 108.44, "corpus", None)


def test_a_typed_point_is_geocoded_and_keeps_its_source():
    hit = {"lat": 11.9404, "lng": 108.4583, "label": "Bến xe", "source": "nominatim", "fetched_at": "t"}
    point, why = pl.resolve_point({"place_id": None, "text": "Bến xe Liên tỉnh"}, {}, geocode=lambda t: hit)
    assert (point.source, point.fetched_at, why) == ("nominatim", "t", None)


@pytest.mark.parametrize("base,geo,reason", [
    (None, lambda t: None, "unknown"),
    ({"place_id": None, "text": "  "}, lambda t: None, "unknown"),
    ({"place_id": None, "text": "nơi lạ"}, lambda t: None, "not_found"),
])
def test_a_point_that_cannot_be_resolved_says_why(base, geo, reason):
    assert pl.resolve_point(base, {}, geo) == (None, reason)


def test_a_dead_geocoder_is_a_reason_not_a_crash():
    def dead(text):
        raise Unavailable("down")

    assert pl.resolve_point({"place_id": None, "text": "Bến xe"}, {}, dead) == (None, "geocode_unavailable")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_places.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/places.py`:

```python
"""Decision Output + serving records -> the places Planning can schedule, and the points a trip starts and ends at.

A confirmed place that cannot be scheduled (no record, no coordinates, no visit time) is reported as Unplaced with
its reason; nothing is filled in to make it fit.
"""

from corpus.serving import feature
from live import Unavailable

from .model import Place, Point, Unplaced
from .settings import Settings, to_min


def parse_hours(value: dict) -> dict:
    """Serving hours ({"mon": [["09:00", "21:00"]], ...}) -> {"mon": [(540, 1260)]}. A close at or before the open
    runs past midnight: 18:00-02:00 becomes (1080, 1560)."""
    out = {}
    for day, spans in value.items():
        ivs = []
        for a, b in spans:
            o, c = to_min(a), to_min(b)
            ivs.append((o, c if c > o else c + 1440))
        out[day] = sorted(ivs)
    return out


def windows_on(hours: dict | None, weekday: str | None) -> list | None:
    """Opening intervals on a weekday: [] = closed that day, None = not known (no hours, or the weekday is unknown
    and the days differ), so the caller must not constrain on it."""
    if hours is None:
        return None
    if weekday is not None:
        return hours.get(weekday, [])
    days = list(hours.values())
    return days[0] if days and all(d == days[0] for d in days) else None


def kind_of(rec: dict) -> str | None:
    """experience | meal | None (a place no plan can use)."""
    usable = rec.get("usable_as") or []
    return "experience" if "experience" in usable else "meal" if "meal" in usable else None


def cost_of(op: dict) -> int | None:
    """Per-person cost estimate in VND, from the entry fee when there is one, else the middle of the price range."""
    fee = op.get("entry_fee")
    if fee and fee.get("typical_vnd") is not None:
        return int(fee["typical_vnd"])
    price = (op.get("price_per_person") or {}).get("value")
    if price and price.get("min_vnd") is not None and price.get("max_vnd") is not None:
        return (int(price["min_vnd"]) + int(price["max_vnd"])) // 2
    return None


def build_places(decision: dict, by_id: dict, cfg: Settings) -> tuple[list[Place], list[Unplaced]]:
    places, unplaced = [], []
    for c in decision["confirmed"]:
        pid = c["id"]
        name = c.get("name") or pid
        rec = by_id.get(pid)
        if rec is None:
            unplaced.append(Unplaced(pid, name, "no_record"))
            continue
        ident, op = rec["identity"], rec["operation"]
        kind = kind_of(rec)
        if kind is None:
            unplaced.append(Unplaced(pid, name, "not_plannable"))
        elif ident.get("lat") is None or ident.get("lng") is None:
            unplaced.append(Unplaced(pid, name, "no_coordinates"))
        elif not op.get("visit_minutes"):
            unplaced.append(Unplaced(pid, name, "no_visit_time"))
        else:
            hours = op.get("hours")
            places.append(Place(
                id=pid, name=ident.get("name") or name, kind=kind, role=c.get("role", "selected"),
                lat=float(ident["lat"]), lng=float(ident["lng"]), area=ident.get("area"),
                dup_group=rec.get("near_duplicate_group"),
                hours=parse_hours(hours["value"]) if hours else None,
                hours_status=hours["status"] if hours else None,
                visit=op["visit_minutes"], cost_vnd=cost_of(op),
                pins=tuple(f for f in cfg.pins if (feature(rec, f) or {}).get("value") == "present"),
                flags=tuple(c.get("flags") or ()), relaxed=tuple(c.get("relaxed") or ()), rec=rec))
    return places, unplaced


def resolve_point(base: dict | None, by_id: dict, geocode) -> tuple[Point | None, str | None]:
    """A Base ({"place_id", "text"}) -> a Point and None, or None and why not. A corpus place wins; otherwise the
    text is geocoded. geocode(text) -> {"lat", "lng", "label", "source", "fetched_at"} | None, may raise Unavailable."""
    if not base:
        return None, "unknown"
    rec = by_id.get(base.get("place_id"))
    if rec and rec["identity"].get("lat") is not None and rec["identity"].get("lng") is not None:
        return Point(float(rec["identity"]["lat"]), float(rec["identity"]["lng"]),
                     rec["identity"].get("name") or base.get("text") or "", "corpus", None), None
    text = (base.get("text") or "").strip()
    if not text:
        return None, "unknown"
    try:
        hit = geocode(text)
    except Unavailable:
        return None, "geocode_unavailable"
    if hit is None:
        return None, "not_found"
    return Point(hit["lat"], hit["lng"], hit.get("label") or text, hit["source"], hit.get("fetched_at")), None
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_places.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/places.py tests/planning/plan_fixtures.py tests/planning/test_planning_places.py
git commit -m "feat(planning): confirmed places become schedulable places"
```


### Task 3: Ma trận thời gian của chuyến

**Files:**
- Create: `src/planning/travel.py`
- Test: `tests/planning/test_planning_travel.py`

**Interfaces:**
- Consumes: `live.Unavailable`, `live.travel_matrix` (truyền vào), `planning.settings.Settings`.
- Produces:
  - `planning.travel.km(a, b) -> float` (haversine), `rough_minutes(distance_km, mobility, cfg) -> int`, `walk_minutes(distance_km, cfg) -> int`
  - `planning.travel.Travel` (`ids`, `legs`, `source`, `fetched_at`, `rough_pairs`; `.leg(a, b) -> (minutes, mode)`; `.leg(a, a) == (0, "none")`)
  - `planning.travel.build_travel(nodes: dict, mobility, cfg, live_cfg, matrix_fn) -> Travel` — `nodes` là `id -> (lat, lng)`; `matrix_fn` là `live.travel_matrix`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_travel.py`:

```python
from plan_fixtures import fake_matrix

from live import Unavailable
from planning import settings
from planning.travel import build_travel, km, rough_minutes, walk_minutes

CFG = settings.load(settings.PATH)
A, B, C = (11.9404, 108.4583), (11.9404, 108.4600), (11.9029, 108.4482)   # B is ~190 m from A; C is ~4 km away


def test_a_short_leg_is_walked_and_a_long_one_uses_the_matrix():
    t = build_travel({"a": A, "b": B, "c": C}, "motorbike", CFG, None, fake_matrix)
    assert t.leg("a", "b") == (walk_minutes(km(A, B), CFG), "walk")
    assert t.leg("a", "c")[1] == "motorbike" and t.leg("a", "c")[0] == fake_matrix([A, C], None, None)["minutes"][0][1]
    assert t.leg("a", "a") == (0, "none")
    assert (t.source, t.rough_pairs) == ("osrm", 0)


def test_a_dead_osrm_makes_the_whole_matrix_rough_and_says_so():
    def dead(points, mode, cfg):
        raise Unavailable("osrm down")

    t = build_travel({"a": A, "c": C}, "car", CFG, None, dead)
    assert t.source == "rough" and t.fetched_at is None
    assert t.leg("a", "c")[0] == rough_minutes(km(A, C), "car", CFG)


def test_one_pair_without_a_road_is_rough_and_counted_while_the_rest_stays_osrm():
    def holes(points, mode, cfg):
        m = fake_matrix(points, mode, cfg)
        m["minutes"][0][2] = None
        return m

    t = build_travel({"a": A, "b": B, "c": C}, "motorbike", CFG, None, holes)
    assert t.source == "osrm" and t.rough_pairs == 1
    assert t.leg("a", "c")[0] == rough_minutes(km(A, C), "motorbike", CFG)
    assert t.leg("c", "a")[0] == fake_matrix([A, B, C], None, None)["minutes"][2][0]


def test_a_single_node_needs_no_matrix():
    t = build_travel({"a": A}, None, CFG, None, lambda *a: (_ for _ in ()).throw(AssertionError("no call")))
    assert t.leg("a", "a") == (0, "none")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_travel.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/travel.py`:

```python
"""Travel times between the points of one trip: one OSRM matrix, short legs walked, a labelled rough fallback.

Every number here is an estimate. When OSRM is down the whole matrix is rough (source "rough"); a single pair OSRM
has no road for is rough too and is counted in rough_pairs.
"""

import math
from dataclasses import dataclass, field

from live import Unavailable

from .settings import Settings


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@dataclass
class Travel:
    ids: list[str]
    legs: list[list[tuple[int, str]]]   # legs[i][j] = (minutes, mode)
    source: str                         # osrm | rough
    fetched_at: str | None
    rough_pairs: int = 0
    index: dict = field(init=False)

    def __post_init__(self):
        self.index = {pid: i for i, pid in enumerate(self.ids)}

    def leg(self, a: str, b: str) -> tuple[int, str]:
        """(minutes, mode) from node a to node b; staying put costs nothing."""
        if a == b:
            return 0, "none"
        return self.legs[self.index[a]][self.index[b]]


def rough_minutes(distance_km: float, mobility: str | None, cfg: Settings) -> int:
    speed = cfg.rough_speed_kmh[mobility or "motorbike"]
    return max(1, round(distance_km * cfg.road_factor / speed * 60))


def walk_minutes(distance_km: float, cfg: Settings) -> int:
    return max(1, math.ceil(distance_km * cfg.road_factor / cfg.walk_kmh * 60))


def build_travel(nodes: dict, mobility: str | None, cfg: Settings, live_cfg, matrix_fn) -> Travel:
    """nodes: id -> (lat, lng). matrix_fn(points, mode, live_cfg) is live.travel_matrix."""
    ids = list(nodes)
    points = [nodes[i] for i in ids]
    source, fetched_at, minutes = "rough", None, None
    if len(points) >= 2:
        try:
            m = matrix_fn(points, mobility, live_cfg)
            source, fetched_at, minutes = m["source"], m["fetched_at"], m["minutes"]
        except Unavailable:
            pass
    rough_pairs = 0
    legs = []
    for i, a in enumerate(points):
        row = []
        for j, b in enumerate(points):
            d = km(a, b)
            if i == j:
                row.append((0, "none"))
            elif d < cfg.walk_km:
                row.append((walk_minutes(d, cfg), "walk"))
            elif minutes is not None and minutes[i][j] is not None:
                row.append((minutes[i][j], mobility or "motorbike"))
            else:
                row.append((rough_minutes(d, mobility, cfg), mobility or "motorbike"))
                rough_pairs += 1 if minutes is not None else 0
        legs.append(row)
    return Travel(ids, legs, source, fetched_at, rough_pairs)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_travel.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/travel.py tests/planning/test_planning_travel.py
git commit -m "feat(planning): one travel matrix per trip with walking and a labelled rough fallback"
```


### Task 4: Các ngày của chuyến

**Files:**
- Create: `src/planning/frame.py`
- Test: `tests/planning/test_planning_frame.py`

**Interfaces:**
- Consumes: `planning.model.Day`, `planning.settings.Settings`, `to_min`.
- Produces:
  - `planning.frame.trip_days(ctx: dict, cfg, home, entry, exit_) -> list[Day]` — `ctx` là `trip_context["context"]`; `home` / `entry` / `exit_` là id nút hoặc `None`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_frame.py`:

```python
from plan_fixtures import CFG

from planning.frame import trip_days


def ctx(**kw):
    base = {"start_date": "2026-12-12", "days": 3, "arrive_at": None, "leave_at": None, "day_end": None}
    return {**base, **kw}


def test_every_day_has_a_date_a_weekday_and_the_default_window():
    days = trip_days(ctx(), CFG, "h", None, None)
    assert [(d.date.isoformat(), d.weekday) for d in days] == [
        ("2026-12-12", "sat"), ("2026-12-13", "sun"), ("2026-12-14", "mon")]
    assert (days[1].start, days[1].end) == (480, 1260)


def test_the_first_day_opens_at_arrival_and_the_last_closes_at_departure():
    days = trip_days(ctx(arrive_at="13:30", leave_at="12:00", day_end="20:00"), CFG, "h", None, None)
    assert (days[0].start, days[0].end) == (810, 1200)
    assert (days[1].start, days[1].end) == (480, 1200)
    assert (days[2].start, days[2].end) == (480, 720)


def test_the_last_day_closes_at_the_default_leave_time_when_the_user_gave_none():
    assert trip_days(ctx(), CFG, "h", None, None)[-1].end == CFG.leave_at


def test_a_one_day_trip_is_both_the_first_and_the_last_day():
    (d,) = trip_days(ctx(days=1, arrive_at="10:00", leave_at="17:00"), CFG, "h", "in", "out")
    assert (d.start, d.end, d.start_node, d.end_node) == (600, 1020, "in", "out")


def test_the_day_opens_at_the_entry_point_and_closes_at_the_exit_point_otherwise_at_home():
    days = trip_days(ctx(), CFG, "h", "in", "out")
    assert [(d.start_node, d.end_node) for d in days] == [("in", "h"), ("h", "h"), ("h", "out")]


def test_without_an_entry_or_exit_point_every_day_is_home_to_home():
    assert [(d.start_node, d.end_node) for d in trip_days(ctx(), CFG, "h", None, None)] == [("h", "h")] * 3


def test_days_and_dates_the_user_never_gave_stay_unknown():
    days = trip_days(ctx(days=None, start_date=None), CFG, "h", None, None)
    assert len(days) == CFG.default_days and all(d.date is None and d.weekday is None for d in days)
    only_date = trip_days(ctx(days=None), CFG, "h", None, None)      # a start date without a length gives no weekdays
    assert all(d.weekday is None for d in only_date)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_frame.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/frame.py`:

```python
"""The days of the trip: date, weekday and the usable window of each day."""

from datetime import date, timedelta

from .model import Day
from .settings import Settings, to_min

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def trip_days(ctx: dict, cfg: Settings, home: str | None, entry: str | None, exit_: str | None) -> list[Day]:
    """ctx: trip_context["context"]. Day one opens at the entry point (else home) no earlier than arrive_at; the last
    day closes at the exit point (else home) no later than leave_at. Days and dates the user never gave stay unknown:
    without a start date there is no weekday, so no weekday-based check."""
    n = ctx.get("days") or cfg.default_days
    start = cfg.day_start
    end = to_min(ctx["day_end"]) if ctx.get("day_end") else cfg.day_end
    first = max(start, to_min(ctx["arrive_at"])) if ctx.get("arrive_at") else start
    last = min(end, to_min(ctx["leave_at"]) if ctx.get("leave_at") else cfg.leave_at)
    first_day = date.fromisoformat(ctx["start_date"]) if ctx.get("start_date") and ctx.get("days") else None
    out = []
    for i in range(n):
        d = first_day + timedelta(days=i) if first_day else None
        out.append(Day(index=i, date=d, weekday=WEEKDAYS[d.weekday()] if d else None,
                       start=first if i == 0 else start, end=last if i == n - 1 else end,
                       start_node=(entry or home) if i == 0 else home, end_node=(exit_ or home) if i == n - 1 else home))
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_frame.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/frame.py tests/planning/test_planning_frame.py
git commit -m "feat(planning): the days of a trip with their windows and end points"
```


### Task 5: Đồng hồ một ngày

**Files:**
- Create: `src/planning/schedule.py`
- Test: `tests/planning/test_planning_schedule.py`

**Interfaces:**
- Consumes: `planning.model`, `planning.places.windows_on`, `planning.travel.Travel`, `tests/planning/plan_fixtures.py::day_ctx`.
- Produces:
  - `planning.schedule.DayCtx(day, places, travel, cfg, pace, sun)`
  - `planning.schedule.intervals_for(place, ctx) -> list[(open, close)]`, `pin_window(place, ctx) -> (earliest start, latest start)`
  - `planning.schedule.simulate(order: list[str], ctx) -> DayResult` — dòng thời gian (`visit`, `travel`, `wait`, `buffer`, `rest`, `meal_free`), `travel_min`, `wait_min`, `end`, `notes` (`meal_missed:<tên>`), các vi phạm mô phỏng đã gặp (chỉ để xếp hạng thứ tự; `validate` mới kết luận)

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_schedule.py`:

```python
from plan_fixtures import all_days, day_ctx, flat_travel, rec

from planning.schedule import intervals_for, pin_window, simulate

OPEN_AT_10 = all_days("10:00", "20:00")


def kinds(r):
    return [i.kind for i in r.items]


def test_a_day_is_travel_visit_buffer_travel_visit_with_the_clock_running_forward():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    assert [(i.kind, i.start, i.end) for i in r.items] == [
        ("travel", 480, 490), ("visit", 490, 550), ("buffer", 550, 570), ("travel", 570, 580), ("visit", 580, 640)]
    assert (r.travel_min, r.wait_min, r.end, r.violations) == (20, 0, 640, ())


def test_arriving_before_opening_waits_and_the_wait_is_counted():
    cx = day_ctx([rec("a", 1, 1, hours=OPEN_AT_10)], start_node="h", extra_nodes=["h"])
    r = simulate(["a"], cx)
    assert [(i.kind, i.start, i.end) for i in r.items][1:] == [("wait", 490, 600), ("visit", 600, 660)]
    assert r.wait_min == 110


def test_with_no_start_point_the_first_stop_opens_the_day_instead_of_being_waited_for():
    r = simulate(["a"], day_ctx([rec("a", 1, 1, hours=OPEN_AT_10)]))
    assert [(i.kind, i.start) for i in r.items] == [("visit", 600)] and r.wait_min == 0


def test_a_place_closed_that_weekday_is_a_violation_and_an_unknown_weekday_does_not_constrain():
    closed = rec("a", 1, 1, hours={**all_days(), "mon": []})
    assert [v.kind for v in simulate(["a"], day_ctx([closed], weekday="mon")).violations] == ["hours"]
    assert simulate(["a"], day_ctx([closed], weekday="tue")).violations == ()
    assert simulate(["a"], day_ctx([closed], weekday=None)).violations == ()      # days differ, weekday unknown


def test_a_visit_that_would_end_after_closing_is_a_violation():
    late = rec("a", 1, 1, hours=all_days("08:00", "08:30"), visit=(30, 60, 90))
    assert [v.kind for v in simulate(["a"], day_ctx([late])).violations] == ["hours"]


def test_the_second_opening_interval_is_used_when_the_first_is_missed():
    split = rec("a", 1, 1, hours={d: [["08:00", "09:00"], ["15:00", "20:00"]] for d in all_days()})
    r = simulate(["a"], day_ctx([split], start=600, start_node="h", extra_nodes=["h"]))    # arrives 10:10, morning over
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 610), ("visit", 900)] and r.violations == ()


def test_hours_unknown_do_not_constrain():
    cx = day_ctx([rec("a", 1, 1, hours=None)])
    assert intervals_for(cx.places["a"], cx) == [(0, 1440)]


def test_a_sunset_place_is_held_until_the_sun_is_about_to_set():
    cx = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=(360, 1050), start_node="h",
                 extra_nodes=["h"])
    assert pin_window(cx.places["a"], cx) == (975, 1030)           # 75 to 20 minutes before 17:30
    r = simulate(["a"], cx)
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 490), ("visit", 975)] and r.violations == ()


def test_a_dawn_place_is_pinned_to_sunrise_and_missing_it_is_a_violation():
    cx = day_ctx([rec("a", 1, 1, features={"cloud_hunting": "present"})], sun=(360, 1050), start=480)
    assert pin_window(cx.places["a"], cx) == (330, 420)
    assert [v.kind for v in simulate(["a"], cx).violations] == ["hours"]      # the day opens at 08:00, too late


def test_without_a_known_sun_a_sun_pin_is_ignored_but_a_clock_pin_stays():
    sun = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=None)
    assert pin_window(sun.places["a"], sun) == (0, 1440)
    music = day_ctx([rec("b", 1, 1, features={"live_music": "present"})], sun=None)
    assert pin_window(music.places["b"], music) == (1080, 1200)


def test_a_meal_place_takes_the_lunch_window():
    cx = day_ctx([rec("m", 1, 1, usable=("meal", "backup"))], start_node="h", extra_nodes=["h"])
    r = simulate(["m"], cx)
    assert [(i.kind, i.start) for i in r.items][1:] == [("wait", 490), ("visit", 690)]


def test_a_lunch_nobody_takes_becomes_a_free_block_never_an_invented_place():
    cx = day_ctx([rec("a", 1, 1, visit=(60, 120, 240)), rec("b", 1, 1)], start=480, end_node="h", extra_nodes=["h"])
    r = simulate(["a", "b"], cx)
    meals = [i for i in r.items if i.kind == "meal_free"]
    assert len(meals) == 1 and meals[0].name == "lunch" and 690 <= meals[0].start <= 810
    assert all(i.place_id in (None, "a", "b") for i in r.items)


def test_a_day_that_opens_after_the_lunch_window_notes_it_instead_of_squeezing_a_meal_in():
    r = simulate(["a"], day_ctx([rec("a", 1, 1)], start=840))
    assert "meal_missed:lunch" in r.notes and "meal_free" not in kinds(r)


def test_a_rest_is_forced_once_active_minutes_pass_the_limit_and_the_day_goes_on():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    rests = [i for i in simulate(["a", "b", "c"], cx).items if i.kind == "rest"]
    assert len(rests) == 1 and rests[0].end - rests[0].start == 15


def test_no_rest_is_added_after_the_last_stop():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)], start_node="h", extra_nodes=["h"])
    assert kinds(simulate(["a", "b", "c"], cx))[-1] == "visit"


def test_the_buffer_grows_for_a_long_leg_and_for_uncertain_hours():
    plain = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)]))
    long_leg = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)], travel=flat_travel(["a", "b"], 40)))
    shaky = simulate(["a", "b"], day_ctx([rec("a", 1, 1, status="UNCERTAIN"), rec("b", 1, 1)]))

    def size(r):
        return next(i.end - i.start for i in r.items if i.kind == "buffer")

    assert (size(plain), size(long_leg), size(shaky)) == (20, 30, 30)


def test_the_way_back_to_the_end_node_counts_and_a_day_that_runs_late_is_a_violation():
    cx = day_ctx([rec("a", 1, 1, visit=(60, 600, 700))], start=480, end=700, end_node="h", extra_nodes=["h"])
    r = simulate(["a"], cx)
    assert r.items[-1].kind == "travel" and r.items[-1].to_id == "h"
    assert [v.kind for v in r.violations] == ["day_window"] and r.violations[0].minutes > 0


def test_an_empty_day_is_empty():
    r = simulate([], day_ctx([rec("a", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"]))
    assert (r.items, r.end, r.violations) == ((), 480, ())
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_schedule.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/schedule.py`:

```python
"""Clock for one day: given the order of the stops, when each is reached, how long it waits, and where the buffers,
rests and meals go. route.py tries orders through simulate(); validate.py re-checks the result independently.
"""

from dataclasses import dataclass

from .model import Day, DayResult, Item, Place, Violation
from .places import windows_on
from .settings import Settings
from .travel import Travel

DAY_MINUTES = 1440


@dataclass(frozen=True)
class DayCtx:
    day: Day
    places: dict                    # id -> Place
    travel: Travel
    cfg: Settings
    pace: str
    sun: tuple[int, int] | None     # (sunrise, sunset) of the day; None when the date or place is unknown


def intervals_for(place: Place, ctx: DayCtx) -> list[tuple[int, int]]:
    """When the place is open that day. Unknown hours or an unknown weekday do not constrain: the whole day."""
    w = windows_on(place.hours, ctx.day.weekday)
    return [(0, DAY_MINUTES)] if w is None else w


def pin_window(place: Place, ctx: DayCtx) -> tuple[int, int]:
    """(earliest start, latest start) for a place known for a timed feature. A sun-based pin on a day with no known
    sun is ignored rather than guessed."""
    lo, hi = 0, DAY_MINUTES
    for fid in place.pins:
        pin = ctx.cfg.pins[fid]
        if pin["anchor"] == "clock":
            a, b = pin["from"], pin["to"]
        elif ctx.sun is None:
            continue
        else:
            base = ctx.sun[0] if pin["anchor"] == "sunrise" else ctx.sun[1]
            a, b = base + pin["from_min"], base + pin["to_min"]
        lo, hi = max(lo, a), min(hi, b)
    return lo, hi


def _meal_slots(order: list[str], ctx: DayCtx) -> tuple[dict, list[str]]:
    """Meal places take the day's meal windows in order; the windows left over get a free block."""
    names = list(ctx.cfg.meal_windows)[: ctx.cfg.meals_per_day]
    meal_ids = [pid for pid in order if ctx.places[pid].kind == "meal"]
    claimed = dict(zip(meal_ids, names))
    return claimed, [n for n in names if n not in claimed.values()]


def _breaks(t: int, active: int, items: list, free: list, served: set, notes: list, ctx: DayCtx) -> tuple[int, int]:
    """Put the meal blocks that are due at time t, and a rest when active minutes ran too long."""
    cfg = ctx.cfg
    for name in free:
        a, b = cfg.meal_windows[name]
        if name in served or t < a:
            continue
        served.add(name)
        if t <= b:
            items.append(Item("meal_free", t, t + cfg.meal_min, name=name, note="free"))
            t, active = t + cfg.meal_min, 0
        else:
            notes.append(f"meal_missed:{name}")
    if active >= cfg.max_consecutive_min[ctx.pace]:
        items.append(Item("rest", t, t + cfg.rest_min[ctx.pace]))
        t, active = t + cfg.rest_min[ctx.pace], 0
    return t, active


def simulate(order: list[str], ctx: DayCtx) -> DayResult:
    cfg, day, travel = ctx.cfg, ctx.day, ctx.travel
    claimed, free = _meal_slots(order, ctx)
    t, here, active = day.start, day.start_node, 0
    items: list[Item] = []
    viol: list[Violation] = []
    notes: list[str] = []
    served: set = set()
    travel_min = wait_min = 0

    def move(frm: str | None, to: str | None):
        nonlocal t, active, travel_min
        if frm is None or to is None or frm == to:
            return
        m, mode = travel.leg(frm, to)
        items.append(Item("travel", t, t + m, from_id=frm, to_id=to, mode=mode))
        t, active, travel_min = t + m, active + m, travel_min + m

    for idx, pid in enumerate(order):
        p = ctx.places[pid]
        t, active = _breaks(t, active, items, free, served, notes, ctx)
        move(here, pid)
        visit = p.visit[cfg.visit_key[ctx.pace]]
        lo, hi = pin_window(p, ctx)
        if pid in claimed:
            a, b = cfg.meal_windows[claimed[pid]]
            lo, hi = max(lo, a), min(hi, b)
            served.add(claimed[pid])
        start = None
        for o, c in intervals_for(p, ctx):
            s = max(t, o, lo)
            if s <= hi and s + visit <= c:
                start = s
                break
        if start is None:
            viol.append(Violation("hours", day.index, pid, 0, False, "no feasible start"))
            start = t
        elif start > t:
            if here is not None:
                items.append(Item("wait", t, start, place_id=pid))
                wait_min += start - t
            t = start       # with no start point the day simply opens at the first stop: nothing is waited out
        items.append(Item("visit", start, start + visit, place_id=pid, name=p.name))
        t, active, here = start + visit, active + visit, pid
        nxt = order[idx + 1] if idx + 1 < len(order) else day.end_node
        if nxt is not None and nxt != pid:
            buffer = cfg.buffer_min[ctx.pace]
            if travel.leg(pid, nxt)[0] > cfg.long_leg_min:
                buffer += cfg.buffer_extra_long
            if p.hours_status in ("UNCERTAIN", "OUTDATED"):
                buffer += cfg.buffer_extra_uncertain
            items.append(Item("buffer", t, t + buffer))
            t += buffer
    if order and day.end_node not in (None, here):      # a day that just ends after its last stop needs no more breaks
        t, active = _breaks(t, active, items, free, served, notes, ctx)
        move(here, day.end_node)
    if t > day.end:
        viol.append(Violation("day_window", day.index, None, t - day.end, False, "the day runs past its end"))
    return DayResult(tuple(items), tuple(order), tuple(viol), travel_min, wait_min, t, tuple(notes), "single")
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_schedule.py -q`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/schedule.py tests/planning/test_planning_schedule.py
git commit -m "feat(planning): simulate one day with waits, buffers, rests, meals and timed pins"
```


### Task 6: Thứ tự trong ngày

**Files:**
- Create: `src/planning/route.py`
- Test: `tests/planning/test_planning_route.py`

**Interfaces:**
- Consumes: `planning.schedule.simulate`, `planning.schedule.DayCtx`, `planning.model.DayResult`.
- Produces:
  - `planning.route.order_day(ids: list[str], ctx: DayCtx) -> DayResult` — `method` là `exact` (tới `cfg.exact_n` nơi) hoặc `heuristic`; ít vi phạm hơn thắng, rồi kết thúc sớm hơn thắng

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_route.py`:

```python
from plan_fixtures import all_days, day_ctx, flat_travel, line_travel, rec

from planning.route import order_day
from planning.schedule import simulate


def test_the_best_order_of_a_few_stops_is_found_by_trying_them_all():
    travel = flat_travel(["h", "a", "b", "c"], 10, h_b=20, h_c=30, a_c=20)      # h - a - b - c along a road
    cx = day_ctx([rec("c", 1, 1), rec("a", 1, 1), rec("b", 1, 1)], start_node="h", extra_nodes=["h"], travel=travel)
    r = order_day(["c", "a", "b"], cx)
    assert r.order == ("a", "b", "c") and r.method == "exact" and r.violations == ()


def test_a_place_that_opens_late_goes_last_even_though_it_is_close():
    late = rec("b", 1, 1, hours=all_days("15:00", "20:00"))
    cx = day_ctx([rec("a", 1, 1), late, rec("c", 1, 1)], start_node="h", extra_nodes=["h"])
    r = order_day(["a", "b", "c"], cx)
    assert r.order[-1] == "b" and r.violations == ()


def test_an_order_without_violations_beats_a_shorter_one_with_a_violation():
    morning_only = rec("a", 1, 1, hours=all_days("08:00", "10:00"))
    travel = flat_travel(["h", "a", "b"], 60, h_a=30, h_b=5)
    cx = day_ctx([morning_only, rec("b", 1, 1)], start_node="h", extra_nodes=["h"], travel=travel)
    assert simulate(["b", "a"], cx).end < simulate(["a", "b"], cx).end      # b first is quicker but misses a's hours
    r = order_day(["a", "b"], cx)
    assert r.order == ("a", "b") and r.violations == ()


def test_the_same_input_gives_the_same_order():
    recs = [rec(f"p{i}", 1, 1) for i in range(5)]
    cx = day_ctx(recs, start_node="h", extra_nodes=["h"], travel=line_travel(
        {"h": -1, "p0": 3, "p1": 0, "p2": 4, "p3": 1, "p4": 2}))
    first = order_day([r["id"] for r in recs], cx)
    assert order_day(list(reversed([r["id"] for r in recs])), cx) == first


def test_more_stops_than_exact_n_use_the_heuristic_and_still_place_every_stop_once():
    pos = {f"p{i}": (i * 7) % 8 for i in range(8)}                 # 8 stops in a scrambled order along a line
    recs = [rec(pid, 1, 1, visit=(10, 20, 30)) for pid in pos]
    cx = day_ctx(recs, start_node="h", extra_nodes=["h"], travel=line_travel({"h": -1, **pos}, scale=3))
    r = order_day(list(pos), cx)
    assert r.method == "heuristic" and sorted(r.order) == sorted(pos)
    assert list(r.order) == sorted(pos, key=pos.get)               # the line is walked end to end


def test_zero_and_one_stop_need_no_search():
    cx = day_ctx([rec("a", 1, 1)], start_node="h", extra_nodes=["h"])
    assert order_day([], cx).items == ()
    assert order_day(["a"], cx) == simulate(["a"], cx)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_route.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/route.py`:

```python
"""Order of the stops inside one day: every permutation up to exact_n stops, else nearest neighbour + 2-opt + or-opt.

Both are deterministic: ties keep the first order found, and the input ids are sorted before anything is tried.
"""

from dataclasses import replace
from itertools import permutations

from .model import DayResult
from .schedule import DayCtx, simulate


def order_day(ids: list[str], ctx: DayCtx) -> DayResult:
    ids = sorted(ids)
    if len(ids) <= 1:
        return simulate(ids, ctx)
    if len(ids) <= ctx.cfg.exact_n:
        best = None
        for perm in permutations(ids):
            r = simulate(list(perm), ctx)
            if best is None or r.key < best.key:
                best = r
        return replace(best, method="exact")
    return replace(_heuristic(ids, ctx), method="heuristic")


def _nearest_neighbour(ids: list[str], ctx: DayCtx) -> list[str]:
    left, order, here = list(ids), [], ctx.day.start_node
    while left:
        nxt = min(left, key=lambda x: (ctx.travel.leg(here, x)[0] if here else 0, x))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return order


def _heuristic(ids: list[str], ctx: DayCtx) -> DayResult:
    order = _nearest_neighbour(ids, ctx)
    best = simulate(order, ctx)
    n = len(order)
    for _ in range(ctx.cfg.improve_passes):
        improved = False
        for i in range(n - 1):                      # 2-opt: reverse a stretch
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                r = simulate(cand, ctx)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        for i in range(n):                          # or-opt: move one stop elsewhere
            for j in range(n):
                if i == j:
                    continue
                cand = order[:]
                cand.insert(j, cand.pop(i))
                r = simulate(cand, ctx)
                if r.key < best.key:
                    order, best, improved = cand, r, True
        if not improved:
            break
    return best
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_route.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/route.py tests/planning/test_planning_route.py
git commit -m "feat(planning): order the stops of a day, exactly up to exact_n and heuristically beyond"
```


### Task 7: Gom cụm

**Files:**
- Create: `src/planning/cluster.py`
- Test: `tests/planning/test_planning_cluster.py`

**Interfaces:**
- Consumes: `planning.travel.Travel`, `cfg.cluster_max_min`, `cfg.cluster_merge_min`.
- Produces:
  - `planning.cluster.distance(a, b, travel) -> int` (đối xứng, lấy chiều chậm hơn)
  - `planning.cluster.cluster_places(ids, area_of: dict, travel, cfg) -> list[list[str]]` (kết quả không phụ thuộc thứ tự `ids`)
  - `planning.cluster.split_to_fit(clusters, load_of, cap: int, travel) -> list[list[str]]`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_cluster.py`:

```python
from plan_fixtures import CFG, line_travel

from planning.cluster import cluster_places, distance, split_to_fit


def test_places_of_one_area_that_are_close_form_one_cluster():
    travel = line_travel({"a": 0, "b": 1, "c": 2, "x": 10, "y": 11})                      # 5 minutes per unit
    got = cluster_places(["a", "b", "c", "x", "y"], {"a": "A", "b": "A", "c": "A", "x": "B", "y": "B"}, travel, CFG)
    assert got == [["a", "b", "c"], ["x", "y"]]


def test_a_cluster_is_cut_where_the_real_travel_gets_too_long():
    travel = line_travel({"a": 0, "b": 1, "far": 20})                                    # 100 minutes to "far"
    assert cluster_places(["a", "b", "far"], {}, travel, CFG) == [["a", "b"], ["far"]]


def test_the_farthest_members_decide_not_the_nearest_neighbours():
    travel = line_travel({"a": 0, "b": 4, "c": 8})        # a-b and b-c are 20, but a-c is 40 > cluster_max_min 25
    assert cluster_places(["a", "b", "c"], {}, travel, CFG) == [["a", "b"], ["c"]]


def test_clusters_of_different_areas_merge_only_when_they_touch():
    travel = line_travel({"a": 0, "b": 1})                                               # 5 minutes apart
    assert cluster_places(["a", "b"], {"a": "A", "b": "B"}, travel, CFG) == [["a", "b"]]
    travel = line_travel({"a": 0, "b": 4})                                               # 20 minutes apart
    assert cluster_places(["a", "b"], {"a": "A", "b": "B"}, travel, CFG) == [["a"], ["b"]]


def test_a_place_with_no_area_is_clustered_by_distance_alone():
    travel = line_travel({"a": 0, "b": 1})
    assert cluster_places(["a", "b"], {"a": None, "b": None}, travel, CFG) == [["a", "b"]]


def test_the_result_does_not_depend_on_the_input_order():
    travel = line_travel({"a": 0, "b": 1, "c": 2, "x": 30})
    assert cluster_places(["x", "c", "a", "b"], {}, travel, CFG) == cluster_places(["a", "b", "c", "x"], {}, travel, CFG)


def test_distance_is_symmetric_even_when_the_matrix_is_not():
    travel = line_travel({"a": 0, "b": 4})
    travel.legs[0][1] = (30, "motorbike")                                                # one way is slower
    assert distance("a", "b", travel) == distance("b", "a", travel) == 30


def test_a_cluster_too_big_for_a_day_is_split_around_its_farthest_pair():
    travel = line_travel({"a": 0, "b": 1, "c": 10, "d": 11})
    load = lambda ids: 60 * len(ids)
    assert split_to_fit([["a", "b", "c", "d"]], load, 150, travel) == [["a", "b"], ["c", "d"]]


def test_a_cluster_that_fits_is_left_alone_and_a_single_place_is_never_split():
    travel = line_travel({"a": 0, "b": 1})
    assert split_to_fit([["a", "b"]], lambda ids: 100, 150, travel) == [["a", "b"]]
    assert split_to_fit([["a"]], lambda ids: 999, 150, travel) == [["a"]]
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_cluster.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/cluster.py`:

```python
"""Clusters of places that are close in real travel time: the unit a day is built from.

Area of the serving record first (complete-link inside it), then a cross-area merge for clusters that touch. A
cluster too big for a day is split in two around its farthest pair, repeatedly, so a day is never one lump.
"""

from .travel import Travel


def distance(a: str, b: str, travel: Travel) -> int:
    return max(travel.leg(a, b)[0], travel.leg(b, a)[0])


def _link(clusters: list[list[str]], travel: Travel, limit: int) -> list[list[str]]:
    """Merge the closest pair (complete-link: the farthest members decide) while that stays within limit."""
    cs = [sorted(c) for c in clusters]
    while True:
        best = None
        for x in range(len(cs)):
            for y in range(x + 1, len(cs)):
                d = max(distance(a, b, travel) for a in cs[x] for b in cs[y])
                if d <= limit and (best is None or d < best[0]):
                    best = (d, x, y)
        if best is None:
            return cs
        _, x, y = best
        cs[x] = sorted(cs[x] + cs[y])
        del cs[y]


def cluster_places(ids: list[str], area_of: dict, travel: Travel, cfg) -> list[list[str]]:
    groups: dict = {}
    for i in sorted(ids):
        groups.setdefault(area_of.get(i) or "", []).append(i)
    clusters: list[list[str]] = []
    for key in sorted(groups):
        clusters += _link([[i] for i in groups[key]], travel, cfg.cluster_max_min)
    clusters = _link(clusters, travel, cfg.cluster_merge_min)
    return sorted(clusters, key=lambda c: c[0])


def split_to_fit(clusters: list[list[str]], load_of, cap: int, travel: Travel) -> list[list[str]]:
    """load_of(ids) -> minutes. Split every cluster whose load exceeds cap around its farthest pair."""
    def split(c: list[str]) -> list[list[str]]:
        if len(c) < 2 or load_of(c) <= cap:
            return [c]
        _, a, b = max(((distance(x, y, travel), x, y) for x in c for y in c if x < y), key=lambda t: (t[0], t[1], t[2]))
        ga = [x for x in c if distance(x, a, travel) <= distance(x, b, travel)]
        gb = [x for x in c if x not in ga]
        if not gb:
            return [c]
        return split(sorted(ga)) + split(sorted(gb))

    out = [part for c in clusters for part in split(c)]
    return sorted(out, key=lambda c: c[0])
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_cluster.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/cluster.py tests/planning/test_planning_cluster.py
git commit -m "feat(planning): cluster places by real travel time"
```


### Task 8: Chia cụm vào ngày

**Files:**
- Create: `src/planning/days.py`
- Test: `tests/planning/test_planning_days.py`

**Interfaces:**
- Consumes: `planning.schedule.DayCtx`, `planning.places.windows_on`.
- Produces:
  - `planning.days.load_of(ids, places, cfg, pace) -> int`, `blocked(ids, ctx) -> int`, `day_cost(ids, ctx) -> float`
  - `planning.days.assign_days(clusters, ctxs: list[DayCtx]) -> (list[list[str]], str | None)` — mỗi ngày một danh sách id; cờ `"days_fallback"` khi quá `max_days` / `max_clusters`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_days.py`:

```python
from plan_fixtures import CFG, all_days, day_ctx, line_travel, rec

from planning.days import assign_days, blocked, day_cost, load_of


def two_days(recs, positions, weekdays=("mon", "tue")):
    """Two DayCtx over the same places and travel, one per weekday."""
    travel = line_travel(positions)
    return [day_ctx(recs, weekday=wd, travel=travel) for wd in weekdays]


def test_two_far_apart_clusters_go_on_separate_days():
    pos = {"a1": 0, "a2": 1, "a3": 2, "b1": 100, "b2": 101, "b3": 102}
    recs = [rec(i, 1, 1) for i in pos]
    out, flag = assign_days([["a1", "a2", "a3"], ["b1", "b2", "b3"]], two_days(recs, pos))
    assert flag is None and sorted(map(sorted, out)) == [["a1", "a2", "a3"], ["b1", "b2", "b3"]]


def test_a_cluster_with_a_place_closed_that_day_moves_to_the_other_day():
    pos = {"a1": 0, "a2": 1, "a3": 2, "b1": 3, "b2": 4, "b3": 5}
    shut_mon = {**all_days(), "mon": []}
    recs = [rec("a1", 1, 1, hours=shut_mon), rec("a2", 1, 1), rec("a3", 1, 1),
            rec("b1", 1, 1), rec("b2", 1, 1), rec("b3", 1, 1)]
    out, _ = assign_days([["a1", "a2", "a3"], ["b1", "b2", "b3"]], two_days(recs, pos))
    assert out == [["b1", "b2", "b3"], ["a1", "a2", "a3"]]


def test_a_place_is_blocked_on_a_day_it_is_closed_or_only_opens_after_the_day_ends():
    evening = rec("e", 1, 1, hours=all_days("18:00", "22:00"))
    shut = rec("s", 1, 1, hours={**all_days(), "mon": []})
    fine = rec("f", 1, 1)
    short_day = day_ctx([evening, shut, fine], weekday="mon", end=900)
    assert blocked(["e", "s", "f"], short_day) == 2
    assert blocked(["e", "s", "f"], day_ctx([evening, shut, fine], weekday="tue")) == 0
    assert blocked(["e"], day_ctx([rec("n", 1, 1, hours=None), evening], weekday="mon", end=900)) == 1


def test_a_cluster_with_an_evening_only_place_never_goes_on_a_day_that_ends_before_it_opens():
    pos = {"e1": 0, "e2": 1, "x1": 50, "x2": 51}
    evening = all_days("18:00", "22:00")
    recs = [rec("e1", 1, 1, hours=evening), rec("e2", 1, 1), rec("x1", 1, 1), rec("x2", 1, 1)]
    travel = line_travel(pos)
    ctxs = [day_ctx(recs, weekday="mon", end=900, travel=travel), day_ctx(recs, weekday="tue", travel=travel)]
    out, _ = assign_days([["e1", "e2"], ["x1", "x2"]], ctxs)
    assert "e1" in out[1]


def test_the_greedy_fallback_also_keeps_a_place_off_a_day_it_cannot_use():
    pos = {f"p{i}": i * 50 for i in range(9)}
    recs = [rec(i, 1, 1, hours=all_days("18:00", "22:00") if i == "p0" else "open") for i in pos]
    travel = line_travel(pos)
    ctxs = [day_ctx(recs, weekday="mon", end=900, travel=travel), day_ctx(recs, weekday="tue", travel=travel)]
    out, flag = assign_days([[i] for i in pos], ctxs)
    assert flag == "days_fallback" and "p0" in out[1]


def test_a_day_that_cannot_hold_its_load_costs_more():
    pos = {f"p{i}": i for i in range(6)}
    recs = [rec(i, 1, 1, visit=(120, 180, 240)) for i in pos]
    cx = day_ctx(recs, travel=line_travel(pos))
    assert day_cost(list(pos)[:2], cx) < day_cost(list(pos), cx)


def test_the_planned_count_per_day_follows_the_pace():
    recs = [rec(f"p{i}", 1, 1) for i in range(3)]
    slow, packed = day_ctx(recs, pace="slow"), day_ctx(recs, pace="packed")
    ids = ["p0", "p1", "p2"]
    assert day_cost(ids, slow) < day_cost(ids, packed)       # three places is the slow target and under the packed one


def test_no_clusters_means_empty_days():
    cx = day_ctx([rec("a", 1, 1)])
    assert assign_days([], [cx, cx]) == ([[], []], None)


def test_the_same_input_always_gives_the_same_split():
    pos = {f"p{i}": i * 3 for i in range(6)}
    recs = [rec(i, 1, 1) for i in pos]
    clusters = [["p0", "p1"], ["p2", "p3"], ["p4", "p5"]]
    ctxs = two_days(recs, pos)
    assert assign_days(clusters, ctxs) == assign_days(clusters, ctxs)


def test_more_clusters_than_max_clusters_falls_back_to_greedy_and_says_so():
    pos = {f"p{i}": i * 50 for i in range(9)}
    recs = [rec(i, 1, 1) for i in pos]
    out, flag = assign_days([[i] for i in pos], two_days(recs, pos))
    assert flag == "days_fallback" and sorted(i for d in out for i in d) == sorted(pos)
    assert abs(len(out[0]) - len(out[1])) <= 1


def test_load_is_visit_minutes_by_pace_plus_the_moves_inside_the_cluster():
    cx = day_ctx([rec("a", 1, 1, visit=(10, 20, 30))])
    assert load_of(["a"], cx.places, CFG, "slow") == 30 + CFG.intra_leg_min
    assert load_of(["a"], cx.places, CFG, "packed") == 10 + CFG.intra_leg_min
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_days.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/days.py`:

```python
"""Which cluster goes on which day. Dynamic programming over subsets of clusters: exact, so the same input always gives
the same split. Past max_days / max_clusters it falls back to a greedy split and says so.
"""

from .places import windows_on
from .schedule import DayCtx


def _tour(ids: list[str], ctx: DayCtx) -> int:
    """Nearest-neighbour path minutes from the day's start through ids to its end: a cheap stand-in for route.py."""
    travel, here, total, left = ctx.travel, ctx.day.start_node, 0, sorted(ids)
    while left:
        nxt = min(left, key=lambda x: (travel.leg(here, x)[0] if here else 0, x))
        total += travel.leg(here, nxt)[0] if here else 0
        here = nxt
        left.remove(nxt)
    if here and ctx.day.end_node:
        total += travel.leg(here, ctx.day.end_node)[0]
    return total


def load_of(ids: list[str], places: dict, cfg, pace: str) -> int:
    """Minutes a set of places asks of a day before travel between clusters: visits plus moving inside the cluster."""
    return sum(places[i].visit[cfg.visit_key[pace]] + cfg.intra_leg_min for i in ids)


def blocked(ids: list[str], ctx: DayCtx) -> int:
    """How many of the places cannot be visited at all inside this day: closed that weekday, or not open long enough
    within the day's window (a restaurant that opens at 18:00 on a day that ends at 15:00)."""
    n = 0
    for i in ids:
        p = ctx.places[i]
        w = windows_on(p.hours, ctx.day.weekday)
        need = p.visit[ctx.cfg.visit_key[ctx.pace]]
        if w is not None and not any(min(c, ctx.day.end) - max(o, ctx.day.start) >= need for o, c in w):
            n += 1
    return n


def day_cost(ids: list[str], ctx: DayCtx) -> float:
    cfg, w = ctx.cfg, ctx.cfg.weights
    target = cfg.per_day[ctx.pace]
    if not ids:
        return w["count"] * target
    closed = blocked(ids, ctx)
    tour = _tour(ids, ctx)
    over = max(0, load_of(ids, ctx.places, cfg, ctx.pace) + tour - (ctx.day.end - ctx.day.start))
    return w["travel"] * tour + w["overflow"] * over + w["count"] * abs(len(ids) - target) + w["closed"] * closed


def assign_days(clusters: list[list[str]], ctxs: list[DayCtx]) -> tuple[list[list[str]], str | None]:
    """-> (place ids of each day, flag). flag is "days_fallback" when the exact search was not used."""
    cfg, n, d_count = ctxs[0].cfg, len(clusters), len(ctxs)
    if n == 0:
        return [[] for _ in ctxs], None
    if d_count > cfg.max_days or n > cfg.max_clusters:
        return _greedy(clusters, ctxs), "days_fallback"

    def members(mask: int) -> list[str]:
        return [i for k in range(n) if mask >> k & 1 for i in clusters[k]]

    inf = float("inf")
    dp = [[inf] * (1 << n) for _ in range(d_count + 1)]
    back = [[0] * (1 << n) for _ in range(d_count + 1)]
    dp[0][0] = 0.0
    cost: dict = {}
    for d in range(1, d_count + 1):
        for mask in range(1 << n):
            sub = mask
            while True:
                prev = dp[d - 1][mask ^ sub]
                if prev < inf:
                    if (d, sub) not in cost:
                        cost[(d, sub)] = day_cost(members(sub), ctxs[d - 1])
                    c = prev + cost[(d, sub)]
                    if c < dp[d][mask]:
                        dp[d][mask], back[d][mask] = c, sub
                if sub == 0:
                    break
                sub = (sub - 1) & mask
    out, mask = [[] for _ in ctxs], (1 << n) - 1
    for d in range(d_count, 0, -1):
        sub = back[d][mask]
        out[d - 1] = members(sub)
        mask ^= sub
    return out, None


def _greedy(clusters: list[list[str]], ctxs: list[DayCtx]) -> list[list[str]]:
    """Biggest cluster first, onto the day where the fewest of its places are blocked, then the least load so far
    (ties: the earlier day)."""
    cx = ctxs[0]
    size = lambda c: load_of(c, cx.places, cx.cfg, cx.pace)
    out = [[] for _ in ctxs]
    for c in sorted(clusters, key=lambda c: (-size(c), c[0])):
        d = min(range(len(ctxs)), key=lambda k: (blocked(c, ctxs[k]), load_of(out[k], cx.places, cx.cfg, cx.pace), k))
        out[d] += c
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_days.py -q`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/days.py tests/planning/test_planning_days.py
git commit -m "feat(planning): assign clusters to days by dynamic programming over subsets"
```


### Task 9: Kiểm tra cuối

**Files:**
- Create: `src/planning/validate.py`
- Test: `tests/planning/test_planning_validate.py`

**Interfaces:**
- Consumes: `planning.schedule.DayCtx/intervals_for/pin_window`, `corpus.serving.check`, `corpus.ontology.load`.
- Produces:
  - `planning.validate.validate(ctxs, results, hard_filters: list, anchors: set, budget_vnd, max_leg_min) -> list[Violation]` — danh sách rỗng = đạt

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_validate.py`:

```python
from dataclasses import replace

from plan_fixtures import all_days, day_ctx, rec

from planning.model import DayResult, Item
from planning.route import order_day
from planning.validate import validate


def result(*items):
    return DayResult(tuple(items), (), (), 0, 0, items[-1].end if items else 0)


def visit(pid, start, end):
    return Item("visit", start, end, place_id=pid, name=pid)


def kinds(violations):
    return sorted(v.kind for v in violations)


def run(cx, res, hard=(), anchors=(), budget=None, max_leg=None):
    return validate([cx], [res], list(hard), set(anchors), budget, max_leg)


def test_a_plan_the_scheduler_built_validly_passes():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], start_node="h", end_node="h", extra_nodes=["h"])
    assert run(cx, order_day(["a", "b"], cx), anchors=["a"]) == []


def test_a_visit_outside_the_opening_hours_fails_even_if_the_scheduler_said_nothing():
    cx = day_ctx([rec("a", 1, 1, hours=all_days("08:00", "09:00"))])
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_place_closed_that_weekday_fails():
    cx = day_ctx([rec("a", 1, 1, hours={**all_days(), "mon": []})], weekday="mon")
    assert kinds(run(cx, result(visit("a", 600, 660)))) == ["hours"]


def test_a_sunset_place_visited_at_noon_fails_the_timed_check():
    cx = day_ctx([rec("a", 1, 1, features={"sunset_view": "present"})], sun=(360, 1050))
    assert kinds(run(cx, result(visit("a", 720, 780)))) == ["timed"]


def test_overlapping_items_fail():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660), visit("b", 650, 710)))
    assert kinds(v) == ["overlap"] and v[0].minutes == 10


def test_a_day_that_runs_past_its_end_or_starts_before_it_fails():
    cx = day_ctx([rec("a", 1, 1, hours=None)], start=480, end=700)      # no hours, so only the day window can fail
    assert kinds(run(cx, result(visit("a", 650, 750)))) == ["day_window"]
    assert kinds(run(cx, result(visit("a", 400, 460)))) == ["day_window"]


def test_a_travel_leg_shorter_than_the_travel_time_fails_and_one_over_the_limit_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)], minutes=30)
    short = Item("travel", 600, 610, from_id="a", to_id="b", mode="motorbike")
    assert kinds(run(cx, result(short))) == ["travel"]
    exact = Item("travel", 600, 630, from_id="a", to_id="b", mode="motorbike")
    assert run(cx, result(exact)) == []
    assert kinds(run(cx, result(exact), max_leg=20)) == ["long_leg"]


def test_an_anchor_that_is_not_in_the_plan_fails():
    cx = day_ctx([rec("a", 1, 1), rec("b", 1, 1)])
    v = run(cx, result(visit("a", 600, 660)), anchors=["a", "b"])
    assert [(x.kind, x.place_id) for x in v] == [("anchor", "b")]


def test_a_day_over_the_budget_fails_and_unknown_prices_are_not_counted():
    price = lambda n: {"min_vnd": n, "typical_vnd": n, "max_vnd": n}
    cx = day_ctx([rec("a", 1, 1, price=price(200000)), rec("b", 1, 1, price=price(150000)), rec("c", 1, 1)])
    res = result(visit("a", 600, 660), visit("b", 700, 760), visit("c", 800, 860))
    assert [(v.kind, v.minutes) for v in run(cx, res, budget=300000)] == [("budget", 50000)]
    assert run(cx, res, budget=400000) == []


def test_a_hard_filter_the_place_clearly_breaks_fails_and_a_physical_one_says_so():
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    cx = day_ctx([steep])
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(cx, result(visit("a", 600, 660)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", True)]


def test_a_relaxed_filter_and_a_place_with_no_evidence_do_not_fail():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "flag"}]
    unknown = day_ctx([rec("u", 1, 1)])
    assert run(unknown, result(visit("u", 600, 660)), hard=hard) == []
    steep = rec("a", 1, 1, features={"steep_or_stairs": "present"})
    relaxed = day_ctx([steep])
    relaxed.places["a"] = replace(relaxed.places["a"], relaxed=("steep_or_stairs",))
    assert run(relaxed, result(visit("a", 600, 660)), hard=hard) == []


def test_the_same_place_twice_and_two_near_duplicates_fail():
    cx = day_ctx([rec("a", 1, 1, dup=7), rec("b", 1, 1, dup=7)])
    assert kinds(run(cx, result(visit("a", 600, 660), visit("a", 700, 760)))) == ["duplicate"]
    v = run(cx, result(visit("a", 600, 660), visit("b", 700, 760)))
    assert kinds(v) == ["duplicate"] and v[0].place_id == "b"


def test_a_non_physical_hard_filter_is_not_marked_physical():
    noisy = rec("a", 1, 1, features={"live_music": "present"})
    hard = [{"feature": "live_music", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    v = run(day_ctx([noisy]), result(visit("a", 1100, 1160)), hard=hard)
    assert [(x.kind, x.physical) for x in v] == [("hard", False)]
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_validate.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/validate.py`:

```python
"""Final check (docs/ARCHITECTURE.md §11): the only place that decides whether a plan passes.

It re-derives every check from the finished timeline instead of trusting what simulate() noticed, so a bug in the
scheduler cannot also hide from the check. Fail-closed: a violation is reported, never repaired here.
"""

from corpus.ontology import load as load_ontology
from corpus.serving import check

from .model import DayResult, Violation
from .schedule import DayCtx, intervals_for, pin_window


def _is_physical(feature: str) -> bool:
    f = load_ontology().features.get(feature)
    return f is not None and f.group == "effort"


def validate(ctxs: list[DayCtx], results: list[DayResult], hard_filters: list, anchors: set,
             budget_vnd: int | None, max_leg_min: int | None) -> list[Violation]:
    out: list[Violation] = []
    visited: dict = {}
    dup_groups: dict = {}
    for cx, r in zip(ctxs, results):
        d = cx.day
        items = sorted(r.items, key=lambda i: (i.start, i.end))
        for a, b in zip(items, items[1:]):
            if b.start < a.end:
                out.append(Violation("overlap", d.index, b.place_id or a.place_id, a.end - b.start, False,
                                     f"{a.kind} and {b.kind} overlap"))
        if items and items[-1].end > d.end:
            out.append(Violation("day_window", d.index, None, items[-1].end - d.end, False, "the day runs past its end"))
        if items and items[0].start < d.start:
            out.append(Violation("day_window", d.index, None, d.start - items[0].start, False, "starts before the day"))
        spend = 0
        for it in items:
            if it.kind == "travel":
                need = cx.travel.leg(it.from_id, it.to_id)[0]
                if it.end - it.start < need:
                    out.append(Violation("travel", d.index, it.to_id, need - (it.end - it.start), False,
                                         "shorter than the travel time"))
                if max_leg_min and it.end - it.start > max_leg_min:
                    out.append(Violation("long_leg", d.index, it.to_id, it.end - it.start - max_leg_min, False,
                                         f"longer than {max_leg_min} min"))
            if it.kind != "visit":
                continue
            p = cx.places[it.place_id]
            if not any(o <= it.start and it.end <= c for o, c in intervals_for(p, cx)):
                out.append(Violation("hours", d.index, p.id, 0, False, "visit outside the opening hours"))
            lo, hi = pin_window(p, cx)
            if not lo <= it.start <= hi:
                out.append(Violation("timed", d.index, p.id, 0, False, "off the time of day its feature needs"))
            if p.id in visited:
                out.append(Violation("duplicate", d.index, p.id, 0, False, "the place is scheduled twice"))
            visited[p.id] = d.index
            if p.dup_group is not None and dup_groups.setdefault(p.dup_group, p.id) != p.id:
                out.append(Violation("duplicate", d.index, p.id, 0, False,
                                     f"near duplicate of {dup_groups[p.dup_group]}"))
            spend += p.cost_vnd or 0
            for hf in hard_filters:
                if hf["op"] == "ne" and hf["feature"] not in p.relaxed \
                        and check(p.rec, hf["feature"], hf["value"]) == "fail":
                    out.append(Violation("hard", d.index, p.id, 0, _is_physical(hf["feature"]),
                                         f'{hf["feature"]} != {hf["value"]}'))
        if budget_vnd and spend > budget_vnd:
            out.append(Violation("budget", d.index, None, spend - budget_vnd, False,
                                 f"{spend} VND per person against {budget_vnd}"))
    for pid in sorted(anchors - set(visited)):
        out.append(Violation("anchor", None, pid, 0, False, "an anchor is not in the plan"))
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_validate.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/validate.py tests/planning/test_planning_validate.py
git commit -m "feat(planning): final validation derived from the finished timeline"
```


### Task 10: Dựng kế hoạch và public API

**Files:**
- Create: `src/planning/build.py`
- Modify: `src/planning/__init__.py`
- Test: `tests/planning/test_planning_build.py`

**Interfaces:**
- Consumes: tất cả Task 1–9; `live.travel_matrix/geocode/sun_times/load_settings`.
- Produces:
  - `planning.build_plan(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None) -> dict` — Plan Output (phần P3). Các tham số sau `records` để test thay nguồn ngoài: `matrix_fn(points, mode, live_cfg)` = `live.travel_matrix`, `geocode_fn(text)`, `sun_fn(date, lat, lng, tz_offset_h)` = `live.sun_times`
  - `planning.render_text(plan) -> str`
  - `planning.Settings`, `planning.load_settings`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_build.py`:

```python
import json

from plan_fixtures import CFG, decision, fake_matrix, fixed_sun, no_geocode, rec

from live import Unavailable
from planning import build_plan, render_text

CENTRE = (11.9404, 108.4583)
FAR = (11.9029, 108.4482)       # about 4 km from the centre


def spot(pid, anchor, i, **kw):
    return rec(pid, anchor[0] + i * 0.002, anchor[1] + i * 0.002, area="area-1" if anchor == CENTRE else "area-2", **kw)


def trip(**kw):
    """Four places in the centre, three out south and a restaurant."""
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2), spot("c4", CENTRE, 3),
            spot("s1", FAR, 0), spot("s2", FAR, 1), spot("s3", FAR, 2),
            spot("r1", CENTRE, 4, usable=("meal", "backup"))]
    return decision([r["id"] for r in recs], **kw), recs


def build(d, recs, matrix=fake_matrix, geocode=no_geocode, **kw):
    return build_plan(d, recs, cfg=CFG, live_cfg=_Live(), geocode_fn=geocode, matrix_fn=matrix, sun_fn=fixed_sun, **kw)


class _Live:
    tz_offset_h = 7


def visits(plan):
    return [[i["place_id"] for i in d["items"] if i["kind"] == "visit"] for d in plan["itinerary"]]


def test_a_two_day_trip_is_built_with_every_place_once_and_passes_validation():
    d, recs = trip()
    plan = build(d, recs)
    assert plan["ok"], plan["violations"]
    placed = [p for day in visits(plan) for p in day]
    assert sorted(placed) == sorted(r["id"] for r in recs) and len(plan["itinerary"]) == 2
    assert plan["uncertainty"]["travel_source"] == "osrm" and plan["unplaced"] == []


def test_the_two_clusters_land_on_different_days():
    d, recs = trip()
    day1, day2 = visits(build(d, recs))
    centre, south = {"c1", "c2", "c3", "c4", "r1"}, {"s1", "s2", "s3"}
    assert (set(day1) | set(day2)) == centre | south
    assert south <= set(day1) or south <= set(day2)


def test_the_same_input_gives_the_same_plan_and_the_plan_is_plain_json():
    d, recs = trip()
    first, second = build(d, recs), build(d, recs)
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_one_matrix_request_serves_the_whole_trip():
    d, recs = trip()
    calls = []

    def counting(points, mode, cfg):
        calls.append(len(points))
        return fake_matrix(points, mode, cfg)

    build(d, recs, matrix=counting)
    assert len(calls) == 1 and calls[0] >= len(recs)


def test_without_osrm_the_plan_is_built_from_rough_times_and_says_so():
    d, recs = trip()

    def dead(points, mode, cfg):
        raise Unavailable("osrm down")

    plan = build(d, recs, matrix=dead)
    assert plan["uncertainty"]["travel_source"] == "rough"
    assert "travel_rough" in {w["code"] for w in plan["warnings"]}
    assert plan["provenance"]["travel"] == {"source": "rough", "fetched_at": None}
    assert sorted(p for day in visits(plan) for p in day) == sorted(r["id"] for r in recs)


def test_a_place_that_cannot_be_scheduled_is_reported_and_an_unplaced_anchor_fails_the_plan():
    d, recs = trip(roles={"c1": "anchor"})
    d["confirmed"].append({"id": "ghost", "name": "Ghost", "role": "selected", "flags": [], "relaxed": []})
    plan = build(d, recs)
    assert plan["unplaced"] == [{"id": "ghost", "name": "Ghost", "reason": "no_record"}]
    assert plan["ok"]
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    failed = build(d, recs)
    assert not failed["ok"] and [v["kind"] for v in failed["violations"]] == ["anchor"]


def test_the_base_the_entry_and_the_exit_become_the_start_and_end_of_the_trip():
    d, recs = trip(base={"place_id": "c1", "text": "c1"}, entry={"place_id": None, "text": "Bến xe"},
                   exit={"place_id": None, "text": "Sân bay"})
    hit = lambda text: {"lat": 11.9404, "lng": 108.4583, "label": text, "source": "nominatim", "fetched_at": "t"}
    plan = build(d, recs, geocode=hit)
    first, last = plan["itinerary"][0]["items"][0], plan["itinerary"][-1]["items"][-1]
    assert first["kind"] == "travel" and first["from"] == "@entry"
    assert last["kind"] == "travel" and last["to"] == "@exit"
    assert plan["provenance"]["points"]["@entry"] == {"text": "Bến xe", "source": "nominatim", "fetched_at": "t"}
    assert "entry_exit_unknown" not in {w["code"] for w in plan["warnings"]}


def test_a_trip_without_dates_or_entry_points_says_what_it_could_not_check():
    d, recs = trip(start_date=None, days=None)
    codes = {w["code"] for w in build(d, recs)["warnings"]}
    assert {"days_assumed", "dates_unknown", "entry_exit_unknown", "base_unknown"} <= codes


def test_places_without_hours_are_flagged_not_assumed_open_silently():
    d, recs = trip()
    recs[0] = spot("c1", CENTRE, 0, hours=None)
    assert any(w["code"] == "hours_unknown" and "c1" in w["text"] for w in build(d, recs)["warnings"])


def test_a_hard_filter_the_confirmed_place_breaks_fails_the_plan_as_physical():
    d, recs = trip(hard=[{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}])
    recs[0] = spot("c1", CENTRE, 0, features={"steep_or_stairs": "present"})
    plan = build(d, recs)
    assert not plan["ok"]
    assert [(v["kind"], v["physical"], v["place_id"]) for v in plan["violations"]] == [("hard", True, "c1")]


def test_what_the_user_relaxed_and_what_could_not_be_placed_are_tradeoffs_and_the_log_is_kept():
    d, recs = trip(relaxed={"c1": ["long_walk"]}, log=["chose c1 over c9"])
    plan = build(d, recs)
    assert {"kind": "relaxed", "place_id": "c1", "features": ["long_walk"]} in plan["tradeoffs"]
    assert plan["reasons"] == ["chose c1 over c9"]


def test_decision_flags_reach_the_warnings():
    d, recs = trip(flags={"s1": ["giờ mở cửa chưa chắc"]})
    assert {"code": "flag", "text": "giờ mở cửa chưa chắc"} in build(d, recs)["warnings"]


def test_travel_load_adds_up_the_travel_items_of_each_day():
    d, recs = trip()
    plan = build(d, recs)
    for day, load in zip(plan["itinerary"], plan["travel_load"]):
        legs = [int(i["end"][:2]) * 60 + int(i["end"][3:]) - int(i["start"][:2]) * 60 - int(i["start"][3:])
                for i in day["items"] if i["kind"] == "travel"]
        assert load["travel_min"] == sum(legs) and load["longest_leg_min"] == max(legs, default=0)


def test_a_trip_with_no_places_is_an_empty_valid_plan():
    d, recs = trip()
    d["confirmed"] = []
    plan = build(d, recs)
    assert plan["ok"] and all(day["items"] == [] for day in plan["itinerary"])


def test_a_meal_window_the_day_opens_after_is_a_warning_in_vietnamese():
    d, recs = trip(days=1, arrive_at="14:00")
    d["confirmed"] = d["confirmed"][:2]
    texts = [w["text"] for w in build(d, recs)["warnings"] if w["code"] == "meal_missed"]
    assert "Ngày 1: quá khung giờ trưa, chưa xếp bữa." in texts


def test_the_text_rendering_lists_each_day_a_free_meal_and_the_verdict():
    d, recs = trip(base={"place_id": "c1", "text": "c1"})
    text = render_text(build(d, recs))
    assert "Ngày 1 (2026-12-12)" in text and "Ngày 2 (2026-12-13)" in text and text.endswith("Hợp lệ.")
    assert "ăn trưa (tự chọn)" in text
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_build.py -q`
Expected: FAIL ở bước import (`ImportError` / `ModuleNotFoundError` về `planning`)

- [ ] **Step 3: Viết code**

Tạo `src/planning/build.py`:

```python
"""Decision Output + serving records -> a checked itinerary (docs/specs/PLANNING_SPEC.md, phase P3).

One path, no randomness: places -> one travel matrix -> clusters -> days -> stop order -> clock -> validate.
This phase builds one plan around the user's base; variants, robustness, backups and lodging come later.
"""

from dataclasses import asdict

import live

from . import places as pl
from .cluster import cluster_places, split_to_fit
from .days import assign_days, load_of
from .frame import trip_days
from .model import Item
from .route import order_day
from .schedule import DayCtx
from .settings import Settings, fmt
from .settings import load as load_settings
from .travel import build_travel
from .validate import validate

HOME, ENTRY, EXIT = "@home", "@entry", "@exit"

WARNING_TEXT = {
    "days_assumed": "Chưa biết số ngày: tạm xếp {n} ngày.",
    "dates_unknown": "Chưa biết ngày đi: không kiểm giờ mở cửa theo thứ và không ghim giờ hoàng hôn / bình minh.",
    "entry_exit_unknown": "Chưa biết điểm vào / ra thành phố: ngày đầu và ngày cuối chỉ cắt theo giờ đến / giờ rời, kém chắc hơn.",
    "base_unknown": "Chưa biết nơi ở: mỗi ngày bắt đầu và kết thúc ở địa điểm đầu / cuối.",
    "travel_rough": "Thời gian di chuyển là ước lượng thô (không có OSRM), không dùng để kết luận độ vững.",
    "travel_pairs_rough": "{n} chặng không có đường trong OSRM, dùng ước lượng thô.",
    "days_fallback": "Quá nhiều ngày hoặc cụm để tìm chính xác: chia ngày theo cách tham lam.",
    "hours_unknown": "{name}: chưa có giờ mở cửa, không kiểm.",
    "meal_missed": "Ngày {day}: quá khung giờ {meal}, chưa xếp bữa.",
}


MEAL_NAME = {"lunch": "trưa", "dinner": "tối"}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _item(it: Item) -> dict:
    d = {"kind": it.kind, "start": fmt(it.start), "end": fmt(it.end), "place_id": it.place_id, "name": it.name,
         "from": it.from_id, "to": it.to_id, "mode": it.mode, "note": it.note}
    return {k: v for k, v in d.items() if v is not None}


def build_plan(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
               matrix_fn=None, sun_fn=None) -> dict:
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    geocode_fn = geocode_fn or (lambda text: live.geocode(text, live_cfg))
    matrix_fn = matrix_fn or live.travel_matrix
    sun_fn = sun_fn or live.sun_times
    by_id = {r["id"]: r for r in records}
    tc = decision["trip_context"]
    ctx, pace_spec = tc["context"], tc.get("pace") or {}
    pace = pace_spec.get("level") or "normal"
    mobility = ctx.get("mobility")
    warnings: list[dict] = []

    placed, unplaced = pl.build_places(decision, by_id, cfg)
    by_place = {p.id: p for p in placed}
    for p in placed:
        if p.hours is None:
            warnings.append(_warn("hours_unknown", name=p.name))

    points, why = {}, {}
    for node, base in ((HOME, ctx.get("base")), (ENTRY, ctx.get("entry_point")), (EXIT, ctx.get("exit_point"))):
        points[node], why[node] = pl.resolve_point(base, by_id, geocode_fn)
    home = HOME if points[HOME] else ENTRY if points[ENTRY] else None
    entry = ENTRY if points[ENTRY] else None
    exit_ = EXIT if points[EXIT] else None
    if home is None:
        warnings.append(_warn("base_unknown"))
    if entry is None or exit_ is None:
        warnings.append(_warn("entry_exit_unknown"))

    nodes = {p.id: (p.lat, p.lng) for p in placed}
    nodes.update({n: (pt.lat, pt.lng) for n, pt in points.items() if pt})
    travel = build_travel(nodes, mobility, cfg, live_cfg, matrix_fn)
    if travel.source == "rough":
        warnings.append(_warn("travel_rough"))
    elif travel.rough_pairs:
        warnings.append(_warn("travel_pairs_rough", n=travel.rough_pairs))

    days = trip_days(ctx, cfg, home, entry, exit_)
    if not ctx.get("days"):
        warnings.append(_warn("days_assumed", n=len(days)))
    if not (ctx.get("start_date") and ctx.get("days")):
        warnings.append(_warn("dates_unknown"))
    centre = (sum(p.lat for p in placed) / len(placed), sum(p.lng for p in placed) / len(placed)) if placed else None
    ctxs = [DayCtx(d, by_place, travel, cfg, pace,
                   sun_fn(d.date, *centre, live_cfg.tz_offset_h) if d.date and centre else None) for d in days]

    ids = sorted(by_place)
    cap = int(cfg.fill_ratio * max(d.end - d.start for d in days))
    clusters = cluster_places(ids, {p.id: p.area for p in placed}, travel, cfg)
    clusters = split_to_fit(clusters, lambda c: load_of(c, by_place, cfg, pace), cap, travel)
    per_day, flag = assign_days(clusters, ctxs)
    if flag:
        warnings.append(_warn(flag))
    results = [order_day(day_ids, cx) for day_ids, cx in zip(per_day, ctxs)]
    for cx, r in zip(ctxs, results):
        for note in r.notes:
            code, _, meal = note.partition(":")
            warnings.append(_warn(code, day=cx.day.index + 1, meal=MEAL_NAME.get(meal, meal)))

    anchors = {c["id"] for c in decision["confirmed"] if c.get("role") == "anchor"}
    violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, ctx.get("budget_vnd"),
                          pace_spec.get("max_leg_min"))
    return {
        "ok": not violations,
        "itinerary": [{"day": d.index + 1, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday,
                       "window": [fmt(d.start), fmt(d.end)], "method": r.method,
                       "items": [_item(i) for i in r.items]} for d, r in zip(days, results)],
        "travel_load": [{"day": d.index + 1, "travel_min": r.travel_min, "wait_min": r.wait_min,
                         "longest_leg_min": max((i.end - i.start for i in r.items if i.kind == "travel"), default=0)}
                        for d, r in zip(days, results)],
        "violations": [asdict(v) for v in violations],
        "warnings": warnings + [{"code": "flag", "text": f} for c in decision["confirmed"] for f in c.get("flags") or []],
        "unplaced": [asdict(u) for u in unplaced],
        "uncertainty": {"travel_source": travel.source, "rough_pairs": travel.rough_pairs,
                        "estimated": ["travel_minutes", "visit_minutes", "cost"]},
        "provenance": {"travel": {"source": travel.source, "fetched_at": travel.fetched_at},
                       "points": {n: {"text": pt.text, "source": pt.source, "fetched_at": pt.fetched_at}
                                  for n, pt in points.items() if pt}},
        "reasons": decision.get("decision_log") or [],
        "tradeoffs": [{"kind": "relaxed", "place_id": c["id"], "features": c["relaxed"]}
                      for c in decision["confirmed"] if c.get("relaxed")]
                     + [{"kind": "unplaced", "place_id": u.id, "reason": u.reason} for u in unplaced],
        "trip_context": tc,
    }


def render_text(plan: dict) -> str:
    """The itinerary as plain lines, for the command line."""
    names = {i["place_id"]: i["name"] for d in plan["itinerary"] for i in d["items"] if i["kind"] == "visit"}
    out = []
    for d in plan["itinerary"]:
        head = f'Ngày {d["day"]}' + (f' ({d["date"]})' if d["date"] else "") + f' · {d["window"][0]}-{d["window"][1]}'
        out.append(head)
        for i in d["items"]:
            span = f'  {i["start"]}-{i["end"]}  '
            if i["kind"] == "visit":
                out.append(span + i["name"])
            elif i["kind"] == "travel":
                out.append(span + f'di chuyển ({i["mode"]}) tới {names.get(i["to"], i["to"])}')
            elif i["kind"] == "meal_free":
                out.append(span + f'ăn {MEAL_NAME.get(i["name"], i["name"])} (tự chọn)')
            else:
                out.append(span + {"wait": "chờ mở cửa", "buffer": "đệm", "rest": "nghỉ"}[i["kind"]])
    for w in plan["warnings"]:
        out.append("! " + w["text"])
    for v in plan["violations"]:
        out.append(f'X {v["kind"]} ngày {(v["day"] + 1) if v["day"] is not None else "-"}: {v["detail"]}'
                   + (" (physical)" if v["physical"] else ""))
    out.append("Hợp lệ." if plan["ok"] else "KHÔNG hợp lệ.")
    return "\n".join(out)
```

Sửa `src/planning/__init__.py` thành:

```python
"""Planning & Validation: confirmed places -> a checked itinerary (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
"""

from .build import build_plan, render_text
from .settings import Settings
from .settings import load as load_settings

__all__ = ["Settings", "build_plan", "load_settings", "render_text"]
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_build.py -q`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/build.py src/planning/__init__.py tests/planning/test_planning_build.py
git commit -m "feat(planning): build a checked itinerary from a Decision Output"
```


### Task 11: Lệnh `python -m planning build`, ranh giới module, tài liệu

**Files:**
- Create: `src/planning/__main__.py`
- Modify: `docs/specs/PLANNING_SPEC.md`
- Modify: `README.md` (không commit)
- Test: `tests/planning/test_planning_cli.py`, `tests/planning/test_planning_boundaries.py`

**Interfaces:**
- Consumes: `planning.build_plan`, `planning.render_text`, `corpus.serving.load`.
- Produces:
  - `python -m planning build <decision_output.json> [--out plan.json]` — in lịch, mã thoát 0 khi hợp lệ, 2 khi không
  - `planning.__main__.main(argv=None) -> int`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_cli.py`:

```python
import json

import pytest
from plan_fixtures import decision, fake_matrix, fixed_sun, no_geocode, rec

import planning.build as build_module
import planning.__main__ as cli


@pytest.fixture
def offline(monkeypatch):
    """No OSRM, no Nominatim, no records file: the command line runs on what the test hands it."""
    monkeypatch.setattr(build_module.live, "travel_matrix", fake_matrix)
    monkeypatch.setattr(build_module.live, "geocode", lambda text, cfg: no_geocode(text))
    monkeypatch.setattr(build_module.live, "sun_times", fixed_sun)


def write_decision(tmp_path, ids, **kw):
    p = tmp_path / "decision.json"
    p.write_text(json.dumps(decision(ids, **kw), ensure_ascii=False), encoding="utf-8")
    return p


def test_build_prints_the_itinerary_and_exits_zero_when_the_plan_is_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["build", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "Ngày 1" in out and out.rstrip().endswith("Hợp lệ.")


def test_build_exits_two_and_names_the_violation_when_the_plan_is_not_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["build", str(path)]) == 2
    out = capsys.readouterr().out
    assert "X anchor" in out and out.rstrip().endswith("KHÔNG hợp lệ.")


def test_build_can_also_write_the_full_plan_output_as_json(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    out = tmp_path / "plan.json"
    assert cli.main(["build", str(write_decision(tmp_path, ["a"])), "--out", str(out)]) == 0
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["ok"] and {"itinerary", "travel_load", "warnings", "uncertainty", "provenance"} <= set(plan)
```

Tạo `tests/planning/test_planning_boundaries.py`:

```python
"""Planning reads other packages only through their public API and writes nothing of the corpus
(docs/specs/PLANNING_SPEC.md §Ranh giới module; RULE.md §2)."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "planning"
ALLOWED_CORPUS = {"corpus.serving", "corpus.ontology"}
WRITTEN_BY_CORPUS = ("data/intel", "data/serving", "data/gmaps", "data/tiktok", "data/review")


def modules():
    return sorted(SRC.rglob("*.py"))


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_there_is_something_to_check():
    assert len(modules()) >= 12


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_deep_import_into_live_or_corpus_and_none_into_decision_or_trip(path):
    for name in imports(path):
        top = name.split(".")[0]
        assert top not in {"decision", "trip"}, f"{path.name} imports {name}"
        assert top != "live" or name == "live", f"{path.name} deep-imports {name}"
        assert top != "corpus" or name in ALLOWED_CORPUS, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_directory_only_the_corpus_writes(path):
    text = path.read_text(encoding="utf-8")
    for bad in WRITTEN_BY_CORPUS:
        assert bad not in text, f"{path.name} names {bad}"


def test_the_public_api_is_the_plan_builder_and_its_settings():
    import planning
    assert set(planning.__all__) == {"Settings", "build_plan", "load_settings", "render_text"}
    for name in planning.__all__:
        assert hasattr(planning, name)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_cli.py -q`
Expected: FAIL ở bước import `planning.__main__` (`ModuleNotFoundError`). `test_planning_boundaries.py` chạy được ngay (26 test xanh, vì nó chỉ đọc các module đã có) và thêm 2 test cho `__main__.py` khi file này xuất hiện

- [ ] **Step 3: Viết code**

Tạo `src/planning/__main__.py`:

```python
"""python -m planning build <decision_output.json> [--out plan.json]"""

import argparse
import json
import sys
from pathlib import Path

from corpus.serving import load as load_records

from . import build_plan, render_text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="print the itinerary of a Decision Output")
    b.add_argument("decision_output", type=Path)
    b.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    decision = json.loads(args.decision_output.read_text(encoding="utf-8"))
    plan = build_plan(decision, load_records())
    if args.out:
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(render_text(plan))
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py -q`
Expected: PASS (31 tests)

- [ ] **Step 5: Chạy toàn bộ test của repo**

Run: `python -m pytest -q`
Expected: PASS — không test cũ nào đỏ; thêm test của `tests/planning`

- [ ] **Step 6: Thử tay trên dữ liệu thật (không bắt buộc, không commit gì)**

Cần `data/serving/places.json`. Lấy vài id thật rồi ghi một Decision Output tối thiểu:

```bash
python - <<'EOF'
import json, random
recs = json.load(open('data/serving/places.json', encoding='utf-8'))['records']
random.seed(1)
base = [r for r in recs if r['identity']['area'] == 'area-1' and 'experience' in r['usable_as'] and r['identity']['lat']]
ids = [r['id'] for r in random.sample(base, 6)]
ctx = {'start_date': '2026-12-12', 'month': None, 'days': 2, 'base': None, 'entry_point': None, 'exit_point': None, 'mobility': 'motorbike', 'companions': [], 'people': 2, 'arrive_at': None, 'leave_at': None, 'day_end': None, 'budget_vnd': None}
doc = {'confirmed': [{'id': i, 'name': i, 'role': 'selected', 'flags': [], 'relaxed': []} for i in ids], 'decision_log': [], 'trip_context': {'context': ctx, 'hard_filters': [], 'anchors': [], 'soft_weights': [], 'pace': {'level': 'normal', 'max_leg_min': None, 'crowd_tolerance': None}, 'novelty': {'level': None, 'visited': []}, 'unknowns': [], 'unmapped': []}}
json.dump(doc, open('decision_output.json', 'w', encoding='utf-8'), ensure_ascii=False)
EOF
python -m planning build decision_output.json
```

Expected: in `Ngày 1`, `Ngày 2` với giờ, chặng, đệm; cuối dòng `Hợp lệ.` (mã thoát 0) hoặc `KHÔNG hợp lệ.` kèm các dòng `X ...` (mã thoát 2). OSRM chưa chạy thì có dòng `! Thời gian di chuyển là ước lượng thô ...`. Xoá `decision_output.json` sau khi xem.

- [ ] **Step 7: Sửa `docs/specs/PLANNING_SPEC.md` cho khớp code**

Năm chỗ, dùng Edit; mỗi chuỗi cũ xuất hiện đúng một lần trong file:

1. Bảng Live Context, dòng `osrm/`, cột Public API:

```text
cũ:  travel_matrix(points, mode, depart_at)
mới: travel_matrix(points, mode)
```

2. Cùng dòng, cột "Khi lỗi":

```text
cũ:  rơi về ước lượng thô của `decision/geo.py`
mới: rơi về ước lượng thô của Planning (`travel.rough_minutes`: đường chim bay × `road_factor` ÷ `rough_speed_kmh`)
```

3. Mục OSRM, đoạn "Mode:":

```text
cũ:  nhân `mode_factor` (`config/planning.yaml`: `car 1.0`, `motorbike 0.95`)
mới: nhân `mode_factor` (`config/live.yaml`: `car 1.0`, `motorbike 0.95`)
```

4. ⓒ Thứ tự trong ngày, dòng "Buổi:":

```text
cũ:  `timed_features` (dùng lại của `decision`) + `sun_times`
mới: `pins` (`config/planning.yaml`: `sunset_view`, `cloud_hunting`, `live_music`) + `sun_times`
```

5. Mục "Cấu hình — `config/planning.yaml`": thay đoạn liệt kê khoá (từ `version`; `mode_factor`; ... tới hết `trọng số phạt của repair_day.`) bằng:

```markdown
`version`; `road_factor`, `rough_speed_kmh` (đường lui khi OSRM chết), `walk_km`, `walk_kmh`; `default_days`, `day_start`, `day_end`, `leave_at`; `visit_key`, `per_day`, `buffer_min` (+ phụ phí `long_leg_min`, `buffer_extra_long`, `buffer_extra_uncertain`), `rest_min`, `max_consecutive_min`; `meals_per_day`, `meal_min`, `meal_windows`; `pins`; `cluster_max_min`, `cluster_merge_min`, `fill_ratio`, `intra_leg_min`, `max_days`, `max_clusters`, `exact_n`, `improve_passes`; `weights` (`travel`, `overflow`, `count`, `closed`). Các phase sau thêm: `radius_km` theo mobility, `lodging_k`, `lodging_share`, `min_reviews`, `split_min`, kịch bản nhiễu của độ vững + ngưỡng 3 mức, trọng số từng mục tiêu, trọng số phạt của `repair_day`.
```

Giữ nguyên câu ngay dưới đoạn đó về `config/live.yaml`.

- [ ] **Step 8: Thêm lệnh vào `README.md`**

Trong mục "Thiết lập", thêm một mục đánh số tiếp theo mục cuối:

```markdown
Lập lịch trình từ Decision Output: `python -m planning build <decision_output.json>` (thêm `--out plan.json` để ghi Plan Output; mã thoát 2 khi lịch không hợp lệ). Cần `data/serving/places.json`; có OSRM (`scripts/osrm_setup.sh`) thì dùng thời gian thật, không có thì dùng ước lượng thô và gắn cảnh báo (`docs/specs/PLANNING_SPEC.md`).
```

`README.md` có thể đang mang thay đổi chưa commit của người dùng: sửa working copy nhưng **không** `git add` file này trong plan này, và ghi vào báo cáo cuối rằng mục README chưa commit.

- [ ] **Step 9: Commit**

```bash
git add src/planning/__main__.py docs/specs/PLANNING_SPEC.md tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py
git commit -m "feat(planning): python -m planning build and the tests that pin its boundaries"
```


---

## Sau khi plan này xong

`python -m planning build` cho ra lịch thật từ một Decision Output: có thứ tự, giờ, chặng, đệm, nghỉ, bữa ăn, cảnh báo, và `validate` đã kết luận. Còn lại theo `PLANNING_SPEC.md` §Các phase:

- P4: `robustness`, `backup`, `objectives`, `variants`. Lúc đó `route.order_day` cần cắt tỉa (5040 hoán vị × 21 lần dựng vượt ngân sách 2 s); hiện một ngày 7 nơi mất khoảng 0,3 s.
- P5: `live/weather`, `live/lodging`, `lodging.py`; chấm K chỗ ở × mục tiêu.
- Sửa `docs/ARCHITECTURE.md` §9.1, §18.2 và `docs/PLACE_DECISION.md` §5 (bảng "Tài liệu phải sửa" của spec) cùng phase đưa chỗ ở vào; chưa thuộc P3.
