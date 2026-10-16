# Kế hoạch Trip Understanding phần 3

Mục tiêu: thực hiện contract kiến trúc §5.4–5.5, giữ các bất biến §1–4. Thiết kế và test do Claude cung cấp; triển khai trực tiếp trong phiên hiện tại theo yêu cầu, không git, server, model hay network; không sửa test mới.

- [x] Đọc contract, public API, code card/question/engine/agent và test; chạy test mới để ghi nhận lỗi ban đầu.
- [x] Thêm `deck.py` (Option, Tab, Deck, build, confirm_tabs), `required.py` (bảy tab từ readiness), `ask.py` (hậu kiểm writes, số nơi và tập nơi). Đọc pace từ YAML bằng settings. Kiểm chứng `test_redesign_deck.py`.
- [x] Nối ask_user/tool schema/prompt; lưu Deck trong SessionStore; engine xử lý option/skip/other và trả JSON không chứa writes. Giữ ask look và dữ liệu legacy. Kiểm chứng deck và các test engine/agent hiện có.
- [x] Sửa apply để busy cộng dồn/bỏ trùng, days gộp index, periods cộng dồn, visit gộp key. Kiểm chứng DK18.
- [x] Sửa R5 tại ranh giới nhận tool args trước khi lưu history; sửa R6 ở prepass và chip đoán; R7 xác định ngôn ngữ trong code/prompt/guard; R8 trim mọi reply trước lưu/phát cuối. Kiểm chứng `test_redesign_review2.py`.
- [x] Chạy `.venv/bin/python -m pytest -q -p no:cacheprovider tests/trip tests/planning tests/decision`; chỉ cập nhật test cũ được §5.4 thay thế và liệt kê từng thay đổi. Không nới safety.
- [x] Review các file đã sửa, ghi quyết định còn mở, bất đồng test và kết quả vào `logs/sol_out/trip_redesign_p3_report.md`.

Bất đồng đã thấy: DK3/DK4 tìm pace ở vị trí 5 khi còn thiếu 7 required; DK16 tìm agent khi 4 tab đầu đã dành hết cho required. Triển khai ưu tiên contract giới hạn 4 tab và required trước agent; không sửa các test này.

Kiểm chứng chưa xanh toàn bộ: bốn test deck giữ nguyên có bất đồng/fixture lỗi; xem báo cáo `logs/sol_out/trip_redesign_p3_report.md` và log pytest để phân biệt lỗi đã biết, socket sandbox và timeout planning.
