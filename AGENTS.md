# Hướng dẫn cho agent

Hệ thống place intelligence + lập lịch trình cá nhân hóa.

**Bắt buộc tuân theo:** `RULE.md`. Rule thường trực chỉ nằm một chỗ ở đó; `CLAUDE.md` chỉ import file này.

**Mục lục tài liệu, cách thiết lập, cách chạy, cách test:** `README.md`. Không chép danh sách tài liệu vào đây.

## Vào việc từ đâu

| Việc | Đọc |
|---|---|
| Hiểu toàn hệ thống trước khi sửa | `docs/ARCHITECTURE.md` |
| Sửa một giai đoạn | tài liệu của chính giai đoạn đó (`docs/P1_CORPUS.md` … `docs/P5_COMPANION.md`) — mỗi file có mục module / CLI và API trỏ thẳng vào code |
| Biết code đã làm gì, đã sửa gì | `docs/log/DEV_LOG.md` (chỉ khi cần) |
| Đổi prompt, model, key | `docs/LLM_PROVIDER.md` |
| Sửa Web | `docs/WEB.md` (§6 = màn nào ở file nào), `docs/UI_DESIGN.md` |
| Việc còn mở | `docs/plans/OPEN_TASKS.md` |

## Bất biến không được phá

- Tài liệu viết **tiếng Việt**; code, comment, identifier, tên file viết **tiếng Anh** (`RULE.md` §0).
- Offline ghi Place Intelligence. Online chỉ đọc nó; online chỉ ghi lịch trình và user / session profile.
- Không bao giờ bịa địa điểm. Không có bằng chứng → `unknown`, không phải `false`. Hard constraint fail-closed.
- Physical constraint không có đường code nào nới được.
- User Profile là prior, không phải fact hay constraint: bối cảnh chuyến đi hiện tại thắng, `unknown` ≠ không thích, đã đến ≠ đã thích.
- Module **chỉ** giao tiếp qua public API (`__init__.py`). Không deep import.
- Gọi model theo **vai trò** (ASR, Extractor, Judge, Agent); model cụ thể nằm trong config, key trong `.env`.
- Mỗi nguồn ngoài (TikTok, Google, …) có module và thư mục dữ liệu riêng; không gộp.

Lỗi lặp lại của agent được ghi làm bằng chứng ở `docs/log/AGENT_FAILURES.md` trước khi được nâng thành rule.
