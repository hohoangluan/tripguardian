# Hướng dẫn cho agent

Hệ thống place intelligence + lập lịch trình cá nhân hóa.

**Bắt buộc tuân theo:** `RULE.md`

**Đọc khi cần (không chép nội dung vào file này):**
- Sản phẩm: vì sao, cho ai, User Profile, nguyên tắc, phạm vi MVP, thước đo: `docs/Project_Context.md`
- Kiến trúc: luồng hệ thống và quy tắc quyết định: `docs/ARCHITECTURE.md`
- Corpus Place Intelligence: `docs/CORPUS.md` (tổng quan), `docs/specs/CORPUS_SPEC.md` (thiết kế chi tiết: vai trò model, gate, định tuyến, data model, phase)
- Chức năng Web theo vai trò (quyền, từng màn làm gì): `docs/Role_Web_Functional_Design.md`
- Brief UI/UX cho designer (nguyên tắc, cách hiển thị dữ liệu, ràng buộc): `docs/UX_Design_Brief.md`
- Nhật ký tính năng / trạng thái code: `docs/log/DEV_LOG.md` (chỉ đọc khi người dùng yêu cầu, hoặc khi cần tìm hiểu code đã sửa gì / thay đổi gì)
- Cấu hình LLM provider (endpoint, chọn model, key, lưu ý): `docs/LLM_PROVIDER.md`
- Nhật ký lỗi của agent (bằng chứng trước khi nâng thành rule): `docs/log/AGENT_FAILURES.md`

`CLAUDE.md` chỉ import file này. Rule thường trực chỉ nằm một chỗ trong `RULE.md`.

## Tóm tắt (xem RULE.md + Project_Context.md + ARCHITECTURE.md)

- Tài liệu viết **tiếng Việt**. Code, comment, identifier, tên file viết **tiếng Anh** (`RULE.md` §0).
- Offline ghi Place Intelligence. Online chỉ đọc nó; online chỉ ghi lịch trình và user/session profile (khi người dùng đồng ý).
- Không bao giờ bịa ra địa điểm. Không có bằng chứng → không phải fact. Hard constraint fail-closed.
- User Profile là prior cá nhân hóa, không phải fact hay constraint: bối cảnh chuyến đi hiện tại thắng, `unknown` ≠ không thích, đã đến ≠ đã thích, một sự kiện không ghi đè profile dài hạn.
- Module **chỉ** giao tiếp qua public API của module (`__init__.py`). Không deep import.
- Gọi model theo **vai trò** (Extractor, Judge, ASR); model cụ thể nằm trong config. Key để trong `.env`, không hardcode. Xem `docs/LLM_PROVIDER.md`.
