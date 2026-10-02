# Plan P4 — Phương án, độ vững, dự phòng

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ một Decision Output dựng 2–3 phương án lịch trình đã kiểm, mỗi phương án tốt nhất theo một mục tiêu (`least_travel`, `weather_robust`, `preference_fit`, `low_cost`, `diverse`), mỗi phương án kèm độ vững 3 mức và dự phòng cho từng nơi nhạy cảm; lệnh `python -m planning variants <decision_output.json> [--weather forecast.json]`.

**Architecture:** `build.prepare()` làm một lần phần mọi phương án dùng chung (địa điểm, điểm vào / ra / ở, một ma trận thời gian, các ngày, mưa và mức "được muốn" của từng nơi); `build.schedule_trip(trip, weights)` chia ngày theo trọng số của một mục tiêu rồi xếp thứ tự (thứ tự một ngày được cache theo `(ngày, tập nơi)` vì nó không phụ thuộc trọng số) và `validate`. `variants.build_variants` chọn mục tiêu theo rule, bỏ phương án không hợp lệ, gộp phương án trùng, đo, chấm `robustness` (nhiễu cố định trong config) và `backups` (chỉ lấy từ `backup_pool`). Thời tiết là **input** (`weather`), P5 mới tự lấy qua `live.weather`. Không random, không gọi model.

**Tech Stack:** Python 3.12, stdlib, `pyyaml`, `pytest`. Không thêm dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Thuật toán ⓕ ⓖ ⓗ, §Plan Output, bảng phase P4). Plan trước: `docs/plans/PLANNING_P3_CORE.md` — **phải xong cả 11 task trước khi bắt đầu plan này** (plan này sửa `build.py`, `test_planning_cli.py`, `test_planning_boundaries.py` do P3 tạo). Đọc thêm `docs/ARCHITECTURE.md` §10 (mục tiêu), §12 (độ vững), §13 (dự phòng).

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0). Chuỗi hiển thị cho người dùng (cảnh báo, nhãn, lý do) tiếng Việt.
- Module chỉ giao tiếp qua public API (`__init__.py`). `planning` dùng: `live`, `corpus.serving` (`feature`, `check`, `load`), `corpus.ontology` (`load`). Không deep import; không import `decision`, `trip` (`RULE.md` §2). `tests/planning/test_planning_boundaries.py` ép điều này cho mọi file mới.
- `src/planning` không ghi gì dưới `data/`. Lệnh `--out` ghi đúng file người dùng chỉ định.
- Mọi bước tất định: không `random`, không đọc đồng hồ (`PLANNING_SPEC.md` §Nguyên tắc 3). Nhiễu của độ vững là danh sách cố định trong config.
- Không bịa (`RULE.md` §3): không có bằng chứng thời tiết → không coi là phơi mưa; không có dự báo → không xét mưa và gắn cờ; không có phương án thay → nói "Không có phương án thay.", không thêm địa điểm ngoài `backup_pool`.
- Physical constraint không nới: không mục tiêu nào đổi điều `validate` kiểm; phương án `validate` từ chối bị bỏ và được nêu tên.
- Không thêm dependency vào `pyproject.toml`. Thay đổi tối thiểu trong file của P3 (`RULE.md` §4): chỉ đúng các chỗ ghi trong task. `decision`, `trip`, `live` không đổi.
- File test mới dưới `tests/planning/` có tiền tố `test_planning_`; không tạo `tests/planning/__init__.py`.
- Chạy test: `python -m pytest -q` ở gốc repo.
- Giờ trong code là số phút sau nửa đêm; xác suất mưa là số 0..1.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| Thời tiết lấy từ `live.weather` (Open-Meteo / `climate.yaml`) | `prepare(..., weather=None)` và `--weather forecast.json` nhận `{"YYYY-MM-DD": {"rain_prob", "source", "fetched_at"}}` | `live/weather` thuộc P5 (bảng phase). P4 dùng được thời tiết ngay mà không chờ nguồn live; P5 chỉ việc đổ kết quả `live.weather` vào tham số này. |
| Kịch bản "mưa theo xác suất dự báo" | Nơi phơi mưa ở ngày `rain_prob ≥ rain_high` được tính là mất | Không random (Nguyên tắc 3): ngưỡng thay cho xác suất. |
| Chọn mục tiêu theo "tháng mưa?" | Theo dự báo đưa vào: có ngày `≥ rain_high` thì chọn `weather_robust` | Khí hậu theo tháng là `config/climate.yaml` của P5. |
| `low_cost` | Điểm = tổng chi phí vé / đồ uống đã biết, hoà thì ít di chuyển hơn | Tiền phòng đến ở P5. Với tập nơi cố định, `low_cost` thường ra đúng lịch `least_travel` và bị gộp (cảnh báo `variants_same`). |
| `preference_fit` | Đặt nơi khớp `soft_weights` nhiều nhất vào ngày ít rủi ro (không mưa, đủ dài — không phải ngày đến / ngày đi) | Tập nơi do Place Decision chốt; Planning chỉ đổi được ngày và giờ. Context của soft weight bị bỏ qua (Planning không biết context của từng lượt). |
| `diverse` | Phạt hai nơi cùng `category_group` trong một ngày | Đa dạng *trong ngày*; tập nơi đã đa dạng nhờ MMR của Place Decision. |
| Dự phòng "cùng cụm" | Phút thô (`travel.rough_minutes`) ≤ `backup_radius_min` | Ứng viên `backup_pool` không nằm trong ma trận OSRM (spec: ma trận = confirmed + chỗ ở + vào / ra). |
| "Bị trễ → bỏ điểm có ưu tiên thấp nhất" (`ARCHITECTURE.md` §13) | `backups.on_delay`: mỗi ngày nêu nơi `selected` có mức "được muốn" thấp nhất (hoà: xa điểm xuất phát hơn) | Decision Output không mang điểm xếp hạng; anchor / `locked` không bao giờ bị đề nghị bỏ. |
| Plan P3 ghi "P4: `route.order_day` cần cắt tỉa" | Không cắt tỉa; cache thứ tự theo `(ngày, tập nơi)` dùng chung giữa các mục tiêu | Đã thử branch-and-bound (cận = vi phạm giờ của tiền tố + giờ kết thúc tối thiểu): 7 nơi vẫn chạy 4993 / 5040 lần `simulate`, thêm cận di chuyển còn tệ hơn (11570) — các thứ tự kết thúc sát nhau vì bữa trưa tự do và nghỉ. Đo trong scratch: 14 nơi, 3 mục tiêu, 2 ngày → 0,9 s. P5 (×7 chỗ ở) đo lại. |
| `chosen` trong Plan Output | Luôn `null` ở P4 | Người dùng chọn qua `pick_variant` ở P6. |

## Review Focus

Năm lớp input spec hàm ý nhưng dễ bị bỏ; mỗi dòng đã có test ở task sở hữu code:

1. **Các mục tiêu cho cùng một lịch, hoặc một mục tiêu không xếp nổi** — mong đợi: còn 1 phương án là 1, không giả vờ có 3; phương án trùng → cảnh báo `variants_same`, phương án hỏng → `variant_invalid` nêu tên mục tiêu, hai thứ không lẫn nhau. → Task 8 (`test_a_plain_trip_whose_objectives_agree...`, `test_a_variant_that_does_not_fit_the_days...`).
2. **Dự báo thiếu ngày, `rain_prob = null`, ngày ngoài chuyến, chuyến không có ngày đi** — mong đợi: ngày đó `rain = None`, không crash, không đoán. → Task 4 (`test_each_day_gets_the_rain_of_its_date...`, `test_without_dates_or_a_forecast...`).
3. **`backup_pool` bẩn**: id không có record, record không toạ độ, id đã nằm trong `confirmed`, `for = null` — mong đợi: bỏ qua lặng lẽ, nơi nhạy cảm vẫn được liệt kê với "Không có phương án thay.". → Task 7 (`test_replacements_that_are_far_shaky_closed...`).
4. **Chuyến rỗng hoặc một nút** — ma trận 1 nút mang nhãn `rough` (P3 không gọi OSRM khi < 2 điểm). Mong đợi: không có chặng nào thì không bị trần "Khả thi"; chuyến rỗng là một phương án rỗng, Vững, không dự phòng. → Task 6 (`test_a_plan_that_never_travels...`), Task 8 (`test_a_trip_with_no_places...`).
5. **Không phương án nào hợp lệ** (anchor không xếp được) — mong đợi: `ok = false`, `back_to_decision` kèm nơi gây lỗi, không chấm độ vững / dự phòng cho lịch hỏng. → Task 8 (`test_no_valid_variant_goes_back...`), Task 9 (`test_variants_exits_two...`).

## Cấu trúc file

| File | Việc |
|---|---|
| `config/planning.yaml` | thêm: mưa, kịch bản độ vững + ngưỡng, mục tiêu + trọng số, ngưỡng dự phòng |
| `src/planning/settings.py` | thêm trường cho các khoá mới |
| `src/planning/schedule.py` | `DayCtx` thêm `rain`, `prefs`; ngày mưa đệm dài hơn |
| `src/planning/traits.py` | mới: `exposure`, `preference`, `kind_group` đọc từ serving record |
| `src/planning/days.py` | `day_cost` thêm `exposed`, `repeat`, `pref_risk` (trọng số mặc định 0) |
| `src/planning/build.py` | tách `prepare` / `schedule_trip` / `itinerary` / `travel_load` / `shared_output`; `build_plan` giữ nguyên đầu ra |
| `src/planning/objectives.py` | mới: `choose`, `metrics`, `score`, `LABEL` |
| `src/planning/robustness.py` | mới: độ vững 3 mức |
| `src/planning/backup.py` | mới: nơi nhạy cảm, phương án thay, `on_delay` |
| `src/planning/variants.py` | mới: `build_variants`, `render_variants` |
| `src/planning/__init__.py`, `__main__.py` | export + lệnh `variants` |
| `tests/planning/plan_fixtures.py` | `rec` đủ nhóm feature + `group`; `day_ctx` nhận `rain`, `prefs`; `sample_trip`, `prepared` |
| `tests/planning/golden/variants_wet_south.json` | golden, sinh ở Task 9 |

---

### Task 1: Config, settings, ngày mưa trong đồng hồ một ngày

**Files:**
- Modify: `config/planning.yaml` (thêm vào cuối)
- Modify: `src/planning/settings.py` (class `Settings`)
- Modify: `src/planning/schedule.py` (`DayCtx`, khối tính `buffer` trong `simulate`)
- Modify: `tests/planning/plan_fixtures.py` (`rec`, `day_ctx`)
- Test: `tests/planning/test_planning_settings.py`, `tests/planning/test_planning_schedule.py`

**Interfaces:**
- Consumes: `planning.settings.Settings/load`, `planning.schedule.DayCtx/simulate` (P3).
- Produces:
  - `Settings` thêm `rain_high: float`, `buffer_extra_rain: int`, `robustness: dict` (`scenarios`: list `{id, tier, start_min | visit_pct | travel_pct | rain}`, `solid_max_lost`, `feasible_max_lost`), `max_variants: int`, `objective_order: list`, `objective_weights: dict`, `near_close_min`, `far_leg_min`, `backup_radius_min`, `backups_per_place: int`
  - `DayCtx(day, places, travel, cfg, pace, sun, rain=None, prefs=None)` — `rain`: xác suất mưa của ngày hoặc `None`; `prefs`: `place id -> float`
  - `plan_fixtures.rec(..., group="x")` (→ `identity.category_group`), feature nhóm `environment` / `service` / `suitability` giờ được giữ lại; `plan_fixtures.day_ctx(..., rain=None, prefs=None)`

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_settings.py`:

```python


def test_the_p4_keys_load():
    cfg = settings.load(settings.PATH)
    assert (cfg.rain_high, cfg.buffer_extra_rain, cfg.max_variants) == (0.6, 10, 3)
    assert [s["id"] for s in cfg.robustness["scenarios"]] == ["late_15", "visit_20", "travel_25", "late_30", "rain"]
    assert set(cfg.objective_weights) == set(cfg.objective_order)
```

Thêm vào cuối `tests/planning/test_planning_schedule.py`:

```python


def test_a_rainy_day_gets_a_longer_buffer_and_a_missing_forecast_changes_nothing():
    def size(rain):
        r = simulate(["a", "b"], day_ctx([rec("a", 1, 1), rec("b", 1, 1)], rain=rain))
        return next(i.end - i.start for i in r.items if i.kind == "buffer")

    assert (size(0.8), size(0.6), size(0.3), size(None)) == (30, 30, 20, 20)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_settings.py tests/planning/test_planning_schedule.py -q`
Expected: FAIL — `test_the_p4_keys_load` với `AttributeError: 'Settings' object has no attribute 'rain_high'`; test ngày mưa với `TypeError: day_ctx() got an unexpected keyword argument 'rain'`

- [ ] **Step 3: Thêm config**

Thêm vào cuối `config/planning.yaml`:

```yaml

# Weather. P4 takes a forecast as input; P5 fetches it (live.weather). A day whose rain probability is at or above
# rain_high is a rainy day: its buffers grow, and its weather-exposed places are lost in the rain scenario.
rain_high: 0.6
buffer_extra_rain: 10

# Robustness (docs/specs/PLANNING_SPEC.md ⓕ): fixed perturbations, never random. Each scenario re-runs the order of
# every day and counts the places that no longer fit. tier small = the few small delays a solid plan must absorb.
robustness:
  scenarios:
    - {id: late_15, tier: small, start_min: 15}
    - {id: visit_20, tier: small, visit_pct: 20}
    - {id: travel_25, tier: small, travel_pct: 25}
    - {id: late_30, tier: large, start_min: 30}
    - {id: rain, tier: large, rain: true}
  solid_max_lost: 0         # every scenario loses at most this many places -> solid
  feasible_max_lost: 0      # every small scenario loses at most this many -> feasible; otherwise fragile

# Objectives (docs/ARCHITECTURE.md §10): tried in this order when the trip calls for them, at most max_variants.
max_variants: 3
objective_order: [least_travel, weather_robust, preference_fit, low_cost, diverse]
objective_weights:          # merged over `weights` when the days are split for that objective
  least_travel: {travel: 2.0}
  low_cost: {}
  weather_robust: {exposed: 400.0}
  diverse: {repeat: 40.0}
  preference_fit: {pref_risk: 200.0}

# Backups (ⓗ): which visits are sensitive, and how far a replacement may be.
near_close_min: 30          # a visit that ends this close to closing time
far_leg_min: 40             # a place this far from where its day starts
backup_radius_min: 25       # rough minutes from the sensitive place to a replacement
backups_per_place: 2
```

- [ ] **Step 4: Viết code**

Trong `src/planning/settings.py`, class `Settings`, ngay sau dòng `    weights: dict` thêm:

```python
    rain_high: float
    buffer_extra_rain: int
    robustness: dict
    max_variants: int
    objective_order: list
    objective_weights: dict
    near_close_min: int
    far_leg_min: int
    backup_radius_min: int
    backups_per_place: int
```

Trong `src/planning/schedule.py`, class `DayCtx`, ngay sau dòng `sun: ...` thêm:

```python
    rain: float | None = None       # rain probability of the day; None = no forecast, rain is not considered
    prefs: dict | None = None       # place id -> how much the trip's soft weights want it (traits.preference)
```

Cũng trong `simulate`, sửa:

```python
            if p.hours_status in ("UNCERTAIN", "OUTDATED"):
                buffer += cfg.buffer_extra_uncertain
```

thành:

```python
            if p.hours_status in ("UNCERTAIN", "OUTDATED"):
                buffer += cfg.buffer_extra_uncertain
            if ctx.rain is not None and ctx.rain >= cfg.rain_high:
                buffer += cfg.buffer_extra_rain
```

Trong `tests/planning/plan_fixtures.py`, bốn chỗ (dùng Edit, mỗi chuỗi cũ xuất hiện một lần):

1. chữ ký `rec`: `features=None, price=None, dup=None, name=None, status="VERIFIED"):` → `features=None, price=None, dup=None, name=None, status="VERIFIED", group="x"):`
2. trong `rec`: `"category": "x", "category_group": "x",` → `"category": "x", "category_group": group,`
3. trong `rec`, thay

```python
            "experience": groups.get("experience", {}), "environment": {}, "service": {},
            "effort": groups.get("effort", {}), "suitability": {}, "usable_as": list(usable),
```

bằng

```python
            "experience": groups.get("experience", {}), "environment": groups.get("environment", {}),
            "service": groups.get("service", {}), "effort": groups.get("effort", {}),
            "suitability": groups.get("suitability", {}), "usable_as": list(usable),
```

4. `day_ctx`: chữ ký `sun=None, roles=None, travel=None, hard=(), extra_nodes=()):` → `sun=None, roles=None, travel=None, hard=(), extra_nodes=(), rain=None, prefs=None):`, và dòng return thành:

```python
    return DayCtx(day, by_id, travel or flat_travel([*by_id, *extra_nodes], minutes), CFG, pace, sun, rain, prefs)
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning -q`
Expected: PASS — toàn bộ test của P3 vẫn xanh, thêm 2 test mới

- [ ] **Step 6: Commit**

```bash
git add config/planning.yaml src/planning/settings.py src/planning/schedule.py tests/planning/plan_fixtures.py tests/planning/test_planning_settings.py tests/planning/test_planning_schedule.py
git commit -m "feat(planning): P4 settings and a rainy day's longer buffer"
```


### Task 2: Đặc điểm của một nơi — `traits.py`

**Files:**
- Create: `src/planning/traits.py`
- Test: `tests/planning/test_planning_traits.py`

**Interfaces:**
- Consumes: `corpus.serving.feature`, `planning.model.Place`.
- Produces:
  - `planning.traits.exposure(place) -> "exposed" | "sheltered" | None`
  - `planning.traits.preference(place, soft_weights: list[dict]) -> float` (`soft_weights` dạng `{"feature", "value", "context", "weight"}` của Search Input)
  - `planning.traits.kind_group(place) -> str | None`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_traits.py`:

```python
from plan_fixtures import CFG, decision, rec

from planning.places import build_places
from planning.traits import exposure, kind_group, preference


def place(r):
    (p,), _ = build_places(decision([r["id"]]), {r["id"]: r}, CFG)
    return p


def test_weather_exposed_decides_exposure_and_setting_fills_in_when_it_is_missing():
    assert exposure(place(rec("a", 1, 1, features={"weather_exposed": "present"}))) == "exposed"
    shelter = rec("b", 1, 1, features={"weather_exposed": "sheltered", "setting": "outdoor"})
    assert exposure(place(shelter)) == "sheltered"
    assert exposure(place(rec("c", 1, 1, features={"setting": "outdoor"}))) == "exposed"
    assert exposure(place(rec("d", 1, 1, features={"setting": "indoor"}))) == "sheltered"


def test_a_place_with_no_weather_evidence_is_not_guessed():
    assert exposure(place(rec("a", 1, 1))) is None
    assert exposure(place(rec("b", 1, 1, features={"setting": "both"}))) is None


def test_preference_adds_the_positive_weights_the_place_matches():
    p = place(rec("a", 1, 1, features={"scenic_view": "present", "photo_spot": "present"}))
    ws = [{"feature": "scenic_view", "value": "present", "context": None, "weight": 1.0},
          {"feature": "photo_spot", "value": "present", "context": None, "weight": 0.5},
          {"feature": "nature", "value": "present", "context": None, "weight": 0.8},          # no evidence: 0
          {"feature": "photo_spot", "value": "present", "context": None, "weight": -1.0}]     # avoidance is not a want
    assert preference(p, ws) == 1.5
    assert preference(p, []) == 0.0


def test_kind_group_is_the_category_group():
    assert kind_group(place(rec("a", 1, 1, group="cafe"))) == "cafe"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_traits.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.traits'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/traits.py`:

```python
"""Facts about a place that objectives, robustness and backups share, read from its serving record.

No evidence -> None or 0, never a guess: a place with no weather evidence is not counted as exposed.
"""

from corpus.serving import feature

from .model import Place


def _value(place: Place, fid: str) -> str | None:
    f = feature(place.rec, fid)
    return f["value"] if f else None


def exposure(place: Place) -> str | None:
    """exposed | sheltered | None. weather_exposed decides; without it, setting outdoor / indoor does."""
    w = _value(place, "weather_exposed")
    if w == "present":
        return "exposed"
    if w == "sheltered":
        return "sheltered"
    s = _value(place, "setting")
    return "exposed" if s == "outdoor" else "sheltered" if s == "indoor" else None


def preference(place: Place, soft_weights: list) -> float:
    """Sum of the positive soft weights whose feature value the place has. Context of a weight is ignored: Planning
    does not know it per visit."""
    return float(sum(w["weight"] for w in soft_weights
                     if w.get("weight", 0) > 0 and _value(place, w["feature"]) == w["value"]))


def kind_group(place: Place) -> str | None:
    """The category group: what "the same kind of experience" means for diversity and for a backup."""
    return place.rec["identity"].get("category_group")
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_traits.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/traits.py tests/planning/test_planning_traits.py
git commit -m "feat(planning): weather exposure, preference and kind of a place"
```


### Task 3: Chia ngày theo mục tiêu — `days.py`

**Files:**
- Modify: `src/planning/days.py` (import, `day_cost`, thêm 4 hàm sau `day_cost`)
- Test: `tests/planning/test_planning_days.py`

**Interfaces:**
- Consumes: `planning.traits.exposure/kind_group`, `DayCtx.rain/prefs` (Task 1).
- Produces:
  - `day_cost` cộng thêm `w.get("exposed", 0) * exposed_risk + w.get("repeat", 0) * repeats + w.get("pref_risk", 0) * pref_risk` — không có trọng số đó trong `weights` thì bằng 0, nên P3 không đổi
  - `planning.days.day_risk(ctx) -> float`, `exposed_risk(ids, ctx) -> float`, `repeats(ids, ctx) -> int`, `pref_risk(ids, ctx) -> float`

- [ ] **Step 1: Viết test**

Trong `tests/planning/test_planning_days.py`, thay khối import đầu file:

```python
from plan_fixtures import CFG, all_days, day_ctx, line_travel, rec

from planning.days import assign_days, blocked, day_cost, load_of
```

bằng:

```python
import pytest
from plan_fixtures import CFG, all_days, day_ctx, line_travel, rec

from planning.days import (assign_days, blocked, day_cost, day_risk, exposed_risk, load_of, pref_risk,
                           repeats)
```

Thêm vào cuối file:

```python


def weighted(cx, **extra):
    """The same DayCtx with objective weights merged over the defaults."""
    from dataclasses import replace
    return replace(cx, cfg=replace(cx.cfg, weights={**cx.cfg.weights, **extra}))


def test_without_objective_weights_the_new_terms_cost_nothing():
    wet = rec("w", 1, 1, features={"weather_exposed": "present"}, group="park")
    cx = day_ctx([wet, rec("p", 1, 1, group="park")], rain=0.9, prefs={"w": 2.0})
    dry = day_ctx([wet, rec("p", 1, 1, group="park")])
    assert day_cost(["w", "p"], cx) == day_cost(["w", "p"], dry)


def test_exposed_places_on_a_rainy_day_cost_more_under_the_weather_objective():
    wet = rec("w", 1, 1, features={"weather_exposed": "present"})
    rainy, dry, unknown = (weighted(day_ctx([wet], rain=r), exposed=400.0) for r in (0.8, 0.1, None))
    assert exposed_risk(["w"], rainy) == 0.8 and exposed_risk(["w"], unknown) == 0.0
    assert day_cost(["w"], rainy) - day_cost(["w"], dry) == pytest.approx(400.0 * 0.7)


def test_two_places_of_one_kind_on_a_day_repeat_and_unknown_kinds_do_not():
    cx = day_ctx([rec("a", 1, 1, group="cafe"), rec("b", 1, 1, group="cafe"), rec("c", 1, 1, group="park"),
                  rec("u", 1, 1, group=None), rec("v", 1, 1, group=None)])
    assert repeats(["a", "b", "c"], cx) == 1 and repeats(["a", "c"], cx) == 0 and repeats(["u", "v"], cx) == 0
    assert day_cost(["a", "b"], weighted(cx, repeat=40.0)) - day_cost(["a", "b"], cx) == 40.0


def test_a_wanted_place_costs_more_on_a_short_or_rainy_day():
    recs = [rec("a", 1, 1)]
    full = day_ctx(recs, prefs={"a": 1.0})
    short = day_ctx(recs, prefs={"a": 1.0}, end=870)                        # 08:00-14:30: half of 08:00-21:00
    rainy = day_ctx(recs, prefs={"a": 1.0}, rain=0.5)
    assert day_risk(full) == 0.0 and day_risk(short) == 0.5 and day_risk(rainy) == 0.5
    assert pref_risk(["a"], short) == 0.5 and pref_risk(["a"], day_ctx(recs)) == 0.0
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_days.py -q`
Expected: FAIL với `ImportError: cannot import name 'day_risk' from 'planning.days'`

- [ ] **Step 3: Viết code**

Trong `src/planning/days.py`, sau `from .schedule import DayCtx` thêm:

```python
from .traits import exposure, kind_group
```

Thay hai dòng cuối của `day_cost`:

```python
    over = max(0, load_of(ids, ctx.places, cfg, ctx.pace) + tour - (ctx.day.end - ctx.day.start))
    return w["travel"] * tour + w["overflow"] * over + w["count"] * abs(len(ids) - target) + w["closed"] * closed
```

bằng:

```python
    over = max(0, load_of(ids, ctx.places, cfg, ctx.pace) + tour - (ctx.day.end - ctx.day.start))
    return (w["travel"] * tour + w["overflow"] * over + w["count"] * abs(len(ids) - target) + w["closed"] * closed
            + w.get("exposed", 0) * exposed_risk(ids, ctx) + w.get("repeat", 0) * repeats(ids, ctx)
            + w.get("pref_risk", 0) * pref_risk(ids, ctx))


def day_risk(ctx: DayCtx) -> float:
    """How likely the day is to go wrong for a place on it: its rain probability (0 when unknown) plus how much
    shorter than a full day it is (an arrival or departure day)."""
    full = ctx.cfg.day_end - ctx.cfg.day_start
    short = max(0.0, 1 - (ctx.day.end - ctx.day.start) / full) if full > 0 else 0.0
    return (ctx.rain or 0.0) + short


def exposed_risk(ids: list[str], ctx: DayCtx) -> float:
    """Weather-exposed places on the day, times its rain probability. No forecast -> 0."""
    return sum(exposure(ctx.places[i]) == "exposed" for i in ids) * (ctx.rain or 0.0)


def repeats(ids: list[str], ctx: DayCtx) -> int:
    """Places of a kind already on the day: 0 when every place is a different kind. Unknown kinds do not repeat."""
    kinds = [kind_group(ctx.places[i]) for i in ids]
    known = [k for k in kinds if k]
    return len(known) - len(set(known))


def pref_risk(ids: list[str], ctx: DayCtx) -> float:
    """How much of what the user wants most sits on a risky day."""
    prefs = ctx.prefs or {}
    return sum(prefs.get(i, 0.0) for i in ids) * day_risk(ctx)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_days.py -q`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/days.py tests/planning/test_planning_days.py
git commit -m "feat(planning): day split terms for rain exposure, repeated kinds and wanted places"
```


### Task 4: Tách phần dùng chung của chuyến — `build.prepare` / `schedule_trip`

**Files:**
- Modify: `src/planning/build.py` (docstring, import, thay `build_plan`)
- Modify: `tests/planning/plan_fixtures.py` (thêm vào cuối)
- Test: `tests/planning/test_planning_prepare.py`; `tests/planning/test_planning_build.py` (không sửa, phải vẫn xanh)

**Interfaces:**
- Consumes: Task 1–3; mọi thứ `build.py` của P3 đã dùng.
- Produces:
  - `planning.build.Trip` (`decision`, `cfg`, `pace`, `by_place`, `unplaced`, `by_id`, `points`, `travel`, `days`, `ctxs`, `warnings`, `weather`, `routes`)
  - `planning.build.Schedule` (`per_day`, `results`, `ctxs`, `violations`, `warnings`)
  - `planning.build.prepare(decision, records, cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None, weather=None) -> Trip` — `weather`: `{"YYYY-MM-DD": {"rain_prob": 0..1 | None, "source", "fetched_at"}}`
  - `planning.build.schedule_trip(trip, weights: dict | None = None) -> Schedule`
  - `planning.build.itinerary(days, results) -> list[dict]`, `travel_load(days, results) -> list[dict]`, `flag_warnings(decision) -> list[dict]`, `shared_output(trip) -> dict` (`unplaced`, `uncertainty`, `provenance`, `reasons`, `tradeoffs`, `trip_context`)
  - `build_plan(...)` cùng chữ ký và **cùng đầu ra** như P3
  - `plan_fixtures`: `CENTRE`, `SOUTH`, `FakeLive`, `spot(pid, anchor, i, **kw)`, `sample_trip(**kw) -> (decision, recs)`, `prepared(d, recs, weather=None, matrix=fake_matrix) -> Trip`

- [ ] **Step 1: Thêm fixture và viết test**

Thêm vào cuối `tests/planning/plan_fixtures.py`:

```python


CENTRE = (11.9404, 108.4583)
SOUTH = (11.9029, 108.4482)     # about 4 km from the centre


class FakeLive:
    """The one live setting build.prepare reads."""
    tz_offset_h = 7


def spot(pid, anchor, i, **kw):
    """A place i steps (about 300 m each) from one of the two centres; the area follows the centre."""
    return rec(pid, anchor[0] + i * 0.002, anchor[1] + i * 0.002, area="area-1" if anchor == CENTRE else "area-2", **kw)


def sample_trip(**kw):
    """Four places in the centre, three out south and a restaurant: the two-day trip the P4 tests share."""
    recs = [spot("c1", CENTRE, 0), spot("c2", CENTRE, 1), spot("c3", CENTRE, 2), spot("c4", CENTRE, 3),
            spot("s1", SOUTH, 0), spot("s2", SOUTH, 1), spot("s3", SOUTH, 2),
            spot("r1", CENTRE, 4, usable=("meal", "backup"))]
    return decision([r["id"] for r in recs], **kw), recs


def prepared(d, recs, weather=None, matrix=fake_matrix):
    """build.prepare with every outside source replaced."""
    from planning.build import prepare
    return prepare(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=matrix, sun_fn=fixed_sun,
                   weather=weather)
```

Tạo `tests/planning/test_planning_prepare.py`:

```python
from plan_fixtures import prepared, sample_trip

import planning.build as build_module
from planning.build import schedule_trip


def test_each_day_gets_the_rain_of_its_date_and_a_date_the_forecast_lacks_stays_unknown():
    d, recs = sample_trip(days=3)
    trip = prepared(d, recs, weather={"2026-12-12": {"rain_prob": 0.7}, "2026-12-13": {"rain_prob": None},
                                      "2027-01-01": {"rain_prob": 1.0}})
    assert [cx.rain for cx in trip.ctxs] == [0.7, None, None]


def test_without_dates_or_a_forecast_no_day_has_rain():
    d, recs = sample_trip(start_date=None, days=None)
    assert all(cx.rain is None for cx in prepared(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}}).ctxs)
    d, recs = sample_trip()
    assert all(cx.rain is None for cx in prepared(d, recs).ctxs)


def test_every_day_knows_how_much_the_trip_wants_each_place():
    d, recs = sample_trip()
    d["trip_context"]["soft_weights"] = [{"feature": "scenic_view", "value": "present", "context": None, "weight": 1}]
    recs[0]["experience"]["scenic_view"] = {"value": "present", "distribution": {"present": 3}, "status": "VERIFIED",
                                            "n": 3}
    prefs = prepared(d, recs).ctxs[0].prefs
    assert prefs["c1"] == 1.0 and prefs["c2"] == 0.0


def test_a_day_seen_before_is_not_ordered_again(monkeypatch):
    d, recs = sample_trip()
    trip = prepared(d, recs)
    calls, real = [], build_module.order_day
    monkeypatch.setattr(build_module, "order_day", lambda ids, cx: calls.append(1) or real(ids, cx))
    first = schedule_trip(trip)
    again = schedule_trip(trip, {"travel": 2.0})
    assert len(calls) == 2 and first.per_day == again.per_day and first.results == again.results


def test_objective_weights_reach_the_day_split_but_not_the_shared_days():
    d, recs = sample_trip()
    trip = prepared(d, recs)
    s = schedule_trip(trip, {"repeat": 40.0})
    assert s.ctxs[0].cfg.weights["repeat"] == 40.0 and "repeat" not in trip.ctxs[0].cfg.weights
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_prepare.py -q`
Expected: FAIL với `ImportError: cannot import name 'prepare' from 'planning.build'` (từ `prepared`) / `cannot import name 'schedule_trip'`

- [ ] **Step 3: Viết code**

Trong `src/planning/build.py`:

1. Docstring: thay câu `This phase builds one plan around the user's base; variants, robustness, backups and lodging come later.` bằng `prepare() does once what every variant shares; schedule_trip() lays the trip out for one objective's weights.`
2. `from dataclasses import asdict` → `from dataclasses import asdict, dataclass, field, replace`
3. `from .travel import build_travel` → hai dòng:

```python
from .traits import preference
from .travel import Travel, build_travel
```

4. Xoá toàn bộ hàm `build_plan` (từ dòng `def build_plan(` tới ngay trước `def render_text(`) và đặt vào chỗ đó:

```python
@dataclass
class Trip:
    """Everything the variants of one trip share: places, points, one travel matrix, the days. Built once a turn."""
    decision: dict
    cfg: Settings
    pace: str
    by_place: dict                  # id -> Place
    unplaced: list
    by_id: dict                     # every serving record by id, for the backups
    points: dict                    # node -> Point | None
    travel: Travel
    days: list
    ctxs: list                      # one DayCtx a day, with the default weights
    warnings: list
    weather: dict | None
    routes: dict = field(default_factory=dict)      # (day index, sorted ids) -> DayResult, shared by every variant


@dataclass(frozen=True)
class Schedule:
    """One way of laying the trip out: which places on which day, in which order, and what validate said."""
    per_day: list
    results: list
    ctxs: list
    violations: list
    warnings: list


def prepare(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
            matrix_fn=None, sun_fn=None, weather: dict | None = None) -> Trip:
    """weather: {"YYYY-MM-DD": {"rain_prob": 0..1, "source", "fetched_at"}} or None. P5 fills it from live.weather."""
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    geocode_fn = geocode_fn or (lambda text: live.geocode(text, live_cfg))
    matrix_fn = matrix_fn or live.travel_matrix
    sun_fn = sun_fn or live.sun_times
    by_id = {r["id"]: r for r in records}
    tc = decision["trip_context"]
    ctx = tc["context"]
    pace = (tc.get("pace") or {}).get("level") or "normal"
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
    soft = tc.get("soft_weights") or []
    prefs = {p.id: preference(p, soft) for p in placed}

    def rain_on(d) -> float | None:
        day = (weather or {}).get(d.date.isoformat()) if d.date else None
        return day.get("rain_prob") if day else None

    ctxs = [DayCtx(d, by_place, travel, cfg, pace,
                   sun_fn(d.date, *centre, live_cfg.tz_offset_h) if d.date and centre else None, rain_on(d), prefs)
            for d in days]
    return Trip(decision, cfg, pace, by_place, unplaced, by_id, points, travel, days, ctxs, warnings, weather)


def schedule_trip(trip: Trip, weights: dict | None = None) -> Schedule:
    """Lay the trip out with one objective's day-split weights merged over the defaults (None = the defaults)."""
    cfg = trip.cfg
    ctxs = trip.ctxs if not weights else [replace(cx, cfg=replace(cfg, weights={**cfg.weights, **weights}))
                                          for cx in trip.ctxs]
    warnings: list[dict] = []
    ids = sorted(trip.by_place)
    cap = int(cfg.fill_ratio * max(d.end - d.start for d in trip.days))
    clusters = cluster_places(ids, {p.id: p.area for p in trip.by_place.values()}, trip.travel, cfg)
    clusters = split_to_fit(clusters, lambda c: load_of(c, trip.by_place, cfg, trip.pace), cap, trip.travel)
    per_day, flag = assign_days(clusters, ctxs)
    if flag:
        warnings.append(_warn(flag))
    results = []
    for day_ids, cx in zip(per_day, ctxs):
        key = (cx.day.index, tuple(sorted(day_ids)))
        if key not in trip.routes:      # the order inside a day does not depend on the day-split weights
            trip.routes[key] = order_day(day_ids, cx)
        results.append(trip.routes[key])
    for cx, r in zip(ctxs, results):
        for note in r.notes:
            code, _, meal = note.partition(":")
            warnings.append(_warn(code, day=cx.day.index + 1, meal=MEAL_NAME.get(meal, meal)))
    tc = trip.decision["trip_context"]
    anchors = {c["id"] for c in trip.decision["confirmed"] if c.get("role") == "anchor"}
    violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                          (tc.get("pace") or {}).get("max_leg_min"))
    return Schedule(per_day, results, ctxs, violations, warnings)


def itinerary(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "date": d.date.isoformat() if d.date else None, "weekday": d.weekday,
             "window": [fmt(d.start), fmt(d.end)], "method": r.method,
             "items": [_item(i) for i in r.items]} for d, r in zip(days, results)]


def travel_load(days: list, results: list) -> list[dict]:
    return [{"day": d.index + 1, "travel_min": r.travel_min, "wait_min": r.wait_min,
             "longest_leg_min": max((i.end - i.start for i in r.items if i.kind == "travel"), default=0)}
            for d, r in zip(days, results)]


def flag_warnings(decision: dict) -> list[dict]:
    return [{"code": "flag", "text": f} for c in decision["confirmed"] for f in c.get("flags") or []]


def shared_output(trip: Trip) -> dict:
    """The parts of the Plan Output that do not depend on how the trip is laid out."""
    decision, travel = trip.decision, trip.travel
    return {
        "unplaced": [asdict(u) for u in trip.unplaced],
        "uncertainty": {"travel_source": travel.source, "rough_pairs": travel.rough_pairs,
                        "estimated": ["travel_minutes", "visit_minutes", "cost"]},
        "provenance": {"travel": {"source": travel.source, "fetched_at": travel.fetched_at},
                       "points": {n: {"text": pt.text, "source": pt.source, "fetched_at": pt.fetched_at}
                                  for n, pt in trip.points.items() if pt}},
        "reasons": decision.get("decision_log") or [],
        "tradeoffs": [{"kind": "relaxed", "place_id": c["id"], "features": c["relaxed"]}
                      for c in decision["confirmed"] if c.get("relaxed")]
                     + [{"kind": "unplaced", "place_id": u.id, "reason": u.reason} for u in trip.unplaced],
        "trip_context": decision["trip_context"],
    }


def build_plan(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
               matrix_fn=None, sun_fn=None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn)
    sched = schedule_trip(trip)
    return {
        "ok": not sched.violations,
        "itinerary": itinerary(trip.days, sched.results),
        "travel_load": travel_load(trip.days, sched.results),
        "violations": [asdict(v) for v in sched.violations],
        "warnings": trip.warnings + sched.warnings + flag_warnings(decision),
        **shared_output(trip),
    }


```

(`from .model import Item` vẫn cần cho `_item`; không xoá import nào khác.)

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning -q`
Expected: PASS — 5 test mới, và 16 test của `test_planning_build.py` cùng 3 test CLI của P3 không đổi mà vẫn xanh (đầu ra `build_plan` giữ nguyên thứ tự khoá và cảnh báo)

- [ ] **Step 5: Commit**

```bash
git add src/planning/build.py tests/planning/plan_fixtures.py tests/planning/test_planning_prepare.py
git commit -m "refactor(planning): prepare a trip once and lay it out per objective"
```


### Task 5: Mục tiêu — `objectives.py`

**Files:**
- Create: `src/planning/objectives.py`
- Test: `tests/planning/test_planning_objectives.py`

**Interfaces:**
- Consumes: `planning.days.exposed_risk/repeats/pref_risk` (Task 3), `planning.traits.exposure`.
- Produces:
  - `planning.objectives.LABEL: dict[str, str]` (nhãn tiếng Việt)
  - `choose(trip_context, rains: list[float | None], prefs: dict, cfg) -> list[str]`
  - `metrics(ctxs, results) -> dict` khoá `travel_min`, `cost_vnd`, `cost_unknown`, `rain_exposed`, `exposure_unknown`, `repeats`, `pref_risk`
  - `score(objective, metrics) -> tuple` (nhỏ hơn là tốt hơn; phần tử 2 là `travel_min`)

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_objectives.py`:

```python
import pytest
from plan_fixtures import CFG, day_ctx, rec

from planning.objectives import LABEL, choose, metrics, score
from planning.route import order_day


def tc(pace="normal", budget=None):
    return {"context": {"budget_vnd": budget}, "pace": {"level": pace}}


def test_least_travel_is_always_chosen_and_the_others_only_when_the_trip_calls_for_them():
    assert choose(tc(pace="slow"), [None, None], {}, CFG) == ["least_travel"]
    assert choose(tc(), [None], {}, CFG) == ["least_travel", "diverse"]
    assert choose(tc(pace="slow", budget=2_000_000), [None], {}, CFG) == ["least_travel", "low_cost"]
    assert choose(tc(pace="slow"), [0.3, 0.7], {}, CFG) == ["least_travel", "weather_robust"]
    assert choose(tc(pace="slow"), [None], {"a": 0.0, "b": 1.0}, CFG) == ["least_travel", "preference_fit"]


def test_never_more_than_max_variants_in_the_configured_order():
    got = choose(tc(budget=1), [0.9], {"a": 1.0}, CFG)
    assert got == ["least_travel", "weather_robust", "preference_fit"] and len(got) == CFG.max_variants


def test_a_rain_probability_just_under_the_threshold_does_not_call_for_weather():
    assert "weather_robust" not in choose(tc(), [CFG.rain_high - 0.01], {}, CFG)


def test_metrics_add_up_travel_known_costs_exposure_repeats_and_preference_risk():
    price = {"min_vnd": 50000, "typical_vnd": 50000, "max_vnd": 50000}
    recs = [rec("a", 1, 1, price=price, features={"weather_exposed": "present"}, group="park"),
            rec("b", 1, 1, group="park"), rec("c", 1, 1, group="cafe", features={"setting": "indoor"})]
    cx = day_ctx(recs, rain=0.5, prefs={"a": 2.0}, start_node="h", extra_nodes=["h"])
    m = metrics([cx], [order_day(["a", "b", "c"], cx)])
    assert (m["cost_vnd"], m["cost_unknown"]) == (50000, 2)
    assert (m["rain_exposed"], m["exposure_unknown"], m["repeats"]) == (0.5, 1, 1)
    assert m["pref_risk"] == pytest.approx(1.0) and m["travel_min"] > 0


def test_each_objective_scores_on_its_own_measure_then_on_travel():
    m = {"travel_min": 90, "cost_vnd": 120000, "rain_exposed": 0.4, "repeats": 2, "pref_risk": 1.5}
    assert [score(o, m) for o in ("least_travel", "low_cost", "weather_robust", "diverse", "preference_fit")] == [
        (90, 90), (120000, 90), (0.4, 90), (2, 90), (1.5, 90)]
    assert set(LABEL) == set(CFG.objective_order)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_objectives.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.objectives'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/objectives.py`:

```python
"""Planning objectives (docs/ARCHITECTURE.md §10): which ones a trip calls for, and how a laid-out trip scores on each.

Every objective is a rule: its day-split weights (config objective_weights) and a score where lower is better, ties
broken by total travel. No objective changes what validate checks.
"""

from .days import exposed_risk, pref_risk, repeats
from .settings import Settings
from .traits import exposure

LABEL = {"least_travel": "Ít di chuyển", "low_cost": "Chi phí thấp", "weather_robust": "Vững trước thời tiết",
         "diverse": "Đa dạng trải nghiệm", "preference_fit": "Hợp sở thích"}


def choose(trip_context: dict, rains: list, prefs: dict, cfg: Settings) -> list[str]:
    """At most max_variants objectives, in objective_order, among those the trip calls for. rains: rain probability
    of each day (None = no forecast); prefs: place id -> preference."""
    ctx = trip_context["context"]
    pace = (trip_context.get("pace") or {}).get("level") or "normal"
    called = {
        "least_travel": True,
        "weather_robust": any(r is not None and r >= cfg.rain_high for r in rains),
        "preference_fit": any(v > 0 for v in prefs.values()),
        "low_cost": ctx.get("budget_vnd") is not None,
        "diverse": pace != "slow",
    }
    return [o for o in cfg.objective_order if called[o]][: cfg.max_variants]


def metrics(ctxs: list, results: list) -> dict:
    """What every objective is scored on, measured on the finished days."""
    m = {"travel_min": 0, "cost_vnd": 0, "cost_unknown": 0, "rain_exposed": 0.0, "exposure_unknown": 0,
         "repeats": 0, "pref_risk": 0.0}
    for cx, r in zip(ctxs, results):
        ids = list(r.order)
        m["travel_min"] += r.travel_min
        for i in ids:
            p = cx.places[i]
            if p.cost_vnd is None:
                m["cost_unknown"] += 1
            else:
                m["cost_vnd"] += p.cost_vnd
            m["exposure_unknown"] += exposure(p) is None
        m["rain_exposed"] += exposed_risk(ids, cx)
        m["repeats"] += repeats(ids, cx)
        m["pref_risk"] += pref_risk(ids, cx)
    m["rain_exposed"] = round(m["rain_exposed"], 3)
    m["pref_risk"] = round(m["pref_risk"], 3)
    return m


def score(objective: str, m: dict) -> tuple:
    """Lower is better. Cost is per person over known prices; lodging joins it in P5."""
    main = {"least_travel": m["travel_min"], "low_cost": m["cost_vnd"], "weather_robust": m["rain_exposed"],
            "diverse": m["repeats"], "preference_fit": m["pref_risk"]}[objective]
    return main, m["travel_min"]
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_objectives.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/objectives.py tests/planning/test_planning_objectives.py
git commit -m "feat(planning): objectives chosen from the trip, with their measures and scores"
```


### Task 6: Độ vững — `robustness.py`

**Files:**
- Create: `src/planning/robustness.py`
- Test: `tests/planning/test_planning_robustness.py`

**Interfaces:**
- Consumes: `planning.schedule.DayCtx/simulate`, `planning.travel.Travel`, `planning.traits.exposure`, `cfg.robustness`, `cfg.rain_high`.
- Produces:
  - `planning.robustness.LEVEL_LABEL` (`solid` → "Vững", `feasible` → "Khả thi", `fragile` → "Mong manh")
  - `lost_places(order: tuple, cx: DayCtx) -> list[str]`
  - `robustness(ctxs, results, travel_source: str) -> dict` khoá `level`, `label`, `reasons` (tiếng Việt), `scenarios` (`{id, tier, text, lost}`), `breaking` (id kịch bản làm mất nơi), `skipped`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_robustness.py`:

```python
from plan_fixtures import day_ctx, rec

from planning.robustness import lost_places, robustness
from planning.route import order_day


def one_day(end, end_node=None, **kw):
    """One place, 10 minutes from the start: travel 08:00-08:10, visit 08:10-09:10 (typical 60), then a buffer."""
    cx = day_ctx([rec("a", 1, 1, **kw)], start_node="h", end_node=end_node, end=end, extra_nodes=["h"])
    return cx, order_day(["a"], cx)


def level(end, source="osrm", **kw):
    cx, r = one_day(end, **kw)
    return robustness([cx], [r], source)


def test_a_day_with_room_to_spare_is_solid():
    rob = level(1260)
    assert (rob["level"], rob["label"], rob["breaking"]) == ("solid", "Vững", [])


def test_a_day_that_survives_the_small_delays_but_not_half_an_hour_late_is_feasible():
    rob = level(570)                                 # 09:30: +15, +20% visit, +25% travel fit; +30 does not
    assert rob["level"] == "feasible" and rob["breaking"] == ["late_30"]
    assert any("xuất phát trễ 30 phút: mất 1 nơi" in t for t in rob["reasons"])


def test_a_day_with_no_slack_is_fragile():
    rob = level(550)                                 # the visit ends exactly at the end of the day
    assert rob["level"] == "fragile" and "late_15" in rob["breaking"]


def test_the_buffer_absorbs_a_delay_before_the_way_back():
    cx, r = one_day(580, end_node="h")               # visit 08:10-09:10, buffer, back home 09:40 = the day's end
    assert lost_places(r.order, cx) == []
    assert robustness([cx], [r], "osrm")["breaking"] == ["late_30"]       # 15 minutes late still gets home in time


def test_a_rough_matrix_never_makes_a_plan_solid():
    rob = level(1260, source="rough")
    assert rob["level"] == "feasible" and any("ước lượng thô" in t for t in rob["reasons"])


def test_exposed_places_on_a_rainy_day_are_lost_in_the_rain_scenario():
    cx = day_ctx([rec("a", 1, 1, features={"weather_exposed": "present"}), rec("b", 1, 1)], rain=0.8)
    rob = robustness([cx], [order_day(["a", "b"], cx)], "osrm")
    rain = next(s for s in rob["scenarios"] if s["id"] == "rain")
    assert rain["lost"] == ["a"] and rob["level"] == "feasible"


def test_without_a_forecast_the_rain_scenario_is_skipped_and_said_so():
    cx = day_ctx([rec("a", 1, 1, features={"weather_exposed": "present"})])
    rob = robustness([cx], [order_day(["a"], cx)], "osrm")
    assert rob["skipped"] == ["rain"] and "rain" not in [s["id"] for s in rob["scenarios"]]
    assert any("Chưa biết thời tiết" in t for t in rob["reasons"])


def test_an_empty_day_loses_nothing_and_the_answer_does_not_change_between_runs():
    cx = day_ctx([rec("a", 1, 1)])
    empty = order_day([], cx)
    assert robustness([cx], [empty], "osrm")["level"] == "solid"
    cx2, r2 = one_day(570)
    assert robustness([cx2], [r2], "osrm") == robustness([cx2], [r2], "osrm")


def test_a_plan_that_never_travels_is_not_capped_by_a_rough_matrix():
    cx = day_ctx([rec("a", 1, 1)])                       # no start or end point: a visit and nothing else
    assert robustness([cx], [order_day(["a"], cx)], "rough")["level"] == "solid"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_robustness.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.robustness'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/robustness.py`:

```python
"""Robustness (docs/specs/PLANNING_SPEC.md ⓕ, docs/ARCHITECTURE.md §12): solid / feasible / fragile.

Fixed perturbations from config, never random. Each scenario re-runs the chosen order of every day and counts the
places that no longer fit: a visit outside its hours, or one after which the day's end point cannot be reached in
time. Buffers are what absorbs a delay, so a delay they swallow loses nothing. A plan that travels on a rough matrix
is capped at feasible: rough minutes cannot prove it solid.
"""

import math
from dataclasses import replace

from .schedule import DayCtx, simulate
from .traits import exposure
from .travel import Travel

LEVEL_LABEL = {"solid": "Vững", "feasible": "Khả thi", "fragile": "Mong manh"}
VISIT_KEYS = ("short", "typical", "long")


def _scaled_travel(travel: Travel, pct: int) -> Travel:
    legs = [[(m if mode == "none" else math.ceil(m * (100 + pct) / 100), mode) for m, mode in row]
            for row in travel.legs]
    return Travel(travel.ids, legs, travel.source, travel.fetched_at, travel.rough_pairs)


def _perturbed(cx: DayCtx, sc: dict) -> DayCtx:
    if sc.get("start_min"):
        cx = replace(cx, day=replace(cx.day, start=cx.day.start + sc["start_min"]))
    if sc.get("visit_pct"):
        pct = sc["visit_pct"]
        cx = replace(cx, places={i: replace(p, visit={**p.visit, **{k: math.ceil(p.visit[k] * (100 + pct) / 100)
                                                                     for k in VISIT_KEYS if k in p.visit}})
                                 for i, p in cx.places.items()})
    if sc.get("travel_pct"):
        cx = replace(cx, travel=_scaled_travel(cx.travel, sc["travel_pct"]))
    return cx


def lost_places(order: tuple, cx: DayCtx) -> list[str]:
    """The stops of one day that no longer fit when the day runs as cx says."""
    if not order:
        return []
    r = simulate(list(order), cx)
    bad = {v.place_id for v in r.violations if v.kind == "hours"}
    end_node = cx.day.end_node
    for it in r.items:
        if it.kind == "visit":
            back = cx.travel.leg(it.place_id, end_node)[0] if end_node else 0
            if it.end + back > cx.day.end:
                bad.add(it.place_id)
    return [i for i in order if i in bad]


def _describe(sc: dict) -> str:
    if sc.get("rain"):
        return "mưa vào ngày dự báo mưa"
    if sc.get("start_min"):
        return f'xuất phát trễ {sc["start_min"]} phút'
    if sc.get("visit_pct"):
        return f'mỗi nơi ở lâu hơn {sc["visit_pct"]}%'
    return f'di chuyển chậm hơn {sc["travel_pct"]}%'


def robustness(ctxs: list[DayCtx], results: list, travel_source: str) -> dict:
    cfg = ctxs[0].cfg
    rob = cfg.robustness
    forecast = any(cx.rain is not None for cx in ctxs)
    scenarios, skipped = [], []
    for sc in rob["scenarios"]:
        if sc.get("rain"):
            if not forecast:
                skipped.append(sc["id"])
                continue
            lost = [i for cx, r in zip(ctxs, results) if cx.rain is not None and cx.rain >= cfg.rain_high
                    for i in r.order if exposure(cx.places[i]) == "exposed"]
        else:
            lost = [i for cx, r in zip(ctxs, results) for i in lost_places(r.order, _perturbed(cx, sc))]
        scenarios.append({"id": sc["id"], "tier": sc["tier"], "text": _describe(sc), "lost": lost})
    if all(len(s["lost"]) <= rob["solid_max_lost"] for s in scenarios):
        level = "solid"
    elif all(len(s["lost"]) <= rob["feasible_max_lost"] for s in scenarios if s["tier"] == "small"):
        level = "feasible"
    else:
        level = "fragile"
    names = {i: p.name for cx in ctxs for i, p in cx.places.items()}
    reasons = [f'{s["text"]}: mất {len(s["lost"])} nơi ({", ".join(names[i] for i in s["lost"])})'
               for s in scenarios if s["lost"]]
    travels = any(i.kind == "travel" for r in results for i in r.items)
    if level == "solid" and travel_source == "rough" and travels:
        level = "feasible"
        reasons.append("Thời gian di chuyển là ước lượng thô nên không kết luận Vững.")
    if not reasons:
        reasons.append("Chịu được mọi kịch bản nhiễu đã thử.")
    if skipped:
        reasons.append("Chưa biết thời tiết: chưa thử kịch bản mưa.")
    return {"level": level, "label": LEVEL_LABEL[level], "reasons": reasons, "scenarios": scenarios,
            "breaking": [s["id"] for s in scenarios if s["lost"]], "skipped": skipped}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_robustness.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/robustness.py tests/planning/test_planning_robustness.py
git commit -m "feat(planning): robustness from fixed delays, capped when travel times are rough"
```


### Task 7: Dự phòng — `backup.py`

**Files:**
- Create: `src/planning/backup.py`
- Test: `tests/planning/test_planning_backup.py`

**Interfaces:**
- Consumes: `planning.places.build_places/windows_on`, `planning.schedule.intervals_for`, `planning.traits`, `planning.travel.km/rough_minutes`, `corpus.serving.check`. `backup_pool` của Decision Output: `{"id", "name", "for": id | None, "reason"}`.
- Produces:
  - `planning.backup.REASON_TEXT`, `sensitive(item, cx) -> list[str]` (mã `rain`, `hours_uncertain`, `near_close`, `far`)
  - `backups(ctxs, results, decision, by_id) -> {"places": [...], "on_delay": [...]}` — mỗi phần tử `places`: `day`, `place_id`, `name`, `reasons`, `text`, `alternatives` (`id`, `name`, `minutes_rough`, `for_this`, `reason`), `none_text`; mỗi phần tử `on_delay`: `day`, `place_id`, `name`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_backup.py`:

```python
from plan_fixtures import all_days, day_ctx, decision, flat_travel, rec

from planning.backup import backups
from planning.route import order_day

AT = (11.94, 108.45)
WET = {"weather_exposed": "present"}
DRY = {"weather_exposed": "sheltered"}


def near(pid, step=1, **kw):
    """A record step x ~300 m from AT."""
    return rec(pid, AT[0] + step * 0.002, AT[1] + step * 0.002, **kw)


def pool_of(*ids, for_=None, reason="next_best"):
    return [{"id": i, "name": i, "for": for_, "reason": reason} for i in ids]


def run(day_recs, pool_recs, pool, *, rain=None, hard=(), roles=None, prefs=None, start_node=None, travel=None):
    """Backups of one day holding day_recs, with pool as the Decision's backup_pool."""
    cx = day_ctx(day_recs, rain=rain, roles=roles, prefs=prefs, start_node=start_node,
                 extra_nodes=["h"] if start_node else (), travel=travel)
    r = order_day(sorted(cx.places), cx)
    d = decision([x["id"] for x in day_recs], roles=roles, hard=hard)
    d["backup_pool"] = pool
    return backups([cx], [r], d, {x["id"]: x for x in [*day_recs, *pool_recs]})


def test_an_exposed_place_on_a_rainy_day_gets_a_sheltered_one_of_its_kind_nearby():
    out = run([near("a", 0, features=WET, group="garden")],
              [near("dry", 1, features=DRY, group="garden"), near("wet", 1, features=WET, group="garden"),
               near("unknown", 1, group="garden"), near("other", 1, features=DRY, group="cafe")],
              pool_of("dry", "wet", "unknown", "other"), rain=0.8)["places"]
    assert [(p["place_id"], p["reasons"]) for p in out] == [("a", ["rain"])]
    assert [x["id"] for x in out[0]["alternatives"]] == ["dry"]
    assert out[0]["text"] == "ngoài trời vào ngày dự báo mưa" and out[0]["none_text"] is None


def test_the_same_place_on_a_dry_or_unknown_day_is_not_sensitive():
    for rain in (0.2, None):
        assert run([near("a", 0, features=WET)], [], [], rain=rain)["places"] == []


def test_a_backup_the_decision_kept_for_this_place_comes_before_a_closer_one_of_the_same_kind():
    out = run([near("a", 0, status="UNCERTAIN", group="cafe")],
              [near("close", 1, group="cafe"), near("mine", 3, group="other")],
              pool_of("close") + pool_of("mine", for_="a", reason="same_kind"))["places"]
    assert out[0]["reasons"] == ["hours_uncertain"]
    assert [(x["id"], x["for_this"]) for x in out[0]["alternatives"]] == [("mine", True), ("close", False)]


def test_replacements_that_are_far_shaky_closed_steep_unknown_or_already_confirmed_are_left_out():
    hard = [{"feature": "steep_or_stairs", "op": "ne", "value": "present", "unknown_policy": "exclude"}]
    out = run([near("a", 0, status="OUTDATED", group="g"), near("b", 5, group="g")],
              [near("far", 100, group="g"), near("shaky", 1, group="g", status="UNCERTAIN"),
               near("closed", 1, group="g", hours={**all_days(), "mon": []}),
               near("steep", 1, group="g", features={"steep_or_stairs": "present"}),
               rec("nocoord", None, None, group="g")],
              pool_of("far", "shaky", "closed", "steep", "nocoord", "ghost", "b"), hard=hard)["places"]
    assert [(p["place_id"], p["alternatives"], p["none_text"]) for p in out] == [
        ("a", [], "Không có phương án thay.")]


def test_a_visit_ending_close_to_closing_time_is_sensitive():
    tight = near("a", 0, hours=all_days("08:00", "08:20"), visit=(10, 15, 20))
    assert run([tight], [], [])["places"][0]["reasons"] == ["near_close"]


def test_a_place_far_from_where_the_day_starts_is_sensitive():
    out = run([near("a", 0)], [], [], start_node="h", travel=flat_travel(["h", "a"], 50))["places"]
    assert out[0]["reasons"] == ["far"]


def test_on_a_delay_the_least_wanted_selected_stop_goes_first_never_an_anchor():
    out = run([near("a", 0), near("b", 1), near("c", 2)], [], [], roles={"a": "anchor"}, prefs={"b": 1.0, "c": 0.0})
    assert out["on_delay"] == [{"day": 1, "place_id": "c", "name": "c"}]
    only_fixed = run([near("a", 0), near("b", 1)], [], [], roles={"a": "anchor", "b": "locked"})
    assert only_fixed["on_delay"] == []
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_backup.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.backup'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/backup.py`:

```python
"""Backups (docs/specs/PLANNING_SPEC.md ⓗ, docs/ARCHITECTURE.md §13).

A sensitive visit: weather-exposed on a rainy day · opening hours UNCERTAIN / OUTDATED · ending close to closing time
· far from where its day starts. Its replacements come only from the Decision's backup_pool: close by (rough minutes,
since backups are not in the travel matrix), the same kind, through the hard filters, and not sensitive for the same
reason. None found -> said so, nothing invented. For a delay, each day names the stop to drop first.
"""

from corpus.serving import check

from . import places as pl
from .schedule import DayCtx, intervals_for
from .traits import exposure, kind_group
from .travel import km, rough_minutes

REASON_TEXT = {"rain": "ngoài trời vào ngày dự báo mưa", "hours_uncertain": "giờ mở cửa chưa chắc",
               "near_close": "sát giờ đóng cửa", "far": "xa điểm xuất phát của ngày"}
SHAKY = ("UNCERTAIN", "OUTDATED")


def sensitive(it, cx: DayCtx) -> list[str]:
    """Why one visit item is sensitive, in REASON_TEXT order; [] = it is not."""
    cfg, p = cx.cfg, cx.places[it.place_id]
    out = []
    if cx.rain is not None and cx.rain >= cfg.rain_high and exposure(p) == "exposed":
        out.append("rain")
    if p.hours_status in SHAKY:
        out.append("hours_uncertain")
    if p.hours is not None and any(o <= it.start and it.end <= c and c - it.end < cfg.near_close_min
                                   for o, c in intervals_for(p, cx)):
        out.append("near_close")
    start = cx.day.start_node
    if start and cx.travel.leg(start, p.id)[0] > cfg.far_leg_min:
        out.append("far")
    return out


def _fits(b, s, reasons: list[str], cx: DayCtx, hard_filters: list) -> bool:
    if b.kind != s.kind:
        return False
    if any(hf["op"] == "ne" and check(b.rec, hf["feature"], hf["value"]) == "fail" for hf in hard_filters):
        return False
    if "rain" in reasons and exposure(b) != "sheltered":
        return False
    if "hours_uncertain" in reasons and (b.hours is None or b.hours_status in SHAKY):
        return False
    return pl.windows_on(b.hours, cx.day.weekday) != []        # not closed that day


def backups(ctxs: list[DayCtx], results: list, decision: dict, by_id: dict) -> dict:
    cfg = ctxs[0].cfg
    tc = decision["trip_context"]
    mobility, hard = tc["context"].get("mobility"), tc.get("hard_filters") or []
    confirmed = {c["id"] for c in decision["confirmed"]}
    pool = [b for b in decision.get("backup_pool") or [] if b["id"] not in confirmed]
    entry = {b["id"]: b for b in pool}
    cands, _ = pl.build_places({"confirmed": [{"id": b["id"], "name": b.get("name"), "role": "selected"}
                                              for b in pool]}, by_id, cfg)
    out, on_delay = [], []
    for cx, r in zip(ctxs, results):
        for it in r.items:
            if it.kind != "visit":
                continue
            reasons = sensitive(it, cx)
            if not reasons:
                continue
            s = cx.places[it.place_id]
            alts = []
            for b in cands:
                minutes = rough_minutes(km((s.lat, s.lng), (b.lat, b.lng)), mobility, cfg)
                mine = entry[b.id].get("for") == s.id
                same_kind = mine or (kind_group(b) is not None and kind_group(b) == kind_group(s))
                if minutes <= cfg.backup_radius_min and same_kind and _fits(b, s, reasons, cx, hard):
                    alts.append((not mine, minutes, b.id, b))
            alts.sort(key=lambda a: a[:3])
            out.append({"day": cx.day.index + 1, "place_id": s.id, "name": s.name, "reasons": reasons,
                        "text": ", ".join(REASON_TEXT[x] for x in reasons),
                        "alternatives": [{"id": b.id, "name": b.name, "minutes_rough": m, "for_this": not other,
                                          "reason": entry[b.id].get("reason")}
                                         for other, m, _, b in alts[: cfg.backups_per_place]],
                        "none_text": None if alts else "Không có phương án thay."})
        droppable = [i for i in r.order if cx.places[i].role == "selected"]
        if len(r.order) >= 2 and droppable:
            start, prefs = cx.day.start_node, cx.prefs or {}
            pid = min(droppable, key=lambda i: (prefs.get(i, 0.0), -(cx.travel.leg(start, i)[0] if start else 0), i))
            on_delay.append({"day": cx.day.index + 1, "place_id": pid, "name": cx.places[pid].name})
    return {"places": out, "on_delay": on_delay}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_backup.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/backup.py tests/planning/test_planning_backup.py
git commit -m "feat(planning): backups for sensitive visits from the decision's backup pool"
```


### Task 8: Dựng các phương án — `variants.py`

**Files:**
- Create: `src/planning/variants.py`
- Test: `tests/planning/test_planning_variants.py`

**Interfaces:**
- Consumes: `planning.build.prepare/schedule_trip/itinerary/travel_load/shared_output/flag_warnings` (Task 4), `objectives` (Task 5), `robustness` (Task 6), `backups` (Task 7).
- Produces:
  - `planning.variants.build_variants(decision, records, cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None, weather=None) -> dict` — Plan Output: `ok`, `variants` (mỗi cái: `id` `v1..`, `objective`, `label`, `score`, `metrics`, `itinerary`, `travel_load`, `robustness`, `backups`, `warnings`), `chosen` (`None`), `comparison`, `violations`, `warnings`, `back_to_decision` (`None` | `{"reason": "no_valid_variant", "places": [...]}`), cộng các khoá của `shared_output`; `provenance.weather` là list `{source, fetched_at}` khi có lịch thành công
  - Mã cảnh báo mới: `weather_unknown`, `variants_same`, `variant_invalid`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_variants.py`:

```python
import json

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, spot

from planning.variants import build_variants

WET = {"weather_exposed": "present"}


def run(d, recs, weather=None):
    return build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                          sun_fn=fixed_sun, weather=weather)


def day_of(variant, pid):
    return next(d["day"] for d in variant["itinerary"] for i in d["items"] if i.get("place_id") == pid)


def wet_south():
    """The sample trip with the three southern places open to the weather, and a last day long enough to hold
    either cluster (the default 15:00 departure leaves no room to swap them)."""
    d, recs = sample_trip(leave_at="20:00")
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features=WET) for i in range(3)]
    return d, recs


def test_a_plain_trip_whose_objectives_agree_gives_one_variant_and_says_so():
    d, recs = sample_trip()                                   # normal pace: least_travel and diverse
    out = run(d, recs)
    assert out["ok"] and [v["objective"] for v in out["variants"]] == ["least_travel"]
    assert "variants_same" in {w["code"] for w in out["warnings"]}


def test_rain_where_the_least_travel_plan_puts_the_open_air_places_gives_a_second_variant_that_moves_them():
    d, recs = wet_south()
    rainy_day = day_of(run(d, recs)["variants"][0], "s1")
    date = ["2026-12-12", "2026-12-13"][rainy_day - 1]
    out = run(d, recs, weather={date: {"rain_prob": 0.9, "source": "open-meteo", "fetched_at": "t"}})
    by_obj = {v["objective"]: v for v in out["variants"]}
    assert set(by_obj) == {"least_travel", "weather_robust"}
    assert day_of(by_obj["least_travel"], "s1") == rainy_day and day_of(by_obj["weather_robust"], "s1") != rainy_day
    assert by_obj["weather_robust"]["metrics"]["rain_exposed"] < by_obj["least_travel"]["metrics"]["rain_exposed"]
    assert out["provenance"]["weather"] == [{"source": "open-meteo", "fetched_at": "t"}]


def test_every_variant_carries_its_itinerary_measures_robustness_and_backups_and_the_table_compares_them():
    d, recs = wet_south()
    out = run(d, recs, weather={"2026-12-12": {"rain_prob": 0.9}, "2026-12-13": {"rain_prob": 0.9}})
    assert out["chosen"] is None and out["back_to_decision"] is None
    for i, v in enumerate(out["variants"]):
        assert v["id"] == f"v{i + 1}" and len(v["itinerary"]) == 2
        assert v["robustness"]["level"] in ("solid", "feasible", "fragile")
        assert {"places", "on_delay"} <= set(v["backups"])
    rows = out["comparison"]
    assert [r["variant"] for r in rows] == [v["id"] for v in out["variants"]]
    assert min(r["travel_vs_best"] for r in rows) == 0
    wet = [p for v in out["variants"] for p in v["backups"]["places"] if "rain" in p["reasons"]]
    assert wet and all(p["none_text"] == "Không có phương án thay." for p in wet)     # the pool is empty


def test_the_same_input_gives_the_same_variants_and_the_output_is_plain_json():
    d, recs = wet_south()
    weather = {"2026-12-12": {"rain_prob": 0.9}}
    first = run(d, recs, weather)
    assert first == run(d, recs, weather) and json.loads(json.dumps(first)) == first


def test_without_a_forecast_the_output_says_weather_was_not_considered():
    d, recs = sample_trip()
    out = run(d, recs)
    assert "weather_unknown" in {w["code"] for w in out["warnings"]} and out["provenance"]["weather"] == []


def test_no_valid_variant_goes_back_to_place_decision_with_the_places_that_broke_it():
    d, recs = sample_trip()
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    out = run(d, recs)
    assert not out["ok"] and out["variants"] == [] and out["comparison"] == []
    assert out["back_to_decision"] == {"reason": "no_valid_variant", "places": ["gone"]}
    assert [v["kind"] for v in out["violations"]] == ["anchor"]


def test_a_trip_with_no_places_is_one_empty_solid_variant():
    d, recs = sample_trip()
    d["confirmed"] = []
    (v,) = run(d, recs)["variants"]
    assert all(day["items"] == [] for day in v["itinerary"]) and v["robustness"]["level"] == "solid"
    assert v["backups"] == {"places": [], "on_delay": []}


def test_a_variant_that_does_not_fit_the_days_is_dropped_and_named():
    d, recs = wet_south()
    d["trip_context"]["context"]["leave_at"] = None          # the last day ends at 15:00 again
    out = run(d, recs, weather={"2026-12-13": {"rain_prob": 0.9}})    # rain where the open-air places go
    codes = [w["code"] for w in out["warnings"]]
    assert [v["objective"] for v in out["variants"]] == ["least_travel"]
    want = {"code": "variant_invalid", "text": "Vững trước thời tiết: không xếp được lịch hợp lệ, bỏ phương án này."}
    assert want in out["warnings"]
    assert codes.count("variants_same") == 1                 # diverse did agree with least_travel: that one is
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_variants.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.variants'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/variants.py`:

```python
"""Two or three checked variants, each best on a different objective (docs/specs/PLANNING_SPEC.md ⓖ).

One prepare() and one travel matrix for all of them. Each chosen objective lays the trip out with its own day-split
weights; a variant validate rejects is dropped, two variants with the same days in the same order are one. No variant
valid -> back to Place Decision with the places that broke it. Lodging joins the loop in P5.
"""

from dataclasses import asdict

from .backup import backups
from .build import flag_warnings, itinerary, prepare, schedule_trip, shared_output, travel_load
from .objectives import LABEL, choose, metrics, score
from .robustness import robustness

WARNING_TEXT = {
    "weather_unknown": "Chưa biết thời tiết: chưa xét mưa khi xếp lịch và khi đo độ vững.",
    "variants_same": "Các mục tiêu cho cùng một lịch: chỉ có {n} phương án.",
    "variant_invalid": "{label}: không xếp được lịch hợp lệ, bỏ phương án này.",
}


def _warn(code: str, **kw) -> dict:
    return {"code": code, "text": WARNING_TEXT[code].format(**kw)}


def _comparison(variants: list[dict]) -> list[dict]:
    """The trade-off table: each variant's measures, and how far it is from the best variant on travel."""
    best_travel = min(v["metrics"]["travel_min"] for v in variants)
    return [{"variant": v["id"], "objective": v["objective"], "label": v["label"],
             "travel_min": v["metrics"]["travel_min"], "travel_vs_best": v["metrics"]["travel_min"] - best_travel,
             "cost_vnd": v["metrics"]["cost_vnd"], "cost_unknown": v["metrics"]["cost_unknown"],
             "rain_exposed": v["metrics"]["rain_exposed"], "repeats": v["metrics"]["repeats"],
             "robustness": v["robustness"]["level"]} for v in variants]


def build_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None,
                   sun_fn=None, weather: dict | None = None) -> dict:
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather)
    cfg = trip.cfg
    objectives = choose(decision["trip_context"], [cx.rain for cx in trip.ctxs], trip.ctxs[0].prefs, cfg)
    tried = [(obj, schedule_trip(trip, cfg.objective_weights[obj])) for obj in objectives]
    warnings = list(trip.warnings)
    if not any(cx.rain is not None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))
    valid = [(obj, s) for obj, s in tried if not s.violations]
    if not valid:
        first = tried[0][1]
        places = sorted({v.place_id for _, s in tried for v in s.violations if v.place_id})
        return {"ok": False, "variants": [], "chosen": None, "comparison": [],
                "violations": [asdict(v) for v in first.violations],
                "warnings": warnings + first.warnings + flag_warnings(decision),
                "back_to_decision": {"reason": "no_valid_variant", "places": places}, **shared_output(trip)}
    warnings += [_warn("variant_invalid", label=LABEL[obj]) for obj, s in tried if s.violations]
    seen, variants = set(), []
    for obj, s in valid:
        orders = tuple(r.order for r in s.results)
        if orders in seen:
            continue
        seen.add(orders)
        m = metrics(s.ctxs, s.results)
        variants.append({
            "id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
            "metrics": m, "itinerary": itinerary(trip.days, s.results),
            "travel_load": travel_load(trip.days, s.results),
            "robustness": robustness(s.ctxs, s.results, trip.travel.source),
            "backups": backups(s.ctxs, s.results, decision, trip.by_id), "warnings": s.warnings})
    if len(variants) < len(valid):
        warnings.append(_warn("variants_same", n=len(variants)))
    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w.get("source")})
    out = {"ok": True, "variants": variants, "chosen": None, "comparison": _comparison(variants), "violations": [],
           "warnings": warnings + flag_warnings(decision), "back_to_decision": None, **shared_output(trip)}
    out["provenance"]["weather"] = [{"source": s, "fetched_at": f} for s, f in weather_src]
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_variants.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/variants.py tests/planning/test_planning_variants.py
git commit -m "feat(planning): two or three checked variants with robustness and backups"
```


### Task 9: Lệnh `python -m planning variants`, public API, golden, tài liệu

**Files:**
- Modify: `src/planning/variants.py` (import + thêm `render_variants`)
- Modify: `src/planning/__init__.py`, `src/planning/__main__.py`
- Modify: `tests/planning/test_planning_cli.py` (thêm vào cuối), `tests/planning/test_planning_boundaries.py` (test public API)
- Create: `tests/planning/test_planning_golden.py`, `tests/planning/golden/variants_wet_south.json` (sinh ra)
- Modify: `docs/specs/PLANNING_SPEC.md`; `README.md` (không commit)

**Interfaces:**
- Consumes: `planning.variants.build_variants` (Task 8), `planning.build.render_text`.
- Produces:
  - `planning.render_variants(out) -> str`, `planning.build_variants`
  - `python -m planning variants <decision_output.json> [--weather forecast.json] [--out plan.json]` — mã thoát 0 khi có phương án hợp lệ, 2 khi không

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_cli.py`:

```python


def test_variants_prints_each_variant_its_robustness_and_the_verdict(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["variants", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "== Phương án 1 · Ít di chuyển" in out and "Độ vững:" in out and out.rstrip().endswith("Hợp lệ.")


def test_variants_reads_a_forecast_file_and_writes_the_plan_output(tmp_path, monkeypatch, capsys, offline):
    wet = rec("a", 11.94, 108.45, features={"weather_exposed": "present"})
    monkeypatch.setattr(cli, "load_records", lambda: [wet])
    forecast = tmp_path / "forecast.json"
    rain = {"rain_prob": 0.9, "source": "open-meteo", "fetched_at": "t"}
    forecast.write_text(json.dumps({"2026-12-12": rain, "2026-12-13": rain}), encoding="utf-8")
    out = tmp_path / "plan.json"
    assert cli.main(["variants", str(write_decision(tmp_path, ["a"])), "--weather", str(forecast),
                     "--out", str(out)]) == 0
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["provenance"]["weather"] == [{"source": "open-meteo", "fetched_at": "t"}]
    assert "rain" in plan["variants"][0]["backups"]["places"][0]["reasons"]


def test_variants_exits_two_and_points_back_to_place_decision(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["variants", str(path)]) == 2
    out = capsys.readouterr().out
    assert "quay lại chọn địa điểm (gone)" in out and out.rstrip().endswith("KHÔNG hợp lệ.")
```

Trong `tests/planning/test_planning_boundaries.py`, test `test_the_public_api_is_the_plan_builder_and_its_settings`, thay dòng

```python
    assert set(planning.__all__) == {"Settings", "build_plan", "load_settings", "render_text"}
```

bằng

```python
    assert set(planning.__all__) == {"Settings", "build_plan", "build_variants", "load_settings", "render_text",
                                     "render_variants"}
```

Tạo `tests/planning/test_planning_golden.py`:

```python
"""Golden variants of a sample trip (docs/specs/PLANNING_SPEC.md §Test). A change to the algorithm that moves them must
update the file on purpose: UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_golden.py"""

import json
import os
from pathlib import Path

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip, spot

from planning.variants import build_variants

GOLDEN = Path(__file__).parent / "golden" / "variants_wet_south.json"


def test_the_variants_of_the_sample_trip_match_the_golden_file():
    d, recs = sample_trip(leave_at="20:00", budget=1_500_000)
    recs[4:7] = [spot(f"s{i + 1}", SOUTH, i, features={"weather_exposed": "present"}) for i in range(3)]
    weather = {"2026-12-12": {"rain_prob": 0.2, "source": "open-meteo", "fetched_at": "t"},
               "2026-12-13": {"rain_prob": 0.8, "source": "open-meteo", "fetched_at": "t"}}
    out = build_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                         sun_fn=fixed_sun, weather=weather)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert out == json.loads(GOLDEN.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py -q`
Expected: FAIL — 3 test `variants` với `SystemExit: 2` (argparse: `invalid choice: 'variants'`) và test public API (`build_variants` chưa có trong `__all__`)

- [ ] **Step 3: Viết code**

Trong `src/planning/variants.py`, dòng import `from .build import flag_warnings, itinerary, prepare, schedule_trip, shared_output, travel_load` thành:

```python
from .build import flag_warnings, itinerary, prepare, render_text, schedule_trip, shared_output, travel_load
```

Thêm vào cuối `src/planning/variants.py`:

```python


def render_variants(out: dict) -> str:
    """The variants as plain lines, for the command line."""
    lines = []
    for n, v in enumerate(out["variants"], 1):
        rob = v["robustness"]
        lines.append(f'== Phương án {n} · {v["label"]} · {rob["label"]}')
        body = render_text({"itinerary": v["itinerary"], "warnings": v["warnings"], "violations": [], "ok": True})
        lines += body.splitlines()[:-1]                 # its last line is the verdict, said once at the end
        lines.append("  Độ vững: " + "; ".join(rob["reasons"]))
        for p in v["backups"]["places"]:
            alts = ", ".join(f'{a["name"]} (~{a["minutes_rough"]} phút)' for a in p["alternatives"])
            lines.append(f'  Dự phòng cho {p["name"]} ({p["text"]}): {alts or p["none_text"]}')
        for x in v["backups"]["on_delay"]:
            lines.append(f'  Nếu trễ ở ngày {x["day"]}: bỏ {x["name"]} trước.')
    if len(out["comparison"]) > 1:
        lines.append("So sánh:")
        for r in out["comparison"]:
            cost = f'{r["cost_vnd"]:,} VND/người'
            if r["cost_unknown"]:
                cost += f' (+{r["cost_unknown"]} nơi chưa có giá)'
            lines.append(f'  {r["label"]}: {r["travel_min"]} phút di chuyển (+{r["travel_vs_best"]}), {cost}')
    for w in out["warnings"]:
        lines.append("! " + w["text"])
    for x in out["violations"]:
        lines.append(f'X {x["kind"]} ngày {(x["day"] + 1) if x["day"] is not None else "-"}: {x["detail"]}'
                     + (" (physical)" if x["physical"] else ""))
    if out["back_to_decision"]:
        lines.append("Không dựng được phương án hợp lệ: quay lại chọn địa điểm ("
                     + ", ".join(out["back_to_decision"]["places"]) + ").")
    lines.append("Hợp lệ." if out["ok"] else "KHÔNG hợp lệ.")
    return "\n".join(lines)
```

Sửa `src/planning/__init__.py` thành:

```python
"""Planning & Validation: confirmed places -> checked itineraries (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
"""

from .build import build_plan, render_text
from .settings import Settings
from .settings import load as load_settings
from .variants import build_variants, render_variants

__all__ = ["Settings", "build_plan", "build_variants", "load_settings", "render_text", "render_variants"]
```

Sửa `src/planning/__main__.py` thành:

```python
"""python -m planning build <decision_output.json> [--out plan.json]
python -m planning variants <decision_output.json> [--weather forecast.json] [--out plan.json]"""

import argparse
import json
import sys
from pathlib import Path

from corpus.serving import load as load_records

from . import build_plan, build_variants, render_text, render_variants


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="print the itinerary of a Decision Output")
    b.add_argument("decision_output", type=Path)
    b.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    v = sub.add_parser("variants", help="print 2-3 checked variants with robustness and backups")
    v.add_argument("decision_output", type=Path)
    v.add_argument("--weather", type=Path, help='{"YYYY-MM-DD": {"rain_prob": 0..1, "source", "fetched_at"}}')
    v.add_argument("--out", type=Path, help="also write the full Plan Output as json")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    decision = json.loads(args.decision_output.read_text(encoding="utf-8"))
    if args.cmd == "build":
        plan = build_plan(decision, load_records())
        text = render_text(plan)
    else:
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_variants(decision, load_records(), weather=weather)
        text = render_variants(plan)
    if args.out:
        args.out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)
    return 0 if plan["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Sinh golden, xem lại nó, rồi chạy test**

Run: `UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_golden.py -q` (PowerShell: `$env:UPDATE_GOLDEN=1; python -m pytest tests/planning/test_planning_golden.py -q; Remove-Item Env:UPDATE_GOLDEN`)
Expected: PASS, file `tests/planning/golden/variants_wet_south.json` được tạo (~13 KB).

Mở file kiểm tay trước khi commit: `variants` có đúng hai phần tử, `least_travel` (`robustness.level = feasible`, vì ba nơi phía nam phơi mưa nằm ở ngày mưa 0,8) và `weather_robust` (`solid`); `warnings` có `variants_same` (`low_cost` trùng `least_travel`). Khác thế này nghĩa là có task trước lệch plan — dừng lại tìm, không commit golden.

Run: `python -m pytest tests/planning -q`
Expected: PASS (187 tests nếu P3 đúng 129 test)

- [ ] **Step 5: Chạy toàn bộ test của repo**

Run: `python -m pytest -q`
Expected: PASS — không test cũ nào đỏ

- [ ] **Step 6: Thử tay và đo (không bắt buộc, không commit gì)**

Dùng lại cách tạo `decision_output.json` ở Task 11 Step 6 của plan P3, rồi:

```bash
python -m planning variants decision_output.json
echo '{"2026-12-12": {"rain_prob": 0.8, "source": "manual", "fetched_at": null}}' > forecast.json
python -m planning variants decision_output.json --weather forecast.json
```

Expected: mỗi phương án một khối `== Phương án n · <mục tiêu> · <mức độ vững>`, các dòng `Độ vững:`, `Dự phòng cho ...`, `Nếu trễ ở ngày ...`; khi có hơn một phương án thì có khối `So sánh:`. Đo thời gian lệnh thứ hai (`Measure-Command` hoặc `time`): ghi số vào báo cáo cuối — ngân sách spec < 2 s cho phần dựng lịch khi OSRM nóng. Xoá `decision_output.json`, `forecast.json`.

- [ ] **Step 7: Sửa `docs/specs/PLANNING_SPEC.md` cho khớp code**

Ba chỗ, dùng Edit; mỗi chuỗi cũ xuất hiện đúng một lần:

1. ⓕ Độ vững:

```text
cũ:  Mỗi kịch bản xếp lại và đếm số nơi bị mất. Ba mức Vững / Khả thi / Mong manh theo ngưỡng.
mới: Mỗi kịch bản chạy lại thứ tự đã chọn của từng ngày và đếm số nơi bị mất (ngoài giờ mở, hoặc sau nó không kịp về điểm kết ngày; đệm là thứ hấp thụ trễ). Mưa không random: nơi phơi mưa ở ngày `rain_prob ≥ rain_high` tính là mất; không có dự báo thì bỏ kịch bản này và nói rõ. Ba mức: Vững = mọi kịch bản mất ≤ `solid_max_lost`; Khả thi = các kịch bản `tier: small` mất ≤ `feasible_max_lost`; còn lại Mong manh.
```

2. Mục "Cấu hình — `config/planning.yaml`", câu do plan P3 viết:

```text
cũ:  Các phase sau thêm: `radius_km` theo mobility, `lodging_k`, `lodging_share`, `min_reviews`, `split_min`, kịch bản nhiễu của độ vững + ngưỡng 3 mức, trọng số từng mục tiêu, trọng số phạt của `repair_day`.
mới: P4 thêm: `rain_high`, `buffer_extra_rain`; `robustness` (kịch bản nhiễu có `tier` small / large, `solid_max_lost`, `feasible_max_lost`); `max_variants`, `objective_order`, `objective_weights` (trộn lên `weights` khi chia ngày: `travel`, `exposed`, `repeat`, `pref_risk`); `near_close_min`, `far_leg_min`, `backup_radius_min`, `backups_per_place`. Các phase sau thêm: `radius_km` theo mobility, `lodging_k`, `lodging_share`, `min_reviews`, `split_min`, trọng số phạt của `repair_day`.
```

3. Bảng "Các phase", dòng P4:

```text
cũ:  | P4 | `robustness`, `backup`, `objectives`, `variants` |
mới: | P4 | `traits`, `robustness`, `backup`, `objectives`, `variants`; CLI `python -m planning variants` (thời tiết vào qua `--weather`, P5 mới tự lấy) |
```

- [ ] **Step 8: Thêm lệnh vào `README.md`**

Ngay sau đoạn `python -m planning build` mà plan P3 đã thêm, thêm:

```markdown
So sánh 2–3 phương án kèm độ vững và dự phòng: `python -m planning variants <decision_output.json> [--weather forecast.json]`; `forecast.json` dạng `{"YYYY-MM-DD": {"rain_prob": 0.8, "source": "...", "fetched_at": "..."}}`, thiếu thì không xét mưa và có cảnh báo.
```

Như P3: sửa working copy nhưng **không** `git add` README; ghi vào báo cáo cuối rằng mục README chưa commit.

- [ ] **Step 9: Commit**

```bash
git add src/planning/variants.py src/planning/__init__.py src/planning/__main__.py tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py tests/planning/test_planning_golden.py tests/planning/golden/variants_wet_south.json docs/specs/PLANNING_SPEC.md
git commit -m "feat(planning): python -m planning variants, its public API and a golden trip"
```


---

## Sau khi plan này xong

`python -m planning variants` cho 2–3 phương án đã kiểm từ một Decision Output, mỗi cái có mục tiêu, số đo, bảng so sánh, độ vững 3 mức với kịch bản làm hỏng, dự phòng cho từng nơi nhạy cảm và nơi bỏ trước khi trễ. Còn lại theo `PLANNING_SPEC.md` §Các phase:

- P5: `live/weather` (đổ vào tham số `weather` của `prepare` — dạng đã chốt ở Task 4), `config/climate.yaml` cho ngày ngoài tầm dự báo, `live/lodging`, `lodging.py`; vòng `for lodging in K+1` bọc quanh `schedule_trip`. Ngân sách 21 lần dựng < 2 s phải đo lại: cache thứ tự theo `(ngày, tập nơi)` không dùng lại được giữa các chỗ ở khác nhau (điểm mở / đóng ngày đổi). Khi đó `low_cost` mới có tiền phòng để khác `least_travel`.
- P6: `pick_variant` đặt `chosen`; `repair_day` dùng `backups` và `on_delay`.
