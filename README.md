# TripGuardian

Hệ thống place intelligence + lập lịch trình cá nhân hóa: giúp người dùng **chọn đúng địa điểm trước khi tạo lịch trình**, rồi kiểm tra tổ hợp đã chọn có đi được cùng nhau không. Phạm vi kiểm chứng ban đầu: Đà Lạt.

Bối cảnh sản phẩm, người dùng mục tiêu, phạm vi MVP: `docs/Project_Context.md`.

## Trạng thái

Có code crawl dữ liệu thô (`src/corpus/crawl/`). Trạng thái code theo từng tính năng ghi ở `docs/log/DEV_LOG.md`.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| `docs/Project_Context.md` | Vì sao, cho ai, User Profile, nguyên tắc, phạm vi MVP, thước đo |
| `docs/ARCHITECTURE.md` | Luồng hệ thống và quy tắc quyết định |
| `docs/CORPUS.md` | Tổng quan corpus Place Intelligence |
| `docs/specs/CORPUS_SPEC.md` | Thiết kế chi tiết corpus: vai trò model, gate, định tuyến, data model, phase |
| `docs/Role_Web_Functional_Design.md` | Chức năng Web theo vai trò và màn hình |
| `docs/UX_Design_Brief.md` | Brief UI/UX cho designer |
| `docs/LLM_PROVIDER.md` | Cấu hình LLM provider: endpoint, model, key, chứng chỉ |

Quy tắc làm việc (bắt buộc): `RULE.md`. Hướng dẫn cho agent: `AGENTS.md`.

## Cấu trúc dự kiến

```
src/offline/{adapters,orchestrator,discovery,resolution,evidence,intelligence}   # ghi Place Intelligence
src/online/{preferences,retrieval,context,planner}                               # đọc Place Intelligence, lập lịch trình
src/shared/{schemas,storage}
tests/{offline,online,fixtures}
```

Module chỉ giao tiếp qua public API (`api.py` / `interface.py`).

## Thiết lập

1. `cp .env.example .env` rồi điền key và model — ý nghĩa từng biến ở `docs/LLM_PROVIDER.md`.
2. Nếu gọi `llm.uit.edu.vn` lỗi chứng chỉ, tạo CA bundle một lần mỗi máy — xem `docs/LLM_PROVIDER.md` (phần chứng chỉ).
3. `pip install -e .` rồi `python -m corpus login tiktok` và `python -m corpus login gmaps` (tài khoản phụ).
4. Crawl: `python -m corpus tiktok --city dalat --headed`, `python -m corpus gmaps --city dalat --headed` (gặp captcha thì giải trong cửa sổ trình duyệt). Dữ liệu ở `data/` (xem `docs/specs/CORPUS_SPEC.md`, mục Dữ liệu thô).
