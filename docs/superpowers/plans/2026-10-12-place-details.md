# Chi tiết địa điểm (13 mục) — plan triển khai

> **Cho agent thực thi:** làm **tuần tự** Task 1 → Task 11 trong **một session** (không chia song song: tốn token hơn và dễ đụng nhau trên `src/corpus/llm/tasks.py`). Mỗi bước dùng checkbox `- [ ]`; đánh dấu `- [x]` ngay khi xong để session sau đọc file này là biết làm tới đâu. Plan chỉ là việc cần làm; chưa task nào được thực thi (2026-10-12).

**Mục tiêu:** corpus trả lời được 13 câu người đi Đà Lạt cần (đi một mình hoặc đi với bất kỳ x nào), rồi Place Decision, Planning và Web dùng được.

**Kiến trúc:** thêm feature enum vào ontology + một kiểu observation mới `detail` (chữ tự do có span) trích trong cùng call Extractor; code gộp thành khối `details` của serving record; online đọc khối đó. Không model nào ghi giá trị.

**Spec (đọc trước):** `docs/superpowers/specs/2026-10-12-place-details-design.md`. File làm việc tạm (`RULE.md` §0.1); Task 11 gộp vào tài liệu chính thức rồi xóa cả spec lẫn plan này.

**Tech:** Python 3.12 (`.venv/bin/python`), pytest (`pythonpath = src`), React + TS (`web/`).

## Thứ tự

| Task | Việc | Sửa file |
|---|---|---|
| 1 | Nền: ontology, companions, seasons, serving config, gate `detail` | `config/ontology.yaml`, `config/companions.yaml`, `config/seasons.yaml`, `config/serving.yaml`, `src/corpus/ontology.py`, `src/corpus/observe/__init__.py`, `src/corpus/observe/details_gate.py` (mới) |
| 2 | Observe Maps | `src/corpus/llm/tasks.py` (`REVIEW_OBSERVE`), `src/corpus/observe/gmaps/gate.py`, `.../gmaps/extract.py`, `config/queries.yaml` |
| 3 | Observe TikTok | `tasks.py` (`VIDEO_OBSERVE`), `src/corpus/observe/tiktok/extract.py` |
| 4 | Observe official | `tasks.py` (`OFFICIAL_OBSERVE`), `src/corpus/observe/official/__init__.py` |
| 5 | Judge + nhãn cho `detail` | `src/corpus/review/labels.py`, `src/corpus/judge/audit.py` |
| 6 | Aggregate `details` | `src/corpus/aggregate/details.py` (mới), `aggregate/place.py` |
| 7 | Serving `details` | `src/corpus/serving/details.py` (mới), `serving/record.py`, `serving/run.py` |
| 8 | Trip + Decision | `src/requirements/checks.py`, `src/trip/domain/*`, `src/decision/*`, `config/trip.yaml`, `config/decision.yaml` |
| 9 | Planning | `src/planning/*`, `config/planning.yaml` |
| 10 | Web | `web/scripts/export_snapshot.py`, `web/src/user/ui/PlaceSheet.tsx` + css, `web/src/user/planning/*` |
| 11 | Chạy thật + tài liệu | `data/`, `docs/*.md`, xóa spec + plan |

## Quy tắc chung (đọc trước khi làm)

- Tuân `RULE.md`: tài liệu tiếng Việt; code, comment, identifier tiếng Anh; thay đổi nhỏ nhất; không deep import giữa module (`AGENTS.md`).
- **Working tree dùng chung với nhiều session: không commit, không push, không `git add -A`, không `git stash`.** Đọc `git status` trước khi sửa; chỉ sửa file trong cột "Sửa file" của task đang làm. Cuối mỗi task: `git diff -- <file của task>` để tự review.
- Không bịa giá trị: thiếu bằng chứng là `unknown` / `null`; không span thì không giá trị.
- Test: `.venv/bin/python -m pytest -q <thư mục>`; không gọi mạng, không gọi model thật (giả lập như test hiện có). Không nới / xóa test cũ để pass.
- Không chạy `python -m corpus ...` trên dữ liệu thật trước Task 11.
- TDD: viết test fail → code → test pass.

## Hợp đồng dữ liệu (mọi task làm đúng hình dạng này)

### H1. Ontology (`config/ontology.yaml`, Task 1)

Feature mới (bump `version` 11 → 12):

| id | group | values | khác |
|---|---|---|---|
| `car_access` | effort | yes, no | check span |
| `coach_access` | effort | yes, no | check span |
| `night_road_risk` | effort | present | check span |
| `rest_benches` | effort | present, absent | check span |
| `stroller_access` | effort | yes, no | check span |
| `fog_blocks_view` | environment | present | check span |
| `cold` | environment | present | |
| `toilet_available` | environment | yes, no | |
| `heater` | environment | present, absent | |
| `hot_water` | environment | good, poor | |
| `kids_play_area` | experience | present | |
| `pets` | suitability | allowed, not_allowed | verify always, caution [not_allowed], check span |
| `scam_stage` | service | parking, photo, tout, forced_purchase, menu_price, rental | caution = mọi giá trị, check span |
| `breakfast` | service | included, not_included | |

Khối mới `details:` — mỗi kind: `id`, `hint` (tiếng Việt, cho prompt), `claim` (mẫu có `{text}`, cho Judge), `audit` (`full` | `sampled`), `targeted` (bool: mẫu `extremes` / `keywords` được tính), `owner` (bool: nguồn của chính doanh nghiệp được tính), `needs` (trường bắt buộc).

| kind | needs | audit | targeted | owner |
|---|---|---|---|---|
| `known_for` | — | sampled | false | false |
| `order` | — | sampled | true | true |
| `avoid` | — | full | true | false |
| `activity` | — | sampled | true | true |
| `photo_spot` | — | sampled | true | true |
| `fee` | amount_vnd | full | true | true |
| `best_time` | — | sampled | true | false |
| `avoid_time` | — | sampled | true | false |
| `schedule` | days | full | true | true |
| `last_entry` | hour | full | true | true |
| `access` | — | sampled | true | true |
| `booking` | — | sampled | true | true |
| `bring` | — | sampled | true | false |
| `situation` | — | sampled | false | false |
| `fit` | who, verdict | full | true | false |

### H2. Từ vựng người đi cùng (`config/companions.yaml`, Task 1)

```yaml
version: 1
sensitive: [baby, parents, pregnant, wheelchair]   # fit=bad of these is a caution value and a hard filter
companions:
  - {id: solo, vi: "Một mình", synonyms: ["một mình", "đi 1 mình", "solo"], suitability: null}
  - {id: partner, vi: "Người yêu, vợ chồng", synonyms: ["người yêu", "vợ chồng", "cặp đôi", "bạn gái", "bạn trai", "hẹn hò"], suitability: couples}
  - {id: friends, vi: "Bạn bè", synonyms: ["bạn bè", "nhóm bạn", "hội bạn"], suitability: null}
  - {id: kids, vi: "Trẻ nhỏ", synonyms: ["trẻ em", "trẻ nhỏ", "các bé", "con nít", "con nhỏ"], suitability: kids}
  - {id: baby, vi: "Em bé", synonyms: ["em bé", "bé sơ sinh", "xe đẩy", "con mới sinh"], suitability: null}
  - {id: parents, vi: "Bố mẹ, người lớn tuổi", synonyms: ["bố mẹ", "ba mẹ", "ông bà", "người lớn tuổi", "người già"], suitability: elderly}
  - {id: pregnant, vi: "Bà bầu", synonyms: ["bà bầu", "mang thai", "có bầu"], suitability: null}
  - {id: wheelchair, vi: "Người đi xe lăn", synonyms: ["xe lăn"], suitability: wheelchair}
  - {id: pet, vi: "Thú cưng", synonyms: ["thú cưng", "chó", "mèo", "cún", "pet"], suitability: pets}
  - {id: coworkers, vi: "Đồng nghiệp", synonyms: ["đồng nghiệp", "công ty", "team building"], suitability: null}
  - {id: large_group, vi: "Đoàn đông", synonyms: ["đoàn đông", "nhóm đông", "cả đoàn"], suitability: groups}
```

Id `parents` trùng id `companions` của Trip (`src/trip/domain/values.py`); spec ghi `elderly` là tên enum suitability, không phải id người đi cùng.

### H3. Observation `detail` (Task 1 định nghĩa, Task 2–4 ghi, Task 5–6 đọc)

File `data/<source>/observations/<fid_dir>.json` có thêm mảng `details` (cạnh `observations`). Mỗi phần tử là `observation(...)` thường với:

```text
feature = "detail.<kind>"     value = text (chuỗi con của quote, giữ nguyên chữ nguồn)
detail = {amount_vnd: int|null, audience: adult|child|senior|all|null, unit: person|group|vehicle|item|null,
          min_people: int|null, months: [1..12], days: [mon..sun], hour: "HH:MM"|null,
          who: <companion id hoặc chữ gốc>|null, verdict: good|bad|conditional|null}
context.time_of_day dùng cho best_time / avoid_time
```

`id` dạng `<source>:<source_id>:d<n>`. `sample` gắn như observation thường. Nguồn official: `source_type = official_page`, `author = official:<fid>` (nguồn có thẩm quyền).

### H4. Intel (`data/intel/places/*.json`, Task 6)

`intel["details"] = {kind: [Cluster]}`, `Cluster = {text, n, authority, members: [obs id], evidence: [≤5 obs id], amount_vnd, audience, unit, min_people, months: {m: n}, days: {d: n}, hours: [..], time_of_day: {tod: n}, who, verdicts: {v: n}}` (trường không áp dụng = null / rỗng). `fit` gom theo (`who`, lý do). `intel["operation"]` thêm `tickets_vnd` ({adult, child, senior}) và `last_entry` ("HH:MM" | null) từ official.

### H5. Serving record (`data/serving/places.json`, Task 7 viết; Task 8–10 đọc)

```text
record["details"] = {
  "known_for": {"headline": Item|null, "more": [Item]},
  "order"|"avoid"|"activity"|"photo_spot"|"access"|"booking"|"bring"|"situation": [Item],
  "cost": null | {"entry": {"adult"|"child"|"senior": {"vnd": int, "source": "official"|"reviews"}|null},
                  "parking": Item|null, "extras": [Item], "per_party": [Item],
                  "total_vnd": {"base": int, "with_extras": int}|null, "kind": "fact"|"estimate"},
  "timing": {"best_time": Window, "avoid_time": Window, "best_months": [int], "avoid_months": [int],
             "schedule": [Item], "last_entry": {"time": "HH:MM", "source": "official"|"reviews"}|null},
  "fit": {who: {"value": "good"|"bad"|"conditional", "distribution": {v: n}, "n": int,
                "reasons": [str], "status": "VERIFIED"|"UNCERTAIN", "evidence": [id]}},
  "relations": {"quieter": [place id], "busier": [place id]},
  "walk_to_night_market_min": int|null
}
Item   = {"text", "n", "status": "VERIFIED"|"UNCERTAIN", "reason": str|null, "evidence": [id],
          "amount_vnd"?, "audience"?, "unit"?, "min_people"?, "months"?, "days"?, "hour"?}
Window = {"by_time_of_day": {tod: n}, "hours": ["HH:MM"], "items": [Item]}
```

Khối không có dữ liệu: danh sách rỗng / `null`, không bao giờ bịa. Feature enum mới nằm trong các khía cạnh cũ (`experience`, `environment`, `service`, `effort`, `suitability`).

`corpus.serving.feature(record, "fit.<who>")` trả `{"value", "distribution", "status"}` của `details.fit[who]` (hoặc `None`), nên `corpus.serving.check(record, "fit.baby", "bad")` chạy như feature thường.

### H6. Bộ lọc cứng (Task 8)

- Có `pet` trong người đi cùng → `HardFilter(feature="pets", op="ne", value="not_allowed")`.
- Có x nhạy cảm (`baby`, `parents`, `pregnant`, `wheelchair`) → `HardFilter(feature="fit.<x>", op="ne", value="bad")`.
- `mobility = car` và `people ≥ config/trip.yaml coach_min_people (9)` → `HardFilter(feature="coach_access", op="ne", value="no")`.

### H7. Cấu hình (Task 1 viết, Task 7 đọc)

`config/serving.yaml` thêm:

```yaml
details:
  min_authors: 2            # a cluster is served from this many authors, or one authoritative source
  max_items: 6              # per list block
  known_for_more: 3
  cluster_jaccard: 0.6      # token-set overlap that merges two phrasings of one thing
  stopwords: ["rất", "khá", "hơi", "cực", "siêu", "lắm", "quá", "nha", "nhé", "thì", "là", "của", "ở", "đây", "này"]
  night_market_fid: "0x317113ff4e41e7c3:0x21cff9ad21a7243c"   # "Chợ Đêm Đà Lạt" in the corpus
  walk_max_min: 20
  walk_road_factor: 1.3
  walk_m_per_min: 80
```

`config/seasons.yaml`: `seasons: []`, mỗi dòng `{match: "<cụm chữ>", months: [..], source: "<url nguồn>"}`; **chỉ người điền, kèm nguồn** — plan không điền tháng nào.

---

## Task 1: Nền — ontology, companions, cấu hình, gate `detail`

**Đọc trước:** `src/corpus/ontology.py`, `config/ontology.yaml`, `src/corpus/observe/__init__.py`, `src/corpus/observe/official/__init__.py` (`amount_in`, `hour_in`), `tests/test_ontology.py`.

**Sản phẩm (task sau dùng đúng tên này):**
- `corpus.ontology`: `DetailKind(id, hint, claim, audit="sampled", targeted=False, owner=False, needs=())`, `Companion(id, vi, synonyms, suitability)`; `Ontology` thêm `details: dict[str, DetailKind]`, `companions: dict[str, Companion]`, `sensitive: frozenset[str]` và các method `valid_detail(feature) -> bool` (`feature == "detail.<kind>"` có trong `details`), `detail_kind(feature) -> DetailKind | None`, `who(text) -> str` (id khi chữ trùng id / chứa một synonym, synonym dài khớp trước; còn lại trả chữ đã chuẩn hóa), `as_feature(fid) -> Feature` (feature thật, hoặc `Feature(fid, "detail", ("*",), kind.hint)` cho detail). `prompt_text()` thêm khối detail kind và danh sách id người đi cùng. `load(path=PATH, companions_path=COMPANIONS)`.
- `corpus.observe.details_gate`: `AUDIENCES`, `UNITS`, `VERDICTS`, `DAYS`, `norm`, `amount_in`, `hour_in`, `month_in`, `day_in`, `gate_detail(d: dict, source_text: str, ont) -> tuple[dict | None, str | None]` trả `({"kind", "text", "quote", "time_of_day", "detail": {...H3}}, None)` hoặc `(None, lý do)`.
- `corpus.observe.observation(..., detail: dict | None = None)`: có `detail` thì thêm khóa `"detail"`.

- [x] **1.1 Test ontology (fail trước).** Thêm vào `tests/test_ontology.py`:

```python
def test_place_details_ontology():
    ont = load()
    assert ont.version >= 12
    for fid in ("car_access", "coach_access", "stroller_access", "pets", "scam_stage", "fog_blocks_view", "cold",
                "rest_benches", "toilet_available", "kids_play_area", "night_road_risk", "heater", "hot_water", "breakfast"):
        assert fid in ont.features
    assert ont.features["pets"].verify == "always" and ont.features["pets"].caution_values == ("not_allowed",)
    assert set(ont.features["scam_stage"].caution_values) == set(ont.features["scam_stage"].values)
    assert ont.valid_detail("detail.fee") and not ont.valid_detail("detail.wifi") and not ont.valid_detail("fee")
    assert ont.details["fee"].needs == ("amount_vnd",) and ont.details["fit"].needs == ("who", "verdict")
    assert ont.details["fit"].audit == "full" and "{text}" in ont.details["known_for"].claim
    assert ont.as_feature("detail.order").group == "detail" and ont.as_feature("crowd").group == "environment"
    assert ont.who("chó") == "pet" and ont.who("đi với con chó nhà mình") == "pet"
    assert ont.who("Bà bầu") == "pregnant" and ont.who("hàng xóm") == "hàng xóm"
    assert ont.sensitive == {"baby", "parents", "pregnant", "wheelchair"}
    assert ont.companions["parents"].suitability == "elderly" and ont.companions["pet"].suitability == "pets"
    text = ont.prompt_text()
    assert "- detail fee:" in text and "who = solo | partner" in text
    assert {"heater", "hot_water", "breakfast", "cold", "toilet_available", "pets"} <= ont.stay


def test_detail_kind_errors():
    raw = {**BASE, "features": [A]}
    with pytest.raises(ValueError, match="needs"):
        parse({**raw, "details": [{"id": "x", "hint": "h", "claim": "{text}", "needs": ["colour"]}]})
    with pytest.raises(ValueError, match="claim"):
        parse({**raw, "details": [{"id": "x", "hint": "h", "claim": "no placeholder"}]})
    with pytest.raises(ValueError, match="duplicate"):
        parse({**raw, "details": [{"id": "x", "hint": "h", "claim": "{text}"}] * 2})
```

Chạy `.venv/bin/python -m pytest -q tests/test_ontology.py` → FAIL.

- [x] **1.2 `config/ontology.yaml`.** `version: 12`. Thêm 14 feature của H1 vào đúng nhóm, mỗi cái có `hint` tiếng Việt theo khuôn feature hiện có (nói rõ cái gì **không** phải: ví dụ `car_access`: "ô tô vào tới cổng hoặc bãi xe của nơi này; đường hẹp chỉ xe máy vào được là no; ô tô của người viết đậu xa rồi đi bộ không nói gì về đường"); feature `check: span` phải có `claims` cho đúng mọi giá trị (parser bắt). `stay_features` thêm `heater, hot_water, breakfast, cold, toilet_available, pets`. Thêm khối `details:` 15 kind theo bảng H1, ví dụ:

```yaml
details:
  - {id: known_for, hint: "điều làm nơi này khác các nơi cùng loại, người viết nói là nổi tiếng / đặc trưng / phải thử (\"xích đu nhìn xuống hồ Tuyền Lâm\"); khen chung (\"view đẹp\", \"đồ ngon\") không phải", claim: "nơi này nổi tiếng vì: {text}", audit: sampled, targeted: false, owner: false}
  - {id: fee, hint: "một khoản tiền ở nơi này: vé theo đối tượng, trò chơi, thuê đồ, xe điện, gửi xe, combo; text = tên khoản", claim: "ở nơi này có khoản phải trả: {text}", audit: full, targeted: true, owner: true, needs: [amount_vnd]}
  - {id: fit, hint: "đi nơi này với một người / con vật cụ thể (who) hoặc một mình thì hợp / không hợp / hợp có điều kiện, kèm lý do; \"đi cùng gia đình rất vui\" không phải", claim: "đi nơi này với {who} thì {verdict}: {text}", audit: full, targeted: true, owner: false, needs: [who, verdict]}
```

(claim của `fit` dùng thêm `{who}`, `{verdict}`; parser chỉ bắt buộc `{text}`.)

- [x] **1.3 `config/companions.yaml`** đúng như H2. **`config/seasons.yaml`**: chú thích (tiếng Anh) + `seasons: []`. **`config/serving.yaml`**: thêm khối `details` của H7.

- [x] **1.4 `src/corpus/ontology.py`.** `COMPANIONS = ROOT / "config" / "companions.yaml"`, `NEEDS = ("amount_vnd", "days", "hour", "who", "verdict")`, `AUDIT = ("full", "sampled")`, `DETAIL_PREFIX = "detail."`. `parse(raw, companions_raw=None)`: kiểm kind trùng (`duplicate detail kind`), `needs` ngoài `NEEDS` (`unknown needs`), `claim` thiếu `{text}` (`claim needs {text}`), `audit` ngoài `AUDIT`. Companions: id trùng → lỗi; `suitability` phải là feature có trong ontology hoặc null; `sensitive` ⊆ id. `who()`: chuẩn hóa NFC + casefold + gộp khoảng trắng; khớp id, rồi synonym (dài trước) là chuỗi con. `prompt_text()` thêm:

```text
Detail kinds (kind: what to copy):
- detail known_for: ...
who = solo | partner | friends | ... (or the source's own word)
verdict = good | bad | conditional
```

- [x] **1.5 Test gate (fail trước).** Tạo `tests/observe/test_details_gate.py`:

```python
from corpus.observe.details_gate import gate_detail
from corpus.ontology import load

ONT = load()
SRC = "Vé 50k/người, xe điện 40k một lượt. Đi tháng 11 có dã quỳ, thứ 7 có đêm nhạc. Mang chó vào được nhưng phải rọ mõm"


def d(**kw):
    base = {"kind": "fee", "text": "xe điện", "amount_vnd": 40000, "audience": "", "unit": "", "min_people": 0,
            "months": [], "days": [], "hour": "", "who": "", "verdict": "", "time_of_day": "unknown",
            "quote": "xe điện 40k một lượt"}
    return {**base, **kw}


def test_keeps_fee_with_amount_in_quote():
    out, why = gate_detail(d(), SRC, ONT)
    assert why is None and out["kind"] == "fee" and out["text"] == "xe điện"
    assert out["detail"]["amount_vnd"] == 40000 and out["detail"]["audience"] is None


def test_drops():
    cases = {"unknown_kind": d(kind="wifi"), "quote_not_in_source": d(quote="xe điện 99k"),
             "text_not_in_quote": d(text="xe buýt"), "amount_not_in_quote": d(amount_vnd=60000),
             "missing_amount_vnd": d(amount_vnd=0), "month_not_in_quote": d(kind="best_time", text="dã quỳ",
             amount_vnd=0, months=[12], quote="tháng 11 có dã quỳ"),
             "day_not_in_quote": d(kind="schedule", text="đêm nhạc", amount_vnd=0, days=["sun"], quote="thứ 7 có đêm nhạc"),
             "missing_who": d(kind="fit", text="phải rọ mõm", amount_vnd=0, verdict="conditional",
                              quote="Mang chó vào được nhưng phải rọ mõm")}
    for reason, item in cases.items():
        assert gate_detail(item, SRC, ONT) == (None, reason), reason


def test_fit_maps_who_and_months_days_kept():
    out, _ = gate_detail(d(kind="fit", text="phải rọ mõm", amount_vnd=0, who="chó", verdict="conditional",
                           quote="Mang chó vào được nhưng phải rọ mõm"), SRC, ONT)
    assert out["detail"]["who"] == "pet" and out["detail"]["verdict"] == "conditional"
    out, _ = gate_detail(d(kind="schedule", text="đêm nhạc", amount_vnd=0, days=["sat"], quote="thứ 7 có đêm nhạc"),
                         SRC, ONT)
    assert out["detail"]["days"] == ["sat"]
```

- [x] **1.6 `src/corpus/observe/details_gate.py`.** Chuyển `amount_in`, `hour_in` từ `observe/official/__init__.py` sang đây; trong official đổi thành `from ..details_gate import amount_in, hour_in` (test official cũ phải vẫn pass). Thứ tự kiểm (lý do đúng chuỗi trong test): `unknown_kind` → `quote_not_in_source` → `text_not_in_quote` → `missing_<need>` (theo `kind.needs`: `amount_vnd` > 0, `days` không rỗng, `hour` dạng `HH:MM`, `who` khác rỗng, `verdict` ∈ `VERDICTS`) → `amount_not_in_quote` (khi `amount_vnd` > 0) → `min_people_not_in_quote` (khi > 0: số đó có trong quote) → `month_not_in_quote` (`(tháng|thg|th)\s*0?{m}(?!\d)`) → `day_not_in_quote` (`mon` "thứ 2|thứ hai|t2" … `sat` "thứ 7|thứ bảy|t7", `sun` "chủ nhật|cn") → `hour_not_in_quote`. `audience` / `unit` ngoài enum → `None` (không bỏ observation). `time_of_day` ngoài context → `"unknown"`. `who` qua `ont.who()`.

- [x] **1.7 `observation(detail=...)`** trong `src/corpus/observe/__init__.py`.

- [x] **1.8 Kiểm:** `.venv/bin/python -m pytest -q tests/test_ontology.py tests/observe tests/aggregate tests/serving` xanh (feature mới không làm hỏng test cũ). `git diff --stat` chỉ có file của Task 1.

## Task 2: Observe Maps trả `details`

**Đọc trước:** `src/corpus/observe/gmaps/extract.py` (`ask_checked`, `observe_place`, `tag_samples`, `prune`, `run`), `gate.py`, `REVIEW_OBSERVE` trong `src/corpus/llm/tasks.py`, `tests/observe/gmaps/test_gmaps_observe.py` (fixture `setup`, `fake_ask`).

- [x] **2.1 Test (fail trước)** trong `tests/observe/gmaps/test_gmaps_observe.py`: một `fake_ask` trả cho review "Vé 50k, xe điện 40k/lượt" một `details` `fee` hợp lệ và một `fee` có quote bịa. Kiểm file observation: `details` có đúng 1 phần tử, `feature == "detail.fee"`, `value == "xe điện"`, `detail.amount_vnd == 40000`, `id` dạng `gmaps:R1:d0`, `stats.dropped["detail_quote_not_in_source"] == 1`. Thêm test: chạy lại với cùng review (reuse) giữ nguyên `details` không gọi model; qc gắn cờ review đó sau → `details` của nó bị cắt (`prune`). Test schema: mỗi phần tử của `reviews[].details` có `quote` là khóa cuối.
- [x] **2.2 `REVIEW_OBSERVE`.** Thêm `_REVIEW_DETAIL_KEYS = ("kind", "text", "amount_vnd", "audience", "unit", "min_people", "months", "days", "hour", "who", "verdict", "time_of_day", "quote")` (quote cuối, cùng lý do comment cũ); kiểu: `amount_vnd`, `min_people` integer; `months` array integer; `days` array string; còn lại string; mọi khóa required. Mỗi review thêm `"details"` (required). Prompt: thêm đoạn sau đoạn `proposed`:

```text
Details: also copy what the review says about THIS place for each detail kind in the list above.
- kind from the list; text = the shortest words naming it, copied exactly and part of quote; quote = the words that state it.
- amount_vnd: the VND amount the quote gives ("30k" -> 30000), else 0; a fee always has one. audience: adult | child |
  senior | all, else "". unit: person | group | vehicle | item, else "". min_people: the smallest party the quote
  names ("tối thiểu 4 người" -> 4), else 0.
- months: month numbers the quote names ("tháng 11" -> [11]); never from your own knowledge ("mùa dã quỳ" -> []).
  days: mon..sun the quote names ("thứ 7" -> ["sat"]). hour: "HH:MM" the quote names ("trước 6h" -> "06:00"), else "".
- fit: who = the companion id the review means, else its own word ("chó", "đồng nghiệp"); verdict = good | bad |
  conditional for going here with them; going with someone and having fun is no fit.
- Fields a kind does not use: "" / 0 / [].
```

  và 4 ví dụ (fee "xe điện 40k/lượt"; order "bánh căn trứng 30k ai cũng gọi"; fit "đẩy xe em bé không được vì toàn bậc thang" → who baby, verdict bad, text "toàn bậc thang"; known_for "nổi tiếng với xích đu nhìn xuống hồ"). Thêm ví dụ `visit_duration` "đi nhanh 30 phút, đi kỹ 2 tiếng" (mục 3).
- [x] **2.3 `gate.py`**: `gate_details(answer, refs, ont) -> tuple[list[tuple[str, dict]], collections.Counter]` dùng `details_gate.gate_detail(item, refs[ref]["text"], ont)`; lý do đếm là `f"detail_{reason}"`. `gate()` giữ nguyên chữ ký.
- [x] **2.4 `extract.py`**: `ask_checked` trả 4 phần `(kept, proposed, details, dropped)` (gộp hai nửa cho cả 4); `observe_place`: hàm `add_detail(r, d, extractor)` tạo `observation(id=f"gmaps:{rid}:d{k}", feature=f"detail.{kind}", value=text, context={time_of_day: d["time_of_day"], day_type: day_type(r), weather: UNKNOWN}, source_type="gmaps_review", field="text", ..., detail=d["detail"])`; review reuse lấy lại `previous.get("details", [])` theo `source_id`; doc ghi `"details"`. `tag_samples` gắn `sample` cho `details` như `observations`; `prune` cắt `details` của review bị cờ. `run`: summary thêm `"details": Counter(feature)`. Câu trả lời thiếu khóa `details` (fake cũ) coi là `[]`.
- [x] **2.5 `config/queries.yaml` `keyword_sets`**: thêm từ (đúng nhóm category có sẵn trong file): nơi trải nghiệm "gửi xe", "xe điện", "thuê đồ", "tháng", "xe 16 chỗ", "lạnh", "sương mù", "một mình", "chó", "xe đẩy", "bà bầu"; ăn uống "món", "nên gọi"; chỗ ở "máy sưởi", "nước nóng", "bữa sáng", "thú cưng".
- [x] **2.6 Kiểm:** `.venv/bin/python -m pytest -q tests/observe/gmaps tests/test_llm_task.py` xanh.

## Task 3: Observe TikTok trả `details`

**Đọc trước:** `src/corpus/observe/tiktok/extract.py`, `VIDEO_OBSERVE`, `tests/observe/tiktok/test_tiktok_observe.py`.

- [x] **3.1 Test (fail trước):** fake `VIDEO_OBSERVE.ask` trả `details` gồm một `fee` speech hợp lệ (quote trong segment `ref`), một caption hợp lệ, một `source: "frame"` → file có 2 `details` (`source_type` `tiktok_segment` / `tiktok_caption`, `start_s` / `end_s` của segment), `dropped["detail_frame_not_allowed"] == 1`.
- [x] **3.2 `VIDEO_OBSERVE`**: schema thêm `"details"` (required) với khóa của `_REVIEW_DETAIL_KEYS` + `source` (enum speech | caption) + `ref` (integer), quote cuối. Prompt thêm đúng đoạn Details của Task 2 (đổi "review" thành "video"), nói rõ details chỉ lấy từ speech / caption.
- [x] **3.3 `extract.py`**: `observe_pair` trả `(out, details_out, dropped)`; gate: source text = `by_i[ref]["checked_text"]` (speech) hoặc caption; frame → `detail_frame_not_allowed`. id `tiktok:{video_id}:d{n}`, `author_of(v, place)`, `observed_at = upload_date(v)`. `run` ghi `"details"`.
- [x] **3.4 Kiểm:** `.venv/bin/python -m pytest -q tests/observe/tiktok` xanh.

## Task 4: Official: vé người già, khoản phí, giờ ngừng bán vé

**Đọc trước:** `src/corpus/observe/official/__init__.py`, `OFFICIAL_OBSERVE`, `tests/observe/test_official_observe.py`.

- [x] **4.1 Test (fail trước):** (a) `ticket` `audience: senior` được giữ, `place_facts.tickets_vnd.senior` có giá; (b) `kind: fee`, `item: "xe điện"`, `amount_vnd: 40000`, quote chứa cả hai → một phần tử `details` `detail.fee` (`source_type = official_page`, `author = official:<fid>`, `detail.unit` từ `unit`); fee mà `item` không có trong quote → bỏ `fee_item_not_in_quote`; (c) `kind: last_entry`, `open: "16:30"`, quote "ngừng bán vé lúc 16h30" → `place_facts.last_entry == "16:30"`; hai giờ khác nhau → `None`.
- [x] **4.2 `OFFICIAL_OBSERVE`**: `kind` enum thêm `fee`, `last_entry`; `audience` thêm `senior`; thêm `item` (string) và `unit` (enum person | group | vehicle | item | none), required. Prompt: vé người già / học sinh tách `senior` / `child`; khoản không phải vé vào cổng là `fee` với `item` = tên khoản chép từ text; `last_entry` = giờ ngừng bán vé / nhận khách cuối (`open`), không phải giờ đóng cửa.
- [x] **4.3 Gate / build**: ticket nhận `adult | child | senior`; `fee` cần `item` trong quote + `amount_in`; `last_entry` cần `TIME` + `hour_in`. `build()`: `tickets_vnd` thêm `senior`; `fee` → `details` (value = item, `detail` theo H3); `place_facts.last_entry`. `GATE_VERSION = "official_gate@v3"`.
- [x] **4.4 Kiểm:** `.venv/bin/python -m pytest -q tests/observe/test_official_observe.py` xanh.

## Task 5: Judge audit + nhãn cho `detail`

**Đọc trước:** `src/corpus/review/labels.py` (`_rows`, `stats`), `src/corpus/judge/audit.py` (`load_rows`, `select`, `risky`, `render`, `claim_text`), `tests/review/test_review.py`, `tests/judge/test_judge.py`.

- [x] **5.1 Test (fail trước):** file observation giả có 3 `details` `detail.order` (giá trị khác nhau) + nhãn Judge `correct`, `correct`, `wrong` → `label_stats()` có một dòng `("detail.order", "*")` với `correct 2, wrong 1, observations 3`. `audit.load_rows` trả cả `details`; `select` với kind `audit: full` (`detail.fee`) lấy hết, kind `sampled` lấy mẫu theo tầng `(feature, "*", source)`. `render` của item detail in câu claim `"nơi này nổi tiếng vì: <text>"`; `fit` điền `{who}` / `{verdict}` từ `detail`.
- [x] **5.2 `labels.py`**: `_rows` đọc thêm `doc.get("details") or []` (lọc `ont.valid_detail`); `stats()` gộp khóa `(feature, "*")` cho feature `detail.*` ở cả `pool` lẫn `got`.
- [x] **5.3 `audit.py`**: `load_rows` thêm details; `select`: tầng dùng `"*"` cho detail; `risky(feat)` → với detail dùng `kind.audit == "full"`; `render` / `strong` dùng `ont.as_feature(fid)`; `claim_text` cho detail = `kind.claim.format(text=value, who=..., verdict=...)`.
- [x] **5.4 Kiểm:** `.venv/bin/python -m pytest -q tests/review tests/judge` xanh.

## Task 6: Aggregate `details` (chỉ code)

**Đọc trước:** `src/corpus/aggregate/place.py` (`_who`, `usable`, `AUTHORITATIVE`, `owner`, `aggregate_place`), `estimates.py` (`amounts_vnd`), `tests/aggregate/test_aggregate.py` (helper `o`, `f`).

- [x] **6.1 Test (fail trước)** `tests/aggregate/test_aggregate_details.py`:
  - "bánh căn trứng" (a), "Bánh căn trứng ngon" (b), "bánh căn" (c) gộp một cụm `n == 3`, `text == "bánh căn trứng"` (dạng nhiều nhất); "mì Ý" (a) là cụm khác `n == 1`.
  - cùng tác giả nói hai lần → `n == 1`; nhãn `wrong` bị bỏ; mẫu `extremes` bị bỏ cho `known_for` (`targeted: false`), giữ cho `fee`.
  - `fee` official một mình → cụm `authority == True`.
  - `fee` "xe điện" 40k (a), 50k (b) → `amount_vnd == 45000` (trung vị, mỗi tác giả một số).
  - `fit` who `pet`: verdict `conditional` (a, "phải rọ mõm"), `bad` (b, "không cho chó vào") → hai cụm, cùng `who == "pet"`, `verdicts` đúng.
  - `best_time` có `time_of_day: early_morning` (a, b) → `time_of_day == {"early_morning": 2}`; `months` [11] (a) → `{11: 1}`.
  - `aggregate_place` có `details` và `operation.tickets_vnd` / `operation.last_entry` từ file official.
- [x] **6.2 `src/corpus/aggregate/details.py`**: `tokens(text, stopwords) -> frozenset` (NFC, casefold, bỏ số tiền bằng `estimates._VND`, bỏ dấu câu, bỏ stopword của `config/serving.yaml details.stopwords`); `cluster(items, jaccard) -> list[list[dict]]` (leader tất định: sắp theo số tác giả của đúng chữ đó giảm dần rồi theo chữ; gộp khi Jaccard ≥ ngưỡng hoặc tập này chứa tập kia, không rỗng; so với leader, không nối chuỗi; `fit` gom theo `who` trước); `place_details(files, ont, verdicts, cfg) -> dict[str, list[Cluster]]` lọc giống `usable` (nhãn `wrong` / `unsure_again`; mẫu có chủ đích chỉ khi `kind.targeted`; nguồn owner chỉ khi `kind.owner`), rồi dựng `Cluster` H4.
- [x] **6.3 `place.py`**: `aggregate_place` thêm `"details": place_details(...)`; `operation` thêm `tickets_vnd` = `official.get("tickets_vnd")`, `last_entry` = `official.get("last_entry")`. Đọc `serving.yaml` qua một hàm nhỏ trong `details.py` (không import `corpus.serving` từ aggregate).
- [x] **6.4 Kiểm:** `.venv/bin/python -m pytest -q tests/aggregate` xanh.

## Task 7: Serving `details`

**Đọc trước:** `src/corpus/serving/record.py`, `run.py`, `groups.py` (`areas`, `near_duplicate_groups`), `tests/serving/test_serving.py`.

- [x] **7.1 Test (fail trước)** `tests/serving/test_serving_details.py` (dựng intel giả):
  - cụm `n == 1` không có trong serving; `n == 2` có, `status` `UNCERTAIN` (`unmeasured_precision`) khi chưa có nhãn, `VERIFIED` khi `quality[("detail.order", "*")]["gate"]`; kind có ≥ 30 nhãn mà không qua gate → không phục vụ.
  - `known_for`: quán A {"xích đu nhìn hồ" n3, "view đồi" n4}, quán B, C cùng nhóm đều có "view đồi" → headline của A là "xích đu nhìn hồ"; nơi không cụm nào đạt → `headline is None`.
  - `cost`: official adult 50000 + cụm gửi xe 10000 + xe điện 40000 → `total_vnd == {"base": 60000, "with_extras": 100000}`, `kind == "estimate"` (gửi xe từ review); "jeep 1.200.000/xe" `unit vehicle` nằm ở `per_party`, không cộng vào `with_extras`; không vé người lớn và `entry_fee` không `free` → `total_vnd is None`.
  - `timing`: `best_months` chỉ gồm tháng có ≥ 2 tác giả hoặc khớp `seasons.yaml` (test truyền seasons giả); `last_entry` official thắng review.
  - `fit`: `bad` của `baby` từ 1 tác giả không phục vụ; 2 tác giả → `value == "bad"`; `feature(record, "fit.baby")` trả `{"value": "bad", ...}` và `check(record, "fit.baby", "bad") == "fail"`.
  - `relations`: A, B cùng `near_duplicate_group`, B nhiều `voices` hơn và tỷ lệ `crowd = high` cao hơn → `A.quieter == []`, `A.busier == [B]`, `B.quieter == [A]`; hai tín hiệu ngược chiều → rỗng.
  - `walk_to_night_market_min`: nơi cách chợ đêm 400 m → `round(400 * 1.3 / 80) == 7`; 3 km → `None`.
- [x] **7.2 `src/corpus/serving/details.py`**: `item(cluster, kind, quality, cfg) -> dict | None`; `place_block(intel, quality, cfg) -> dict` (mọi khối H5 trừ phần cần cả thành phố; giữ `known_for` ứng viên ở khóa tạm `_known_for`); `finish(records, cfg, seasons) -> None` (known_for theo độ hiếm: `score = n * log(N_group / (1 + số nơi cùng category_group có cụm trùng))`, xóa `_known_for`; `relations` dùng `provenance.voices` + phân phối `crowd`; `walk_to_night_market_min` từ tọa độ bản ghi `night_market_fid`, không có bản ghi đó → mọi nơi `None`). Phân loại `fee`: gửi xe = regex `gửi xe|giữ xe|đậu xe|đỗ xe|bãi xe|parking`; vé = `estimates.TICKET` và không `estimates.NOT_TICKET`; còn lại `extras` (unit person / item / null) hoặc `per_party` (group / vehicle).
- [x] **7.3 `record.py`**: `build(intel, built, judged, quality=None)` thêm `"details": place_block(...)`; `feature(record, fid)`: `fid` bắt đầu `fit.` → đọc `details.fit`. **`run.py`**: truyền quality (đọc `label_stats()` như `aggregate.run`), gọi `finish(records, cfg, seasons)` sau `near_duplicate_groups`; summary thêm số nơi có `known_for.headline`, `cost.total_vnd`, `timing.best_time.items`, `fit`.
- [x] **7.4 Kiểm:** `.venv/bin/python -m pytest -q tests/serving tests/aggregate` xanh.

## Task 8: Trip + Place Decision

**Đọc trước:** `src/requirements/checks.py` (`hard_result`, `applicable`), `src/trip/domain/{state,values,questions,prepass,guard,compile}.py`, `src/decision/{fit,cards,compare,feasibility,screen}.py`, `config/trip.yaml`, `config/decision.yaml`, test tương ứng trong `tests/trip`, `tests/decision`.

- [x] **8.1 Test (fail trước):**
  - `hard_result(rec, {"feature": "fit.baby", "op": "ne", "value": "bad"})`: `fail` khi `details.fit.baby` `bad` `VERIFIED`; `unknown` khi không có; `pass` khi `good` `VERIFIED` không ai nói `bad`. `{"feature": "pets", ...}` chạy như feature thường.
  - Trip: chip `baby` ghi `companions` có `baby` + hard `fit.baby ne bad`; chip `pet` ghi `pet` + hard `pets ne not_allowed`; chip `parents` thêm hard `fit.parents ne bad`; chip care `pregnant` / `wheelchair` thêm hard `fit.pregnant` / `fit.wheelchair`; prepass "đi với con chó" → `pet`; x ngoài danh sách ("hàng xóm") giữ ở `companions_other`.
  - compile: `mobility car`, `people 10` → có hard `coach_access ne no`; `people 4` → không.
  - Decision `fit`: `companions` có `kids` + bản ghi `kids_play_area present` → điểm cao hơn bản ghi không có; `details.fit.friends` `bad` → flag kèm lý do, điểm thấp hơn.
  - `cards` / `compare` có `known_for.headline.text` và `cost.total_vnd`; `feasibility._cost_vnd` dùng `total_vnd.base` khi có.
- [x] **8.2 `checks.py`**: dòng tra `ontology().features[fid].group` chỉ chạy khi `fid in ontology().features`; `applicable()` không lỗi với `fit.*`.
- [x] **8.3 Trip**: `values.ENUM_VALUES["companions"]` và `Who` thêm `baby`, `pet`, `coworkers`; field `companions_other: tuple[str, ...]` (thêm vào Search Input `Context`); `WHO` chip mới + hard draft H6; `care_q` thêm hard draft `fit.pregnant` / `fit.wheelchair`; `prepass` / `guard` (`GROUP_WORDS`, `GROUP_LABEL`) thêm từ của `config/companions.yaml` cho 3 id mới; `compile.py` thêm hard `coach_access` theo `config/trip.yaml coach_min_people: 9`.
- [x] **8.4 Decision**: `fit.py` thêm điểm mềm `config/decision.yaml details_fit: {good_bonus, bad_penalty}` cho mỗi x của chuyến (`companions` ∪ signal `pregnant` / `wheelchair` ∪ `large_group` khi `people ≥ coach_min_people`) và cộng theo feature (`kids` / `baby` → `kids_play_area present`, `stroller_access yes`; `parents` → `rest_benches present`, `toilet_available yes`). `cards.py`, `compare.py`, `feasibility.py` như test.
- [x] **8.5 Kiểm:** `.venv/bin/python -m pytest -q tests/trip tests/decision` xanh; `python -m decision evaluate` không tụt (chạy cuối Task 11 với dữ liệu thật; ở đây chỉ chạy được nếu `data/serving` có sẵn — báo kết quả, không sửa ngưỡng).

## Task 9: Planning

**Đọc trước:** `src/planning/{places,objectives,composer,conditions,timefit,backup,output}.py`, `config/planning.yaml`, `tests/planning`.

- [x] **9.1 Test (fail trước):**
  - `cost_of`: bản ghi có `details.cost.total_vnd.base = 60000` → 60000; thêm `per_party` "jeep 1.200.000/xe" khi chuyến `people = 1` → cộng 1.200.000; `people = 4` → cộng 300.000; không có `details.cost` → công thức cũ.
  - metrics có `extras_max_vnd` = Σ `with_extras - base`.
  - điểm giờ: mục bắt đầu trong buổi `best_time` có điểm cao hơn cùng mục ở buổi `avoid_time`.
  - `last_entry` official 16:00 → lịch không xếp bắt đầu sau 16:00; review → được xếp nhưng có cảnh báo.
  - xe máy + `night_road_risk present` + kết thúc sau hoàng hôn → cảnh báo + điểm thấp hơn.
  - tháng chuyến ∈ `avoid_months` → cảnh báo; ngày `crowd = peak` → nơi trong `relations.quieter` được ưu tiên làm dự phòng.
  - output: checklist chuẩn bị gồm `bring`, `booking`, `scam_stage`, `cold`, `fog_blocks_view` (khi dự báo sương mù), `schedule` khi ngày chuyến trùng thứ.
- [x] **9.2 Code** theo bảng spec §3.1; trọng số mới trong `config/planning.yaml` (`timing_bonus`, `timing_penalty`, `night_road_penalty`). Không có dữ liệu → hành vi cũ (test cũ phải xanh).
- [x] **9.3 Kiểm:** `.venv/bin/python -m pytest -q tests/planning` xanh.

## Task 10: Web

**Đọc trước:** `web/scripts/export_snapshot.py`, `web/src/user/ui/PlaceSheet.tsx`, `web/src/user/store.ts` (`PlaceInfo`), `docs/Role_Web_Functional_Design.md` §6, memory UI: **thiết kế bằng `/ui-ux-pro-max` trước khi code; màu chỉ từ token; chỉ desktop; không build vào `web/dist`** (prod chạy từ đó).

- [x] **10.1** `export_snapshot.py` xuất `details` + feature mới (giữ kích thước: ≤ 5 item mỗi khối, bỏ `evidence` trừ id cần mở quote).
- [x] **10.2** Dùng `/ui-ux-pro-max` thiết kế tab Tổng quan: "Nổi tiếng vì …" dưới tên (kèm "N người nhắc"); Tổng tiền (vé người lớn / trẻ em / người già, gửi xe, từng khoản, "tổng khoảng X–Y", giá theo xe / nhóm); Gọi món gì / Làm gì; Giờ & mùa đẹp; Đường đi; Trời xấu; Đi cùng ai (mọi x có dữ liệu + lý do, x của chuyến lên đầu, "Một mình" là một dòng); Chuẩn bị; Cảnh báo (khâu bị chặt); Nơi tương tự (vắng hơn / đông hơn, mở nơi đó). Thiếu → "Chưa có thông tin". Mỗi dòng xem được quote.
- [x] **10.3** Tab Gợi ý lịch trình + thẻ lịch trình: checklist chuẩn bị, cảnh báo tháng / giờ, `extras_max_vnd`.
- [ ] **10.4 Kiểm:** `cd web && npx tsc --noEmit` không thêm lỗi mới (lỗi sẵn ở `src/user/landing/*` của session khác thì bỏ qua); chụp `node web/scripts/shots_sheet.mjs <base> <journey>` trên Vite dev, xem ảnh.

## Task 11: Chạy thật + tài liệu

Cần mạng UIT / LAN Gemma (`docs/LLM_PROVIDER.md`); làm trên server theo memory "crawl server ops" (venv, cache, log trong repo; không giết process của session khác).

- [x] **11.1 Baseline:** `python -m decision evaluate` và `python -m planning evaluate` trên dữ liệu hiện tại, lưu số vào `logs/place_details_baseline.txt`.
- [x] **11.2** `python -m corpus gmaps keywords --city dalat` (chỉ tìm từ mới) → `python -m corpus official observe` (trang đổi gate).
- [ ] **11.3** Tạm dừng lane TikTok của Gemma (memory "Photo ranking on Gemma"), tắt `OBSERVE_KEEP_STALE`, chạy `python -m corpus build --city dalat`. Đo thời gian một lô trước khi để chạy cả thành phố; theo dõi `observe_summary.json` `dropped.detail_text_not_in_quote` — cao (> 30% số detail) thì dừng, sửa prompt Task 2.
- [ ] **11.4** `python -m corpus judge audit` → xem `label_stats` dòng `detail.*`; `aggregate` → `serving` → `web/scripts/export_snapshot.py`.
- [ ] **11.5 Báo cáo coverage** (in ra, không ghi vào tài liệu chính thức): số nơi có `known_for.headline`, `cost.total_vnd`, `timing`, từng feature mới, `fit` theo từng x, precision từng kind. Mục coverage thấp → đề xuất thêm nguồn, không bỏ mục.
- [ ] **11.6** Chạy lại evaluate, so với baseline; tụt thì báo, không sửa ngưỡng cho pass.
- [x] **11.7 Tài liệu** (tiếng Việt, mô tả đúng code hiện tại, không ghi lịch sử): `docs/CORPUS.md` (§Bản ghi địa điểm, §Data model observation `detail`, §4 Observe, §5 Aggregate + serving `details`, §Nguồn), `docs/PLACE_DECISION.md` (hard filter `fit.*`, `pets`, `coach_access`; điểm `details_fit`), `docs/PLANNING.md` (chi phí thật, giờ đẹp / tránh, `last_entry`, checklist), `docs/TRIP_UNDERSTANDING.md` (người đi cùng mở), `docs/Role_Web_Functional_Design.md` §6. Thêm một mục vào `docs/log/DEV_LOG.md` theo khuôn của nó.
- [ ] **11.8** Xóa `docs/superpowers/specs/2026-10-12-place-details-design.md` và file plan này (`RULE.md` §0.1). Báo người dùng; không commit trừ khi được bảo.
