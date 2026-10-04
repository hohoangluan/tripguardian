# TripGuardian

> **Dự án học tập, phi thương mại.** Không dùng code, dữ liệu hay nội dung crawl (review Google Maps, video và bình luận TikTok) cho mục đích thương mại. Nội dung crawl thuộc về tác giả gốc và chỉ dùng cho nghiên cứu trong dự án này.

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
| `docs/UI_SPEC_LANDING.md` | Đặc tả landing: thế giới 3D, ngân sách chữ, animation |
| `docs/LLM_PROVIDER.md` | Model nào đảm nhận vai trò nào: endpoint, key, chứng chỉ, ASR local |
| `docs/log/DEV_LOG.md` | Nhật ký **code đang có gì** theo từng tính năng |
| `docs/log/AGENT_FAILURES.md` | Nhật ký lỗi của coding agent, làm bằng chứng trước khi nâng thành rule |

Quy tắc làm việc (bắt buộc): `RULE.md`. Hướng dẫn cho agent: `AGENTS.md`.

## Thiết lập

Mục tiêu: clone code, tải gói dữ liệu, chạy được cả hệ thống như máy đang phát triển. Dữ liệu không nằm trong git.

**Cần cài trước:** Python ≥ 3.12 (đang dùng 3.13), Node ≥ 20.19 (đang dùng 24), Git Bash (Windows; `run.sh` là shell script, dùng `netstat`/`taskkill`), Google Chrome bản thường (Playwright mở Chrome qua `channel="chrome"`), Docker (chỉ cho OSRM). Chỉ khi crawl: ffmpeg trên `PATH`, GPU cho ASR.

```sh
git clone https://github.com/hohoangluan/tripguardian && cd tripguardian
python -m venv .venv && source .venv/Scripts/activate   # Linux/macOS: .venv/bin/activate
pip install -e ".[dev]"                                 # thêm .[asr] chỉ khi chạy ASR; chunkformer: pip install --no-deps
python -m playwright install chromium                    # browser headless cho test parser và crawl
cd web && npm install && cd ..
cp .env.example .env                                     # điền key: docs/LLM_PROVIDER.md
```

1. **Dữ liệu.** Tải `tripguardian-data-<ngày>.zip` mới nhất từ [Drive của nhóm](https://drive.google.com/drive/folders/1LeEgIdoioyCAM64WV3VLGeKYA-X5yEGT?usp=sharing), giải nén **tại thư mục gốc repo**: `python -m zipfile -e tripguardian-data-<ngày>.zip .` — gói trả về đúng chỗ `data/`, `web/public/data/snapshot.json` (dữ liệu web hiển thị) và `tests/fixtures/{gmaps,tiktok}` (trang crawl thật cho test parser). Mấy file này trích review và tài khoản người thật nên không nằm trong repo public. Gói không có `video.mp4` của TikTok (chỉ bước ASR khi crawl cần); bản `--no-photos` không có ảnh Maps, khi đó `/admin/labels` không hiện ảnh.
2. **Key.** Trip Understanding, chọn câu hỏi và mọi phase cần model gọi API UIT, chỉ trả lời trong mạng campus; key và endpoint ở `.env`. Lỗi chứng chỉ `llm.uit.edu.vn`: tạo CA bundle một lần mỗi máy — `docs/LLM_PROVIDER.md` §Chứng chỉ TLS.
3. **OSRM** (thời gian di chuyển cho Planning): `bash scripts/osrm_setup.sh` một lần mỗi máy — tải OSM Việt Nam, dựng chỉ mục vào `osrm-data/`, mở `127.0.0.1:5000`. Lần sau chỉ cần chạy lại container (dòng `docker run ... -p 127.0.0.1:5000:5000` cuối script). Không có OSRM thì Planning ước lượng thô và gắn cảnh báo. Endpoint và TTL ở `config/live.yaml`; `LIVE_CONTACT` trong `.env` là liên hệ gửi kèm request.
4. **Chỉ khi crawl:** đăng nhập tài khoản phụ một lần mỗi máy, `python -m corpus login tiktok`, `python -m corpus login gmaps` (profile lưu ở `.browser/`, đã gitignore). Chạy dịch vụ và Planning lodging không cần đăng nhập.

Người giữ dữ liệu tạo gói mới: `python scripts/pack_data.py [--no-photos] [--out <thư mục>]` (cái gì bị bỏ và vì sao: docstring của script), rồi đưa zip lên Drive. Sửa `data/` xong mà web cần thấy: `python web/scripts/export_snapshot.py` trước khi đóng gói.

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

Log ở `logs/run/<tên>.log`. Web đọc địa điểm từ `web/public/data/snapshot.json` (trong gói Drive); sinh lại bằng `python web/scripts/export_snapshot.py` sau khi aggregate. Ảnh bìa (ảnh Maps / frame clip không có người) nằm ở `web/public/data/covers.json`, sinh bằng `python web/scripts/pick_covers.py` (YOLO, chạy GPU khoảng 1 giờ; `--resume` chạy tiếp chỗ dừng).

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
python -m pytest -q                      # không gọi mạng; thiếu gói Drive thì test parser Maps/TikTok tự skip
python -m pytest -q tests/planning        # một giai đoạn
python -m pytest -m live tests/trip/test_live.py   # gọi model thật, chạy tay
```

Test gọi mạng hoặc model thật nằm sau marker `live` và bị `addopts` loại khỏi lần chạy mặc định (`pyproject.toml`).

## Làm việc nhóm

- Mỗi task một branch từ `main` (`feat/<giai-đoạn>-<việc>`, `fix/...`), mở PR vào `main`; không push thẳng `main`.
- Trước khi mở PR: `python -m pytest -q` xanh. CI (`.github/workflows/test.yml`) chạy đúng lệnh này trên mỗi PR.
- Bắt buộc theo `RULE.md`: tài liệu tiếng Việt, code tiếng Anh, chỉ gọi module khác qua `__init__.py`, sửa tài liệu của giai đoạn khi đổi hành vi.
- Không commit `.env`, `data/`, `.browser/`, `logs/`, `snapshot.json`, `tests/fixtures/{gmaps,tiktok}` (đã gitignore). Repo public: không đưa nội dung crawl (review, bình luận, tên tài khoản người thật) vào git; dữ liệu chung đi qua gói zip ở §Thiết lập.

## Ranh giới

Mỗi giai đoạn chỉ giao tiếp với giai đoạn khác qua public API của package (`__init__.py`), không deep import; mỗi nguồn dữ liệu ngoài có module và thư mục dữ liệu riêng. Chi tiết và lý do: `RULE.md` §2, `docs/ARCHITECTURE.md` §3.
