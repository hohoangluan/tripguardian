# Plan P9 — evaluate.py, measure, write up Planning in README / DEV_LOG

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m planning evaluate` runs the same 30 hidden Trip States Place Decision already uses (`config/eval_trips.yaml`) end to end -- Search Input → Place Decision (`confirmed`) → Planning (variant, lodging, confirm) -- and reports the table `docs/specs/PLANNING_SPEC.md` §Đo asks for: feasible-itinerary rate, real minutes saved against a nearest-neighbour baseline, minutes lodging saves per day, the Vững/Khả thi/Mong manh split, and latency. Then the whole Planning phase (P1, P3-P9), never summarized in `docs/log/DEV_LOG.md` until now, gets one entry there, and `README.md` gains the `evaluate` command next to `build`/`variants`/`lodging`.

**Architecture:** `evaluate.py` is two layers, like `src/decision/evaluate.py` already is: a pure, fixture-testable core (`decision_outputs`, `plan_results`, `evaluate`) that takes records and injected live functions, and a thin `run()` that loads real `corpus.serving` records and real `live.*` functions and writes `data/planning/eval.json` -- only `run()` needs OSRM up and is meant to be run by hand, exactly like `python -m planning build/variants/lodging` already are. Getting a Decision Output for each hidden trip reuses `decision.Engine`'s own public `create`/`act`/`confirm` **in process** (no HTTP, no second server) -- `docs/specs/PLANNING_SPEC.md`'s own module table lists `decision` as one of `planning`'s one-directional dependencies, and `decision/__init__.py` already exports everything this needs. One new public method, `Engine.baseline_travel_min`, gives the real "how much did the optimizer actually buy" baseline without reaching into Planning's own private internals from outside the class.

**Tech Stack:** Python 3.12, stdlib, `pyyaml` (already a dependency), `pytest`. No new dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Đo, bảng phase P9). Blueprint, read directly, not imported beyond its public surface: `src/decision/evaluate.py` (the two-layer shape, the `trips()`/`search_input()` pattern, the `monkeypatch.setattr(ev, "trips", ...)` test style used in `tests/decision/test_evaluate.py`), `src/decision/engine.py`'s `confirm()` (what `NotConfirmable` means and when it fires), `config/eval_trips.yaml` (reused as-is, not modified).

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh.
- `planning` được import `decision` qua `decision/__init__.py` (`Data`, `Engine`, `Store`, `load_settings`) -- đúng bảng "Ranh giới module" của `PLANNING_SPEC.md` ("`planning` → `live`, `decision`, `trip`, `corpus.serving`, `corpus.ontology`, chỉ qua `__init__.py`"). Đây **khác** với P6/P7, nơi tạo phiên qua HTTP loopback vì hai tiến trình server chạy tách biệt; `evaluate.py` chạy một tiến trình, không có server nào đang chạy, nên import trực tiếp qua `__init__.py` là đúng, không phạm RULE §2. Không bao giờ `from decision.engine import ...` hay bất kỳ deep import nào vào nội bộ `decision`.
- `decision.NotConfirmable` không nằm trong `decision/__init__.py`'s export -- `decision_outputs()` bắt `Exception` rộng khi `eng.confirm(...)` thất bại (ghi nhận là trip đó bị Place Decision coi "không khả thi", không phải lỗi) thay vì import riêng kiểu lỗi đó.
- `trips()` và `search_input()` trong `src/planning/evaluate.py` là **bản sao có chủ đích** của hai hàm cùng tên (không public) trong `src/decision/evaluate.py` -- không import chúng (cùng lý do `decision.evaluate` không nằm trong export công khai). Đây là tiền lệ đã có (triplication: `trip/agent.py`, `decision/agent.py` giống hệt nhau vì lý do tương tự).
- Không thêm dependency vào `pyproject.toml`.
- `Engine.baseline_travel_min` là bổ sung tối thiểu duy nhất vào `engine.py` trong plan này; mọi chữ ký khác của P3-P8 không đổi.
- File test mới dưới `tests/planning/`, tiền tố `test_planning_`. `python -m pytest -q` ở gốc repo -- **không cần OSRM, không cần mạng**: mọi test của plan này tiêm `plan_fixtures`'s `fake_matrix`/`no_geocode`/`fixed_sun`/`fake_lodging` và dùng `corpus.serving` records tổng hợp từ `tests/decision`'s `fixtures.srec`/`feat` (hoặc tương đương), giống hệt cách `tests/decision/test_evaluate.py` đã làm với `decision.evaluate`.
- `python -m planning evaluate` (lệnh thật, không phải test) cần `data/serving/places.json` (`python -m corpus serving`), OSRM local đang chạy (`scripts/osrm_setup.sh` + `osrm-routed`), và tuỳ chọn `gmaps` đã đăng nhập cho crawl chỗ ở thật -- không chạy trong CI, như `build`/`variants`/`lodging` đã không chạy.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| "Mỗi chuyến ẩn ... → Trip Understanding → Place Decision → `confirmed`" | Không chạy qua Trip Understanding's free-text turn -- xây `SearchInput` trực tiếp từ chuyến ẩn (hard/soft/role), y hệt `decision.evaluate.search_input()` đã làm cho phép đo riêng của Decision | `docs/decision`'s evaluate đã chốt chính xác cách đọc này (`config/eval_trips.yaml`'s mục đích từ đầu là "Hidden Trip States", đã ở dạng SearchInput-ready, không phải hội thoại thô); chạy một turn hội thoại giả cho 30 chuyến sẽ cần gọi model that tốn tiền, không tất định, và không đo được gì Planning cần. |
| "`confirmed` của Place Decision" cho mỗi chuyến ẩn | Không có người dùng thật để chọn `confirmed` -- tự động `select` mọi nơi mà pipeline's shortlist xếp vào đúng `role` của chuyến đó (giống hệt `picked` mà `decision.evaluate.evaluate()` đã tính cho phép đo của chính nó), rồi `confirm()` | Đây là lựa chọn hợp lý nhất khi không có người dùng: "chấp nhận shortlist hạng cao nhất" là xấp xỉ gần nhất của một người dùng không phản đối gì. Để lại: nếu sau pilot thấy xấp xỉ này lệch quá xa hành vi thật, thay bằng danh sách `confirmed` tay cho một tập chuyến nhỏ hơn. |
| "Phút di chuyển so với baseline = nearest-neighbour + anchor base, không chọn chỗ ở" | `Engine.baseline_travel_min(sid)`: lấy đúng tập nơi mỗi ngày của phương án đã chọn (`base.variants[i]["_results"]`, luôn neo ở base/entry vì được dựng trước khi chỗ ở crawl xong), xếp lại thứ tự bằng `route._nearest_neighbour` thay vì thứ tự đã tối ưu, đo lại bằng `schedule.simulate` | Tách đúng biến đang đo: giữ nguyên "nơi nào vào ngày nào" (để không lẫn phần "tối ưu cụm/chia ngày" vào phép so sánh), chỉ đổi "thứ tự trong ngày" -- đúng với cụm từ "nearest-neighbour" của spec, vốn là một thuật toán *xếp thứ tự*, không phải một thuật toán chia cụm/chia ngày khác. |
| "Hành vi agent không tất định nên đo bằng mô phỏng nhiều lần... thêm số lần guardrail chặn, số tool-call mỗi lượt, độ trễ mỗi lượt" | **Không làm trong plan này** | `src/decision/evaluate.py` (cùng dòng spec tương ứng ở `PLACE_DECISION.md` §17) cũng chưa làm việc này -- không có hạ tầng mô phỏng hội thoại nhiều lượt nào đã tồn tại trong repo để soi theo, và việc gọi model thật 30+ lần mỗi lần `evaluate` chạy vừa tốn tiền vừa không tất định, không hợp một phép đo CI-safe. Ghi vào Giới hạn đã biết, nhất quán với Decision's cùng khoảng trống. |
| "Số lượt sửa trước `confirm`" | Không báo cáo (không có vòng sửa nào được mô phỏng trong phép đo tự động này) | Hệ quả trực tiếp của dòng trên: không có người dùng mô phỏng nào tạo ra "lượt sửa" để đếm. |

## File Structure

| File | Việc |
|---|---|
| `src/planning/engine.py` | thêm method `Engine.baseline_travel_min(sid) -> int` |
| `src/planning/evaluate.py` | mới: `trips`, `search_input`, `decision_outputs`, `plan_results`, `evaluate`, `run` |
| `src/planning/__main__.py` | thêm subcommand `evaluate` |
| `docs/specs/PLANNING_SPEC.md` | thêm dòng Giới hạn đã biết cho khoảng trống "agent simulation" |
| `README.md` | thêm `python -m planning evaluate` |
| `docs/log/DEV_LOG.md` | thêm mục `## planning` (section đầu tiên của cả phase, chưa từng viết) |
| `tests/planning/test_planning_evaluate.py` | mới |
| `tests/planning/test_planning_engine.py` | thêm test cho `baseline_travel_min` |

---

### Task 1: `Engine.baseline_travel_min`

**Files:**
- Modify: `src/planning/engine.py`
- Test: `tests/planning/test_planning_engine.py` (file exists; add to it)

**Interfaces:**
- Consumes: `self._get`, `self._ensure_base` (already private methods of the same class), `planning.route._nearest_neighbour`, `planning.schedule.simulate` (both already exist, intra-package import).
- Produces: `Engine.baseline_travel_min(sid: str) -> int`. Raises `ActionError` when no variant is chosen yet (same contract as `confirm()`'s own guard).

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_engine.py`:

```python
def test_baseline_travel_min_uses_the_same_day_membership_with_a_naive_order():
    e, sid = started()  # existing helper in this file: small_trip, variant already picked
    base_min = e.baseline_travel_min(sid)
    optimized_min = e.load(sid)["view"]["variants"][0]["metrics"]["travel_min"]
    assert base_min >= optimized_min >= 0  # nearest-neighbour is never better than the exact/heuristic order


def test_baseline_travel_min_without_a_chosen_variant_is_an_error():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.baseline_travel_min(sid)
```

(`started()`, `CFG`, `FakeLive`, `fake_matrix`, `no_geocode`, `fake_lodging`, `small_trip`, `Engine`, `ActionError`, `Store`, `pytest` are all already imported or defined at the top of this test file from earlier tasks -- no new imports needed in the test file itself.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_engine.py -k baseline_travel_min -v`
Expected: FAIL with `AttributeError: 'Engine' object has no attribute 'baseline_travel_min'`

- [ ] **Step 3: Write minimal implementation**

In `src/planning/engine.py`, add after `confirm()`:

```python
    def baseline_travel_min(self, sid: str) -> int:
        """Total travel minutes of the chosen variant's own day membership, laid out by plain nearest-neighbour
        from base/entry (docs/specs/PLANNING_SPEC.md §Đo: "baseline = nearest-neighbour + anchor base, không chọn
        chỗ ở"). base.variants is always built before the lodging crawl (_build_base), so its own `_results` are
        already anchored at base/entry, never at a lodging candidate -- exactly the baseline the spec means."""
        s = self._get(sid)
        base = self._ensure_base(sid)
        if s.state.chosen_variant is None:
            raise ActionError("pick a variant before measuring a baseline")
        from .route import _nearest_neighbour
        from .schedule import simulate
        results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
        return sum(simulate(_nearest_neighbour(list(r.order), cx), cx).travel_min
                  for cx, r in zip(base.trip.ctxs, results))
```

Add `ActionError` to the existing `from .session import ...` import line at the top of `engine.py` if it is not already imported there (check first -- Task 7 of `PLANNING_P7_AGENT.md` did not need it at module scope, but `session.py`'s `ActionError` is already used inside `act()`'s body via a bare `raise ActionError(...)`, so it must already be imported; if the existing import line is `from .session import ActCtx, ActionError, Session, State, Store` this step needs no import change at all).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_engine.py -v`
Expected: PASS, full file green

- [ ] **Step 5: Commit**

```bash
git add src/planning/engine.py tests/planning/test_planning_engine.py
git commit -m "feat(planning): Engine.baseline_travel_min -- the real optimizer-vs-naive comparison"
```

---

### Task 2: `decision_outputs` -- Place Decision in process, for 30 hidden trips

**Files:**
- Create: `src/planning/evaluate.py`
- Test: `tests/planning/test_planning_evaluate.py`

**Interfaces:**
- Consumes: `decision.Data`, `decision.Engine`, `decision.Store`, `decision.load_settings` (all public), `trip.SearchInput`, `corpus.ontology.load`.
- Produces: `trips() -> list[dict]`, `search_input(trip: dict, version: int, days: int = 3) -> SearchInput`, `decision_outputs(records: list[dict], cfg=None) -> list[tuple[str, dict]]` (trip id, Decision Output).

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_planning_evaluate.py`. It needs serving records with enough feature coverage for Decision's pipeline to shortlist something -- reuse `tests/decision/fixtures.py`'s `srec`/`feat` helpers the same way `tests/decision/test_evaluate.py` does (read that file's imports first to copy the exact helper names and signatures; do not guess them):

```python
import pytest

from planning import evaluate as ev


def test_trips_loads_the_shared_eval_trips_yaml():
    t = ev.trips()
    assert len(t) >= 10 and all({"id", "role", "hard", "soft"} <= set(x) for x in t)


def test_search_input_from_a_hidden_trip():
    si = ev.search_input({"id": "x", "role": "experience", "hard": {}, "soft": {"scenic_view": 1.0}}, version=1)
    assert si.soft_weights[0].feature == "scenic_view" and si.context.days == 3


def test_decision_outputs_skips_trips_place_decision_cannot_confirm(monkeypatch):
    from fixtures import srec  # tests/decision/fixtures.py; see note below if this import path is wrong
    monkeypatch.setattr(ev, "trips", lambda: [
        {"id": "nothing_matches", "role": "experience", "hard": {"kids": "unsuitable"}, "soft": {}}])
    recs = [srec("A", usable=("meal",))]  # no "experience" record exists -> Decision cannot fill any experience role
    out = ev.decision_outputs(recs)
    assert out == []
```

If `tests/decision/fixtures.py`'s `srec` is not importable by a bare `from fixtures import srec` from `tests/planning/` (pytest's `rootdir`/`conftest.py` path setup may scope fixture modules per directory), use `tests/planning/plan_fixtures.py`'s own `rec(...)` instead (it already builds a valid serving record dict with the same shape) and check which one actually resolves by running the test -- do not fight `sys.path`; whichever of the two is already importable from `tests/planning/test_planning_engine.py` (check that file's own imports) is the one to use here too, for consistency within the directory.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'planning.evaluate'`

- [ ] **Step 3: Write minimal implementation**

Create `src/planning/evaluate.py`:

```python
"""Offline check of Planning on the serving records (docs/specs/PLANNING_SPEC.md §Đo).

python -m planning evaluate  ->  data/planning/eval.json

Each hidden trip of config/eval_trips.yaml (the same file src/decision/evaluate.py reads) becomes a Search Input,
run through Place Decision in process -- decision.Engine's own public create/act/confirm, no HTTP, no second
server -- into a Decision Output, then through Planning: create, pick the first ok variant, confirm.
"""

import json
import os
import time
from functools import cache
from pathlib import Path

import yaml

from corpus.ontology import load as load_ontology
from decision import Data as DecisionData, Engine as DecisionEngine, Store as DecisionStore
from decision import load_settings as decision_default
from trip import SearchInput

from .engine import Engine
from .session import ActionError, Store
from .settings import ROOT
from .settings import load as load_settings

TRIPS = ROOT / "config" / "eval_trips.yaml"


@cache
def trips() -> list[dict]:
    """The named hidden trips of config/eval_trips.yaml -- not the `cross` combinations that file also builds
    (those exist for Decision's own feature-pass coverage; the 10 named trips already vary enough in hard/soft/role
    for Planning's purposes)."""
    raw = yaml.safe_load(TRIPS.read_text(encoding="utf-8"))
    return list(raw["trips"])


def search_input(trip: dict, version: int, days: int = 3) -> SearchInput:
    """Mirrors decision.evaluate's own (non-public) search_input() -- duplicated, not imported, since
    decision.evaluate is not part of decision's public API (decision/__init__.py)."""
    ont = load_ontology()
    return SearchInput.model_validate({
        "ontology_version": version,
        "context": {"start_date": "2026-12-14", "month": None, "days": days, "base": None, "mobility": "motorbike",
                    "companions": [], "people": 2, "arrive_at": "09:00", "leave_at": "15:00", "day_end": None,
                    "budget_vnd": 3_000_000, "experience": None},
        "hard_filters": [{"feature": f, "op": "ne", "value": v, "unknown_policy": "exclude"}
                         for f, v in trip["hard"].items()],
        "anchors": [],
        "soft_weights": [{"feature": f, "value": ont.features[f].values[0], "context": None, "weight": 1,
                          "source": "user"} for f in trip["soft"]],
        "pace": {"level": "normal", "max_leg_min": None, "crowd_tolerance": None},
        "novelty": {"level": None, "visited": []}, "unknowns": [], "unmapped": []})


def decision_outputs(records: list[dict], cfg=None) -> list[tuple[str, dict]]:
    """(trip id, Decision Output) for every hidden trip Place Decision can actually confirm -- a trip whose
    pipeline shortlist cannot fill its role, or whose feasibility is "partial"/"infeasible", is skipped (not an
    error: it means Place Decision itself found nothing fit, which Planning has nothing to schedule)."""
    cfg = cfg or decision_default()
    data = DecisionData(records)
    version = load_ontology().version
    out = []
    for trip in trips():
        eng = DecisionEngine(data, cfg, DecisionStore(None))  # a fresh Engine per trip: no session state to leak
        si = search_input(trip, version)
        created = eng.create(si.model_dump(mode="json"))
        sid = created["id"]
        picked = [c["id"] for g in created["view"]["groups"] if g["id"] != "anchors" for c in g["cards"]
                 if c["role"] == trip["role"]]
        for pid in picked:
            eng.act(sid, {"type": "select", "place_id": pid})
        try:
            confirmed = eng.confirm(sid)
        except Exception:  # decision.NotConfirmable is not part of decision's public API; catch broadly on purpose
            continue
        out.append((trip["id"], confirmed))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/planning/evaluate.py tests/planning/test_planning_evaluate.py
git commit -m "feat(planning): evaluate -- hidden trips through Place Decision, in process"
```

---

### Task 3: `plan_results` -- one trip through Planning

**Files:**
- Modify: `src/planning/evaluate.py`
- Modify: `tests/planning/test_planning_evaluate.py`

**Interfaces:**
- Produces: `plan_results(decision_output: dict, records: list[dict], planning_cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict` -- one row: `{ok, ms_variants, ms_total, travel_min, baseline_travel_min, lodging_saved_min_per_day, robustness}` when `ok`, else `{ok: False, ms_variants, reason}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_evaluate.py` (reuse `plan_fixtures`, already proven in `tests/planning/test_planning_engine.py`):

```python
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip


def test_plan_results_measures_a_confirmable_decision_output():
    d, recs = sample_trip(budget=5_000_000)
    row = ev.plan_results(d, recs, planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode,
                          matrix_fn=fake_matrix, sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging)
    assert row["ok"] and row["travel_min"] <= row["baseline_travel_min"]
    assert row["robustness"] in ("Vững", "Khả thi", "Mong manh")
    assert row["ms_variants"] >= 0 and row["ms_total"] >= row["ms_variants"]
    assert row["lodging_saved_min_per_day"] >= 0  # the best candidate is never worse than no lodging at all


def test_plan_results_reports_not_ok_when_no_variant_is_feasible():
    from plan_fixtures import decision
    d = decision(["ghost"])  # a place id with no matching record -> build_places drops it, nothing left to schedule
    row = ev.plan_results(d, [], planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                          sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging)
    assert row == {"ok": False, "ms_variants": pytest.approx(row["ms_variants"], abs=10_000), "reason": "no_valid_variant"}
```

Note on the second test: the exact `reason` string must match whatever `base.back_to_decision["reason"]` actually contains for this input (`_build_base` sets it to `"no_valid_variant"` when `variants` ends up empty -- confirmed by reading `src/planning/engine.py`'s `_build_base`). If a fresh read of that method at implementation time shows a different literal, use that literal instead of guessing from this plan text.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: FAIL with `AttributeError: module 'planning.evaluate' has no attribute 'plan_results'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/planning/evaluate.py`:

```python
def plan_results(decision_output: dict, records: list[dict], planning_cfg=None, live_cfg=None, geocode_fn=None,
                 matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict:
    """One hidden trip's Decision Output, laid out and measured. background=False: the lodging crawl (itself
    offline/fixture-driven in tests, real in run()) finishes before create() returns, so ms_total below already
    includes it -- matching docs/specs/PLANNING_SPEC.md §Đo's "Độ trễ: dựng 21 phương án · crawl chỗ ở"."""
    eng = Engine(records, cfg=planning_cfg, live_cfg=live_cfg, store=Store(None), geocode_fn=geocode_fn,
                matrix_fn=matrix_fn, sun_fn=sun_fn, lodging_fn=lodging_fn, route_fn=route_fn, background=False)
    t0 = time.perf_counter()
    created = eng.create(decision_output)
    ms_variants = round((time.perf_counter() - t0) * 1000)
    view = created["view"]
    if not view["ok"]:
        return {"ok": False, "ms_variants": ms_variants, "reason": (view["back_to_decision"] or {}).get("reason")}
    sid = created["id"]
    variant = view["variants"][0]
    travel_no_lodging = variant["metrics"]["travel_min"]
    eng.act(sid, {"type": "pick_variant", "id": variant["id"]})
    # Try every candidate, remember the best one's id -- `pick_lodging` on the next candidate overwrites the
    # previous pick, so the loop itself never leaves the session on the best choice; that happens explicitly after.
    best_travel, best_id = travel_no_lodging, None
    for c in eng.lodging(sid)["candidates"]:
        eng.act(sid, {"type": "pick_lodging", "id": c["id"]})
        total = sum(d["travel_min"] for d in eng.load(sid)["view"]["travel_load"])
        if total < best_travel:
            best_travel, best_id = total, c["id"]
    if best_id is not None:
        eng.act(sid, {"type": "pick_lodging", "id": best_id})
    else:
        eng.act(sid, {"type": "clear_lodging"})
    ms_total = round((time.perf_counter() - t0) * 1000)
    baseline = eng.baseline_travel_min(sid)
    try:
        out = eng.confirm(sid)
    except Exception as e:
        return {"ok": False, "ms_variants": ms_variants, "ms_total": ms_total, "reason": str(e)}
    nights = max((decision_output["trip_context"]["context"].get("days") or 1) - 1, 0)
    saved_per_day = (travel_no_lodging - best_travel) / max(nights, 1)
    return {"ok": True, "ms_variants": ms_variants, "ms_total": ms_total, "travel_min": best_travel,
           "baseline_travel_min": baseline, "lodging_saved_min_per_day": round(saved_per_day, 1),
           "robustness": out["robustness"]["level"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: PASS. If the "not ok" test's literal `reason` string mismatches, fix the test's expected string to match `_build_base`'s real one (see the note in Step 1) -- do not change `plan_results` to produce a different string just to satisfy a guessed literal.

- [ ] **Step 5: Commit**

```bash
git add src/planning/evaluate.py tests/planning/test_planning_evaluate.py
git commit -m "feat(planning): plan_results -- lay out, measure against baseline, pick the best lodging"
```

---

### Task 4: `evaluate` / `run`, CLI wiring

**Files:**
- Modify: `src/planning/evaluate.py`
- Modify: `src/planning/__main__.py`
- Modify: `tests/planning/test_planning_evaluate.py`

**Interfaces:**
- Produces: `evaluate(records=None, decision_cfg=None, planning_cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict` (summary + per-trip rows), `run() -> dict` (CLI entry, real data/live defaults, writes `data/planning/eval.json`).

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_planning_evaluate.py`:

```python
def test_evaluate_summarizes_every_confirmable_trip(monkeypatch):
    d, recs = sample_trip(budget=5_000_000)
    monkeypatch.setattr(ev, "decision_outputs", lambda records, cfg=None: [("t1", d), ("t2", d)])
    res = ev.evaluate(recs, planning_cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                      sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging)
    assert res["summary"]["trips"] == 2 and res["summary"]["ok"] == 2
    assert res["summary"]["avg_saved_vs_baseline_pct"] >= 0
    assert set(res["summary"]["robustness"]) <= {"Vững", "Khả thi", "Mong manh"}
    assert len(res["trips"]) == 2 and res["trips"][0]["trip"] == "t1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: FAIL with `AttributeError: module 'planning.evaluate' has no attribute 'evaluate'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/planning/evaluate.py`:

```python
def evaluate(records: list[dict] | None = None, decision_cfg=None, planning_cfg=None, live_cfg=None,
            geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, route_fn=None) -> dict:
    from corpus.serving import load as load_serving
    records = records if records is not None else load_serving()
    rows = []
    for trip_id, decision_output in decision_outputs(records, decision_cfg):
        row = plan_results(decision_output, records, planning_cfg, live_cfg, geocode_fn, matrix_fn, sun_fn,
                           lodging_fn, route_fn)
        rows.append({"trip": trip_id, **row})
    ok_rows = [r for r in rows if r["ok"]]
    n = len(rows)

    def pct_saved(r):
        return 0.0 if r["baseline_travel_min"] == 0 else 100 * (1 - r["travel_min"] / r["baseline_travel_min"])

    summary = {
        "trips": n, "ok": len(ok_rows),
        "feasible_itinerary_rate": round(len(ok_rows) / n, 3) if n else 0.0,
        "avg_saved_vs_baseline_pct": round(sum(pct_saved(r) for r in ok_rows) / len(ok_rows), 1) if ok_rows else 0.0,
        "avg_lodging_saved_min_per_day": round(sum(r["lodging_saved_min_per_day"] for r in ok_rows) / len(ok_rows), 1)
                                        if ok_rows else 0.0,
        "robustness": {lv: sum(1 for r in ok_rows if r["robustness"] == lv)
                      for lv in ("Vững", "Khả thi", "Mong manh")},
        "ms_total_max": max((r.get("ms_total", 0) for r in rows), default=0),
        "not_ok_trips": [r["trip"] for r in rows if not r["ok"]],
    }
    return {"summary": summary, "trips": rows}


def run() -> dict:
    import live
    res = evaluate(matrix_fn=None, geocode_fn=None, sun_fn=None, lodging_fn=None, route_fn=None,
                   live_cfg=live.load_settings())
    d = Path(os.environ.get("DATA_DIR", "data"))
    out = (d if d.is_absolute() else ROOT / d) / "planning" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evaluate: {json.dumps(res['summary'], ensure_ascii=False)}")
    return res
```

Note: passing `matrix_fn=None` etc. to `evaluate()` and down into `Engine(...)` relies on `Engine.__init__`'s own defaults (`self.lodging_fn = lodging_fn or live.lodging_near`, `self.route_fn = route_fn or live.route_shape`) for `lodging_fn`/`route_fn`; `geocode_fn`/`matrix_fn`/`sun_fn` being `None` is also already handled inside `build.prepare` (check `src/planning/build.py`'s `prepare()` signature -- it already falls back to `live.geocode`/`live.travel_matrix`/`live.sun_times` when these are `None`, the same way `python -m planning build` leaves them unset). This is exactly why `run()` need not pass real functions explicitly: the defaults already are the real `live.*` calls.

In `src/planning/__main__.py`, add the subcommand:

```python
    ev = sub.add_parser("evaluate", help="offline Planning check: 30 hidden trips through Decision and Planning")
```

right after the existing `l = sub.add_parser("lodging", ...)` block's arguments, and in `main()`'s dispatch, before `sys.stdout.reconfigure(...)`:

```python
    if args.cmd == "evaluate":
        from .evaluate import run as run_evaluate
        run_evaluate()
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planning/test_planning_evaluate.py -v`
Expected: PASS

- [ ] **Step 5: Manual smoke check of the CLI wiring (not of the live run itself)**

Run: `python -m planning evaluate --help` is not meaningful (no args), so instead run: `python -c "from planning.__main__ import main; main(['evaluate'])"` **only if** `data/serving/places.json` and a running OSRM are available locally; otherwise confirm by reading the dispatch code that `args.cmd == "evaluate"` is reached before the `decision_output` / `load_records()` lines that the `build`/`variants`/`lodging` branches need (those would crash with no CLI argument, since `evaluate` takes none) -- this is a static check of `main()`'s branch order, not a run.

- [ ] **Step 6: Commit**

```bash
git add src/planning/evaluate.py src/planning/__main__.py tests/planning/test_planning_evaluate.py
git commit -m "feat(planning): evaluate aggregation + python -m planning evaluate"
```

---

### Task 5: Spec's known limitations, README, DEV_LOG

**Files:**
- Modify: `docs/specs/PLANNING_SPEC.md`
- Modify: `README.md`
- Modify: `docs/log/DEV_LOG.md`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Record the agent-simulation gap in the spec**

Append to `docs/specs/PLANNING_SPEC.md`'s §Giới hạn đã biết:

```markdown
- `python -m planning evaluate` đo lịch dựng được (feasible rate, phút tiết kiệm so với baseline, chỗ ở tiết kiệm
bao nhiêu, Vững/Khả thi/Mong manh, độ trễ) nhưng **không** mô phỏng hội thoại nhiều lượt với agent thật -- "số lần
guardrail chặn, số tool-call mỗi lượt, độ trễ mỗi lượt" (§Đo) chưa đo được, giống khoảng trống tương ứng ở
`src/decision/evaluate.py`. `confirmed` của mỗi chuyến ẩn trong phép đo này là shortlist hạng cao nhất tự động
chấp nhận (không có người dùng thật chọn/bỏ), nên số liệu phản ánh "Planning có xếp được thứ Decision xếp hạng cao
không", không phản ánh một phiên sửa thật.
```

- [ ] **Step 2: README**

In `README.md`, extend the line that currently ends with `...; cần Chrome đã đăng nhập \`gmaps\` (\`python -m corpus login gmaps\`) và OSRM đang chạy.` (step 7, the Planning line) with one more sentence:

```markdown
Đo trên 30 chuyến ẩn giống Place Decision, qua cả hai bước (Decision → Planning): `python -m planning evaluate` → `data/planning/eval.json` (cần OSRM đang chạy; không chạy trong CI).
```

- [ ] **Step 3: DEV_LOG**

`docs/log/DEV_LOG.md` has no `## planning` section yet despite P1/P3-P8 being built and committed -- this is the first write-up for the whole phase. Add a new section, placed alphabetically/thematically next to `## corpus-serving` and the other module sections (match the file's existing section order by reading its table of contents / heading list first), in the same format every other module uses:

```markdown
## planning — Lịch trình từ Decision Output tới Plan Output

- file: `src/live/` (`cache.py`, `osrm/`, `weather/`, `lodging/`, `geocode/`, `sun.py`, `holidays.py`), `src/planning/` (toàn bộ), `config/planning.yaml`, `config/live.yaml`, `config/climate.yaml`, `config/holidays.yaml`, `tests/live/`, `tests/planning/`
- cách kiểm chứng: `python -m pytest -q tests/live tests/planning`; `python -m planning build|variants|lodging <decision_output.json>`; `python -m planning serve` (web qua `/api/planning`); `python -m planning evaluate` (cần OSRM, không trong CI)

### Hiện tại (2026-10-03)
- hành vi: từ `confirmed` của Place Decision, dựng 2-3 phương án theo mục tiêu (`least_travel`, `low_cost`,
`weather_robust`, `diverse`, `preference_fit`), mỗi phương án đã qua gom cụm (`cluster.py`), chia ngày bằng DP
(`days.py`), xếp thứ tự trong ngày (vét cạn ≤ `exact_n`, nearest-neighbour + 2-opt/or-opt khi đông hơn, `route.py`),
khớp giờ mở / đệm / nghỉ (`schedule.py`), kiểm fail-closed (`validate.py`). Chỗ ở tra live qua mặt "Khách sạn" của
Maps (`src/live/lodging`, dùng lại `corpus.crawl`), cạnh tranh làm neo đầu/cuối ngày cho K ứng viên, không bao giờ
vào Place Intelligence. Thời gian di chuyển qua OSRM local (`src/live/osrm`), rơi về ước lượng thô khi OSRM lỗi,
trần "Khả thi" khi đó. Độ vững 3 mức từ nhiễu cố định (trễ, visit dài hơn, mưa theo xác suất dự báo). Phiên có
undo/redo thật, `act` tất định (chip) và `turn` (gõ chữ, một call agent/lượt, `guard.py` chặn số/alias bịa, rơi về
`policy.py` từ khoá khi agent lỗi/timeout) đều chạy qua cùng một đường `repair_day`/`relayout` nên không xáo lịch
âm thầm. `python -m planning evaluate` trên 30 chuyến ẩn giống Place Decision: xem kết quả thật trong
`data/planning/eval.json` sau khi chạy (số liệu thay đổi theo serving records hiện tại, không chốt cứng ở đây).
Web: `Itinerary.tsx` gọi thẳng phiên Planning thật, `planner.ts` (ước lượng client cũ) chỉ còn dùng cho màn debug
của admin.
- giới hạn: chưa mô phỏng agent nhiều lượt trong `evaluate`; `lodging_near` qua câu nói chưa tìm lại K ứng viên
quanh tâm mới; "bỏ nhiều nơi qua nhiều lượt" chỉ nhắc ở kênh gõ chữ, chưa chặn ở chip. Xem đầy đủ ở
`docs/specs/PLANNING_SPEC.md` §Giới hạn đã biết.

### Trước đó
_không có_
```

(The exact measured numbers from a real `python -m planning evaluate` run are deliberately left out of this entry -- they depend on whatever `data/serving/places.json` contains at run time, which changes as the corpus grows; stating a number here would go stale immediately and nobody would come back to fix it. If the person running this task has already run `evaluate` for real and wants the actual numbers recorded, add one more sentence with the `summary` dict's contents and today's date.)

- [ ] **Step 4: Commit**

```bash
git add docs/specs/PLANNING_SPEC.md README.md docs/log/DEV_LOG.md
git commit -m "docs: record Planning's evaluate gap, README command, and its first DEV_LOG entry"
```

---

### Task 6: Full suite, self-review

**Files:** none (verification only).

- [ ] **Step 1: Run everything**

Run: `python -m pytest -q` at repo root.
Expected: PASS, no regressions in `tests/decision`, `tests/trip`, `tests/corpus`, `tests/live`, `tests/planning`.

- [ ] **Step 2: Self-review against the spec**

Re-read `docs/specs/PLANNING_SPEC.md`'s §Đo table with this plan's Task 3/4 code open side by side. Confirm every row has a home:
- Hard constraint violation: structurally 0 -- `confirm()` only returns when `validate()` is `ok` (unchanged since P3); `plan_results` never reports a row as `ok: True` without having gone through it.
- Unsupported claim rate: out of scope here, see Task 5's spec note.
- Feasible itinerary rate: `summary["feasible_itinerary_rate"]`.
- Vững/Khả thi/Mong manh: `summary["robustness"]`.
- Phút di chuyển so với baseline: `summary["avg_saved_vs_baseline_pct"]`, per trip in `row["baseline_travel_min"]`/`row["travel_min"]`.
- Chỗ ở giảm bao nhiêu phút/ngày: `summary["avg_lodging_saved_min_per_day"]`.
- Số lượt sửa trước confirm: out of scope (no simulated user turns).
- Độ trễ: `row["ms_variants"]`/`row["ms_total"]`, `summary["ms_total_max"]`.

- [ ] **Step 3: Commit (only if Step 1 or 2 required a fix)**

If everything already passed and no fix was needed, there is nothing to commit for this task.
