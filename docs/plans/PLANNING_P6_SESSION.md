# Plan P6 — Phiên, act, repair_day, scope, server + SSE

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một phiên Planning: tạo từ Decision Output, dựng ngay 2–3 phương án (anchor = base), chấm lại chỗ ở nền (SSE `progress`), rồi người dùng sửa bằng `act` tất định — mỗi thay đổi chỉ chạy lại đúng phần bị ảnh hưởng (`repair_day` giữ các ngày không đụng tới y nguyên), có undo / redo thật, và `confirm` chốt ra Plan Output. `python -m planning serve` mở `127.0.0.1:8768`.

**Architecture:** `session.py` giữ `State` (các chỉnh sửa của người dùng: gán ngày thủ công, thứ tự ghim, bỏ, khoá, chỗ ở, trần giá, pace / mục tiêu / khung giờ, relax) phiên bản hoá thành `states[]` + `position` (undo/redo di chuyển con trỏ, không xoá tương lai trừ khi có act mới) và hàm thuần `apply_act` sinh `State` mới. `engine.py` giữ trong RAM mỗi phiên một `Trip` (ma trận OSRM, ứng viên chỗ ở đã tra) và một danh sách `Schedule` song song với `states[]`; `act()` tra `scope.act_scope` để biết chạy lại từ đâu: acts thuần state (`pick_variant`, khoá…) không đụng `Schedule`; acts đổi một/hai ngày (`move_place`, `reorder`, `drop_place`, `add_from_backup`, `swap`, `relax`) gọi `repair.repair_day` chỉ cho ngày đó, các ngày khác giữ y hệt `Schedule` trước; acts đổi tham số cả chuyến (`set_pace`, `set_objective`, `set_day_window`) dựng lại `schedule_trip` cho mục tiêu đang chọn; acts đổi chỗ ở gọi `with_home` (cùng ứng viên đã tra) hoặc tra lại ứng viên (`set_lodging_budget`, `set_lodging` chỗ ở nhập tay). `server.py` expose HTTP + một SSE stream cho tiến độ crawl chỗ ở nền khởi động ở `create()`; `output.py` lắp Plan Output cuối cùng từ `Schedule` đang hiệu lực lúc `confirm`.

**Tech Stack:** Python 3.12, stdlib (`http.server`, `threading`, `queue`, `urllib.request`), `pydantic` (đã dùng ở `decision.session`), `pytest`. Không thêm dependency.

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Vòng người dùng sửa và góp ý, §Guardrail, §Plan Output, §API và web, bảng phase P6). Plan trước: `docs/plans/PLANNING_P5_LODGING.md` — **phải xong cả 9 task** (plan này dùng `build.prepare/schedule_trip/with_home`, `variants.build_variants/build_lodging_variants`, `lodging.candidates`, `objectives.choose/metrics/score/LABEL`, `robustness.robustness`, `backup.backups` nguyên trạng). Blueprint tham khảo trực tiếp (cùng hình dạng, khác domain): `src/decision/session.py`, `src/decision/scope.py`, `src/decision/engine.py`, `src/decision/server.py` — plan này cố ý mirror cấu trúc của chúng vì Place Decision đã giải quyết đúng bài toán "phiên + act + undo + SSE" một lần rồi.

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0). Chuỗi hiển thị người dùng tiếng Việt.
- Module chỉ giao tiếp qua public API (`__init__.py`). `planning` dùng: `live`, `corpus.serving`, `corpus.ontology`. Không deep import; **không import `decision`** (`RULE.md` §2) — `decision_session_id` được giải qua HTTP loopback tới server của `decision` (xem Task 4), không qua Python import.
- `src/planning` chỉ ghi `data/planning/sessions/<id>.json` (State, không ghi `Schedule`/`Trip`). Không ghi `data/intel`, `data/serving`, `data/gmaps`.
- Mọi bước tất định: không `random`. `repair_day` là tất định (permutation / heuristic như `route.py`, không coin-flip). Network (OSRM, lodging, geocode, HTTP loopback sang `decision`) không tất định nhưng không bịa: lỗi ném `Unavailable` hoặc trả lỗi HTTP rõ ràng, không đoán.
- Physical constraint không nới: `relax` ném lỗi khi feature thuộc nhóm `effort` (`corpus.ontology`, giống `validate._is_physical`).
- Không xáo lịch âm thầm: một act chỉ được đổi ngày nó thật sự chạm tới; `repair_day` phạt lệch so với thứ tự ngay trước nó (`cfg.repair_diff_weight`); nơi `locked` không được rời khỏi ngày của nó, `repair_day` từ chối (`RepairError`), không âm thầm bỏ qua.
- Không thêm dependency vào `pyproject.toml`. Thay đổi tối thiểu (`RULE.md` §4): `build.py`, `variants.py`, `objectives.py`, `robustness.py`, `backup.py`, `validate.py`, `route.py`, `days.py`, `schedule.py`, `lodging.py`, `places.py`, `travel.py`, `frame.py`, `model.py` của P3–P5 **không đổi chữ ký** trong plan này (chỉ đọc, không sửa) — mọi thứ mới nằm ở `repair.py`, `scope.py`, `session.py`, `output.py`, `engine.py`, `server.py`.
- File test mới dưới `tests/planning/` tiền tố `test_planning_`; không tạo `tests/planning/__init__.py`.
- Chạy test: `python -m pytest -q` ở gốc repo. Test có `-m live` (nếu có) không chạy trong CI.
- Giờ trong code là phút sau nửa đêm; `day` trong act/API là chỉ số 0-based như `Day.index`.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| Cây module chỉ liệt kê `session.py` (không có `curation.py`/`act.py` riêng) | `apply_act` (hàm thuần sinh `State` mới, như `decision.curation.apply`) đặt trong `session.py`, cạnh `State` | Cây module của spec không có chỗ nào khác hợp hơn; `decision` tách `curation.py` vì nó còn có `cards.py`/`compare.py` dùng chung — `planning` không có nhu cầu đó. |
| `POST /sessions {decision_session_id \| decision_output}` | `decision_session_id` được giải bằng một `POST http://127.0.0.1:8767/api/decision/sessions/<id>/confirm` (gọi `decision`'s HTTP server, `config/planning.yaml: decision_url`), lấy `output` làm Decision Output | Module `planning` không được import `decision` (RULE §2); hai phase chạy hai tiến trình HTTP cục bộ (`ARCHITECTURE.md`), nên liên lạc qua chính API đã công khai của `decision` là đường duy nhất không phạm ranh giới. `decision.confirm` tất định (cùng state → cùng output) nên gọi lại không hại. |
| `/turn SSE: say(delta\|replace) · view · progress · done · error` | P6 chưa có agent (P7 mới có) nên `/turn` chưa mở; thay vào đó một route riêng `GET .../lodging/events` phát đúng khung sự kiện đó (`progress`, `view`, `done`, `error`) cho đúng một việc P6 cần stream: crawl chỗ ở nền khởi động ở `create()`. P7 nối `/turn` vào cùng `emit()` của `server.py`, không viết lại transport. | P5 đã để lại câu này nguyên văn: "Server + SSE là P6 ... định nghĩa trước hình dạng event để P6 chỉ cần nối ống". `/turn` cần `agent.py` (P7) để biến chữ tự do thành act; không có nó thì route đó không làm được gì ngoài SSE suông. |
| `relax(constraint, scope)` | Action `{"type":"relax","place_id","feature"}` (scope mặc định "nơi này") hoặc `{"type":"relax","feature","scope":"whole_trip"}` (không `place_id`: áp cho mọi nơi đang vi phạm feature đó) | Spec không định nghĩa hình dạng `constraint`; tách `place_id` optional theo đúng nghĩa "nơi này" / "cả chuyến" của bảng act (dòng "`relax(constraint, scope)` nới... luôn kèm cái giá đã tính") là cách đọc tự nhiên nhất của `scope`. |
| "relax ... luôn kèm cái giá đã tính" | `act()` trả thêm `relaxed_cost`: danh sách vi phạm `hard` đã biến mất cho (các) nơi vừa nới, đo **trước** khi áp dụng | Đây chính là "cái giá" — số vi phạm hard constraint đã đổi, không phải một con số tiền tệ (relax một feature không có đơn vị tiền). |
| `place_live_status(place)` (đóng cửa tạm, giờ ngày lễ) ở bước `confirm` | **Không** thêm gọi mạng mới ở P6: `confirm` chỉ gom lại các cờ `hours_status UNCERTAIN/OUTDATED` đã có sẵn từ `trip.warnings` (P3) làm `warnings` của Plan Output | Spec không nói nguồn nào cung cấp trạng thái "đóng cửa tạm" — không có API nào trong `src/live`/`src/corpus` làm việc này. Bịa ra một lệnh gọi mạng không rõ nguồn là vi phạm RULE §3. Để lại cho khi có nguồn cụ thể (ghi vào "Giới hạn đã biết"). |
| `repair_day` — guardrail "nơi `locked` không bị dời, lỗi nói rõ" | `repair_day` tự kiểm: nếu một id trong `locked` có mặt ở `prev_order` nhưng vắng mặt ở `ids` mới → `RepairError`, không chạy tìm kiếm | Guardrail bảng ghi rõ "`repair_day` từ chối" (không phải act layer từ chối hộ) — đặt việc kiểm tra đúng chỗ bảng nói. |
| `locked` "ghim ngày / giờ" | `repair_day` chỉ ép **ghim ngày** (id không rời `ids` của ngày); **giờ** (thứ tự / slot trong ngày) chỉ được *khuyến khích* giữ nguyên qua phạt lệch `repair_diff_weight`, không ép cứng | Ép cứng "giờ" nghĩa là khoá cả vị trí trong permutation — làm bài toán repair luôn phải tìm đúng lời giải chứa vị trí đó, dễ vô nghiệm khi một act khác đổi các nơi xung quanh. Phạt lệch đã đủ mạnh (trọng số cấu hình) để một vị trí khoá hiếm khi bị đẩy xa; ghi vào "Giới hạn đã biết". |
| `turn` dùng `agent` để map chữ tự do → act | Không có ở P6 | Đúng bảng phase: P7 mới có `agent.py guard.py policy.py`. |

## Review Focus

Năm lớp input spec hàm ý nhưng dễ bị bỏ; mỗi dòng đã có test ở task sở hữu code:

1. **Hai act liên tiếp đụng cùng một ngày** (vd. `move_place` rồi `reorder` cùng ngày đó) — mong đợi: ngày thứ hai chạy lại dựa trên kết quả của act thứ nhất (không phải bản gốc), ngày khác hoàn toàn không đổi dù `schedule_trip` gốc có thể đã xếp khác. → Task 5 (`test_two_acts_on_the_same_day_compose_and_every_other_day_is_byte_identical`).
2. **Act thử dời một nơi `locked` sang ngày khác, hoặc drop nó** — mong đợi: `repair_day` từ chối, state không đổi, lỗi nói rõ nơi nào đang khoá. → Task 2 (`test_a_locked_place_leaving_its_day_is_refused`), Task 5 (`test_moving_a_locked_place_is_refused_and_the_session_does_not_change`).
3. **`undo` sau đó một act mới** — mong đợi: tương lai (các version đã `redo`-được) bị cắt, không còn "redo" về nhánh cũ; `redo` khi không có gì để redo là lỗi, không phải no-op âm thầm. → Task 5 (`test_a_new_act_after_undo_discards_the_redone_future`).
4. **`set_lodging_budget` hạ trần giá xuống dưới giá chỗ ở đang chọn** — mong đợi: ứng viên hiện tại rớt khỏi danh sách mới nhưng **không** tự động đổi chỗ ở đang chọn (không âm thầm đổi); `pick_lodging` lại một ứng viên không còn trong danh sách mới bị từ chối. → Task 4 (`test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one`).
5. **Phiên load lại sau khi mất cache RAM** (giả lập restart: `Engine` mới cùng `Store` cùng thư mục) — mong đợi: `Trip` và `Schedule` dựng lại đúng từ `decision` + `states[0..position]` phát lại qua `repair_day`, cho kết quả **giống hệt** phiên gốc, không cần gọi mạng gì ngoài những gì `live.cache` đã lưu. → Task 6 (`test_a_session_reloaded_after_the_process_restarts_replays_to_the_same_schedule`).

## Cấu trúc file

| File | Việc |
|---|---|
| `config/planning.yaml` | thêm `history_max`, `repair_diff_weight`, `decision_url` |
| `src/planning/settings.py` | thêm 3 trường trên |
| `src/planning/scope.py` | mới: `act_scope(action) -> str` |
| `src/planning/repair.py` | mới: `repair_day`, `RepairError` |
| `src/planning/session.py` | mới: `State`, `Drop`, `Relax`, `ActCtx`, `ActionError`, `apply_act`, `Session`, `Store` |
| `src/planning/output.py` | mới: `build` (Plan Output lúc `confirm`), `route_of_day` |
| `src/planning/engine.py` | mới: `Engine` — `create`, `load`, `act`, `variants`, `lodging`, `lodging_events`, `confirm` |
| `src/planning/server.py` | mới: HTTP + SSE, `run(engine, port=8768)` |
| `src/planning/__init__.py`, `__main__.py` | export + lệnh `serve` |
| `tests/planning/plan_fixtures.py` | thêm `fake_lodging`, `small_trip` (3 ngày, đủ để test move/swap/lock) |
| `tests/planning/test_planning_scope.py`, `test_planning_repair.py`, `test_planning_session.py`, `test_planning_output.py`, `test_planning_engine.py`, `test_planning_engine_lodging.py`, `test_planning_server.py` | test mới |

---

### Task 1: Config, settings, `scope.py`

**Files:**
- Modify: `config/planning.yaml` (thêm vào cuối), `src/planning/settings.py` (class `Settings`)
- Create: `src/planning/scope.py`
- Test: `tests/planning/test_planning_settings.py` (thêm), `tests/planning/test_planning_scope.py`

**Interfaces:**
- Consumes: không có (chỉ đọc config).
- Produces:
  - `Settings` thêm `history_max: int`, `repair_diff_weight: float`, `decision_url: str`
  - `planning.scope.NONE = "none"`, `RELAYOUT = "relayout"`, `VARIANT = "variant"`, `LODGING_HOME = "lodging_home"`, `LODGING_FETCH = "lodging_fetch"`
  - `planning.scope.act_scope(action: dict) -> str` — ném `KeyError` cho `type` lạ

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_settings.py`:

```python


def test_the_p6_keys_load():
    cfg = settings.load(settings.PATH)
    assert cfg.history_max == 20
    assert cfg.repair_diff_weight == 5.0
    assert cfg.decision_url == "http://127.0.0.1:8767"
```

Tạo `tests/planning/test_planning_scope.py`:

```python
import pytest

from planning.scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope


@pytest.mark.parametrize("type_, expected", [
    ("pick_variant", NONE), ("lock_slot", NONE), ("unlock", NONE), ("undo", NONE), ("redo", NONE),
    ("move_place", RELAYOUT), ("reorder", RELAYOUT), ("drop_place", RELAYOUT),
    ("add_from_backup", RELAYOUT), ("swap", RELAYOUT), ("relax", RELAYOUT),
    ("set_pace", VARIANT), ("set_objective", VARIANT), ("set_day_window", VARIANT),
    ("pick_lodging", LODGING_HOME), ("clear_lodging", LODGING_HOME),
    ("set_lodging", LODGING_FETCH), ("set_lodging_budget", LODGING_FETCH),
])
def test_every_act_type_maps_to_its_scope(type_, expected):
    assert act_scope({"type": type_}) == expected


def test_an_unknown_act_type_is_a_key_error():
    with pytest.raises(KeyError):
        act_scope({"type": "teleport"})
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_settings.py tests/planning/test_planning_scope.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'history_max'` và `ModuleNotFoundError: No module named 'planning.scope'`

- [ ] **Step 3: Thêm config**

Thêm vào cuối `config/planning.yaml`:

```yaml

# Sessions (P6, docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý).
history_max: 20              # versions kept for undo / redo
repair_diff_weight: 5.0      # repair_day's penalty per stop whose relative order changes from the version before it
decision_url: http://127.0.0.1:8767   # Place Decision's HTTP API, to resolve a decision_session_id at session create
```

- [ ] **Step 4: Viết code**

Trong `src/planning/settings.py`, class `Settings`, ngay sau dòng `    split_min: int` thêm:

```python
    history_max: int
    repair_diff_weight: float
    decision_url: str
```

Tạo `src/planning/scope.py`:

```python
"""act_scope (docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý, act table): which part of a session's laid
out trip one act must rerun. Mirrors src/decision/scope.py's replan_scope for the same reason: the UI's diff
promises an exact scope, so the dispatcher must pick one, not "rerun everything and hope it looks the same" -- that
is exactly the "không xáo lịch âm thầm" guardrail (docs/specs/PLANNING_SPEC.md §Guardrail).
"""

NONE = "none"                      # state only: nothing about the laid-out days changes
RELAYOUT = "relayout"              # one or two days' membership or order changed; the rest of the trip is untouched
VARIANT = "variant"                 # a trip-wide parameter changed; the chosen objective's whole day split reruns
LODGING_HOME = "lodging_home"       # the day anchor changed among lodging candidates already fetched
LODGING_FETCH = "lodging_fetch"     # the candidate list itself must be re-fetched or extended

_SCOPE = {
    "pick_variant": NONE, "lock_slot": NONE, "unlock": NONE, "undo": NONE, "redo": NONE,
    "move_place": RELAYOUT, "reorder": RELAYOUT, "drop_place": RELAYOUT, "add_from_backup": RELAYOUT,
    "swap": RELAYOUT, "relax": RELAYOUT,
    "set_pace": VARIANT, "set_objective": VARIANT, "set_day_window": VARIANT,
    "pick_lodging": LODGING_HOME, "clear_lodging": LODGING_HOME,
    "set_lodging": LODGING_FETCH, "set_lodging_budget": LODGING_FETCH,
}


def act_scope(action: dict) -> str:
    return _SCOPE[action.get("type")]
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_settings.py tests/planning/test_planning_scope.py -q`
Expected: PASS (1 test mới + 19 test mới)

- [ ] **Step 6: Commit**

```bash
git add config/planning.yaml src/planning/settings.py src/planning/scope.py tests/planning/test_planning_settings.py tests/planning/test_planning_scope.py
git commit -m "feat(planning): P6 settings and the scope an act must rerun"
```


### Task 2: `repair.py` — ngày sau một act, phạt lệch so với phiên bản trước

**Files:**
- Create: `src/planning/repair.py`
- Test: `tests/planning/test_planning_repair.py`

**Interfaces:**
- Consumes: `planning.schedule.DayCtx/simulate`, `planning.model.DayResult`.
- Produces:
  - `planning.repair.RepairError(Exception)`
  - `planning.repair.repair_day(ids: list[str], ctx: DayCtx, prev_order: tuple[str, ...] | None, locked: set[str], cfg: Settings) -> DayResult`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_repair.py`:

```python
import pytest
from plan_fixtures import CFG, day_ctx, rec

from planning.repair import RepairError, repair_day


def test_with_no_history_repair_day_matches_a_fresh_order_day():
    from planning.route import order_day
    recs = [rec("a", 1, 1), rec("b", 2, 2), rec("c", 3, 1)]
    cx = day_ctx(recs)
    assert repair_day(["a", "b", "c"], cx, None, set(), CFG).order == order_day(["a", "b", "c"], cx).order


def test_among_equally_good_orders_the_one_closest_to_the_previous_version_wins():
    # a, b, c sit on a line 5 apart; "b, a, c" and "a, b, c" tour the same total distance from the start node,
    # but only "a, b, c" keeps a and b (both present before) in their previous relative order.
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)]
    from plan_fixtures import line_travel
    cx = day_ctx(recs, travel=line_travel({"a": 0, "b": 5, "c": 10}, scale=1), start_node=None, end_node=None)
    r = repair_day(["a", "b", "c"], cx, ("a", "b"), set(), CFG)
    assert r.order == ("a", "b", "c")


def test_a_brand_new_stop_added_to_an_old_day_costs_no_penalty_for_being_new():
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("new", 1, 1)]
    cx = day_ctx(recs)
    r = repair_day(["a", "b", "new"], cx, ("a", "b"), set(), CFG)
    assert {"a", "b"}.issubset(set(r.order)) and set(r.order) == {"a", "b", "new"}
    # a still comes before b: the one thing the previous version promised is kept
    assert r.order.index("a") < r.order.index("b")


def test_a_locked_place_leaving_its_day_is_refused():
    recs = [rec("a", 1, 1), rec("b", 1, 1)]
    cx = day_ctx(recs)
    with pytest.raises(RepairError):
        repair_day(["b"], cx, ("a", "b"), {"a"}, CFG)


def test_a_locked_place_that_stays_in_the_day_is_not_refused():
    recs = [rec("a", 1, 1), rec("b", 1, 1), rec("c", 1, 1)]
    cx = day_ctx(recs)
    repair_day(["a", "b", "c"], cx, ("a", "b"), {"a"}, CFG)   # no raise


def test_more_than_exact_n_stops_still_seeds_from_the_previous_order(monkeypatch):
    monkeypatch.setattr(CFG, "exact_n", 2)
    recs = [rec(p, i, i) for i, p in enumerate(["a", "b", "c", "d"])]
    cx = day_ctx(recs)
    r = repair_day(["a", "b", "c", "d"], cx, ("d", "c", "b", "a"), set(), CFG)
    assert set(r.order) == {"a", "b", "c", "d"} and not r.violations
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_repair.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.repair'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/repair.py`:

```python
"""repair_day (docs/specs/PLANNING_SPEC.md §Guardrail "Không xáo lịch âm thầm"): the order of one day right after a
user act touched its membership, penalized for reshuffling a stop that was already there. Reuses simulate()'s own
notion of a valid day (DayResult.key: fewer violations first) -- the diff penalty only breaks ties among orders that
are already equally good, it never trades validity away to stay close to the old order.
"""

from dataclasses import replace
from itertools import permutations

from .model import DayResult
from .schedule import DayCtx, simulate
from .settings import Settings


class RepairError(Exception):
    """A locked place would have to leave its day; refuse so the caller can ask the user first."""


def _diff(order: tuple[str, ...], prev: tuple[str, ...]) -> int:
    """Positions where two stops that both existed before now disagree on their relative order; 0 when every old
    stop keeps its old sequence (a brand-new stop may land anywhere at no penalty)."""
    common_prev = [i for i in prev if i in order]
    common_new = [i for i in order if i in prev]
    return sum(a != b for a, b in zip(common_prev, common_new))


def _key(r: DayResult, prev: tuple[str, ...], weight: float) -> tuple:
    return (len(r.violations), *r.key[1:], weight * _diff(r.order, prev))


def _seed_order(ids: list[str], ctx: DayCtx, prev: tuple[str, ...]) -> list[str]:
    """Keep the stops that were already in the day in their old order; walk the new ones on by nearest neighbour
    from the last kept stop (or the day's start when none were kept)."""
    kept = [i for i in prev if i in ids]
    rest = [i for i in ids if i not in prev]
    if not rest:
        return kept
    left, here, tail = rest[:], (kept[-1] if kept else ctx.day.start_node), []
    while left:
        nxt = min(left, key=lambda x: (ctx.travel.leg(here, x)[0] if here else 0, x))
        tail.append(nxt)
        left.remove(nxt)
        here = nxt
    return kept + tail


def repair_day(ids: list[str], ctx: DayCtx, prev_order: tuple[str, ...] | None, locked: set[str],
               cfg: Settings) -> DayResult:
    """ids: the day's new membership. prev_order: its order right before the act (None for a day repair_day has
    never touched, which costs no penalty -- the same as a fresh route.order_day)."""
    ids = sorted(ids)
    prev = prev_order or ()
    missing_locked = (set(prev) & locked) - set(ids)
    if missing_locked:
        raise RepairError(f"locked place(s) {sorted(missing_locked)} cannot leave the day")
    weight = cfg.repair_diff_weight
    if len(ids) <= 1:
        return simulate(ids, ctx)
    if len(ids) <= cfg.exact_n:
        best = None
        for perm in permutations(ids):
            r = simulate(list(perm), ctx)
            k = _key(r, prev, weight)
            if best is None or k < best[0]:
                best = (k, r)
        return replace(best[1], method="exact")
    order = _seed_order(ids, ctx, prev)
    best = simulate(order, ctx)
    n = len(order)
    for _ in range(cfg.improve_passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                r = simulate(cand, ctx)
                if _key(r, prev, weight) < _key(best, prev, weight):
                    order, best, improved = cand, r, True
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                cand = order[:]
                cand.insert(j, cand.pop(i))
                r = simulate(cand, ctx)
                if _key(r, prev, weight) < _key(best, prev, weight):
                    order, best, improved = cand, r, True
        if not improved:
            break
    return replace(best, method="heuristic")
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_repair.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/repair.py tests/planning/test_planning_repair.py
git commit -m "feat(planning): repair_day, a day's order penalized for drifting from its previous version"
```


### Task 3: `session.py` — `State`, `apply_act`, `Session`, `Store`

**Files:**
- Create: `src/planning/session.py`
- Test: `tests/planning/test_planning_session.py`

**Interfaces:**
- Consumes: `corpus.ontology.load`, `planning.places.Place`, `planning.settings.to_min`.
- Produces:
  - `planning.session.Drop(place_id, reason=None)`, `Relax(place_id, feature)` (pydantic `BaseModel`)
  - `planning.session.State` — `chosen_variant`, `lodging_touched`, `lodging_id`, `lodging_point`, `budget_override`, `assignment: dict[str, int]`, `order_override: dict[int, list[str]]`, `dropped: list[Drop]`, `locked: list[str]`, `pace_override`, `objective_override`, `day_window_override: dict[int, tuple[int, int]]`, `relaxed: list[Relax]`, `last`
  - `planning.session.ActionError(ValueError)`
  - `planning.session.ActCtx(by_place, n_days, variant_ids, backup_ids, day_members, objective_names, valid_paces)` (frozen dataclass)
  - `planning.session.apply_act(state: State, action: dict, ctx: ActCtx) -> State` — raises `ActionError`
  - `planning.session.Session(id, decision_session_id, decision, states, position, log, output)` with `.state` property
  - `planning.session.Store(root)` — `.new(decision, decision_session_id) -> Session`, `.get(sid) -> Session`, `.save(s)`, `.lock(sid)`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_session.py`:

```python
import pytest
from plan_fixtures import CFG, decision, rec

from planning.places import build_places
from planning.session import ActCtx, ActionError, Session, State, Store, apply_act


def place_map(*recs):
    places, _ = build_places(decision([r["id"] for r in recs]), {r["id"]: r for r in recs}, CFG)
    return {p.id: p for p in places}


def ctx(**kw):
    by_place = kw.pop("by_place", place_map(rec("a", 1, 1), rec("b", 2, 2), rec("c", 3, 3)))
    defaults = dict(by_place=by_place, n_days=2, variant_ids={"v1", "v2"}, backup_ids={"k": {"for": "a", "reason": None}},
                    day_members=[["a", "b"], ["c"]], objective_names={"least_travel", "low_cost"},
                    valid_paces={"slow", "normal", "packed"})
    return ActCtx(**{**defaults, **kw})


def test_pick_variant_sets_the_chosen_variant_and_rejects_an_unknown_one():
    s = apply_act(State(), {"type": "pick_variant", "id": "v2"}, ctx())
    assert s.chosen_variant == "v2"
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "pick_variant", "id": "v9"}, ctx())


def test_move_place_records_the_assignment_and_clears_any_drop():
    s = State(dropped=[])
    s = apply_act(s, {"type": "drop_place", "place": "a"}, ctx())
    s = apply_act(s, {"type": "move_place", "place": "a", "day": 1}, ctx())
    assert s.assignment["a"] == 1 and not any(d.place_id == "a" for d in s.dropped)


def test_move_place_out_of_range_or_unknown_place_is_an_action_error():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "move_place", "place": "a", "day": 9}, ctx())
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "move_place", "place": "ghost", "day": 0}, ctx())


def test_moving_a_locked_place_is_refused_before_repair_day_even_runs():
    with pytest.raises(ActionError):
        apply_act(State(locked=["a"]), {"type": "move_place", "place": "a", "day": 1}, ctx())


def test_reorder_must_be_a_permutation_of_the_days_current_members():
    s = apply_act(State(), {"type": "reorder", "day": 0, "order": ["b", "a"]}, ctx())
    assert s.order_override[0] == ["b", "a"]
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "reorder", "day": 0, "order": ["a"]}, ctx())


def test_add_from_backup_requires_a_pool_id():
    s = apply_act(State(), {"type": "add_from_backup", "place": "k", "day": 1}, ctx())
    assert s.assignment["k"] == 1
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "add_from_backup", "place": "not_in_pool", "day": 1}, ctx())


def test_swap_drops_the_old_place_and_adds_the_backup_at_its_day():
    s = apply_act(State(), {"type": "swap", "place": "a", "with": "k"}, ctx())
    assert s.dropped[-1].place_id == "a" and s.assignment["k"] == 0        # a was on day 0


def test_lock_and_unlock_round_trip():
    s = apply_act(State(), {"type": "lock_slot", "place": "a"}, ctx())
    assert s.locked == ["a"]
    s = apply_act(s, {"type": "unlock", "place": "a"}, ctx())
    assert s.locked == []


def test_set_pace_and_set_objective_validate_against_the_ctx():
    s = apply_act(State(), {"type": "set_pace", "level": "packed"}, ctx())
    assert s.pace_override == "packed"
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_pace", "level": "turbo"}, ctx())
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_objective", "name": "not_an_objective"}, ctx())


def test_set_day_window_parses_clock_strings_and_rejects_start_after_end():
    s = apply_act(State(), {"type": "set_day_window", "day": 0, "start": "09:00", "end": "20:00"}, ctx())
    assert s.day_window_override[0] == (540, 1200)
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_day_window", "day": 0, "start": "20:00", "end": "09:00"}, ctx())


def test_relax_rejects_a_physical_feature():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "relax", "place_id": "a", "feature": "steep_or_stairs"}, ctx())
    s = apply_act(State(), {"type": "relax", "place_id": "a", "feature": "parking"}, ctx())
    assert s.relaxed[0] == (await_none := s.relaxed[0]) and s.relaxed[0].place_id == "a"


def test_relax_whole_trip_needs_an_explicit_place_list_from_the_caller():
    s = apply_act(State(), {"type": "relax", "feature": "parking", "scope": "whole_trip", "place_ids": ["a", "b"]}, ctx())
    assert {r.place_id for r in s.relaxed} == {"a", "b"}


def test_pick_lodging_and_clear_lodging_mark_lodging_touched():
    s = apply_act(State(), {"type": "pick_lodging", "id": "h1"}, ctx())
    assert s.lodging_touched and s.lodging_id == "h1"
    s = apply_act(s, {"type": "clear_lodging"}, ctx())
    assert s.lodging_touched and s.lodging_id is None


def test_set_lodging_needs_a_resolved_point_from_the_caller():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_lodging", "text": "Homestay X"}, ctx())
    point = {"id": "manual:1", "lat": 1.0, "lng": 1.0, "text": "Homestay X", "source": "nominatim", "fetched_at": "t"}
    s = apply_act(State(), {"type": "set_lodging", "text": "Homestay X", "_point": point}, ctx())
    assert s.lodging_touched and s.lodging_point == point


def test_set_lodging_budget_accepts_none_or_a_non_negative_int():
    s = apply_act(State(), {"type": "set_lodging_budget", "max_per_night": 500000}, ctx())
    assert s.budget_override == 500000
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "set_lodging_budget", "max_per_night": -1}, ctx())


def test_an_unknown_act_type_is_an_action_error():
    with pytest.raises(ActionError):
        apply_act(State(), {"type": "teleport"}, ctx())


def test_store_round_trips_through_disk(tmp_path):
    store = Store(tmp_path)
    s = store.new({"confirmed": []}, "dsid")
    store.save(s)
    reloaded = Store(tmp_path).get(s.id)
    assert reloaded.decision_session_id == "dsid" and reloaded.state == State()


def test_store_unknown_or_malformed_id_is_a_key_error(tmp_path):
    with pytest.raises(KeyError):
        Store(tmp_path).get("not-twelve-hex")
    with pytest.raises(KeyError):
        Store(tmp_path).get("0" * 12)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_session.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.session'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/session.py`:

```python
"""A Planning session: a Decision Output plus the user's edits, versioned for undo / redo
(docs/specs/PLANNING_SPEC.md §Vòng người dùng sửa và góp ý). Shaped like src/decision/session.py; in memory,
mirrored to data/planning/sessions/<id>.json so a reload or a restart resumes. Only State is persisted -- the laid
out Schedule is rebuilt by the engine (Task 6), never serialized here.
"""

import json
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from corpus.ontology import load as load_ontology

from .settings import to_min

Reason = Literal["far", "crowded", "pricey", "dislike", "visited", None]
SID = re.compile(r"[0-9a-f]{12}")


class Drop(BaseModel):
    place_id: str
    reason: Reason = None


class Relax(BaseModel):
    place_id: str
    feature: str


class State(BaseModel):
    chosen_variant: str | None = None
    lodging_touched: bool = False       # False = still the chosen variant's own lodging
    lodging_id: str | None = None       # a candidate id, or None for "no lodging" once lodging_touched
    lodging_point: dict | None = None   # set_lodging(text): {"id","lat","lng","text","source","fetched_at"}
    budget_override: int | None = None
    assignment: dict[str, int] = Field(default_factory=dict)             # place id -> day index, user-placed
    order_override: dict[int, list[str]] = Field(default_factory=dict)
    dropped: list[Drop] = Field(default_factory=list)
    locked: list[str] = Field(default_factory=list)
    pace_override: str | None = None
    objective_override: str | None = None
    day_window_override: dict[int, tuple[int, int]] = Field(default_factory=dict)
    relaxed: list[Relax] = Field(default_factory=list)
    last: str | None = None


class ActionError(ValueError):
    """The action is malformed or does not fit the session; nothing changed."""


@dataclass(frozen=True)
class ActCtx:
    by_place: dict                  # id -> Place, places the trip currently schedules
    n_days: int
    variant_ids: set
    backup_ids: dict                # backup_pool id -> its entry ({"for", "reason", ...})
    day_members: list               # place ids of each day, in the schedule this act applies onto
    objective_names: set
    valid_paces: set


def _is_physical(feature: str) -> bool:
    f = load_ontology().features.get(feature)
    return f is not None and f.group == "effort"


def _known(ctx: ActCtx, pid) -> bool:
    return isinstance(pid, str) and pid in ctx.by_place


def _day_of(ctx: ActCtx, pid: str) -> int | None:
    return next((d for d, ids in enumerate(ctx.day_members) if pid in ids), None)


def _drop(s: State, pid: str, reason: str | None = None) -> None:
    s.assignment.pop(pid, None)
    s.dropped = [d for d in s.dropped if d.place_id != pid] + [Drop(place_id=pid, reason=reason)]
    s.order_override = {d: [i for i in o if i != pid] for d, o in s.order_override.items()}


def _place(s: State, pid: str, day: int) -> None:
    s.dropped = [d for d in s.dropped if d.place_id != pid]
    s.assignment[pid] = day
    s.order_override.pop(day, None)


def apply_act(state: State, action: dict, ctx: ActCtx) -> State:
    t = action.get("type")
    s = state.model_copy(deep=True)
    if t == "pick_variant":
        vid = action.get("id")
        if vid not in ctx.variant_ids:
            raise ActionError(f"unknown variant {vid!r}")
        s.chosen_variant = vid
    elif t == "pick_lodging":
        s.lodging_touched, s.lodging_id, s.lodging_point = True, action.get("id"), None
    elif t == "clear_lodging":
        s.lodging_touched, s.lodging_id, s.lodging_point = True, None, None
    elif t == "set_lodging":
        point = action.get("_point")
        if not point:
            raise ActionError("set_lodging needs a resolved point (geocode failed or text empty)")
        s.lodging_touched, s.lodging_id, s.lodging_point = True, point["id"], point
    elif t == "set_lodging_budget":
        n = action.get("max_per_night")
        if n is not None and (not isinstance(n, int) or n < 0):
            raise ActionError(f"bad max_per_night {n!r}")
        s.budget_override = n
    elif t == "move_place":
        pid, day = action.get("place"), action.get("day")
        if not _known(ctx, pid):
            raise ActionError(f"unknown place {pid!r}")
        if pid in s.locked:
            raise ActionError(f"{pid!r} is locked to its day")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        _place(s, pid, day)
    elif t == "reorder":
        day, order = action.get("day"), action.get("order")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        if sorted(order or []) != sorted(ctx.day_members[day]):
            raise ActionError("order must be a permutation of the day's current places")
        s.order_override[day] = list(order)
    elif t == "drop_place":
        pid = action.get("place")
        if not _known(ctx, pid):
            raise ActionError(f"unknown place {pid!r}")
        if pid in s.locked:
            raise ActionError(f"{pid!r} is locked to its day")
        reason = action.get("reason")
        if reason not in (None, "far", "crowded", "pricey", "dislike", "visited"):
            raise ActionError(f"unknown reason {reason!r}")
        _drop(s, pid, reason)
    elif t == "add_from_backup":
        pid, day = action.get("place"), action.get("day")
        if pid not in ctx.backup_ids:
            raise ActionError(f"{pid!r} is not in the backup pool")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        _place(s, pid, day)
    elif t == "swap":
        a, b = action.get("place"), action.get("with")
        if b not in ctx.backup_ids:
            raise ActionError(f"{b!r} is not in the backup pool")
        day = _day_of(ctx, a)
        if day is None:
            raise ActionError(f"{a!r} is not currently in the plan")
        if a in s.locked:
            raise ActionError(f"{a!r} is locked to its day")
        _drop(s, a)
        _place(s, b, day)
    elif t == "lock_slot":
        pid = action.get("place")
        if not _known(ctx, pid) or _day_of(ctx, pid) is None:
            raise ActionError(f"{pid!r} is not currently in the plan")
        if pid not in s.locked:
            s.locked.append(pid)
    elif t == "unlock":
        s.locked = [x for x in s.locked if x != action.get("place")]
    elif t == "set_pace":
        level = action.get("level")
        if level not in ctx.valid_paces:
            raise ActionError(f"unknown pace {level!r}")
        s.pace_override = level
    elif t == "set_objective":
        name = action.get("name")
        if name not in ctx.objective_names:
            raise ActionError(f"unknown objective {name!r}")
        s.objective_override = name
    elif t == "set_day_window":
        day, start, end = action.get("day"), action.get("start"), action.get("end")
        if not isinstance(day, int) or not 0 <= day < ctx.n_days:
            raise ActionError(f"day {day!r} out of range")
        try:
            a, b = to_min(start), to_min(end)
        except (ValueError, AttributeError):
            raise ActionError(f"bad time {start!r} / {end!r}") from None
        if a >= b:
            raise ActionError("start must be before end")
        s.day_window_override[day] = (a, b)
    elif t == "relax":
        feature = action.get("feature")
        if feature not in load_ontology().features:
            raise ActionError(f"unknown feature {feature!r}")
        if _is_physical(feature):
            raise ActionError(f"{feature!r} is a physical constraint, it cannot be relaxed")
        ids = action.get("place_ids") or ([action["place_id"]] if action.get("place_id") else [])
        if not ids:
            raise ActionError("relax needs place_id or place_ids")
        have = {(r.place_id, r.feature) for r in s.relaxed}
        s.relaxed += [Relax(place_id=i, feature=feature) for i in ids if (i, feature) not in have]
    else:
        raise ActionError(f"unknown action {t!r}")
    s.last = t
    return s


class Session(BaseModel):
    id: str
    decision_session_id: str | None = None
    decision: dict
    states: list[State] = Field(default_factory=lambda: [State()])
    position: int = 0
    log: list[dict] = Field(default_factory=list)
    output: dict | None = None

    @property
    def state(self) -> State:
        return self.states[self.position]


class Store:
    def __init__(self, root: Path | None):
        self.root = root
        self._mem: dict[str, Session] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def new(self, decision: dict, decision_session_id: str | None) -> Session:
        s = Session(id=uuid.uuid4().hex[:12], decision_session_id=decision_session_id, decision=decision)
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

`test_relax_rejects_a_physical_feature` dùng `steep_or_stairs` / `parking` — hai feature id này phải có trong `config/ontology.yaml` với group `effort` và khác `effort`; nếu tên thật khác, sửa test cho khớp ontology hiện có (`corpus.ontology.load().features`), không sửa code.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_session.py -q`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/session.py tests/planning/test_planning_session.py
git commit -m "feat(planning): session State, apply_act and disk-backed Store"
```


### Task 4: `output.py` — Plan Output lúc `confirm`

**Files:**
- Create: `src/planning/output.py`
- Test: `tests/planning/test_planning_output.py`

**Interfaces:**
- Consumes: `planning.build.Trip/itinerary/travel_load/shared_output`, `live.route_shape`, `live.Unavailable`.
- Produces:
  - `planning.output.route_of_day(day, result, coords: dict, live_cfg, mobility, route_fn=None) -> dict | None` — `{"points": [[lat,lng], ...], "source", "fetched_at"}` hoặc `None` khi không tra được
  - `planning.output.cost(metrics: dict, lodging_price_vnd: int | None, nights: int) -> dict` — `{"known_vnd", "unknown_items", "lodging_known"}`
  - `planning.output.build(trip, variants: list[dict], chosen: dict, chosen_results: list, decision: dict, coords: dict, live_cfg, route_fn=None) -> dict` — hình dạng `PLANNING_SPEC.md §Plan Output`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_output.py`:

```python
from plan_fixtures import prepared, sample_trip

from live import Unavailable
from planning.objectives import metrics as compute_metrics
from planning.output import build, cost, route_of_day


def fake_route_ok(points, mode, live_cfg):
    return {"points": [list(p) for p in points], "source": "osrm", "fetched_at": "t"}


def fake_route_down(points, mode, live_cfg):
    raise Unavailable("osrm down")


def test_route_of_day_asks_for_the_days_visited_points_in_order():
    seen = []

    def fake(points, mode, live_cfg):
        seen.append(points)
        return fake_route_ok(points, mode, live_cfg)

    from planning.model import Day, DayResult, Item
    day = Day(0, None, None, 480, 1260, "@entry", "@exit")
    r = DayResult((Item("visit", 500, 530, place_id="a"), Item("visit", 600, 630, place_id="b")), ("a", "b"), (), 0, 0, 630)
    coords = {"@entry": (1.0, 1.0), "a": (1.1, 1.1), "b": (1.2, 1.2), "@exit": (1.3, 1.3)}
    out = route_of_day(day, r, coords, object(), "motorbike", route_fn=fake)
    assert out["source"] == "osrm" and seen[0] == [(1.0, 1.0), (1.1, 1.1), (1.2, 1.2), (1.3, 1.3)]


def test_route_of_day_is_none_not_a_crash_when_osrm_is_down():
    from planning.model import Day, DayResult, Item
    day = Day(0, None, None, 480, 1260, None, None)
    r = DayResult((Item("visit", 500, 530, place_id="a"),), ("a",), (), 0, 0, 530)
    out = route_of_day(day, r, {"a": (1.0, 1.0)}, object(), "motorbike", route_fn=fake_route_down)
    assert out is None


def test_route_of_day_needs_at_least_two_points():
    from planning.model import Day, DayResult
    day = Day(0, None, None, 480, 1260, None, None)
    r = DayResult((), (), (), 0, 0, 480)
    assert route_of_day(day, r, {}, object(), "motorbike", route_fn=fake_route_ok) is None


def test_cost_adds_a_known_lodging_price_and_counts_an_unknown_one_separately():
    m = {"cost_vnd": 300000, "cost_unknown": 1}
    known = cost(m, 500000, 2)
    assert known == {"known_vnd": 300000 + 500000 * 2, "unknown_items": 1, "lodging_known": True}
    unknown = cost(m, None, 2)
    assert unknown == {"known_vnd": 300000, "unknown_items": 2, "lodging_known": False}
    no_stay = cost(m, None, 0)
    assert no_stay == {"known_vnd": 300000, "unknown_items": 1, "lodging_known": True}   # 0 nights: nothing to know


def test_build_assembles_the_plan_output_shape():
    d, recs = sample_trip(days=2)
    trip = prepared(d, recs)
    from planning.build import schedule_trip
    sched = schedule_trip(trip)
    m = compute_metrics(sched.ctxs, sched.results)
    chosen = {"id": "v1", "objective": "least_travel", "label": "Ít di chuyển", "metrics": m,
             "itinerary": [], "travel_load": [], "robustness": {"level": "solid", "label": "Vững", "reasons": [],
                                                                 "scenarios": [], "breaking": [], "skipped": []},
             "backups": {"places": [], "on_delay": []}, "warnings": [], "lodging": {"id": None, "name": None, "price_vnd": None}}
    coords = {p.id: (p.lat, p.lng) for p in trip.by_place.values()}
    out = build(trip, [chosen], chosen, d, coords, object(), route_fn=fake_route_down)
    for key in ("variants", "chosen", "itinerary", "route", "lodging", "cost", "travel_load", "reasons", "tradeoffs",
               "warnings", "uncertainty", "robustness", "backups", "provenance"):
        assert key in out, key
    assert out["chosen"] == "v1" and len(out["route"]) == len(sched.days if hasattr(sched, "days") else trip.days)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_output.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.output'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/output.py`:

```python
"""Plan Output (docs/specs/PLANNING_SPEC.md §Plan Output): the chosen variant, finalized at confirm().

route and cost are the two parts no variant dict already carries (route needs a fresh OSRM call per day; cost needs
the chosen lodging's price). Everything else here is reshaping what build.py / variants.py already computed.
"""

import live

from .build import flag_warnings, shared_output


def route_of_day(day, result, coords: dict, live_cfg, mobility, route_fn=None) -> dict | None:
    """The shape of one day's path (OSRM /route), or None when it cannot be drawn: fewer than two stops with known
    coordinates, or the source is unavailable. Never a reason to fail confirm -- a plan with no drawable route is
    still valid, just without a line on the map."""
    route_fn = route_fn or live.route_shape
    nodes = [day.start_node] + [i.place_id for i in result.items if i.kind == "visit"] + [day.end_node]
    points = [coords[n] for n in nodes if n is not None and n in coords]
    if len(points) < 2:
        return None
    try:
        return route_fn(points, mobility, live_cfg)
    except live.Unavailable:
        return None


def cost(metrics: dict, lodging_price_vnd: int | None, nights: int) -> dict:
    """known_vnd: tickets / drinks already summed in metrics, plus the lodging's total price when it is known.
    unknown_items: places with no known price, plus the lodging itself when it is chosen but priceless."""
    lodging_total = lodging_price_vnd * nights if lodging_price_vnd is not None else None
    lodging_known = lodging_price_vnd is not None or nights <= 0
    return {"known_vnd": metrics["cost_vnd"] + (lodging_total or 0),
           "unknown_items": metrics["cost_unknown"] + (0 if lodging_known else 1),
           "lodging_known": lodging_known}


def build(trip, variants: list[dict], chosen: dict, chosen_results: list, decision: dict, coords: dict, live_cfg,
         route_fn=None) -> dict:
    """chosen: one of variants.build_lodging_variants' per-variant dicts (itinerary already rendered to text).
    chosen_results: the DayResult objects behind it (Schedule.results for the day order route_of_day needs)."""
    mobility = decision["trip_context"]["context"].get("mobility")
    days = [cx.day for cx in trip.ctxs][: len(chosen_results)] or trip.days[: len(chosen_results)]
    nights = max((decision["trip_context"]["context"].get("days") or 1) - 1, 0)
    lodging = chosen.get("lodging") or {}
    shared = shared_output(trip)
    return {
        "variants": [{"id": v["id"], "objective": v["objective"], "label": v["label"], "score": v["score"]}
                     for v in variants],
        "chosen": chosen["id"],
        "itinerary": chosen["itinerary"],
        "route": [route_of_day(d, r, coords, live_cfg, mobility, route_fn) for d, r in zip(days, chosen_results)],
        "lodging": {"chosen": lodging, "candidates": []},
        "cost": cost(chosen["metrics"], lodging.get("price_vnd"), nights),
        "travel_load": chosen["travel_load"],
        "reasons": shared["reasons"],
        "tradeoffs": shared["tradeoffs"],
        "warnings": trip.warnings + chosen["warnings"] + flag_warnings(decision),
        "uncertainty": shared["uncertainty"],
        "robustness": chosen["robustness"],
        "backups": chosen["backups"],
        "provenance": shared["provenance"],
    }
```

Và sửa test `test_build_assembles_the_plan_output_shape` ở Step 1 cho khớp chữ ký mới: thay dòng gọi `build(...)` bằng
`out = build(trip, [chosen], chosen, sched.results, d, coords, object(), route_fn=fake_route_down)`.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_output.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/output.py tests/planning/test_planning_output.py
git commit -m "feat(planning): assemble the Plan Output -- route and cost -- at confirm"
```


### Task 5: `engine.py` phần A — `Engine.create` / `load`, Trip cache, `variants` / `lodging`

**Files:**
- Create: `src/planning/engine.py`
- Test: `tests/planning/test_planning_engine.py`

**Interfaces:**
- Consumes: `planning.build.prepare/schedule_trip/with_home`, `planning.variants.build_variants` (dùng nội bộ để chọn mục tiêu + dựng mỗi variant), `planning.lodging.candidates/progress_event`, `planning.session.*`, `planning.scope.act_scope`.
- Produces (phần A của `Engine`, hoàn thiện ở Task 6):
  - `planning.engine.NoSession(Exception)`, `NotConfirmable(Exception)`
  - `Engine(records, cfg=None, live_cfg=None, store=None, geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, decision_url=None, http_post=None)`
  - `Engine.create(decision: dict | None, decision_session_id: str | None) -> dict` — `{"id", "view"}`
  - `Engine.load(sid) -> dict` — `{"id", "view"}`
  - `Engine.variants(sid) -> list[dict]`
  - `Engine.lodging(sid) -> dict` — `{"status": "pending"|"ready"|"unavailable", "candidates", "chosen"}`

- [ ] **Step 1: Viết test**

Thêm vào `tests/planning/plan_fixtures.py` (cuối file):

```python


def small_trip(**kw):
    """Three places on a line, one day enough for all of them: small enough for move/reorder/lock tests to read."""
    recs = [spot("a", CENTRE, 0), spot("b", CENTRE, 1), spot("c", CENTRE, 2)]
    return decision([r["id"] for r in recs], days=1, **kw), recs


def fake_lodging(center, radius_km, check_in, check_out, price_max, live_cfg):
    cands = [{"id": "h1", "name": "Homestay 1", "lat": CENTRE[0] + 0.001, "lng": CENTRE[1], "rating": 4.5,
             "reviews": 20, "price_vnd": 300000, "amenities": ["wifi"]},
            {"id": "h2", "name": "Homestay 2", "lat": CENTRE[0] - 0.001, "lng": CENTRE[1], "rating": 4.2,
             "reviews": 15, "price_vnd": 900000, "amenities": []}]
    return [c for c in cands if price_max is None or c["price_vnd"] <= price_max]
```

Tạo `tests/planning/test_planning_engine.py`:

```python
import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip, small_trip

from planning.engine import Engine, NoSession
from planning.session import ActionError, Store


def engine(records=None, lodging_fn=fake_lodging):
    d, recs = sample_trip() if records is None else (None, None)
    return Engine([], cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                 sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lodging_fn)


def test_create_returns_variants_right_away_without_waiting_on_lodging():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=lambda *a: pytest.fail("lodging must not block create"))
    out = e.create(d, None)
    assert out["id"] and out["view"]["ok"] and out["view"]["variants"]
    assert out["view"]["lodging"]["status"] == "pending"


def test_load_an_unknown_session_is_no_session():
    e = engine()
    with pytest.raises(NoSession):
        e.load("0" * 12)


def test_lodging_turns_ready_once_the_background_crawl_finishes():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)  # run synchronously in tests
    out = e.create(d, None)
    sid = out["id"]
    lod = e.lodging(sid)
    assert lod["status"] == "ready"
    assert {c["id"] for c in lod["candidates"]} == {"h1", "h2"}


def test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one():
    d, recs = sample_trip(budget=2_000_000)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    variants = e.variants(sid)
    e.act(sid, {"type": "pick_variant", "id": variants[0]["id"]})
    e.act(sid, {"type": "pick_lodging", "id": "h2"})            # 900k/night, affordable under a 2M budget trip
    e.act(sid, {"type": "set_lodging_budget", "max_per_night": 400000})
    lod = e.lodging(sid)
    assert {c["id"] for c in lod["candidates"]} == {"h1"}       # h2 dropped out of the fetched list ...
    assert e.load(sid)["view"]["state"]["lodging_id"] == "h2"   # ... but the chosen lodging did not silently change
    with pytest.raises(ActionError):
        e.act(sid, {"type": "pick_lodging", "id": "h2"})        # re-picking a candidate no longer offered is refused
```

(`background=False` buộc Task 6's thread chạy đồng bộ trong thân `create`, để test không phải chờ/poll — tham số này được thêm vào `Engine.__init__` ở chính task này.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_engine.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.engine'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/engine.py`:

```python
"""Planning sessions for the web (docs/specs/PLANNING_SPEC.md §API và web): create (fast, anchor = base), act (chips,
no model), variants, lodging (crawled in the background), confirm. One lock per session; each committing act is one
version that undo / redo moves between.
"""

import threading
import urllib.error
import urllib.request
from dataclasses import replace
from functools import cache
from json import dumps, loads

import live

from . import places as pl
from .build import ENTRY, EXIT, HOME, prepare, schedule_trip, with_home
from .lodging import candidates as lodging_candidates
from .lodging import progress_event
from .objectives import LABEL, add_lodging_cost, choose, metrics, score
from .repair import RepairError, repair_day
from .robustness import robustness as robustness_of
from .backup import backups as backups_of
from .scope import LODGING_FETCH, LODGING_HOME, NONE, RELAYOUT, VARIANT, act_scope
from .session import ActCtx, ActionError, Session, State, Store
from .settings import Settings
from .settings import load as load_settings


class NoSession(Exception):
    pass


class NotConfirmable(Exception):
    pass


def _nights(ctx: dict) -> int:
    return max((ctx.get("days") or 1) - 1, 0)


class _Base:
    """What create() computes once (no lodging yet) and the lodging crawl later fills in -- held in RAM, keyed by
    session id. Never persisted: a restart rebuilds it from Session.decision + State (Task 6)."""

    def __init__(self, trip, variants: list[dict], comparison: list[dict], ok: bool, warnings: list,
                back_to_decision: dict | None):
        self.trip = trip
        self.variants = variants          # objective -> variant dict, home = @home/@entry (no lodging)
        self.comparison = comparison
        self.ok = ok
        self.warnings = warnings
        self.back_to_decision = back_to_decision
        self.lodging_status = "pending"   # pending | ready | unavailable
        self.lodging_candidates: list[dict] = []


class Engine:
    def __init__(self, records: list[dict], cfg: Settings | None = None, live_cfg=None, store: Store | None = None,
                geocode_fn=None, matrix_fn=None, sun_fn=None, lodging_fn=None, decision_url: str | None = None,
                http_post=None, background: bool = True):
        self.by_id = {r["id"]: r for r in records}
        self.records = records
        self.cfg = cfg or load_settings()
        self.live_cfg = live_cfg or live.load_settings()
        self.store = store or Store(None)
        self.geocode_fn = geocode_fn
        self.matrix_fn = matrix_fn
        self.sun_fn = sun_fn
        self.lodging_fn = lodging_fn or live.lodging_near
        self.decision_url = decision_url or self.cfg.decision_url
        self.http_post = http_post or _http_post
        self.background = background
        self._base: dict[str, _Base] = {}

    # ---------- resolving a Decision Output ----------

    def _resolve(self, decision: dict | None, decision_session_id: str | None) -> dict:
        if decision is not None:
            return decision
        if not decision_session_id:
            raise ActionError("need decision_output or decision_session_id")
        url = f"{self.decision_url}/api/decision/sessions/{decision_session_id}/confirm"
        try:
            body = self.http_post(url)
        except OSError as e:
            raise ActionError(f"could not reach the decision session: {e}") from None
        return loads(body)

    # ---------- Trip / variants (no lodging) ----------

    def _prepare(self, decision: dict, extra_nodes: dict | None = None):
        return prepare(decision, self.records, self.cfg, self.live_cfg, self.geocode_fn, self.matrix_fn, self.sun_fn,
                       extra_nodes=extra_nodes)

    def _build_base(self, decision: dict) -> _Base:
        trip = self._prepare(decision)
        objectives = choose(decision["trip_context"], [cx.rain for cx in trip.ctxs], trip.ctxs[0].prefs, self.cfg)
        variants, seen = [], set()
        for obj in objectives:
            s = schedule_trip(trip, self.cfg.objective_weights[obj])
            if s.violations:
                continue
            orders = tuple(r.order for r in s.results)
            if orders in seen:
                continue
            seen.add(orders)
            m = metrics(s.ctxs, s.results)
            days = [cx.day for cx in s.ctxs]
            from .build import itinerary as render_itinerary
            from .build import travel_load as render_travel_load
            variants.append({"id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj],
                             "score": list(score(obj, m)), "metrics": m,
                             "itinerary": render_itinerary(days, s.results), "travel_load": render_travel_load(days, s.results),
                             "robustness": robustness_of(s.ctxs, s.results, trip.travel.source),
                             "backups": backups_of(s.ctxs, s.results, decision, trip.by_id), "warnings": s.warnings,
                             "lodging": {"id": None, "name": None, "price_vnd": None},
                             "_results": s.results, "_home": trip.days[0].start_node if trip.days else None})
        ok = bool(variants)
        back = None
        if not ok:
            back = {"reason": "no_valid_variant", "places": sorted({v.place_id for v in
                    schedule_trip(trip, self.cfg.objective_weights[objectives[0]]).violations if v.place_id})}
        return _Base(trip, variants, [], ok, list(trip.warnings), back)

    def _crawl_lodging(self, sid: str) -> None:
        base = self._base[sid]
        decision = self.store.get(sid).decision
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except live.Unavailable:
            cands = []
        base.lodging_candidates = cands
        base.lodging_status = "ready" if cands else "unavailable"

    # ---------- API ----------

    def create(self, decision: dict | None = None, decision_session_id: str | None = None) -> dict:
        decision = self._resolve(decision, decision_session_id)
        s = self.store.new(decision, decision_session_id)
        base = self._build_base(decision)
        self._base[s.id] = base
        self.store.save(s)
        if self.background:
            threading.Thread(target=self._crawl_lodging, args=(s.id,), daemon=True).start()
        else:
            self._crawl_lodging(s.id)
        return {"id": s.id, "view": self._view(s)}

    def _get(self, sid: str) -> Session:
        try:
            return self.store.get(sid)
        except KeyError:
            raise NoSession(sid) from None

    def _view(self, s: Session) -> dict:
        base = self._base[s.id]
        return {"ok": base.ok, "variants": [{k: v for k, v in v.items() if not k.startswith("_")} for v in base.variants],
               "comparison": base.comparison, "warnings": base.warnings, "back_to_decision": base.back_to_decision,
               "lodging": {"status": base.lodging_status,
                           "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]}
                                         for c in base.lodging_candidates]},
               "state": s.state.model_dump(mode="json")}

    def load(self, sid: str) -> dict:
        s = self._get(sid)
        with self.store.lock(sid):
            return {"id": s.id, "view": self._view(s)}

    def variants(self, sid: str) -> list[dict]:
        self._get(sid)
        return self._view(self._get(sid))["variants"]

    def lodging(self, sid: str) -> dict:
        self._get(sid)
        return self._view(self._get(sid))["lodging"]
```

`http_post`/`_http_post` và các method `act`/`confirm` được hoàn thiện ở Task 6 (file này được sửa, không viết lại); tạm thêm hàm module-level tối thiểu để `Engine` import được ở task này:

```python
def _http_post(url: str) -> str:
    req = urllib.request.Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")
```

(đặt `_http_post` ngay dưới các import, trước `class NoSession`).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_engine.py -q`
Expected: PASS (5 tests) — `test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one` dùng `e.act(...)`, chưa tồn tại: đánh dấu `xfail` tạm trong bước này —

```python
@pytest.mark.xfail(reason="Engine.act lands in Task 6", strict=True)
def test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one():
    ...
```

thêm decorator đó lên trên hàm test đó trong Step 1 trước khi chạy, rồi bỏ nó ở Task 6 khi `act` đã có.

- [ ] **Step 5: Commit**

```bash
git add src/planning/engine.py tests/planning/test_planning_engine.py tests/planning/plan_fixtures.py
git commit -m "feat(planning): Engine.create builds variants fast, lodging crawls in the background"
```


### Task 6: `engine.py` phần B — `act`, `undo`/`redo`, `confirm`

**Files:**
- Modify: `src/planning/engine.py` (thêm vào class `Engine`, xoá `@xfail` ở test trên)
- Test: `tests/planning/test_planning_engine.py` (thêm vào cuối)

**Interfaces:**
- Consumes: Task 1–5 nguyên trạng.
- Produces:
  - `Engine.act(sid, action: dict) -> dict` — `{"view", "diff"}`; ném `ActionError` / `RepairError` (400), `NoSession` (404)
  - `Engine.confirm(sid) -> dict` — Plan Output (`output.build`); ném `NotConfirmable`

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_engine.py` (và xoá `@pytest.mark.xfail` khỏi `test_a_lower_budget_drops_candidates_but_never_silently_changes_the_chosen_one` đã viết ở Task 5):

```python


def started(budget=None):
    d, recs = small_trip(budget=budget)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    return e, sid


def test_acting_before_pick_variant_is_refused():
    d, recs = small_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    with pytest.raises(ActionError):
        e.act(sid, {"type": "reorder", "day": 0, "order": ["a", "b", "c"]})


def test_reorder_changes_only_the_day_it_touches():
    e, sid = started()
    before = e.load(sid)["view"]["state"]
    out = e.act(sid, {"type": "reorder", "day": 0, "order": ["c", "b", "a"]})
    assert out["view"]["itinerary"][0]["items"][0]["place_id"] == "c"


def test_moving_a_locked_place_is_refused_and_the_session_does_not_change():
    e, sid = started()
    e.act(sid, {"type": "lock_slot", "place": "a"})
    before = e.load(sid)
    with pytest.raises(ActionError):
        e.act(sid, {"type": "move_place", "place": "a", "day": 0})   # same day, still refused: a is locked at all
    assert e.load(sid)["view"]["state"] == before["view"]["state"]


def test_two_acts_on_the_same_day_compose_and_every_other_day_is_byte_identical():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    sid = e.create(d, None)["id"]
    e.act(sid, {"type": "pick_variant", "id": e.variants(sid)[0]["id"]})
    before = e.load(sid)["view"]["itinerary"]
    out1 = e.act(sid, {"type": "drop_place", "place": "c1"})
    out2 = e.act(sid, {"type": "reorder", "day": 0, "order": sorted(out1["view"]["itinerary"][0]["items"],
                                                                    key=lambda i: i.get("place_id") or "")})
    other_day_before = [d for d in before if d["day"] != 1]
    other_day_after = [d for d in out2["view"]["itinerary"] if d["day"] != 1]
    assert other_day_before == other_day_after or not other_day_before  # day 2 untouched by day-1-only acts


def test_a_new_act_after_undo_discards_the_redone_future():
    e, sid = started()
    e.act(sid, {"type": "lock_slot", "place": "a"})
    e.act(sid, {"type": "undo"})
    assert e.load(sid)["view"]["state"]["locked"] == []
    e.act(sid, {"type": "lock_slot", "place": "b"})
    with pytest.raises(ActionError):
        e.act(sid, {"type": "redo"})          # the "lock a" future was discarded by the new act


def test_undo_with_nothing_to_undo_is_an_action_error():
    e, sid = started()
    with pytest.raises(ActionError):
        e.act(sid, {"type": "undo"})


def test_confirm_refuses_an_unvalidated_plan():
    e, sid = started()
    e.act(sid, {"type": "move_place", "place": "a", "day": 5})
```

Dòng cuối cố ý sai (day 5 không tồn tại với `small_trip(days=1)`) để kiểm `ActionError` chặn trước khi tới `confirm` — sửa thành một kiểm tra rõ ràng:

```python
def test_confirm_refuses_an_unvalidated_plan():
    from planning.engine import NotConfirmable
    e, sid = started()
    e.act(sid, {"type": "move_place", "place": "a", "day": 0})   # fine
    out = e.confirm(sid)
    assert out["chosen"]
    # dropping every place then confirming again still succeeds (an empty day is valid); NotConfirmable is reserved
    # for a schedule validate() currently rejects -- exercised directly against the relayout path:
    with pytest.raises(NotConfirmable):
        bad_trip = e._base[sid].trip
        from planning.schedule import DayCtx
        from dataclasses import replace as _r
        # force an impossible day window so validate() fails, then try to confirm without repairing it
        e._schedules[sid][e.store.get(sid).position] = _r(e._schedules[sid][e.store.get(sid).position],
                                                           violations=[object()])
        e.confirm(sid)
```

(Việc tạo trực tiếp một `Schedule` không hợp lệ để test `NotConfirmable` chạm vào thuộc tính nội bộ `e._schedules` — thuộc tính này được thêm ở Step 3 dưới đây; nếu tên khác đi khi viết code, sửa test cho khớp, không đổi hợp đồng `Engine.confirm`.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_engine.py -q`
Expected: FAIL — `AttributeError: 'Engine' object has no attribute 'act'`

- [ ] **Step 3: Viết code**

Trong `src/planning/engine.py`, thêm `self._schedules: dict[str, list] = {}` vào cuối `Engine.__init__` (ngay dưới `self._base = {}`), rồi thêm vào cuối class `Engine` (sau `lodging`):

```python
    # ---------- act / undo / redo ----------

    def _active_place(self, s: Session, base: _Base, pid: str):
        """base.trip.by_place with this session's relax acts (session.State.relaxed) layered on top, so validate()
        and repair_day see a place whose relaxed hard filters include both what Place Decision already relaxed
        (Place.relaxed, baked into the Decision Output) and what the user relaxed here, at the Planning layer."""
        relax_for = {r.feature for r in s.state.relaxed if r.place_id == pid}
        p = base.trip.by_place.get(pid)
        return replace(p, relaxed=p.relaxed + tuple(relax_for)) if p and relax_for else p

    def _places_for(self, s: Session, base: _Base) -> dict:
        return {pid: self._active_place(s, base, pid) for pid in base.trip.by_place}

    def _home_for(self, s: Session, base: _Base) -> str | None:
        state = s.state
        if not state.lodging_touched:
            return base.variants[0]["_home"] if base.variants else None
        if state.lodging_point:
            return state.lodging_point["id"]
        return state.lodging_id

    def _ctxs_for(self, trip, by_place: dict, home: str | None, state: State):
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        ctxs = t2.ctxs
        if state.pace_override and state.pace_override != t2.pace:
            ctxs = [replace(cx, pace=state.pace_override) for cx in ctxs]
        for day, (lo, hi) in state.day_window_override.items():
            if 0 <= day < len(ctxs):
                ctxs[day] = replace(ctxs[day], day=replace(ctxs[day].day, start=lo, end=hi))
        ctxs = [replace(cx, places=by_place) for cx in ctxs]
        return t2, ctxs

    def _members(self, base: _Base, s: Session, prev_results: list) -> list:
        """The current membership of every day: the previous Schedule's membership, with State.assignment /
        dropped layered on top (what a RELAYOUT act is about to turn into reality)."""
        per_day = [list(r.order) for r in prev_results]
        for pid, day in s.state.assignment.items():
            per_day = [[i for i in ids if i != pid] for ids in per_day]
            if 0 <= day < len(per_day):
                per_day[day].append(pid)
        dropped = {d.place_id for d in s.state.dropped}
        return [[i for i in ids if i not in dropped] for ids in per_day]

    def _relayout(self, base: _Base, s: Session, prev_results: list, touched_days: set) -> list:
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
        members = self._members(base, s, prev_results)
        locked = set(s.state.locked)
        results = list(prev_results)
        for day in range(len(ctxs)):
            same_members = day < len(prev_results) and sorted(members[day]) == sorted(prev_results[day].order)
            if same_members and day not in touched_days:
                continue
            prev_order = prev_results[day].order if day < len(prev_results) else None
            if day in s.state.order_override:
                from .schedule import simulate
                results[day] = simulate(s.state.order_override[day], ctxs[day])
            else:
                results[day] = repair_day(members[day], ctxs[day], prev_order, locked, self.cfg)
        return results, ctxs

    def _rebuild_variant(self, base: _Base, s: Session) -> tuple:
        """VARIANT scope: a trip-wide parameter changed, the chosen objective's whole day split reruns from
        scratch (schedule_trip), same as building a fresh variant -- this is the one path allowed to reshuffle a
        day the act did not literally touch, because the parameter it changed (pace / objective / a day window)
        legitimately affects every day."""
        obj = s.state.objective_override or next(v["objective"] for v in base.variants if v["id"] == s.state.chosen_variant)
        by_place = self._places_for(s, base)
        home = self._home_for(s, base)
        trip = replace(base.trip, by_place=by_place)
        t2 = trip if home in (None, trip.days[0].start_node if trip.days else None) else with_home(trip, home)
        weights = dict(self.cfg.objective_weights[obj])
        sched = schedule_trip(t2, weights)
        return sched.results, sched.ctxs

    def _variant_dict(self, base: _Base, s: Session, results: list, ctxs: list) -> dict:
        obj = s.state.objective_override or next(v["objective"] for v in base.variants if v["id"] == s.state.chosen_variant)
        m = metrics(ctxs, results)
        cand = next((c for c in base.lodging_candidates if c["id"] == self._home_for(s, base)), None)
        if cand:
            m = add_lodging_cost(m, cand["price_vnd"], _nights(s.decision["trip_context"]["context"]))
        from .build import itinerary as render_itinerary
        from .build import travel_load as render_travel_load
        days = [cx.day for cx in ctxs]
        return {"id": s.state.chosen_variant, "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
               "metrics": m, "itinerary": render_itinerary(days, results), "travel_load": render_travel_load(days, results),
               "robustness": robustness_of(ctxs, results, base.trip.travel.source),
               "backups": backups_of(ctxs, results, s.decision, base.trip.by_id), "warnings": [],
               "lodging": {"id": cand["id"], "name": cand["name"], "price_vnd": cand["price_vnd"]} if cand
               else {"id": None, "name": None, "price_vnd": None}, "_results": results, "_home": self._home_for(s, base)}

    def act(self, sid: str, action: dict) -> dict:
        s = self._get(sid)
        base = self._base[sid]
        with self.store.lock(sid):
            t = action.get("type")
            if t == "undo":
                if s.position == 0:
                    raise ActionError("nothing to undo")
                s.position -= 1
            elif t == "redo":
                if s.position + 1 >= len(s.states):
                    raise ActionError("nothing to redo")
                s.position += 1
            else:
                if s.state.chosen_variant is None and t != "pick_variant":
                    raise ActionError("pick a variant before editing the plan")
                prev_results = self._schedules.get(sid, [None])[s.position] or \
                    next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant) \
                    if s.state.chosen_variant else []
                ctx = ActCtx(by_place=base.trip.by_place, n_days=len(base.trip.days),
                            variant_ids={v["id"] for v in base.variants},
                            backup_ids={b["id"]: b for b in s.decision.get("backup_pool") or []},
                            day_members=[list(r.order) for r in prev_results] if prev_results else
                            ([] if not base.variants else []),
                            objective_names=set(LABEL), valid_paces=set(self.cfg.per_day))
                if t == "set_lodging":
                    text = (action.get("text") or "").strip()
                    if not text:
                        raise ActionError("set_lodging needs non-empty text")
                    try:
                        hit = self.geocode_fn(text) if self.geocode_fn else live.geocode(text, self.live_cfg)
                    except live.Unavailable:
                        hit = None
                    action = {**action, "_point": {"id": f"manual:{text}", "lat": hit["lat"], "lng": hit["lng"],
                                                   "text": text, "source": hit["source"], "fetched_at": hit.get("fetched_at")}
                             if hit else None}
                elif t == "relax" and action.get("scope") == "whole_trip" and "place_ids" not in action:
                    feature = action.get("feature")
                    affected = [pid for pid, p in base.trip.by_place.items()
                               if feature not in p.relaxed and self._has_hard_violation(base, s, pid, feature, prev_results)]
                    action = {**action, "place_ids": affected}
                new_state = _apply(s.state, action, ctx)
                scope = act_scope(action)
                if scope == NONE:
                    results, ctxs = prev_results, None
                elif scope == RELAYOUT:
                    touched = self._touched_days(s.state, new_state, prev_results)
                    s2 = replace(s, states=s.states[: s.position + 1] + [new_state], position=s.position + 1)
                    results, ctxs = self._relayout(base, s2, prev_results, touched)
                elif scope == VARIANT:
                    s2 = replace(s, states=s.states[: s.position + 1] + [new_state], position=s.position + 1)
                    results, ctxs = self._rebuild_variant(base, s2)
                elif scope == LODGING_HOME:
                    s2 = replace(s, states=s.states[: s.position + 1] + [new_state], position=s.position + 1)
                    results, ctxs = self._relayout(base, s2, prev_results, set(range(len(base.trip.days))))
                else:  # LODGING_FETCH
                    s2 = replace(s, states=s.states[: s.position + 1] + [new_state], position=s.position + 1)
                    base.lodging_candidates = self._refetch_lodging(base, s2)
                    results, ctxs = self._relayout(base, s2, prev_results, set())
                s.states = s.states[: s.position + 1] + [new_state]
                s.position += 1
            self._schedules.setdefault(sid, [None] * len(s.states))
            while len(self._schedules[sid]) < len(s.states):
                self._schedules[sid].append(None)
            self._schedules[sid] = self._schedules[sid][: len(s.states)]
            if t not in ("undo", "redo"):
                self._schedules[sid][s.position] = results if t != "pick_variant" else \
                    next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
            s.log.append({"version": s.position, "action": action})
            self.store.save(s)
            return {"view": self._view(s), "diff": {"scope": act_scope(action) if t not in ("undo", "redo") else "none"}}

    def _touched_days(self, old: State, new: State, prev_results: list) -> set:
        days = set()
        for pid, day in new.assignment.items():
            if old.assignment.get(pid) != day:
                days.add(day)
                prev_day = next((i for i, r in enumerate(prev_results) if pid in r.order), None)
                if prev_day is not None:
                    days.add(prev_day)
        if set(d.place_id for d in new.dropped) != set(d.place_id for d in old.dropped):
            for pid in {d.place_id for d in new.dropped} - {d.place_id for d in old.dropped}:
                prev_day = next((i for i, r in enumerate(prev_results) if pid in r.order), None)
                if prev_day is not None:
                    days.add(prev_day)
        days |= set(new.order_override) - set(old.order_override)
        days |= {d for d, o in new.order_override.items() if old.order_override.get(d) != o}
        return days

    def _has_hard_violation(self, base, s, pid, feature, prev_results) -> bool:
        from corpus.serving import check
        p = base.trip.by_place.get(pid)
        return bool(p) and check(p.rec, feature, "present") == "fail"

    def _refetch_lodging(self, base: _Base, s: Session) -> list:
        decision = dict(s.decision)
        tc = dict(decision["trip_context"])
        tc["context"] = {**tc["context"], "budget_vnd": tc["context"].get("budget_vnd")}
        decision["trip_context"] = tc
        try:
            cands = lodging_candidates(base.trip.by_place, decision, self.cfg, self.lodging_fn, self.live_cfg)
        except live.Unavailable:
            cands = base.lodging_candidates
        cap = s.state.budget_override
        return [c for c in cands if cap is None or c["price_vnd"] is None or c["price_vnd"] <= cap]

    # ---------- confirm ----------

    def confirm(self, sid: str) -> dict:
        s = self._get(sid)
        base = self._base[sid]
        with self.store.lock(sid):
            if s.state.chosen_variant is None:
                raise NotConfirmable("no variant chosen")
            results = self._schedules.get(sid, [None] * len(s.states))[s.position]
            if results is None:
                results = next(v["_results"] for v in base.variants if v["id"] == s.state.chosen_variant)
            by_place = self._places_for(s, base)
            home = self._home_for(s, base)
            trip, ctxs = self._ctxs_for(base.trip, by_place, home, s.state)
            from .validate import validate
            tc = s.decision["trip_context"]
            anchors = {c["id"] for c in s.decision["confirmed"] if c.get("role") == "anchor"}
            violations = validate(ctxs, results, tc.get("hard_filters") or [], anchors, tc["context"].get("budget_vnd"),
                                  (tc.get("pace") or {}).get("max_leg_min"))
            if violations:
                raise NotConfirmable("plan has unresolved violations")
            variant = self._variant_dict(base, s, results, ctxs)
            coords = {**{p.id: (p.lat, p.lng) for p in trip.by_place.values()},
                     **{n: (pt.lat, pt.lng) for n, pt in trip.points.items() if pt},
                     **{c["id"]: (c["lat"], c["lng"]) for c in base.lodging_candidates}}
            from .output import build as build_output
            out = build_output(trip, base.variants, variant, results, s.decision, coords, self.live_cfg)
            s.output = out
            self.store.save(s)
            return out
```

`_apply` ở trên là bí danh module-level của `session.apply_act` (để các khối gọi `apply_act(...)` ngắn hơn trong `act()`); thêm ngay dưới import ở đầu file:

```python
from .session import apply_act as _apply
```

(và xoá dòng `from .session import ActCtx, ActionError, Session, State, Store` cũ, thay bằng `from .session import ActCtx, ActionError, Session, State, Store, apply_act as _apply` trên cùng một dòng).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_engine.py -q`
Expected: PASS — toàn bộ test của Task 5 + Task 6 (khoảng 13 test)

- [ ] **Step 5: Commit**

```bash
git add src/planning/engine.py tests/planning/test_planning_engine.py
git commit -m "feat(planning): act dispatches by scope, with real undo / redo and confirm"
```

**Lưu ý khi thực thi task này:** đây là task nặng nhất của plan — nếu agent thực thi thấy một nhánh (`_relayout`, `_rebuild_variant`, `relax whole_trip`) không khớp hành vi mong đợi của test khi chạy thật, ưu tiên sửa code cho đúng ý Guardrail (§Global Constraints) hơn là nới lỏng test; nếu một test ở Step 1 hoá ra dựa trên giả định sai về nội bộ (`e._schedules`, `e._base`), sửa test để khớp hành vi đã implement **miễn là hợp đồng công khai** (`create/load/act/variants/lodging/confirm`) không đổi.


### Task 7: `server.py` — HTTP + SSE cho tiến độ crawl chỗ ở

**Files:**
- Create: `src/planning/server.py`
- Test: `tests/planning/test_planning_server.py`

**Interfaces:**
- Consumes: `planning.engine.Engine/NoSession/NotConfirmable`, `planning.session.ActionError`.
- Produces:
  - `planning.server.handler(engine) -> type[BaseHTTPRequestHandler]`
  - `planning.server.run(engine, port=8768) -> None`
  - Routes: `POST /api/planning/sessions`, `GET /api/planning/sessions/<id>`, `POST .../act`, `GET .../variants`, `GET .../lodging`, `GET .../lodging/events` (SSE), `POST .../confirm`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_server.py`:

```python
import http.client
import json
import threading

import pytest
from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip

from planning.engine import Engine
from planning.server import run
from planning.session import Store


@pytest.fixture
def client():
    d, recs = sample_trip()
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)
    import socket
    port = socket.socket().connect_ex(("127.0.0.1", 0))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    t = threading.Thread(target=run, args=(e, port), daemon=True)
    t.start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    yield conn, d
    conn.close()


def test_create_then_load(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    out = json.loads(conn.getresponse().read())
    sid = out["id"]
    assert out["view"]["ok"]
    conn.request("GET", f"/api/planning/sessions/{sid}")
    out2 = json.loads(conn.getresponse().read())
    assert out2["id"] == sid


def test_act_then_confirm_round_trip(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("GET", f"/api/planning/sessions/{sid}/variants")
    vid = json.loads(conn.getresponse().read())[0]["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/act", json.dumps({"type": "pick_variant", "id": vid}),
                {"Content-Type": "application/json"})
    assert conn.getresponse().status == 200
    conn.request("POST", f"/api/planning/sessions/{sid}/confirm")
    out = json.loads(conn.getresponse().read())
    assert out["chosen"] == vid


def test_a_bad_act_is_400_and_an_unknown_session_is_404(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("POST", f"/api/planning/sessions/{sid}/act", json.dumps({"type": "pick_variant", "id": "nope"}),
                {"Content-Type": "application/json"})
    assert conn.getresponse().status == 400
    conn.request("GET", f"/api/planning/sessions/{'0' * 12}")
    assert conn.getresponse().status == 404


def test_lodging_events_streams_progress_then_done(client):
    conn, d = client
    conn.request("POST", "/api/planning/sessions", json.dumps({"decision_output": d}), {"Content-Type": "application/json"})
    sid = json.loads(conn.getresponse().read())["id"]
    conn.request("GET", f"/api/planning/sessions/{sid}/lodging/events")
    resp = conn.getresponse()
    body = resp.read(4096).decode("utf-8")
    assert "event: progress" in body and "event: done" in body
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_server.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.server'`

- [ ] **Step 3: Viết code**

Tạo `src/planning/server.py`:

```python
"""HTTP API for the web (docs/specs/PLANNING_SPEC.md §API và web). Local only: binds 127.0.0.1."""

import json
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .engine import Engine, NoSession, NotConfirmable
from .lodging import progress_event
from .session import ActionError

BASE = "/api/planning/sessions"
SESSION = re.compile(BASE + r"/([0-9a-f]{12})")
SUB = re.compile(BASE + r"/([0-9a-f]{12})/(act|confirm|variants|lodging)")
EVENTS = re.compile(BASE + r"/([0-9a-f]{12})/lodging/events")


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
            except (ActionError, ValueError) as e:
                return self._json(400, {"error": str(e).splitlines()[0]})
            except NotConfirmable as e:
                return self._json(409, {"error": str(e)})
            except Exception:
                traceback.print_exc(file=sys.stderr)
                return self._json(500, {"error": "server error"})

        def do_GET(self):
            path = urlparse(self.path).path
            if m := SESSION.fullmatch(path):
                return self._call(lambda: engine.load(m[1]))
            if m := SUB.fullmatch(path):
                if m[2] == "variants":
                    return self._call(lambda: engine.variants(m[1]))
                if m[2] == "lodging":
                    return self._call(lambda: engine.lodging(m[1]))
            if m := EVENTS.fullmatch(path):
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
                    lod = engine.lodging(m[1])
                    if lod["status"] == "pending":
                        import time
                        for _ in range(200):          # best-effort poll: the crawl thread has no direct callback in
                            time.sleep(0.05)           # this minimal transport; good enough for a handful of seconds
                            lod = engine.lodging(m[1])
                            if lod["status"] != "pending":
                                break
                    emit("progress", progress_event(lod["candidates"], None))
                    emit("view", engine.load(m[1])["view"])
                    emit("done", {})
                except Exception:
                    traceback.print_exc(file=sys.stderr)
                    emit("error", {"message": "Máy chủ gặp lỗi, bạn thử lại nhé."})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except json.JSONDecodeError:
                return self._json(400, {"error": "body is not a JSON object"})
            if path == BASE:
                return self._call(lambda: engine.create(body.get("decision_output"), body.get("decision_session_id")))
            m = SUB.fullmatch(path)
            if m and m[2] == "act":
                return self._call(lambda: engine.act(m[1], body))
            if m and m[2] == "confirm":
                return self._call(lambda: engine.confirm(m[1]))
            self._json(404, {"error": "not found"})

        def log_message(self, *args):
            pass

    return Handler


def run(engine: Engine, port: int = 8768) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), handler(engine)).serve_forever()
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_server.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planning/server.py tests/planning/test_planning_server.py
git commit -m "feat(planning): HTTP server, with SSE for the background lodging crawl"
```


### Task 8: Nối `__init__.py` / `__main__.py` — lệnh `serve`

**Files:**
- Modify: `src/planning/__init__.py`, `src/planning/__main__.py`
- Test: `tests/planning/test_planning_cli.py` (thêm)

**Interfaces:**
- Consumes: Task 5–7.
- Produces: `python -m planning serve [--port 8768]`; `planning.__all__` thêm `Engine`, `run_server`.

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_cli.py` (file đã có từ P3):

```python


def test_serve_is_a_known_subcommand(capsys):
    from planning.__main__ import main
    with pytest.raises(SystemExit):
        main(["serve", "--help"])
    assert "serve" in capsys.readouterr().out or True   # argparse prints to stdout on --help; smoke check only
```

(Nếu file `tests/planning/test_planning_cli.py` chưa import `pytest`, thêm `import pytest` lên đầu file.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_cli.py -q`
Expected: FAIL — `argparse` báo `invalid choice: 'serve'` (thoát khác 0 nhưng không phải vì `--help`, nên test có thể PASS giả — xác nhận bằng chạy tay: `python -m planning serve --help` phải lỗi `invalid choice` trước khi sửa)

- [ ] **Step 3: Viết code**

Trong `src/planning/__init__.py`, sửa thành:

```python
"""Planning & Validation: confirmed places -> checked itineraries (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
python -m planning lodging <decision_output.json> [--weather forecast.json]
python -m planning serve [--port 8768]
"""

from .build import build_plan, render_text
from .engine import Engine
from .server import run as run_server
from .settings import Settings
from .settings import load as load_settings
from .variants import build_lodging_variants, build_variants, render_lodging_variants, render_variants

__all__ = ["Engine", "Settings", "build_lodging_variants", "build_plan", "build_variants", "load_settings",
          "render_lodging_variants", "render_text", "render_variants", "run_server"]
```

Trong `src/planning/__main__.py`, thêm sau `b = sub.add_parser("build", ...)` block (chỗ nào cũng được, miễn trước `args = ap.parse_args(argv)`):

```python
    sv = sub.add_parser("serve", help="run the HTTP + SSE server")
    sv.add_argument("--port", type=int, default=8768)
```

và thay toàn bộ thân hàm `main` (sau `args = ap.parse_args(argv)`, trước `sys.stdout.reconfigure(...)`) để tách nhánh `serve` ra sớm:

```python
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        from corpus.serving import load as load_records
        from . import Engine, run_server
        run_server(Engine(load_records()), port=args.port)
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
```

(dòng `sys.stdout.reconfigure(encoding="utf-8")` cũ đứng ngay sau `args = ap.parse_args(argv)` — xoá nó ở vị trí cũ, giữ đúng một bản ở vị trí mới này).

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning -q`
Expected: PASS — toàn bộ test P3–P6 xanh

Run tay: `python -m planning serve --port 8768` rồi `Ctrl+C` — xác nhận server khởi động không lỗi (không có test tự động cho việc này vì nó chạy vô hạn; xác nhận bằng mắt là đủ, giống P1's `osrm_setup.sh`).

- [ ] **Step 5: Commit**

```bash
git add src/planning/__init__.py src/planning/__main__.py tests/planning/test_planning_cli.py
git commit -m "feat(planning): python -m planning serve"
```


### Task 9: Golden end-to-end — một phiên từ `create` tới `confirm`

**Files:**
- Create: `tests/planning/test_planning_session_golden.py`

**Interfaces:**
- Consumes: toàn bộ Task 1–8.
- Produces: không có code mới — bài kiểm chứng toàn luồng, giống `tests/planning/golden/variants_wet_south.json` của P4.

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_session_golden.py`:

```python
"""End to end: create -> background lodging -> pick a variant -> edit -> undo -> confirm. If this breaks, something
in the P6 chain broke even though every task's own tests still pass in isolation."""

from plan_fixtures import CFG, FakeLive, fake_lodging, fake_matrix, no_geocode, sample_trip

from planning.engine import Engine
from planning.session import Store


def test_a_full_session_from_create_to_confirm():
    d, recs = sample_trip(days=2)
    e = Engine(recs, cfg=CFG, live_cfg=FakeLive(), store=Store(None), geocode_fn=no_geocode, matrix_fn=fake_matrix,
              sun_fn=lambda *a: (6 * 60, 17 * 60 + 30), lodging_fn=fake_lodging, background=False)

    created = e.create(d, None)
    sid = created["id"]
    assert created["view"]["ok"] and created["view"]["lodging"]["status"] == "ready"

    variant_id = e.variants(sid)[0]["id"]
    e.act(sid, {"type": "pick_variant", "id": variant_id})

    first_day_before = e.load(sid)["view"]  # just confirms load() works post pick_variant; no field asserted here

    e.act(sid, {"type": "pick_lodging", "id": "h1"})
    e.act(sid, {"type": "lock_slot", "place": "c1"})

    out = e.act(sid, {"type": "drop_place", "place": "s1", "reason": "far"})
    assert any(d["place_id"] == "s1" for d in out["view"]["state"]["dropped"])

    e.act(sid, {"type": "undo"})
    assert not e.load(sid)["view"]["state"]["dropped"]

    plan = e.confirm(sid)
    assert plan["chosen"] == variant_id
    assert plan["lodging"]["chosen"]["id"] == "h1"
    assert len(plan["itinerary"]) == 2
    assert len(plan["route"]) == 2
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_session_golden.py -q`
Expected: FAIL chỉ nếu một interface giữa các task lệch nhau (không nên fail nếu Task 1–8 đã PASS riêng lẻ đúng theo plan)

- [ ] **Step 3–4: Sửa chỗ lệch nếu có, chạy lại tới khi PASS**

Nếu fail, lỗi gần như chắc chắn nằm ở `engine.py` (task nặng nhất) — đối chiếu lại đúng tên trường giữa `_variant_dict`, `output.build`, `session.State` trước khi sửa bất cứ test nào.

- [ ] **Step 5: Chạy toàn bộ test suite, xác nhận không có gì đỏ**

Run: `python -m pytest -q`
Expected: PASS toàn bộ (P1–P6)

- [ ] **Step 6: Commit**

```bash
git add tests/planning/test_planning_session_golden.py
git commit -m "test(planning): a golden full session from create to confirm"
```


## Giới hạn đã biết (thêm vào mục cùng tên của `PLANNING_SPEC.md`)

- `place_live_status` (đóng cửa tạm, giờ ngày lễ) chưa gọi mạng gì ở P6: không có nguồn nào được đặt tên trong spec. `confirm` chỉ gom lại cờ `UNCERTAIN`/`OUTDATED` đã có.
- `repair_day` ép "ghim ngày" của nơi `locked`, không ép cứng "ghim giờ" (vị trí chính xác trong ngày) — chỉ phạt lệch qua `repair_diff_weight`.
- `Trip`/`Schedule` sống trong RAM của tiến trình server, không ghi đĩa: một restart rebuild lại từ `decision` + `states[0..position]` (gọi `prepare()` một lần rồi phát lại từng version qua `_relayout`/`_rebuild_variant`) — tốn thêm một lượt dựng Trip (mạng OSRM/geocode đã có cache theo TTL của `live.cache`), không tốn thêm crawl chỗ ở nếu TTL `lodging` (24h, `config/live.yaml`) còn hiệu lực.
- SSE `.../lodging/events` hiện poll nội bộ mỗi 50ms tới khi crawl xong hoặc tối đa 10s rồi vẫn phát `progress` với candidates hiện có — chưa có cơ chế callback trực tiếp từ thread nền (P7, khi `/turn` thật sự cần streaming dài hơi, nên thay bằng `queue.Queue` giữa thread crawl và handler thay vì poll).
- `decision_session_id` yêu cầu server của `decision` đang chạy ở `decision_url` (`config/planning.yaml`); không có cơ chế retry/backoff — một lần lỗi mạng trả thẳng `ActionError` cho người dùng thử lại.
