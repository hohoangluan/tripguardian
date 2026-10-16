# Decision wish score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mọi mong muốn Trip Understanding ghi được (món, kiểu nơi, vibe, giống X, `liked_groups`, `purpose`) quy về một thành phần điểm `wish`; Lựa chọn hiện đủ mọi nơi qua sàng lọc, nơi hợp hơn đứng trước, mọi thẻ có `why`, mọi nơi có `why_not`.

**Architecture:** Module mới `src/decision/wishes.py` dựng `Wish` từ Search Input (một lần mỗi Search Input, memo trong `frame.table`) và tính `lift` noisy-or. `rank.score` (theo từng nơi) và `frame.score_table` (theo bảng) cùng cộng `w_wish · wish`, thay `w_vibe · vibe_fit`; oracle `tests/decision/reference.py` giữ hai đường khớp. `cards._why` và `pipeline.why_not` đọc các hit để nói lý do. Giao diện giữ nguyên.

**Tech Stack:** Python 3.12, numpy, polars snapshot (`corpus.snapshot`), pydantic (`trip.SearchInput`), pytest; web React/TS chỉ đổi một dòng logic.

**Spec:** `docs/superpowers/specs/2026-10-15-place-decision-needs-design.md` §1, §2, §2.1, §4.1, §11, §12, §12.1

## Global Constraints

- Tài liệu viết tiếng Việt; code, comment, identifier, tên file viết tiếng Anh (`RULE.md` §0).
- Module chỉ giao tiếp qua public API; `decision` chỉ dùng `corpus.serving` (`similarity`, `feature`, `dishes`) và `trip.SearchInput`.
- Mong muốn chỉ nâng điểm: không loại nơi nào, không điểm âm, sàng lọc cứng chạy trước (spec §4.1).
- `unknown` ≠ không: không bao giờ viết "không bán"; viết "Chưa thấy ghi …".
- Giá trị khởi điểm (spec §4.1): `a` = dish 0.8, kind 0.8, vibe 0.8, like 0.8, group 0.4, purpose 0.25; `like_min` 0.3; `w_wish` 1.5; map `purpose`: `relax→chill`, `food_culture→meal`, `nature→nature`, `explore→sights`, `photo→photo_spot` (bằng chứng VERIFIED/OUTDATED); `bond`, `adventure` không map.
- Tốc độ (spec §12.1 G): lần đầu p95 ≤ 120 ms; memo trúng trung vị ≤ 20 ms; dựng `like` ≤ 10 ms.
- Chạy pytest luôn bằng `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider …` (NFS `.browser` treo pytest nếu thiếu cờ).
- **Không commit, không push** trừ khi user bảo: working tree dùng chung với nhiều session. Bước "Commit" của mỗi task thay bằng "Review diff" (`git diff -- <files>`; nếu git treo vì NFS, đọc lại file bằng Read).
- Trước Task 1 chạy nền `tests/trip tests/planning tests/harness` một lần và ghi danh sách fail có sẵn (Task 8 so với nó).
- Nền `tests/decision` trước khi sửa (15/10): 264 pass, 1 fail có sẵn `tests/decision/test_decision_engine.py::test_agent_sees_every_shown_place_but_reasons_only_for_the_first_page` — không thuộc plan này, không sửa, không tính là hồi quy.

## Review Focus

1. Nơi tham chiếu của "giống X" là chỗ ở (`stay`) hoặc không có trong snapshot → không có mong muốn nào, không lỗi (Task 1: `test_like_reference_missing_or_stay_gives_no_wish`).
2. `vibes` có id trùng trong `places` → mỗi nơi một strength, không đếm đôi (Task 1: `test_vibe_duplicates_count_once`).
3. Phiên cũ lưu trước khi có `wishes` / `liked_groups` / `purpose` được khôi phục → điểm `wish` = 0, không lỗi (Task 2: `test_no_wishes_means_zero_wish_everywhere`).
4. Đĩa xoay đếm dòng `why` để ra mức "Rất hợp / Hợp / Khá hợp": dòng dự phòng không được làm nơi "hợp" hơn (Task 4: `fit: false` + `DiscPicker.fitOf`).
5. Đổi mong muốn giữa phiên với cùng một memo → không trả điểm hay mong muốn cũ (Task 3: `test_equivalence_memo_follows_wish_changes`).

---

### Task 1: `wishes.py` — dựng mong muốn và `lift`

**Files:**
- Create: `src/decision/wishes.py`
- Modify: `config/decision.yaml` (khối `wish`, `weights.vibe` → `weights.wish`)
- Modify: `src/decision/settings.py` (field `wish`)
- Test: `tests/decision/test_wishes.py`

**Interfaces:**
- Consumes: `corpus.serving.similarity(a, b, sigs=None) -> float`; `si.wishes.dishes[].{dish, quote, place_ids}`, `si.wishes.kinds[].{kind, quote, place_ids}`, `si.wishes.like[].{place_id, but, quote}`, `si.vibes[].{phrase, places}`, `si.liked_groups`, `si.context.purpose`.
- Produces:
  - `SAID: tuple[str, ...] = ("dish", "kind", "vibe", "like")`
  - `@dataclass(frozen=True) class Wish: key: str; kind: str; label: str; a: float; places: Mapping[str, float] | None = None; group: str | None = None; role: str | None = None`
  - `build(si, rows: Iterable[dict], cfg, sigs: Mapping | None = None, firm: Callable[[str, str], set[str]] | None = None, name: Callable[[str], str | None] = lambda pid: None) -> tuple[Wish, ...]`
  - `strength(w: Wish, pid: str, role: str | None, group: str | None) -> float`
  - `lift(ws, pid, role, group) -> tuple[float, list[tuple[str, str, str, float]]]` — `(1 − Π(1 − a·s), hits)`, hit = `(key, kind, label, round(a·s, 4))`, hits xếp giảm dần theo đóng góp rồi theo key.
  - `cfg.wish: dict` = `{"a": {...}, "like_min": float, "purpose": {purpose: {"group": str} | {"feature": str, "value": str}}}`; `cfg.weights["wish"]`.

- [ ] **Step 1: Write the failing tests**

`tests/decision/test_wishes.py`:

```python
"""Wishes from Trip Understanding as place lifts (spec 2026-10-15-place-decision-needs-design.md §4.1, §12.1 A)."""

import pytest

from fixtures import feat, si, srec

from decision.settings import default
from decision.wishes import SAID, build, lift, strength

CFG = default()
A = CFG.wish["a"]
KIND = ("scenic_view", "photo_spot", "cozy_decor", "live_music")  # experience features that make a signature


def wishes(dishes=(), kinds=(), like=()):
    return {"dishes": list(dishes), "kinds": list(kinds), "like": list(like)}


def dish(name, *ids):
    return {"dish": name, "quote": name, "place_ids": list(ids)}


def kind(name, *ids):
    return {"kind": name, "quote": name, "place_ids": list(ids)}


def cafe(pid, feats=KIND, **kw):
    return srec(pid, group="cafe", usable=("experience",), features={f: feat("present", n=5) for f in feats}, **kw)


def test_dish_ranks_its_places_and_lifts_meals_only():  # A1
    ws = build(si(wishes=wishes(dishes=[dish("bánh căn", "P1", "P2", "P3")])), [], CFG)
    assert [w.key for w in ws] == ["dish:bánh căn"]
    assert dict(ws[0].places) == {"P1": 1.0, "P2": 0.75, "P3": 0.5} and ws[0].role == "meal"
    assert lift(ws, "P1", "meal", "meal")[0] == pytest.approx(A["dish"])
    assert lift(ws, "P1", "experience", "chill")[0] == 0.0


def test_dish_without_places_gives_no_wish():  # A2
    assert build(si(wishes=wishes(dishes=[dish("halal")])), [], CFG) == ()


def test_same_wish_twice_counts_once():  # A3
    ws = build(si(wishes=wishes(dishes=[dish("Bánh căn", "P1"), dish("bánh căn", "P2")])), [], CFG)
    assert len(ws) == 1


def test_kind_lifts_its_places_fully():  # A4
    ws = build(si(wishes=wishes(kinds=[kind("karaoke", "K1", "K2")])), [], CFG)
    assert dict(ws[0].places) == {"K1": 1.0, "K2": 1.0} and ws[0].role is None


def test_vibe_ranks_like_vibe_fit():  # A5
    ws = build(si(vibes=[{"phrase": "mây", "places": ["V1", "V2", "V3", "V4"]}]), [], CFG)
    p = ws[0].places
    assert p["V1"] == 1.0 and p["V4"] == 0.5 and p["V1"] > p["V2"] > p["V3"] > p["V4"]
    assert ws[0].label == "mây"


def test_vibe_duplicates_count_once():  # Review Focus 2
    ws = build(si(vibes=[{"phrase": "mây", "places": ["V1", "V1", "V2"]}]), [], CFG)
    assert dict(ws[0].places) == {"V1": 1.0, "V2": 0.5}


def test_like_lifts_similar_places_of_the_same_kind_but_not_the_reference():  # A6
    rows = [cafe("X"), cafe("Y"), cafe("Z", feats=("hiking", "camping", "animals")),
            srec("R", group="restaurant", usable=("meal",), features={f: feat("present", n=5) for f in KIND})]
    ws = build(si(wishes=wishes(like=[{"place_id": "X", "but": [], "quote": "giống X"}])), rows, CFG,
               name=lambda pid: "Mọt Cafe" if pid == "X" else None)
    assert [w.key for w in ws] == ["like:X"] and ws[0].label == "Mọt Cafe"
    assert set(ws[0].places) == {"Y"} and ws[0].places["Y"] == 1.0


def test_like_reference_with_too_few_features_matches_nothing():  # A7
    rows = [cafe("X", feats=("scenic_view",)), cafe("Y")]
    assert build(si(wishes=wishes(like=[{"place_id": "X", "but": [], "quote": "giống X"}])), rows, CFG) == ()


def test_like_reference_missing_or_stay_gives_no_wish():  # A8, Review Focus 1
    rows = [cafe("Y"), srec("S", group="stay", usable=(), features={f: feat("present", n=5) for f in KIND})]
    for ref in ("GHOST", "S"):
        assert build(si(wishes=wishes(like=[{"place_id": ref, "but": [], "quote": "giống"}])), rows, CFG) == ()


def test_liked_group_lifts_that_group_only():  # A9, A10
    ws = build(si(liked_groups=["chill", "meal"]), [], CFG)
    assert [w.key for w in ws] == ["group:chill", "group:meal"]
    assert strength(ws[0], "C", "experience", "chill") == 1.0
    assert strength(ws[0], "N", "experience", "nature") == 0.0
    assert strength(ws[1], "M", "meal", "meal") == 1.0


@pytest.mark.parametrize("purpose,group", [("relax", "chill"), ("food_culture", "meal"), ("nature", "nature"),
                                           ("explore", "sights")])
def test_purpose_maps_to_a_group_and_leans_less(purpose, group):  # A11
    ws = build(si(context={"purpose": purpose}), [], CFG)
    assert [(w.kind, w.group) for w in ws] == [("purpose", group)] and ws[0].a == A["purpose"] < A["dish"]


def test_purpose_photo_lifts_only_firm_photo_spots():  # A12
    firm = lambda fid, value: {"P1"} if (fid, value) == ("photo_spot", "present") else set()
    ws = build(si(context={"purpose": "photo"}), [], CFG, firm=firm)
    assert dict(ws[0].places) == {"P1": 1.0}
    assert build(si(context={"purpose": "photo"}), [], CFG, firm=lambda f, v: set()) == ()


@pytest.mark.parametrize("purpose", ["bond", "adventure", None])
def test_unmapped_purpose_gives_no_wish(purpose):  # A13
    assert build(si(context={"purpose": purpose}), [], CFG) == ()


def test_lift_is_noisy_or_and_stays_within_one():  # B3 at the source
    ws = build(si(wishes=wishes(dishes=[dish("bánh căn", "M")], kinds=[kind("lẩu", "M")]), liked_groups=["meal"],
                  context={"purpose": "food_culture"}), [], CFG)
    value, hits = lift(ws, "M", "meal", "meal")
    one = lift(ws[:1], "M", "meal", "meal")[0]
    assert one < value <= 1.0
    assert [h[1] for h in hits][:2] == ["dish", "kind"] and all(h[1] in SAID for h in hits[:2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_wishes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'decision.wishes'`.

- [ ] **Step 3: Add config and settings**

`config/decision.yaml` — trong dòng `weights`, đổi `vibe: 0.8` thành `wish: 1.5` và sửa comment:

```yaml
weights: {ctx: 1.0, pref: 2.0, nov: 1.0, exp: 0.3, pop: 0.2, unc: 0.5, price: 0.5, wish: 1.5}  # wish: Trip's wishes (decision.wishes)
```

Thêm ngay dưới dòng `weights`:

```yaml
wish:                       # decision.wishes: how much meeting one wish lifts a place (spec 2026-10-15 §4.1)
  a: {dish: 0.8, kind: 0.8, vibe: 0.8, like: 0.8, group: 0.4, purpose: 0.25}
  like_min: 0.3             # corpus.serving.similarity at or above this = "giống X"
  purpose:                  # Trip context.purpose -> what it leans to; bond, adventure lean to nothing
    relax: {group: chill}
    food_culture: {group: meal}
    nature: {group: nature}
    explore: {group: sights}
    photo: {feature: photo_spot, value: present}
```

`src/decision/settings.py` — thêm field cuối `Settings` (sau `details_fit`):

```python
    wish: dict = field(default_factory=lambda: {"a": {}, "like_min": 1.0, "purpose": {}})  # config/decision.yaml wish
```

- [ ] **Step 4: Write `src/decision/wishes.py`**

```python
"""Trip Understanding's wishes as place lifts (docs/PLACE_DECISION.md §8 `wish`). A wish only lifts the places that
meet it: it never pushes one down or out, and screening runs before it."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from corpus.serving import similarity

SAID = ("dish", "kind", "vibe", "like")  # the user said it; group and purpose only lean


@dataclass(frozen=True)
class Wish:
    key: str  # "dish:bánh căn", "kind:karaoke", "vibe:0", "like:<id>", "group:chill", "purpose:relax"
    kind: str  # dish | kind | vibe | like | group | purpose
    label: str  # the user's words, the reference's name, or a group / purpose id
    a: float  # how much meeting it lifts (config wish.a)
    places: Mapping[str, float] | None = None  # id -> strength 0..1; None: every place of `group`
    group: str | None = None  # display group it is about (group, purpose)
    role: str | None = None  # only places of this role (a dish is a meal)


def ranked(ids: Iterable[str]) -> dict[str, float]:
    """1 for the first place down to 0.5 for the last; a repeated id keeps its first rank."""
    ids = list(dict.fromkeys(ids))
    n = max(1, len(ids) - 1)
    return {pid: 1.0 - 0.5 * i / n for i, pid in enumerate(ids)}


def build(si, rows: Iterable[dict], cfg, sigs: Mapping | None = None,
          firm: Callable[[str, str], set[str]] | None = None,
          name: Callable[[str], str | None] = lambda pid: None) -> tuple[Wish, ...]:
    """rows: every place as {id, identity.category_group, usable_as} (a record, or Region.light), read only for
    "giống X". sigs: id -> signature (Region.sigs). firm(feature, value): ids whose served value is that, VERIFIED or
    OUTDATED. A wish no place meets is left out: it would lift nothing."""
    a, out, seen = cfg.wish["a"], [], set()

    def add(w: Wish) -> None:
        k = (w.kind, w.label.casefold())
        if k not in seen and (w.places is None or w.places):
            seen.add(k)
            out.append(w)

    for d in si.wishes.dishes:
        add(Wish(f"dish:{d.dish}", "dish", d.dish, a["dish"], ranked(d.place_ids), role="meal"))
    for k in si.wishes.kinds:
        add(Wish(f"kind:{k.kind}", "kind", k.kind, a["kind"], dict.fromkeys(k.place_ids, 1.0)))
    for i, v in enumerate(si.vibes):
        add(Wish(f"vibe:{i}", "vibe", v.phrase, a["vibe"], ranked(v.places)))
    if si.wishes.like:
        rows = list(rows)
        by = {r["id"]: r for r in rows}
        for lk in si.wishes.like:
            ref = by.get(lk.place_id)
            if ref is None:
                continue
            near = {r["id"]: s for r in rows
                    if r["id"] != ref["id"] and (s := similarity(ref, r, sigs)) >= cfg.wish["like_min"]}
            add(Wish(f"like:{lk.place_id}", "like", name(lk.place_id) or lk.place_id, a["like"], near))
    for g in si.liked_groups:
        add(Wish(f"group:{g}", "group", g, a["group"], group=g))
    purpose = si.context.purpose
    lean = cfg.wish["purpose"].get(purpose or "")
    if lean and "group" in lean:
        add(Wish(f"purpose:{purpose}", "purpose", purpose, a["purpose"], group=lean["group"]))
    elif lean and firm is not None:
        add(Wish(f"purpose:{purpose}", "purpose", purpose, a["purpose"],
                 dict.fromkeys(sorted(firm(lean["feature"], lean.get("value", "present"))), 1.0)))
    return tuple(out)


def strength(w: Wish, pid: str, role: str | None, group: str | None) -> float:
    if w.role is not None and role != w.role:
        return 0.0
    if w.places is not None:
        return w.places.get(pid, 0.0)
    return 1.0 if group == w.group else 0.0


def lift(ws, pid: str, role: str | None, group: str | None) -> tuple[float, list[tuple[str, str, str, float]]]:
    """(1 − Π(1 − a·strength), hits best first). Same multiplication order as decision.frame._wish."""
    keep, hits = 1.0, []
    for w in ws:
        s = strength(w, pid, role, group)
        keep *= 1 - w.a * s
        if s > 0:
            hits.append((w.key, w.kind, w.label, round(w.a * s, 4)))
    return 1 - keep, sorted(hits, key=lambda h: (-h[3], h[0]))
```

Lưu ý `add`: `dict.fromkeys(())` rỗng → bị bỏ (A2, A7, A8, A12).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_wishes.py -q`
Expected: PASS (17 test). Nếu A6/A7 fail vì signature: kiểm `corpus.serving.groups.signature` cần `n ≥ experience_min_n` (2) và `mention_rate ≥ 0.03` — fixture `feat(n=5)` có `rate=0.1`, đủ.

- [ ] **Step 6: Review diff**

`git diff -- config/decision.yaml src/decision/settings.py` và đọc lại `src/decision/wishes.py`, `tests/decision/test_wishes.py`. Không commit.

---

### Task 2: Điểm `wish` trong `rank`, `frame`, oracle và pipeline

**Files:**
- Modify: `src/decision/model.py` (`Cand.wishes`)
- Modify: `src/decision/rank.py` (`score`)
- Modify: `src/decision/frame.py` (`score_table`, `_wish`, `firm_ids`, `table`, `Table.wishes`)
- Modify: `src/decision/pipeline.py` (`Cands.__getitem__`, `Result.wishes`, `run`)
- Modify: `tests/decision/reference.py` (dựng wishes, truyền vào `score`)
- Test: `tests/decision/test_rank.py` (thêm)

**Interfaces:**
- Consumes: `wishes.build`, `wishes.lift` (Task 1); `diversify.display_group(c, cfg) -> str`; `frame.display_groups(region, role, cfg) -> list[str]`.
- Produces:
  - `Cand.wishes: list[tuple[str, str, str, float]]` (hits của `lift`).
  - `rank.score(cands, si, profile, cfg, voices=None, wishes=()) -> None`; `c.parts` có khóa `"wish"`, không còn `"vibe"`.
  - `frame.score_table(..., extra_voices=0, overrides=None, group=None, wishes=())`.
  - `frame.firm_ids(region) -> Callable[[str, str], set[str]]`.
  - `frame.Table.wishes: tuple` (mặc định `()`); memo tier `"wishes"`.
  - `pipeline.Result.wishes: tuple` (mặc định `()`).

- [ ] **Step 1: Write the failing tests**

Thêm vào cuối `tests/decision/test_rank.py`:

```python
from decision.wishes import build


def _meal(pid):
    return Cand(srec(pid, group="restaurant", category="Nhà hàng", usable=("meal",)), "meal")


def _dish(name, *ids):
    return {"dishes": [{"dish": name, "quote": name, "place_ids": list(ids)}], "kinds": [], "like": []}


def _run(cands, s):
    for c in cands:
        c.fit = 1.0
    score(cands, s, prof(), CFG, wishes=build(s, [c.rec for c in cands], CFG))


def test_meeting_a_wish_lifts_and_missing_one_never_lowers():  # B1, C4
    a, b = _meal("A"), _meal("B")
    _run([a, b], si(wishes=_dish("bánh căn", "A")))
    assert a.score > b.score and a.parts["wish"] > 0 and b.parts["wish"] == 0.0
    assert a.wishes[0][:3] == ("dish:bánh căn", "dish", "bánh căn")


def test_meeting_two_wishes_beats_meeting_one():  # B2
    a, b = _meal("A"), _meal("B")
    w = _dish("bánh căn", "A", "B")
    w["kinds"] = [{"kind": "lẩu", "quote": "lẩu", "place_ids": ["B"]}]
    _run([a, b], si(wishes=w))
    assert b.parts["wish"] > a.parts["wish"]


def test_wish_stays_within_one():  # B3
    a = _meal("A")
    w = _dish("bánh căn", "A")
    w["kinds"] = [{"kind": "lẩu", "quote": "lẩu", "place_ids": ["A"]}]
    _run([a], si(wishes=w, vibes=[{"phrase": "ấm", "places": ["A"]}], liked_groups=["meal"],
                 context={"purpose": "food_culture"}))
    assert 0 < a.parts["wish"] <= 1


def test_a_dish_does_not_lift_a_place_of_another_role():  # B4
    n = Cand(srec("N", group="nature", category="Thắng cảnh", usable=("experience",)), "experience")
    _run([n], si(wishes=_dish("bánh căn", "N")))
    assert n.parts["wish"] == 0.0


def test_a_said_wish_lifts_more_than_a_purpose():  # B5
    a = _meal("A")
    c = Cand(srec("C", group="cafe", usable=("experience",)), "experience")
    _run([a, c], si(wishes=_dish("bánh căn", "A"), context={"purpose": "relax"}))
    assert a.parts["wish"] > c.parts["wish"] > 0


def test_vibe_keeps_its_order_and_lifts_over_equal_places():  # B6
    cs = [Cand(srec(p, group="cafe", usable=("experience",)), "experience") for p in ("V1", "V2", "V3", "Z")]
    _run(cs, si(vibes=[{"phrase": "mây", "places": ["V3", "V1", "V2"]}]))
    assert [c.id for c in sorted(cs, key=lambda c: (-c.score, c.id))] == ["V3", "V1", "V2", "Z"]


def test_parts_have_wish_not_vibe_and_score_is_their_weighted_sum():  # B7
    a = _meal("A")
    _run([a], si(wishes=_dish("bánh căn", "A")))
    assert "wish" in a.parts and "vibe" not in a.parts
    assert a.score == round(sum(CFG.weights.get(k, 0.0) * v for k, v in a.parts.items()), 4)


def test_no_wishes_means_zero_wish_everywhere():  # A14, E10, Review Focus 3
    cs = [_meal("A"), Cand(srec("C"), "experience")]
    _run(cs, si())
    assert all(c.parts["wish"] == 0.0 and c.wishes == [] for c in cs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_rank.py -q`
Expected: FAIL — `TypeError: score() got an unexpected keyword argument 'wishes'`.

- [ ] **Step 3: `Cand.wishes`**

`src/decision/model.py`, trong `class Cand` ngay sau `matches`:

```python
    wishes: list[tuple] = field(default_factory=list)  # (key, kind, label, contribution): decision.wishes.lift hits
```

- [ ] **Step 4: `rank.score`**

`src/decision/rank.py`: thêm import

```python
from .diversify import display_group
from .wishes import lift
```

Thay hàm `score` bằng:

```python
def score(cands: list[Cand], si, profile, cfg, voices: list[int] | None = None, wishes=()) -> None:
    """voices: the sorted voices of every live candidate, when scoring a few of them alone (decision.frame).
    wishes: decision.wishes.build of this Search Input."""
    ws = wants(si, profile)
    voices = voices if voices is not None else sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
    top = max(1, len(voices) - 1)
    visited = set(si.novelty.visited) | set(profile.visited)
    nov_of = {"new": -1.0, "familiar": 0.3}
    for c in cands:
        pref, unc, matches = preference(c.rec, ws, si.activities.get(c.id), c.role)
        pop = min(1.0, bisect_left(voices, c.rec["provenance"].get("voices") or 0) / top)
        exp = si.context.experience
        wish, c.wishes = lift(wishes, c.id, c.role, display_group(c, cfg))
        c.parts = {"ctx": c.fit, "pref": round(pref, 4),
                   "nov": nov_of.get(si.novelty.level, 0.0) if c.id in visited else 0.0,
                   "exp": pop if exp == "first" else 1 - pop if exp == "returning" else 0.0,
                   "pop": round(pop, 4), "unc": -round(unc, 4),
                   "price": -round(profile.price_sensitivity * _price_norm(c.rec, cfg), 4),
                   "wish": round(wish, 4)}
        c.score = round(sum(cfg.weights.get(k, 0.0) * v for k, v in c.parts.items()), 4)
        c.matches = sorted(matches, key=lambda m: (-m[2], m[0]))
```

Giữ nguyên hàm `vibe_fit` (`tests/trip/test_vibes.py` còn dùng); nó không còn trong điểm.

- [ ] **Step 5: `frame`**

`src/decision/frame.py`:

1. Import: đổi `from .rank import vibe_fit, wants` thành `from .rank import wants` và thêm `from .wishes import build as build_wishes`.
2. Chữ ký `score_table`: thêm `group: list | None = None, wishes=()` sau `overrides`. Ngay đầu thân hàm thêm `group = group if group is not None else display_groups(region, role, cfg)`.
3. Xóa dòng `vibe = vibe_fit(si)`; trong `parts` thay khóa `"vibe"` bằng:

```python
             "wish": np.array(_round(_wish(region, wishes, role, group)))}
```

4. Thêm sau `_py_sum`:

```python
def _wish(region, wishes, role: list, group: list) -> np.ndarray:
    """decision.wishes.lift for every place: 1 − Π(1 − a·strength), multiplied in the order lift multiplies."""
    n = len(region.ids)
    keep = np.ones(n)
    if not wishes:
        return np.zeros(n)
    role_a = np.array([r or "" for r in role], dtype=object)
    group_a = np.array(group, dtype=object)
    for w in wishes:
        s = np.zeros(n)
        if w.places is not None:
            for pid, v in w.places.items():
                if (i := region.index.get(pid)) is not None:
                    s[i] = v
        else:
            s[group_a == w.group] = 1.0
        if w.role is not None:
            s[role_a != w.role] = 0.0
        keep = keep * (1 - w.a * s)
    return 1 - keep


def firm_ids(region):
    """wishes.build's firm(feature, value): the places whose served value is that, VERIFIED or OUTDATED."""
    def firm(fid: str, value: str) -> set[str]:
        col = region.feature(fid)
        return {pid for pid, v, ok in zip(region.ids, col.value, col.firm) if ok and v == value}
    return firm
```

5. `Table`: thêm field cuối `wishes: tuple = ()  # decision.wishes.build of the Search Input the score tier read`.
6. Trong `table`, thay khối từ `kc = _key(` đến `return Table(` bằng:

```python
    kw = _key(si.model_dump(mode="json", include={"wishes", "vibes", "liked_groups"}), si.context.purpose)
    names, index = region.column("name"), region.index
    wl = _cached(memo, "wishes", kw, lambda: build_wishes(
        si, region.light, cfg, region.sigs, firm_ids(region), lambda pid: names[index[pid]] if pid in index else None))
    kc = _key(kf, ks, hashlib.md5(live.tobytes()).hexdigest(), n_missing, profile.model_dump(mode="json"),
              si.model_dump(mode="json", include={"soft_weights", "novelty", "vibes", "context", "wishes", "liked_groups"}))
    score, voices = _cached(memo, "score", kc, lambda: score_table(region, si, profile, cfg, fit, live, role, act,
                                                                    n_missing, si.activities, group=group, wishes=wl))
    return Table(role, act, scr.status, scr.fails, fit, score, live, members, voices, group, anchor_areas, kc, wl)
```

Sửa docstring của `table`: tầng score "(+ wishes, liked_groups, novelty, vibes, live set)".

- [ ] **Step 6: `pipeline`**

`src/decision/pipeline.py`:

1. `Result`: thêm field cuối `wishes: tuple = ()`.
2. `Cands.__getitem__`: đổi `score([c], self.si, self.profile, self.cfg, voices=self.t.voices)` thành `score([c], self.si, self.profile, self.cfg, voices=self.t.voices, wishes=self.t.wishes)`.
3. Cuối `run`: `return Result(view, cands, {...}, group_of, days, shown, ranked, allocation, t.wishes)`.

- [ ] **Step 7: Oracle `reference.py`**

`tests/decision/reference.py`: thêm import

```python
from corpus.serving import feature
from decision.model import FIRM
from decision.wishes import build as build_wishes
```

Thay dòng `score(live, si, st.profile, cfg)` bằng:

```python
    wl = build_wishes(si, records, cfg, None,
                      lambda fid, value: {r["id"] for r in records
                                          if (f := feature(r, fid)) and f["status"] in FIRM and f["value"] == value},
                      lambda pid: by_id[pid]["identity"]["name"] if pid in by_id else None)
    score(live, si, st.profile, cfg, wishes=wl)
```

và truyền `wl` làm đối số cuối khi dựng `Result(...)` của reference (nếu nó dựng `Result` theo vị trí, thêm `wl` ở cuối).

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_rank.py tests/decision/test_wishes.py tests/decision/test_frame.py tests/decision/test_equivalence.py tests/trip/test_vibes.py -q`
Expected: PASS. `test_equivalence_eval_trips_on_the_real_snapshot` chạy trên snapshot thật; nếu fail chỉ ở nơi có "giống X" thì nguyên nhân là `region.sigs` khác `signature(record)` — sửa `build` cho đường reference dùng cùng sigs, không nới test.

- [ ] **Step 9: Run the whole decision suite**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision tests/trip/test_vibes.py tests/harness -q`
Expected: chỉ còn fail có sẵn `test_agent_sees_every_shown_place_but_reasons_only_for_the_first_page`.

- [ ] **Step 10: Review diff**

`git diff -- src/decision/model.py src/decision/rank.py src/decision/frame.py src/decision/pipeline.py tests/decision/reference.py tests/decision/test_rank.py`. Không commit.

---

### Task 3: Sinh ngẫu nhiên có mong muốn + memo

**Files:**
- Modify: `tests/decision/gen.py` (`sessions`)
- Test: `tests/decision/test_equivalence.py` (thêm)

**Interfaces:**
- Consumes: `si(..., wishes=, vibes=, liked_groups=, context={"purpose": ...})` (fixtures); `run(s, data, cfg, memo)`, `run_reference`.
- Produces: các Session ngẫu nhiên có `wishes`, `vibes`, `liked_groups`, `purpose`.

- [ ] **Step 1: Write the failing test**

Thêm vào `tests/decision/test_equivalence.py`:

```python
def test_equivalence_memo_follows_wish_changes():  # F3, Review Focus 5
    recs = records(7)
    data = Data(recs)
    meals = [r["id"] for r in recs if "meal" in r["usable_as"]][:5]
    with_wish = si(wishes={"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": meals}], "kinds": [],
                           "like": [{"place_id": recs[0]["id"], "but": [], "quote": "giống"}]},
                   liked_groups=["chill"], context={"purpose": "relax"})
    memo = {}
    for search in (with_wish, si(), with_wish):
        assert_same(Session(id="0" * 12, search_input=search, state=State()), recs, data=data, memo=memo)


def test_random_sessions_carry_wishes():  # F1
    ss = sessions(3, records(3), 30)
    assert any(s.search_input.wishes.dishes for s in ss) and any(s.search_input.liked_groups for s in ss)
    assert any(s.search_input.wishes.like for s in ss) and any(s.search_input.context.purpose for s in ss)
```

- [ ] **Step 2: Run to verify `test_random_sessions_carry_wishes` fails**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_equivalence.py -q -k "wish"`
Expected: `test_random_sessions_carry_wishes` FAIL (assert any(...) False); `test_equivalence_memo_follows_wish_changes` PASS hoặc FAIL — nếu FAIL là lỗi memo của Task 2, sửa khóa tier.

- [ ] **Step 3: Extend `gen.sessions`**

Trong `tests/decision/gen.py`, ngay trước `search = si(`:

```python
        meals = [r["id"] for r in recs if "meal" in r["usable_as"]]
        wish = {"dishes": [{"dish": f"món {j}", "quote": f"món {j}",
                            "place_ids": rng.sample(meals, min(len(meals), rng.randint(0, 4)))}
                           for j in range(rng.randint(0, 2))],
                "kinds": [{"kind": f"kiểu {j}", "quote": f"kiểu {j}", "place_ids": rng.sample(ids, rng.randint(0, 5))}
                          for j in range(rng.randint(0, 2))],
                "like": [{"place_id": rng.choice(ids), "but": [], "quote": "giống"}] if rng.random() < 0.3 else []}
        vibes = [{"phrase": "look", "places": rng.sample(ids, rng.randint(1, 4))}] if rng.random() < 0.3 else []
```

và trong lời gọi `si(`, thêm `wishes=wish, vibes=vibes, liked_groups=rng.sample(["nature", "sights", "chill", "meal"], rng.randint(0, 2)),`; trong dict `context` thêm `"purpose": rng.choice([None, "relax", "photo", "food_culture", "bond"]),`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_equivalence.py tests/decision/test_frame.py -q`
Expected: PASS (mọi seed, F2).

- [ ] **Step 5: Review diff**

`git diff -- tests/decision/gen.py tests/decision/test_equivalence.py`. Không commit.

---

### Task 4: Lý do trên thẻ (`why`) + đĩa xoay

**Files:**
- Modify: `src/decision/cards.py` (`wish_text`, `_fallback`, `_why`)
- Modify: `web/src/user/pd/types.ts` (`Claim.fit?`)
- Modify: `web/src/user/ui/DiscPicker.tsx` (`fitOf`)
- Test: `tests/decision/test_cards.py` (thêm), `tests/decision/test_pipeline.py` (thêm)

**Interfaces:**
- Consumes: `Cand.wishes` (Task 2), `wishes.SAID`, `corpus.serving.dishes.search(records, query, limit)`, `dishes.SOURCE_RANK`.
- Produces: `cards.wish_text(hit, rec, cfg) -> str`; mỗi phần tử `why` = `{"text", "sid"}` hoặc `{"text", "sid": None, "fit": False}` cho dòng dự phòng.

- [ ] **Step 1: Write the failing tests**

Thêm vào `tests/decision/test_cards.py`:

```python
def _menu(rec, *names):
    rec["menu"] = {"dishes": [{"name": n, "name_en": None, "section": None, "popular": False, "price": None}
                              for n in names], "photos": []}
    return rec


def test_why_says_the_wish_first_with_its_source():  # D1, D2
    c = cand(_menu(srec("M", group="restaurant", usable=("meal",)), "Bánh căn"),
             wishes=[("dish:bánh căn", "dish", "bánh căn", 0.8), ("purpose:food_culture", "purpose", "food_culture", 0.25)],
             matches=[("scenic_view", "present", 1.0, 7), ("crowd", "low", 0.5, 4)])
    got = [w["text"] for w in card(c, si(), CFG)["why"]]
    assert got[0] == "Có bánh căn bạn muốn ăn · theo menu"
    assert got[1:] == ["View đẹp, 7 người nhắc", "Độ đông: vắng, 4 người nhắc"]


def test_purpose_reason_is_marked_as_a_guess():  # D3
    c = cand(srec("C"), wishes=[("purpose:relax", "purpose", "relax", 0.25)])
    assert card(c, si(), CFG)["why"] == [{"text": "Hợp chuyến thư giãn ✎", "sid": None}]


def test_card_with_no_reason_still_says_something_true_but_not_a_fit():  # D4
    far = card(cand(srec("B", voices=240), minutes=30, center="chỗ ở"), si(), CFG)["why"]
    assert far == [{"text": "Cách chỗ ở ≈30 phút (ước tính)", "sid": None, "fit": False}]
    unknown = card(cand(srec("B", voices=240)), si(), CFG)["why"]
    assert unknown == [{"text": "240 người đã viết về nơi này", "sid": None, "fit": False}]


def test_other_wish_texts():
    c = cand(srec("K"), wishes=[("kind:karaoke", "kind", "karaoke", 0.8), ("vibe:0", "vibe", "mây", 0.8),
                                ("like:X", "like", "Mọt Cafe", 0.8)])
    assert [w["text"] for w in card(c, si(), CFG)["why"]] == [
        "Đúng loại karaoke bạn tìm", "Hợp phong cách “mây” bạn chọn", "Giống Mọt Cafe bạn thích"]
    g = cand(srec("C"), wishes=[("group:chill", "group", "chill", 0.4)])
    assert card(g, si(), CFG)["why"][0]["text"] == "Vì bạn thích cà phê và thư giãn"
```

Thêm vào `tests/decision/test_pipeline.py` (import `records`, `sessions` từ `gen`, `Data`, `run`, `CFG` nếu file chưa có):

```python
def test_every_card_of_every_group_has_a_reason():  # D5
    for seed in range(5):
        recs = records(seed)
        data = Data(recs)
        for s in sessions(seed, recs, 6):
            v = run(s, data, CFG).view
            cards = [c for g in v["groups"] for c in g["cards"]] + v["unverified"]["cards"]
            assert all(len(c["why"]) >= 1 for c in cards), s.id
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_cards.py tests/decision/test_pipeline.py -q`
Expected: FAIL (thiếu dòng mong muốn, `why` rỗng).

- [ ] **Step 3: Implement in `cards.py`**

Thêm import `from corpus.serving import dishes` và `from .wishes import SAID`. Thêm trước `_why`:

```python
PURPOSE_TEXT = {"relax": "thư giãn", "food_culture": "ăn uống, văn hóa", "nature": "thiên nhiên",
                "explore": "khám phá", "photo": "chụp ảnh"}
SOURCE_TEXT = {"menu_popular": " · theo menu", "menu": " · theo menu", "review_order": " · theo review"}


def wish_text(hit: tuple, rec: dict, cfg) -> str:
    """One met wish (decision.wishes.lift hit) in the user's words; a dish names where it was written down."""
    _, kind, label, _ = hit
    if kind == "dish":
        found = dishes.search([rec], label, 1)
        best = max((e["source"] for e in found[0]["evidence"]), key=dishes.SOURCE_RANK.get) if found else None
        return f"Có {label} bạn muốn ăn" + SOURCE_TEXT.get(best, "")
    if kind == "kind":
        return f"Đúng loại {label} bạn tìm"
    if kind == "vibe":
        return f"Hợp phong cách “{label}” bạn chọn"
    if kind == "like":
        return f"Giống {label} bạn thích"
    if kind == "group":
        return f"Vì bạn thích {cfg.labels['group'][label].lower()}"
    return f"Hợp chuyến {PURPOSE_TEXT.get(label, label)} ✎"


def _fallback(c: Cand) -> dict:
    """A card no wish, feature or nearness speaks for still says something true; fit False: no view counts it as a fit."""
    if c.missing:
        text = "Chưa có dữ liệu về nơi này; bạn tự kiểm trước chuyến"
    elif c.minutes is not None:
        text = f"Cách {c.center} ≈{c.minutes} phút (ước tính)"
    else:
        text = f"{c.rec['provenance'].get('voices') or 0} người đã viết về nơi này"
    return {"text": text, "sid": None, "fit": False}
```

Thay `_why` bằng:

```python
def _why(c: Cand, anchor: bool, cfg) -> list[dict]:
    out = [{"text": "Nơi bạn muốn đến", "sid": None}] if anchor else []
    out += [{"text": wish_text(h, c.rec, cfg), "sid": None} for h in c.wishes if h[1] in SAID]
    out += [{"text": f"{phrase(f, v, cfg)}, {n} người nhắc", "sid": f} for f, v, contrib, n in c.matches if contrib > 0]
    out += [{"text": wish_text(h, c.rec, cfg), "sid": None} for h in c.wishes if h[1] not in SAID]
    if c.minutes is not None and c.minutes <= cfg.near_min:
        out.append({"text": f"Gần {c.center}, ≈{c.minutes} phút (ước tính)", "sid": None})
    return out[:3] or [_fallback(c)]
```

- [ ] **Step 4: Web: lưới và đĩa xoay đọc cùng `why`**

`web/src/user/pd/types.ts`, trong `interface Claim` thêm:

```ts
  fit?: boolean // false: a true fact shown for a card nothing else speaks for; never counted as a fit
```

`web/src/user/ui/DiscPicker.tsx`, thay dòng `const fitOf = ...` bằng:

```ts
const fitOf = (c: Card) => {
  const fits = c.why.filter((w) => w.fit !== false)
  return { level: fits.length >= 3 ? 'Rất hợp' : fits.length === 2 ? 'Hợp' : fits.length === 1 ? 'Khá hợp' : 'Tạm được', matched: fits.map((w) => w.text) }
}
```

Run: `cd web && npx tsc --noEmit -p .` — Expected: không lỗi mới. Không build vào `web/dist` (prod).

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_cards.py tests/decision/test_pipeline.py tests/decision/test_equivalence.py -q`
Expected: PASS.

- [ ] **Step 6: Review diff**

`git diff -- src/decision/cards.py web/src/user/pd/types.ts web/src/user/ui/DiscPicker.tsx tests/decision/test_cards.py tests/decision/test_pipeline.py`. Không commit.

---

### Task 5: `why_not` nói mong muốn chưa khớp

**Files:**
- Modify: `src/decision/pipeline.py` (`_unmet`, `why_not`)
- Test: `tests/decision/test_pipeline.py` (thêm)

**Interfaces:**
- Consumes: `Result.wishes`, `Result.group_of`, `Result.ranked` (Task 2); `wishes.SAID`.
- Produces: `why_not(res, pid, si, cfg)["reasons"]` thêm dòng "Chưa thấy ghi món {label} ở nơi này" / "Chưa khớp mong muốn “{label}”".

- [ ] **Step 1: Write the failing tests**

Thêm vào `tests/decision/test_pipeline.py`:

```python
import dataclasses

from fixtures import hard


def _meals(n):
    return [srec(f"M{i:02d}", group="restaurant", category="Nhà hàng", usable=("meal",)) for i in range(n)]


def _session(search):
    return Session(id="0" * 12, search_input=search, state=State())


def test_why_not_names_the_unmet_wish_and_never_says_not_sold():  # D6, D7
    recs = _meals(8)
    cfg = dataclasses.replace(CFG, page_size=3)
    search = si(wishes={"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": ["M07"]}], "kinds": [], "like": []})
    res = run(_session(search), Data(recs), cfg)
    out = why_not(res, "M00", search, cfg)
    assert out["listed"] and any("xếp thứ" in r for r in out["reasons"])
    assert "Chưa thấy ghi món bánh căn ở nơi này" in out["reasons"]
    assert not any("không bán" in r for r in out["reasons"])


def test_why_not_puts_a_hard_fail_before_any_wish():  # D8
    recs = _meals(3)
    recs[0]["service"]["vegetarian_options"] = feat("no", n=5)
    search = si(hard_filters=[hard("vegetarian_options", "yes", op="eq")],
                wishes={"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": ["M00"]}], "kinds": [], "like": []})
    out = why_not(run(_session(search), Data(recs), CFG), "M00", search, CFG)
    assert out["reasons"][0].startswith("Bị loại") and not any("mong muốn" in r or "món" in r for r in out["reasons"])


def test_reasons_name_only_what_the_trip_or_record_holds():  # D9
    recs = _meals(4)
    search = si(wishes={"dishes": [{"dish": "bánh căn", "quote": "bánh căn", "place_ids": ["M03"]}], "kinds": [], "like": []})
    res = run(_session(search), Data(recs), CFG)
    texts = [w["text"] for g in res.view["groups"] for c in g["cards"] for w in c["why"]]
    texts += [r for pid in ("M00", "M01") for r in why_not(res, pid, search, CFG)["reasons"]]
    for t in texts:
        if "món" in t or "muốn ăn" in t:
            assert "bánh căn" in t
```

(Import `Session`, `State` từ `decision.session`, `why_not` từ `decision.pipeline`, `feat`, `srec`, `si` từ `fixtures` nếu file chưa có.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_pipeline.py -q -k "why_not or reasons_name"`
Expected: D6 FAIL (thiếu dòng "Chưa thấy ghi món").

- [ ] **Step 3: Implement**

`src/decision/pipeline.py`: thêm `from .wishes import SAID`. Thêm trước `why_not`:

```python
def _unmet(res: Result, pid: str, group: str) -> list[str]:
    """The said wishes that have places in this place's group, and that this place does not meet."""
    out = []
    for w in res.wishes:
        if w.kind not in SAID or w.places is None or pid in w.places:
            continue
        if any(res.group_of.get(p) == group for p in w.places):
            out.append(f"Chưa thấy ghi món {w.label} ở nơi này" if w.kind == "dish" else f"Chưa khớp mong muốn “{w.label}”")
    return out
```

Trong `why_not`, ở nhánh `elif (g := ...) is not None:` thêm sau `reasons.append(...)`:

```python
        reasons += _unmet(res, pid, g)
```

và ở nhánh `else: reasons.append("Điểm phù hợp thấp hơn các nơi đang gợi ý")` thêm `reasons += _unmet(res, pid, res.group_of.get(pid, "sights"))`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_pipeline.py tests/decision/test_decision_engine.py -q`
Expected: PASS (trừ fail có sẵn).

- [ ] **Step 5: Review diff**

`git diff -- src/decision/pipeline.py tests/decision/test_pipeline.py`. Không commit.

---

### Task 6: Bất biến và ca user

**Files:**
- Test: `tests/decision/test_wish_cases.py` (mới)
- Modify: code chỉ khi một ca lộ lỗi thật (sửa nguyên nhân, không nới test)

**Interfaces:**
- Consumes: `run`, `why_not`, `Data`, `Session`, `State`, `corpus.serving.dishes.search`; fixtures `srec`, `si`, `feat`, `hard`, `love`, `fit_entry`.

- [ ] **Step 1: Write the tests**

`tests/decision/test_wish_cases.py`:

```python
"""Wish ranking on whole runs: invariants (spec §12.1 C) and user cases from the persona matrix (§12.1 E)."""

from fixtures import feat, fit_entry, hard, love, si, srec

from corpus.serving import dishes
from decision.pipeline import Data, run, why_not
from decision.session import Session, State
from decision.settings import default

CFG = default()
KIND = ("scenic_view", "photo_spot", "cozy_decor", "live_music")


def menu(rec, *names):
    rec["menu"] = {"dishes": [{"name": n, "name_en": None, "section": None, "popular": False, "price": None}
                              for n in names], "photos": []}
    return rec


def meal(pid, *names, **kw):
    return menu(srec(pid, group="restaurant", category="Nhà hàng", usable=("meal",), **kw), *names)


def cafe(pid, **kw):
    return srec(pid, group="cafe", category="Quán cà phê", usable=("experience",), **kw)


def nature(pid, **kw):
    return srec(pid, group="nature", category="Thắng cảnh", usable=("experience",), **kw)


def dish_wish(recs, *names):
    return [{"dish": n, "quote": n, "place_ids": [h["id"] for h in dishes.search(recs, n)]} for n in names]


def W(dishes_=(), kinds=(), like=()):
    return {"dishes": list(dishes_), "kinds": list(kinds), "like": list(like)}


def go(search, recs, state=None, cfg=CFG):
    return run(Session(id="0" * 12, search_input=search, state=state or State()), Data(recs), cfg)


def order(res, gid):
    return res.ranked.get(gid, [])


def every(res):
    return {pid for ids in res.ranked.values() for pid in ids}


# ---------- invariants (C) ----------

def test_wishes_reorder_but_never_add_or_remove_places():  # C3, C4, C5
    recs = [meal("M1", "bánh căn"), meal("M2"), cafe("C1"), cafe("C2"), nature("N1"), nature("N2")]
    plain = go(si(), recs)
    wished = go(si(wishes=W(dish_wish(recs, "bánh căn"), [{"kind": "cà phê", "quote": "cà phê", "place_ids": ["C2"]}]),
                   liked_groups=["chill"], context={"purpose": "relax"}), recs)
    assert every(plain) == every(wished)
    assert set(order(plain, "nature")) == set(order(wished, "nature"))
    assert order(wished, "chill")[0] == "C2"
    assert all(wished.cands[p].parts["wish"] >= 0 for p in every(wished))


def test_a_wished_place_that_fails_a_hard_filter_never_shows():  # C1
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    recs[0]["service"]["vegetarian_options"] = feat("no", n=5)
    recs[1]["service"]["vegetarian_options"] = feat("yes", n=5)
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq")], wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert "M1" not in every(res) and order(res, "meal") == ["M2"]


def test_unknown_evidence_goes_to_unverified_not_the_list():  # C2
    recs = [meal("M1", "bánh căn")]
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq", policy="flag")],
                wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert "M1" not in every(res) and [c["id"] for c in res.view["unverified"]["cards"]] == ["M1"]


def test_anchor_and_chosen_places_keep_their_place():  # C6, C7
    recs = [meal("M1", "bánh căn"), meal("M2"), nature("N1"), nature("N2")]
    st = State(selected=["N2"])
    res = go(si(anchors=[{"place_id": "N1", "priority": "must"}], wishes=W(dish_wish(recs, "bánh căn")),
                liked_groups=["meal"]), recs, st)
    assert res.view["groups"][0]["id"] == "anchors" and res.view["groups"][0]["cards"][0]["id"] == "N1"
    assert order(res, "nature")[0] == "N2"


def test_novelty_new_keeps_a_visited_place_out_even_if_wished():  # C8, E15
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    res = go(si(novelty={"level": "new", "visited": ["M1"]}, wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert order(res, "meal") == ["M2"]


def test_stays_and_unknown_ids_in_a_wish_are_ignored():  # C9, C10
    recs = [cafe("C1"), srec("S1", group="stay", category="Khách sạn", usable=())]
    res = go(si(wishes=W(kinds=[{"kind": "view", "quote": "view", "place_ids": ["S1", "GHOST", "C1"]}])), recs)
    assert "S1" not in every(res) and "GHOST" not in res.view["shortlist"] and order(res, "chill") == ["C1"]


# ---------- user cases (E) ----------

def test_food_tour_place_with_both_dishes_first():  # E1
    recs = [meal("M1"), meal("M2", "bánh căn"), meal("M3", "bánh căn", "lẩu gà lá é")]  # ids against the wished order
    res = go(si(wishes=W(dish_wish(recs, "lẩu gà lá é", "bánh căn")), context={"purpose": "food_culture"}), recs)
    assert order(res, "meal") == ["M3", "M2", "M1"]


def test_couple_chill_quiet_cafe_first_nature_untouched():  # E2
    recs = [cafe("C1", features={"crowd": feat("high", n=5)}), cafe("C2", features={"crowd": feat("low", n=5)}),
            nature("N1"), nature("N2")]
    res = go(si(liked_groups=["chill"], soft_weights=[love("crowd", "low")], context={"companions": ["partner"]}), recs)
    assert order(res, "chill")[0] == "C2" and set(order(res, "nature")) == {"N1", "N2"}


def test_family_with_kids_fit_and_kind_beat_kind_only():  # E3
    good = {"fit": {"kids": fit_entry("good")}}
    recs = [srec("K1", group="amusement"), srec("K2", group="amusement"),
            srec("K3", group="amusement", features={"kids_play_area": feat("present", n=5)}, details=good)]
    res = go(si(context={"companions": ["kids"]}, soft_weights=[love("kids_play_area")],
                wishes=W(kinds=[{"kind": "khu vui chơi", "quote": "khu vui chơi", "place_ids": ["K3", "K2"]}])), recs)
    assert order(res, "sights") == ["K3", "K2", "K1"]


def test_wheelchair_photo_place_that_is_bad_for_wheelchairs_never_shows():  # E4
    recs = [nature("P1", features={"photo_spot": feat("present", n=5)}, details={"fit": {"wheelchair": fit_entry("bad")}}),
            nature("P2", features={"photo_spot": feat("present", n=5)}, details={"fit": {"wheelchair": fit_entry("good")}})]
    res = go(si(hard_filters=[hard("fit.wheelchair", "bad")], context={"purpose": "photo"}), recs)
    assert "P1" not in every(res) and order(res, "nature") == ["P2"]


def test_vegetarian_group_wished_dish_unverified_stays_out():  # E5
    recs = [meal("M1", "bánh căn"), meal("M2", "bánh căn")]
    recs[1]["service"]["vegetarian_options"] = feat("yes", n=5)
    res = go(si(hard_filters=[hard("vegetarian_options", "yes", op="eq")], wishes=W(dish_wish(recs, "bánh căn"))), recs)
    assert order(res, "meal") == ["M2"] and "M1" not in every(res)


def test_like_x_but_quieter():  # E6
    f = lambda crowd: {**{k: feat("present", n=5) for k in KIND}, "crowd": feat(crowd, n=5)}
    recs = [cafe("X", features=f("high")), cafe("Z", features=f("high")), cafe("Y", features=f("low")),
            cafe("W", features={**{k: feat("present", n=5) for k in ("hiking", "camping", "animals")},
                                "crowd": feat("high", n=5)})]
    res = go(si(wishes=W(like=[{"place_id": "X", "but": ["crowd=low"], "quote": "giống X nhưng vắng hơn"}]),
                soft_weights=[love("crowd", "low")]), recs)
    chill = order(res, "chill")
    assert chill.index("Y") < chill.index("Z") < chill.index("W")
    assert "X" in chill and res.cands["X"].parts["wish"] == 0.0


def test_cloud_hunting_look_keeps_its_order():  # E7
    recs = [nature(p) for p in ("V1", "V2", "V3", "Z")]
    res = go(si(vibes=[{"phrase": "sương sáng sớm", "places": ["V3", "V1", "V2"]}]), recs)
    assert order(res, "nature") == ["V3", "V1", "V2", "Z"]


def test_nightlife_bar_is_not_banned_by_no_alcohol_and_karaoke_leads():  # E8
    recs = [srec("B1", group="bar", category="Quán bar", usable=("experience",)),
            srec("K0", group="other", category="Quán nhậu", usable=("experience",)),
            srec("K1", group="other", category="Karaoke", usable=("experience",))]
    res = go(si(hard_filters=[hard("activity", "alcohol_consumption")],
                wishes=W(kinds=[{"kind": "karaoke", "quote": "karaoke", "place_ids": ["K1"]},
                                {"kind": "bar", "quote": "bar", "place_ids": ["B1"]}])), recs)
    assert "B1" in order(res, "chill") and order(res, "sights")[0] == "K1"


def test_mixed_group_both_wished_groups_lead():  # E9
    recs = [meal("M1"), meal("M2", "bánh căn"), nature("N1"), nature("N2"), cafe("C1")]
    res = go(si(context={"companions": ["kids", "parents"]}, wishes=W(dish_wish(recs, "bánh căn")),
                liked_groups=["nature", "meal"]), recs)
    assert order(res, "meal")[0] == "M2" and order(res, "nature") and order(res, "chill") == ["C1"]


def test_change_of_mind_keeps_the_chosen_place():  # E11
    recs = [meal("M1", "bánh căn"), meal("M2"), meal("M3")]
    first = go(si(wishes=W(dish_wish(recs, "bánh căn"))), recs, State(selected=["M2"]))
    st = State(selected=["M2"], shown=first.shown)
    second = go(si(wishes=W(kinds=[{"kind": "lẩu", "quote": "lẩu", "place_ids": ["M3"]}])), recs, st)
    assert order(second, "meal")[:2] == ["M2", "M3"]


def test_dish_no_corpus_place_has_changes_nothing():  # E12
    recs = [meal("M1"), meal("M2")]
    assert order(go(si(wishes=W([{"dish": "halal", "quote": "halal", "place_ids": []}])), recs), "meal") == \
        order(go(si(), recs), "meal")


def test_more_wishes_than_slots_keeps_everyone_and_orders_by_wishes_met():  # E13
    recs = [meal(f"M{i}", *(["a", "b"] if i == 9 else ["a"] if i == 8 else [])) for i in range(10)]
    res = go(si(context={"days": 1}, wishes=W(dish_wish(recs, "a", "b", "c", "d", "e"),
                                              [{"kind": f"k{j}", "quote": f"k{j}", "place_ids": []} for j in range(3)])), recs)
    assert order(res, "meal")[:2] == ["M9", "M8"] and len(order(res, "meal")) == 10


def test_coach_party_hard_access_runs_before_the_wish():  # E14
    recs = [meal("R1"), meal("R2")]
    recs[0]["effort"]["coach_access"] = feat("no", n=5)
    recs[1]["effort"]["coach_access"] = feat("yes", n=5)
    res = go(si(context={"people": 18, "mobility": "car"}, hard_filters=[hard("coach_access", "no")],
                wishes=W(kinds=[{"kind": "nhà hàng", "quote": "nhà hàng", "place_ids": ["R1", "R2"]}])), recs)
    assert order(res, "meal") == ["R2"]
```

Ghi chú khi chạy: E8 kiểm đúng contract Trip §9 ("không cấm venue chỉ phục vụ rượu"); nếu B1 bị loại thì đó là lỗi có sẵn của `requirements`, báo user thay vì sửa test.

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_wish_cases.py -q`
Expected: PASS. Ca nào FAIL: dùng superpowers:systematic-debugging, sửa nguyên nhân trong `src/decision`; không đổi kỳ vọng trừ khi chính fixture sai (ghi rõ lý do).

- [ ] **Step 3: Review diff**

Đọc lại `tests/decision/test_wish_cases.py` và mọi file `src` bị sửa ở bước 2. Không commit.

---

### Task 7: Tốc độ trên snapshot thật

**Files:**
- Test: `tests/decision/test_wish_speed.py` (mới, marker `corpus`)

**Interfaces:**
- Consumes: `corpus.snapshot.shared().region().warm()`, `decision.eval_trips`, `decision.eval_search_input`, `frame.score_table`, `frame.build_wishes`, `frame.firm_ids`, `wishes.build`.

- [ ] **Step 1: Write the tests**

```python
"""Wish scoring stays fast on the real snapshot (spec §12.1 G). Baseline 2026-10-15, 3,208 places, 30 eval trips:
first run median 59 ms / p95 100 ms; memo hit median 17 ms."""

import statistics
import time

import pytest

from corpus.ontology import load
from decision import eval_search_input, eval_trips, frame
from decision.pipeline import Data, run
from decision.session import Session, State
from decision.settings import default
from decision.wishes import build

CFG = default()
pytestmark = pytest.mark.corpus


@pytest.fixture(scope="module")
def region():
    snap = pytest.importorskip("corpus.snapshot")
    try:
        return snap.shared().region().warm()
    except FileNotFoundError:
        pytest.skip("no snapshot")


def wished(si_, region):
    ids, groups, uses = region.ids, region.column("category_group"), region.column("usable_as")
    meals = [p for p, u in zip(ids, uses) if "meal" in u]
    cafes = [p for p, g in zip(ids, groups) if g == "cafe"]
    ref = max(cafes, key=lambda p: len(region.sigs[p]))
    data = si_.model_dump(mode="json")
    data["wishes"] = {"dishes": [{"dish": f"món {i}", "quote": f"món {i}", "place_ids": meals[i * 20:(i + 1) * 20]}
                                 for i in range(3)],
                      "kinds": [{"kind": "cà phê", "quote": "cà phê", "place_ids": cafes[:40]},
                                {"kind": "bar", "quote": "bar", "place_ids": [p for p, g in zip(ids, groups) if g == "bar"]}],
                      "like": [{"place_id": ref, "but": [], "quote": "giống"}]}
    data["liked_groups"] = ["chill", "nature"]
    data["context"]["purpose"] = "relax"
    return type(si_).model_validate(data)


def inputs(region):
    version, trips = eval_trips()
    ov = load().version
    return [wished(eval_search_input(t, version).model_copy(update={"ontology_version": ov}), region) for t in trips]


def ms(fn) -> float:
    def once():
        t = time.perf_counter()
        fn()
        return time.perf_counter() - t
    return statistics.median(once() for _ in range(3)) * 1000


def test_first_run_p95_within_budget(region):  # G1
    data = Data(region=region)
    times = sorted(ms(lambda: run(Session(id="0" * 12, search_input=s, state=State()), data, CFG, {}))
                   for s in inputs(region))
    p95 = times[int(0.95 * len(times)) - 1]
    assert p95 <= 120, f"p95 {p95:.0f} ms"


def test_memo_hit_median_within_budget(region):  # G2
    data = Data(region=region)
    times = []
    for s in inputs(region):
        session, memo = Session(id="0" * 12, search_input=s, state=State()), {}
        run(session, data, CFG, memo)
        times.append(ms(lambda: run(session, data, CFG, memo)))
    assert statistics.median(times) <= 20, f"median {statistics.median(times):.0f} ms"


def test_like_build_is_cheap(region):  # G3
    s = inputs(region)[0]
    t = ms(lambda: build(s, region.light, CFG, region.sigs, frame.firm_ids(region)))
    assert t <= 10, f"{t:.1f} ms"


def test_memo_hit_rebuilds_neither_wishes_nor_scores(region, monkeypatch):  # G4
    calls = {"score": 0, "wishes": 0}
    real_score, real_build = frame.score_table, frame.build_wishes

    def count(name, fn):
        def wrapped(*a, **k):
            calls[name] += 1
            return fn(*a, **k)
        return wrapped

    monkeypatch.setattr(frame, "score_table", count("score", real_score))
    monkeypatch.setattr(frame, "build_wishes", count("wishes", real_build))
    session, memo, data = Session(id="0" * 12, search_input=inputs(region)[0], state=State()), {}, Data(region=region)
    run(session, data, CFG, memo)
    calls.update(score=0, wishes=0)
    run(session, data, CFG, memo)
    assert calls == {"score": 0, "wishes": 0}
```

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision/test_wish_speed.py -q`
Expected: PASS. G1 hoặc G3 vượt ngưỡng: đo lại một lần khi máy rảnh (`uptime`); vẫn vượt thì tối ưu `_wish` / `build` (ví dụ chỉ duyệt `rows` cùng `category_group` với X), không nâng ngưỡng.

- [ ] **Step 3: Review diff**

Đọc lại `tests/decision/test_wish_speed.py`. Không commit.

---

### Task 8: Tài liệu chính thức, đo, kiểm toàn bộ

**Files:**
- Modify: `docs/PLACE_DECISION.md` (§2.1 bảng field, §8 công thức + quy tắc, §11 thẻ `why`, §18 danh sách module)
- Modify: `docs/TRIP_UNDERSTANDING.md` (§9 dòng `liked_groups`)
- Modify: `docs/log/DEV_LOG.md` (theo khuôn mẫu của chính file)
- Modify: `docs/superpowers/specs/2026-10-15-place-decision-needs-design.md` (§14: đánh dấu phần việc 2–3 đã xong phần điểm `wish` và lý do)

- [ ] **Step 1: `docs/PLACE_DECISION.md`**

§2.1 bảng: thay dòng `vibes` bằng các dòng (giữ văn phong bảng):

```markdown
| `wishes` (món, kiểu nơi, giống X), `vibes` | Xếp hạng | Thành phần `wish` (§8); không loại nơi nào |
| `liked_groups` | Xếp hạng | `wish` mức thấp cho nơi thuộc nhóm đó; không ẩn nhóm khác |
| `context.purpose` | Xếp hạng | `wish` mức thấp nhất theo map trong config; là suy luận (✎ trên thẻ) |
```

§8 công thức: thay dòng `+ w_vibe · vibe_fit ...` bằng

```text
      + w_wish  · wish                1 − Π(1 − a·strength) trên các mong muốn áp cho nơi đó (decision.wishes)
```

Thay quy tắc "`vibe_fit` chỉ nâng nơi user đã chọn qua ảnh thật…" bằng: "`wish` chỉ nâng: món (`place_ids` theo thứ tự), kiểu nơi, vibe (1 → 0,5 theo hạng), giống X (`corpus.serving.similarity` ≥ `like_min`, trừ X), `liked_groups`, `purpose`. Không khớp = 0, không âm, không loại; sàng lọc chạy trước. Mức `a`, `like_min`, map `purpose` ở `config/decision.yaml` `wish`."

§11 bảng thẻ, dòng "Vì sao phù hợp": "Mong muốn user nói (món · nguồn, kiểu, phong cách, giống X) trước, rồi 1–3 feature khớp, rồi `liked_groups` / `purpose` (✎), rồi vị trí. Thẻ không có lý do nào vẫn có một dòng thật (khoảng cách hoặc số người viết) mang `fit: false`: lưới và đĩa xoay hiện như nhau, mức "hợp" không đếm dòng này."

§18 danh sách module, thêm dòng `wishes.py                  mong muốn của Trip → điểm wish (§8)`.

- [ ] **Step 2: `docs/TRIP_UNDERSTANDING.md` §9**

Dòng `liked_groups` trong khối Search Input: thay "→ Place Decision chọn tab mặc định, ưu tiên nhóm này" bằng "→ Place Decision cộng điểm `wish` cho nhóm này (`PLACE_DECISION.md` §8)".

- [ ] **Step 3: `docs/log/DEV_LOG.md`**

Đọc 40 dòng đầu để theo đúng khuôn mẫu **Hiện tại / Trước đó**; thêm mục ngày 2026-10-15: điểm `wish` gộp mọi mong muốn của Trip, lý do `why` / `why_not`, số đo tốc độ đo được ở Task 7.

- [ ] **Step 4: Đo trên dữ liệu thật**

Run: `.venv/bin/python -m decision evaluate`
Expected: chạy hết 30 Trip State; ghi các chỉ số liên quan (hard violation = 0) vào báo cáo cuối cho user.

- [ ] **Step 5: Kiểm toàn bộ**

Run: `.venv/bin/python -m pytest --collect-in-virtualenv -p no:cacheprovider tests/decision tests/trip tests/harness tests/planning -q`
Expected: chỉ còn fail có sẵn `test_agent_sees_every_shown_place_but_reasons_only_for_the_first_page` (và fail có sẵn khác nếu `tests/trip` / `tests/planning` đã fail trước khi sửa — so với một lần chạy nền của chính các thư mục đó trước Task 1).

- [ ] **Step 6: Review diff toàn bộ**

`git diff --stat` (nếu git treo vì NFS thì liệt kê file đã sửa theo plan) và đọc lại từng file; loại mọi thay đổi ngoài plan. Không commit. Báo user: file đã đổi, kết quả test, số đo tốc độ, chỉ số evaluate.
