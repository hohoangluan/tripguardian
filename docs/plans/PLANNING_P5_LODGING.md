# Plan P5 — Chỗ ở live và chấm K × mục tiêu

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm `live/weather` (Open-Meteo + khí hậu theo tháng) và `live/lodging` (chỗ ở crawl live qua `corpus.crawl`), `src/planning/lodging.py` (vùng tìm → sàng → K ứng viên), và vòng `for lodging in K+1: for obj in objectives` bọc quanh `schedule_trip` để mỗi mục tiêu chọn chỗ ở tốt nhất cho chính nó — `python -m planning lodging <decision_output.json>` in ra 2–3 phương án, mỗi phương án kèm chỗ ở đã chọn, và một bảng so sánh chỗ ở ở cấp Plan Output.

**Architecture:** `planning.lodging.candidates()` dựng 1–2 tâm tìm từ các nơi đã xác nhận, gọi `lodging_fn` (mặc định `live.lodging_near`, chạy qua `corpus.crawl`'s public API), sàng tất định, cắt còn `lodging_k`. `build.prepare()` được thêm tham số `extra_nodes` để đưa toạ độ các ứng viên vào CÙNG một ma trận OSRM với `confirmed + entry/exit`; `build.with_home()` dựng lại các `Day`/`DayCtx` của một `Trip` đã có với một điểm neo khác (chỗ ở khác), tái dùng ma trận và cache thứ tự trong ngày — cache đó đổi khoá sang `(ngày, start_node, end_node, tập nơi)` để không lẫn thứ tự giữa các chỗ ở khác nhau. `variants.build_lodging_variants()` thử mọi tổ hợp (chỗ ở, mục tiêu) — K+1 ứng viên (gồm "không chỗ ở") × tối đa 3 mục tiêu — giữ tổ hợp tốt nhất cho mỗi mục tiêu, rồi dựng variant như P4 (đo, độ vững, dự phòng) cộng thêm chi phí phòng vào `cost_vnd`. Thời tiết vẫn là tham số `weather` của `prepare()` đúng hình dạng P4 đã chốt; P5 chỉ đổ `live.weather(...)` vào đó trước khi gọi. Không random, không gọi model.

**Tech Stack:** Python 3.12, stdlib, `pyyaml`, `pytest`; `corpus.crawl`'s Playwright qua public API (đã có sẵn, không dependency mới).

**Spec:** `docs/specs/PLANNING_SPEC.md` (§Live Context, §OSRM, §Chỗ ở (crawl live), §Thuật toán ⓐ ⓖ, §Chỗ ở không làm người dùng chờ, §Plan Output, bảng phase P5). Plan trước: `docs/plans/PLANNING_P4_VARIANTS.md` — **phải xong cả 9 task trước khi bắt đầu plan này** (plan này sửa `build.py`, `objectives.py`, `variants.py`, `__init__.py`, `__main__.py`, và các test P4 tạo ra). Đọc thêm `docs/plans/PLANNING_P1_LIVE_CONTEXT.md` cho quy ước của `src/live`.

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0). Chuỗi hiển thị cho người dùng tiếng Việt.
- Module chỉ giao tiếp qua public API (`__init__.py`). `planning` dùng: `live`, `corpus.serving`, `corpus.ontology`; không deep import; không import `decision`, `trip` (`RULE.md` §2; ép bởi `tests/planning/test_planning_boundaries.py`). `src/live` không import `corpus`, **trừ** `src/live/lodging/`, nơi nó gọi đúng ba tên public của `corpus.crawl` (`open_sessions`, `LoginRequired`, `maps_search`) — ngoại lệ này tự nó được một test ép ở Task 2 (`test_lodging_reaches_corpus_only_through_its_crawl_public_api`), và mọi file khác của `src/live` vẫn bị cấm như cũ.
- `src/planning` và `src/live` không ghi gì dưới `data/intel`, `data/serving`, `data/gmaps`, `data/tiktok`, `data/review`. Chỗ ở chỉ sống trong kết quả gọi và trong `data/live/lodging/` (cache theo request, TTL, `source` + `fetched_at`) — không bao giờ vào Place Intelligence (`PLANNING_SPEC.md` §Nguyên tắc 1).
- Mọi bước của `planning` tất định: không `random`, không đọc đồng hồ. `src/live` được phép không tất định (nó là nguồn sống) nhưng mọi giá trị mang `source` + `fetched_at`, và một nguồn không trả lời ném `Unavailable`, không bịa (`RULE.md` §3).
- Không thêm dependency vào `pyproject.toml`: `corpus.crawl` đã dùng Playwright, `src/live` qua `live/lodging` nay kéo theo nó khi `import live` — không phải dependency mới, nhưng từ P5 trở đi `import live` cũng nạp Playwright; ghi rõ trong "Khác với spec" dưới đây để không ai ngỡ ngàng.
- Thay đổi tối thiểu (`RULE.md` §4): `places.py`, `travel.py`, `frame.py`, `schedule.py`, `route.py`, `cluster.py`, `days.py`, `validate.py`, `traits.py`, `robustness.py`, `backup.py` của P3/P4 không đổi trong plan này. `decision`, `trip` không đổi.
- File test mới dưới `tests/planning/`, `tests/live/`, `tests/crawl/` theo tiền tố đã có của mỗi cây (`test_planning_`, không tiền tố riêng trong `tests/live` và `tests/crawl` — xem test hiện có); không tạo `__init__.py` dưới `tests/`.
- Chạy test: `python -m pytest -q` ở gốc repo.
- Giá tiền là VND; xác suất mưa 0..1; giờ là phút sau nửa đêm.

## Khác với spec (đã chốt, ghi để khỏi tranh luận lại)

| Spec nói | Plan này làm | Vì sao |
|---|---|---|
| `src/live` không import `corpus` (ranh giới module gốc) | Ngoại lệ đúng một chỗ: `src/live/lodging/maps.py` import `corpus.crawl` qua `__init__.py` của nó | Spec chính §Chỗ ở (crawl live) tự nói "Dùng lại code crawl đúng ranh giới... `src/live/lodging` gọi qua đó". Test biên giới cũ (`tests/live/test_boundaries.py`) viết trước khi điều này tồn tại; sửa nó là đi theo spec, không phải phá luật. |
| Maps crawl trả `price_per_night`, `amenities` qua "mặt lodging" | `gmaps/search.py` đọc `card.innerText` thô (đã có sẵn khung `div.Nv2PK`/`a.hfpxzc` từ search thường), rồi regex giá (`₫`) và một danh sách từ khoá tiện nghi cố định (`wifi`, `parking`, `breakfast`, `pool`) trong Python | Không biết chắc class CSS riêng của thẻ khách sạn (Maps có thể đổi, và không có phiên trình duyệt thật để dò ngay trong lúc viết plan này). Quét text thô trên khung thẻ đã được kiểm chứng (`a.closest('div.Nv2PK')`) là cách ít giả định nhất; kết quả gắn nhãn "ước lượng, kiểm lại khi đặt" đúng như spec đã dặn. Trước khi chạy thật: mở trình duyệt headed, in `card.innerText` của vài thẻ khách sạn, chỉnh `_PRICE` / `_AMENITY` nếu cách Maps viết khác giả định. |
| "đặt check-in = ngày đầu, check-out = ngày cuối, đặt trần giá bằng bộ lọc giá của Maps" | `live.lodging_near` nhận `check_in`, `check_out`, `price_max` nhưng mới dùng `price_max` để lọc kết quả ở phía client; ngày chưa được gửi lên Maps (chưa biết chọn đúng nút/ô ngày nào mà không dò trực tiếp) | Lọc giá phía client vẫn đúng ràng buộc (không v nào vượt trần lọt qua); thiếu ngày chỉ làm giá hiển thị là giá mặc định của Maps tại thời điểm crawl, vẫn đúng với nhãn "giá tham khảo" đã có. Ghi vào "Giới hạn đã biết" của spec. |
| ⓐ.1 "Thêm vùng quanh `entry_point` khi ngày đầu / cuối gấp" | Bỏ qua ở P5: chỉ 1–2 tâm từ trọng số các nơi đã chọn | Spec không định nghĩa "gấp" bằng số; thêm phán đoán tuỳ ý là bịa một ngưỡng không ai duyệt. Để lại cho vòng sau khi có số liệu thật. |
| Thời tiết vào qua `live.weather` trực tiếp trong `prepare()` | `prepare()` không đổi (giữ tham số `weather` là dữ liệu, như P4 đã chốt); `variants.build_lodging_variants()` tự gọi `live.weather(...)` rồi đổ kết quả vào tham số đó trước khi gọi `prepare()` | Đúng câu P4 để lại: "P5 chỉ việc đổ kết quả `live.weather` vào tham số này" — không đổi shape, không phải viết lại toàn bộ test P4 đã có cho `prepare()`. |
| Plan Output `lodging`: "đã chọn + ứng viên khác, mỗi cái: tổng phút di chuyển cả chuyến, giá, amenities" | Bảng so sánh ở cấp Plan Output đo theo lịch của mục tiêu `least_travel` (mục tiêu luôn được thử); mỗi `variant` còn có field `lodging` riêng (chỗ ở mục tiêu đó chọn, có thể khác nhau giữa các mục tiêu) | `least_travel` luôn có trong `objectives` nên không cần dựng thêm lịch chỉ để so sánh; dùng cùng một thước đo cho cả bảng so sánh là điều kiện để con số "−55 phút/ngày" có nghĩa. |
| "SSE event progress" | P5 chỉ định nghĩa hình dạng sự kiện (`planning.lodging.progress_event`, hàm thuần không mạng); chưa có transport SSE | Server + SSE là P6 (`engine.py server.py`). Định nghĩa trước hình dạng event để P6 chỉ cần nối ống, không phải thiết kế lại payload. |
| Task 6 trong các bản kiểm trước của plan này giả định `variants.build_variants` đúng y văn bản `PLANNING_P4_VARIANTS.md` | Đã đối chiếu lại với code P4 đã chạy thật (có 2 commit sửa sau khi plan P4 được viết) và chỉnh `build_lodging_variants` cho khớp: cảnh báo `weather_unknown` bật khi **bất kỳ** ngày nào thiếu dự báo (không phải khi *mọi* ngày đều thiếu); `itinerary`/`travel_load` dùng `[cx.day for cx in s.ctxs]` (không phải `trip.days`) vì `early_start` có thể dời giờ mở ngày; `no_valid_variant` có nhánh dự phòng nêu tên nơi qua `per_day[v.day]` khi vi phạm không gắn `place_id`; `weather_src` lọc `w and w.get("source")` và sort bằng khoá null-safe để không crash khi `fetched_at = None` | Plan luôn phải khớp code thật tại thời điểm nó được viết, không khớp bản plan trước — nếu không các task sau sẽ build trên một nền đã lỗi thời. |

## Review Focus

Năm lớp input spec hàm ý nhưng dễ bị bỏ; mỗi dòng đã có test ở task sở hữu code:

1. **Chuyến không có `base` / `entry_point` / `exit_point` nào** — mọi ngày không có điểm neo cố định, nên thêm một chỗ ở chỉ có thể làm NẶNG hơn (phải đi tới rồi về nó mỗi ngày), không bao giờ nhẹ hơn. Mong đợi: `least_travel` vẫn có thể chọn "không chỗ ở". → Task 6 (`test_without_any_anchor_point_the_no_lodging_option_wins_least_travel`).
2. **`lodging_fn` chết ở một trong hai tâm tìm** (khi nơi đã chọn tách thành 2 cụm xa) — mong đợi: vẫn trả về ứng viên của tâm còn sống, không hỏng cả lượt chấm. → Task 4 (`test_a_dead_lodging_source_at_one_centre_still_returns_what_the_other_found`).
3. **Ứng viên trùng id tới từ hai tâm tìm khác nhau** — mong đợi: khử trùng trước khi cắt còn `lodging_k`, không tính một chỗ ở hai lần. → Task 4 (`test_candidates_merges_two_centres_without_duplicates_and_passes_the_price_cap_through`).
4. **Giá `price_vnd = None`** (homestay ngoài OTA, spec §Chỗ ở) — mong đợi: không bị trần giá loại, không bị tính là 0 đồng khi cộng vào `cost_vnd`, hiện riêng ở `cost_unknown`. → Task 2 (`test_a_card_with_no_price_or_known_amenity_text_says_so_without_crashing`), Task 3 (`test_a_price_over_the_cap_is_dropped_but_an_unknown_price_is_kept`), Task 6 (`test_add_lodging_cost_merges_a_known_price_or_counts_it_unknown`).
5. **Ngày dự báo ngoài tầm 16 ngày của Open-Meteo** (chuyến xa ngày hôm nay) — mong đợi: rơi về `climate.yaml`, không gọi mạng cho ngày đó, không crash. → Task 1 (`test_a_date_past_the_horizon_comes_from_climate_and_touches_no_network`, `test_dates_on_both_sides_of_the_horizon_are_split`).

## Cấu trúc file

| File | Việc |
|---|---|
| `config/live.yaml` | thêm `open_meteo_url`, `lodging_query_limit` |
| `config/climate.yaml` | mới: khí hậu mưa theo tháng, nhập tay |
| `config/planning.yaml` | thêm `radius_km`, `lodging_k`, `lodging_share`, `min_reviews`, `split_min` |
| `src/live/weather/__init__.py` `open_meteo.py` `climate.py` | mới: dự báo trong tầm, khí hậu ngoài tầm |
| `src/corpus/crawl/__init__.py` | mới: public API `open_sessions`, `LoginRequired`, `maps_search` |
| `src/corpus/crawl/gmaps/search.py` | thêm `card.innerText` vào `FEED_JS`; `place_row` đọc giá / tiện nghi |
| `src/live/lodging/__init__.py` `maps.py` | mới: `lodging_near` qua `corpus.crawl`, cache, lọc trần giá |
| `src/planning/lodging.py` | mới: vùng tìm, sàng, cắt K, `progress_event` |
| `src/planning/build.py` | `prepare` thêm `extra_nodes`; `Trip` thêm `lodging_ids`; cache thứ tự đổi khoá; `with_home` mới |
| `src/planning/objectives.py` | `add_lodging_cost` mới |
| `src/planning/variants.py` | `build_lodging_variants`, `render_lodging_variants` mới |
| `src/planning/__init__.py` `__main__.py` | export + lệnh `lodging` |
| `tests/live/weather/...`, `tests/live/test_lodging.py`, `tests/crawl/gmaps/test_gmaps_search.py` (thêm), `tests/planning/test_planning_lodging.py`, `test_planning_lodging_variants.py`, `test_planning_lodging_golden.py` | test mới |

---

### Task 1: `live/weather` — Open-Meteo trong tầm, khí hậu ngoài tầm

**Files:**
- Create: `config/climate.yaml`
- Modify: `config/live.yaml` (thêm `open_meteo_url`), `src/live/settings.py` (thêm field), `src/live/__init__.py`
- Create: `src/live/weather/__init__.py`, `src/live/weather/open_meteo.py`, `src/live/weather/climate.py`
- Modify: `tests/live/test_boundaries.py` (`__all__` mong đợi)
- Test: `tests/live/test_weather.py`, `tests/live/fixtures/open_meteo.json` (không cần, dựng doc trực tiếp trong test)

**Interfaces:**
- Consumes: `live.cache.get/put`, `live.http.get_json/Unavailable`, `live.settings.Settings`.
- Produces:
  - `live.weather(lat, lng, dates: list[str], cfg, today_fn=date.today) -> dict[str, dict]` — mỗi ngày `{"rain_prob": 0..1 | None, "source": "open-meteo" | "climate", "fetched_at": str | None}`; ném `Unavailable` khi một ngày trong tầm dự báo không lấy được.
  - `live.weather.open_meteo.forecast(lat, lng, dates, cfg) -> dict`, `in_range(dates, today) -> list[str]`, `FORECAST_DAYS = 16`
  - `live.weather.climate.climate(dates, path=PATH) -> dict`

- [ ] **Step 1: Viết test**

Tạo `tests/live/test_weather.py`:

```python
from datetime import date

import pytest

from live import settings
from live.http import Unavailable
from live.weather import open_meteo
from live.weather import weather as weather_fn


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg():
    settings.load.cache_clear()
    c = settings.load(settings.PATH)
    yield c
    settings.load.cache_clear()


TODAY = lambda: date(2026, 10, 2)


def doc(dates, probs):
    return {"daily": {"time": dates, "precipitation_probability_max": probs}}


def test_a_date_within_the_horizon_is_fetched_from_open_meteo(cfg, monkeypatch):
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: doc(["2026-10-05"], [80]))
    out = weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)
    assert out["2026-10-05"]["rain_prob"] == 0.8
    assert out["2026-10-05"]["source"] == "open-meteo" and out["2026-10-05"]["fetched_at"]


def test_a_date_past_the_horizon_comes_from_climate_and_touches_no_network(cfg):
    out = weather_fn(11.94, 108.45, ["2027-06-15"], cfg, today_fn=TODAY)
    assert out["2027-06-15"]["source"] == "climate" and out["2027-06-15"]["fetched_at"] is None
    assert 0 <= out["2027-06-15"]["rain_prob"] <= 1


def test_dates_on_both_sides_of_the_horizon_are_split_and_only_the_near_one_calls_the_network(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(open_meteo, "get_json",
                        lambda url, ua, timeout: calls.append(url) or doc(["2026-10-05"], [10]))
    out = weather_fn(11.94, 108.45, ["2026-10-05", "2027-06-15"], cfg, today_fn=TODAY)
    assert len(calls) == 1 and set(out) == {"2026-10-05", "2027-06-15"}
    assert out["2026-10-05"]["source"] == "open-meteo" and out["2027-06-15"]["source"] == "climate"


def test_a_date_the_forecast_answer_does_not_cover_is_none_not_a_crash(cfg, monkeypatch):
    monkeypatch.setattr(open_meteo, "get_json", lambda url, ua, timeout: doc([], []))
    out = weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)
    assert out["2026-10-05"]["rain_prob"] is None and out["2026-10-05"]["source"] == "open-meteo"


def test_a_dead_source_is_unavailable_not_a_crash(cfg, monkeypatch):
    def dead(url, ua, timeout):
        raise Unavailable("open-meteo down")

    monkeypatch.setattr(open_meteo, "get_json", dead)
    with pytest.raises(Unavailable):
        weather_fn(11.94, 108.45, ["2026-10-05"], cfg, today_fn=TODAY)


def test_the_second_call_for_the_same_range_comes_from_the_cache(cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(open_meteo, "get_json",
                        lambda url, ua, timeout: calls.append(url) or doc(["2026-10-05", "2026-10-06"], [10, 20]))
    weather_fn(11.94, 108.45, ["2026-10-05", "2026-10-06"], cfg, today_fn=TODAY)
    weather_fn(11.94, 108.45, ["2026-10-05", "2026-10-06"], cfg, today_fn=TODAY)
    assert len(calls) == 1


def test_no_dates_needs_no_network(cfg):
    assert weather_fn(11.94, 108.45, [], cfg) == {}
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_weather.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.weather'`

- [ ] **Step 3: Viết config**

Tạo `config/climate.yaml`:

```yaml
# Đà Lạt's monthly rain probability (docs/specs/PLANNING_SPEC.md §Live Context), hand-entered like
# config/holidays.yaml: used only for a date beyond Open-Meteo's forecast horizon. A rough estimate to tune against
# local knowledge before the pilot, not a measurement.
rain_prob_by_month:
  1: 0.15
  2: 0.15
  3: 0.20
  4: 0.35
  5: 0.55
  6: 0.65
  7: 0.70
  8: 0.70
  9: 0.65
  10: 0.55
  11: 0.35
  12: 0.20
```

Trong `config/live.yaml`, ngay trước dòng `# Seconds. Roads change slowly, forecasts quickly, OTA prices daily.` thêm:

```yaml
# Open-Meteo: free, no key, daily forecast up to 16 days ahead; config/climate.yaml covers dates beyond that.
open_meteo_url: https://api.open-meteo.com/v1/forecast

```

Trong `src/live/settings.py`, class `Settings`, ngay sau dòng `    ttl_s: dict` thêm:

```python
    open_meteo_url: str
```

- [ ] **Step 4: Viết code**

Tạo `src/live/weather/open_meteo.py`:

```python
"""Open-Meteo daily forecast: rain probability for dates within its 16-day horizon."""

from datetime import date, timedelta

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import get_json
from ..settings import Settings

FORECAST_DAYS = 16


def in_range(dates: list[str], today: date) -> list[str]:
    last = (today + timedelta(days=FORECAST_DAYS - 1)).isoformat()
    return sorted(d for d in dates if today.isoformat() <= d <= last)


def forecast(lat: float, lng: float, dates: list[str], cfg: Settings) -> dict:
    """{"YYYY-MM-DD": {"rain_prob", "source": "open-meteo", "fetched_at"}}; dates must already be in_range."""
    if not dates:
        return {}
    start, end = min(dates), max(dates)
    payload = {"kind": "forecast", "lat": round(lat, 4), "lng": round(lng, 4), "start": start, "end": end}
    hit = cache_get("weather", payload, cfg.ttl_s["weather"])
    if hit is None:
        url = (f"{cfg.open_meteo_url}?latitude={lat:.4f}&longitude={lng:.4f}"
               f"&daily=precipitation_probability_max&timezone=Asia%2FBangkok&start_date={start}&end_date={end}")
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        daily = doc.get("daily") or {}
        by_date = dict(zip(daily.get("time", []), daily.get("precipitation_probability_max", [])))
        hit = cache_put("weather", payload, by_date, "open-meteo")
    by_date = hit["value"]
    return {d: {"rain_prob": by_date[d] / 100 if by_date.get(d) is not None else None,
               "source": hit["source"], "fetched_at": hit["fetched_at"]} for d in dates}
```

Tạo `src/live/weather/climate.py`:

```python
"""Monthly rain climate for dates beyond Open-Meteo's forecast horizon (config/climate.yaml, hand-entered)."""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "config" / "climate.yaml"


@cache
def _table(path: Path) -> dict[int, float]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {int(k): float(v) for k, v in (doc.get("rain_prob_by_month") or {}).items()}


def climate(dates: list[str], path: Path = PATH) -> dict:
    """{"YYYY-MM-DD": {"rain_prob", "source": "climate", "fetched_at": None}}; a month missing from the file is None."""
    table = _table(path)
    return {d: {"rain_prob": table.get(date.fromisoformat(d).month), "source": "climate", "fetched_at": None}
            for d in dates}
```

Tạo `src/live/weather/__init__.py`:

```python
"""Rain probability: Open-Meteo within its forecast horizon, config/climate.yaml beyond it."""

from datetime import date as _date

from ..settings import Settings
from .climate import climate
from .open_meteo import forecast, in_range

__all__ = ["weather"]


def weather(lat: float, lng: float, dates: list[str], cfg: Settings, today_fn=_date.today) -> dict:
    """{"YYYY-MM-DD": {"rain_prob": 0..1 | None, "source": "open-meteo" | "climate", "fetched_at"}}.

    May raise live.Unavailable when a date inside the forecast horizon cannot be fetched; dates beyond it never
    touch the network. An empty dates list needs neither.
    """
    if not dates:
        return {}
    near = in_range(dates, today_fn())
    far = sorted(set(dates) - set(near))
    out = forecast(lat, lng, near, cfg) if near else {}
    out.update(climate(far) if far else {})
    return out
```

Trong `src/live/__init__.py`, thêm import và `__all__`:

```python
from .weather import weather
```

(xen vào giữa `from .sun import sun_times` và dòng `__all__ = [...]`), và sửa `__all__` thành:

```python
__all__ = ["Settings", "Unavailable", "geocode", "holidays", "load_settings", "route_shape", "sun_times",
           "travel_matrix", "weather"]
```

Trong `tests/live/test_boundaries.py`, sửa `test_the_public_api_is_exactly_what_planning_may_use`:

```python
    assert set(live.__all__) == {"Settings", "Unavailable", "geocode", "holidays", "load_settings", "route_shape",
                                 "sun_times", "travel_matrix", "weather"}
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live -q`
Expected: PASS — 7 test mới, toàn bộ test `live` cũ vẫn xanh

- [ ] **Step 6: Commit**

```bash
git add config/climate.yaml config/live.yaml src/live/settings.py src/live/weather src/live/__init__.py tests/live/test_weather.py tests/live/test_boundaries.py
git commit -m "feat(live): rain probability from Open-Meteo, falling back to monthly climate"
```


### Task 2: `corpus.crawl` public API và giá / tiện nghi trên thẻ khách sạn

**Files:**
- Modify: `src/corpus/crawl/__init__.py`
- Modify: `src/corpus/crawl/gmaps/search.py` (`FEED_JS`, `place_row`, `parse_feed`'s docstring)
- Test: thêm vào `tests/crawl/gmaps/test_gmaps_search.py`

**Interfaces:**
- Consumes: không có (dùng lại code đã có).
- Produces:
  - `corpus.crawl.open_sessions`, `corpus.crawl.LoginRequired`, `corpus.crawl.maps_search` (= `gmaps.search.search`, chữ ký không đổi: `async def maps_search(ctx, query, limit, at) -> tuple[list[dict], bool, bool]`)
  - `gmaps.search.place_row(name, url, info="", stars="", card_text="") -> dict | None` — thêm khoá `"price_vnd"`, `"amenities"`
  - `gmaps.search.price_vnd(card_text) -> int | None`, `amenities(card_text) -> list[str]`

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/crawl/gmaps/test_gmaps_search.py`:

```python


def test_a_hotel_card_with_a_price_and_known_amenities_is_read_by_place_row():
    url = "https://www.google.com/maps/place/A/@11.9,108.4,17z/data=!4m6!3m5!1s0x1a2b:0x3c4d!8m2!3d11.94!4d108.45"
    row = search.place_row("Khách sạn A", url, "Khách sạn", "4,2 sao 80 bài đánh giá",
                           "Khách sạn A\n4,2 · 80 bài đánh giá\n696.263 ₫ / đêm\nBãi đỗ xe miễn phí · Wi-Fi miễn phí")
    assert row["price_vnd"] == 696263 and set(row["amenities"]) == {"parking", "wifi"}


def test_a_card_with_no_price_or_known_amenity_text_says_so_without_crashing():
    url = "https://www.google.com/maps/place/A/@11.9,108.4,17z/data=!4m6!3m5!1s0x1a2b:0x3c4d!8m2!3d11.94!4d108.45"
    row = search.place_row("Cafe", url, "Quán cà phê", "4,5 sao 10 bài đánh giá")
    assert row["price_vnd"] is None and row["amenities"] == []


def test_parse_feed_fixture_still_has_price_and_amenities_keys_even_when_empty():
    rows = parse_fixture("feed.html", search.parse_feed)
    assert all(r["price_vnd"] is None and r["amenities"] == [] for r in rows)  # a non-lodging search finds neither
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/crawl/gmaps/test_gmaps_search.py -q`
Expected: FAIL với `KeyError: 'price_vnd'` (2 test mới đầu) và 1 test cũ vẫn xanh

- [ ] **Step 3: Viết code**

Trong `src/corpus/crawl/gmaps/search.py`, dòng đầu docstring (dòng 3-4) sửa câu:

```text
cũ:  Writes only data/gmaps/search/<city>/<category>.jsonl, one line per tile: {at, query, tile, end, lodging, items:[{fid,
name, url, category, rating, reviews, lat, lng}]}, only places inside the area; ...
mới: Writes only data/gmaps/search/<city>/<category>.jsonl, one line per tile: {at, query, tile, end, lodging, items:[{fid,
name, url, category, rating, reviews, lat, lng, price_vnd, amenities}]}, only places inside the area; price_vnd and
amenities are read from the card's own text and are None / [] outside the lodging list; ...
```

Sửa `FEED_JS` (thêm `card.innerText` làm phần tử thứ năm):

```python
FEED_JS = """() => [...document.querySelectorAll('a.hfpxzc')].map(a => {
  const card = a.closest('div.Nv2PK') || a.parentElement;
  return [a.getAttribute('aria-label'), a.href, card.querySelector('div.W4Efsd > div.W4Efsd')?.innerText ?? '',
          [...card.querySelectorAll('[role="img"][aria-label]')].map(e => e.getAttribute('aria-label'))
            .find(l => /sao/.test(l)) ?? '', card.innerText];
})"""
```

Ngay trước `def place_row(`, thêm:

```python
_PRICE = re.compile(r"([\d][\d.]*)\s*₫")
# Best-effort: a candidate's card text against a fixed phrase list, not a guessed CSS class. Re-check against the
# live hotel list before trusting this — Maps may word or lay these out differently than assumed here.
_AMENITY = {"parking": re.compile(r"bãi đỗ xe|bãi đậu xe", re.I), "breakfast": re.compile(r"bữa sáng", re.I),
           "pool": re.compile(r"hồ bơi", re.I), "wifi": re.compile(r"wi-?fi", re.I)}


def price_vnd(card_text: str) -> int | None:
    m = _PRICE.search(card_text or "")
    return int(m.group(1).replace(".", "")) if m else None


def amenities(card_text: str) -> list[str]:
    return [a for a, pat in _AMENITY.items() if pat.search(card_text or "")]
```

Sửa `place_row` thành:

```python
def place_row(name: str, url: str, info: str = "", stars: str = "", card_text: str = "") -> dict | None:
    fid, ll = _FID.search(url), _LATLNG.search(url)
    if not fid:
        return None
    st = _STARS.search(unicodedata.normalize("NFC", stars or ""))
    return {"fid": fid.group(1), "name": _VISITED.sub("", unicodedata.normalize("NFC", name)).strip(), "url": url,
            "category": info.split("·")[0].strip() or None,
            "rating": float(st.group(1).replace(",", ".")) if st else None,
            "reviews": int(st.group(2).replace(".", "")) if st and st.group(2) else None,
            "lat": float(ll.group(1)) if ll else None, "lng": float(ll.group(2)) if ll else None,
            "price_vnd": price_vnd(card_text), "amenities": amenities(card_text)}
```

`parse_feed`'s `rows = [place_row(*r) for r in await page.evaluate(FEED_JS)]` không cần sửa (`*r` nay có 5 phần tử, khớp chữ ký mới); nhánh "exact match" của `parse_feed` gọi `place_row(name, url or page.url, category, f"{stars} {count}")` với 4 đối số, `card_text` mặc định `""` — giữ nguyên, không sửa.

Tạo `src/corpus/crawl/__init__.py` (ghi đè toàn bộ file, hiện chỉ có một dòng docstring):

```python
"""Raw data crawl: one module per source, plain files under DATA_DIR, nothing is ever deleted.

Public API for other packages (RULE.md §2): a caller outside src/corpus/crawl may use only these three names.
"""

from .common.browser import LoginRequired, open_sessions
from .gmaps.search import search as maps_search

__all__ = ["LoginRequired", "maps_search", "open_sessions"]
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/crawl/gmaps/test_gmaps_search.py -q`
Expected: PASS (toàn bộ file, 3 test mới cộng các test cũ)

Run: `python -m pytest tests/crawl -q`
Expected: PASS — không test cũ nào đỏ (các test khác fake nguyên hàm `search.search`, không chạm `place_row`/`FEED_JS`)

- [ ] **Step 5: Commit**

```bash
git add src/corpus/crawl/__init__.py src/corpus/crawl/gmaps/search.py tests/crawl/gmaps/test_gmaps_search.py
git commit -m "feat(crawl): a minimal public API, and price / amenities read from a card's own text"
```


### Task 3: `live/lodging` — chỗ ở qua `corpus.crawl`

**Files:**
- Modify: `config/live.yaml`, `src/live/settings.py`, `src/live/__init__.py`
- Create: `src/live/lodging/__init__.py`, `src/live/lodging/maps.py`
- Modify: `tests/live/test_boundaries.py` (ngoại lệ `corpus` cho `lodging/`, `__all__`)
- Test: `tests/live/test_lodging.py`

**Interfaces:**
- Consumes: `corpus.crawl.open_sessions/LoginRequired/maps_search` (Task 2), `live.cache`, `live.http.Unavailable`.
- Produces:
  - `live.lodging_near(center: tuple[float, float], radius_km: float, check_in: str | None, check_out: str | None, price_max: int | None, cfg) -> list[dict]` — mỗi phần tử `id`, `name`, `lat`, `lng`, `rating`, `reviews`, `price_vnd`, `amenities`, `source`, `fetched_at`; ném `Unavailable` khi Maps không chuyển sang mặt lodging hoặc cần đăng nhập.

- [ ] **Step 1: Viết test**

Tạo `tests/live/test_lodging.py`:

```python
from contextlib import asynccontextmanager

import pytest

from corpus.crawl import LoginRequired
from live import settings
from live.http import Unavailable
from live.lodging import maps


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg():
    settings.load.cache_clear()
    c = settings.load(settings.PATH)
    yield c
    settings.load.cache_clear()


class FakeCtx:
    async def close(self):
        pass


@asynccontextmanager
async def fake_sessions(headed=False):
    async def new_session():
        return FakeCtx()

    yield new_session


def rows(*price_amenity):
    return [{"fid": f"h{i}", "name": f"Homestay {i}", "lat": 11.94 + i * 0.001, "lng": 108.45, "rating": 4.5,
            "reviews": 20, "price_vnd": p, "amenities": a} for i, (p, a) in enumerate(price_amenity)]


@pytest.fixture
def search(monkeypatch):
    calls = []

    async def fake(ctx, query, limit, at):
        calls.append((query, limit, at))
        return rows((500000, ["wifi"]), (None, [])), True, True

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", fake)
    return calls


def test_candidates_carry_their_provenance(cfg, search):
    out = maps.lodging_near((11.94, 108.45), 3.0, "2026-12-12", "2026-12-14", None, cfg)
    assert {c["id"] for c in out} == {"h0", "h1"}
    assert out[0]["source"] == "gmaps" and out[0]["fetched_at"]


def test_a_price_over_the_cap_is_dropped_but_an_unknown_price_is_kept(cfg, search):
    out = maps.lodging_near((11.94, 108.45), 3.0, None, None, 400000, cfg)
    assert {c["id"] for c in out} == {"h1"}


def test_the_second_call_for_the_same_area_comes_from_the_cache(cfg, search):
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    assert len(search) == 1


def test_a_different_radius_is_a_different_cache_entry(cfg, search):
    maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
    maps.lodging_near((11.94, 108.45), 6.0, None, None, None, cfg)
    assert len(search) == 2


def test_maps_not_switching_to_its_hotel_list_is_unavailable(cfg, monkeypatch):
    async def not_lodging(ctx, query, limit, at):
        return [], True, False

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", not_lodging)
    with pytest.raises(Unavailable):
        maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)


def test_login_required_is_unavailable_not_a_crash(cfg, monkeypatch):
    async def blocked(ctx, query, limit, at):
        raise LoginRequired("gmaps")

    monkeypatch.setattr(maps, "open_sessions", fake_sessions)
    monkeypatch.setattr(maps, "maps_search", blocked)
    with pytest.raises(Unavailable):
        maps.lodging_near((11.94, 108.45), 3.0, None, None, None, cfg)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_lodging.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.lodging'`

- [ ] **Step 3: Viết config và code**

Trong `config/live.yaml`, ngay sau khối `open_meteo_url` vừa thêm ở Task 1, thêm:

```yaml
# Maps' hotel list ("Khách sạn"), queried through corpus.crawl's public API (PLANNING_SPEC.md §Chỗ ở).
lodging_query_limit: 40

```

Trong `src/live/settings.py`, class `Settings`, ngay sau dòng `    open_meteo_url: str` thêm:

```python
    lodging_query_limit: int
```

Tạo `src/live/lodging/maps.py`:

```python
"""Lodging candidates from Maps' hotel list, through corpus.crawl's public API (RULE.md §2: no deep import).

Maps' date and price filters are UI controls this does not drive yet (needs a live dry run to pin the right
clicks): every card is read as Maps shows it by default, and a price over price_max is dropped here instead.
"""

import asyncio

from corpus.crawl import LoginRequired, maps_search, open_sessions

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable
from ..settings import Settings

QUERY = "khách sạn"
ZOOM = 14  # the hotel list ignores the viewport (corpus.crawl.gmaps.search), so any reasonable zoom works


async def _fetch(center: tuple[float, float], limit: int) -> tuple[list[dict], bool]:
    async with open_sessions() as new_session:
        ctx = await new_session()
        try:
            rows, _end, is_lodging = await maps_search(ctx, QUERY, limit, (*center, ZOOM))
            return rows, is_lodging
        finally:
            await ctx.close()


def lodging_near(center: tuple[float, float], radius_km: float, check_in: str | None, check_out: str | None,
                 price_max: int | None, cfg: Settings) -> list[dict]:
    """[{"id", "name", "lat", "lng", "rating", "reviews", "price_vnd", "amenities", "source", "fetched_at"}].

    radius_km narrows nothing here (planning.lodging's sieve does the real distance cut); it only keeps a request
    for a different area from being wrongly served the cached one.
    """
    payload = {"center": [round(center[0], 4), round(center[1], 4)], "radius_km": radius_km,
              "check_in": check_in, "check_out": check_out}
    hit = cache_get("lodging", payload, cfg.ttl_s["lodging"])
    if hit is None:
        try:
            rows, is_lodging = asyncio.run(_fetch(center, cfg.lodging_query_limit))
        except LoginRequired as e:
            raise Unavailable(str(e)) from e
        if not is_lodging:
            raise Unavailable("maps did not switch to its hotel list")
        hit = cache_put("lodging", payload, [{"id": r["fid"], "name": r["name"], "lat": r["lat"], "lng": r["lng"],
                                              "rating": r["rating"], "reviews": r["reviews"],
                                              "price_vnd": r["price_vnd"], "amenities": r["amenities"]}
                                             for r in rows if r["lat"] is not None], "gmaps")
    return [{**r, "source": hit["source"], "fetched_at": hit["fetched_at"]} for r in hit["value"]
            if price_max is None or r["price_vnd"] is None or r["price_vnd"] <= price_max]
```

Tạo `src/live/lodging/__init__.py`:

```python
"""Lodging crawled live per request (docs/specs/PLANNING_SPEC.md §Chỗ ở). Never becomes Place Intelligence."""

from .maps import lodging_near

__all__ = ["lodging_near"]
```

Trong `src/live/__init__.py`, thêm `from .lodging import lodging_near` (ngay trên `from .weather import weather`), sửa `__all__`:

```python
__all__ = ["Settings", "Unavailable", "geocode", "holidays", "load_settings", "lodging_near", "route_shape",
           "sun_times", "travel_matrix", "weather"]
```

Trong `tests/live/test_boundaries.py`, sửa toàn bộ khối từ `OTHER_PACKAGES = ...` tới hết `test_no_module_imports_another_project_package`, và sửa `__all__` mong đợi:

```python
OTHER_PACKAGES = {"corpus", "decision", "trip", "planning"}
CORPUS_EXCEPTION = {"corpus"}  # live/lodging reuses corpus.crawl's public API (PLANNING_SPEC.md §Chỗ ở, P5)


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_imports_another_project_package(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    allowed = CORPUS_EXCEPTION if "lodging" in path.parts else set()
    bad = (imported & OTHER_PACKAGES) - allowed
    assert not bad, f"{path.name} imports {bad}"


def test_lodging_reaches_corpus_only_through_its_crawl_public_api():
    tree = ast.parse((SRC / "lodging" / "maps.py").read_text(encoding="utf-8"))
    modules_imported = {n.module for n in ast.walk(tree)
                        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    assert "corpus.crawl" in modules_imported
    assert not any(m.startswith("corpus.crawl.") for m in modules_imported)
```

và sửa `test_the_public_api_is_exactly_what_planning_may_use`:

```python
    assert set(live.__all__) == {"Settings", "Unavailable", "geocode", "holidays", "load_settings", "lodging_near",
                                 "route_shape", "sun_times", "travel_matrix", "weather"}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live -q`
Expected: PASS — 6 test mới của `test_lodging.py`, test biên giới vẫn xanh

- [ ] **Step 5: Commit**

```bash
git add config/live.yaml src/live/settings.py src/live/lodging src/live/__init__.py tests/live/test_lodging.py tests/live/test_boundaries.py
git commit -m "feat(live): lodging candidates from Maps' hotel list, through corpus.crawl"
```


### Task 4: `planning/lodging.py` — vùng tìm, sàng, cắt K

**Files:**
- Modify: `config/planning.yaml`, `src/planning/settings.py`
- Create: `src/planning/lodging.py`
- Test: `tests/planning/test_planning_lodging.py`

**Interfaces:**
- Consumes: `live.Unavailable`, `planning.places.Place`, `planning.travel.km`, `planning.settings.Settings`.
- Produces:
  - `planning.lodging.search_area(by_place, mobility, cfg) -> list[dict]` (mỗi phần tử `lat`, `lng`, `radius_km`; 1 hoặc 2 phần tử)
  - `price_cap(ctx, nights, cfg) -> int | None`
  - `sieve(raw, hard_filters, min_reviews) -> list[dict]`
  - `shortlist(cands, centres, k) -> list[dict]`
  - `candidates(by_place, decision, cfg, lodging_fn, live_cfg) -> list[dict]`

- [ ] **Step 1: Viết test**

Tạo `tests/planning/test_planning_lodging.py`:

```python
import pytest
from plan_fixtures import CFG, decision, rec

from live import Unavailable
from planning.lodging import candidates, price_cap, search_area, shortlist, sieve
from planning.places import build_places

CENTRE = (11.9404, 108.4583)


def place(r):
    (p,), _ = build_places(decision([r["id"]]), {r["id"]: r}, CFG)
    return p


def by(*recs):
    return {r["id"]: place(r) for r in recs}


def test_search_area_is_the_visit_weighted_centre_of_one_tight_cluster():
    a = by(rec("a", 11.94, 108.45, visit=(10, 10, 10)), rec("b", 11.941, 108.451, visit=(10, 100, 10)))
    [centre] = search_area(a, "motorbike", CFG)
    assert centre["lat"] == pytest.approx(11.9406, abs=1e-3)  # pulled toward b's longer typical visit
    assert centre["radius_km"] == CFG.radius_km["motorbike"]


def test_places_far_apart_split_into_two_centres():
    a = by(rec("a", 11.94, 108.45), rec("b", 11.941, 108.451), rec("c", 11.60, 108.10))
    assert len(search_area(a, "car", CFG)) == 2


def test_no_places_has_no_search_area():
    assert search_area({}, "car", CFG) == []


def test_price_cap_is_the_lodging_share_of_budget_over_the_nights_or_unknown():
    assert price_cap({"budget_vnd": 3_000_000}, 3, CFG) == round(3_000_000 * CFG.lodging_share / 3)
    assert price_cap({"budget_vnd": None}, 3, CFG) is None
    assert price_cap({"budget_vnd": 1_000_000}, 0, CFG) is None


def cand(i, reviews=10, price=None, amenities=()):
    return {"id": f"h{i}", "name": f"Homestay {i}", "lat": CENTRE[0] + i * 0.001, "lng": CENTRE[1], "rating": 4.5,
           "reviews": reviews, "price_vnd": price, "amenities": list(amenities)}


def test_sieve_drops_too_few_reviews_but_keeps_what_it_cannot_verify():
    raw = [cand(0, reviews=1), cand(1, reviews=20), cand(2, reviews=20, amenities=["parking"])]
    hard = [{"feature": "parking", "op": "ne", "value": "present"}]
    out = sieve(raw, hard, CFG.min_reviews)
    assert {c["id"] for c in out} == {"h1"}  # h0: too few reviews; h2: hard filter evidence against it


def test_shortlist_keeps_the_k_candidates_closest_to_any_centre():
    raw = [cand(i) for i in range(10)]
    centres = [{"lat": CENTRE[0], "lng": CENTRE[1], "radius_km": 3.0}]
    assert [c["id"] for c in shortlist(raw, centres, 3)] == ["h0", "h1", "h2"]


def test_candidates_merges_two_centres_without_duplicates_and_passes_the_price_cap_through():
    places = by(rec("a", *CENTRE), rec("b", 11.60, 108.10))
    seen = []

    def fake(center, radius_km, check_in, check_out, price_max, live_cfg):
        seen.append(price_max)
        return [cand(0), cand(1)]  # same ids from both centres: a duplicate to drop

    out = candidates(places, decision(["a", "b"], budget=3_000_000, days=3), CFG, fake, None)
    assert len(seen) == 2 and all(p == round(3_000_000 * CFG.lodging_share / 2) for p in seen)
    assert sorted(c["id"] for c in out) == ["h0", "h1"]


def test_a_dead_lodging_source_at_one_centre_still_returns_what_the_other_found():
    places = by(rec("a", *CENTRE), rec("b", 11.60, 108.10))

    def flaky(center, *a):
        if round(center[0], 2) == round(CENTRE[0], 2):
            raise Unavailable("blocked")
        return [cand(0)]

    out = candidates(places, decision(["a", "b"]), CFG, flaky, None)
    assert [c["id"] for c in out] == ["h0"]


def test_no_places_means_no_candidates():
    assert candidates({}, decision([]), CFG, lambda *a: pytest.fail("no call"), None) == []
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_lodging.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'planning.lodging'`

- [ ] **Step 3: Viết config và code**

Vào cuối `config/planning.yaml`, thêm:

```yaml

# Lodging (ⓐ, P5): a candidate competes as the anchor of each day; it never becomes Place Intelligence.
radius_km: {motorbike: 3.0, car: 5.0, ride: 4.0}
lodging_k: 6
lodging_share: 0.3  # share of budget_vnd spent on lodging, over the whole stay
min_reviews: 5
split_min: 20       # minutes of real travel diameter beyond which the search area splits into two centres
```

Trong `src/planning/settings.py`, class `Settings`, ngay sau dòng `    backups_per_place: int` thêm:

```python
    radius_km: dict
    lodging_k: int
    lodging_share: float
    min_reviews: int
    split_min: int
```

Tạo `src/planning/lodging.py`:

```python
"""Lodging candidates for the trip (docs/specs/PLANNING_SPEC.md ⓐ): search area, sieve, shortlist to K.

Candidates never become Place Intelligence: they live only in this call's result, each carrying source and
fetched_at. A sieve step with no amenity evidence keeps the candidate (unknown, not rejected); it never drops one
it cannot check.
"""

from datetime import date, timedelta

from live import Unavailable

from .places import Place
from .settings import Settings
from .travel import km


def search_area(by_place: dict[str, Place], mobility: str | None, cfg: Settings) -> list[dict]:
    """One centre weighted by typical visit length, or two when the places span wider than split_min of real
    travel (approximated here by straight-line distance at a city driving speed; the real matrix comes later)."""
    places = list(by_place.values())
    if not places:
        return []
    radius = cfg.radius_km.get(mobility or "motorbike", 3.0)

    def centroid(ps: list) -> dict:
        w = [p.visit.get("typical") or 1 for p in ps]
        return {"lat": sum(p.lat * x for p, x in zip(ps, w)) / sum(w),
               "lng": sum(p.lng * x for p, x in zip(ps, w)) / sum(w), "radius_km": radius}

    if len(places) < 2:
        return [centroid(places)]
    pairs = [(a, b) for a in places for b in places]
    a, b = max(pairs, key=lambda ab: km((ab[0].lat, ab[0].lng), (ab[1].lat, ab[1].lng)))
    if km((a.lat, a.lng), (b.lat, b.lng)) * 60 / 25 <= cfg.split_min:
        return [centroid(places)]
    near_a = [p for p in places if km((p.lat, p.lng), (a.lat, a.lng)) <= km((p.lat, p.lng), (b.lat, b.lng))]
    near_b = [p for p in places if p.id not in {x.id for x in near_a}]
    return [centroid(g) for g in (near_a, near_b) if g]


def price_cap(ctx: dict, nights: int, cfg: Settings) -> int | None:
    """lodging_share of the whole trip's budget, spread over the nights; unknown when the budget is unknown."""
    budget = ctx.get("budget_vnd")
    if budget is None or nights <= 0:
        return None
    return round(budget * cfg.lodging_share / nights)


def _evidence(cand: dict, feature: str) -> str | None:
    return "present" if feature in (cand.get("amenities") or []) else None


def sieve(raw: list[dict], hard_filters: list[dict], min_reviews: int) -> list[dict]:
    """A hard filter only rejects a candidate that has the evidence against it, never one with no evidence either
    way (that one is kept, unverified)."""
    out = []
    for c in raw:
        if (c.get("reviews") or 0) < min_reviews:
            continue
        if any(f["op"] == "ne" and _evidence(c, f["feature"]) == f["value"] for f in hard_filters):
            continue
        out.append(c)
    return out


def shortlist(cands: list[dict], centres: list[dict], k: int) -> list[dict]:
    """The k candidates closest (straight line) to whichever search centre is nearest them."""
    def dist(c: dict) -> float:
        return min(km((c["lat"], c["lng"]), (ct["lat"], ct["lng"])) for ct in centres)

    return sorted(cands, key=dist)[:k]


def candidates(by_place: dict[str, Place], decision: dict, cfg: Settings, lodging_fn, live_cfg) -> list[dict]:
    """[] on no places to anchor a search on, or when every centre's source was unavailable — never a reason to
    fail the whole plan: the "no lodging" option always stays alongside whatever this returns (ⓐ.5)."""
    tc = decision["trip_context"]["context"]
    centres = search_area(by_place, tc.get("mobility"), cfg)
    if not centres:
        return []
    nights = max((tc.get("days") or 1) - 1, 0)
    cap = price_cap(tc, nights, cfg)
    start = tc.get("start_date")
    check_out = ((date.fromisoformat(start) + timedelta(days=(tc.get("days") or 1) - 1)).isoformat()
                if start and tc.get("days") else None)
    hard_filters = decision["trip_context"].get("hard_filters") or []
    raw, seen = [], set()
    for ct in centres:
        try:
            found = lodging_fn((ct["lat"], ct["lng"]), ct["radius_km"], start, check_out, cap, live_cfg)
        except Unavailable:
            continue
        for c in found:
            if c["id"] not in seen:
                seen.add(c["id"])
                raw.append(c)
    return shortlist(sieve(raw, hard_filters, cfg.min_reviews), centres, cfg.lodging_k)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_lodging.py -q`
Expected: PASS (9 test)

- [ ] **Step 5: Commit**

```bash
git add config/planning.yaml src/planning/settings.py src/planning/lodging.py tests/planning/test_planning_lodging.py
git commit -m "feat(planning): a search area, a sieve and a shortlist of lodging candidates"
```


### Task 5: `build.prepare` nhận thêm nút, `with_home` đổi điểm neo

**Files:**
- Modify: `src/planning/build.py`
- Modify: `tests/planning/plan_fixtures.py` (`prepared`)
- Test: thêm vào `tests/planning/test_planning_prepare.py`

**Interfaces:**
- Consumes: mọi thứ P4's `build.py` đã có.
- Produces:
  - `Trip` thêm field `lodging_ids: tuple = ()`
  - `prepare(..., extra_nodes: dict[str, tuple[float, float]] | None = None) -> Trip` — toạ độ trong `extra_nodes` vào CÙNG ma trận OSRM, không trở thành `Place`
  - `with_home(trip: Trip, home_id: str | None) -> Trip` — cùng `travel`/`routes`, `days`/`ctxs` dựng lại với điểm neo khác
  - `schedule_trip`'s cache nội bộ đổi khoá sang `(ngày, start_node, end_node, tập nơi)`

- [ ] **Step 1: Thêm fixture và viết test**

Trong `tests/planning/plan_fixtures.py`, sửa `prepared`:

```python
def prepared(d, recs, weather=None, matrix=fake_matrix, extra_nodes=None):
    """build.prepare with every outside source replaced."""
    from planning.build import prepare
    return prepare(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=matrix, sun_fn=fixed_sun,
                   weather=weather, extra_nodes=extra_nodes)
```

Thêm vào cuối `tests/planning/test_planning_prepare.py`:

```python
from planning.build import with_home


def test_extra_nodes_join_the_one_travel_matrix_and_are_not_otherwise_placed():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (CENTRE[0] + 0.001, CENTRE[1])})
    assert "h1" in trip.travel.ids and "h1" not in trip.by_place
    assert trip.lodging_ids == ("h1",)


def test_with_home_changes_only_where_the_day_starts_and_ends():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (SOUTH[0], SOUTH[1])})
    swapped = with_home(trip, "h1")
    assert swapped.days[0].start_node == "h1" and trip.days[0].start_node != "h1"
    assert swapped.ctxs[0].rain == trip.ctxs[0].rain and swapped.travel is trip.travel


def test_order_is_cached_separately_per_home():
    d, recs = sample_trip()
    trip = prepared(d, recs, extra_nodes={"h1": (SOUTH[0], SOUTH[1])})
    schedule_trip(trip)
    n = len(trip.routes)
    schedule_trip(with_home(trip, "h1"))
    assert len(trip.routes) > n  # a different start node is a different cache key, not reused
```

(`CENTRE`, `SOUTH`, `sample_trip`, `prepared` đã có từ `plan_fixtures.py`; import `schedule_trip` nếu file chưa import — thêm `from planning.build import schedule_trip` nếu dòng import đầu file chưa có.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_prepare.py -q`
Expected: FAIL — `prepare() got an unexpected keyword argument 'extra_nodes'` và `ImportError: cannot import name 'with_home'`

- [ ] **Step 3: Viết code**

Trong `src/planning/build.py`, class `Trip`, ngay sau dòng `    weather: dict | None` thêm:

```python
    lodging_ids: tuple = ()         # ids of the extra nodes added to the matrix as lodging candidates (P5)
```

Chữ ký `prepare`:

```python
def prepare(decision: dict, records: list[dict], cfg: Settings | None = None, live_cfg=None, geocode_fn=None,
           matrix_fn=None, sun_fn=None, weather: dict | None = None, extra_nodes: dict | None = None) -> Trip:
```

Khối dựng `nodes`/`travel`:

```python
    nodes = {p.id: (p.lat, p.lng) for p in placed}
    nodes.update({n: (pt.lat, pt.lng) for n, pt in points.items() if pt})
    nodes.update(extra_nodes or {})
    travel = build_travel(nodes, mobility, cfg, live_cfg, matrix_fn)
```

Dòng `return Trip(...)` ở cuối `prepare`:

```python
    return Trip(decision, cfg, pace, by_place, unplaced, by_id, points, travel, days, ctxs, warnings, weather,
               lodging_ids=tuple(extra_nodes or {}))
```

Trong `schedule_trip`, dòng khoá cache:

```python
        key = (cx.day.index, tuple(sorted(day_ids)))
```

thành:

```python
        key = (cx.day.index, cx.day.start_node, cx.day.end_node, tuple(sorted(day_ids)))
```

Ngay sau hết thân `schedule_trip` (trước `def itinerary(`), thêm:

```python
def with_home(trip: Trip, home_id: str | None) -> Trip:
    """The same trip anchored at a different place to sleep (a lodging candidate, or None for the original base):
    same places, same travel matrix, same per-day sun / rain / preference — only where each day starts and ends
    changes, so the day-order cache (now keyed on the start and end node too) still pays off across candidates."""
    ctx = trip.decision["trip_context"]["context"]
    entry = ENTRY if trip.points.get(ENTRY) else None
    exit_ = EXIT if trip.points.get(EXIT) else None
    days = trip_days(ctx, trip.cfg, home_id, entry, exit_)
    ctxs = [replace(cx, day=d) for cx, d in zip(trip.ctxs, days)]
    return replace(trip, days=days, ctxs=ctxs)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning -q`
Expected: PASS — 3 test mới, toàn bộ test P3/P4 vẫn xanh (đầu ra `build_plan` không đổi: không có lời gọi nào truyền `extra_nodes`)

- [ ] **Step 5: Commit**

```bash
git add src/planning/build.py tests/planning/plan_fixtures.py tests/planning/test_planning_prepare.py
git commit -m "feat(planning): a trip's matrix can hold extra nodes, and its home can be swapped"
```


### Task 6: `objectives.add_lodging_cost` và `variants.build_lodging_variants`

**Files:**
- Modify: `src/planning/objectives.py`, `src/planning/variants.py`
- Test: thêm vào `tests/planning/test_planning_objectives.py`; Create: `tests/planning/test_planning_lodging_variants.py`

**Interfaces:**
- Consumes: `planning.build.{prepare, schedule_trip, with_home, itinerary, travel_load, shared_output, flag_warnings}`, `planning.lodging.candidates`, `planning.objectives.{choose, metrics, score, LABEL}`, `planning.robustness.robustness`, `planning.backup.backups`.
- Produces:
  - `planning.objectives.add_lodging_cost(m: dict, price_vnd: int | None, nights: int) -> dict`
  - `planning.variants.build_lodging_variants(decision, records, cfg=None, live_cfg=None, geocode_fn=None, matrix_fn=None, sun_fn=None, weather=None, lodging_fn=None) -> dict` — như `build_variants` cộng thêm `lodging: {"candidates": [...], "chosen": None} | None`; mỗi `variant` thêm field `lodging: {"id", "name", "price_vnd"}`

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_objectives.py` (và thêm `add_lodging_cost` vào dòng import đầu file):

```python
from planning.objectives import LABEL, add_lodging_cost, choose, metrics, score


def test_add_lodging_cost_merges_a_known_price_or_counts_it_unknown():
    m = {"cost_vnd": 100000, "cost_unknown": 1}
    assert add_lodging_cost(m, 50000, 3)["cost_vnd"] == 250000
    assert add_lodging_cost(m, None, 3)["cost_unknown"] == 2
```

Tạo `tests/planning/test_planning_lodging_variants.py`:

```python
from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip

from live import Unavailable
from planning.variants import build_lodging_variants


def hit(i, price=None, lat=None, lng=None):
    return {"id": f"h{i}", "name": f"Homestay {i}", "lat": lat if lat is not None else SOUTH[0] + i * 0.001,
           "lng": lng if lng is not None else SOUTH[1], "rating": 4.5, "reviews": 20, "price_vnd": price,
           "amenities": []}


def fake_lodging(hits):
    return lambda center, radius_km, check_in, check_out, price_max, live_cfg: hits


def run(d, recs, lodging_fn, weather=None):
    return build_lodging_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                                  sun_fn=fixed_sun, weather=weather, lodging_fn=lodging_fn)


def test_without_any_anchor_point_the_no_lodging_option_wins_least_travel():
    d, recs = sample_trip()  # no base / entry / exit: days already start and end nowhere
    out = run(d, recs, fake_lodging([hit(0)]))
    lt = next(v for v in out["variants"] if v["objective"] == "least_travel")
    assert lt["lodging"]["id"] is None
    assert any(r["id"] is None for r in out["lodging"]["candidates"])
    assert any(r["id"] == "h0" for r in out["lodging"]["candidates"])


def test_a_dead_lodging_source_still_gives_the_no_lodging_variant():
    d, recs = sample_trip()
    out = run(d, recs, lambda *a: (_ for _ in ()).throw(Unavailable("blocked")))
    assert out["ok"] and all(r["id"] is None for r in out["lodging"]["candidates"])
    assert "lodging_unavailable" in {w["code"] for w in out["warnings"]}


def test_low_cost_never_prefers_the_pricier_candidate_when_travel_time_is_tied():
    d, recs = sample_trip(budget=3_000_000, days=3)
    cheap = hit(0, price=200_000, lat=SOUTH[0], lng=SOUTH[1])
    pricey = hit(1, price=2_000_000, lat=SOUTH[0], lng=SOUTH[1])
    out = run(d, recs, fake_lodging([cheap, pricey]))
    low_cost = next(v for v in out["variants"] if v["objective"] == "low_cost")
    assert low_cost["lodging"]["id"] != "h1"  # the pricier of the two (the no-lodging baseline may legitimately win)


def test_the_same_input_gives_the_same_output():
    d, recs = sample_trip()
    a = run(d, recs, fake_lodging([hit(0), hit(1)]))
    b = run(d, recs, fake_lodging([hit(0), hit(1)]))
    assert a == b


def test_no_valid_schedule_for_any_lodging_goes_back_to_place_decision():
    d, recs = sample_trip()
    d["confirmed"].append({"id": "gone", "name": "Gone", "role": "anchor", "flags": [], "relaxed": []})
    out = run(d, recs, fake_lodging([hit(0)]))
    assert not out["ok"] and out["lodging"] is None and out["back_to_decision"]["places"] == ["gone"]
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_objectives.py tests/planning/test_planning_lodging_variants.py -q`
Expected: FAIL — `ImportError: cannot import name 'add_lodging_cost'`, rồi (sau khi sửa `objectives.py`) `ImportError: cannot import name 'build_lodging_variants'`

- [ ] **Step 3: Viết code**

Vào cuối `src/planning/objectives.py`, thêm:

```python


def add_lodging_cost(m: dict, price_vnd: int | None, nights: int) -> dict:
    """metrics() with a lodging candidate's cost merged into cost_vnd / cost_unknown over the whole stay."""
    out = dict(m)
    if price_vnd is None:
        out["cost_unknown"] += 1
    else:
        out["cost_vnd"] += price_vnd * nights
    return out
```

Trong `src/planning/variants.py`, dòng import đầu file, thêm:

```python
import live

from .build import ENTRY, EXIT, with_home
from .lodging import candidates as lodging_candidates
from .objectives import add_lodging_cost
from .settings import load as load_settings
```

(giữ nguyên các import đã có của P4: `from .backup import backups`, `from .build import flag_warnings, itinerary, prepare, schedule_trip, shared_output, travel_load`, `from .objectives import LABEL, choose, metrics, score`, `from .robustness import robustness`.)

Trong `WARNING_TEXT`, thêm khoá:

```python
    "lodging_unavailable": "Chưa tra được chỗ ở: mỗi phương án dùng điểm vào / nơi ở đã biết làm neo.",
```

Vào cuối `src/planning/variants.py`, thêm:

```python


def _nights(ctx: dict) -> int:
    return max((ctx.get("days") or 1) - 1, 0)


def build_lodging_variants(decision: dict, records: list[dict], cfg=None, live_cfg=None, geocode_fn=None,
                           matrix_fn=None, sun_fn=None, weather: dict | None = None, lodging_fn=None) -> dict:
    """build_variants, with lodging candidates competing as each day's anchor (docs/specs/PLANNING_SPEC.md ⓐ ⓖ).

    Every candidate (plus the original base, as "no lodging") is tried under every chosen objective, sharing one
    travel matrix and one day-order cache keyed on where each day starts and ends. An objective keeps whichever
    candidate scores best for it; two objectives may end up with different lodging. The top-level lodging block
    compares every candidate on least_travel's schedule, since that objective is always tried.
    """
    cfg = cfg or load_settings()
    live_cfg = live_cfg or live.load_settings()
    lodging_fn = lodging_fn or live.lodging_near
    base_trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather)
    warnings = []
    try:
        cands = lodging_candidates(base_trip.by_place, decision, cfg, lodging_fn, live_cfg)
    except live.Unavailable:
        cands = []
    if not cands:
        warnings.append(_warn("lodging_unavailable"))
    trip = prepare(decision, records, cfg, live_cfg, geocode_fn, matrix_fn, sun_fn, weather,
                   extra_nodes={c["id"]: (c["lat"], c["lng"]) for c in cands})
    home0 = trip.days[0].start_node if trip.days else None
    options = [{"id": None, "home": home0, "price": None, "name": None}] + \
        [{"id": c["id"], "home": c["id"], "price": c["price_vnd"], "name": c["name"]} for c in cands]
    nights = _nights(decision["trip_context"]["context"])
    objectives = choose(decision["trip_context"], [cx.rain for cx in trip.ctxs], trip.ctxs[0].prefs, cfg)

    rows = {obj: [] for obj in objectives}
    for opt in options:
        t2 = trip if opt["home"] == home0 else with_home(trip, opt["home"])
        for obj in objectives:
            s = schedule_trip(t2, cfg.objective_weights[obj])
            m = add_lodging_cost(metrics(s.ctxs, s.results), opt["price"], nights) if not s.violations else None
            rows[obj].append({**opt, "sched": s, "metrics": m})

    warnings += list(trip.warnings)
    if any(cx.rain is None for cx in trip.ctxs):
        warnings.append(_warn("weather_unknown"))

    best = {obj: min((r for r in rs if r["metrics"] is not None), key=lambda r: score(obj, r["metrics"]),
                     default=None) for obj, rs in rows.items()}
    best = {obj: r for obj, r in best.items() if r is not None}
    if not best:
        first = rows[objectives[0]][0]["sched"]
        places = sorted({v.place_id for rs in rows.values() for r in rs for v in r["sched"].violations if v.place_id})
        if not places:          # a violation with no place_id (e.g. a day-window overflow): name the day's places
            places = sorted({i for rs in rows.values() for r in rs for v in r["sched"].violations
                             if v.day is not None for i in r["sched"].per_day[v.day]})
        return {"ok": False, "variants": [], "chosen": None, "comparison": [], "lodging": None,
                "violations": [asdict(v) for v in first.violations],
                "warnings": warnings + first.warnings + flag_warnings(decision),
                "back_to_decision": {"reason": "no_valid_variant", "places": places}, **shared_output(trip)}
    warnings += [_warn("variant_invalid", label=LABEL[obj]) for obj in objectives if obj not in best]

    seen, variants = set(), []
    for obj, r in best.items():
        key = (r["home"], tuple(x.order for x in r["sched"].results))
        if key in seen:
            continue
        seen.add(key)
        s, m = r["sched"], r["metrics"]
        days = [cx.day for cx in s.ctxs]        # schedule_trip may pull a later day's start earlier (early_start)
        variants.append({
            "id": f"v{len(variants) + 1}", "objective": obj, "label": LABEL[obj], "score": list(score(obj, m)),
            "metrics": m, "itinerary": itinerary(days, s.results), "travel_load": travel_load(days, s.results),
            "robustness": robustness(s.ctxs, s.results, trip.travel.source),
            "backups": backups(s.ctxs, s.results, decision, trip.by_id), "warnings": s.warnings,
            "lodging": {"id": r["id"], "name": r["name"], "price_vnd": r["price"]}})
    if len(variants) < len(best):
        warnings.append(_warn("variants_same", n=len(variants)))

    least = rows.get("least_travel") or next(iter(rows.values()))
    baseline = next((r["metrics"]["travel_min"] for r in least if r["id"] is None and r["metrics"]), None)
    lodging_rows = []
    for r in least:
        if r["metrics"] is None:
            continue
        cand = next((c for c in cands if c["id"] == r["id"]), None)
        row = {"id": r["id"], "name": r["name"] or "Không chỗ ở", "price_vnd": r["price"],
              "amenities": cand["amenities"] if cand else [], "total_travel_min": r["metrics"]["travel_min"]}
        if baseline is not None and r["id"] is not None:
            row["minutes_vs_no_lodging"] = r["metrics"]["travel_min"] - baseline
        lodging_rows.append(row)

    weather_src = sorted({(w.get("source"), w.get("fetched_at")) for w in (weather or {}).values()
                          if w and w.get("source")}, key=lambda t: (t[0], t[1] or ""))
    out = {"ok": True, "variants": variants, "chosen": None, "comparison": _comparison(variants),
          "lodging": {"candidates": lodging_rows, "chosen": None}, "violations": [],
          "warnings": warnings + flag_warnings(decision), "back_to_decision": None, **shared_output(trip)}
    out["provenance"]["weather"] = [{"source": s_, "fetched_at": f} for s_, f in weather_src]
    return out
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_objectives.py tests/planning/test_planning_lodging_variants.py -q`
Expected: PASS (2 test mới ở `test_planning_objectives.py`, 5 test ở `test_planning_lodging_variants.py`)

Run: `python -m pytest tests/planning -q`
Expected: PASS — toàn bộ test P3/P4 không đổi (file `variants.py` chỉ được thêm vào, không có dòng nào của `build_variants` bị sửa)

- [ ] **Step 5: Commit**

```bash
git add src/planning/objectives.py src/planning/variants.py tests/planning/test_planning_objectives.py tests/planning/test_planning_lodging_variants.py
git commit -m "feat(planning): lodging competes per objective, each keeping whichever candidate scores best"
```


### Task 7: Hình dạng sự kiện `progress`

**Files:**
- Modify: `src/planning/lodging.py` (thêm vào cuối)
- Test: thêm vào `tests/planning/test_planning_lodging.py`

**Interfaces:**
- Consumes: không có (hàm thuần).
- Produces: `planning.lodging.progress_event(cands: list[dict], baseline_travel_min: int | None) -> dict`

- [ ] **Step 1: Viết test**

Thêm vào cuối `tests/planning/test_planning_lodging.py`:

```python


from planning.lodging import progress_event


def test_progress_event_names_every_candidate_with_its_price():
    ev = progress_event([cand(0, price=300000), cand(1)], baseline_travel_min=120)
    assert ev == {"event": "progress", "stage": "lodging_scored",
                 "candidates": [{"id": "h0", "name": "Homestay 0", "price_vnd": 300000},
                                {"id": "h1", "name": "Homestay 1", "price_vnd": None}],
                 "baseline_travel_min": 120}
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_lodging.py -q`
Expected: FAIL với `ImportError: cannot import name 'progress_event'`

- [ ] **Step 3: Viết code**

Vào cuối `src/planning/lodging.py`, thêm:

```python


def progress_event(cands: list[dict], baseline_travel_min: int | None) -> dict:
    """The one event P6's SSE server relays while lodging crawls in the background
    (docs/specs/PLANNING_SPEC.md §Chỗ ở không làm người dùng chờ). baseline_travel_min comes from the caller (the
    trip already scheduled once without lodging): this module never recomputes it.
    """
    return {"event": "progress", "stage": "lodging_scored",
            "candidates": [{"id": c["id"], "name": c["name"], "price_vnd": c["price_vnd"]} for c in cands],
            "baseline_travel_min": baseline_travel_min}
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/planning/test_planning_lodging.py -q`
Expected: PASS (10 test)

- [ ] **Step 5: Commit**

```bash
git add src/planning/lodging.py tests/planning/test_planning_lodging.py
git commit -m "feat(planning): the shape of the progress event a lodging search reports"
```


### Task 8: Lệnh `python -m planning lodging`, public API, golden

**Files:**
- Modify: `src/planning/variants.py` (thêm `render_lodging_variants`), `src/planning/__init__.py`, `src/planning/__main__.py`
- Modify: `tests/planning/test_planning_cli.py`, `tests/planning/test_planning_boundaries.py`
- Create: `tests/planning/test_planning_lodging_golden.py`, `tests/planning/golden/lodging_sample_trip.json` (sinh ra)

**Interfaces:**
- Consumes: `planning.variants.build_lodging_variants` (Task 6), `planning.variants.render_variants` (P4).
- Produces: `planning.render_lodging_variants(out) -> str`, `planning.build_lodging_variants`; `python -m planning lodging <decision_output.json> [--weather forecast.json] [--out plan.json]` — mã thoát 0 / 2 như `variants`

- [ ] **Step 1: Viết test**

Trong `tests/planning/test_planning_cli.py`, dòng import đầu file thêm:

```python
import planning.variants as variants_module
```

và sửa fixture `offline`:

```python
@pytest.fixture
def offline(monkeypatch):
    """No OSRM, no Nominatim, no records file, no lodging crawl: the command line runs on what the test hands it."""
    monkeypatch.setattr(build_module.live, "travel_matrix", fake_matrix)
    monkeypatch.setattr(build_module.live, "geocode", lambda text, cfg: no_geocode(text))
    monkeypatch.setattr(build_module.live, "sun_times", fixed_sun)
    monkeypatch.setattr(variants_module.live, "lodging_near", lambda *a: [])
```

Thêm vào cuối file:

```python


def test_lodging_prints_a_cho_o_block_and_exits_zero_when_the_plan_is_valid(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45), rec("b", 11.941, 108.451)])
    assert cli.main(["lodging", str(write_decision(tmp_path, ["a", "b"]))]) == 0
    out = capsys.readouterr().out
    assert "Chỗ ở:" in out and "Không chỗ ở" in out and out.rstrip().endswith("Hợp lệ.")


def test_lodging_exits_two_and_points_back_to_place_decision(tmp_path, monkeypatch, capsys, offline):
    monkeypatch.setattr(cli, "load_records", lambda: [rec("a", 11.94, 108.45)])
    path = write_decision(tmp_path, ["a", "gone"], roles={"gone": "anchor"})
    assert cli.main(["lodging", str(path)]) == 2
    out = capsys.readouterr().out
    assert "quay lại chọn địa điểm (gone)" in out and out.rstrip().endswith("KHÔNG hợp lệ.")
```

Trong `tests/planning/test_planning_boundaries.py`, sửa `test_the_public_api_is_the_plan_builder_and_its_settings` (giả định P4 đã đổi assertion sang `{"Settings", "build_plan", "build_variants", "load_settings", "render_text", "render_variants"}`):

```python
    assert set(planning.__all__) == {"Settings", "build_lodging_variants", "build_plan", "build_variants",
                                     "load_settings", "render_lodging_variants", "render_text", "render_variants"}
```

Tạo `tests/planning/test_planning_lodging_golden.py`:

```python
"""Golden lodging variants of the sample trip (docs/specs/PLANNING_SPEC.md §Test).
UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_lodging_golden.py"""

import json
import os
from pathlib import Path

from plan_fixtures import CFG, SOUTH, FakeLive, fake_matrix, fixed_sun, no_geocode, sample_trip

from planning.variants import build_lodging_variants

GOLDEN = Path(__file__).parent / "golden" / "lodging_sample_trip.json"


def test_the_lodging_variants_of_the_sample_trip_match_the_golden_file():
    d, recs = sample_trip(budget=2_000_000, days=3)
    lodging_fn = lambda *a: [{"id": "h0", "name": "Homestay Nam", "lat": SOUTH[0], "lng": SOUTH[1], "rating": 4.6,
                             "reviews": 30, "price_vnd": 350000, "amenities": ["wifi"]}]
    out = build_lodging_variants(d, recs, cfg=CFG, live_cfg=FakeLive(), geocode_fn=no_geocode, matrix_fn=fake_matrix,
                                 sun_fn=fixed_sun, lodging_fn=lodging_fn)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    assert out == json.loads(GOLDEN.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py -q`
Expected: FAIL — `SystemExit: 2` (argparse: `invalid choice: 'lodging'`), `AttributeError` (`planning.live` chưa có trong `variants_module`), và assertion `__all__` sai

- [ ] **Step 3: Viết code**

Vào cuối `src/planning/variants.py`, thêm:

```python


def render_lodging_variants(out: dict) -> str:
    """render_variants with a "Chỗ ở:" block comparing every candidate on least_travel's own measure."""
    lines = render_variants(out).splitlines()
    verdict = lines.pop()
    if out["lodging"]:
        lines.append("Chỗ ở:")
        for r in out["lodging"]["candidates"]:
            cost = f'{r["price_vnd"]:,} VND/đêm' if r["price_vnd"] is not None else "chưa có giá"
            delta = r.get("minutes_vs_no_lodging")
            tail = f' ({delta:+d} phút cả chuyến so với không chỗ ở)' if delta is not None and r["id"] else ""
            lines.append(f'  {r["name"]}: {cost}, tổng {r["total_travel_min"]} phút di chuyển cả chuyến{tail}')
    lines.append(verdict)
    return "\n".join(lines)
```

(`render_lodging_variants` cần `render_text` qua `render_variants`, đã được import ở P4's Task 9: `from .build import flag_warnings, itinerary, prepare, render_text, schedule_trip, shared_output, travel_load` — không cần thêm import mới.)

Sửa `src/planning/__init__.py`:

```python
"""Planning & Validation: confirmed places -> checked itineraries (docs/specs/PLANNING_SPEC.md).

python -m planning build <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
python -m planning lodging <decision_output.json> [--weather forecast.json]
"""

from .build import build_plan, render_text
from .settings import Settings
from .settings import load as load_settings
from .variants import build_lodging_variants, build_variants, render_lodging_variants, render_variants

__all__ = ["Settings", "build_lodging_variants", "build_plan", "build_variants", "load_settings", "render_lodging_variants",
          "render_text", "render_variants"]
```

Sửa `src/planning/__main__.py`: dòng import cuối:

```python
from . import build_lodging_variants, build_plan, build_variants, render_lodging_variants, render_text, render_variants
```

Trong `main()`, sau khối `v = sub.add_parser("variants", ...)` thêm:

```python
    l = sub.add_parser("lodging", help="print 2-3 checked variants with lodging competing as each day's anchor")
    l.add_argument("decision_output", type=Path)
    l.add_argument("--weather", type=Path, help='{"YYYY-MM-DD": {"rain_prob": 0..1, "source", "fetched_at"}}')
    l.add_argument("--out", type=Path, help="also write the full Plan Output as json")
```

Khối `if args.cmd == "build": ... else: ...` sửa thành:

```python
    if args.cmd == "build":
        plan = build_plan(decision, load_records())
        text = render_text(plan)
    elif args.cmd == "variants":
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_variants(decision, load_records(), weather=weather)
        text = render_variants(plan)
    else:
        weather = json.loads(args.weather.read_text(encoding="utf-8")) if args.weather else None
        plan = build_lodging_variants(decision, load_records(), weather=weather)
        text = render_lodging_variants(plan)
```

- [ ] **Step 4: Sinh golden, xem lại nó, rồi chạy test**

Run: `UPDATE_GOLDEN=1 python -m pytest tests/planning/test_planning_lodging_golden.py -q` (PowerShell: `$env:UPDATE_GOLDEN=1; python -m pytest tests/planning/test_planning_lodging_golden.py -q; Remove-Item Env:UPDATE_GOLDEN`)

Mở file trước khi commit: `variants` có đúng một hoặc hai phần tử; `lodging.candidates` có đúng 2 dòng (`id: null` và `id: "h0"`), dòng `id: null` không có `minutes_vs_no_lodging` (nó là mốc 0, không tự so với chính nó); mỗi `variant` có field `lodging` khớp với ứng viên nó thật sự dùng (đối chiếu `start_node` của ngày đầu trong `itinerary` với `lodging.id`). Khác thế này nghĩa là có task trước lệch — dừng lại tìm, không commit golden.

Run: `python -m pytest tests/planning -q`
Expected: PASS (toàn bộ, cộng 3 test mới của Task 8)

- [ ] **Step 5: Chạy toàn bộ test của repo**

Run: `python -m pytest -q`
Expected: PASS — không test cũ nào đỏ

- [ ] **Step 6: Thử tay (không bắt buộc, không commit gì)**

```bash
python -m planning lodging decision_output.json
```

(dùng `decision_output.json` dựng như P3/P4's "thử tay"). Expected: khối `Chỗ ở:` liệt kê "Không chỗ ở" và mọi ứng viên thật crawl được (cần OSRM + Chrome đã đăng nhập `gmaps`), mỗi dòng có giá hoặc "chưa có giá" và tổng phút di chuyển cả chuyến. Đo thời gian: ngân sách spec < 2 s cho phần DỰNG LỊCH khi ma trận đã có (không tính thời gian crawl Maps, chạy song song/nền theo thiết kế); ghi số đo vào báo cáo cuối. Xoá `decision_output.json`.

- [ ] **Step 7: Commit**

```bash
git add src/planning/variants.py src/planning/__init__.py src/planning/__main__.py tests/planning/test_planning_cli.py tests/planning/test_planning_boundaries.py tests/planning/test_planning_lodging_golden.py tests/planning/golden/lodging_sample_trip.json
git commit -m "feat(planning): python -m planning lodging, its public API and a golden trip"
```


### Task 9: Sửa tài liệu cho khớp code

**Files:**
- Modify: `docs/specs/PLANNING_SPEC.md`; `README.md` (không commit)

**Interfaces:**
- Consumes: không có.
- Produces: không có — chỉ văn bản.

- [ ] **Step 1: Sửa `docs/specs/PLANNING_SPEC.md`**

Bốn chỗ, dùng Edit; mỗi chuỗi cũ xuất hiện đúng một lần.

1. §Chỗ ở (crawl live), sau đoạn "Dùng lại code crawl đúng ranh giới...", thêm đoạn mới:

```text
cũ:  `LoginRequired` hoặc captcha → trả rỗng kèm lý do; Planning chạy tiếp ở phương án không chỗ ở.
mới: `LoginRequired` hoặc captcha → trả rỗng kèm lý do; Planning chạy tiếp ở phương án không chỗ ở. Ngày check-in /
check-out và trần giá hiện mới lọc được ở phía Planning (`price_max`), chưa gửi lên bộ lọc của Maps — giá đọc được
là giá Maps hiển thị mặc định tại thời điểm crawl, không phải giá đúng hai ngày đó; cần dò lại bằng trình duyệt
thật trước khi nối UI ngày / giá của Maps. Giá và tiện nghi đọc bằng quét văn bản thô của thẻ (không phải một
class CSS riêng): best-effort, kiểm lại trước khi tin.
```

2. §Thuật toán ⓖ, câu cuối đoạn mô tả:

```text
cũ:  21 lần dựng lịch mỗi lượt, dùng chung một ma trận OSRM. Ngân sách: **< 2 s** khi cache nóng, đo trong `evaluate.py`.
mới: 21 lần dựng lịch mỗi lượt (K+1 chỗ ở × tối đa 3 mục tiêu), dùng chung một ma trận OSRM (toạ độ ứng viên nằm
trong CÙNG ma trận đó) và cache thứ tự trong ngày theo `(ngày, điểm mở, điểm đóng, tập nơi)` — đổi chỗ ở chỉ đổi
điểm mở/đóng ngày, không tính lại cụm hay chia ngày. Mỗi mục tiêu giữ tổ hợp (chỗ ở, lịch) tốt nhất riêng cho nó.
Ngân sách: **< 2 s** khi cache nóng, đo trong `evaluate.py`.
```

3. Mục "Giới hạn đã biết", thêm dòng mới:

```text
cũ:  - Chưa có User Profile dài hạn nên `preference_fit` chỉ dùng `soft_weights` của phiên.
mới: - Chưa có User Profile dài hạn nên `preference_fit` chỉ dùng `soft_weights` của phiên.
- Giá và tiện nghi của chỗ ở đọc bằng quét văn bản thô trên thẻ Maps (không phải DOM đã dò kỹ): có thể trống hoặc
sai nếu Maps đổi cách hiển thị; ngày check-in / check-out chưa đặt qua bộ lọc của Maps.
```

4. Bảng "Các phase", dòng P5:

```text
cũ:  | P5 | `live/weather`, `live/lodging`, `lodging.py`, chấm K × mục tiêu, event `progress` |
mới: | P5 | `live/weather` (Open-Meteo + `config/climate.yaml`), `live/lodging` (qua `corpus.crawl`), `planning/lodging.py`, `build.with_home`, chấm K × mục tiêu trong `variants.build_lodging_variants`, hình dạng event `progress`; CLI `python -m planning lodging` |
```

- [ ] **Step 2: Thêm lệnh vào `README.md`**

Ngay sau đoạn `python -m planning variants` mà plan P4 đã thêm, thêm:

```markdown
Chấm chỗ ở theo từng mục tiêu rồi in 2–3 phương án kèm chỗ ở đã chọn: `python -m planning lodging <decision_output.json> [--weather forecast.json]`; cần Chrome đã đăng nhập `gmaps` (`python -m corpus login gmaps`) và OSRM đang chạy.
```

Như P3/P4: sửa working copy nhưng **không** `git add` README; ghi vào báo cáo cuối rằng mục README chưa commit.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/PLANNING_SPEC.md
git commit -m "docs: match PLANNING_SPEC.md to the lodging and K x objectives implementation"
```

---

## Sau khi plan này xong

`python -m planning lodging` cho 2–3 phương án đã kiểm, mỗi phương án tự chọn chỗ ở tốt nhất cho mục tiêu của nó, cộng một bảng so sánh chỗ ở đo trên cùng một thước đo (`least_travel`). Còn lại theo `PLANNING_SPEC.md` §Các phase:

- P6: `session.py` (phiên có phiên bản, undo), các `act` (`pick_variant`, `pick_lodging`, `clear_lodging`, `set_lodging(text)`, `set_lodging_budget`, ...), `repair_day`, `scope.py`, `engine.py server.py` (HTTP + SSE cổng 8768) — đây là nơi `planning.lodging.progress_event` được thật sự đẩy qua SSE trong lúc `lodging_near` chạy nền, và nơi `chosen` lần đầu được đặt khác `None`.
- P7: `agent.py guard.py policy.py`.
- P8: Web `Itinerary.tsx` gọi `/api/planning` thật; xoá `web/src/user/planner.ts`.
- P9: `evaluate.py`, đo, cập nhật `README.md` + `docs/log/DEV_LOG.md`.
