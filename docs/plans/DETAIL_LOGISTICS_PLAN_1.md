# Kế hoạch 1 — Hiện hết gợi ý, chat thu hẹp, chuyển cảnh (phần B)

> **Cho agent thực thi:** BẮT BUỘC dùng superpowers:subagent-driven-development (khuyên dùng) hoặc superpowers:executing-plans để làm từng task. Bước dùng checkbox (`- [ ]`).

**Mục tiêu:** Explore hiện dần mọi nơi qua giới hạn cứng (cuộn tới đâu tải tới đó); người dùng nhắn điều họ muốn, bot Place Decision chuyển phần gu cho Trip Understanding rồi Place Decision chạy lại, màn đổi ít nhất có thể, chuyển cảnh mượt.

**Kiến trúc:** Decision giữ thứ hạng đầy đủ mỗi nhóm và một **cửa sổ đang hiện** (`State.shown`) trong session; mỗi lần dựng lại, cửa sổ mới được gộp với cửa sổ cũ (giữ chỗ / lấp ô / thay hết). Op mới `trip` của bot Decision được harness chuyển sang operation mới `refine` của Trip, rồi `decision.rebase`. Web nhận `change` mỗi nhóm để chạy chuyển cảnh.

**Tech stack:** Python 3.12 + pydantic + pytest (`.venv/bin/python -m pytest`), React 19 + TypeScript + Vite (`cd web && npx tsc -b`), Playwright 1.52 (`web/scripts/shots_app.mjs`).

**Spec:** `docs/plans/DETAIL_LOGISTICS_SPEC.md` §2 (đọc cùng file này).

## Ràng buộc chung

- Tài liệu tiếng Việt; code, comment, identifier, commit message tiếng Anh (`RULE.md` §0).
- Module chỉ gọi nhau qua public API (`__init__.py` / `Tools`); không deep import (`RULE.md` §2).
- Không bịa: nét của nơi X chỉ lấy từ catalog; không có bằng chứng → `unknown` (`AGENTS.md`).
- Soft là prior, không phải constraint: nét "giống X" chỉ đổi thứ hạng, không loại nơi nào.
- `page_size` = 24, `keep_factor` = 2, `replace_below` = 0.3 — trong `config/decision.yaml`.
- Chuyển cảnh: giữ đứng yên / trượt FLIP 280 ms; gỡ fade + scale 180 ms; mới fade-up lệch 40 ms; thay hết cross-fade 240 ms; `prefers-reduced-motion` → chỉ fade.
- Không sửa / nới test cũ chỉ để pass; test cũ đổi kỳ vọng chỉ khi hành vi được spec đổi (ghi rõ trong task).
- Commit chỉ file của task (`git commit -- <files>`): branch đang có nhiều thay đổi dở của người dùng.

## Trọng tâm review

1. Nhóm có ít nơi hơn `page_size` hoặc rỗng sau lọc → cửa sổ không lỗi chỉ số, web không gọi trang tiếp mãi (Task 1, Task 6).
2. Người dùng chọn một nơi trong lưới → nơi đó **đứng yên** đúng chỗ, không nhảy lên đầu nhóm (Task 2).
3. Bot trả op `trip` nhưng trip session không có (journey cũ) → lượt vẫn xong, chỉ không rebase (Task 5).
4. "Không thích quán giống X" với X không có trong catalog → không có draft nào, bot nói không tìm thấy X, danh sách giữ nguyên (Task 4).
5. Cuộn nhanh khi đang tải trang → không gửi trùng request, không chèn trùng thẻ (Task 6).

---

### Task 1: Cửa sổ hiện và gộp ít xáo trộn (`decision/window.py`)

**Files:**
- Create: `src/decision/window.py`
- Modify: `src/decision/settings.py` (thêm 3 trường), `config/decision.yaml` (thêm 3 khóa)
- Test: `tests/decision/test_window.py`

**Interfaces:**
- Produces: `merge(old: list[str], ranked: list[str], pinned: set[str], cfg) -> tuple[list[str], dict]` — trả cửa sổ mới và `{"kept": int, "added": int, "removed": int, "replaced_all": bool}`. `pinned` = nơi đã chọn trong nhóm: luôn giữ.
- Produces: `extend(window: list[str], ranked: list[str], cfg) -> list[str]` — nối `page_size` nơi tiếp theo chưa có trong cửa sổ.
- Produces: `Settings.page_size: int`, `Settings.keep_factor: float`, `Settings.replace_below: float`.

- [ ] **Step 1: Viết test hỏng**

```python
# tests/decision/test_window.py
from types import SimpleNamespace

from decision.window import extend, merge

CFG = SimpleNamespace(page_size=4, keep_factor=2, replace_below=0.3)
R = [f"P{i}" for i in range(20)]


def test_first_window_is_the_top_page():
    win, ch = merge([], R, set(), CFG)
    assert win == ["P0", "P1", "P2", "P3"]
    assert ch == {"kept": 0, "added": 4, "removed": 0, "replaced_all": False}


def test_same_ranking_changes_nothing():
    win, ch = merge(["P0", "P1", "P2", "P3"], R, set(), CFG)
    assert win == ["P0", "P1", "P2", "P3"] and ch["added"] == ch["removed"] == 0


def test_dropped_place_slot_is_filled_in_place_by_the_best_new_one():
    win, ch = merge(["P0", "P1", "P2", "P3"], ["P0", "P2", "P3", "P9", "P8"], set(), CFG)
    assert win == ["P0", "P9", "P2", "P3"]
    assert ch == {"kept": 3, "added": 1, "removed": 1, "replaced_all": False}


def test_a_kept_place_far_down_the_new_ranking_is_removed():
    ranked = ["N0", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "P0", "P1", "P2", "P3"]
    win, ch = merge(["P0", "P1", "P2", "P3"], ranked, set(), CFG)
    assert ch["replaced_all"] and win == ["N0", "N1", "N2", "N3"]


def test_pinned_places_stay_in_place_even_when_ranked_low():
    ranked = ["N0", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "P1"]
    win, _ = merge(["P0", "P1", "P2", "P3"], ranked, {"P1"}, CFG)
    assert win[1] == "P1" and "P0" not in win


def test_extend_adds_the_next_page_without_duplicates():
    assert extend(["P0", "P2"], R, CFG) == ["P0", "P2", "P1", "P3", "P4", "P5"]
    assert extend(R, R, CFG) == R


def test_short_ranking_never_overflows():
    win, _ = merge([], ["P0", "P1"], set(), CFG)
    assert win == ["P0", "P1"]
    win, ch = merge(["P0", "P1", "P2"], ["P0"], set(), CFG)
    assert win == ["P0"] and ch["removed"] == 2
```

- [ ] **Step 2: Chạy test, xác nhận hỏng**

Run: `.venv/bin/python -m pytest tests/decision/test_window.py -q`
Expected: FAIL `ModuleNotFoundError: No module named 'decision.window'`

- [ ] **Step 3: Viết code tối thiểu**

```python
# src/decision/window.py
"""The window of places shown per display group, and how it survives a new ranking (docs/PLACE_DECISION.md §9.4):
places that still match stay where they are, freed slots take the best new places, a mostly stale window is
replaced whole."""


def _change(old: list[str], new: list[str], replaced_all: bool) -> dict:
    o, n = set(old), set(new)
    return {"kept": len(o & n), "added": len(n - o), "removed": len(o - n), "replaced_all": replaced_all}


def merge(old: list[str], ranked: list[str], pinned: set[str], cfg) -> tuple[list[str], dict]:
    if not old:
        win = ranked[: cfg.page_size]
        return win, _change([], win, False)
    pos = {pid: i for i, pid in enumerate(ranked)}
    limit = int(cfg.keep_factor * len(old))
    keep = {p for p in old if p in pinned or pos.get(p, limit) < limit}
    size = min(len(old), len(ranked) + len(pinned - set(ranked)))
    replaced_all = len(keep) < cfg.replace_below * len(old)
    if replaced_all:  # mostly stale: only the user's own picks keep their slots
        keep = {p for p in old if p in pinned}
    fresh = iter([p for p in ranked if p not in keep])
    win = []
    for p in old:
        if p in keep:
            win.append(p)
        elif (nxt := next(fresh, None)) is not None:
            win.append(nxt)
    while len(win) < size and (nxt := next(fresh, None)) is not None:
        win.append(nxt)
    return win, _change(old, win, replaced_all)


def extend(window: list[str], ranked: list[str], cfg) -> list[str]:
    have = set(window)
    return window + [p for p in ranked if p not in have][: cfg.page_size]
```

Thêm vào `Settings` (`src/decision/settings.py`, cạnh `unverified_show`):

```python
    page_size: int
    keep_factor: float
    replace_below: float
```

Thêm vào `config/decision.yaml` (sau `unverified_show: 12`):

```yaml
page_size: 24               # places per display group shown at once; scrolling loads the next page
keep_factor: 2              # a shown place survives a new ranking while it ranks within keep_factor x the window
replace_below: 0.3          # fewer survivors than this share of the window -> replace the window whole
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/decision/test_window.py tests/decision/test_basics.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/decision/window.py tests/decision/test_window.py
git commit -m "feat(decision): shown window that survives a new ranking" -- src/decision/window.py tests/decision/test_window.py src/decision/settings.py config/decision.yaml
```

---

### Task 2: Pipeline trả thứ hạng đầy đủ theo cửa sổ; engine lưu cửa sổ, đọc trang, rebase trả diff

**Files:**
- Modify: `src/decision/pipeline.py` (`Result`, `run`)
- Modify: `src/decision/cards.py:89` (`card(..., top=False)` → trường `"top"`)
- Modify: `src/decision/session.py` (`State.shown`)
- Modify: `src/decision/engine.py` (`_result`, `create`, method mới `page`)
- Modify: `src/decision/tools.py` (`read` "page", `rebase` trả `diff`)
- Test: `tests/decision/test_pipeline.py`, `tests/decision/test_decision_engine.py`

**Interfaces:**
- Consumes: `merge`, `extend`, `Settings.page_size` (Task 1).
- Produces: view nhóm `{"id", "label", "cards", "total": int}`; card có `"top": bool`; view có `"change": {group_id: {kept, added, removed, replaced_all}}`.
- Produces: `State.shown: dict[str, list[str]]`.
- Produces: `Engine.page(sid: str, group: str) -> dict` trả `{"view": view}`; `Tools.read(sid, "page", {"group": g})`.
- Produces: `Tools.rebase(...)` trả `{"id", "view", "diff"}`.

- [ ] **Step 1: Viết test hỏng**

Thêm vào `tests/decision/test_pipeline.py`:

```python
def many_cafes(n):
    return Data([srec(f"CAFE{i:02d}", features={"steep_or_stairs": "absent", "cozy_decor": "present"},
                      lng=108.44 + i / 1000) for i in range(n)])


def test_window_shows_a_page_and_reports_the_total():
    res = run(session(), many_cafes(40), CFG)
    chill = next(g for g in res.view["groups"] if g["id"] == "chill")
    assert len(chill["cards"]) == CFG.page_size and chill["total"] == 40
    assert any(c["top"] for c in chill["cards"]) and not all(c["top"] for c in chill["cards"])
    assert res.shown["chill"] == [c["id"] for c in chill["cards"]]


def test_chosen_place_stays_where_it_was_in_the_window():
    data = many_cafes(40)
    first = run(session(), data, CFG)
    ids = first.shown["chill"]
    st = State(selected=[ids[5]], shown=first.shown)
    again = run(session(state=st), data, CFG)
    assert again.shown["chill"][5] == ids[5]
    assert again.view["change"]["chill"]["added"] == 0


def test_hard_filter_still_fail_closed_with_full_ranking():
    v = run(session(), data(), CFG).view
    shown = {c["id"] for g in v["groups"] for c in g["cards"]}
    assert "STEEP" not in shown and "UNK" not in shown
```

Thêm vào `tests/decision/test_decision_engine.py`:

```python
def test_page_extends_the_window_and_is_kept_in_the_session():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    e = Engine(Data(recs), CFG, Store(None), None)
    out = e.create(trip())
    g = next(x for x in out["view"]["groups"] if x["id"] == "chill")
    assert len(g["cards"]) == CFG.page_size
    more = e.page(out["id"], "chill")["view"]
    g2 = next(x for x in more["groups"] if x["id"] == "chill")
    assert len(g2["cards"]) == 2 * CFG.page_size and [c["id"] for c in g2["cards"]][: CFG.page_size] == [c["id"] for c in g["cards"]]
    assert e.load(out["id"])["view"]["groups"] == more["groups"]


def test_first_shortlist_counts_top_and_anchors_not_the_whole_window():
    recs = [srec(f"C{i:02d}", features={"scenic_view": "present", "steep_or_stairs": "absent"}, lng=108.44 + i / 1000)
            for i in range(60)]
    e = Engine(Data(recs), CFG, Store(None), None)
    out = e.create(trip())
    s = e.store.get(out["id"])
    assert s.first_shortlist == sum(1 for g in out["view"]["groups"] for c in g["cards"] if c["top"] or c["anchor"])
    assert s.first_shortlist < len(out["view"]["shortlist"])
```

Sửa test cũ `test_create_selects_anchors_and_counts_first_shortlist` (hành vi đổi theo spec §2.1: `first_shortlist` = card `top` + anchor): thay vế `s.first_shortlist == len(out["view"]["shortlist"])` bằng
`s.first_shortlist == sum(1 for g in out["view"]["groups"] for c in g["cards"] if c["top"] or c["anchor"])`.

- [ ] **Step 2: Chạy test, xác nhận hỏng**

Run: `.venv/bin/python -m pytest tests/decision/test_pipeline.py tests/decision/test_decision_engine.py -q`
Expected: FAIL (`KeyError: 'total'`, `State` không có `shown`, `Engine` không có `page`)

- [ ] **Step 3: Viết code**

`src/decision/session.py` — trong `State`, sau `last`:

```python
    shown: dict[str, list[str]] = Field(default_factory=dict)  # display group -> ids on screen, in screen order
```

`src/decision/cards.py` — chữ ký `card(..., suggested=False, group="", top=False)` và thêm `"top": top,` vào dict trả về (cạnh `"suggested"`).

`src/decision/pipeline.py`:

```python
from .window import merge
```

`Result` thêm hai trường:

```python
    shown: dict[str, list[str]]
    ranked: dict[str, list[str]]
```

Trong `run`, thay khối từ `suggested = ...` tới hết vòng `for gid in [*cfg.display_groups, "meal"]:` bằng:

```python
    top = {c.id for c in reps}
    rest = sorted((c for c in pool if c.id not in top), key=lambda c: (-c.score, c.id))
    ranked: dict[str, list[str]] = {}
    for c in [*(x for x in chosen if x.id not in anchors), *reps, *rest]:
        ranked.setdefault(group_of.get(c.id, "sights"), []).append(c.id)

    suggested = next((c.id for c in reps if group_of[c.id] == st.suggest_group), None) if st.suggest_group else None
    want = wanted(si, st.profile)
    labels = cfg.labels["group"]

    def mk(c: Cand) -> dict:
        return card(c, si, cfg, wanted=want, chosen=c.id in st.selected, locked=c.id in st.locked,
                    anchor=c.id in anchors, alternatives=[(x.id, x.name) for x in alts.get(c.id, [])],
                    suggested=c.id == suggested, group=group_of.get(c.id, "sights"), top=c.id in top)

    groups, shown, change = [], {}, {}
    if anchors:
        groups.append({"id": "anchors", "label": labels["anchors"], "cards": [mk(cands[a]) for a in anchors],
                       "total": len(anchors)})
    for gid in [*cfg.display_groups, "meal"]:
        ids = ranked.get(gid, [])
        pinned = {c.id for c in chosen if group_of.get(c.id) == gid}
        win, ch = merge(st.shown.get(gid, []), ids, pinned, cfg)
        if win:
            shown[gid], change[gid] = win, ch
            groups.append({"id": gid, "label": labels[gid], "cards": [mk(cands[i]) for i in win], "total": len(ids)})
```

Trong `view = {...}` thêm `"change": change,`. Dòng `return` cuối:

```python
    return Result(view, cands, {k: [x.id for x in v] for k, v in alts.items()}, group_of, days, shown, ranked)
```

`src/decision/engine.py`:

`_result` (dòng ~83) — sau khi tính, lưu cửa sổ vào state (không đẩy history: cửa sổ là trạng thái màn, không phải hành động):

```python
    def _result(self, s: Session) -> Result:
        if s.id not in self._results:
            res = run(s, self.data, self.cfg)
            if res.shown != s.state.shown:
                s.state = s.state.model_copy(update={"shown": res.shown})
                self.store.save(s)
            self._results[s.id] = res
        return self._results[s.id]
```

`create` — thay `s.first_shortlist = len(res.view["shortlist"])` bằng:

```python
        s.first_shortlist = sum(1 for g in res.view["groups"] for c in g["cards"] if c["top"] or c["anchor"])
```

Method mới (sau `load`):

```python
    def page(self, sid: str, group: str) -> dict:
        """The next page of one display group: the window grows, the session keeps it."""
        s = self._get(sid)
        with self.store.lock(sid):
            res = self._result(s)
            if group not in res.ranked:
                raise ValueError(f"unknown group {group!r}")
            s.state.shown[group] = extend(s.state.shown.get(group, []), res.ranked[group], self.cfg)
            self._results.pop(s.id, None)
            self.store.save(s)
            return {"view": self._result(s).view}
```

(import `from .window import extend`.)

`src/decision/tools.py` — trong `read`, trước `raise`:

```python
        if operation == "page":
            return self.engine.page(sid, str(payload.get("group", "")))
```

`rebase` — trước khi đổi `s.search_input`, giữ view cũ; trả thêm `diff`:

```python
    def rebase(self, sid: str, payload: dict) -> dict:
        inp = StartInput.model_validate(payload)
        before = self.load(sid)["view"]
        with self.engine.store.lock(sid):
            ...  # unchanged body
        out = self.load(sid)
        return {**out, "diff": diff(before, out["view"], None)}
```

(import `from .engine import diff`.)

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/decision -q`
Expected: PASS (mọi test decision, kể cả test cũ)

- [ ] **Step 5: Đo cỡ view trên dữ liệu thật**

Run:
```bash
.venv/bin/python - <<'EOF'
import json, sys; sys.path[:0] = ["src", "tests/decision"]
from fixtures import si
from decision.pipeline import Data, run
from decision.session import Session, State
from decision.settings import default
res = run(Session(id="0"*12, search_input=si(context={"days": 3}), state=State()), Data.load(), default())
print({g["id"]: (len(g["cards"]), g["total"]) for g in res.view["groups"]}, len(json.dumps(res.view)) // 1024, "KB")
EOF
```
Expected: mỗi nhóm ≤ 24 card, `total` = 116 / 193 / 424 / 545 (±), view dưới 400 KB.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(decision): rank every candidate, show a stable window, page through it" -- src/decision/pipeline.py src/decision/cards.py src/decision/session.py src/decision/engine.py src/decision/tools.py tests/decision/test_pipeline.py tests/decision/test_decision_engine.py
```

---

### Task 3: Bot Decision có op `trip`

**Files:**
- Modify: `src/corpus/llm/tasks.py:743` (`DECISION_OPS`, prompt `DECISION_TURN`)
- Modify: `src/decision/guard.py` (`Op`, nhánh `trip`; bỏ `soft`, `unmapped`)
- Modify: `src/decision/engine.py` (`turn`: tách action `trip`, phát event `trip`)
- Test: `tests/decision/test_decision_guard.py`, `tests/decision/test_decision_engine.py`

**Interfaces:**
- Produces: action `{"type": "trip", "text": str}` (chỉ trong engine, không vào `curation.apply`).
- Produces: event `emit("trip", {"texts": [str, ...]})` phát **trước** `view` khi lượt có op `trip`.

- [ ] **Step 1: Viết test hỏng**

Trong `tests/decision/test_decision_guard.py`, hai test đang dùng `("soft", ...)` / `("unmapped", ...)`: đổi kỳ vọng theo spec §2.3 (gu đi Trip Understanding). Thêm:

```python
def test_trip_wish_becomes_a_trip_action_with_the_quoted_words():
    text = "mình không thích quán giống Cà Phê Số 1, muốn yên tĩnh hơn"
    g = guard(plan(("trip", "", "", "không thích quán giống Cà Phê Số 1"), ("trip", "", "", "muốn yên tĩnh hơn")),
              text, ALIASES, "", KEYS)
    assert g.actions == [{"type": "trip", "text": "không thích quán giống Cà Phê Số 1"},
                         {"type": "trip", "text": "muốn yên tĩnh hơn"}]


def test_trip_wish_with_a_quote_not_in_the_message_is_dropped():
    g = guard(plan(("trip", "", "", "thích cà phê sách")), "bỏ nơi thứ hai", ALIASES, "", KEYS)
    assert g.actions == []
```

(`plan(...)` là helper sẵn có của file: tuple `(op, place, value, quote)`.)

Trong `tests/decision/test_decision_engine.py`:

```python
def test_turn_with_a_trip_wish_emits_trip_before_view_and_still_applies_place_ops():
    say_plan = TurnPlan(say="Mình hiểu rồi.", updates=(
        PlanUpdate(op="trip", place="", value="", quote="muốn yên tĩnh hơn"),
        PlanUpdate(op="drop", place="P1", value="", quote="bỏ quán số 0")))
    e = engine(FakeAgent(say_plan))
    out = e.create(trip())
    events = []
    e.turn(out["id"], "bỏ quán số 0, muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    names = [ev for ev, _ in events]
    assert ("trip", {"texts": ["muốn yên tĩnh hơn"]}) in events and names.index("trip") < names.index("view")
    assert [d.place_id for d in e.store.get(out["id"]).state.dropped] != []
```

- [ ] **Step 2: Chạy test, xác nhận hỏng**

Run: `.venv/bin/python -m pytest tests/decision/test_decision_guard.py tests/decision/test_decision_engine.py -q`
Expected: FAIL (`op` không nhận `trip`)

- [ ] **Step 3: Viết code**

`src/corpus/llm/tasks.py`:

```python
DECISION_OPS = ["select", "drop", "lock", "travel", "crowd", "price", "trip", "visited"]
```

Trong prompt `DECISION_TURN`, thay hai gạch đầu dòng `soft:` và `unmapped:` bằng:

```text
- trip: a wish about the trip or the kind of place, not one place on screen: quieter, vegetarian, no stairs, near
  the centre, a budget, who comes along, "not like <a place>", "like <a place>". value "". quote = the exact words
  of that wish. Trip Understanding reads it and the list is rebuilt; do not also turn it into select or drop,
  except a drop when the user also rejects a place on screen by name.
```

`src/decision/guard.py`:

```python
Op = Literal["select", "drop", "lock", "travel", "crowd", "price", "trip", "visited"]
```

Thay hai nhánh `elif u.op == "soft":` và `elif u.op == "unmapped" ...` bằng:

```python
        elif u.op == "trip":
            actions.append({"type": "trip", "text": u.quote.strip()})
```

`src/decision/engine.py` — trong `turn`, ngay sau khi có `actions` (trước `new, done, skipped = self._apply(...)`):

```python
            trips = [a["text"] for a in actions if a.get("type") == "trip"]
            actions = [a for a in actions if a.get("type") != "trip"]
```

và ngay trước `emit("view", out)`:

```python
            if trips:
                emit("trip", {"texts": trips})
```

Khi `trips` có mà `done` rỗng: không coi là "không làm gì" — đổi dòng `say = say or (DONE if done else NONE)` thành `say = say or (DONE if done or trips else NONE)`.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/decision tests/test_llm_task.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(decision): route trip wishes out of the decision turn" -- src/corpus/llm/tasks.py src/decision/guard.py src/decision/engine.py tests/decision/test_decision_guard.py tests/decision/test_decision_engine.py
```

---

### Task 4: Trip Understanding hiểu "giống X" và operation `refine`

**Files:**
- Create: `src/trip/domain/traits.py`
- Modify: `src/trip/agent/nodes.py` (`_prepare`: tính `compared`), `src/trip/agent/prompt.py` (`prompt_fields(..., compared=())`), `src/corpus/llm/tasks.py` (prompt `TRIP_TURN`: luật so sánh)
- Modify: `src/trip/domain/guard.py` (`guard(..., compared=None)`)
- Modify: `src/trip/api/engine.py` (method `refine`), `src/trip/api/tools.py` (`apply` nhận `"refine"`), `src/trip/skills.yaml` (cho phép `trip.refine`)
- Test: `tests/trip/test_traits.py`, `tests/trip/test_guard.py`, `tests/trip/test_engine.py`

**Interfaces:**
- Produces: `compared_places(text: str, catalog: Catalog) -> list[dict]` → `[{"id", "name", "traits": [{"feature", "value", "n"}]}]`, tối đa 2 nơi, mỗi nơi ≤ 4 nét.
- Produces: `guard(plan, state, text, turn, catalog, cfg, heard, compared=None)`.
- Produces: `Tools.apply(sid, "refine", {"text": str}, emit)`; event `done {"search_input"}` khi compile được, `say` như lượt thường; **không** phát `card`.

- [ ] **Step 1: Viết test hỏng**

```python
# tests/trip/test_traits.py
from trip_fixtures import rec

from trip.domain.traits import compared_places
from trip.infrastructure.catalog import Catalog


def cat():
    return Catalog.from_records([
        rec(1, "Cà Phê Ồn Ào Phố Núi", {"noise": ("loud", 12), "crowd": ("high", 8), "scenic_view": ("present", 3)}),
        rec(2, "Cà Phê Một", {"noise": ("quiet", 9), "crowd": ("low", 4), "scenic_view": ("present", 5)}),
        rec(3, "Cà Phê Hai", {"noise": ("quiet", 7), "crowd": ("low", 3), "scenic_view": ("present", 6)}),
    ], n_min=1)


def test_distinctive_traits_of_the_named_place():
    out = compared_places("mình không thích quán giống Cà Phê Ồn Ào Phố Núi", cat())
    assert out[0]["name"] == "Cà Phê Ồn Ào Phố Núi"
    assert out[0]["traits"] == [{"feature": "noise", "value": "loud", "n": 12}, {"feature": "crowd", "value": "high", "n": 8}]


def test_no_cue_or_unknown_place_gives_nothing():
    assert compared_places("muốn yên tĩnh hơn", cat()) == []
    assert compared_places("không thích quán giống Highlands", cat()) == []
```

Thêm vào `tests/trip/test_guard.py`:

```python
COMPARED = [{"id": "0x1:0x1", "name": "Cà Phê Ồn Ào Phố Núi",
             "traits": [{"feature": "noise", "value": "loud", "n": 12}, {"feature": "crowd", "value": "high", "n": 8}]}]
LIKE = "không thích quán giống Cà Phê Ồn Ào Phố Núi"


def test_inferred_soft_from_a_compared_place_is_kept_only_for_its_traits(catalog, cfg):
    p = plan(u("soft", "noise=loud:avoid", LIKE, "add", "inferred"), u("soft", "cozy_decor=present:avoid", LIKE, "add", "inferred"))
    g = guard(p, framed(), LIKE, 2, catalog, cfg, heard=LIKE, compared=COMPARED)
    assert "noise=loud" in g.state.soft and "cozy_decor=present" not in g.state.soft
    assert any("not a trait" in line for line in g.log)
```

Thêm vào `tests/trip/test_engine.py` (dùng fixture engine + `FakeAgent` sẵn có của file; trạng thái đã đủ để compile):

```python
def test_refine_updates_the_state_and_emits_done_without_a_card(ready_engine):
    e, sid = ready_engine  # a session that already reached "show"
    events = []
    e.agent = FakeAgent({"say": "Mình ưu tiên chỗ yên tĩnh.", "updates": [
        {"field": "soft", "op": "add", "value": "noise=quiet:love", "quote": "yên tĩnh hơn", "how": "said"}],
        "next": {"kind": "stop", "qid": "", "custom_text": "", "custom_chips": [], "reason": ""}})
    e.refine(sid, "muốn yên tĩnh hơn", lambda ev, d: events.append((ev, d)))
    names = [ev for ev, _ in events]
    assert "done" in names and "card" not in names
    done = dict(events)["done"]
    assert any(w["feature"] == "noise" for w in done["search_input"]["soft_weights"])
```

Nếu `tests/trip/test_engine.py` chưa có fixture `ready_engine`: thêm vào `tests/trip/conftest.py` một fixture tạo `Engine` với `FakeAgent`, chạy `turn` kiểu `show` trên state đã `framed()` đủ trường bắt buộc, trả `(engine, sid)` — theo đúng cách các test `_show` hiện có trong file dựng engine.

- [ ] **Step 2: Chạy test, xác nhận hỏng**

Run: `.venv/bin/python -m pytest tests/trip/test_traits.py tests/trip/test_guard.py tests/trip/test_engine.py -q`
Expected: FAIL (`No module named 'trip.domain.traits'`, `guard()` không nhận `compared`, `Engine` không có `refine`)

- [ ] **Step 3: Viết code**

```python
# src/trip/domain/traits.py
"""What a place the user compares to is like ("không thích quán giống X", "kiểu X"): its served features whose value
differs from what most places of its category have, strongest first. Read only from the catalog."""

from collections import Counter

from ..infrastructure.catalog import Candidate, Catalog
from .resolve import search
from .text import contains, fold

CUES = ("giong", "kieu", "nhu", "tuong tu")
MAX_PLACES, MAX_TRAITS = 2, 4


def _common(catalog: Catalog, category: str | None) -> dict[str, str]:
    """Most frequent served value per feature among places of this category (a few thousand places: no cache)."""
    counts: dict[str, Counter] = {}
    for p in catalog.places:
        if p.category == category:
            for f, k in p.known.items():
                counts.setdefault(f, Counter())[k.value] += 1
    return {f: c.most_common(1)[0][0] for f, c in counts.items()}


def traits(place: Candidate, catalog: Catalog) -> list[dict]:
    common = _common(catalog, place.category)
    out = [{"feature": f, "value": k.value, "n": k.n} for f, k in place.known.items()
           if k.value != "unknown" and common.get(f) != k.value]
    return sorted(out, key=lambda t: (-t["n"], t["feature"]))[:MAX_TRAITS]


def compared_places(text: str, catalog: Catalog) -> list[dict]:
    folded = fold(text)
    if not any(f" {c} " in f" {folded} " for c in CUES):
        return []
    out = []
    for c in CUES:
        i = f" {folded} ".find(f" {c} ")
        if i < 0:
            continue
        tail = " ".join(text.split()[len(folded[:i].split()) + len(c.split()):][:8])
        for p in search(tail, catalog, limit=1):
            if contains(text, p.name) and all(o["id"] != p.id for o in out):
                out.append({"id": p.id, "name": p.name, "traits": traits(p, catalog)})
    return out[:MAX_PLACES]
```

(`fold` bỏ dấu + hạ chữ thường — có sẵn ở `trip/domain/text.py`.)

`src/trip/agent/prompt.py` — `prompt_fields(..., transcript=None, compared=())`, trong `context` thêm:

```python
        "compared_places": list(compared),
```

`src/trip/agent/nodes.py` — trong `_prepare`, trước `fields = ...`:

```python
    compared = compared_places(text, engine.catalog)
```

truyền `compared=compared` vào `prompt_fields(...)`, và thêm `"compared": compared` vào dict trả về. Trong `reason_text`, gọi `guard(..., data["heard"], compared=data.get("compared"))`.

Prompt `TRIP_TURN` (`src/corpus/llm/tasks.py`) — thêm vào phần luật cập nhật:

```text
- compared_places in CURRENT CONTEXT lists places the user compares the trip to, with what each is like (traits).
  "không thích / tránh quán giống X" -> one soft update per trait of X: "<feature>=<value>:avoid"; "kiểu X",
  "giống X" as a wish -> ":love". how = inferred; quote = the user's words naming X and the wish. Use only the
  traits listed for X. If the user names a place that is not in compared_places, say you could not find it.
```

`src/trip/domain/guard.py` — chữ ký `guard(..., heard: str, compared: list[dict] | None = None)`; trong vòng `for u in plan.updates:`, ngay sau check `quote`:

```python
        if u.field == "soft" and u.how == "inferred" and compared:
            named = [c for c in compared if contains(u.quote, c["name"])]
            key = values.split_weight(u.value)[0].replace(" ", "")
            if named and key not in {f"{t['feature']}={t['value']}" for c in named for t in c["traits"]}:
                log.append(f"drop soft={u.value!r}: not a trait of {named[0]['name']!r}")
                continue
```

`src/trip/api/engine.py` — method mới (cạnh `turn`):

```python
    def refine(self, sid: str, text: str, emit: Emit) -> None:
        """A wish typed later, at Chọn nơi: read it like any text turn, then compile again. The Understand screen's
        card is left as it was; only say / state / done leave this method."""
        s = self.store.get(sid)
        quiet = lambda ev, d: None if ev == "card" else emit(ev, d)  # noqa: E731
        with s.lock:
            try:
                card_before = s.card
                self._text_flow.invoke(s, TurnInput(kind="text", text=text), quiet, None)
                s.card = card_before
                if required(s.state, self.catalog, self.cfg) is None:
                    si = compile_search_input(s.state)
                    emit("done", {"search_input": si.model_dump(mode="json")})
            finally:
                self.store.save(s)
```

`src/trip/api/tools.py` — `apply`:

```python
    def apply(self, sid: str, operation: str, payload: dict, emit) -> dict:
        if operation == "refine":
            permit_tool(self.skill, "trip.refine")
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 1000 or set(payload) != {"text"}:
                raise ValueError("text must be 1-1000 characters")
            self.engine.refine(sid, text.strip(), emit)
            return self.load(sid)
        if operation != "turn":
            raise ValueError(f"trip does not accept {operation}")
        ...
```

`src/trip/skills.yaml` — thêm `trip.refine` vào danh sách tool được phép, cạnh `trip.turn`.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/trip -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(trip): read 'like X' wishes from X's traits; refine operation for later wishes" -- src/trip/domain/traits.py src/trip/agent/nodes.py src/trip/agent/prompt.py src/corpus/llm/tasks.py src/trip/domain/guard.py src/trip/api/engine.py src/trip/api/tools.py src/trip/skills.yaml tests/trip/test_traits.py tests/trip/test_guard.py tests/trip/test_engine.py tests/trip/conftest.py
```

---

### Task 5: Harness nối `trip` → `refine` → `rebase`; route đọc trang

**Files:**
- Modify: `src/harness/dispatch.py` (`request`: sau decision `turn`)
- Modify: `src/harness/server.py:23` (`READ` thêm `page`)
- Test: `tests/harness/test_dispatch.py`, `tests/harness/test_harness_server.py`

**Interfaces:**
- Consumes: event `trip {texts}` (Task 3), `Tools.apply(trip_sid, "refine", {"text"})` (Task 4), `Tools.rebase(...)` trả `diff` (Task 2), `Tools.read(sid, "page", {"group"})` (Task 2).
- Produces: lượt `turn` ở stage `decision` có op `trip` kết thúc bằng event `view {view, diff}` **sau rebase**; `GET /api/harness/sessions/<jid>/read/decision/page?group=<id>`.

- [ ] **Step 1: Viết test hỏng**

Trong `tests/harness/test_dispatch.py`, `Tools` giả: thêm nhánh cho decision `turn` phát `trip`, cho trip `refine`, và `rebase`:

```python
    def apply(self, sid, operation, payload, emit):
        self.calls += 1
        if self.stage == "decision" and operation == "turn" and "yên tĩnh" in payload.get("text", ""):
            emit("trip", {"texts": ["muốn yên tĩnh hơn"]})
        if self.stage == "trip" and operation == "refine":
            self.states[sid]["refined"] = payload["text"]
            emit("say", {"delta": "Mình ưu tiên chỗ yên tĩnh."})
            return self._compiled(sid, emit)
        if operation == "turn" and self.stage == "trip":
            return self._compiled(sid, emit)
        ...  # existing branches
```

(tách phần tạo `SearchInput` + `emit("done", ...)` hiện có thành helper `_compiled(sid, emit)` trả `self.load(sid)`), và:

```python
    def rebase(self, sid, payload):
        self.states[sid]["rebased"] = payload["search_input"]["context"]["days"]
        return {**self.load(sid), "diff": {"added": [], "removed": [], "text": "+0 nơi"}}
```

Test mới:

```python
def test_decision_turn_with_a_trip_wish_refines_trip_then_rebases_decision():
    h, tools = make()
    v = decision(h)
    out = run(h, v, "turn", "chat-1", {"text": "muốn yên tĩnh hơn"})
    j = h.load(out["id"])
    trip_sid, dec_sid = h._get(out["id"]).sessions["trip"], h._get(out["id"]).sessions["decision"]
    assert tools["trip"].states[trip_sid]["refined"] == "muốn yên tĩnh hơn"
    assert tools["decision"].states[dec_sid]["rebased"] == 2
    assert out["stage"] == "decision" and j["revision"] == out["revision"]


def test_decision_turn_without_a_trip_wish_never_touches_trip():
    h, tools = make()
    v = decision(h)
    before = tools["trip"].calls
    run(h, v, "turn", "chat-2", {"text": "bỏ quán số 2"})
    assert tools["trip"].calls == before
```

Trong `tests/harness/test_harness_server.py`, thêm một test GET `.../read/decision/page?group=chill` trả 200 với tools giả có `read("page")` (theo cách file đang test `why-not`).

- [ ] **Step 2: Chạy test, xác nhận hỏng**

Run: `.venv/bin/python -m pytest tests/harness -q`
Expected: FAIL (`KeyError: 'refined'`, route `page` 404)

- [ ] **Step 3: Viết code**

`src/harness/dispatch.py` — trong `request`, ngay sau dòng `result = self.tools[stage].apply(session.sessions[stage], request.operation, request.payload, capture)`:

```python
                    if stage == "decision" and request.operation == "turn":
                        texts = [t for e in events if e["event"] == "trip" for t in e["data"]["texts"]]
                        if texts and "trip" in session.sessions:
                            result = self._refine(session, " ".join(texts), capture) or result
```

Method mới:

```python
    def _refine(self, session: Journey, text: str, capture) -> dict | None:
        """A wish typed at Chọn nơi: Trip Understanding reads it, then Decision is rebuilt on the new Search Input."""
        compiled: list[dict] = []

        def on_trip(event: str, data: dict) -> None:
            if event == "say":
                capture("say", data)
            elif event == "done":
                compiled.append(data["search_input"])

        self.tools["trip"].apply(session.sessions["trip"], "refine", {"text": text}, on_trip)
        if not compiled:
            return None
        session.outputs["trip"] = SearchInput.model_validate(compiled[-1]).model_dump(mode="json")
        out = self.tools["decision"].rebase(session.sessions["decision"],
                                            {"search_input": session.outputs["trip"], "trip_session": session.sessions["trip"]})
        capture("view", {"view": out["view"], "diff": out["diff"]})
        return {"id": out["id"], "view": out["view"]}
```

`src/harness/server.py`:

```python
READ = re.compile(BASE + r"/([0-9a-f]{12})/read/(decision|planning)/(compare|why-not|lodging|variants|page)")
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/python -m pytest tests/harness tests/decision tests/trip -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(harness): trip wishes at Chọn nơi refine Trip and rebase Decision; page read" -- src/harness/dispatch.py src/harness/server.py tests/harness/test_dispatch.py tests/harness/test_harness_server.py
```

---

### Task 6: Web — dữ liệu: `top`, `total`, `change`, tải trang

**Files:**
- Modify: `web/src/user/pd/types.ts` (`Card.top`, `Group.total`, `View.change`)
- Modify: `web/src/user/pd/api.ts` (`morePlaces`)
- Modify: `web/src/user/pd/decision.tsx` (context có `more(group)`)

**Interfaces:**
- Consumes: read `decision/page?group=` (Task 5) trả `{view}`.
- Produces: `useDecision().more(group: string): Promise<void>` — không gửi trùng khi đang tải nhóm đó; `useDecision().loadingMore: string | null`.
- Produces: kiểu `Change = { kept: number; added: number; removed: number; replaced_all: boolean }`.

- [ ] **Step 1: Kiểu dữ liệu**

`web/src/user/pd/types.ts`:

```ts
// in Card
  top: boolean
// in Group
  total: number
// new
export interface Change { kept: number; added: number; removed: number; replaced_all: boolean }
// in View
  change: Record<string, Change>
```

- [ ] **Step 2: API**

`web/src/user/pd/api.ts`:

```ts
export const morePlaces = (id: string, group: string) => readJourney<{ view: View }>(id, `decision/page?group=${encodeURIComponent(group)}`)
```

- [ ] **Step 3: Provider**

Trong `DecisionProvider` (`web/src/user/pd/decision.tsx`):

```tsx
  const [loadingMore, setLoadingMore] = useState<string | null>(null)
  const loading = useRef<string | null>(null)
  const more = useCallback(async (group: string) => {
    if (!id || loading.current === group) return
    loading.current = group
    setLoadingMore(group)
    try {
      const r = await morePlaces(id, group)
      setView(r.view)
    } finally {
      loading.current = null
      setLoadingMore(null)
    }
  }, [id])
```

thêm `more`, `loadingMore` vào kiểu context và `value`.

- [ ] **Step 4: Kiểm tra kiểu**

Run: `cd web && npx tsc -b`
Expected: lỗi chỉ ở chỗ chưa dùng tới (nếu có) — sửa hết trước khi commit; cuối bước: không lỗi.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(web): decision paging and change data" -- web/src/user/pd/types.ts web/src/user/pd/api.ts web/src/user/pd/decision.tsx
```

---

### Task 7: Web — lưới tự tải, nhãn "Hợp nhất", chuyển cảnh, đĩa giữ nơi đang xem

**Files:**
- Create: `web/src/user/ui/useStagedList.ts`
- Modify: `web/src/user/screens/Explore.tsx` (header, lưới, sentinel)
- Modify: `web/src/user/ui/PlaceCard.tsx` (badge, class chuyển cảnh)
- Modify: `web/src/user/ui/DiscPicker.tsx` (giữ nơi đang xem theo id, badge)
- Modify: `web/src/user/css/explore.css` (badge, keyframes chuyển cảnh, skeleton)

**Interfaces:**
- Consumes: `Card.top`, `Group.total`, `View.change`, `more`, `loadingMore` (Task 6).
- Produces: `useStagedList(cards: Card[], change: Change | undefined): { items: { card: Card; phase: 'stay' | 'enter' | 'leave'; i: number }[]; replacing: boolean }` — giữ thẻ bị gỡ thêm 180 ms ở vị trí cũ với `phase: 'leave'`, đánh `enter` cho thẻ mới kèm thứ tự `i` để lệch 40 ms, `replacing` = true trong 240 ms khi `replaced_all`.

- [ ] **Step 1: Hook chuyển cảnh**

```ts
// web/src/user/ui/useStagedList.ts
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Card, Change } from '../pd/types'

type Item = { card: Card; phase: 'stay' | 'enter' | 'leave'; i: number }
const LEAVE_MS = 180
const REPLACE_MS = 240
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches

// Cards that stay keep their slot, removed ones fade out where they were, new ones fade up into the freed slots.
export function useStagedList(cards: Card[], change: Change | undefined) {
  const prev = useRef<Card[]>(cards)
  const [items, setItems] = useState<Item[]>(() => cards.map((card) => ({ card, phase: 'stay', i: 0 })))
  const [replacing, setReplacing] = useState(false)
  useLayoutEffect(() => {
    const before = prev.current
    prev.current = cards
    const now = new Set(cards.map((c) => c.id))
    const was = new Set(before.map((c) => c.id))
    if (change?.replaced_all && !reduced()) {
      setReplacing(true)
      const t = setTimeout(() => { setReplacing(false); setItems(cards.map((card) => ({ card, phase: 'stay', i: 0 }))) }, REPLACE_MS)
      return () => clearTimeout(t)
    }
    let n = 0
    const next: Item[] = cards.map((card) => ({ card, phase: was.has(card.id) ? 'stay' : 'enter', i: was.has(card.id) ? 0 : n++ }))
    const leaving = before.filter((c) => !now.has(c.id))
    if (!leaving.length || reduced()) { setItems(next); return }
    const merged = [...next]
    before.forEach((c, k) => { if (!now.has(c.id)) merged.splice(Math.min(k, merged.length), 0, { card: c, phase: 'leave', i: 0 }) })
    setItems(merged)
    const t = setTimeout(() => setItems(next), LEAVE_MS)
    return () => clearTimeout(t)
  }, [cards, change])
  useEffect(() => () => { prev.current = [] }, [])
  return { items, replacing }
}
```

- [ ] **Step 2: Trượt FLIP cho thẻ giữ lại đổi vị trí**

Trong `Explore.tsx`, lưới dùng ref; trước mỗi lần `items` đổi, chụp `getBoundingClientRect()` của mọi `[data-place]`, sau khi render thì thẻ nào lệch > 2 px được `animate([{ transform: translate(dx, dy) }, { transform: 'none' }], { duration: 280, easing: 'cubic-bezier(.2,.8,.2,1)' })`; bỏ qua khi `reduced()`:

```tsx
  const gridRef = useRef<HTMLDivElement>(null)
  const rects = useRef(new Map<string, DOMRect>())
  useLayoutEffect(() => {
    const el = gridRef.current
    if (!el || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    el.querySelectorAll<HTMLElement>('[data-place]').forEach((n) => {
      const id = n.dataset.place!
      const old = rects.current.get(id)
      const r = n.getBoundingClientRect()
      if (old && (Math.abs(old.left - r.left) > 2 || Math.abs(old.top - r.top) > 2))
        n.animate([{ transform: `translate(${old.left - r.left}px, ${old.top - r.top}px)` }, { transform: 'none' }], { duration: 280, easing: 'cubic-bezier(.2,.8,.2,1)' })
    })
    rects.current = new Map([...el.querySelectorAll<HTMLElement>('[data-place]')].map((n) => [n.dataset.place!, n.getBoundingClientRect()]))
  }, [items])
```

- [ ] **Step 3: Lưới, sentinel, header**

Trong `Explore.tsx`:
- `const { items, replacing } = useStagedList(current?.cards ?? [], view.change?.[current?.id ?? ''])`.
- Lưới render `items` thay `current.cards`: `<PlaceCard key={it.card.id} c={it.card} phase={it.phase} order={it.i} ... />`; class lưới thêm `is-replacing` khi `replacing`.
- Sentinel cuối lưới (chỉ khi `current.cards.length < current.total`):

```tsx
  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el || !current || current.cards.length >= current.total) return
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) more(current.id) }, { rootMargin: '600px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [current?.id, current?.cards.length, current?.total, more])
  ...
  {current && current.cards.length < current.total && (
    <div ref={sentinel} className="tg-grid__more" aria-live="polite">
      {loadingMore === current.id && Array.from({ length: 3 }, (_, i) => <div key={i} className="tg-skel-card"><div className="tg-skel" /></div>)}
    </div>
  )}
```

- Header: thay `<p>Một tập nhỏ đáng cân nhắc…</p>` bằng:

```tsx
<p>{total - anchors.length} nơi hợp với chuyến của bạn, xếp từ hợp nhất. <button type="button" className="tg-link" onClick={() => openAssistant(true)}>Chat để thu hẹp</button></p>
```

với `total = view.groups.filter((g) => g.id !== 'anchors').reduce((n, g) => n + g.total, 0) + anchors.length`.
- Tab hiện `g.total` thay `g.cards.length`.
- Thông báo `diff.text` sau lượt chat (đã có trong Assistant) giữ nguyên.

- [ ] **Step 4: PlaceCard + CSS**

`PlaceCard` nhận `phase?: 'stay' | 'enter' | 'leave'`, `order?: number`; `article` thêm class `is-${phase}` và `style={{ '--i': order } as CSSProperties}`; khi `c.top` hiện `<span className="tg-tag tg-pc__top">Hợp nhất</span>` trong `.tg-pc__media`.

`web/src/user/css/explore.css` (chỉ dùng token sẵn có trong `tokens.css`):

```css
.tg-pc__top { position: absolute; left: 12px; bottom: 12px; background: var(--tg-pine); color: #fff; }
.tg-pc.is-enter { animation: tg-pc-enter 320ms var(--tg-ease) both; animation-delay: calc(var(--i, 0) * 40ms); }
.tg-pc.is-leave { animation: tg-pc-leave 180ms var(--tg-ease) both; pointer-events: none; }
.tg-grid.is-replacing { animation: tg-grid-swap 240ms var(--tg-ease); }
.tg-grid__more { grid-column: 1 / -1; display: grid; grid-template-columns: inherit; gap: inherit; min-height: 1px; }
@keyframes tg-pc-enter { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes tg-pc-leave { to { opacity: 0; transform: scale(0.96); } }
@keyframes tg-grid-swap { 0% { opacity: 1; } 45% { opacity: 0; } 100% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .tg-pc.is-enter, .tg-pc.is-leave { animation: tg-fade 150ms both; animation-delay: 0ms; }
  .tg-grid.is-replacing { animation: none; }
}
```

- [ ] **Step 5: Đĩa xoay giữ nơi đang xem**

`DiscPicker.tsx`: thay `const [active, setActive] = useState(0)` bằng theo dõi id:

```tsx
  const [activeId, setActiveId] = useState<string | null>(null)
  const found = activeId ? ids.indexOf(activeId) : -1
  const i = found >= 0 ? found : Math.min(active, Math.max(0, n - 1))
```

giữ `active` cho trường hợp nơi đang xem đã bị gỡ; mọi `setActive(k)` thêm `setActiveId(ids[k] ?? null)`; `turn` cập nhật cả hai. Badge: trong `.tg-disc__meta` thêm `{c.top && <span className="tg-tag tg-pc__top tg-disc__top">Hợp nhất</span>}` (`.tg-disc__top { position: static; }`). Khi tới gần cuối danh sách (`i >= n - 4` và `n < total` của nhóm) gọi `more(tab)`.

- [ ] **Step 6: Kiểm tra kiểu + build**

Run: `cd web && npx tsc -b && npm run build`
Expected: không lỗi

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(web): endless suggestion grid with calm transitions" -- web/src/user/ui/useStagedList.ts web/src/user/screens/Explore.tsx web/src/user/ui/PlaceCard.tsx web/src/user/ui/DiscPicker.tsx web/src/user/css/explore.css
```

---

### Task 8: Kiểm tra toàn luồng trên app thật + tài liệu chính thức

**Files:**
- Modify: `web/scripts/shots_app.mjs` (cuộn lưới, chat thu hẹp)
- Modify: `docs/PLACE_DECISION.md` §9 (bỏ cắt shortlist; thêm cửa sổ / gộp / `top` / `page_size` / `keep_factor` / `replace_below`; op `trip`), `docs/TRIP_UNDERSTANDING.md` (operation `refine`, nét của nơi so sánh, guard), `docs/AGENT_HARNESS.md` (luồng `trip → refine → rebase`, read `page`), `docs/LLM_PROVIDER.md` (đổi op của `decision_turn`, luật mới của `trip_turn`), `docs/Role_Web_Functional_Design.md` §6 (`useStagedList`), `docs/log/DEV_LOG.md`

- [ ] **Step 1: Kịch bản chụp**

Trong `shots_app.mjs`, sau bước tới Chọn nơi:

```js
  step('explore: scroll loads more')
  const before = await page.locator('.tg-grid [data-place]').count()
  await page.locator('.tg-grid__more').scrollIntoViewIfNeeded()
  await page.waitForFunction((n) => document.querySelectorAll('.tg-grid [data-place]').length > n, before, { timeout: 30000 })
  await shot('explore-more')
  step('explore: narrow by chat')
  await page.getByRole('button', { name: 'Chat để thu hẹp' }).click()
  await page.fill('.tg-asst textarea, .tg-asst input', 'mình muốn chỗ yên tĩnh hơn, không thích quán đông')
  await page.keyboard.press('Enter')
  await page.waitForSelector('.tg-pc.is-enter, .tg-pc.is-leave, .tg-grid.is-replacing', { timeout: 120000 }).catch(() => {})
  await shot('explore-narrowed')
```

- [ ] **Step 2: Chạy app thật và chụp**

Run (3 terminal, hoặc nền):
```bash
.venv/bin/python -m harness serve &
cd web && npx vite --host 127.0.0.1 &
node web/scripts/shots_app.mjs http://127.0.0.1:5173
```
Expected: `shots/app/*-explore-more.png` có nhiều thẻ hơn trang đầu; `*-explore-narrowed.png` có thẻ mới / nhãn "Hợp nhất"; log không có `pageerror`. Xem từng ảnh trước khi báo xong.

- [ ] **Step 3: Tài liệu**

Sửa thẳng đoạn mô tả cũ trong từng file liệt kê ở trên cho khớp code (RULE §0.1: không ghi lịch sử, không ghi "trước đây"). `PLACE_DECISION.md` §9.2 thay đoạn "Hệ số dư để user có chỗ chọn nhưng không bị ngợp" bằng mô tả cửa sổ + `top`; thêm §9.4 "Cửa sổ hiện và lọc lại" (luật gộp 3 bước). `DEV_LOG.md` thêm mục theo khuôn mẫu của chính file.

- [ ] **Step 4: Chạy toàn bộ test liên quan**

Run: `.venv/bin/python -m pytest tests/decision tests/trip tests/harness -q && (cd web && npx tsc -b)`
Expected: PASS, không lỗi kiểu

- [ ] **Step 5: Commit**

```bash
git commit -m "docs: shown window, trip wishes at Chọn nơi; shots for paging and narrowing" -- web/scripts/shots_app.mjs docs/PLACE_DECISION.md docs/TRIP_UNDERSTANDING.md docs/AGENT_HARNESS.md docs/LLM_PROVIDER.md docs/Role_Web_Functional_Design.md docs/log/DEV_LOG.md
```

---

## Các kế hoạch sau (mỗi cái một file, viết khi tới lượt)

| # | File | Phần spec |
|---|---|---|
| 2 | `docs/plans/DETAIL_LOGISTICS_PLAN_2.md` | §1.1–1.2 modal "Xem chi tiết" (`PlaceSheet`, mở từ đĩa và lưới, animation) |
| 3 | `docs/plans/DETAIL_LOGISTICS_PLAN_3.md` | §4.1 corpus `stay` (query, `list`, bàn giao GMAPS / MODEL) — chạy song song từ sớm vì crawl + observe lâu |
| 4 | `docs/plans/DETAIL_LOGISTICS_PLAN_4.md` | §1.3 `photo_rank` (Gemma, dừng luồng TikTok khi chạy) |
| 5 | `docs/plans/DETAIL_LOGISTICS_PLAN_5.md` | §3.1–3.4 xuất phát, phương tiện, chuyến (live + chạy trước), câu chỗ ở + `PlaceInput` |
| 6 | `docs/plans/DETAIL_LOGISTICS_PLAN_6.md` | §4.2–4.3 xếp hạng chỗ ở theo gu (corpus khi đủ, live khi chưa), màn "Bạn ở đâu?" |
