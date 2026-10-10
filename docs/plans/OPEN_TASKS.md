# Việc còn mở

File làm việc tạm (`RULE.md` §0.1): gom từ các plan / handoff đã xóa ngày 2026-10-10. Xong việc nào thì xóa dòng đó; hành vi đã ship mô tả ở tài liệu chính thức, không ở đây.

## Corpus (P1)

- TikTok `place_search` còn ~1.259 nơi, tạm dừng vì người dùng không kịp giải captcha — **hỏi trước khi chạy lại**. Video crawl ≤ 3 tab / tài khoản.
- TikTok clips: quyết lược đồ `ASR_CHECK` (`screen_text` tùy chọn) trên ~10 video; chạy lại `asr_check` tới khi `llm_errors` ≈ 0 → `place_verify` → `clips`; xử lý video quá dài (HTTP 400). Thứ tự bắt buộc: `poi_crawl → asr → asr_check → place_verify → clips` rồi mới `scripts/free_tiktok_clips.py --verified`.
- Build cuối và đo: `corpus build` → `judge audit` (`JUDGE_READ_ALL=1`) → `aggregate` → `serving` → `web/scripts/export_snapshot.py` → `decision evaluate` (0 violation, `filled_rate` ≥ 0,967).
- Vớt nhận định đúng bị Judge Gemma bỏ nhầm (~30%): nhãn sau `data/review/judge_labels.before_read_all.jsonl`, cần Judge khác họ model hoặc người.
- Chỗ ở `dalat_stay`: observe nhóm `stay` → aggregate → serving; ≥ `stay_min` chỗ ở trong vùng thì Planning tự dùng corpus.
- Ontology: đề xuất chuẩn hóa / mở rộng tag ở `docs/plans/TAG_EXPANSION_NOTES.md`, chờ chốt trước khi sinh dữ liệu Laya.
- Prompt Extractor tốn host (prefix cache, JSON gọn): đo bằng nhãn trước khi áp (`docs/LLM_PROVIDER.md` §Host LAN).

## Trip (P2)

- Người dùng cũ đồng ý điều khoản trước khi có ô "nhớ lựa chọn": cá nhân hóa tắt tới khi họ bật; cân nhắc lời nhắc một lần.
- Thẻ `geo` chưa có lựa chọn "dùng quê nhà" từ hồ sơ; gõ chữ trên thẻ `origin` / `lodging` / `inbound` / `outbound` đi vào chat.
- Chưa có giao diện xem / xóa từng mẫu đã nhớ; mẫu `avoid` cho nơi chưa nối từ Decision `drop`.
- Bench: `lost_questions`, `silent_overrides` chưa đo; coverage của Trip lệch `corpus.serving.check`.
- System One (Laya, Clef local) là thử nghiệm ngoài repo (`system_one_model/`, `training/` gitignored), chưa nối vào `src/`.

## Decision / Planning (P3, P4)

- `/geo`, `/lodging/suggest` chưa ưu tiên vùng (Photon `lat/lon` + `bbox` quanh Đà Lạt / Việt Nam).
- Sau khi chỗ ở crawl xong, phương án chưa tự chấm lại theo K ứng viên; Plan Output `lodging.candidates` rỗng.
- "Chọn giúp phần còn lại" (act ủy quyền rõ) chưa có. Repair ngày đi + đồng bộ lại Calendar sau sự cố chưa có.
- Đề xuất cải tiến Planning (data-driven, System One): `docs/plans/PLANNING_IMPROVEMENT_PROPOSAL.md`, chưa duyệt.

## Web, giọng nói, vận hành

- Chọn giọng TTS đã chốt `Trúc Ly`; kiểm lại worker `tts` sau reboot (tiến trình `nohup` không tự khởi động).
- `Assistant.tsx`: hàng chip bị cắt mép phải trong đĩa xoay.
- Chưa ai xem bằng trình duyệt thật: nút Dùng thử, thanh báo khách, thẻ chuyến xe / bay có bước xác nhận, công tắc "Nhớ lựa chọn", micro trợ lý (`node web/scripts/shots_app.mjs`).
- Xóa tài khoản test còn lại (`@test.local`, khách tạo khi kiểm deploy); giữ nguyên người dùng thật. Thứ tự: `events`, `notifications`, `feedback` → `trip_stops`, `checkins` → `trips`, `journeys`, `users`.
- Lỗi UX từ phiên test 09/10 chưa xác nhận đã sửa hết: lời lỗi cho dev lộ ra người dùng, thêm nơi trong chuyến, câu hỏi lặp, lỗi tiếng Anh ở chỗ ở.
- 20 test cần Playwright headless (`tests/crawl/common`, `tests/crawl/gmaps`) fail trên gpu156 vì thiếu `chromium_headless_shell`.
