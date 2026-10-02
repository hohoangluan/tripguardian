# Plan P1+P2 — Live Context + điểm vào/ra trong Trip State

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng `src/live` (ma trận thời gian OSRM, geocode, mặt trời, lễ, cache có TTL) và thêm `entry_point` / `exit_point` vào Trip State, để Plan 2 (Planning lõi) có đủ đầu vào.

**Architecture:** `src/live` là package độc lập, không import package nào khác của dự án, không có đường ghi nào tới dữ liệu corpus. Mỗi nguồn ngoài một thư mục con, cache theo request dưới `data/live/<source>/`, mỗi mục mang `source` + `fetched_at`. Nguồn chết thì raise `Unavailable` — người gọi (Planning) quyết nghĩa, `src/live` không bao giờ đoán giá trị. Trip State chỉ lưu text + `place_id` của điểm vào/ra; geocode xảy ra ở Planning nên `trip` không phụ thuộc `live`.

**Tech Stack:** Python 3.12, stdlib `urllib.request` (không thêm dependency HTTP), `pyyaml`, `pydantic` (đã có), `pytest`. OSRM chạy local trên OSM Việt Nam.

**Spec:** `docs/specs/PLANNING_SPEC.md`

## Global Constraints

- Tài liệu tiếng Việt; code, comment, identifier, tên file, commit message tiếng Anh (`RULE.md` §0).
- Module chỉ giao tiếp qua public API (`__init__.py`). Không deep import (`RULE.md` §2).
- Mỗi nguồn dữ liệu ngoài có module **và** thư mục dữ liệu riêng; không gộp nhiều nguồn (`RULE.md` §2).
- `src/live` không bao giờ ghi `data/intel`, `data/serving`, `data/gmaps`, `data/tiktok`, `data/review` (`PLANNING_SPEC.md` §Nguyên tắc 1).
- Không bịa giá trị còn thiếu: thiếu dữ liệu → `None` hoặc `Unavailable`, không điền (`RULE.md` §3).
- Không thêm dependency mới vào `pyproject.toml` trong plan này.
- Thay đổi tối thiểu: không refactor, đổi tên, format lại code không liên quan (`RULE.md` §4).
- Chạy test: `python -m pytest -q` ở gốc repo (`pythonpath = ["src"]` đã có trong `pyproject.toml`).
- Mọi giá trị live trả về phải có `source` và `fetched_at`.
- `DATA_DIR` đọc từ biến môi trường, mặc định `data`, giống `src/decision/__main__.py:19`.

## Review Focus

Năm lớp input mà spec hàm ý nhưng dễ bị bỏ, mỗi dòng đã được gắn test vào task sở hữu code:

1. **OSRM trả `null` cho một cặp không có đường** — `durations[i][j]` là `null`. Mong đợi: cặp đó là `None` trong ma trận, các cặp khác vẫn dùng được, không crash, không thành `0`. → Task 3, Step 7.
2. **OSRM trả HTTP 200 nhưng `code != "Ok"`** (service vừa khởi động, chưa nạp xong dữ liệu). Mong đợi: `Unavailable`, không cache kết quả rác. → Task 3, Step 9.
3. **Nominatim trả danh sách rỗng** cho tên chỗ ở người dùng tự gõ. Mong đợi: `None` (không phải lỗi), và lần hỏi lại không gọi mạng nữa. → Task 5, Step 7.
4. **File cache bị cắt ngang / JSON hỏng** (tắt máy giữa lúc ghi). Mong đợi: coi như cache miss, không raise. → Task 1, Step 7.
5. **`entry_point` người dùng gõ không khớp địa điểm nào trong corpus** (bến xe, sân bay không có trong corpus vì corpus chỉ chứa nơi du khách đến). Mong đợi: `Base(place_id=None, text=<nguyên văn>)` được giữ, không mất, không bịa `place_id`. → Task 9, Step 1.

---

### Task 1: Cache có TTL + settings của Live Context

**Files:**
- Create: `config/live.yaml`
- Create: `src/live/__init__.py`
- Create: `src/live/settings.py`
- Create: `src/live/cache.py`
- Modify: `.env.example`
- Test: `tests/live/test_cache.py`, `tests/live/test_settings.py`

**Interfaces:**
- Consumes: không có (task đầu).
- Produces:
  - `live.settings.Settings` — dataclass frozen với các field: `version: int`, `osrm_url: str`, `osrm_profile: str`, `mode_factor: dict`, `timeout_s: float`, `nominatim_url: str`, `user_agent: str`, `nominatim_min_interval_s: float`, `ttl_s: dict`, `tz_offset_h: float`.
  - `live.settings.load(path: Path = PATH) -> Settings`
  - `live.cache.data_dir() -> Path`, `live.cache.base_dir() -> Path`
  - `live.cache.key(payload: dict) -> str`
  - `live.cache.get(source: str, payload: dict, ttl_s: int) -> dict | None` — trả `{"source", "fetched_at", "value"}` khi còn tươi
  - `live.cache.put(source: str, payload: dict, value, label: str) -> dict` — trả đúng mục vừa ghi

- [ ] **Step 1: Viết test cho `cache.put` / `cache.get`**

Tạo `tests/live/test_cache.py`:

```python
import json
from datetime import UTC, datetime, timedelta

import pytest

from live import cache


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_put_then_get_returns_the_value_with_its_provenance():
    cache.put("osrm", {"points": [[1.0, 2.0]]}, [[0, 300]], "osrm")
    hit = cache.get("osrm", {"points": [[1.0, 2.0]]}, ttl_s=60)
    assert hit is not None
    assert hit["value"] == [[0, 300]]
    assert hit["source"] == "osrm"
    datetime.fromisoformat(hit["fetched_at"])  # parses, so it is a real timestamp
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_cache.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live'`

- [ ] **Step 3: Viết `src/live/cache.py` tối thiểu**

```python
"""Per-request cache for live context: data/live/<source>/<key>.json, each entry carrying its own provenance.

Nothing here reads or writes corpus data. The cache is the only thing src/live ever writes.
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = Path(os.environ.get("DATA_DIR", "data"))
    return d if d.is_absolute() else ROOT / d


def base_dir() -> Path:
    return data_dir() / "live"


def key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _path(source: str, payload: dict) -> Path:
    return base_dir() / source / f"{key(payload)}.json"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get(source: str, payload: dict, ttl_s: int) -> dict | None:
    """The stored entry while it is still fresh, else None. A missing, unreadable or malformed file is a miss."""
    p = _path(source, payload)
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
        age = (datetime.now(UTC) - datetime.fromisoformat(entry["fetched_at"])).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return None if age > ttl_s else entry


def put(source: str, payload: dict, value, label: str) -> dict:
    """Write one entry atomically and return it, so callers use the same shape on a hit and on a miss."""
    entry = {"source": label, "fetched_at": now(), "value": value}
    p = _path(source, payload)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return entry
```

Tạo `src/live/__init__.py` tạm thời (sẽ mọc dần qua các task sau):

```python
"""Live Context: facts fetched per request from outside (docs/specs/PLANNING_SPEC.md §Live Context).

Never writes Place Intelligence. A source that does not answer raises Unavailable; nothing here invents a value.
"""
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_cache.py -q`
Expected: PASS (1 test)

- [ ] **Step 5: Viết test cho TTL hết hạn và cho key khác nhau**

Thêm vào `tests/live/test_cache.py`:

```python
def test_an_entry_older_than_its_ttl_is_a_miss(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    entry = json.loads(p.read_text(encoding="utf-8"))
    entry["fetched_at"] = (datetime.now(UTC) - timedelta(seconds=120)).isoformat(timespec="seconds")
    p.write_text(json.dumps(entry), encoding="utf-8")
    assert cache.get("osrm", {"a": 1}, ttl_s=60) is None
    assert cache.get("osrm", {"a": 1}, ttl_s=3600) is not None


def test_different_payloads_do_not_share_an_entry():
    cache.put("osrm", {"a": 1}, "one", "osrm")
    cache.put("osrm", {"a": 2}, "two", "osrm")
    assert cache.get("osrm", {"a": 1}, 60)["value"] == "one"
    assert cache.get("osrm", {"a": 2}, 60)["value"] == "two"


def test_key_ignores_dict_ordering():
    assert cache.key({"a": 1, "b": 2}) == cache.key({"b": 2, "a": 1})


def test_sources_are_kept_in_separate_directories(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    cache.put("geocode", {"a": 1}, "v", "nominatim")
    assert {d.name for d in (data_dir / "live").iterdir()} == {"osrm", "geocode"}
```

- [ ] **Step 6: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_cache.py -q`
Expected: PASS (5 tests)

- [ ] **Step 7: Viết test cho file cache hỏng (Review Focus #4)**

Thêm vào `tests/live/test_cache.py`:

```python
def test_a_truncated_cache_file_is_a_miss_not_a_crash(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    p.write_text('{"source": "osrm", "fetch', encoding="utf-8")  # killed mid-write
    assert cache.get("osrm", {"a": 1}, 60) is None


def test_a_cache_file_without_a_timestamp_is_a_miss(data_dir):
    cache.put("osrm", {"a": 1}, "v", "osrm")
    p = next((data_dir / "live" / "osrm").glob("*.json"))
    p.write_text('{"source": "osrm", "value": "v"}', encoding="utf-8")
    assert cache.get("osrm", {"a": 1}, 60) is None
```

- [ ] **Step 8: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_cache.py -q`
Expected: PASS (7 tests) — `cache.get` đã bắt `ValueError` / `KeyError` nên không cần sửa code

- [ ] **Step 9: Viết test cho settings**

Tạo `tests/live/test_settings.py`:

```python
from pathlib import Path

from live import settings


def test_the_shipped_config_loads_with_every_field_filled():
    cfg = settings.load(settings.PATH)
    assert cfg.version == 1
    assert cfg.osrm_url.startswith("http")
    assert cfg.mode_factor["car"] == 1.0
    assert cfg.mode_factor["motorbike"] < 1.0
    assert set(cfg.ttl_s) == {"osrm", "weather", "lodging", "geocode"}
    assert cfg.ttl_s["osrm"] > cfg.ttl_s["weather"]
    assert cfg.tz_offset_h == 7
    assert cfg.nominatim_min_interval_s >= 1.0  # Nominatim's usage policy


def test_the_user_agent_carries_a_contact(monkeypatch):
    monkeypatch.setenv("LIVE_CONTACT", "someone@example.com")
    settings.load.cache_clear()
    assert "someone@example.com" in settings.load(settings.PATH).user_agent
    settings.load.cache_clear()
```

- [ ] **Step 10: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_settings.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.settings'`

- [ ] **Step 11: Viết `config/live.yaml`**

```yaml
# Live Context settings (docs/specs/PLANNING_SPEC.md §Live Context).
# Planning reads config/planning.yaml; this file belongs to src/live alone, so src/live needs no other package.
version: 1

# OSRM runs on this machine; see scripts/osrm_setup.sh.
osrm_url: http://127.0.0.1:5000
osrm_profile: driving

# OSM has no motorbike profile, so the car profile is scaled. Every number built on this is labelled an estimate.
mode_factor:
  car: 1.0
  motorbike: 0.95
  ride: 1.0
  walk: 1.0

timeout_s: 10

nominatim_url: https://nominatim.openstreetmap.org/search
# Nominatim requires an identifying User-Agent with a contact; LIVE_CONTACT fills {contact} from .env.
user_agent: "TripGuardian/0.1 (contact: {contact})"
nominatim_min_interval_s: 1.0

# Seconds. Roads change slowly, forecasts quickly, OTA prices daily.
ttl_s:
  osrm: 604800      # 7 days
  weather: 10800    # 3 hours
  lodging: 86400    # 1 day
  geocode: 2592000  # 30 days

tz_offset_h: 7
```

- [ ] **Step 12: Viết `src/live/settings.py`**

```python
"""Live Context settings (config/live.yaml). The contact in the User-Agent comes from .env, not from the repo."""

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "live.yaml"


@dataclass(frozen=True)
class Settings:
    version: int
    osrm_url: str
    osrm_profile: str
    mode_factor: dict
    timeout_s: float
    nominatim_url: str
    user_agent: str
    nominatim_min_interval_s: float
    ttl_s: dict
    tz_offset_h: float


@cache
def load(path: Path = PATH) -> Settings:
    load_dotenv(ROOT / ".env")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    contact = os.environ.get("LIVE_CONTACT", "unset")
    raw["user_agent"] = raw["user_agent"].format(contact=contact)
    return Settings(**raw)
```

- [ ] **Step 13: Thêm `LIVE_CONTACT` vào `.env.example`**

Thêm vào cuối `.env.example`:

```
# Contact put in the User-Agent of live-context requests. Nominatim's usage policy asks for one.
LIVE_CONTACT=
```

- [ ] **Step 14: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live -q`
Expected: PASS (9 tests)

- [ ] **Step 15: Commit**

```bash
git add config/live.yaml src/live/__init__.py src/live/settings.py src/live/cache.py .env.example tests/live
git commit -m "feat(live): TTL cache and settings for live context"
```

---

### Task 2: HTTP JSON tối thiểu + `Unavailable`

**Files:**
- Create: `src/live/http.py`
- Test: `tests/live/test_http.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `live.http.Unavailable` — `RuntimeError`, nghĩa "nguồn ngoài không trả lời dùng được"
  - `live.http.get_json(url: str, user_agent: str, timeout_s: float)` — trả object JSON, raise `Unavailable` khi lỗi mạng / timeout / JSON hỏng

- [ ] **Step 1: Viết test**

Tạo `tests/live/test_http.py`:

```python
import io
import json
import urllib.error

import pytest

from live import http


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_get_json_returns_the_parsed_body_and_sends_the_user_agent(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return _Resp(json.dumps({"code": "Ok"}).encode("utf-8"))

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    assert http.get_json("http://x/y?q=1", "TG/0.1", 3.5) == {"code": "Ok"}
    assert seen["url"] == "http://x/y?q=1"
    assert seen["ua"] == "TG/0.1"
    assert seen["timeout"] == 3.5


def test_a_network_error_becomes_unavailable(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http.Unavailable) as e:
        http.get_json("http://127.0.0.1:5000/table/v1/driving/x?annotations=duration", "TG/0.1", 1)
    assert "?" not in str(e.value)  # the query string can hold user text, so it stays out of the message


def test_a_body_that_is_not_json_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda req, timeout: _Resp(b"<html>502</html>"))
    with pytest.raises(http.Unavailable):
        http.get_json("http://x/y", "TG/0.1", 1)


def test_a_timeout_becomes_unavailable(monkeypatch):
    def fake_urlopen(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(http.Unavailable):
        http.get_json("http://x/y", "TG/0.1", 1)
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_http.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.http'`

- [ ] **Step 3: Viết `src/live/http.py`**

```python
"""One JSON GET for live sources: stdlib only, one timeout, no retries.

A failure is handed to the caller as Unavailable; deciding what a missing source means belongs to Planning.
"""

import json
import urllib.error
import urllib.request


class Unavailable(RuntimeError):
    """A live source did not answer usably. Planning turns this into a flag, never into a made-up value."""


def get_json(url: str, user_agent: str, timeout_s: float):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise Unavailable(f"{url.split('?', 1)[0]}: {e}") from e
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_http.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/live/http.py tests/live/test_http.py
git commit -m "feat(live): json GET helper that reports a dead source as Unavailable"
```

---

### Task 3: Ma trận thời gian OSRM

**Files:**
- Create: `src/live/osrm/__init__.py`
- Create: `src/live/osrm/client.py`
- Create: `scripts/osrm_setup.sh`
- Modify: `README.md` (mục "Thiết lập", thêm bước OSRM)
- Test: `tests/live/test_osrm.py`
- Test fixture: `tests/live/fixtures/osrm_table.json`

**Interfaces:**
- Consumes: `live.cache.get/put`, `live.http.get_json`, `live.http.Unavailable`, `live.settings.Settings`.
- Produces:
  - `live.osrm.Point = tuple[float, float]` — `(lat, lng)`
  - `live.osrm.travel_matrix(points: list[Point], mode: str | None, cfg: Settings) -> dict` — `{"minutes": list[list[int | None]], "source": str, "fetched_at": str}`; `minutes[i][i] == 0`; cặp không có đường là `None`

- [ ] **Step 1: Lưu fixture phản hồi OSRM**

Tạo `tests/live/fixtures/osrm_table.json` (dạng phản hồi `/table/v1/driving/...?annotations=duration`, ba điểm Đà Lạt):

```json
{
 "code": "Ok",
 "durations": [[0, 540.3, 1260.8], [548.1, 0, 980.2], [1272.4, 991.6, 0]],
 "sources": [{"name": ""}, {"name": ""}, {"name": ""}],
 "destinations": [{"name": ""}, {"name": ""}, {"name": ""}]
}
```

- [ ] **Step 2: Viết test cho đường đi vui vẻ**

Tạo `tests/live/test_osrm.py`:

```python
import json
from pathlib import Path

import pytest

from live import cache, http, settings
from live.osrm import client

FIXTURES = Path(__file__).parent / "fixtures"
PTS = [(11.9465, 108.4419), (11.9404, 108.4583), (11.9029, 108.4482)]


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


@pytest.fixture
def table(monkeypatch):
    """Serve the saved OSRM table and count the calls, so cache behaviour is visible."""
    doc = json.loads((FIXTURES / "osrm_table.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return doc

    monkeypatch.setattr(client, "get_json", fake)
    return calls


def test_the_matrix_is_minutes_with_zero_on_the_diagonal(cfg, table):
    m = client.travel_matrix(PTS, "car", cfg)
    assert m["minutes"][0][0] == 0 and m["minutes"][1][1] == 0
    assert m["minutes"][0][1] == 9       # 540.3 s * 1.0 / 60
    assert m["minutes"][0][2] == 21      # 1260.8 s * 1.0 / 60
    assert m["source"] == "osrm" and m["fetched_at"]


def test_the_request_sends_lng_then_lat(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    assert "108.441900,11.946500" in table[0]
    assert "annotations=duration" in table[0]


def test_the_motorbike_factor_scales_the_car_times(cfg, table):
    car = client.travel_matrix(PTS, "car", cfg)["minutes"][0][1]
    moto = client.travel_matrix(PTS, "motorbike", cfg)["minutes"][0][1]
    assert moto < car
    assert moto == 9  # 540.3 s * 0.95 / 60 rounds to 9


def test_an_unknown_mode_falls_back_to_a_factor_of_one(cfg, table):
    assert client.travel_matrix(PTS, "hovercraft", cfg)["minutes"][0][1] == 9
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_osrm.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.osrm'`

- [ ] **Step 4: Viết `src/live/osrm/client.py`**

```python
"""OSRM on this machine: a duration matrix and the shape of one route.

The matrix is cached mode-free (roads do not care about the vehicle); the mode factor is applied on the way out.
"""

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings

Point = tuple[float, float]  # (lat, lng)


def _coords(points: list[Point]) -> str:
    return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)  # OSRM reads lng,lat


def _factor(mode: str | None, cfg: Settings) -> float:
    return float(cfg.mode_factor.get(mode or "motorbike", 1.0))


def _rounded(points: list[Point]) -> list[list[float]]:
    return [[round(lat, 6), round(lng, 6)] for lat, lng in points]


def travel_matrix(points: list[Point], mode: str | None, cfg: Settings) -> dict:
    """{"minutes": [[int | None]], "source", "fetched_at"}. None is a pair OSRM found no road for."""
    if len(points) < 2:
        raise ValueError("travel_matrix needs at least two points")
    payload = {"kind": "table", "profile": cfg.osrm_profile, "points": _rounded(points)}
    hit = cache_get("osrm", payload, cfg.ttl_s["osrm"])
    if hit is None:
        url = f"{cfg.osrm_url}/table/v1/{cfg.osrm_profile}/{_coords(points)}?annotations=duration"
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        if doc.get("code") != "Ok" or not doc.get("durations"):
            raise Unavailable(f"osrm table: code={doc.get('code')!r}")
        hit = cache_put("osrm", payload, doc["durations"], "osrm")
    f, secs = _factor(mode, cfg), hit["value"]
    minutes = [[0 if i == j else (None if secs[i][j] is None else max(1, round(secs[i][j] * f / 60)))
                for j in range(len(points))] for i in range(len(points))]
    return {"minutes": minutes, "source": hit["source"], "fetched_at": hit["fetched_at"]}
```

Tạo `src/live/osrm/__init__.py` (Task 4 sẽ thêm `route_shape` vào đây):

```python
"""OSRM, one module per external source (RULE.md §2): data/live/osrm/ holds its cache and nothing else."""

from .client import Point, travel_matrix

__all__ = ["Point", "travel_matrix"]
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_osrm.py -q`
Expected: PASS (4 tests)

- [ ] **Step 6: Viết test cache dùng lại và độc lập với mode**

Thêm vào `tests/live/test_osrm.py`:

```python
def test_the_second_call_comes_from_the_cache(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS, "car", cfg)
    assert len(table) == 1


def test_changing_only_the_mode_does_not_refetch(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS, "motorbike", cfg)
    assert len(table) == 1


def test_a_different_point_set_refetches(cfg, table):
    client.travel_matrix(PTS, "car", cfg)
    client.travel_matrix(PTS[:2], "car", cfg)
    assert len(table) == 2


def test_fewer_than_two_points_is_a_programming_error(cfg, table):
    with pytest.raises(ValueError):
        client.travel_matrix([PTS[0]], "car", cfg)
```

- [ ] **Step 7: Viết test cho cặp không có đường (Review Focus #1)**

Thêm vào `tests/live/test_osrm.py`:

```python
def test_a_pair_with_no_road_is_none_and_the_others_still_work(cfg, monkeypatch):
    doc = {"code": "Ok", "durations": [[0, None, 1260.8], [None, 0, 980.2], [1272.4, 991.6, 0]]}
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: doc)
    m = client.travel_matrix(PTS, "car", cfg)["minutes"]
    assert m[0][1] is None and m[1][0] is None
    assert m[0][2] == 21 and m[2][1] == 17
    assert m[0][0] == 0
```

- [ ] **Step 8: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_osrm.py -q`
Expected: PASS (9 tests)

- [ ] **Step 9: Viết test cho OSRM trả `code != "Ok"` (Review Focus #2)**

Thêm vào `tests/live/test_osrm.py`:

```python
def test_a_non_ok_code_is_unavailable_and_nothing_is_cached(cfg, data_dir, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "NoSegment", "message": "no road"})
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)
    assert not (data_dir / "live" / "osrm").exists()


def test_an_ok_code_with_no_durations_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "Ok"})
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)


def test_a_dead_osrm_is_unavailable_not_a_crash(cfg, monkeypatch):
    def dead(url, ua, timeout):
        raise http.Unavailable("http://127.0.0.1:5000/table/v1/driving: connection refused")

    monkeypatch.setattr(client, "get_json", dead)
    with pytest.raises(http.Unavailable):
        client.travel_matrix(PTS, "car", cfg)
```

- [ ] **Step 10: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_osrm.py -q`
Expected: PASS (12 tests)

- [ ] **Step 11: Viết `scripts/osrm_setup.sh`**

```bash
#!/usr/bin/env bash
# One-time OSRM setup for Planning's travel matrices (docs/specs/PLANNING_SPEC.md, Live Context).
# Needs docker. Data lands in ./osrm-data, which .gitignore excludes.
set -euo pipefail

DIR="${1:-osrm-data}"
PBF_URL="https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"
IMAGE="ghcr.io/project-osrm/osrm-backend:latest"

mkdir -p "$DIR"
cd "$DIR"

if [ ! -f vietnam-latest.osm.pbf ]; then
  echo "downloading $PBF_URL"
  curl -L -o vietnam-latest.osm.pbf "$PBF_URL"
fi

if [ ! -f vietnam-latest.osrm.mldgr ]; then
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-extract -p /opt/car.lua /data/vietnam-latest.osm.pbf
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-partition /data/vietnam-latest.osrm
  docker run --rm -t -v "$PWD:/data" "$IMAGE" \
    osrm-customize /data/vietnam-latest.osrm
fi

echo "starting osrm-routed on 127.0.0.1:5000 (ctrl-c to stop)"
docker run --rm -t -p 127.0.0.1:5000:5000 -v "$PWD:/data" "$IMAGE" \
  osrm-routed --algorithm mld --max-table-size 300 /data/vietnam-latest.osrm
```

Thêm `osrm-data/` vào `.gitignore`.

- [ ] **Step 12: Thêm bước OSRM vào `README.md`**

Trong mục "Thiết lập" của `README.md`, thêm một bước sau bước 3 (`pip install -e .`):

```markdown
4. Thời gian di chuyển cho Planning: chạy OSRM một lần mỗi máy — `bash scripts/osrm_setup.sh` (cần docker; tải OSM Việt Nam, dựng chỉ mục, rồi mở `127.0.0.1:5000`). Không chạy OSRM thì Planning vẫn chạy ở chế độ ước lượng thô và gắn cảnh báo. Endpoint và TTL ở `config/live.yaml`; `LIVE_CONTACT` trong `.env` là liên hệ gửi kèm request.
```

Các bước sau đó trong README đánh số lại.

- [ ] **Step 13: Viết test gọi OSRM thật (chạy tay)**

Tạo `tests/live/test_live.py`:

```python
"""Real network and a real local OSRM: python -m pytest -m live tests/live/test_live.py -s"""

import pytest

from live import load_settings, travel_matrix

pytestmark = pytest.mark.live

DALAT = [(11.9465, 108.4419), (11.9029, 108.4482)]  # Hồ Xuân Hương, Thung lũng Tình yêu area


def test_osrm_answers_for_two_points_in_dalat():
    m = travel_matrix(DALAT, "motorbike", load_settings())
    assert m["source"] == "osrm"
    assert 3 <= m["minutes"][0][1] <= 60, m["minutes"]
```

- [ ] **Step 14: Chạy toàn bộ test (không live), xác nhận pass**

Run: `python -m pytest -q`
Expected: PASS — toàn bộ test cũ vẫn xanh, thêm test của `tests/live`

- [ ] **Step 15: Commit**

```bash
git add src/live/osrm tests/live/test_osrm.py tests/live/test_live.py tests/live/fixtures scripts/osrm_setup.sh README.md .gitignore
git commit -m "feat(live): OSRM duration matrix with a mode factor and a one-time setup script"
```

---

### Task 4: Hình lộ trình OSRM

**Files:**
- Modify: `src/live/osrm/client.py`
- Modify: `src/live/osrm/__init__.py`
- Test: `tests/live/test_osrm_route.py`
- Test fixture: `tests/live/fixtures/osrm_route.json`

**Interfaces:**
- Consumes: mọi thứ Task 3 tạo.
- Produces: `live.osrm.route_shape(points: list[Point], mode: str | None, cfg: Settings) -> dict` — `{"coords": list[list[float]]` (từng phần tử `[lat, lng]`), `"minutes": int, "source": str, "fetched_at": str}`

- [ ] **Step 1: Lưu fixture phản hồi `/route`**

Tạo `tests/live/fixtures/osrm_route.json`:

```json
{
 "code": "Ok",
 "routes": [{"duration": 1802.4, "distance": 9123.5,
             "geometry": {"type": "LineString",
                          "coordinates": [[108.4419, 11.9465], [108.4500, 11.9300], [108.4482, 11.9029]]}}],
 "waypoints": [{"name": ""}, {"name": ""}]
}
```

- [ ] **Step 2: Viết test**

Tạo `tests/live/test_osrm_route.py`:

```python
import json
from pathlib import Path

import pytest

from live import http, settings
from live.osrm import client

FIXTURES = Path(__file__).parent / "fixtures"
PTS = [(11.9465, 108.4419), (11.9029, 108.4482)]


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


@pytest.fixture
def route(monkeypatch):
    doc = json.loads((FIXTURES / "osrm_route.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return doc

    monkeypatch.setattr(client, "get_json", fake)
    return calls


def test_the_shape_comes_back_as_lat_lng_pairs(cfg, route):
    r = client.route_shape(PTS, "car", cfg)
    assert r["coords"][0] == [11.9465, 108.4419]   # geojson is lng,lat; the app draws lat,lng
    assert r["coords"][-1] == [11.9029, 108.4482]
    assert r["minutes"] == 30                       # 1802.4 s * 1.0 / 60
    assert r["source"] == "osrm" and r["fetched_at"]


def test_the_request_asks_for_a_full_geojson_overview(cfg, route):
    client.route_shape(PTS, "car", cfg)
    assert "overview=full" in route[0] and "geometries=geojson" in route[0]
    assert "/route/v1/" in route[0]


def test_the_route_cache_is_separate_from_the_matrix_cache(cfg, route, monkeypatch):
    table = json.loads((FIXTURES / "osrm_table.json").read_text(encoding="utf-8"))
    both = []

    def fake(url, ua, timeout):
        both.append(url)
        return json.loads((FIXTURES / "osrm_route.json").read_text(encoding="utf-8")) if "/route/" in url else table

    monkeypatch.setattr(client, "get_json", fake)
    client.route_shape(PTS, "car", cfg)
    client.travel_matrix(PTS, "car", cfg)
    assert len(both) == 2


def test_a_non_ok_route_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(client, "get_json", lambda url, ua, timeout: {"code": "NoRoute"})
    with pytest.raises(http.Unavailable):
        client.route_shape(PTS, "car", cfg)


def test_fewer_than_two_points_is_a_programming_error(cfg, route):
    with pytest.raises(ValueError):
        client.route_shape([PTS[0]], "car", cfg)
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_osrm_route.py -q`
Expected: FAIL với `AttributeError: module 'live.osrm.client' has no attribute 'route_shape'`

- [ ] **Step 4: Thêm `route_shape` vào `src/live/osrm/client.py`**

Thêm vào cuối file:

```python
def route_shape(points: list[Point], mode: str | None, cfg: Settings) -> dict:
    """{"coords": [[lat, lng]], "minutes": int, "source", "fetched_at"} — the line one day's route draws."""
    if len(points) < 2:
        raise ValueError("route_shape needs at least two points")
    payload = {"kind": "route", "profile": cfg.osrm_profile, "points": _rounded(points)}
    hit = cache_get("osrm", payload, cfg.ttl_s["osrm"])
    if hit is None:
        url = (f"{cfg.osrm_url}/route/v1/{cfg.osrm_profile}/{_coords(points)}"
               "?overview=full&geometries=geojson&steps=false")
        doc = get_json(url, cfg.user_agent, cfg.timeout_s)
        if doc.get("code") != "Ok" or not doc.get("routes"):
            raise Unavailable(f"osrm route: code={doc.get('code')!r}")
        r = doc["routes"][0]
        hit = cache_put("osrm", payload, {"coords": r["geometry"]["coordinates"], "duration": r["duration"]}, "osrm")
    v, f = hit["value"], _factor(mode, cfg)
    return {"coords": [[lat, lng] for lng, lat in v["coords"]], "minutes": max(1, round(v["duration"] * f / 60)),
            "source": hit["source"], "fetched_at": hit["fetched_at"]}
```

Sửa `src/live/osrm/__init__.py` thành:

```python
"""OSRM, one module per external source (RULE.md §2): data/live/osrm/ holds its cache and nothing else."""

from .client import Point, route_shape, travel_matrix

__all__ = ["Point", "route_shape", "travel_matrix"]
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live -q`
Expected: PASS (tất cả test `tests/live`, gồm 5 test mới)

- [ ] **Step 6: Commit**

```bash
git add src/live/osrm tests/live/test_osrm_route.py tests/live/fixtures/osrm_route.json
git commit -m "feat(live): OSRM route shape for drawing a day's route"
```

---

### Task 5: Geocode qua Nominatim

**Files:**
- Create: `src/live/geocode/__init__.py`
- Create: `src/live/geocode/nominatim.py`
- Test: `tests/live/test_geocode.py`
- Test fixture: `tests/live/fixtures/nominatim_hit.json`

**Interfaces:**
- Consumes: `live.cache`, `live.http`, `live.settings.Settings`.
- Produces: `live.geocode.geocode(text: str, cfg: Settings, city: str = "Đà Lạt, Việt Nam", clock=time.monotonic, sleep=time.sleep) -> dict | None` — `{"lat": float, "lng": float, "label": str, "source": str, "fetched_at": str}`, hoặc `None` khi không khớp gì

- [ ] **Step 1: Lưu fixture**

Tạo `tests/live/fixtures/nominatim_hit.json`:

```json
[{"place_id": 1, "lat": "11.9404", "lon": "108.4583",
  "display_name": "Bến xe Liên tỉnh Đà Lạt, Phường 2, Đà Lạt, Lâm Đồng, Việt Nam",
  "category": "amenity", "type": "bus_station"}]
```

- [ ] **Step 2: Viết test**

Tạo `tests/live/test_geocode.py`:

```python
import json
from pathlib import Path

import pytest

from live import settings
from live.geocode import nominatim

FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.fixture
def hit(monkeypatch):
    rows = json.loads((FIXTURES / "nominatim_hit.json").read_text(encoding="utf-8"))
    calls = []

    def fake(url, ua, timeout):
        calls.append(url)
        return rows

    monkeypatch.setattr(nominatim, "get_json", fake)
    return calls


def test_a_match_becomes_a_point_with_its_provenance(cfg, hit):
    p = nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert p["lat"] == 11.9404 and p["lng"] == 108.4583
    assert "Đà Lạt" in p["label"]
    assert p["source"] == "nominatim" and p["fetched_at"]


def test_the_city_is_appended_when_the_text_does_not_name_it(cfg, hit):
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert "%C4%90%C3%A0+L%E1%BA%A1t" in hit[0]  # "Đà Lạt" is urlencoded into the query
    assert "countrycodes=vn" in hit[0]
    assert "limit=1" in hit[0]


def test_text_that_already_names_the_city_is_not_doubled(cfg, hit):
    nominatim.geocode("Sân bay Liên Khương, Đà Lạt", cfg, sleep=lambda s: None)
    assert hit[0].count("%C4%90%C3%A0+L%E1%BA%A1t") == 1


def test_the_second_lookup_comes_from_the_cache(cfg, hit):
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
    assert len(hit) == 1


def test_empty_text_is_a_programming_error(cfg, hit):
    with pytest.raises(ValueError):
        nominatim.geocode("   ", cfg, sleep=lambda s: None)
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_geocode.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.geocode'`

- [ ] **Step 4: Viết `src/live/geocode/nominatim.py`**

```python
"""Nominatim: text -> one point. At most one request a second, which is the service's usage policy.

A text that matches nothing is cached as a miss, so asking twice does not hit the service twice.
"""

import time
import urllib.parse

from ..cache import get as cache_get
from ..cache import put as cache_put
from ..http import Unavailable, get_json
from ..settings import Settings

_last_call = 0.0


def _throttle(min_interval_s: float, clock, sleep) -> None:
    global _last_call
    wait = min_interval_s - (clock() - _last_call)
    if wait > 0:
        sleep(wait)
    _last_call = clock()


def geocode(text: str, cfg: Settings, city: str = "Đà Lạt, Việt Nam", clock=time.monotonic,
            sleep=time.sleep) -> dict | None:
    """{"lat", "lng", "label", "source", "fetched_at"}, or None when nothing matches. Never guesses a point."""
    q = text.strip()
    if not q:
        raise ValueError("geocode needs text")
    if city.split(",")[0].casefold() not in q.casefold():
        q = f"{q}, {city}"
    payload = {"q": q}
    hit = cache_get("geocode", payload, cfg.ttl_s["geocode"])
    if hit is None:
        _throttle(cfg.nominatim_min_interval_s, clock, sleep)
        query = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "vn"})
        rows = get_json(f"{cfg.nominatim_url}?{query}", cfg.user_agent, cfg.timeout_s)
        if not isinstance(rows, list):
            raise Unavailable("nominatim: the body is not a list of results")
        hit = cache_put("geocode", payload, rows[0] if rows else None, "nominatim")
    row = hit["value"]
    if row is None:
        return None
    return {"lat": float(row["lat"]), "lng": float(row["lon"]), "label": row.get("display_name") or q,
            "source": hit["source"], "fetched_at": hit["fetched_at"]}
```

Tạo `src/live/geocode/__init__.py`:

```python
"""Geocoding, one module per external source (RULE.md §2): data/live/geocode/ holds its cache and nothing else."""

from .nominatim import geocode

__all__ = ["geocode"]
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_geocode.py -q`
Expected: PASS (5 tests)

- [ ] **Step 6: Viết test cho throttle**

Thêm vào `tests/live/test_geocode.py`:

```python
def test_two_lookups_in_a_row_wait_out_the_rate_limit(cfg, monkeypatch):
    rows = json.loads((FIXTURES / "nominatim_hit.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, timeout: rows)
    monkeypatch.setattr(nominatim, "_last_call", 0.0)
    slept, t = [], [100.0]
    nominatim.geocode("Bến xe Liên tỉnh", cfg, clock=lambda: t[0], sleep=slept.append)
    nominatim.geocode("Sân bay Liên Khương", cfg, clock=lambda: t[0], sleep=slept.append)
    assert slept[-1] == pytest.approx(cfg.nominatim_min_interval_s)
```

- [ ] **Step 7: Viết test cho Nominatim trả rỗng (Review Focus #3)**

Thêm vào `tests/live/test_geocode.py`:

```python
def test_no_match_is_none_and_is_remembered(cfg, monkeypatch):
    calls = []

    def empty(url, ua, timeout):
        calls.append(url)
        return []

    monkeypatch.setattr(nominatim, "get_json", empty)
    assert nominatim.geocode("Homestay Không Tồn Tại XYZ", cfg, sleep=lambda s: None) is None
    assert nominatim.geocode("Homestay Không Tồn Tại XYZ", cfg, sleep=lambda s: None) is None
    assert len(calls) == 1  # the miss is cached, so the service is asked once


def test_a_body_that_is_not_a_list_is_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(nominatim, "get_json", lambda url, ua, timeout: {"error": "blocked"})
    with pytest.raises(Unavailable):
        nominatim.geocode("Bến xe Liên tỉnh", cfg, sleep=lambda s: None)
```

Thêm import ở đầu file test: `from live.http import Unavailable`

- [ ] **Step 8: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_geocode.py -q`
Expected: PASS (8 tests)

- [ ] **Step 9: Thêm geocode vào test gọi mạng thật**

Thêm vào `tests/live/test_live.py`:

```python
def test_nominatim_finds_a_place_in_dalat():
    from live import geocode
    p = geocode("Bến xe Liên tỉnh Đà Lạt", load_settings())
    assert p is not None
    assert 11.8 < p["lat"] < 12.1 and 108.3 < p["lng"] < 108.6, p
```

- [ ] **Step 10: Commit**

```bash
git add src/live/geocode tests/live/test_geocode.py tests/live/test_live.py tests/live/fixtures/nominatim_hit.json
git commit -m "feat(live): geocode through Nominatim, rate limited, misses cached"
```

---

### Task 6: Giờ mặt trời mọc và lặn

**Files:**
- Create: `src/live/sun.py`
- Test: `tests/live/test_sun.py`

**Interfaces:**
- Consumes: không có (thuần toán, không mạng, không cache).
- Produces: `live.sun.sun_times(d: date, lat: float, lng: float, tz_offset_h: float = 7.0) -> tuple[int, int] | None` — phút theo đồng hồ địa phương của mọc và lặn; `None` ở nơi/ngày mặt trời không mọc hoặc không lặn

- [ ] **Step 1: Viết test**

Tạo `tests/live/test_sun.py`:

```python
from datetime import date

from live.sun import sun_times

DALAT_LAT, DALAT_LNG = 11.9465, 108.4419


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def test_dalat_midsummer_sunrise_and_sunset_land_in_the_right_window():
    rise, set_ = sun_times(date(2026, 6, 21), DALAT_LAT, DALAT_LNG)
    assert 5 * 60 + 15 <= rise <= 5 * 60 + 40, hhmm(rise)
    assert 18 * 60 + 0 <= set_ <= 18 * 60 + 25, hhmm(set_)


def test_dalat_midwinter_sunrise_and_sunset_land_in_the_right_window():
    rise, set_ = sun_times(date(2026, 12, 21), DALAT_LAT, DALAT_LNG)
    assert 6 * 60 + 0 <= rise <= 6 * 60 + 25, hhmm(rise)
    assert 17 * 60 + 15 <= set_ <= 17 * 60 + 40, hhmm(set_)


def test_the_longest_day_of_the_year_is_in_june_not_december():
    june = sun_times(date(2026, 6, 21), DALAT_LAT, DALAT_LNG)
    december = sun_times(date(2026, 12, 21), DALAT_LAT, DALAT_LNG)
    assert (june[1] - june[0]) > (december[1] - december[0])


def test_sunrise_is_always_before_sunset_across_a_year():
    first = date(2026, 1, 1).toordinal()
    for offset in range(0, 365, 7):
        day = date.fromordinal(first + offset)
        rise, set_ = sun_times(day, DALAT_LAT, DALAT_LNG)
        assert rise < set_, day
        assert 10 * 60 < (set_ - rise) < 14 * 60, day  # the tropics never swing further than this


def test_on_the_equinox_at_the_equator_the_day_is_about_twelve_hours():
    rise, set_ = sun_times(date(2026, 3, 20), 0.0, 105.0, tz_offset_h=7.0)
    assert 11 * 60 + 50 <= (set_ - rise) <= 12 * 60 + 20


def test_the_polar_night_has_no_sunrise():
    assert sun_times(date(2026, 12, 21), 78.0, 15.0, tz_offset_h=1.0) is None
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_sun.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.sun'`

- [ ] **Step 3: Viết `src/live/sun.py`**

```python
"""Sunrise and sunset, computed here (NOAA solar position). No network, no cache, no new dependency.

Planning needs these to pin sunset places to the end of a day and misty places to its start.
"""

import math
from datetime import date

_J2000 = date(2000, 1, 1).toordinal()
_ZENITH = math.radians(90.833)  # 90°50': the sun's disc plus average refraction at the horizon


def _sun_position(days_since_j2000: float) -> tuple[float, float]:
    """Equation of time in minutes and solar declination in radians."""
    n = days_since_j2000
    mean_anomaly = math.radians((357.529 + 0.98560028 * n) % 360)
    mean_longitude = (280.459 + 0.98564736 * n) % 360
    ecliptic_longitude = math.radians((mean_longitude + 1.915 * math.sin(mean_anomaly)
                                       + 0.020 * math.sin(2 * mean_anomaly)) % 360)
    obliquity = math.radians(23.439 - 0.00000036 * n)
    declination = math.asin(math.sin(obliquity) * math.sin(ecliptic_longitude))
    right_ascension = math.degrees(math.atan2(math.cos(obliquity) * math.sin(ecliptic_longitude),
                                              math.cos(ecliptic_longitude))) % 360
    equation_of_time = 4 * ((mean_longitude - right_ascension + 180) % 360 - 180)
    return equation_of_time, declination


def sun_times(d: date, lat: float, lng: float, tz_offset_h: float = 7.0) -> tuple[int, int] | None:
    """Local clock minutes of sunrise and sunset, or None where the sun neither rises nor sets that day."""
    equation_of_time, declination = _sun_position(d.toordinal() - _J2000 + 0.5)
    phi = math.radians(lat)
    cos_hour_angle = ((math.cos(_ZENITH) - math.sin(phi) * math.sin(declination))
                      / (math.cos(phi) * math.cos(declination)))
    if not -1.0 <= cos_hour_angle <= 1.0:
        return None
    half_day_min = 4 * math.degrees(math.acos(cos_hour_angle))
    solar_noon_min = 720 - 4 * lng - equation_of_time + tz_offset_h * 60
    return round(solar_noon_min - half_day_min), round(solar_noon_min + half_day_min)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_sun.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/live/sun.py tests/live/test_sun.py
git commit -m "feat(live): local sunrise and sunset from the NOAA solar position"
```

---

### Task 7: Ngày lễ Việt Nam

**Files:**
- Create: `src/live/holidays.py`
- Create: `config/holidays.yaml`
- Test: `tests/live/test_holidays.py`

**Interfaces:**
- Consumes: không có.
- Produces: `live.holidays.holidays(dates: list[date], path: Path = PATH) -> dict[date, str]` — chỉ các ngày có trong file, map sang tên lễ

- [ ] **Step 1: Viết test**

Tạo `tests/live/test_holidays.py`:

```python
from datetime import date

import pytest

from live import holidays as mod


def test_a_listed_date_comes_back_with_its_name():
    got = mod.holidays([date(2026, 1, 1)])
    assert got == {date(2026, 1, 1): "Tết Dương lịch"}


def test_an_unlisted_date_is_simply_not_a_holiday():
    assert mod.holidays([date(2026, 3, 11)]) == {}


def test_a_mixed_list_keeps_only_the_holidays():
    got = mod.holidays([date(2026, 4, 30), date(2026, 5, 1), date(2026, 5, 2)])
    assert set(got) == {date(2026, 4, 30), date(2026, 5, 1)}


def test_an_empty_request_is_an_empty_answer():
    assert mod.holidays([]) == {}


def test_the_shipped_file_covers_the_fixed_date_holidays_of_2026():
    want = [date(2026, 1, 1), date(2026, 4, 30), date(2026, 5, 1), date(2026, 9, 2)]
    assert set(mod.holidays(want)) == set(want)


def test_tet_2026_is_several_days_long():
    span = [date(2026, 2, d) for d in range(14, 24)]
    got = mod.holidays(span)
    assert len(got) >= 5
    assert date(2026, 2, 17) in got  # mùng 1 Tết Bính Ngọ


def test_a_file_whose_keys_yaml_already_parsed_as_dates_still_loads(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text("holidays:\n  2026-01-01: Tết Dương lịch\n", encoding="utf-8")
    mod._table.cache_clear()
    assert mod.holidays([date(2026, 1, 1)], path=p) == {date(2026, 1, 1): "Tết Dương lịch"}
    mod._table.cache_clear()


def test_a_file_whose_keys_are_quoted_strings_still_loads(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text('holidays:\n  "2026-01-01": Tết Dương lịch\n', encoding="utf-8")
    mod._table.cache_clear()
    assert mod.holidays([date(2026, 1, 1)], path=p) == {date(2026, 1, 1): "Tết Dương lịch"}
    mod._table.cache_clear()
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_holidays.py -q`
Expected: FAIL với `ModuleNotFoundError: No module named 'live.holidays'`

- [ ] **Step 3: Viết `config/holidays.yaml`**

```yaml
# Vietnamese public holidays, hand-entered: the lunar ones have no formula here (docs/specs/PLANNING_SPEC.md).
# Lunar dates (Tết, Giỗ Tổ Hùng Vương) were taken from the 2026-2027 calendar; check them before a real trip.
# Planning uses these only as a crowd signal, never to open or close a place.
holidays:
  "2026-01-01": Tết Dương lịch
  "2026-02-16": Tết Nguyên Đán (29 tháng Chạp)
  "2026-02-17": Tết Nguyên Đán (mùng 1)
  "2026-02-18": Tết Nguyên Đán (mùng 2)
  "2026-02-19": Tết Nguyên Đán (mùng 3)
  "2026-02-20": Tết Nguyên Đán (mùng 4)
  "2026-04-26": Giỗ Tổ Hùng Vương
  "2026-04-30": Ngày Giải phóng miền Nam
  "2026-05-01": Quốc tế Lao động
  "2026-09-02": Quốc khánh
  "2027-01-01": Tết Dương lịch
  "2027-02-05": Tết Nguyên Đán (29 tháng Chạp)
  "2027-02-06": Tết Nguyên Đán (mùng 1)
  "2027-02-07": Tết Nguyên Đán (mùng 2)
  "2027-02-08": Tết Nguyên Đán (mùng 3)
  "2027-02-09": Tết Nguyên Đán (mùng 4)
  "2027-04-30": Ngày Giải phóng miền Nam
  "2027-05-01": Quốc tế Lao động
  "2027-09-02": Quốc khánh
```

- [ ] **Step 4: Viết `src/live/holidays.py`**

```python
"""Vietnamese public holidays from config/holidays.yaml.

Hand-entered on purpose: converting lunar dates would be a second calendar implementation, and the file is small.
A date the file does not list is not a holiday; the file is the whole truth.
"""

from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "config" / "holidays.yaml"


def _as_date(key) -> date:
    return key if isinstance(key, date) else date.fromisoformat(str(key))


@cache
def _table(path: Path) -> dict[date, str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {_as_date(k): str(v) for k, v in (doc.get("holidays") or {}).items()}


def holidays(dates: list[date], path: Path = PATH) -> dict[date, str]:
    """Only the listed dates, mapped to the holiday's name."""
    table = _table(path)
    return {d: table[d] for d in dates if d in table}
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live/test_holidays.py -q`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add src/live/holidays.py config/holidays.yaml tests/live/test_holidays.py
git commit -m "feat(live): Vietnamese holidays from a hand-entered config"
```

---

### Task 8: Public API của `src/live` + test bất biến

**Files:**
- Modify: `src/live/__init__.py`
- Test: `tests/live/test_boundaries.py`

**Interfaces:**
- Consumes: mọi thứ Task 1–7 tạo.
- Produces: `live.__all__ = ["Settings", "Unavailable", "geocode", "holidays", "load_settings", "route_shape", "sun_times", "travel_matrix"]` — đây là mặt tiếp xúc duy nhất `src/planning` được phép dùng ở Plan 2.

- [ ] **Step 1: Viết test bất biến**

Tạo `tests/live/test_boundaries.py`:

```python
"""The invariants that keep live context from becoming Place Intelligence (docs/specs/PLANNING_SPEC.md)."""

import ast
from pathlib import Path

import pytest

import live

SRC = Path(__file__).resolve().parents[2] / "src" / "live"
CORPUS_DIRS = ("data/intel", "data/serving", "data/gmaps", "data/tiktok", "data/review",
               "data\\intel", "data\\serving", "data\\gmaps")
OTHER_PACKAGES = {"corpus", "decision", "trip", "planning"}


def modules():
    return sorted(SRC.rglob("*.py"))


def test_there_is_something_to_check():
    assert len(modules()) >= 7


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_names_a_corpus_directory(path):
    text = path.read_text(encoding="utf-8")
    for bad in CORPUS_DIRS:
        assert bad not in text, f"{path.name} names {bad}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_imports_another_project_package(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & OTHER_PACKAGES), f"{path.name} imports {imported & OTHER_PACKAGES}"


def test_the_public_api_is_exactly_what_planning_may_use():
    assert set(live.__all__) == {"Settings", "Unavailable", "geocode", "holidays", "load_settings", "route_shape",
                                 "sun_times", "travel_matrix"}
    for name in live.__all__:
        assert hasattr(live, name), name


def test_the_only_thing_live_writes_is_its_own_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from live import cache
    cache.put("osrm", {"a": 1}, [[0]], "osrm")
    cache.put("geocode", {"q": "x"}, None, "nominatim")
    top = {p.relative_to(tmp_path).parts[0] for p in tmp_path.rglob("*") if p.is_file()}
    assert top == {"live"}
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/live/test_boundaries.py -q`
Expected: FAIL ở `test_the_public_api_is_exactly_what_planning_may_use` với `AttributeError: module 'live' has no attribute '__all__'`

- [ ] **Step 3: Viết `src/live/__init__.py` đầy đủ**

```python
"""Live Context: facts fetched per request from outside (docs/specs/PLANNING_SPEC.md §Live Context).

Three rules hold for everything in here:
  - it never writes Place Intelligence; the only thing it writes is its own cache under data/live/;
  - every value it returns carries `source` and `fetched_at`, so Planning can label it an estimate;
  - a source that does not answer raises Unavailable. Nothing here invents a value to fill a gap.
"""

from .geocode import geocode
from .holidays import holidays
from .http import Unavailable
from .osrm import route_shape, travel_matrix
from .settings import Settings
from .settings import load as load_settings
from .sun import sun_times

__all__ = ["Settings", "Unavailable", "geocode", "holidays", "load_settings", "route_shape", "sun_times",
           "travel_matrix"]
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/live -q`
Expected: PASS — toàn bộ `tests/live`

- [ ] **Step 5: Chạy toàn bộ test của repo**

Run: `python -m pytest -q`
Expected: PASS — không test cũ nào đỏ

- [ ] **Step 6: Commit**

```bash
git add src/live/__init__.py tests/live/test_boundaries.py
git commit -m "feat(live): public API plus the tests that pin the module's boundaries"
```

---

### Task 9: `entry_point` / `exit_point` trong Trip State

**Files:**
- Modify: `src/trip/state.py` (`SCALARS` dòng 34–35; `class TripState` dòng ~185–195; `def unknown_fields` dòng 371–374; `class Context` dòng ~379–392)
- Modify: `src/trip/values.py` (`def parse`, nhánh `base`, dòng 49–53)
- Modify: `src/trip/compile.py` (`Context(...)` dòng 27–30)
- Test: `tests/trip/test_entry_exit.py`

**Interfaces:**
- Consumes: `trip.state.Base`, `trip.state.Field`, `trip.state.apply`, `trip.state.Update`, `trip.compile.compile_search_input`.
- Produces:
  - `TripState.entry_point: Field[Base]`, `TripState.exit_point: Field[Base]`
  - `SearchInput.context.entry_point: Base | None`, `SearchInput.context.exit_point: Base | None`
  - `values.parse("entry_point", raw, catalog) -> Base` — khớp corpus thì có `place_id`, không khớp thì `Base(place_id=None, text=raw)`

- [ ] **Step 1: Viết test (gồm Review Focus #5)**

Tạo `tests/trip/test_entry_exit.py`:

```python
"""entry_point / exit_point: where the user enters and leaves the city (docs/specs/PLANNING_SPEC.md §Đầu vào)."""

from datetime import date

import pytest

from trip.compile import compile_search_input
from trip.state import Base, Evidence, TripState, Update, apply, settle, unknown_fields
from trip.values import parse

EV = Evidence(turn=1, quote="mình xuống bến xe Liên tỉnh")


def up(s, field, value=None, op="set", source="user"):
    return apply(s, Update(field=field, op=op, value=value, source=source,
                           confidence="high" if source == "user" else "medium", evidence=EV))


def minimal():
    s = up(TripState(), "start_date", date(2026, 12, 12))
    return up(up(s, "days", 3), "mobility", "motorbike")


def test_a_bus_station_the_corpus_does_not_hold_is_kept_as_plain_text(catalog):
    got = parse("entry_point", "Bến xe Liên tỉnh Đà Lạt", catalog)
    assert isinstance(got, Base)
    assert got.place_id is None                      # the corpus holds no bus stations, and nothing is invented
    assert got.text == "Bến xe Liên tỉnh Đà Lạt"     # the text survives for Planning to geocode


def test_both_points_reach_the_search_input():
    s = minimal()
    s = up(s, "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    s = up(s, "exit_point", Base(text="Sân bay Liên Khương"))
    si = compile_search_input(settle(s))
    assert si.context.entry_point.text == "Bến xe Liên tỉnh Đà Lạt"
    assert si.context.exit_point.text == "Sân bay Liên Khương"


def test_not_knowing_them_leaves_them_none_and_breaks_nothing():
    si = compile_search_input(settle(minimal()))
    assert si.context.entry_point is None and si.context.exit_point is None


def test_only_the_entry_point_is_known():
    s = up(minimal(), "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    si = compile_search_input(settle(s))
    assert si.context.entry_point is not None and si.context.exit_point is None


def test_the_user_can_skip_the_question_without_losing_the_field():
    s = up(minimal(), "entry_point", op="remove")
    assert s.entry_point.status == "skipped"
    assert compile_search_input(settle(s)).context.entry_point is None


def test_they_are_not_counted_as_unknowns_that_block_the_search():
    assert "entry_point" not in unknown_fields(settle(minimal()))
    assert "exit_point" not in unknown_fields(settle(minimal()))
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/trip/test_entry_exit.py -q`
Expected: FAIL — `parse` raise `ValueError` cho field lạ, và `TripState` chưa có field

- [ ] **Step 3: Thêm hai field vào `src/trip/state.py`**

Sửa `SCALARS` (dòng 34–35) thành:

```python
SCALARS = ("start_date", "month", "days", "people", "base", "entry_point", "exit_point", "mobility", "arrive_at",
           "leave_at", "day_end", "purpose", "pace", "max_leg_min", "crowd_tolerance", "novelty", "budget_vnd")
```

Trong `class TripState`, ngay dưới dòng `base: Field[Base] = Field[Base]()`, thêm:

```python
    entry_point: Field[Base] = Field[Base]()  # where the trip enters the city: station, airport, own vehicle
    exit_point: Field[Base] = Field[Base]()   # where it leaves; the last day has to get back here in time
```

Trong `class Context`, ngay dưới dòng `base: Base | None`, thêm:

```python
    entry_point: Base | None = None
    exit_point: Base | None = None
```

`unknown_fields` không đổi: hai field này không chặn tìm kiếm, nên không vào danh sách.

- [ ] **Step 4: Mở rộng nhánh `base` của `src/trip/values.py`**

Sửa dòng 49 từ `if field == "base":` thành:

```python
    if field in ("base", "entry_point", "exit_point"):
```

- [ ] **Step 5: Đưa hai field vào `src/trip/compile.py`**

Sửa `Context(...)` thành:

```python
        context=Context(start_date=v("start_date"), month=v("month"), days=v("days"), base=v("base"),
                        entry_point=v("entry_point"), exit_point=v("exit_point"),
                        mobility=v("mobility"), companions=tuple(sorted(v("companions") or ())), people=v("people"),
                        arrive_at=v("arrive_at"), leave_at=v("leave_at"), day_end=v("day_end"),
                        budget_vnd=v("budget_vnd"), experience=state.meta.experience),
```

- [ ] **Step 6: Chạy test, xác nhận pass**

Run: `python -m pytest tests/trip/test_entry_exit.py -q`
Expected: PASS (6 tests)

- [ ] **Step 7: Chạy toàn bộ test của `trip` và `decision`**

Run: `python -m pytest tests/trip tests/decision -q`
Expected: PASS — `SearchInput` có thêm field mặc định `None` nên `decision` không đổi hành vi

- [ ] **Step 8: Commit**

```bash
git add src/trip/state.py src/trip/values.py src/trip/compile.py tests/trip/test_entry_exit.py
git commit -m "feat(trip): carry the trip's entry and exit point into the Search Input"
```

---

### Task 10: Câu hỏi điểm vào/ra + cập nhật tài liệu

**Files:**
- Modify: `src/trip/questions.py` (thêm `ENTRY_POINTS` cạnh `VEHICLE` dòng ~57; thêm một câu vào `bank` dòng 273, ngay trước khối `want("times", ...)` dòng ~323)
- Modify: `docs/TRIP_UNDERSTANDING.md` (§4 Trip State, §11 Search Input)
- Modify: `AGENTS.md`, `README.md` (thêm `docs/specs/PLANNING_SPEC.md` vào bảng tài liệu)
- Test: `tests/trip/test_questions.py` (thêm test), `tests/trip/test_entry_exit.py` (thêm test)

**Interfaces:**
- Consumes: `trip.questions.bank` (hàm dựng câu tier-3, `src/trip/questions.py:273`), `trip.questions.Question`, `trip.questions.Chip`, `trip.questions.d`, hai field Task 9 thêm.
- Produces: `Question(qid="entry_exit", ...)` — câu multi hai hàng ("Tới Đà Lạt bằng", "Rời Đà Lạt từ"), chip ghi `entry_point` / `exit_point`, thêm `input="text"` để người dùng gõ nơi khác.

- [ ] **Step 1: Viết test**

Thêm vào `tests/trip/test_entry_exit.py`:

```python
from trip.questions import bank


def test_the_question_appears_once_the_trip_has_dates_and_a_length(catalog, cfg):
    qs = {q.qid for q in bank(settle(minimal()), catalog, cfg)}
    assert "entry_exit" in qs


def test_the_question_disappears_once_both_points_are_known(catalog, cfg):
    s = up(minimal(), "entry_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    s = up(s, "exit_point", Base(text="Bến xe Liên tỉnh Đà Lạt"))
    qs = {q.qid for q in bank(settle(s), catalog, cfg)}
    assert "entry_exit" not in qs


def test_asking_once_does_not_ask_again(catalog, cfg):
    from trip.state import with_meta
    s = with_meta(settle(minimal()), asked=("entry_exit",))
    assert "entry_exit" not in {q.qid for q in bank(s, catalog, cfg)}


def test_every_chip_of_the_question_writes_one_of_the_two_fields(catalog, cfg):
    q = next(q for q in bank(settle(minimal()), catalog, cfg) if q.qid == "entry_exit")
    assert q.multi is True
    assert set(q.single_rows) == {"Tới Đà Lạt bằng", "Rời Đà Lạt từ"}
    for chip in q.chips:
        fields = {dr.field for dr in chip.drafts}
        assert fields <= {"entry_point", "exit_point"} and fields
```

`bank` là hàm dựng câu tier-3 (`src/trip/questions.py:273`); nó tự lấy `done` từ `state.meta.asked | state.meta.skipped`, không nhận tham số `done`. `catalog` và `cfg` là fixture có sẵn ở `tests/trip/conftest.py:22-30`.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `python -m pytest tests/trip/test_entry_exit.py -q`
Expected: FAIL — chưa có câu `entry_exit`

- [ ] **Step 3: Thêm câu hỏi vào `src/trip/questions.py`**

Ngay trước khối `if want("times", ...)`, thêm:

```python
    if want("entry_exit", state.days.known and not (state.entry_point.known and state.exit_point.known)):
        out.append(Question(
            qid="entry_exit", group="A", cost=1.5, multi=True, input="text", input_field="entry_point",
            single_rows=("Tới Đà Lạt bằng", "Rời Đà Lạt từ"),
            text="Bạn tới Đà Lạt từ đâu, và rời từ đâu?",
            reason="Để ngày đầu và ngày cuối tính đúng đoạn từ nơi bạn xuống xe.",
            chips=tuple(Chip(id=f"in:{key}", label=label, row="Tới Đà Lạt bằng",
                             drafts=(d("entry_point", Base(text=label)),))
                        for key, label in ENTRY_POINTS)
                  + tuple(Chip(id=f"out:{key}", label=label, row="Rời Đà Lạt từ",
                               drafts=(d("exit_point", Base(text=label)),))
                          for key, label in ENTRY_POINTS)))
```

Và gần đầu file, cạnh `VEHICLE` (dòng ~57), thêm:

```python
# The common ways into Đà Lạt. The corpus holds none of them (it holds places visitors go to), so these are text
# that Planning geocodes; the question also takes free text for anything else.
ENTRY_POINTS = (
    ("bus_station", "Bến xe Liên tỉnh Đà Lạt"),
    ("airport", "Sân bay Liên Khương"),
    ("own_vehicle", "Tự lái, vào từ đèo Prenn"),
)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `python -m pytest tests/trip/test_entry_exit.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Chạy toàn bộ test của `trip`**

Run: `python -m pytest tests/trip -q`
Expected: PASS — nếu một test cũ đếm số câu tier-3 thì cập nhật con số đó trong test ấy, không nới điều kiện của nó

- [ ] **Step 6: Cập nhật `docs/TRIP_UNDERSTANDING.md`**

Trong §4 (Trip State), ở khối "Thông tin cơ bản", sửa dòng liệt kê thành:

```
├── Thông tin cơ bản   dates, duration, companions, base (chỗ ở), entry_point / exit_point (nơi vào / ra thành phố), mobility
```

Trong §11 (Search Input), thêm `entry_point`, `exit_point` vào bảng / khối `context`, kèm một dòng: "`entry_point` / `exit_point`: nơi người dùng vào và rời thành phố (bến xe, sân bay, tự lái). Chỉ là text + `place_id` nếu khớp corpus; Planning geocode chúng (`docs/specs/PLANNING_SPEC.md` §Đầu vào). Không biết thì ngày đầu / cuối chỉ cắt theo `arrive_at` / `leave_at` và được gắn cờ."

- [ ] **Step 7: Thêm spec vào bảng tài liệu**

Trong `AGENTS.md`, mục "Đọc khi cần", thêm dòng:

```markdown
- Planning & Validation + Live Context (địa điểm đã xác nhận → lịch trình đã kiểm, chỗ ở live): `docs/specs/PLANNING_SPEC.md`
```

Trong `README.md`, bảng "Tài liệu", thêm dòng:

```markdown
| `docs/specs/PLANNING_SPEC.md` | Thiết kế chi tiết Planning & Validation + Live Context: thuật toán, chỗ ở live, kiểm tra, độ vững |
```

- [ ] **Step 8: Chạy toàn bộ test của repo**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/trip/questions.py docs/TRIP_UNDERSTANDING.md AGENTS.md README.md tests/trip/test_entry_exit.py
git commit -m "feat(trip): ask where the trip enters and leaves the city"
```

---

## Sau khi plan này xong

`src/live` có public API đủ cho Plan 2, Trip State mang điểm vào/ra, và `docs/specs/PLANNING_SPEC.md` nằm trong bảng tài liệu chính thức. Hai việc **không** thuộc plan này, đã ghi trong spec, Plan 2 và Plan 3 làm:

- `live/weather` và `live/lodging`: Plan 3 (P5). Spec đã định nghĩa chữ ký; `config/live.yaml` đã có TTL cho cả hai.
- Đường lui khi OSRM chết (`travel_source = rough`): ở `src/planning`, Plan 2. `src/live` chỉ raise `Unavailable`.

Một chỗ spec cần sửa nhỏ khi plan này chạy: spec viết "TTL từng nguồn live; endpoint OSRM" nằm trong `config/planning.yaml`. Chúng nằm trong `config/live.yaml`, vì `src/live` không được đọc config của `planning` (phụ thuộc một hướng). Sửa câu đó trong `docs/specs/PLANNING_SPEC.md` §Cấu hình ở Task 1, Step 15, cùng commit đó.
