# TripGuardian

Hệ thống place intelligence + lập lịch trình cá nhân hóa: giúp người dùng **chọn đúng địa điểm trước khi tạo lịch trình**, rồi kiểm tra tổ hợp đã chọn có đi được cùng nhau không. Phạm vi kiểm chứng ban đầu: Đà Lạt.

Bốn giai đoạn, mỗi giai đoạn một package và một tài liệu:

```text
Place Intelligence  src/corpus/   offline: địa điểm → fact / signal / estimate có bằng chứng
Trip Understanding  src/trip/     người dùng cần gì cho chuyến này → Search Input
Place Decision      src/decision/ → shortlist → người dùng tuyển chọn → Decision Output
Planning & Valid.   src/planning/ + src/live/ → phương án, chỗ ở, độ vững → Plan Output
```

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| `docs/Project_Context.md` | Vì sao, cho ai, User Profile, nguyên tắc sản phẩm, phạm vi MVP, thước đo |
| `docs/ARCHITECTURE.md` | Bản đồ hệ thống: bốn giai đoạn, ranh giới module, constraint, cấu hình, quyết định thiết kế |
| `docs/CORPUS.md` | Place Intelligence: nguồn, vai trò model, pipeline, gate, data model, CLI, đo chất lượng |
| `docs/TRIP_UNDERSTANDING.md` | Trip State, chọn câu hỏi, ngân hàng câu hỏi, Search Input, CLI và API |
| `docs/PLACE_DECISION.md` | Sàng lọc fail-closed, xếp hạng, đa dạng, khả thi của tổ hợp, Decision Output, CLI và API |
| `docs/PLANNING.md` | Live Context, chia ngày, thứ tự, chỗ ở live, độ vững, dự phòng, Plan Output, CLI và API |
| `docs/Role_Web_Functional_Design.md` | Chức năng Web theo vai trò, từng màn, và màn nào nằm ở file nào |
| `docs/UX_Design_Brief.md` | Brief UI/UX: nguyên tắc, cách hiển thị chất lượng dữ liệu, hệ thị giác |
| `docs/UI_SPEC_USER_WEB.md` | Đặc tả trang User Web cho designer / Figma |
| `docs/LLM_PROVIDER.md` | Model nào đảm nhận vai trò nào: endpoint, key, chứng chỉ, ASR local |
| `docs/log/DEV_LOG.md` | Nhật ký **code đang có gì** theo từng tính năng |
| `docs/log/AGENT_FAILURES.md` | Nhật ký lỗi của coding agent, làm bằng chứng trước khi nâng thành rule |

Quy tắc làm việc (bắt buộc): `RULE.md`. Hướng dẫn cho agent: `AGENTS.md`.

## Thiết lập

1. `cp .env.example .env` rồi điền key và model — ý nghĩa từng biến ở `docs/LLM_PROVIDER.md`.
2. Nếu gọi `llm.uit.edu.vn` lỗi chứng chỉ, tạo CA bundle một lần mỗi máy — `docs/LLM_PROVIDER.md` §Chứng chỉ TLS.
3. `pip install -e .` (thêm `.[dev]` cho pytest, `.[asr]` cho ASR local).
4. `cd web && npm install`.
5. Đăng nhập tài khoản phụ, một lần mỗi máy: `python -m corpus login tiktok`, `python -m corpus login gmaps`.
6. Thời gian di chuyển cho Planning: `bash scripts/osrm_setup.sh` một lần mỗi máy (cần docker; tải OSM Việt Nam, dựng chỉ mục, rồi mở `127.0.0.1:5000`). Không chạy OSRM thì Planning vẫn chạy ở chế độ ước lượng thô và gắn cảnh báo. Endpoint và TTL ở `config/live.yaml`; `LIVE_CONTACT` trong `.env` là liên hệ gửi kèm request.

## Chạy

```sh
./run.sh start   # 4 API Python + web dev server, in ra URL khi mọi cổng đã trả lời
./run.sh stop    # dừng mọi tiến trình script này khởi động
```

| Dịch vụ | Cổng | Lệnh tương đương |
|---|---|---|
| Web (Vite) | 5173 | `http://127.0.0.1:5173/app` · `/admin` |
| Trip Understanding | 8766 | `python -m trip serve` |
| Place Decision | 8767 | `python -m decision serve` |
| Planning | 8768 | `python -m planning serve` |
| Trang review / gán nhãn | 8765 | `python -m corpus review` |

Log ở `logs/run/<tên>.log`. Web cần `web/public/data/snapshot.json` để hiển thị địa điểm: `python web/scripts/export_snapshot.py` sau khi aggregate.

## Xây dữ liệu và chạy từng bước

Lệnh đầy đủ của từng giai đoạn nằm trong tài liệu của giai đoạn đó. Đường chính:

```sh
# 1. Place Intelligence (docs/CORPUS.md §CLI)
python -m corpus gmaps all --city dalat --headed     # search → filter → counts → list → crawl → qc → observe
python -m corpus gmaps photos && python -m corpus gmaps photo_observe
python -m corpus tiktok all --city dalat --headed
python -m corpus aggregate && python -m corpus serving

# 2. Đo xem corpus đã đủ cho Place Decision chưa (docs/PLACE_DECISION.md §17)
python -m decision evaluate                          # 30 Trip State ẩn → data/decision/eval.json

# 3. Lập lịch trình từ một Decision Output (docs/PLANNING.md §CLI và API)
python -m planning build    <decision_output.json>
python -m planning variants <decision_output.json> [--weather forecast.json]
python -m planning lodging  <decision_output.json>   # chỗ ở cạnh tranh làm neo mỗi ngày
python -m planning evaluate                          # 30 chuyến ẩn qua Decision → Planning
```

Phase cần model cần mạng UIT; gặp captcha thì giải trong cửa sổ trình duyệt (`--headed`). `evaluate` của Planning cần OSRM đang chạy và không chạy trong CI.

## Test

```sh
python -m pytest -q                      # 1028 test, không gọi mạng
python -m pytest -q tests/planning        # một giai đoạn
python -m pytest -m live tests/trip/test_live.py   # gọi model thật, chạy tay
```

Test gọi mạng hoặc model thật nằm sau marker `live` và bị `addopts` loại khỏi lần chạy mặc định (`pyproject.toml`).

## Ranh giới

Mỗi giai đoạn chỉ giao tiếp với giai đoạn khác qua public API của package (`__init__.py`), không deep import; mỗi nguồn dữ liệu ngoài có module và thư mục dữ liệu riêng. Chi tiết và lý do: `RULE.md` §2, `docs/ARCHITECTURE.md` §3.
