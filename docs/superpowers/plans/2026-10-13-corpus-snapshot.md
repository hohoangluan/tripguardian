# Corpus snapshot — plan triển khai

> **Cho agent thực thi (Sonnet):** làm **tuần tự** Task 0 → Task 10 trong một session. Không chạy song song: các task dùng chung interface. Mỗi bước có checkbox `- [ ]`; đánh `- [x]` ngay khi xong để session sau biết đã làm tới đâu. Plan chưa được thực thi (2026-10-13). Cách làm: superpowers:executing-plans (hoặc superpowers:subagent-driven-development).

**Mục tiêu:** corpus chiếm phần nhỏ nhất trong độ trễ từ lúc nhận yêu cầu tới lúc trả kết quả, ở mọi quy mô. Place Decision cho ra kết quả y hệt hiện tại.

**Kiến trúc:**
- Offline: `corpus serving` biên dịch thêm một **snapshot** bất biến theo vùng, gồm các bảng LanceDB ở `data/snapshot/<version>/<region>/`.
- Online: chỉ đọc snapshot qua `corpus.snapshot.Region`.
- Place Decision tính screen / fit / score cho mọi nơi một lượt bằng bảng (`decision.frame`, numpy). Các hàm Python hiện có vẫn là định nghĩa: chúng dựng `Cand` cho số ít nơi được hiển thị hoặc được hỏi tới.
- Oracle test chứng minh view không đổi.

**Tech:** Python 3.12 (`.venv/bin/python`), pytest (`pythonpath = src`), LanceDB 0.40, Polars 2.0, pyarrow 25, numpy 2.5, orjson. Tất cả đã cài trong `.venv`.

**Spec (đọc trước):** `docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md`.

## Global Constraints

- Tuân `RULE.md`: tài liệu tiếng Việt; code, comment, identifier, tên file tiếng Anh; thay đổi nhỏ nhất; module chỉ gọi nhau qua `__init__.py` (không deep import giữa module trong `src/`; test được import nội bộ như test hiện có).
- **Working tree dùng chung với nhiều session (kể cả Codex):**
  - Không commit, không push, không `git add -A`, không `git stash`, không `git checkout -- <file>`.
  - Đọc `git status` trước mỗi task. `src/decision/*`, `src/planning/*`, `src/corpus/serving/*` đang có thay đổi chưa commit của người khác: **đọc lại file ngay trước khi sửa, không hoàn tác thay đổi không phải của mình.**
  - Cuối mỗi task: `git diff -- <file của task>` để tự review.
- Không chạy `python -m corpus serving` / `build` / `aggregate` trên dữ liệu thật (chúng ghi lại `places.json`). Chỉ chạy `python -m corpus snapshot` (Task 4), lệnh này chỉ đọc `places.json` và intel.
- Build v13 của session khác (`corpus build --city dalat --skip tiktok`, log `logs/corpus_build_v13.log`): không kill, không chạy song song bước nào ghi intel / serving. Mọi phép đo trên dữ liệu thật (Task 1 trở đi) chỉ chạy **sau khi** Task 0 xác nhận build đã xong, để baseline và các lần đo sau cùng một corpus (có chỗ ở).
- Chỉ trạng thái được phục vụ (`VERIFIED`, `UNCERTAIN`, `OUTDATED`) vào snapshot. `DISABLED` / `NEEDS_REVIEW` không bao giờ vào (user đã duyệt 2026-10-13). Chỗ ở (`stay`) có trong snapshot cho Planning; Decision không bao giờ gợi ý chúng.
- Offline ghi, online chỉ đọc. Thiếu bằng chứng là `unknown`, không phải `false`. Hard constraint fail-closed.
- **Kết quả Place Decision phải y hệt**: `run(...).view == run_reference(...).view` (Task 2). Không nới test, không xóa test cũ.
- Ngân sách (spec §7): `create` p99 ≤ 30 ms (×1) / ≤ 150 ms (×20); `act` p99 ≤ 15 ms (×1) / ≤ 25 ms (×20); nạp vùng ≤ 1 s (×1) / ≤ 5 s (×20); Trip `Catalog` ≤ 1,5 s; tool agent ≤ 10 ms (×1) / ≤ 20 ms (×20). Không đạt thì **ghi số thật và báo**, không nới ngân sách.
- Mỗi lần đo: điền một dòng vào spec §9 "Kết quả đo" (không xóa dòng cũ) và giữ file JSON trong `data/bench/latency/`.
- Test: `.venv/bin/python -m pytest -q <đường dẫn>`. Không gọi mạng, không gọi model thật.
- TDD: viết test fail → code → test pass.

## Review Focus

- **Chỗ ở trong vùng** (khoảng 1.400 bản ghi `stay` sau build v13): Decision không bao giờ đưa chúng vào gợi ý, kể cả khi user chọn hay đặt anchor là một chỗ ở. Planning vẫn thấy chúng qua `serving.load()`. `Data.by_id` vẫn trả chúng cho `set_lodging`. Test ở Task 2 (bộ sinh có nhóm `stay`) và Task 4 (`test_compile_keeps_only_served_and_keeps_stays`).
- **Dữ liệu fixture thiếu field** (record không có `details`, `mention_rate`, `crowd_by_time`, `hours`, tọa độ `None`): `tables()` và `frame` phải coi là không có bằng chứng, không được ném lỗi. Test ở Task 3 (`test_tables_tolerate_missing_fields`) và Task 6/7 (bộ sinh ngẫu nhiên tạo các record này).
- **Override `activities` và nơi được giữ dù không có `role`** (user chọn một chỗ thuê xe): phải đi đường Python, cho đúng role và activity như `pipeline.run`. Test ở Task 8 (`test_equivalence_activity_override_and_roleless_keep`).
- **Nơi được giữ nhưng không có trong snapshot** (`stub`): vẫn live, có voices = 0 trong phép tính `pop` của mọi nơi khác. Test ở Task 8 (`test_equivalence_missing_kept_place`).
- **Hard filter đặc biệt** (`venue_category`, `activity`, `activity = alcohol_consumption`, `wine_tasting_available`) và filter `fit.<who>`: kết quả phải khớp `hard_result`. Test ở Task 6 (`test_screen_special_and_fit_filters`).
- **Snapshot chưa có, hoặc `current` trỏ tới version đã bị xóa**: lỗi rõ ràng, nói phải chạy lệnh nào, không trả list rỗng ngầm. Test ở Task 4 (`test_open_without_snapshot_explains`).

## Bản đồ file

| File | Trách nhiệm | Task |
|---|---|---|
| `src/bench/latency.py` (mới) | đo độ trễ, nhân bản vùng, ghi JSON | 1, 9 |
| `src/bench/__main__.py` | thêm lệnh `latency` | 1 |
| `src/decision/__init__.py` | export `eval_trips`, `eval_search_input` | 1 |
| `tests/decision/reference.py` (mới) | bản sao `pipeline.run` hiện tại, làm oracle | 2 |
| `tests/decision/gen.py` (mới) | sinh record và session ngẫu nhiên (seed cố định) | 2 |
| `tests/decision/test_equivalence.py` (mới) | `run` == `run_reference` | 2, 8 |
| `pyproject.toml` | marker `corpus`; khai báo `lancedb`, `polars`, `pyarrow`, `orjson` | 2, 4 |
| `src/corpus/snapshot/tables.py` (mới) | record → bảng Arrow (thuần, không I/O) | 3 |
| `src/corpus/snapshot/compile.py` (mới) | ghi `data/snapshot/<version>/`, `current`, dọn version cũ | 4 |
| `src/corpus/snapshot/read.py` (mới) | `Snapshot`, `Region`, `FeatureColumn` | 4 |
| `src/corpus/snapshot/__init__.py` (mới) | public API | 4 |
| `src/corpus/serving/run.py` | `run()` gọi compile ở cuối; `load()` đọc snapshot | 4 |
| `src/corpus/__main__.py` | lệnh `snapshot` | 4 |
| `config/serving.yaml` | `default_region`, `snapshot_keep_versions` | 4 |
| `src/trip/infrastructure/catalog.py` | `Catalog.from_snapshot`; tham số `evidence` | 5 |
| `src/trip/api/tools.py`, `src/trip/__main__.py`, `src/bench/generate.py` | dùng `Catalog.from_snapshot` | 5 |
| `src/requirements/checks.py`, `src/requirements/__init__.py` | tách `scope_allows` | 6 |
| `src/decision/frame.py` (mới) | screen / fit / score theo bảng | 6, 7, 9 |
| `src/decision/rank.py` | `score(..., voices=None)` | 7 |
| `src/corpus/serving/groups.py` | `mmr(..., sigs=None)` | 8 |
| `src/decision/pipeline.py` | `Data` trên `Region`; `run` trên bảng; `Cands` lazy; `Row` | 8 |
| `src/decision/engine.py` | `name_keys` từ bảng; memo theo phiên | 8, 9 |
| `docs/CORPUS.md`, `docs/PLACE_DECISION.md`, `README.md`, `docs/log/DEV_LOG.md` | tài liệu chính thức | 10 |

---

### Task 0: Kiểm tình trạng corpus (cổng trước mọi phép đo)

**Files:** không sửa code. Chỉ ghi kết quả vào spec §2.1 và §9.

Bối cảnh: lúc viết plan, serving (2026-10-08) có 1.696 nơi và 0 chỗ ở. Build v13 đang chạy, sẽ đưa khoảng 1.500 chỗ ở và 18 nơi mới vào intel rồi serving. Đọc `docs/plans/LODGING_AT_SELECTION_HANDOFF.md` §3.1: việc kiểm này cũng là việc của handoff đó.

- [ ] **Step 1: Build v13 xong chưa**

Run:
```bash
ps -eo pid,etime,args | grep "corpus build" | grep -v grep
grep -nE "^(aggregate|serving) dalat:|^build dalat: (aggregate|serving)" logs/corpus_build_v13.log | tail -5
tail -3 logs/corpus_build_v13.log
```

Expected khi xong: không còn tiến trình `corpus build`, và log có dòng `serving dalat: {...}`.

Nếu còn chạy:
- Ghi bước hiện tại và số call vào spec §2.1.
- Vẫn được làm phần **không đo trên dữ liệu thật**: Task 2 Step 1–6 và Task 3 (code + test fixture).
- Sau đó quay lại step này. Không tự chạy `aggregate` / `serving`.

Nếu build dừng mà không có dòng `serving dalat:` (lỗi): báo user, không tự chạy lại.

- [ ] **Step 2: Đếm corpus sau build**

Run:
```bash
.venv/bin/python - <<'EOF'
import collections, glob, json
d = json.load(open("data/serving/places.json"))
recs = d["records"]
print("serving built_at", d["built_at"], "records", len(recs))
print("status", collections.Counter(r["status"] for r in recs))
print("disabled skipped", d["summary"].get("disabled"))
stay = [r for r in recs if r["identity"].get("category_group") == "stay"]
print("stay", len(stay), "with price_per_night", sum(bool(r["operation"].get("price_per_night")) for r in stay))
print("intel files", len(glob.glob("data/intel/places/*.json")))
lst = {i["fid"] for i in json.load(open("data/gmaps/list/dalat.json"))["items"]}
ids = {r["id"] for r in recs}
print("main list not served", len(lst - ids))
EOF
```

Expected:
- `built_at` sau 2026-10-13.
- `stay` khoảng 1.400 trở lên, `price_per_night` khoảng 740.
- `status` không có `DISABLED` / `NEEDS_REVIEW`.

Ghi bảng số này vào spec §2.1, thêm một dòng "sau build v13". Nếu `stay` = 0 hoặc thấp hơn nhiều: báo user (handoff §3.1 có lệnh bù), không tự chạy.

- [ ] **Step 3: Ghi phần còn thiếu cho user** (không làm trong plan này)

Ghi vào spec §2.1 những gì corpus còn thiếu sau build:
- Chỗ ở chưa vào chỉ mục ngữ nghĩa (`python -m corpus index`, cần GPU).
- 119 chỗ ở chưa có ảnh (handoff §3.1, cần user giải captcha).
- TikTok chưa chạy trong build này.

Plan này không làm các việc đó.

---

### Task 1: Đo baseline độ trễ (code cũ)

**Files:**
- Create: `src/bench/latency.py`
- Modify: `src/bench/__main__.py` (thêm subcommand), `src/decision/__init__.py` (2 export)
- Test: `tests/bench/test_latency.py` (thư mục mới; thêm `tests/bench/__init__.py` nếu các thư mục test khác có)

**Interfaces:**
- Produces:
  - `bench.latency.pct(xs: list[float]) -> dict` (giây → ms `{n, p50, p95, p99, max}`)
  - `bench.latency.replicate(records: list[dict], n: int) -> list[dict]`
  - `bench.latency.decision_bench(data, cfg, trips_n: int = 30) -> dict`
  - `bench.latency.main(scales: list[int], out: Path | None) -> Path`
  - `decision.eval_trips() -> tuple[int, list[dict]]`, `decision.eval_search_input(trip, version) -> SearchInput`

- [ ] **Step 1: Viết test fail**

```python
# tests/bench/test_latency.py
from bench.latency import pct, replicate


def rec(i, area="area-1", dup=None):
    return {"id": f"P{i}", "identity": {"name": f"N{i}", "lat": 11.9, "lng": 108.4, "area": area},
            "near_duplicate_group": dup, "usable_as": ["experience"]}


def test_pct_reports_ms():
    p = pct([0.001, 0.002, 0.003, 0.004])
    assert p["n"] == 4 and p["max"] == 4.0 and p["p50"] in (2.0, 3.0)


def test_replicate_keeps_copies_apart():
    out = replicate([rec(1, dup=3), rec(2)], 3)
    assert len(out) == 6
    assert len({r["id"] for r in out}) == 6
    assert out[0]["id"] == "P1" and out[2]["id"] == "P1~1"
    assert out[2]["near_duplicate_group"] != out[0]["near_duplicate_group"]
    assert out[2]["identity"]["area"] != out[0]["identity"]["area"]
    assert out[2]["identity"]["lng"] > out[0]["identity"]["lng"]
    assert replicate([rec(1)], 1)[0] is not None
```

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/bench/test_latency.py`
Expected: FAIL (`ModuleNotFoundError: bench.latency`).

- [ ] **Step 3: Export eval trips trong `src/decision/__init__.py`**

Thêm vào `src/decision/__init__.py`:

```python
from .evaluate import search_input as eval_search_input
from .evaluate import trips as eval_trips
```

và thêm `"eval_search_input", "eval_trips"` vào `__all__`.

- [ ] **Step 4: Viết `src/bench/latency.py`**

```python
"""python -m bench latency: how long the corpus-backed steps take (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md
§7). Offline: no model, no network. Writes data/bench/latency/<timestamp>.json and prints a table."""

import json
import time
from datetime import datetime
from pathlib import Path

import orjson

ROOT = Path(__file__).resolve().parents[2]
SHIFT_DEG = 0.001  # each copy of a region moves this far east, so copies stay in the same city


def pct(xs: list[float]) -> dict:
    s = sorted(xs)
    at = lambda q: s[min(len(s) - 1, round(q * (len(s) - 1)))]  # noqa: E731
    ms = lambda v: round(v * 1000, 1)  # noqa: E731
    return {"n": len(s), "p50": ms(at(0.5)), "p95": ms(at(0.95)), "p99": ms(at(0.99)), "max": ms(s[-1])}


def timed(fn, *a, **k):
    t = time.perf_counter()
    out = fn(*a, **k)
    return out, time.perf_counter() - t


def replicate(records: list[dict], n: int) -> list[dict]:
    """n copies of a region's records: copy k has ids '<id>~k', its own areas and near-duplicate groups, points moved
    k * SHIFT_DEG east. Copy 0 is the original."""
    out = []
    for k in range(n):
        for r in records:
            c = orjson.loads(orjson.dumps(r))
            if k:
                c["id"] = f"{c['id']}~{k}"
                ident = c["identity"]
                if ident.get("area"):
                    ident["area"] = f"{ident['area']}~{k}"
                if ident.get("lng") is not None:
                    ident["lng"] = float(ident["lng"]) + k * SHIFT_DEG
                if c.get("near_duplicate_group") is not None:
                    c["near_duplicate_group"] = c["near_duplicate_group"] + k * 1_000_000
            out.append(c)
    return out


def decision_bench(data, cfg, trips_n: int = 30) -> dict:
    """create for each eval trip, then select x3, lock, drop, undo, page, why_not on its shortlist."""
    from corpus.ontology import load as load_ontology
    from decision import Engine, Store, eval_search_input, eval_trips

    eng = Engine(data, cfg, Store(None))
    version, trips = eval_trips()
    times: dict[str, list[float]] = {k: [] for k in ("create", "select", "lock", "drop", "undo", "page", "why_not")}
    for trip in trips[:trips_n]:
        si = eval_search_input(trip, version).model_dump(mode="json")
        si["ontology_version"] = load_ontology().version
        v, dt = timed(eng.create, si)
        times["create"].append(dt)
        sid = v["id"]
        cards = [c["id"] for g in v["view"]["groups"] for c in g["cards"]]
        for pid in cards[:3]:
            times["select"].append(timed(eng.act, sid, {"type": "select", "place_id": pid})[1])
        if len(cards) > 3:
            times["lock"].append(timed(eng.act, sid, {"type": "lock", "place_id": cards[3]})[1])
        if len(cards) > 4:
            times["drop"].append(timed(eng.act, sid, {"type": "drop", "place_id": cards[4], "reason": "far"})[1])
            times["undo"].append(timed(eng.act, sid, {"type": "undo"})[1])
        groups = [g["id"] for g in v["view"]["groups"] if g["id"] != "anchors"]
        if groups:
            times["page"].append(timed(eng.page, sid, groups[0])[1])
        if cards:
            times["why_not"].append(timed(eng.why_not, sid, cards[-1])[1])
    return {k: pct(v) for k, v in times.items() if v}


def startup_bench() -> dict:
    """Process-start costs, each measured once in this process (imports already warm)."""
    from corpus.serving import load as load_records
    from decision import Data

    from trip import Catalog
    from trip.infrastructure.settings import load as trip_settings  # trip exports no settings loader; bench is tooling

    out = {}
    _, out["serving.load_s"] = timed(load_records)
    _, out["decision.Data.load_s"] = timed(Data.load)
    _, out["trip.Catalog_s"] = timed(Catalog.load, ROOT / "data", trip_settings().n_min)
    return {k: round(v, 3) for k, v in out.items()}


def tools_bench(catalog, queries: list[str]) -> dict:
    """search_places as the Trip agent calls it (Catalog search, top 5)."""
    from trip.domain.resolve import search  # bench reaches into trip on purpose, like bench.generate does

    xs = [timed(lambda q=q: search(q, catalog)[:5])[1] for q in queries for _ in range(20)]
    return {"search_places": pct(xs)}


def main(scales: list[int], out: Path | None) -> Path:
    from corpus.serving import load as load_records
    from decision import Data
    from decision.settings import default

    cfg = default()
    base = load_records()
    result = {"at": datetime.now().isoformat(timespec="seconds"), "places": len(base), "startup": startup_bench(),
              "decision": {}}
    for n in scales:
        recs = replicate(base, n)
        data, load_s = timed(Data, recs)
        result["decision"][f"x{n}"] = {"places": len(recs), "data_s": round(load_s, 3), **decision_bench(data, cfg)}
    out = out or ROOT / "data" / "bench" / "latency"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return path
```

Ghi chú khi viết:
- `trip.infrastructure.settings.load` là cách `src/trip/__main__.py` lấy `cfg.n_min`. Bench là công cụ nên được import thẳng, giống `bench/generate.py`.
- `tools_bench` nhận catalog; ở Task 1 chưa gọi nó trong `main` (chưa có catalog nhanh). Task 9 mới gọi.
- `Data(recs)` ở Task 1 là `Data` cũ (list record).

- [ ] **Step 5: Thêm subcommand vào `src/bench/__main__.py`**

Trong `main()`, sau parser `run`:

```python
    lt = sub.add_parser("latency", help="corpus-backed latency (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md §7)")
    lt.add_argument("--scale", default="1", help="comma list of region copies, e.g. 1,5,20")
    lt.add_argument("--out", default="", help="directory (default data/bench/latency)")
```

và trong phần dispatch:

```python
    if args.cmd == "latency":
        from .latency import main as latency_main
        latency_main([int(x) for x in args.scale.split(",")], Path(args.out) if args.out else None)
        return 0
```

Đặt nhánh này **trước** các nhánh khác, để `latency` không import `generate` / `run`. Nếu dòng `from . import generate, load, quotas, run` ở đầu file làm chậm hoặc lỗi thì để nguyên, chỉ thêm nhánh.

- [ ] **Step 6: Chạy test, thấy pass**

Run: `.venv/bin/python -m pytest -q tests/bench/test_latency.py`
Expected: PASS.

- [ ] **Step 7: Đo baseline**

Run: `.venv/bin/python -m bench latency --scale 1,5,20`

Chạy khoảng vài phút, vì ×20 dùng code cũ trên ~34k nơi. Nếu ×20 chạy quá 15 phút thì dừng, chạy lại với `--scale 1,5` và ghi rõ "×20 không đo được" vào spec §9.

Expected: in JSON; có file mới trong `data/bench/latency/`.

- [ ] **Step 8: Ghi kết quả**

Điền một dòng vào spec §9: `Lần đo = baseline`, `Task = 1`, các cột từ JSON (`create`/`select` p50/p99 ×1, p99 ×20, `decision.Data.load_s`, `trip.Catalog_s`). Ghi chú tên file JSON.

- [ ] **Step 9: Tự review**

Run: `git diff -- src/bench/__main__.py src/decision/__init__.py` và `git status --short src/bench tests/bench`
Expected: chỉ có thay đổi của task này.

---

### Task 2: Oracle — bản sao `pipeline.run` hiện tại và test tương đương

**Files:**
- Create: `tests/decision/reference.py`, `tests/decision/gen.py`, `tests/decision/test_equivalence.py`
- Modify: `pyproject.toml` (marker `corpus`)

**Interfaces:**
- Produces:
  - `reference.run_reference(s, records: list[dict], cfg) -> Result`
  - `gen.records(seed: int, n: int = 60) -> list[dict]`
  - `gen.sessions(seed: int, records: list[dict], n: int) -> list[Session]`
  - `test_equivalence.assert_same(s, records, cfg)`

- [ ] **Step 1: Tạo `tests/decision/reference.py`**

Mở `src/decision/pipeline.py` **ngay lúc này** (người khác có thể vừa sửa) và chép nguyên văn hàm `run` thành `run_reference`. Chỉ đổi hai chỗ: tham số `data` thành `records`, và dòng đầu dựng `by_id`:

```python
"""The Place Decision run as it was before the corpus snapshot (a verbatim copy of decision.pipeline.run, per place
over a list of serving records). Oracle for tests/decision/test_equivalence.py: the table-based run must give the
same view. Update this copy only when the behaviour of run() changes on purpose."""

from collections import Counter

from requirements import activity_for

from decision.cards import card
from decision.chunks import assign_chunks, coverage, describe_chunks
from decision.curation import pending
from decision.diversify import display_group, pick, sizes
from decision.feasibility import evaluate
from decision.fit import centers, fit
from decision.model import Cand, role_of
from decision.pipeline import Result, _lodging_view, _rule_label, stub, wanted
from decision.rank import score
from decision.screen import screen
from decision.trip_days import trip_days
from decision.window import merge


def run_reference(s, records: list[dict], cfg) -> Result:
    by_id = {r["id"]: r for r in records}
    # ↓ from here: the body of decision.pipeline.run, with `data.records` -> `records`, `data.by_id` -> `by_id`
    ...
```

Thay `...` bằng thân hàm `run` chép nguyên văn. Mọi `data.records` thành `records`, mọi `data.by_id` thành `by_id`. Không đổi gì khác.

- [ ] **Step 2: Tạo `tests/decision/gen.py`**

Đọc `src/decision/session.py` để biết đúng field của `State`, `Drop` và `Profile` (`soft`, `visited`, `travel_mult`, `crowd_tolerance`, `price_sensitivity`, …). Hàm dưới chỉ dùng field có thật; field nào tên khác thì sửa theo file đó.

```python
"""Seeded random serving records and Decision sessions for the equivalence test: wide on purpose (missing fields,
UNCERTAIN values, conflicts, contexts, overrides, kept places without a role or a record)."""

import random

from fixtures import ALL_DAY, MONDAY, ONT, feat, fit_entry, hard, love, si, srec

from decision.session import Drop, Session, State

GROUPS = [("cafe", ("experience", "meal", "backup")), ("restaurant", ("meal",)), ("nature", ("experience",)),
          ("attraction", ("experience", "backup")), ("bar", ("experience",)), ("other", ()), ("rental", ()),
          ("stay", ())]  # lodging: config/category_defaults.yaml gives it usable_as []
FIDS = ["steep_or_stairs", "scenic_view", "cozy_decor", "crowd", "long_walk", "kids_play_area", "rest_benches",
        "toilet_available", "weather_exposed", "setting", "rough_road_access", "stroller_access", "food_quality"]
WHO = ["kids", "parents", "pregnant", "wheelchair"]


def _value(rng, fid):
    vals = list(ONT.features[fid].values)
    v = rng.choice(vals)
    status = rng.choice(["VERIFIED", "VERIFIED", "OUTDATED", "UNCERTAIN"])
    dist = {v: rng.randint(1, 5)}
    if rng.random() < 0.3:
        dist[rng.choice(vals)] = rng.randint(1, 3)
    ctx = {}
    if rng.random() < 0.3:
        ctx = {"time_of_day=morning": {rng.choice(vals): 2}, "day_type=weekend": {}}
    return feat(v, n=rng.randint(1, 6), status=status, dist=dist, by_context=ctx, rate=rng.random() / 5,
                agreement=round(rng.uniform(0.4, 1.0), 2))


def records(seed: int, n: int = 60) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        group, usable = rng.choice(GROUPS)
        feats = {f: _value(rng, f) for f in rng.sample(FIDS, rng.randint(0, 6))}
        hours = None if rng.random() < 0.15 else (
            ALL_DAY if rng.random() < 0.7 else {d: [["08:00", "17:00"]] for d in rng.sample(list(ALL_DAY), 3)})
        crowd = None if rng.random() < 0.5 else {dt: {b: rng.randint(10, 100) for b in ("morning", "noon", "afternoon", "evening")}
                                                 for dt in ("weekday", "weekend")}
        price = None if rng.random() < 0.5 else {"min_vnd": rng.choice([None, 30000, 80000]), "max_vnd": rng.choice([None, 150000])}
        details = None
        if rng.random() < 0.4:
            details = {"fit": {w: fit_entry(rng.choice(["good", "bad", "conditional"]),
                                            status=rng.choice(["VERIFIED", "UNCERTAIN"]), reasons=["r1", "r2"])
                               for w in rng.sample(WHO, 2)}}
        lat = None if rng.random() < 0.05 else 11.9 + rng.random() / 10
        r = srec(f"P{i:03d}", group=group, usable=usable, features=feats, hours=hours,
                 hours_status=rng.choice(["VERIFIED", "VERIFIED", "OUTDATED"]), crowd_by_time=crowd, price=price,
                 voices=rng.randint(0, 200), dup=rng.choice([None, None, 1, 2]), lat=lat,
                 lng=108.4 + rng.random() / 10, area=rng.choice(["area-1", "area-2", "area-3", None]), details=details)
        out.append(r)
    return out


def sessions(seed: int, recs: list[dict], n: int) -> list[Session]:
    rng = random.Random(seed)
    ids = [r["id"] for r in recs]
    out = []
    for k in range(n):
        hf = []
        for f in rng.sample(FIDS, rng.randint(0, 3)):
            hf.append(hard(f, rng.choice(list(ONT.features[f].values)), op=rng.choice(["ne", "ne", "eq"]),
                           policy=rng.choice(["exclude", "flag"])))
        if rng.random() < 0.2:
            hf.append(hard(f"fit.{rng.choice(WHO)}", "bad"))
        sw = [love(f, rng.choice(list(ONT.features[f].values)), weight=rng.choice([1, 2, -1]),
                   context=rng.choice([None, {"time_of_day": "morning"}]))
              for f in rng.sample(FIDS, rng.randint(0, 4))]
        anchors = [{"place_id": p, "priority": rng.choice(["must", "nice"])} for p in rng.sample(ids, rng.randint(0, 2))]
        if rng.random() < 0.2:
            anchors.append({"place_id": "MISSING1", "priority": "must"})
        stays = [r["id"] for r in recs if r["identity"]["category_group"] == "stay"]
        if stays and rng.random() < 0.3:  # a lodging named as an anchor must never become a suggestion
            anchors.append({"place_id": rng.choice(stays), "priority": "must"})
        search = si(hard_filters=hf, soft_weights=sw, anchors=anchors,
                    context={"companions": rng.sample(["kids", "parents"], rng.randint(0, 2)),
                             "days": rng.choice([1, 2, 3]),
                             "start_date": rng.choice([MONDAY.isoformat(), None]),
                             "month": rng.choice([None, 6, 12])},
                    pace={"level": rng.choice(["slow", "normal", "fast"]),
                          "crowd_tolerance": rng.choice([None, "avoid"])},
                    novelty={"level": rng.choice([None, "new", "familiar"]), "visited": rng.sample(ids, 2)})
        st = State(selected=rng.sample(ids, rng.randint(0, 3)),
                   dropped=[Drop(place_id=p, reason=None) for p in rng.sample(ids, rng.randint(0, 2))],
                   wishlist=rng.sample(ids, rng.randint(0, 1)),
                   relaxed=[[p, hf[0]["feature"]] for p in rng.sample(ids, 1)] if hf else [],
                   activities={p: rng.choice(["eating", "coffee", "sightseeing"]) for p in rng.sample(ids, rng.randint(0, 2))})
        out.append(Session(id=f"{k:012d}", search_input=search, state=st))
    return out
```

Nếu `si(...)` hoặc `State(...)` báo lỗi validate (ví dụ `anchors` cần thêm field, `start_date=None` cần `month`, giá trị `pace.level` khác), sửa **bộ sinh** cho hợp với schema. Không sửa schema. Thêm vào `State` các field profile ngẫu nhiên (`profile.soft`, `profile.visited`, `travel_mult`, `crowd_tolerance`, `price_sensitivity`) theo đúng tên trong `session.py`.

- [ ] **Step 3: Marker `corpus` trong `pyproject.toml`**

Trong `[tool.pytest.ini_options] markers`, thêm dòng:

```toml
    "corpus: needs data/snapshot/current (python -m corpus snapshot); skipped without it",
```

- [ ] **Step 4: Viết `tests/decision/test_equivalence.py`**

```python
"""The table-based Place Decision run gives the same view as the per-place run (tests/decision/reference.py)."""

import pytest

from gen import records, sessions
from reference import run_reference

from decision.pipeline import Data, run
from decision.settings import default

CFG = default()


def assert_same(s, recs, cfg=CFG):
    new = run(s, Data(recs), cfg).view
    old = run_reference(s, recs, cfg).view
    assert new == old, f"session {s.id}: views differ"


@pytest.mark.parametrize("seed", range(10))
def test_equivalence_random_sessions(seed):
    recs = records(seed)
    for s in sessions(seed, recs, 20):
        assert_same(s, recs)
```

- [ ] **Step 5: Chạy, thấy pass**

Lúc này `run` vẫn là code cũ, nên oracle khớp hiển nhiên. Test này kiểm bộ sinh có hợp lệ không.

Run: `.venv/bin/python -m pytest -q tests/decision/test_equivalence.py`
Expected: PASS, 10 test. Nếu có lỗi validate thì sửa `gen.py` (Step 2).

- [ ] **Step 6: Chạy cả bộ test decision**

Run: `.venv/bin/python -m pytest -q tests/decision`
Expected: cùng kết quả như trước task (ghi số pass/fail hiện có. Test fail sẵn từ trước không phải lỗi của task này; ghi tên chúng lại để so ở Task 8).

- [ ] **Step 7: Tự review**

Run: `git diff -- pyproject.toml` và `git status --short tests/decision`

---

### Task 3: Bảng snapshot (thuần, không I/O)

**Files:**
- Create: `src/corpus/snapshot/__init__.py` (tạm export `tables`), `src/corpus/snapshot/tables.py`
- Test: `tests/snapshot/test_tables.py` (thư mục mới; thêm `tests/snapshot/conftest.py` chèn `tests/decision` vào `sys.path` để dùng `fixtures.srec`, giống `tests/decision/conftest.py`)

**Interfaces:**
- Consumes: `corpus.serving.feature`, `corpus.serving.groups.signature` (cùng package `corpus`), `corpus.ontology.load`
- Produces: `corpus.snapshot.tables(records: list[dict], intel: list[dict] | None = None, videos: dict[str, str] | None = None) -> dict[str, pa.Table]`. Key: `places`, `features`, `feature_ctx`, `fit_verdicts`, `records`, `intel`, `videos`. Cột đúng như spec §5.

Ranh giới module: `corpus` không được import `decision` hay `requirements`, vì hai module đó import `corpus`. Các hàm cần cho cột suy ra (`role_of`, `activity_for`, `category_for`, `conf`, `_price_norm`) **chép công thức** vào `tables.py` dưới dạng hàm riêng (`_role_of`, `_activity`, `_category_for`, `_conf`, `_price_mid`). Test ở Step 1 so từng hàm chép với hàm gốc trên mọi record sinh ngẫu nhiên, để hai bản không bao giờ lệch nhau.

- [ ] **Step 1: Viết test fail**

```python
# tests/snapshot/test_tables.py
import orjson
import pyarrow as pa
import pytest

from fixtures import feat, fit_entry, srec
from gen import records

from corpus.snapshot import tables
from decision.model import role_of
from decision.rank import _price_norm, conf
from decision.settings import default
from requirements import activity_for, category_for

CFG = default()


def by_id(t: pa.Table) -> dict:
    return {r["id"]: r for r in t.to_pylist()}


def test_places_columns_match_the_per_place_functions():
    for seed in range(5):
        recs = records(seed)
        p = by_id(tables(recs)["places"])
        for r in recs:
            row = p[r["id"]]
            role = role_of(r)
            act = activity_for(r, None, role)
            if role and act == "eating":
                role = "meal"
            elif role and act:
                role = "experience"
            assert row["role"] == role
            assert row["activity"] == (activity_for(r, None, role) if role else activity_for(r, None, None))
            assert row["category_for"] == category_for(r)
            price = r["operation"].get("price_per_person")
            assert (row["price_mid_vnd"] is None) == (not price)
            if price:
                assert min(1.0, row["price_mid_vnd"] / CFG.price_ref_vnd) == _price_norm(r, CFG)


def test_features_rows_carry_reference_conf_and_fit_rows():
    r = srec("A", features={"scenic_view": feat("present", n=2, agreement=0.8, status="OUTDATED")},
             details={"fit": {"kids": fit_entry("bad")}})
    f = tables([r])["features"].to_pylist()
    sv = next(x for x in f if x["fid"] == "scenic_view")
    assert sv["conf"] == conf(r["experience"]["scenic_view"]) and sv["dist_values"] == ["present"]
    kid = next(x for x in f if x["fid"] == "fit.kids")
    assert kid["value"] == "bad" and kid["conf"] is None


def test_feature_ctx_keeps_first_max_and_skips_empty():
    v = feat("present", by_context={"time_of_day=morning": {"absent": 2, "present": 2}, "day_type=weekend": {}})
    r = srec("A", features={"scenic_view": v})
    ctx = tables([r])["feature_ctx"].to_pylist()
    assert ctx == [{"place_id": "A", "fid": "scenic_view", "ctx_key": "time_of_day=morning", "top": "absent"}]


def test_open_mask_and_crowd_columns():
    r = srec("A", hours={"mon": [["08:00", "17:00"]], "tue": []},
             crowd_by_time={"weekday": {"morning": 90}, "peak": {"day": "mon", "hour": 9, "pct": 100}})
    row = tables([r])["places"].to_pylist()[0]
    assert row["open_mask"] == 0b0000001 and row["has_hours_value"] is True
    assert row["crowd_weekday_morning"] == 90 and row["crowd_weekend_noon"] is None and row["has_crowd"] is True


def test_records_table_roundtrips_json():
    recs = records(1)
    t = by_id(tables(recs)["records"])
    for r in recs:
        assert orjson.loads(t[r["id"]]["json"]) == orjson.loads(orjson.dumps(r))


def test_tables_tolerate_missing_fields():
    r = srec("A", hours=None, lat=None)
    r.pop("details", None)
    r["operation"].pop("crowd_by_time")
    out = tables([r])
    row = out["places"].to_pylist()[0]
    assert row["lat"] is None and row["hours_status"] is None and row["has_crowd"] is False
```

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/snapshot/test_tables.py`
Expected: FAIL (`ModuleNotFoundError: corpus.snapshot`).

- [ ] **Step 3: Viết `src/corpus/snapshot/tables.py`**

```python
"""Serving records -> the snapshot tables (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md §5). Pure: no
I/O. Derived columns repeat the per-place formulas of decision / requirements, which corpus cannot import;
tests/snapshot/test_tables.py checks each copy against its original."""

import orjson
import pyarrow as pa

from ..categories import group as category_group
from ..ontology import load as load_ontology
from ..serving.groups import signature
from ..serving.record import feature

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # decision.trip_days.DAYS
DAYTIME = ("morning", "noon", "afternoon", "evening")     # decision.fit.DAYTIME
STATUS_W = {"VERIFIED": 1.0, "OUTDATED": 0.7, "UNCERTAIN": 0.5}  # decision.rank.STATUS_W
FULL_N = 3                                                 # decision.rank.FULL_N


def _role_of(rec: dict) -> str | None:  # decision.model.role_of
    u = rec.get("usable_as") or []
    return "experience" if "experience" in u else "meal" if "meal" in u else None


def _category_for(rec: dict) -> str | None:  # requirements.checks.category_for
    ...


def _activity(rec: dict, role: str | None) -> str | None:  # requirements.checks.activity_for(rec, None, role)
    ...


def _final_role(rec: dict) -> str | None:  # decision.pipeline.run without an activities override
    role = _role_of(rec)
    act = _activity(rec, role)
    if role and act == "eating":
        return "meal"
    if role and act:
        return "experience"
    return role


def _conf(f: dict) -> float:  # decision.rank.conf
    return f["confidence"]["agreement"] * min(1.0, f["n"] / FULL_N) * STATUS_W[f["status"]]


def _price_mid(rec: dict) -> float | None:  # decision.rank._price_norm before / price_ref_vnd
    p = rec["operation"].get("price_per_person")
    if not p:
        return None
    v = p["value"]
    lo = v.get("min_vnd") or 0
    return (lo + (v.get("max_vnd") or lo)) / 2
```

Viết thân `_category_for` và `_activity` bằng cách **chép nguyên văn** `category_for` và `activity_for` trong `src/requirements/checks.py` (với `activity=None`). `category_group` của requirements chính là `corpus.categories.group`: kiểm `src/corpus/__init__.py` xem `category_group` export từ đâu, rồi import đúng hàm đó.

Tiếp theo trong cùng file là hàm `tables()`:

```python
def tables(records: list[dict], intel: list[dict] | None = None, videos: dict[str, str] | None = None) -> dict[str, pa.Table]:
    ont = load_ontology()
    places, feats, ctx, verdicts, recs = [], [], [], [], []
    for r in records:
        ident, op = r["identity"], r["operation"]
        hours, crowd = op.get("hours"), op.get("crowd_by_time")
        role = _final_role(r)
        row = {"id": r["id"], "name": ident.get("name") or r["id"], "status": r["status"], "kind": ident.get("kind"),
               "category": ident.get("category"), "category_group": ident.get("category_group"),
               "area": ident.get("area"), "address": ident.get("address"),
               "lat": None if ident.get("lat") is None else float(ident["lat"]),
               "lng": None if ident.get("lng") is None else float(ident["lng"]),
               "usable_as": list(r.get("usable_as") or []), "role": role,
               "activity": _activity(r, role), "category_for": _category_for(r),
               "is_stay": ident.get("category_group") == "stay",
               "near_duplicate_group": r.get("near_duplicate_group"),
               "voices": (r.get("provenance") or {}).get("voices") or 0, "price_mid_vnd": _price_mid(r),
               "hours_status": hours["status"] if hours else None,
               "has_hours_value": bool(hours and hours.get("value")),
               "open_mask": sum(1 << i for i, d in enumerate(DAYS) if hours and (hours.get("value") or {}).get(d)),
               "has_crowd": bool(crowd),
               "signature": sorted(f"{fid}={v}" for fid, v in signature(r))}
        for dt in ("weekday", "weekend"):
            for b in DAYTIME:
                row[f"crowd_{dt}_{b}"] = ((crowd or {}).get(dt) or {}).get(b)
        places.append(row)
        for fid in ont.features:
            f = feature(r, fid)
            if f is None:
                continue
            feats.append({"place_id": r["id"], "fid": fid, "value": f["value"], "status": f["status"], "n": f["n"],
                          "conf": _conf(f), "dist_values": list(f["distribution"])})
            for key, d in (f.get("by_context") or {}).items():
                if d:
                    ctx.append({"place_id": r["id"], "fid": fid, "ctx_key": key, "top": max(d, key=d.get)})
        for who in ((r.get("details") or {}).get("fit") or {}):
            f = feature(r, f"fit.{who}")
            if f is not None:
                feats.append({"place_id": r["id"], "fid": f"fit.{who}", "value": f["value"], "status": f["status"],
                              "n": None, "conf": None, "dist_values": list(f["distribution"])})
                verdicts.append({"place_id": r["id"], "who": who, "value": f["value"], "status": f["status"]})
        recs.append({"id": r["id"], "json": orjson.dumps(r).decode()})
    return {"places": _table(places, PLACES_SCHEMA), "features": _table(feats, FEATURES_SCHEMA),
            "feature_ctx": _table(ctx, CTX_SCHEMA), "fit_verdicts": _table(verdicts, VERDICT_SCHEMA),
            "records": _table(recs, RECORDS_SCHEMA),
            "intel": _table([{"id": i["place_fid"], "json": orjson.dumps(i).decode()} for i in intel or []], RECORDS_SCHEMA),
            "videos": _table([{"video_id": k, "place_id": v} for k, v in sorted((videos or {}).items())], VIDEOS_SCHEMA)}
```

Khai báo schema Arrow tường minh (`PLACES_SCHEMA = pa.schema([...])`, …). Lý do: bảng rỗng vẫn đúng kiểu, và `None` không bị đoán sai kiểu. Kiểu theo spec §5.1:
- `lat`/`lng`/`price_mid_vnd`: `pa.float64()`
- `voices`: `pa.int32()`
- `near_duplicate_group`: `pa.int64()`
- `open_mask`: `pa.uint8()`
- `crowd_*`: `pa.int16()`
- `usable_as` / `signature` / `dist_values`: `pa.list_(pa.string())`
- `conf`: `pa.float64()`
- `n`: `pa.int32()`

`_table(rows, schema)` = `pa.Table.from_pylist(rows, schema=schema)`.

Một lưu ý về `signature()`: hàm này trả `frozenset` các tuple `(fid, value)`. Lưu thành chuỗi `"fid=value"` đã sort. `read.py` (Task 4) dựng lại `frozenset((fid, value))` bằng `s.split("=", 1)`. Giá trị ontology không chứa `=`; nếu có thì test Task 4 sẽ bắt.

- [ ] **Step 4: `src/corpus/snapshot/__init__.py` tạm thời**

```python
"""corpus.snapshot: what online reads (docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md). Offline compiles
it (python -m corpus snapshot, and at the end of python -m corpus serving); online only reads it."""

from .tables import tables

__all__ = ["tables"]
```

- [ ] **Step 5: Chạy test, thấy pass**

Run: `.venv/bin/python -m pytest -q tests/snapshot/test_tables.py`
Expected: PASS, 6 test.

- [ ] **Step 6: Tự review**

Run: `git status --short src/corpus/snapshot tests/snapshot`

---

### Task 4: Compile ra đĩa + đọc online (`Snapshot`, `Region`) + `serving.load()`

**Files:**
- Create: `src/corpus/snapshot/compile.py`, `src/corpus/snapshot/read.py`
- Modify: `src/corpus/snapshot/__init__.py`, `src/corpus/serving/run.py`, `src/corpus/serving/__init__.py` (nếu cần export), `src/corpus/__main__.py`, `config/serving.yaml`, `pyproject.toml`
- Test: `tests/snapshot/test_snapshot.py`

**Interfaces:**
- Consumes: `corpus.snapshot.tables(...)` (Task 3)
- Produces:
  - `corpus.snapshot.compile_snapshot(city: str, root: Path | None = None) -> dict` (summary). Đọc `data/serving/places.json`, intel, TikTok `place_filter`.
  - `corpus.snapshot.Snapshot.open(root: Path | None = None) -> Snapshot`
  - `Snapshot.region(key: str | None = None) -> Region`; `Snapshot.version: str`
  - `corpus.snapshot.Region.from_records(records, intel=None, videos=None, key="test") -> Region`
  - Thuộc tính của `Region`:
    - `key: str`
    - `ids: list[str]`, `index: dict[str, int]`
    - `places: pl.DataFrame`, `stay: frozenset[str]`
    - `sigs: dict[str, frozenset]`
    - `videos: dict[str, str]`
    - `light: list[dict]`: mỗi nơi một dict nhỏ `{"id", "identity": {"category_group"}, "usable_as", "near_duplicate_group"}`, theo thứ tự `ids`, dựng một lần
  - Phương thức của `Region`:
    - `column(name) -> list`: một cột của `places` dưới dạng list Python, cache. Không lấy từng ô bằng `places[col][i]`, vì Polars chậm khi truy cập từng scalar.
    - `record(pid) -> dict | None`, `records() -> list[dict]`
    - `by_id: Mapping[str, dict]`
    - `intel() -> list[dict]`
    - `feature(fid) -> FeatureColumn`
    - `ctx_top(fid, ctx_key) -> list[str | None]`
    - `verdict(who) -> tuple[list[str | None], list[str | None]]`
  - `corpus.snapshot.FeatureColumn` (căn theo thứ tự `Region.ids`):
    - `value: list[str | None]`, `status: list[str | None]`
    - `exists: np.ndarray[bool]`, `firm: np.ndarray[bool]`, `uncertain: np.ndarray[bool]`
    - `conf: np.ndarray[float64]` (0.0 khi không có)
    - `n: list[int | None]`
    - `eq(v) -> np.ndarray[bool]`, `has(v) -> np.ndarray[bool]` (v ∈ distribution), `only(v) -> np.ndarray[bool]` (set(distribution) ⊆ {v})
  - `corpus.serving.load(region: str | None = None) -> list[dict]` (đọc snapshot)

- [ ] **Step 1: Viết test fail**

```python
# tests/snapshot/test_snapshot.py
import json

import numpy as np
import pytest

from fixtures import feat, srec
from gen import records

from corpus.snapshot import Region, Snapshot, compile_snapshot


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    recs = records(3)
    (tmp_path / "serving").mkdir()
    (tmp_path / "serving" / "places.json").write_text(
        json.dumps({"built_at": "x", "summary": {}, "records": recs}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "intel" / "places").mkdir(parents=True)
    for r in recs:
        (tmp_path / "intel" / "places" / f"{r['id']}.json").write_text(json.dumps(
            {"place_fid": r["id"], "place_name": r["identity"]["name"], "identity": {"category": "Quán cà phê"},
             "estimates": {}, "operation": {}, "features": {}}), encoding="utf-8")
    return tmp_path, recs


def test_compile_then_open_reads_the_same_records(data_dir):
    root, recs = data_dir
    summary = compile_snapshot("dalat")
    assert summary["regions"]["dalat"]["places"] == len(recs)
    reg = Snapshot.open().region("dalat")
    assert reg.ids == [r["id"] for r in recs]
    assert reg.record(recs[0]["id"]) == json.loads(json.dumps(recs[0]))
    assert reg.record("nope") is None and "nope" not in reg.by_id
    assert len(reg.records()) == len(recs) and len(reg.intel()) == len(recs)


def test_current_switches_atomically_and_old_versions_are_pruned(data_dir):
    root, _ = data_dir
    for _ in range(4):
        compile_snapshot("dalat")
    versions = [p for p in (root / "snapshot").iterdir() if p.is_dir()]
    assert len(versions) == 3  # snapshot_keep_versions in config/serving.yaml
    assert (root / "snapshot" / "current").read_text().strip() == Snapshot.open().version


def test_open_without_snapshot_explains(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="python -m corpus snapshot"):
        Snapshot.open()
    (tmp_path / "snapshot").mkdir()
    (tmp_path / "snapshot" / "current").write_text("20000101T000000")
    with pytest.raises(FileNotFoundError, match="python -m corpus snapshot"):
        Snapshot.open()


def test_feature_column_is_aligned_with_places():
    a = srec("A", features={"scenic_view": feat("present", dist={"present": 2, "absent": 1}, status="UNCERTAIN")})
    b = srec("B")
    reg = Region.from_records([a, b])
    col = reg.feature("scenic_view")
    assert list(col.exists) == [True, False] and list(col.uncertain) == [True, False]
    assert list(col.eq("present")) == [True, False] and list(col.has("absent")) == [True, False]
    assert list(col.only("present")) == [False, False]
    assert reg.sigs["A"] == frozenset() and reg.stay == frozenset()
    assert reg.column("id") == ["A", "B"]
    assert reg.light[0] == {"id": "A", "identity": {"category_group": "cafe"},
                            "usable_as": ["experience", "meal", "backup"], "near_duplicate_group": None}


def test_compile_keeps_only_served_and_keeps_stays(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    ok, stay = srec("OK"), srec("H", group="stay", usable=())
    hidden = [{**srec("NR"), "status": "NEEDS_REVIEW"}, {**srec("DIS"), "status": "DISABLED"}]
    (tmp_path / "serving").mkdir()
    (tmp_path / "serving" / "places.json").write_text(
        json.dumps({"built_at": "x", "summary": {}, "records": [ok, stay, *hidden]}), encoding="utf-8")
    (tmp_path / "intel" / "places").mkdir(parents=True)
    compile_snapshot("dalat")
    reg = Snapshot.open().region("dalat")
    assert reg.ids == ["OK", "H"]
    assert reg.stay == frozenset({"H"}) and reg.record("H")["identity"]["category_group"] == "stay"


def test_serving_load_reads_the_snapshot(data_dir):
    from corpus.serving import load
    _, recs = data_dir
    compile_snapshot("dalat")
    assert [r["id"] for r in load()] == [r["id"] for r in recs if r["status"] in ("VERIFIED", "UNCERTAIN", "OUTDATED")]
```

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/snapshot/test_snapshot.py`
Expected: FAIL (`ImportError: cannot import name 'Region'`).

- [ ] **Step 3: Config và dependency**

Thêm vào `config/serving.yaml`:

```yaml
default_region: dalat        # the region online reads when the caller names none (config/cities.yaml key)
snapshot_keep_versions: 3    # data/snapshot/<version>/ kept; older ones are deleted by the next compile
```

Thêm vào `dependencies` của `pyproject.toml`: `"lancedb>=0.40"`, `"polars>=2.0"`, `"pyarrow>=20"`, `"orjson>=3.10"`, `"numpy>=2.0"`.

- [ ] **Step 4: Viết `src/corpus/snapshot/compile.py`**

```python
"""data/serving/places.json (+ intel, TikTok place_filter) -> data/snapshot/<version>/<region>/ LanceDB tables, then
data/snapshot/current names that version (written atomically, like data/index/current). Offline only."""

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import lancedb
import yaml

from ..crawl.common.files import ROOT, data_dir, now
from ..serving.record import SERVED, config
from .tables import tables


def _region_of(rec: dict, cities: dict, city: str) -> str:
    lat, lng = rec["identity"].get("lat"), rec["identity"].get("lng")
    if lat is not None and lng is not None:
        for key, c in cities.items():
            a = c.get("area")
            if a and a[0] <= float(lat) <= a[2] and a[1] <= float(lng) <= a[3]:
                return key
    return city


def _intel_subset(intel: dict) -> dict:
    """What trip.Catalog reads from an intel record, without evidence ids or quotes."""
    keep = ("n", "status", "needs_review", "top_value", "by_context", "distribution")
    return {"place_fid": intel["place_fid"], "place_name": intel["place_name"], "identity": intel.get("identity") or {},
            "estimates": intel.get("estimates") or {}, "operation": {"hours": (intel.get("operation") or {}).get("hours")},
            "features": {fid: {k: s[k] for k in keep if k in s} for fid, s in (intel.get("features") or {}).items()}}


def _videos(root: Path) -> dict[str, str]:
    """TikTok video id -> place id, relevance yes (the same rule trip.Catalog.load used)."""
    out = {}
    for p in sorted((root / "tiktok" / "place_filter").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        vids = d.get("videos")
        for v in vids if isinstance(vids, list) else []:  # some files store a count
            if (v.get("llm") or {}).get("relevance") == "yes":
                out[str(v["video_id"])] = d["fid"]
    return out


def compile_snapshot(city: str, root: Path | None = None) -> dict:
    root = root or data_dir()
    doc = json.loads((root / "serving" / "places.json").read_text(encoding="utf-8"))
    recs = [r for r in doc["records"] if r["status"] in SERVED]  # never NEEDS_REVIEW / DISABLED, stays included
    served = {r["id"] for r in recs}
    intel = {}
    for p in sorted((root / "intel" / "places").glob("*.json")):
        i = json.loads(p.read_text(encoding="utf-8"))
        if i["place_fid"] in served:
            intel[i["place_fid"]] = _intel_subset(i)
    videos = _videos(root)
    cities = yaml.safe_load((ROOT / "config" / "cities.yaml").read_text(encoding="utf-8"))
    by_region: dict[str, list[dict]] = {}
    for r in recs:
        by_region.setdefault(_region_of(r, cities, city), []).append(r)
    base = root / "snapshot"
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    while (base / version).exists():
        version += "x"
    out = base / version
    regions = {}
    for key, rs in sorted(by_region.items()):
        ids = {r["id"] for r in rs}
        t = tables(rs, [intel[i] for i in sorted(ids) if i in intel],
                   {v: p for v, p in videos.items() if p in ids})
        db = lancedb.connect(str(out / key))
        for name, table in t.items():
            db.create_table(name, table, mode="overwrite")
        regions[key] = {"places": len(rs)}
    from ..ontology import load as load_ontology
    manifest = {"version": version, "built_at": now(), "serving_built_at": doc.get("built_at"),
                "ontology_version": load_ontology().version, "regions": regions}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp = base / "current.tmp"
    tmp.write_text(version, encoding="utf-8")
    os.replace(tmp, base / "current")
    keep = config()["snapshot_keep_versions"]
    olds = sorted(p for p in base.iterdir() if p.is_dir())[:-keep]
    for p in olds:
        if p.name != version:
            shutil.rmtree(p)
    print(f"snapshot {version}: {json.dumps(regions, ensure_ascii=False)}")
    return manifest
```

Kiểm `ROOT`, `data_dir`, `now` có trong `src/corpus/crawl/common/files.py` (đã thấy `data_dir`, `now`, và `ROOT` dùng ở dòng 78). `SERVED` (từ `serving/record.py`) là bộ trạng thái được phục vụ: chỉ những record đó vào snapshot.

- [ ] **Step 5: Viết `src/corpus/snapshot/read.py`**

```python
"""Online read side of the snapshot: one Region per city, loaded once, read-only."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import lancedb
import numpy as np
import orjson
import polars as pl
import pyarrow as pa

from ..crawl.common.files import data_dir
from ..serving.record import config
from .tables import tables

FIRM = ("VERIFIED", "OUTDATED")
HINT = "run python -m corpus snapshot"


@dataclass
class FeatureColumn:
    """One served feature for every place of a region, in Region.ids order."""
    value: list
    status: list
    n: list
    conf: np.ndarray
    dist: list  # tuple of distribution keys, or None
    exists: np.ndarray = field(init=False)
    firm: np.ndarray = field(init=False)
    uncertain: np.ndarray = field(init=False)

    def __post_init__(self):
        self.exists = np.array([v is not None for v in self.status], dtype=bool)
        self.firm = np.array([s in FIRM for s in self.status], dtype=bool)
        self.uncertain = np.array([s == "UNCERTAIN" for s in self.status], dtype=bool)

    def eq(self, v) -> np.ndarray:
        return np.array([x == v for x in self.value], dtype=bool)

    def has(self, v) -> np.ndarray:
        return np.array([d is not None and v in d for d in self.dist], dtype=bool)

    def only(self, v) -> np.ndarray:
        return np.array([d is not None and set(d) <= {v} for d in self.dist], dtype=bool)


class _ById(Mapping):
    def __init__(self, region):
        self._r = region

    def __getitem__(self, pid):
        rec = self._r.record(pid)
        if rec is None:
            raise KeyError(pid)
        return rec

    def __contains__(self, pid):
        return pid in self._r.index

    def __iter__(self):
        return iter(self._r.ids)

    def __len__(self):
        return len(self._r.ids)


class Region:
    def __init__(self, key: str, t: dict[str, pa.Table]):
        self.key = key
        self.places = pl.from_arrow(t["places"])
        self._features = pl.from_arrow(t["features"])
        self._ctx = pl.from_arrow(t["feature_ctx"])
        self._verdicts = pl.from_arrow(t["fit_verdicts"])
        self._json = t["records"].column("json").to_pylist() if t["records"].num_rows else []
        self._intel = t["intel"].column("json").to_pylist() if t["intel"].num_rows else []
        self.videos = dict(zip(t["videos"].column("video_id").to_pylist(), t["videos"].column("place_id").to_pylist()))
        self.ids = self.places["id"].to_list()
        self.index = {pid: i for i, pid in enumerate(self.ids)}
        self.stay = frozenset(self.places.filter(pl.col("is_stay"))["id"].to_list())
        self.sigs = {pid: frozenset(tuple(s.split("=", 1)) for s in sig)
                     for pid, sig in zip(self.ids, self.places["signature"].to_list())}
        self.by_id = _ById(self)
        self._parsed: dict[str, dict] = {}
        self._all: list[dict] | None = None
        self._cols: dict = {}

    @classmethod
    def from_records(cls, records, intel=None, videos=None, key: str = "test") -> "Region":
        return cls(key, tables(list(records), intel, videos))

    def column(self, name: str) -> list:
        if ("p", name) not in self._cols:
            self._cols[("p", name)] = self.places[name].to_list()
        return self._cols[("p", name)]

    @property
    def light(self) -> list[dict]:
        """Per place: what code needs of a record's kind without parsing it (diversify.pick, groups.mmr)."""
        if ("light",) not in self._cols:
            self._cols[("light",)] = [
                {"id": pid, "identity": {"category_group": g}, "usable_as": u, "near_duplicate_group": d}
                for pid, g, u, d in zip(self.ids, self.column("category_group"), self.column("usable_as"),
                                        self.column("near_duplicate_group"))]
        return self._cols[("light",)]

    def record(self, pid: str) -> dict | None:
        i = self.index.get(pid)
        if i is None:
            return None
        if pid not in self._parsed:
            self._parsed[pid] = orjson.loads(self._json[i])
        return self._parsed[pid]

    def records(self) -> list[dict]:
        if self._all is None:
            self._all = [self.record(pid) for pid in self.ids]
        return self._all

    def intel(self) -> list[dict]:
        return [orjson.loads(j) for j in self._intel]

    def feature(self, fid: str) -> FeatureColumn:
        if ("f", fid) not in self._cols:
            rows = {r["place_id"]: r for r in self._features.filter(pl.col("fid") == fid).iter_rows(named=True)}
            get = [rows.get(pid) for pid in self.ids]
            self._cols[("f", fid)] = FeatureColumn(
                value=[r and r["value"] for r in get], status=[r and r["status"] for r in get],
                n=[r and r["n"] for r in get],
                conf=np.array([(r["conf"] or 0.0) if r else 0.0 for r in get], dtype=np.float64),
                dist=[tuple(r["dist_values"]) if r else None for r in get])
        return self._cols[("f", fid)]

    def ctx_top(self, fid: str, ctx_key: str) -> list:
        if ("c", fid, ctx_key) not in self._cols:
            rows = dict(self._ctx.filter((pl.col("fid") == fid) & (pl.col("ctx_key") == ctx_key))
                        .select("place_id", "top").iter_rows())
            self._cols[("c", fid, ctx_key)] = [rows.get(pid) for pid in self.ids]
        return self._cols[("c", fid, ctx_key)]

    def verdict(self, who: str) -> tuple[list, list]:
        if ("v", who) not in self._cols:
            rows = {r["place_id"]: r for r in self._verdicts.filter(pl.col("who") == who).iter_rows(named=True)}
            self._cols[("v", who)] = ([rows[p]["value"] if p in rows else None for p in self.ids],
                                      [rows[p]["status"] if p in rows else None for p in self.ids])
        return self._cols[("v", who)]


class Snapshot:
    def __init__(self, root: Path, version: str):
        self.root, self.version = root, version
        self._regions: dict[str, Region] = {}

    @classmethod
    def open(cls, root: Path | None = None) -> "Snapshot":
        base = root or data_dir() / "snapshot"
        cur = base / "current"
        if not cur.exists():
            raise FileNotFoundError(f"no {cur}: {HINT}")
        version = cur.read_text(encoding="utf-8").strip()
        if not (base / version).is_dir():
            raise FileNotFoundError(f"{cur} names {version}, which is missing: {HINT}")
        return cls(base, version)

    def region(self, key: str | None = None) -> Region:
        key = key or config()["default_region"]
        if key not in self._regions:
            path = self.root / self.version / key
            if not path.is_dir():
                raise FileNotFoundError(f"snapshot {self.version} has no region {key!r}: {HINT} --city {key}")
            db = lancedb.connect(str(path))
            names = ("places", "features", "feature_ctx", "fit_verdicts", "records", "intel", "videos")
            self._regions[key] = Region(key, {n: db.open_table(n).to_arrow() for n in names})
        return self._regions[key]
```

Đường đọc cache theo process (`Snapshot.open()` nhiều lần không được nạp lại vùng). Thêm vào cuối `read.py`:

```python
_OPEN: dict[tuple[str, str], Snapshot] = {}


def shared(root: Path | None = None) -> Snapshot:
    """One Snapshot per process and version: Decision, Planning and Trip in one server share the regions."""
    s = Snapshot.open(root)
    return _OPEN.setdefault((str(s.root), s.version), s)
```

- [ ] **Step 6: `__init__.py`, `serving.load`, `serving.run`, CLI**

`src/corpus/snapshot/__init__.py`:

```python
from .compile import compile_snapshot
from .read import FeatureColumn, Region, Snapshot, shared
from .tables import tables

__all__ = ["FeatureColumn", "Region", "Snapshot", "compile_snapshot", "shared", "tables"]
```

Trong `src/corpus/serving/run.py`:
- Cuối `run()`, sau `write_json(...)` và `print(...)`, thêm dòng dưới. Import trong hàm, để tránh vòng import serving ↔ snapshot.

```python
    from ..snapshot import compile_snapshot
    compile_snapshot(city)
```

- Thay `load()` bằng:

```python
def load(region: str | None = None) -> list[dict]:
    """The records online serves (data/snapshot/current); never NEEDS_REVIEW / DISABLED."""
    from ..snapshot import shared
    return [r for r in shared().region(region).records() if r["status"] in SERVED]
```

Trong `src/corpus/__main__.py`: thêm subparser `snapshot` (`--city`, mặc định `dalat`, help `"data/serving/places.json -> data/snapshot/<version>/ (what online reads)"`), nhánh dispatch `elif args.cmd == "snapshot": compile_snapshot(args.city)`, và cập nhật docstring dòng 1 (thêm `| snapshot`).

- [ ] **Step 7: Chạy test, thấy pass**

Run: `.venv/bin/python -m pytest -q tests/snapshot tests/serving`
Expected: PASS. `tests/serving/test_serving.py` gọi `run()` trong `tmp_path`: nay `run()` compile thêm snapshot vào `tmp_path/snapshot`, vẫn phải pass. Nếu test đó không đặt `DATA_DIR` mà patch `data_dir` theo cách khác, thì `compile_snapshot` phải dùng cùng `data_dir()` (đã dùng). Nếu vẫn fail, đọc test để biết nó cô lập thư mục thế nào; không sửa test.

- [ ] **Step 8: Compile trên dữ liệu thật và đo thời gian nạp**

Run:
```bash
.venv/bin/python -m corpus snapshot --city dalat
.venv/bin/python -c "
import sys, time; sys.path.insert(0, 'src')
t = time.perf_counter()
from corpus.snapshot import Snapshot
r = Snapshot.open().region()
print('region load s', round(time.perf_counter() - t, 3), len(r.ids))
t = time.perf_counter(); r.records(); print('records() s', round(time.perf_counter() - t, 3))
"
```

Expected: in số nơi bằng số record trong `places.json` (1.696 lúc viết plan). `region load` ≤ 1 s. Ghi một dòng vào spec §9 (`Task = 4`, cột "Nạp vùng"; ghi chú thêm `records()` s).

- [ ] **Step 9: Chạy các bộ test có dùng `serving.load()`**

Run: `.venv/bin/python -m pytest -q tests/planning tests/harness tests/companion tests/notify tests/decision`
Expected: giống trước task. Test nào trước đây đọc `places.json` thật nay đọc snapshot thật (vừa compile ở Step 8).

- [ ] **Step 10: Tự review**

Run: `git diff -- src/corpus/serving/run.py src/corpus/__main__.py config/serving.yaml pyproject.toml` và `git status --short src/corpus/snapshot tests/snapshot`

---

### Task 5: Trip `Catalog` đọc snapshot

**Files:**
- Modify: `src/trip/infrastructure/catalog.py` (`from_records(..., evidence=None)`, thêm `from_snapshot`), `src/trip/api/tools.py:95`, `src/trip/__main__.py:29`, `src/bench/generate.py:65`
- Test: `tests/trip/test_catalog_snapshot.py`

**Interfaces:**
- Consumes: `corpus.snapshot.Region` (`intel()`, `videos`, `by_id`), `corpus.snapshot.shared`
- Produces: `trip.Catalog.from_snapshot(region, n_min: int) -> Catalog`; `Catalog.from_records(records, n_min, videos=None, evidence: Mapping[str, dict] | None = None)`

Hành vi đổi có chủ đích (spec §6.3, **user đã duyệt 2026-10-13**): catalog chỉ còn nơi được phục vụ, không có `DISABLED` / `NEEDS_REVIEW`; `evidence_record` là record đã phục vụ. Chỗ ở có trong catalog như mọi nơi được phục vụ, vì Trip cần tìm được tên chỗ ở user gõ.

- [ ] **Step 1: Viết test fail**

```python
# tests/trip/test_catalog_snapshot.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "decision"))
from fixtures import feat, srec  # noqa: E402

from corpus.snapshot import Region  # noqa: E402
from trip import Catalog  # noqa: E402


def intel_of(r, n=3):
    return {"place_fid": r["id"], "place_name": r["identity"]["name"], "identity": {"category": "Quán cà phê"},
            "estimates": {"category_group": "cafe", "usable_as_default": ["experience"]},
            "operation": {"hours": None},
            "features": {"scenic_view": {"n": n, "status": "signal", "top_value": "present",
                                         "by_context": {"time_of_day": {"morning": 2}}, "distribution": {"present": n}}}}


def test_from_snapshot_matches_from_records_except_evidence():
    recs = [srec("A", features={"scenic_view": feat("present")}), srec("B")]
    intel = [intel_of(r) for r in recs]
    region = Region.from_records(recs, intel, {"v1": "A"})
    snap = Catalog.from_snapshot(region, n_min=1)
    old = Catalog.from_records(intel, 1, {"v1": "A"})
    assert [p.id for p in snap.places] == [p.id for p in old.places]
    for a, b in zip(snap.places, old.places):
        assert (a.name, a.category, a.lat, a.lng, a.hours, a.known, a.weight) == (b.name, b.category, b.lat, b.lng, b.hours, b.known, b.weight)
        assert a.evidence_record == region.by_id[a.id]
    assert snap.video_place == {"v1": "A"}
```

Kiểm tên field thật của `Candidate` trong `catalog.py` (`id`, `name`, `category`, `lat`, `lng`, `hours`, `known`, `weight`, `category_group`, `usable_as`, `evidence_record`) và sửa test cho đúng nếu khác.

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/trip/test_catalog_snapshot.py`
Expected: FAIL (`AttributeError: from_snapshot`).

- [ ] **Step 3: Code**

Trong `Catalog.from_records`, thêm tham số `evidence: Mapping[str, dict] | None = None`. Ngay đầu thân vòng `for r in records`, sau khi tính `known` / `total` / `group`, chọn evidence:

```python
            if evidence is not None:
                ev = evidence.get(r["place_fid"])
            else:
                ev = None
```

Đoạn dựng `evidence = {...}` và vòng `for fid, sig in ...` (gọi `build(r)`) chỉ chạy khi `ev is None`. Nếu `ev is not None` thì dùng `evidence_record=ev`. Đổi tên biến cục bộ `evidence` cũ thành `ev_built` để khỏi trùng tham số. Giữ nguyên hành vi cũ khi `evidence=None`.

Thêm classmethod:

```python
    @classmethod
    def from_snapshot(cls, region, n_min: int) -> Catalog:
        """The served places of one corpus snapshot region (python -m corpus snapshot): no intel file reads, no
        record rebuilds."""
        return cls.from_records(region.intel(), n_min, region.videos, evidence=region.by_id)
```

Tại `src/trip/api/tools.py:95`, `src/trip/__main__.py:29`, `src/bench/generate.py:65`: thay `Catalog.load(data, n_min)` bằng

```python
from corpus.snapshot import shared
catalog = Catalog.from_snapshot(shared().region(), cfg.n_min)
```

(`bench/generate.py` dùng `n_min=1` như cũ.) Giữ `Catalog.load`: `tests/trip/test_catalog.py` vẫn dùng nó.

- [ ] **Step 4: Chạy test**

Run: `.venv/bin/python -m pytest -q tests/trip`
Expected: PASS. Test trip nào dựa vào nơi DISABLED có trong catalog thật sẽ fail: **ghi lại tên, báo user, không sửa test.** `tests/trip/test_eval_conversations.py` đã fail sẵn (KeyError `conversations`, handoff §0); không tính.

- [ ] **Step 5: Đo**

Run:
```bash
.venv/bin/python -c "
import sys, time; sys.path.insert(0, 'src')
from corpus.snapshot import shared
from trip import Catalog
t = time.perf_counter(); c = Catalog.from_snapshot(shared().region(), 3); print('catalog s', round(time.perf_counter() - t, 3), len(c.places))
"
```

Expected: ≤ 1,5 s (gồm nạp vùng). Ghi spec §9 (`Task = 5`, cột "Catalog").

- [ ] **Step 6: Tự review**

Run: `git diff -- src/trip/infrastructure/catalog.py src/trip/api/tools.py src/trip/__main__.py src/bench/generate.py`

---

### Task 6: `scope_allows` + screen theo bảng

**Files:**
- Modify: `src/requirements/checks.py`, `src/requirements/__init__.py`
- Create: `src/decision/frame.py` (phần screen)
- Test: `tests/decision/test_frame.py`

**Interfaces:**
- Consumes: `Region.feature(fid) -> FeatureColumn`, `Region.places`, `Region.ids`, `Region.index`, `Region.record`
- Produces:
  - `requirements.scope_allows(requirement, selected: Activity | None) -> bool`
  - `decision.frame.roles(region, overrides: dict[str, str], keep: set[str]) -> tuple[list[str | None], list[str | None]]`: role cuối và activity của từng nơi, theo thứ tự `region.ids`. Nơi `keep` không có role thì role `"experience"`.
  - `decision.frame.Screen` (dataclass):
    - `status: list[str]` (`main` | `unverified` | `excluded`)
    - `fails: dict[str, np.ndarray[int]]`: key là reason (`closed_all_trip_days`, `hard:<fid>`), giá trị là **số check fail** của từng nơi. Hai filter cùng feature thì đếm 2, như `Counter` trong `pipeline.run`.
  - `decision.frame.screen_table(region, si, days, relaxed: set[tuple[str, str]], role, act) -> Screen`

- [ ] **Step 1: Viết test fail**

```python
# tests/decision/test_frame.py
import pytest

from fixtures import feat, hard, si, srec
from gen import records, sessions

from corpus.snapshot import Region
from decision.frame import roles, screen_table
from decision.model import Cand
from decision.screen import screen
from decision.settings import default
from decision.trip_days import trip_days
from requirements import applicable, scope_allows

CFG = default()


def reference_screen(s, recs):
    si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
    days = trip_days(si_.context, CFG)
    relaxed = {tuple(x) for x in s.state.relaxed}
    region = Region.from_records(recs)
    keep = set(s.state.selected)
    role, act = roles(region, si_.activities, keep)
    got = screen_table(region, si_, days, relaxed, role, act)
    for i, r in enumerate(recs):
        if role[i] is None:
            continue
        c = Cand(r, role[i], keep=r["id"] in keep)
        screen(c, si_, days, relaxed)
        fails = {x["reason"] for x in c.checks if x["result"] == "fail"}
        assert got.status[i] == c.status, (s.id, r["id"])
        assert {k for k, v in got.fails.items() if v[i] > 0} == fails, (s.id, r["id"])


@pytest.mark.parametrize("seed", range(10))
def test_screen_table_matches_screen(seed):
    recs = records(seed)
    for s in sessions(seed, recs, 20):
        reference_screen(s, recs)


def test_scope_allows_is_the_scope_part_of_applicable():
    r = srec("A", group="restaurant", usable=("meal",))
    for fid in ("vegetarian_options", "drink_quality", "steep_or_stairs", "scenic_view", "fit.kids"):
        for scope in (None, "eating", "drinking", "all"):
            req = {"feature": fid, "scope": scope}
            assert applicable(r, req) == scope_allows(req, "eating")


def test_screen_special_and_fit_filters():
    recs = [srec("C", group="cafe"), srec("R", group="restaurant", usable=("meal",)),
            srec("W", group="bar", features={"alcohol_required": feat("yes")}),
            srec("K", details={"fit": {"kids": fit_entry("bad")}})]
    for h in (hard("venue_category", "cafe", op="eq"), hard("activity", "alcohol_consumption"),
              hard("wine_tasting_available", "yes", op="eq"), hard("fit.kids", "bad")):
        reference_screen(Session(id="0" * 12, search_input=si(hard_filters=[h]), state=State()), recs)


def test_duplicate_filters_count_each_failed_check():
    recs = [srec("S", features={"steep_or_stairs": feat("present")})]
    s = Session(id="0" * 12, search_input=si(hard_filters=[hard("steep_or_stairs", "present"),
                                                           hard("steep_or_stairs", "present", policy="flag")]),
                state=State())
    region = Region.from_records(recs)
    role, act = roles(region, {}, set())
    got = screen_table(region, s.search_input, trip_days(s.search_input.context, CFG), set(), role, act)
    assert int(got.fails["hard:steep_or_stairs"][0]) == 2
```

Import ở đầu file: thêm `from fixtures import fit_entry` và `from decision.session import Session, State`. Nếu `hard("activity", ...)` cần `op="eq"` theo schema `SearchInput`, đổi cho hợp lệ. Nếu schema không cho hai filter trùng feature thì bỏ test thứ hai và ghi lý do vào spec §9 phần ghi chú.

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/decision/test_frame.py`
Expected: FAIL (`ImportError: scope_allows`).

- [ ] **Step 3: Tách `scope_allows` trong `src/requirements/checks.py`**

```python
def scope_allows(requirement, selected: Activity | None) -> bool:
    """The scope part of applicable(): does a requirement apply to a place whose activity is `selected`?"""
    fid = _get(requirement, "feature")
    canonical = scope_for(fid)
    scope = _get(requirement, "scope") or canonical
    f = ontology().features.get(fid)
    if canonical != "all":
        scope = canonical
    elif fid in {"venue_category", "activity"} or (f and f.group in {"effort", "suitability"}):
        scope = "all"                  # raw public inputs cannot narrow a protected scope
    # Unknown activity cannot be used as a reason to bypass a hard requirement.
    return scope == "all" or selected is None or ACTIVITY_SCOPE[selected] == scope


def applicable(rec: dict, requirement, activity: Activity | None = None, role: str | None = None) -> bool:
    selected = activity_for(rec, activity, role)
    if _get(requirement, "feature") == "wine_tasting_available":
        if activity is not None:
            return selected in {"wine_tasting", "tasting", "alcohol_consumption", "drinking"}
        offered = feature(rec, "wine_tasting_available")
        return offered is not None or selected in {"wine_tasting", "tasting", "alcohol_consumption", "drinking"} or selected is None
    return scope_allows(requirement, selected)
```

Thêm `"scope_allows"` vào import và `__all__` của `src/requirements/__init__.py`.

- [ ] **Step 4: Viết phần screen của `src/decision/frame.py`**

```python
"""③-⑤ for every place of a corpus snapshot region at once (docs/PLACE_DECISION.md §6-8). The per-place functions
(screen.py, fit.py, rank.py) stay the definition and build the cards; this module must give the same status, fit and
score for every place (tests/decision/test_frame.py, tests/decision/test_equivalence.py). Sums run in the reference
order, vectorised over places, float64; rounding is Python's round()."""

from dataclasses import dataclass

import numpy as np

from corpus import load_ontology
from requirements import activity_for, hard_result, scope_allows

from .model import role_of
from .trip_days import DAYS

SPECIAL = {"venue_category", "activity", "wine_tasting_available"}  # hard_result has its own rules for these
PROTECTED = {"effort", "suitability"}                                # hard_result: no uncertain_value pass


def roles(region, overrides: dict[str, str], keep: set[str]) -> tuple[list, list]:
    """Final role and activity of every place as pipeline.run sets them. An `activities` override and a kept place
    without a role are recomputed with the per-place functions."""
    role = region.places["role"].to_list()
    act = region.places["activity"].to_list()
    for pid in set(overrides) | keep:
        i = region.index.get(pid)
        if i is None:
            continue
        rec = region.record(pid)
        r = role_of(rec)
        a = activity_for(rec, overrides.get(pid), r)
        if r and a == "eating":
            r = "meal"
        elif r and a:
            r = "experience"
        if r is None and pid in keep:
            r = "experience"
        role[i] = r
        act[i] = activity_for(rec, overrides.get(pid), r)
    return role, act


@dataclass
class Screen:
    status: list
    fails: dict


def _applies(h, act: list) -> np.ndarray:
    allowed = {a: scope_allows(h, a) for a in set(act)}
    return np.array([allowed[a] for a in act], dtype=bool)


def _hard(region, h, act: list) -> np.ndarray:
    """pass | fail | unknown | not_applicable of one generic hard filter for every place (requirements.hard_result)."""
    col = region.feature(h.feature)
    eqv = col.eq(h.value)
    if h.op == "eq":
        out = np.where(~col.exists | ~col.firm, "unknown",
                       np.where(~eqv, "fail", np.where(col.only(h.value), "pass", "unknown")))
    else:
        has = col.has(h.value)
        out = np.where(~col.exists, "unknown",
                       np.where(eqv, np.where(col.firm, "fail", "unknown"),
                                np.where(has | ~col.firm, "unknown", "pass")))
        f = load_ontology().features.get(h.feature)
        if f is not None and f.group not in PROTECTED:
            up = (out == "unknown") & col.exists & col.uncertain & ~eqv & ~has
            out = np.where(up, "pass", out)
    return np.where(_applies(h, act), out, "not_applicable")


def _hard_slow(region, h, act: list, role: list, overrides: dict) -> np.ndarray:
    """Special features: the per-place rule on every place (rare filters; measured in bench latency)."""
    return np.array([hard_result(region.record(pid), h, overrides.get(pid), role[i])[0] if role[i] else "not_applicable"
                     for i, pid in enumerate(region.ids)])


def screen_table(region, si, days, relaxed: set, role: list, act: list) -> Screen:
    n = len(region.ids)
    fails: dict[str, np.ndarray] = {}
    unknown = np.zeros(n, dtype=bool)
    if not any(d.weekday is None for d in days):  # screen.closed_all_days
        mask = 0
        for d in days:
            mask |= 1 << DAYS.index(d.weekday)
        p = region.places
        closed = ((p["hours_status"] == "VERIFIED").fill_null(False).to_numpy()
                  & p["has_hours_value"].to_numpy()
                  & ((p["open_mask"].to_numpy() & mask) == 0))
        fails["closed_all_trip_days"] = closed.astype(np.int32)
    for h in si.hard_filters:
        slow = h.feature in SPECIAL
        res = _hard_slow(region, h, act, role, si.activities) if slow else _hard(region, h, act)
        skip = np.array([(pid, h.feature) in relaxed for pid in region.ids], dtype=bool) if relaxed else np.zeros(n, bool)
        fail = (res == "fail") & ~skip
        key = f"hard:{h.feature}"
        fails[key] = fails.get(key, np.zeros(n, np.int32)) + fail.astype(np.int32)
        unknown |= (res == "unknown") & ~skip
    any_fail = np.zeros(n, dtype=bool)
    for v in fails.values():
        any_fail |= v > 0
    status = np.where(any_fail, "excluded", np.where(unknown, "unverified", "main")).tolist()
    return Screen(status, fails)
```

Lưu ý khi viết:
- `_applies` cho hard filter dùng `scope_allows(h, a)`. `h` là object Pydantic: `_get` trong checks đọc được cả Mapping lẫn object.
- Hard filter `activity = alcohol_consumption` thuộc `activity`, nên đã nằm trong `SPECIAL`. Mọi feature khác (gồm `fit.*`) đi `_hard`.
- Với nơi có override hoặc keep, giá trị trong `act` đã đúng (do `roles()`). Đường generic vẫn đúng vì `scope_allows` chỉ cần activity.
- `np.where(..., "unknown", ...)` với chuỗi cho mảng kiểu `<U…`. So sánh `res == "fail"` vẫn đúng. Nếu numpy cắt chuỗi (`"not_applicable"` dài hơn chuỗi đầu tiên), khởi tạo bằng `np.full(n, "not_applicable", dtype="<U14")` rồi gán theo mask.
- `status` cho nơi `role is None` (không phải ứng viên) không được dùng; để nguyên.

- [ ] **Step 5: Chạy test, thấy pass**

Run: `.venv/bin/python -m pytest -q tests/decision/test_frame.py tests/decision/test_requirement_activities.py tests/decision/test_screen.py`
Expected: PASS. Nếu một seed lệch, in `(s.id, r["id"])`, so `c.checks` với `_hard` cho filter đó, rồi sửa `frame.py`. Không sửa reference.

- [ ] **Step 6: Chạy bộ requirements và planning** (vì `applicable` đổi cấu trúc)

Run: `.venv/bin/python -m pytest -q tests/planning tests/decision`
Expected: giống trước task.

- [ ] **Step 7: Tự review**

Run: `git diff -- src/requirements/checks.py src/requirements/__init__.py` và `git status --short src/decision/frame.py tests/decision/test_frame.py`

---

### Task 7: fit + score theo bảng

**Files:**
- Modify: `src/decision/frame.py` (thêm fit, score), `src/decision/rank.py` (`score(..., voices=None)`)
- Test: `tests/decision/test_frame.py` (thêm test)

**Interfaces:**
- Consumes: `Screen`, `roles`, `Region.verdict`, `Region.ctx_top`, `Region.feature` (Task 4, 6)
- Produces:
  - `decision.frame.fit_table(region, si, days, ctrs, anchor_areas: set[str], profile, cfg) -> list[float]` (đã `round(…, 4)`, cho mọi nơi)
  - `decision.frame.score_table(region, si, profile, cfg, fit: list[float], live: np.ndarray[bool], role, act, extra_voices: int = 0, overrides: dict | None = None) -> tuple[list[float], list[int]]` (score cho mọi nơi; voices đã sort của tập live, gồm `extra_voices` số 0 cho nơi giữ mà không có record)
  - `decision.rank.score(cands, si, profile, cfg, voices: list[int] | None = None)`

- [ ] **Step 1: Viết test fail** (thêm vào `tests/decision/test_frame.py`)

```python
from decision.fit import centers, fit
from decision.frame import fit_table, score_table
from decision.rank import score


def reference_numbers(s, recs):
    si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
    days = trip_days(si_.context, CFG)
    relaxed = {tuple(x) for x in s.state.relaxed}
    region = Region.from_records(recs)
    keep = set(s.state.selected)
    role, act = roles(region, si_.activities, keep)
    scr = screen_table(region, si_, days, relaxed, role, act)
    by_id = {r["id"]: r for r in recs}
    ctrs = centers(si_, by_id, CFG)
    anchors = [a.place_id for a in si_.anchors if a.place_id in by_id]
    anchor_areas = {a for pid in anchors if (a := by_id[pid]["identity"].get("area"))}
    cands = []
    for i, r in enumerate(recs):
        if role[i] is None:
            continue
        c = Cand(r, role[i], keep=r["id"] in keep)
        screen(c, si_, days, relaxed)
        cands.append(c)
    live = [c for c in cands if c.status != "excluded" or c.keep]
    for c in live:
        fit(c, si_, days, ctrs, anchor_areas, s.state.profile, CFG)
    score(live, si_, s.state.profile, CFG)
    live_ids = {c.id for c in live}
    live_mask = np.array([pid in live_ids for pid in region.ids])
    got_fit = fit_table(region, si_, days, ctrs, anchor_areas, s.state.profile, CFG)
    got_score, _ = score_table(region, si_, s.state.profile, CFG, got_fit, live_mask, role, act,
                               overrides=si_.activities)
    for c in live:
        i = region.index[c.id]
        assert got_fit[i] == c.fit, (s.id, c.id, "fit")
        assert got_score[i] == c.score, (s.id, c.id, "score")


@pytest.mark.parametrize("seed", range(10))
def test_fit_and_score_tables_match(seed):
    recs = records(seed)
    for s in sessions(seed, recs, 20):
        reference_numbers(s, recs)


def test_score_with_given_voices_equals_score_over_the_list():
    recs = records(2)
    s = sessions(2, recs, 1)[0]
    cands = [Cand(r, "experience") for r in recs[:10]]
    for c in cands:
        c.fit = 0.5
    score(cands, s.search_input, s.state.profile, CFG)
    whole = {c.id: c.score for c in cands}
    voices = sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
    for c in cands:
        one = Cand(c.rec, "experience")
        one.fit = 0.5
        score([one], s.search_input, s.state.profile, CFG, voices=voices)
        assert one.score == whole[c.id]
```

Thêm `import numpy as np` ở đầu file test.

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/decision/test_frame.py -k "fit_and_score or given_voices"`
Expected: FAIL (`ImportError: fit_table`).

- [ ] **Step 3: `rank.score(..., voices=None)`**

Trong `src/decision/rank.py`, đổi chữ ký và dòng `voices = sorted(...)`:

```python
def score(cands: list[Cand], si, profile, cfg, voices: list[int] | None = None) -> None:
    """voices: the sorted voices of every live candidate, when scoring a few of them alone (decision.frame)."""
    ws = wants(si, profile)
    voices = voices if voices is not None else sorted(c.rec["provenance"].get("voices") or 0 for c in cands)
```

Phần còn lại giữ nguyên.

- [ ] **Step 4: Thêm fit + score vào `src/decision/frame.py`**

```python
from .fit import DAYTIME, NEEDS, radius, trip_companions
from .model import FIRM
from .rank import vibe_fit, wants

SOFT_SPECIAL = {"wine_tasting_available"}  # applicable() has its own rule for it


def _round(xs) -> list[float]:
    return [round(float(x), 4) for x in xs]


def fit_table(region, si, days, ctrs, anchor_areas: set, profile, cfg) -> list[float]:
    """decision.fit.fit's number for every place: distance + area + crowd + details, clipped, rounded."""
    p = region.places
    n = len(region.ids)
    lat = p["lat"].to_numpy()
    lng = p["lng"].to_numpy()
    has_pt = ~np.isnan(lat) & ~np.isnan(lng)
    dist = np.zeros(n)
    if has_pt.any():
        d = np.full(n, np.inf)
        la1, lo1 = np.radians(lat), np.radians(lng)
        for _, (qlat, qlng) in ctrs:  # decision.geo.km, same operation order
            la2, lo2 = np.radians(qlat), np.radians(qlng)
            h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
            d = np.minimum(d, 2 * 6371 * np.arcsin(np.sqrt(h)))
        r = radius(si, profile, cfg)
        dist = np.where(has_pt, 1 - np.minimum(1.0, d / r), 0.0)
    area = np.array([cfg.area_bonus if a in anchor_areas else 0.0 for a in p["area"].to_list()])
    crowd = np.zeros(n)
    if (profile.crowd_tolerance or si.pace.crowd_tolerance) == "avoid":
        known = sorted({d.day_type for d in days if d.day_type})
        if known:
            busy = np.zeros(n, dtype=bool)
            for dt in known:
                for b in DAYTIME:
                    busy |= (p[f"crowd_{dt}_{b}"].fill_null(0).to_numpy() >= cfg.crowd_busy_pct)
            crowd = np.where(p["has_crowd"].to_numpy() & busy, -cfg.crowd_penalty, 0.0)
    details = np.zeros(n)
    cf = cfg.details_fit
    for who in trip_companions(si, cfg):
        val, st = region.verdict(who)
        firm = np.array([s in FIRM for s in st], dtype=bool)
        good = np.array([v == "good" for v in val], dtype=bool) & firm
        bad = np.array([v == "bad" for v in val], dtype=bool) & firm
        details = details + np.where(good, cf["good_bonus"], 0.0)
        details = details - np.where(bad, cf["bad_penalty"], 0.0)
        for fid, want in NEEDS.get(who, ()):
            col = region.feature(fid)
            details = details + np.where(col.exists & col.firm & col.eq(want), cf["feature_bonus"], 0.0)
    total = np.maximum(0.0, np.minimum(1.0, dist + area + crowd + details))
    return _round(total)
```

Ba chỗ phải kiểm đúng với reference:
- Reference cộng `details` theo thứ tự: verdict good / bad trước, rồi từng NEEDS. `total += bonus` và `total -= penalty`. Bản vector dùng `+ np.where(…, x, 0.0)` / `- np.where(…, x, 0.0)`. Cộng hoặc trừ 0.0 không đổi giá trị.
- Reference tính `dist + area + crowd + details` từ trái sang phải; bản vector giữ đúng thứ tự đó.
- `p["lat"].to_numpy()` với giá trị null cho `nan`. Nếu Polars trả kiểu object, ép bằng `p["lat"].cast(pl.Float64).to_numpy()`.

Cuối cùng là hàm `score_table`:

```python
def score_table(region, si, profile, cfg, fit: list, live: np.ndarray, role: list, act: list,
                extra_voices: int = 0, overrides: dict | None = None) -> tuple[list[float], list[int]]:
    """decision.rank.score's number for every place, `pop` ranked among the live places (+ extra_voices zeros for
    kept places without a record). overrides: the session's activities (only the slow path needs them)."""
    p = region.places
    n = len(region.ids)
    voices_all = p["voices"].to_numpy().astype(np.int64)
    live_voices = sorted(voices_all[live].tolist() + [0] * extra_voices)
    top = max(1, len(live_voices) - 1)
    pop = np.minimum(1.0, np.searchsorted(np.array(live_voices), voices_all, side="left") / top)
    ws = wants(si, profile)
    pref, unc = _preference(region, ws, role, act, n, overrides or {})
    visited = set(si.novelty.visited) | set(profile.visited)
    nov_v = {"new": -1.0, "familiar": 0.3}.get(si.novelty.level, 0.0)
    nov = np.array([nov_v if pid in visited else 0.0 for pid in region.ids])
    exp_kind = si.context.experience
    exp = pop if exp_kind == "first" else (1 - pop if exp_kind == "returning" else np.zeros(n))
    mid = p["price_mid_vnd"].fill_null(0.0).to_numpy()
    norm = np.where(p["price_mid_vnd"].is_null().to_numpy(), 0.0, np.minimum(1.0, mid / cfg.price_ref_vnd))
    vibe = vibe_fit(si)
    parts = {"ctx": np.array(fit, dtype=np.float64),
             "pref": np.array(_round(pref)),
             "nov": nov,
             "exp": exp,
             "pop": np.array(_round(pop)),
             "unc": -np.array(_round(unc)),
             "price": -np.array(_round(profile.price_sensitivity * norm)),
             "vibe": np.array(_round([vibe.get(pid, 0.0) for pid in region.ids]))}
    acc = np.zeros(n)
    for k, v in parts.items():  # rank.score: sum(cfg.weights.get(k, 0.0) * v for k, v in parts.items())
        acc = acc + cfg.weights.get(k, 0.0) * v
    return _round(acc), live_voices


def _preference(region, ws, role, act, n, overrides: dict) -> tuple[np.ndarray, np.ndarray]:
    """rank.preference for every place: (fit / total, missing / total), 0 when no want applies."""
    if any(w[0] in SOFT_SPECIAL for w in ws):
        return _preference_slow(region, ws, role, n, overrides)
    total = np.zeros(n)
    fit = np.zeros(n)
    missing = np.zeros(n)
    for fid, val, ctx, w, scope in ws:
        app = _applies({"feature": fid, "scope": scope}, act)
        col = region.feature(fid)
        cur = list(col.value)
        for k, v in reversed(list((ctx or {}).items())):  # first context key with data wins (rank._contextual)
            top = region.ctx_top(fid, f"{k}={v}")
            cur = [t if t is not None else c for t, c in zip(top, cur)]
        hit = np.array([c == val for c in cur], dtype=bool) & col.exists
        total = total + np.where(app, abs(w), 0)
        if w > 0:
            missing = missing + np.where(app & (~col.exists | col.uncertain), w, 0)
        fit = fit + np.where(app & hit, w * col.conf, 0.0)
    safe = np.where(total > 0, total, 1)
    return np.where(total > 0, fit / safe, 0.0), np.where(total > 0, missing / safe, 0.0)
```

Lưu ý khi viết `_preference`:
- **`reversed`**: `_contextual` lấy key **đầu tiên** của `ctx` có dữ liệu. Duyệt ngược rồi ghi đè thì key đầu thắng. Kiểm bằng test có hai key.
- **`exists` và `uncertain`**: `col.exists` = có feature được phục vụ. `missing` cộng khi `(f is None or status == UNCERTAIN) and w > 0`.
- **Kiểu số**: `total` của reference là `sum(abs(w[3]) for w in ws)` với `w` là int, nên `total` là int; `fit / total` là float. Bản vector dùng float64, kết quả như nhau vì giá trị nguyên nhỏ biểu diễn chính xác.
- **`missing / total`**: reference trả `missing / total`. Khi `missing` = 0 (int) thì `0 / total` = 0.0, khớp.
- **Thứ tự `ws`**: bản vector cộng theo thứ tự want (vòng `for`) và vector hóa theo nơi, đúng như reference.
- **`ws` có 4 phần tử** (tuple cũ): reference pad thêm `scope=None`. Nếu `wants()` luôn trả 5 phần tử thì bỏ qua.

Còn `_preference_slow` là đường chậm cho want đặc biệt:

```python
def _preference_slow(region, ws, role, n, overrides: dict):
    """A want rank.preference treats specially (wine_tasting_available): the per-place rule on every place."""
    from .rank import preference
    pref, unc = np.zeros(n), np.zeros(n)
    for i, pid in enumerate(region.ids):
        if role[i] is None:
            continue
        pref[i], unc[i], _ = preference(region.record(pid), ws, overrides.get(pid), role[i])
    return pref, unc
```

- [ ] **Step 5: Chạy test, thấy pass**

Run: `.venv/bin/python -m pytest -q tests/decision/test_frame.py tests/decision/test_rank.py tests/decision/test_fit.py tests/decision/test_details_fit.py`
Expected: PASS.

Nếu `fit` lệch đúng 1 ulp ở vài nơi (do `np.sin` khác `math.sin`), đổi phần khoảng cách sang list comprehension gọi `decision.geo.km` (Python `math`):

```python
d = np.array([min(km((la, lo), q) for _, q in ctrs) if ok else np.inf
              for la, lo, ok in zip(lat.tolist(), lng.tolist(), has_pt.tolist())])
```

Sau đó ghi vào spec §9 phần ghi chú là đã dùng `math`.

- [ ] **Step 6: Tự review**

Run: `git diff -- src/decision/rank.py` và `git status --short src/decision tests/decision`

---

### Task 8: `pipeline.run` trên bảng

**Files:**
- Modify: `src/decision/pipeline.py` (`Data`, `run`, thêm `Row`, `Cands`), `src/decision/frame.py` (thêm `table()`), `src/corpus/serving/groups.py` (`mmr(..., sigs=None)`), `src/decision/diversify.py` (truyền `sigs` cho `mmr`), `src/decision/engine.py:98` (`name_keys`), `src/decision/__main__.py:40-48` (thông báo khi thiếu snapshot, đếm nơi)
- Test: `tests/decision/test_equivalence.py` (thêm test), cả `tests/decision`

**Interfaces:**
- Consumes: `roles`, `screen_table`, `fit_table`, `score_table` (Task 6–7); `Region` (Task 4); `rank.score(voices=)` (Task 7)
- Produces:
  - `decision.Data(records: list[dict] | None = None, region=None)` với `.region`, `.records` (property → `region.records()`), `.by_id` (`region.by_id`), `Data.load(region: str | None = None)`
  - `decision.frame.Table` (dataclass):
    - `role`, `act`, `status`, `fails`, `fit`, `score`
    - `live: np.ndarray[bool]`, `members: np.ndarray[bool]`
    - `voices: list[int]`, `group: list[str]`, `anchor_areas: set[str]`
  - `decision.frame.table(region, si, profile, days, relaxed, ctrs, anchors: list[str], keep: set[str], n_missing: int, cfg, memo: dict | None = None) -> Table`
  - `decision.pipeline.Cands` (Mapping[str, Cand], lazy), `decision.pipeline.Row(id, score, role, dup, rec)`
  - `corpus.serving.mmr(records, scores, k, lam=None, sigs=None)`

- [ ] **Step 1: Viết test fail** (thêm vào `tests/decision/test_equivalence.py`)

```python
from fixtures import si, srec, hard, love
from decision.session import Drop, Session, State


def test_equivalence_activity_override_and_roleless_keep():
    recs = records(4)
    recs.append(srec("RENT", group="rental", usable=()))
    s = Session(id="0" * 12, search_input=si(soft_weights=[love("scenic_view")]),
                state=State(selected=["RENT", recs[0]["id"]], activities={recs[1]["id"]: "eating", recs[2]["id"]: "coffee"}))
    assert_same(s, recs)


def test_equivalence_missing_kept_place():
    recs = records(5)
    s = Session(id="0" * 12, search_input=si(anchors=[{"place_id": "GONE", "priority": "must"}]),
                state=State(selected=["GONE2"]))
    assert_same(s, recs)


def test_data_keeps_the_list_api():
    recs = records(6)
    d = Data(recs)
    assert [r["id"] for r in d.records] == [r["id"] for r in recs]
    assert recs[0]["id"] in d.by_id and "nope" not in d.by_id


@pytest.mark.corpus
def test_equivalence_eval_trips_on_the_real_snapshot():
    snap = pytest.importorskip("corpus.snapshot")
    try:
        region = snap.shared().region()
    except FileNotFoundError:
        pytest.skip("no snapshot")
    from decision import eval_search_input, eval_trips
    from decision.curation import apply
    from corpus.ontology import load
    recs = region.records()
    data = Data(region=region)
    version, trips = eval_trips()
    for trip in trips:
        si_ = eval_search_input(trip, version).model_copy(update={"ontology_version": load().version})
        s = Session(id="0" * 12, search_input=si_, state=State())
        for step in range(4):
            new = run(s, data, CFG)
            old = run_reference(s, recs, CFG)
            assert new.view == old.view, (trip["id"], step)
            ids = new.view["shortlist"]
            if not ids:
                break
            act = [{"type": "select", "place_id": ids[0]}, {"type": "drop", "place_id": ids[-1], "reason": "far"},
                   {"type": "lock", "place_id": ids[0]}, {"type": "select", "place_id": ids[len(ids) // 2]}][step]
            s.state = apply(s.state, act, lambda p: p in new.cands or p in data.by_id, new.alternatives, None, CFG)
```

Thêm `import pytest` ở đầu nếu chưa có. Đọc chữ ký `apply` trong `src/decision/curation.py` (`apply(state, action, known, alternatives, pending, cfg)`, theo cách `engine._apply` gọi) và sửa tham số cho đúng.

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/decision/test_equivalence.py -k "data_keeps"`
Expected: FAIL (`Data` chưa nhận `region=`).

- [ ] **Step 3: `mmr(..., sigs=None)`**

Trong `src/corpus/serving/groups.py`:

```python
def mmr(records: list[dict], scores: dict[str, float], k: int, lam: float | None = None,
        sigs: dict | None = None) -> list[str]:
    """Up to k record ids: high score, but each unlike the ones picked before. sigs: id -> signature, precomputed."""
    lam = lam if lam is not None else config()["mmr_lambda"]
    pool, picked = {r["id"]: r for r in records}, []
    sigs = sigs if sigs is not None else {r["id"]: signature(r) for r in records}
```

Phần còn lại giữ nguyên. Trong `src/decision/diversify.py` `pick(pool, k, cfg, sigs=None)`: truyền `sigs={c.id: sigs[c.id] for c in head} if sigs else None` vào `mmr`.

- [ ] **Step 4: `frame.table()`**

Thêm vào `src/decision/frame.py`:

```python
@dataclass
class Table:
    role: list
    act: list
    status: list
    fails: dict
    fit: list
    score: list
    live: np.ndarray
    members: np.ndarray
    voices: list
    group: list
    anchor_areas: set


def display_groups(region, role: list, cfg) -> list[str]:
    """diversify.display_group for every place (first display group that lists the category group)."""
    of: dict[str, str] = {}
    for k, gs in cfg.display_groups.items():
        for g in gs:
            of.setdefault(g, k)
    return ["meal" if r == "meal" else of.get(g, "sights") for r, g in zip(role, region.column("category_group"))]


def table(region, si, profile, days, relaxed, ctrs, anchors: list, keep: set, n_missing: int, cfg,
          memo: dict | None = None) -> Table:
    role, act = roles(region, si.activities, keep)
    keep_mask = np.array([pid in keep for pid in region.ids], dtype=bool)
    stay = region.places["is_stay"].to_numpy()
    members = np.array([r is not None for r in role], dtype=bool) & ~stay
    scr = screen_table(region, si, days, relaxed, role, act)
    live = members & ((np.array(scr.status) != "excluded") | keep_mask)
    area_of = region.column("area")
    anchor_areas = {a for pid in anchors if pid in region.index and (a := area_of[region.index[pid]])}
    fit = fit_table(region, si, days, ctrs, anchor_areas, profile, cfg)
    fit = [f if l else 0.0 for f, l in zip(fit, live)]
    score, voices = score_table(region, si, profile, cfg, fit, live, role, act, n_missing, si.activities)
    return Table(role, act, scr.status, scr.fails, fit, score, live, members, voices,
                 display_groups(region, role, cfg), anchor_areas)
```

Kiểm `display_group` trong `diversify.py`: nó đọc `cfg.display_groups.items()` và trả key đầu tiên chứa nhóm. Bản map `of` phải giữ đúng "key đầu tiên" khi một nhóm nằm ở nhiều key, nên dựng `of` bằng vòng không ghi đè (`of.setdefault(g, k)`).

Một nơi `stay` thì pipeline cũ không bao giờ đưa vào ứng viên, kể cả khi nằm trong keep (keep đã trừ stay). Vì vậy `members` loại stay.

- [ ] **Step 5: `Data`, `Row`, `Cands`, `run` trong `src/decision/pipeline.py`**

Đọc lại `pipeline.py` ngay trước khi sửa (người khác có thể đã đổi). Giữ nguyên `stub`, `wanted`, `_rule_label`, `_lodging_view`, `Result`, `why_not`.

```python
from collections.abc import Mapping

import numpy as np

from corpus.snapshot import Region, shared

from . import frame
from .fit import centers, fit
from .rank import score
from .screen import screen


class Data:
    """The corpus Place Decision reads: one snapshot region. Data(records) builds one in memory (tests, bench)."""

    def __init__(self, records: list[dict] | None = None, region: Region | None = None):
        self.region = region if region is not None else Region.from_records(records or [])
        self.by_id = self.region.by_id

    @property
    def records(self) -> list[dict]:
        return self.region.records()

    @classmethod
    def load(cls, region: str | None = None) -> "Data":
        return cls(region=shared().region(region))


@dataclass
class Row:
    """A pool place before it is built into a Cand: what diversify.pick reads (id, score, rec for the group)."""
    id: str
    score: float
    role: str
    dup: int | None
    rec: dict  # {"id", "identity": {"category_group"}, "usable_as", "near_duplicate_group"}


class Cands(Mapping):
    """Every place one run considered, built into a Cand (same as the per-place run built) only when asked: cards,
    compare, why_not, feasibility."""

    def __init__(self, region, t, si, days, relaxed, ctrs, profile, cfg, keep: set, missing: list[str]):
        self.region, self.t, self.si, self.days, self.relaxed = region, t, si, days, relaxed
        self.ctrs, self.profile, self.cfg, self.keep = ctrs, profile, cfg, keep
        self.missing = set(missing)
        self._made: dict[str, Cand] = {}

    def __contains__(self, pid) -> bool:
        if pid in self.missing:
            return True
        i = self.region.index.get(pid)
        return i is not None and bool(self.t.members[i])

    def __getitem__(self, pid) -> Cand:
        if pid not in self:
            raise KeyError(pid)
        if pid not in self._made:
            if pid in self.missing:
                c = Cand(stub(pid), "experience", keep=True, missing=True)
            else:
                i = self.region.index[pid]
                c = Cand(self.region.record(pid), self.t.role[i], keep=pid in self.keep)
            screen(c, self.si, self.days, self.relaxed)
            if c.status != "excluded" or c.keep:
                fit(c, self.si, self.days, self.ctrs, self.t.anchor_areas, self.profile, self.cfg)
                score([c], self.si, self.profile, self.cfg, voices=self.t.voices)
            self._made[pid] = c
        return self._made[pid]

    def __iter__(self):
        yield from sorted(self.missing)
        yield from (pid for i, pid in enumerate(self.region.ids) if self.t.members[i])

    def __len__(self) -> int:
        return len(self.missing) + int(self.t.members.sum())
```

Hàm `run` mới. **Thứ tự và điều kiện phải đúng như `run_reference`**; chỉ thay nguồn số liệu:

```python
def run(s, data: Data, cfg, memo: dict | None = None) -> Result:
    si, st = s.search_input, s.state
    si = si.model_copy(update={'activities': {**si.activities, **st.activities}})
    days = trip_days(si.context, cfg)
    known_days = si.context.days is not None
    wish = set(st.wishlist)
    dropped = {d.place_id for d in st.dropped}
    region = data.region
    stay = region.stay
    anchors = [a.place_id for a in si.anchors if a.place_id not in wish | dropped | stay]
    keep = (set(anchors) | set(st.selected)) - wish - stay
    missing = sorted(p for p in keep if p not in region.index)
    relaxed = {tuple(x) for x in st.relaxed}
    ctrs = centers(si, data.by_id, cfg)
    t = frame.table(region, si, st.profile, days, relaxed, ctrs, anchors, keep, len(missing), cfg, memo)
    cands = Cands(region, t, si, days, relaxed, ctrs, st.profile, cfg, keep, missing)
    ids = region.ids
    group_of = {ids[i]: t.group[i] for i in np.flatnonzero(t.live)}
    for pid in missing:
        group_of[pid] = display_group(cands[pid], cfg)

    visited = set(si.novelty.visited) | set(st.profile.visited)
    dup, light = region.column("near_duplicate_group"), region.light
    pool = [Row(ids[i], t.score[i], t.role[i], dup[i], light[i])
            for i in np.flatnonzero(t.live)
            if ids[i] not in keep and t.status[i] == "main" and ids[i] not in dropped and ids[i] not in wish
            and t.fit[i] >= cfg.min_context_fit and not (si.novelty.level == "new" and ids[i] in visited)]
    chosen = [cands[i] for i in st.selected if i in cands]
    size = sizes(si, len(days), sum(1 for a in anchors if cands[a].role == "experience"), cfg)
    reps, alts = [], {}
    for role in ("experience", "meal"):
        k = size[role] - sum(1 for c in chosen if c.role == role and c.id not in anchors)
        r_, a_ = pick([c for c in pool if c.role == role], k, cfg, sigs=region.sigs)
        reps += [cands[x.id] for x in r_]
        alts.update({lid: [cands[x.id] for x in v] for lid, v in a_.items()})
    for c in chosen:
        g = c.rec.get("near_duplicate_group")
        if g is not None and c.id not in alts:
            same = sorted((x for x in pool if x.dup == g), key=lambda x: (-x.score, x.id))
            if same:
                alts[c.id] = [cands[x.id] for x in same[:3]]

    top = {c.id for c in reps}
    rest = sorted((c for c in pool if c.id not in top), key=lambda c: (-c.score, c.id))
    ranked: dict[str, list[str]] = {}
    for c in [*(x for x in chosen if x.id not in anchors), *reps, *rest]:
        ranked.setdefault(group_of.get(c.id, "sights"), []).append(c.id)
    # ↓ from `suggested = ...` to the end: the reference body, with these replacements only
    #   unverified = sorted((cands[ids[i]] ... )) -> see below
    #   excluded   = Counter(...)                 -> see below
```

Hai đoạn khác reference:

```python
    unv = sorted((ids[i] for i in np.flatnonzero(t.live)
                  if ids[i] not in keep and t.status[i] == "unverified" and ids[i] not in dropped),
                 key=lambda p: (-t.score[region.index[p]], p))
    unverified_cards = [mk(cands[p]) for p in unv[:cfg.unverified_show]]
    # view["unverified"] = {"count": len(unv), "open": ..., "cards": unverified_cards}

    excluded = Counter()
    excl = np.array([s == "excluded" for s in t.status]) & t.members
    excl &= ~np.array([p in keep for p in ids])
    for reason, count in t.fails.items():  # count = failed checks per place, as Counter over c.checks counts them
        if (n := int(count[excl].sum())):
            excluded[reason] += n
```

Phần còn lại (từ `suggested = ...` tới `return Result(...)`) chép nguyên từ `run_reference`, chỉ đổi:
- `cands` là `Cands`.
- `name()` dùng `cands.get(pid)` (Mapping có sẵn `.get`).
- `Result(view, cands, {k: [x.id for x in v] for k, v in alts.items()}, group_of, days, shown, ranked, allocation)`.

Kiểm thêm: `pick` trong reference nhận list `Cand`. Ở đây nó nhận `Row`, có đủ `.id`, `.score`, `.rec.get("near_duplicate_group")`; `mmr` đọc `rec["identity"]["category_group"]`, `rec["usable_as"]`, và `sigs`.

Hai đoạn reference phải giữ đúng nghĩa:
- `[c for c in pool if c.role == role]`: `Row.role` = `t.role[i]`.
- `(x for x in pool if x.rec.get("near_duplicate_group") == g)` thành `x.dup == g`.

`Cand.score` của nơi lẻ (`Cands`) phải bằng `t.score`: test Task 7 đã chứng minh. `why_not` / `output.build` / `compare` dùng `res.cands.get(pid)` hoặc `res.cands[pid]`: Mapping đáp ứng.

Trong `src/decision/engine.py:98`, đổi `name_keys` để không parse mọi record:

```python
        names = zip(data.region.ids, data.region.places["name"].to_list())
        self.name_keys = [(k, pid) for pid, name in names if len((k := squash(name or "")).split()) >= 3]
```

Trong `src/decision/__main__.py`: thay thông báo "no data/serving/places.json …" bằng "no data/snapshot/current: run python -m corpus snapshot first". Chỗ in `len(data.records)` đổi thành `len(data.region.ids)`.

- [ ] **Step 6: Chạy toàn bộ test decision**

Run: `.venv/bin/python -m pytest -q tests/decision`
Expected: PASS, giống danh sách ghi ở Task 2 Step 6 (test fail sẵn từ trước vẫn fail y như cũ, không thêm test fail mới). Mọi test `test_equivalence*` PASS.

Lệch ở đâu thì tìm như sau:
1. In hai view.
2. Tìm key đầu tiên khác nhau.
3. Lần ngược về `Table` / `Cands`.

Không sửa reference, không sửa test cũ.

- [ ] **Step 7: Chạy test trên snapshot thật và các module dùng decision**

Run: `.venv/bin/python -m pytest -q -m corpus tests/decision/test_equivalence.py` rồi `.venv/bin/python -m pytest -q tests/harness tests/planning`
Expected: PASS (corpus test chạy 30 chuyến × 4 bước; vài phút là bình thường).

- [ ] **Step 8: Đo**

`bench.latency.main` dùng `Data(recs)`, nay là `Region.from_records`. Đo cả ×20.

Run: `.venv/bin/python -m bench latency --scale 1,5,20`
Expected: `create` / `act` ×1 nhanh hơn baseline nhiều lần. Ghi spec §9 (`Task = 8`). Chưa cần đạt ngân sách `act` (memo ở Task 9).

- [ ] **Step 9: Tự review**

Run: `git diff -- src/decision/pipeline.py src/decision/engine.py src/decision/diversify.py src/decision/__main__.py src/corpus/serving/groups.py`

---

### Task 9: Memo theo phiên + đo đầy đủ (quy mô, agent tool, end-to-end)

**Files:**
- Modify: `src/decision/frame.py` (memo trong `table()`), `src/decision/engine.py` (giữ `memo` theo session, truyền vào `run`), `src/bench/latency.py` (thêm tool + harness end-to-end; nhân bản qua snapshot)
- Test: `tests/decision/test_frame.py` (memo), `tests/bench/test_latency.py`

**Interfaces:**
- Consumes: `frame.table(..., memo)`, `pipeline.run(s, data, cfg, memo)` (Task 8)
- Produces: `Engine._memo: dict[str, dict]` (session id → memo); `bench.latency.tools_bench(catalog, queries)`; `bench.latency.harness_bench(scale: int) -> dict`; `bench.latency.lodging_bench(engine, decision_outputs: list[dict]) -> dict`

- [ ] **Step 1: Viết test fail** (thêm vào `tests/decision/test_frame.py`)

```python
from decision.frame import table


def test_memo_reuses_tiers_and_never_changes_numbers():
    recs = records(7)
    region = Region.from_records(recs)
    for s in sessions(7, recs, 10):
        si_ = s.search_input.model_copy(update={"activities": {**s.search_input.activities, **s.state.activities}})
        days = trip_days(si_.context, CFG)
        relaxed = {tuple(x) for x in s.state.relaxed}
        by_id = {r["id"]: r for r in recs}
        ctrs = centers(si_, by_id, CFG)
        keep = set(s.state.selected)
        memo = {}
        a = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
        b = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, memo)
        c = table(region, si_, s.state.profile, days, relaxed, ctrs, [], keep, 0, CFG, None)
        assert a.score == b.score == c.score and a.fit == c.fit and a.status == c.status
        assert set(memo) == {"screen", "fit", "score"}
```

- [ ] **Step 2: Chạy, thấy fail**

Run: `.venv/bin/python -m pytest -q tests/decision/test_frame.py -k memo`
Expected: FAIL (`assert set(memo) == …`).

- [ ] **Step 3: Memo trong `frame.table()`**

```python
import json


def _key(*parts) -> str:
    return json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)


def _cached(memo, tier: str, key: str, fn):
    if memo is None:
        return fn()
    hit = memo.get(tier)
    if hit and hit[0] == key:
        return hit[1]
    val = fn()
    memo[tier] = (key, val)
    return val
```

Trong `table()`:

```python
    sk = _key(si.model_dump(mode="json", include={"hard_filters", "activities"}),
              [(d.weekday, d.day_type) for d in days], sorted(relaxed), sorted(keep))
    role, act, scr = _cached(memo, "screen", sk, lambda: (*roles(region, si.activities, keep),
                                                         screen_table(region, si, days, relaxed, *roles(region, si.activities, keep))))
```

Viết lại cho rõ: một hàm `_screen_tier()` trả `(role, act, scr)` và chỉ gọi `roles` một lần. Hai tầng còn lại:

- **fit**: khóa = `sk` + `si.model_dump(mode="json", include={"context", "pace", "hard_filters"})` + `ctrs` + `sorted(anchor_areas)` + `profile.model_dump(mode="json", include={"travel_mult", "crowd_tolerance"})`. Đọc `fit.py` / `radius()` / `trip_companions()` để bảo đảm khóa có đủ mọi field chúng đọc. Thiếu field thì memo trả số sai, và test equivalence sẽ bắt.
- **score**: khóa = khóa fit + `si.model_dump(mode="json", include={"soft_weights", "novelty", "vibes", "context"})` + `profile.model_dump(mode="json")` + `n_missing`.

- [ ] **Step 4: Engine giữ memo theo session**

Trong `src/decision/engine.py`:
- `__init__`: `self._memo: dict[str, dict] = {}`
- `_result()`: `res = run(s, self.data, self.cfg, self._memo.setdefault(s.id, {}))`

Memo chỉ là cache theo input: không cần xóa khi `act` (khóa tự đổi). Session hết hạn hoặc bị xóa thì dọn `self._memo.pop(sid, None)`. Tìm chỗ engine xóa session (nếu có); nếu không có thì để nguyên và ghi vào spec §9 phần ghi chú là "memo sống theo process".

- [ ] **Step 5: Chạy test**

Run: `.venv/bin/python -m pytest -q tests/decision`
Expected: PASS (cả equivalence).

- [ ] **Step 6: Bench đo đầy đủ**

Trong `src/bench/latency.py`:

1. `main()`: với mỗi `n`, dựng vùng bằng `Region.from_records(replicate(base, n))` rồi `Data(region=...)`. Đo riêng `region_s` (thời gian dựng bảng) và `decision_bench`.
2. Thêm `tools_bench(Catalog.from_snapshot(shared().region(), n_min), QUERIES)`. Dùng `QUERIES` = 10 tên nơi có thật lấy từ 10 record đầu (`r["identity"]["name"][:20]`) và 5 chuỗi không khớp (`"quán xyz"`, …). Đo thêm ×20 bằng catalog dựng từ `Region.from_records(replicate(...))` cùng `intel` nhân bản: nhân `region.intel()` theo cùng quy tắc id `~k`.
3. Thêm `harness_bench(scale)`: dựng `Harness` offline như `bench/run.py` `Sim.__init__` (Trip / Decision / Planning tools, `Store` trong `data/bench/latency/sessions`). Với 10 chuyến, gọi `decision.create` rồi 3 lần `decision.act` qua `Harness.request`, đo `time.perf_counter()` quanh `request`. Chỉ đo ×1: harness dùng `shared().region()`.
4. `startup_bench()`: thêm `snapshot.region_s` (Snapshot mới, không qua `shared`), `trip.Catalog.from_snapshot_s`, `planning.create_engine_s` (`planning.tools.create_engine(ROOT / "data")`, offline env như `bench/__main__.py`).
5. `lodging_bench(engine, decision_outputs)`: đo `planning.Engine.lodging_options(decision)` (tab "Chỗ ở", handoff §2). Dùng Decision Output của 10 chuyến đầu sau 3 lần `select`, lấy bằng `decision.Engine.draft(sid, any_state=True)` (`src/decision/engine.py:291`, chính là cách harness `read/decision/lodging` lấy). Ghi `first` (lần đầu, không cache) và `cached` (gọi lại cùng input). Báo số `stay` trong vùng và số ứng viên trả về. Chỉ đo, không tối ưu: Planning ngoài phạm vi (spec §1). Nếu `first` p99 > 200 ms, ghi vào spec §9 phần ghi chú để user quyết.

Thêm test nhỏ cho `tools_bench` vào `tests/bench/test_latency.py` (catalog từ `Region.from_records` fixture, 2 query, kiểm key `search_places`).

- [ ] **Step 7: Đo và so ngân sách**

Run: `.venv/bin/python -m bench latency --scale 1,5,20`

So với ngân sách ở Global Constraints. Ghi spec §9 (`Task = 9`).

Mục nào **không đạt**:
- Profile bằng `cProfile` như cách đo baseline trong spec §2.
- Ghi 3 hàm tốn nhất vào ghi chú §9.
- Dừng, báo user. Không nới ngân sách, không bỏ oracle.

- [ ] **Step 8: Tự review**

Run: `git diff -- src/decision/frame.py src/decision/engine.py src/bench/latency.py`

---

### Task 10: Tài liệu chính thức

**Files:**
- Modify: `docs/CORPUS.md` (§Data model, §Place Decision dùng corpus thế nào, §Kiểm soát chi phí và hiệu năng, §CLI, §Sai lệch cho bản demo), `docs/PLACE_DECISION.md` (§2.2, §18), `README.md` (lệnh `python -m corpus snapshot`, `python -m bench latency`), `docs/log/DEV_LOG.md` (theo khuôn của chính file đó), `docs/superpowers/specs/2026-10-12-corpus-semantic-index-design.md` (xóa §2, thay bằng một dòng trỏ sang spec này)

- [ ] **Step 1: `docs/CORPUS.md`**

- §Data model, bảng đường dẫn: thêm dòng `data/snapshot/<version>/<region>/` (ghi bởi `corpus.snapshot`, nội dung: bảng `places`, `features`, `feature_ctx`, `fit_verdicts`, `records`, `intel`, `videos`) và `data/snapshot/current`.
- Ghi rõ: `data/serving/places.json` là bản build offline; online chỉ đọc snapshot.
- Câu "Lưu trữ hiện tại là file, không phải DB" thành "Lưu trữ là file: JSON cho các bước offline, LanceDB cho snapshot online".
- §Place Decision dùng corpus thế nào: thay "Planner chỉ đọc serving record" bằng mô tả đọc qua `corpus.snapshot.Region` (bảng nóng + `record(id)`). Một sơ đồ mermaid ngắn như spec §4.
- §Kiểm soát chi phí và hiệu năng: thêm một gạch đầu dòng về snapshot + ngân sách độ trễ, trỏ tới `python -m bench latency`.
- Viết đúng hiện trạng code (`RULE.md` §0.1): không viết "trước đây", không viết kiểu kế hoạch.

- [ ] **Step 2: `docs/PLACE_DECISION.md`**

- §2.2: thêm một câu: Place Decision đọc serving record qua snapshot (`corpus.snapshot`). Bước ③–⑤ tính cho mọi nơi bằng bảng (`decision.frame`); thẻ dựng bằng hàm theo từng nơi; hai bên được giữ khớp bằng oracle test (`tests/decision/test_equivalence.py`).
- §18 CLI và API: ghi `Data.load(region)` và lỗi khi thiếu snapshot.

- [ ] **Step 3: `README.md`, `docs/log/DEV_LOG.md`**

- README: thêm hai lệnh vào mục CLI / cách chạy. Không chép bảng ngân sách.
- DEV_LOG: một mục theo khuôn của file. Có gì đổi, số đo trước / sau (từ spec §9), hành vi đổi có chủ đích (catalog chỉ còn nơi được phục vụ).

- [ ] **Step 4: Spec cũ**

Trong `docs/superpowers/specs/2026-10-12-corpus-semantic-index-design.md`, thay cả §2 bằng:

```markdown
## 2. Mask tất định cho Place Decision

Đã thay bằng `docs/superpowers/specs/2026-10-13-corpus-snapshot-design.md`.
```

- [ ] **Step 5: Kiểm tài liệu khớp code**

Run: `grep -rn "serving/places.json" docs README.md`
Expected: mọi chỗ nhắc file này đều nói đó là bản build offline, không còn chỗ nói online đọc nó.

- [ ] **Step 6: Báo user và chờ**

Báo user:
- Bảng spec §9.
- Danh sách test fail từ trước (Task 2 Step 6).
- Hành vi catalog đã đổi.
- Hỏi có xóa spec + plan này không (`RULE.md` §0.1).

Không tự xóa.

---

## Tự kiểm (người viết plan đã chạy)

- Spec §2.1 (tình trạng corpus, chỗ ở, build v13) → Task 0; chỉ trạng thái được phục vụ + giữ chỗ ở → Task 4 (`test_compile_keeps_only_served_and_keeps_stays`), Task 2 (bộ sinh có `stay`); tab "Chỗ ở" → Task 9 (`lodging_bench`).
- Spec §3 (công nghệ) → Task 4 (dependency); §4 (kiến trúc, `current`, compile ở cuối serving) → Task 4; §5 (bảng) → Task 3; §6.1 → Task 4; §6.2 → Task 6–9; §6.3 → Task 5; §6.4 + §7 (đo) → Task 1, 9; oracle → Task 2, 8; §9 → mọi task đo; tài liệu → Task 10.
- Tên dùng chéo: `tables`, `compile_snapshot`, `Snapshot.open/region`, `shared`, `Region.from_records/record/records/by_id/intel/videos/feature/ctx_top/verdict/sigs/stay/ids/index/places`, `FeatureColumn.eq/has/only/exists/firm/uncertain/conf`, `roles`, `screen_table`, `Screen`, `fit_table`, `score_table`, `table`, `Table`, `Cands`, `Row`, `Data(records|region)`, `rank.score(voices=)`, `mmr(sigs=)`, `pick(sigs=)`, `scope_allows`, `Catalog.from_snapshot`, `eval_trips`, `eval_search_input`.
