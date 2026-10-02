# Kế hoạch: nâng chất lượng corpus cho Place Decision

Plan làm việc tạm (`RULE.md` §0.1): khi xong từng việc, gộp phần còn giá trị vào `docs/specs/CORPUS_SPEC.md` / `docs/CORPUS.md` / `docs/log/DEV_LOG.md`, xóa mục tương ứng ở đây; hết việc thì xóa file.

Hiện trạng (2026-10-02, trưa): code của V1–V6 đã xong và đã ghi vào `CORPUS_SPEC.md` §4–§5 + `DEV_LOG.md` (corpus-observe, corpus-aggregate, corpus-review, corpus-observe-tiktok, corpus-serving). Còn lại là việc máy chạy, việc người, và hai quyết định.

## Trạng thái chạy máy (2026-10-02 14:40) — session khác tiếp tục từ đây

Mọi thứ tiếp tục từ file trên đĩa; chạy lại lệnh là đi tiếp. Gemma (UIT) chỉ vào được trên mạng campus và đã đứt 3 lần trong ngày; script tự chờ mạng.

| Việc | Lệnh | Tiến độ | Ghi chú |
|---|---|---|---|
| Observe Maps ontology v7 | `sh scripts/rerun_observe.sh` (log `logs/rerun_observe.log`, đích `RERUN_DONE`) | ~450 / 1.437 nơi, ~1,4 nơi/phút | eval prompt 37/37; chạy xong tự aggregate → serving → evaluate. Bản cũ ở `data/gmaps/observations_before_v6/` |
| TikTok: ASR + kiểm + xác minh + observe | `sh scripts/tiktok_now.sh` (log `logs/tiktok_now.log`, đích `TIKTOK_NOW_DONE`) | observe 294 nơi xong; `asr_check` / `place_verify` đang chạy | 475 video chưa có transcript; ~850 video đã tìm thấy chưa tải (`tiktok place_crawl` dùng chung profile TikTok với `place_search`: chạy khi không có `place_search`) |
| Crawl ảnh Maps | `python -m corpus gmaps photos` | **TẠM DỪNG** 178 / 1.438 nơi | dừng vì RAM chỉ còn ~1 GB (44 tiến trình Chrome) và 0,2 nơi/phút; nên chạy lại khi máy rảnh hoặc giảm `photo_tabs` (config/queries.yaml, hiện 6) xuống 3 |
| Đọc ảnh → aggregate → serving → evaluate | `sh scripts/after_photos.sh` (đích `AFTER_PHOTOS_DONE`) | đang chờ | chờ `AFTER_RERUN_DONE` trong log và dòng "done, the rest in errors" của `logs/gmaps_photos.log` (xuất hiện khi `gmaps photos` chạy hết) |
| **TikTok Gemma tạm dừng** (15:15, người dùng ưu tiên Maps) | `sh scripts/tiktok_now.sh`, sau đó `sh scripts/after_rerun.sh` | `tiktok_now.sh` và `after_rerun.sh` đã bị dừng | chỉ khởi động lại SAU `RERUN_DONE` (dòng trong `logs/rerun_observe.log`): chúng dùng chung key Gemma với observe Maps. `after_photos.sh` đang chờ `AFTER_RERUN_DONE` do `after_rerun.sh` in: nếu không chạy `after_rerun.sh` thì `after_photos.sh` sẽ chờ mãi, hãy chạy `sh scripts/after_rerun.sh` rồi để `after_photos.sh` chạy tiếp |
| Sau `after_rerun.sh` | `sh scripts/after_rerun.sh` (đích `AFTER_RERUN_DONE`) | đang chờ `RERUN_DONE` | TikTok observe + aggregate + serving + evaluate |

Chạy tách (Windows): `Start-Process -WindowStyle Hidden -FilePath D:\AppDownload\Gitinash.exe -ArgumentList "-c","'/d/Study/mlai/tripguardian/scripts/<tên>.sh 2> logs/<tên>.err'"` từ thư mục tripguardian. Đừng chạy hai bản cùng một script. Nút thắt hiện tại: key Gemma 40 call dùng chung (observe Maps, TikTok `asr_check` / `place_verify` / `observe`, `PHOTO_OBSERVE`) + RAM.

Việc nên làm khi máy rảnh: (1) `python -m corpus gmaps photos` cho hết 1.438 nơi (khoảng 8–10 giờ ở 6 tab nếu RAM đủ); (2) `python -m corpus gmaps photo_observe --limit 20` xem chất lượng trước khi chạy hết (ảnh cận cảnh món ăn đôi khi vẫn ra `setting = indoor`); (3) sau `AFTER_PHOTOS_DONE`: đo lại độ phủ `steep_or_stairs` / `rough_road_access` và số chuyến đủ shortlist ở `data/serving/eval.json`.

## Việc người

- **Gán nhãn** (`python -m corpus review` + `cd web && npm run dev`, `/admin/labels`): ≥ 30 nhãn đúng/sai cho mỗi giá trị quan trọng; ưu tiên `steep_or_stairs`, `long_walk` (cả `absent`), `weather_exposed`, `booking_needed`, `entry_fee`, `visit_duration`, suitability, rồi nguồn TikTok. Nhãn khóa theo nội dung nên gán ngay bây giờ vẫn giữ sau lần chạy lại (trừ khẳng định lần chạy mới không còn tạo). Sau khi gán: `python -m corpus aggregate && python -m corpus serving && python -m corpus evaluate`.
- Nghiệm thu V1: 5 feature đã sửa (`condition_change`, `long_walk`, `weather_exposed`, `booking_needed`, `visit_duration`) đạt ≥ 85% trên nhãn.

## Quyết định đã chốt

- 2026-10-02: feature chỉ có `present` dùng làm ràng buộc cứng → thêm giá trị phủ định (ontology v7: `tourist_trap`, `rough_road_access`, `cash_only` = `absent`). Effort thiếu `absent` → crawl ảnh Maps (V4b, đang chạy).

## Quyết định cũ (đã xử lý ở trên)

1. **Feature chỉ có `present`** (`tourist_trap`, `rough_road_access`, `cash_only`…): theo luật "không nhắc không phải âm", ràng buộc cứng "không chặt chém" / "không đường xấu" không bao giờ `pass`, nên `evaluate` cho 0 ứng viên chính ở các chuyến đó. Lựa chọn: (a) giữ fail-closed, chỉ hiển thị mục "chưa xác minh"; (b) coi "≥ N người viết (vd 50) mà không ai nhắc" là `pass` kèm cờ; (c) thêm giá trị phủ định vào ontology (`tourist_trap = absent`: "giá niêm yết rõ, không ép mua").
2. **Effort `absent` hiếm** (13 nơi `steep_or_stairs = absent` trên 1.437): chuyến có người lớn tuổi / xe lăn gần như không có ứng viên chính. Nguồn bổ sung: TikTok (đang chạy, chỉ cho `present` từ ảnh), V4b ảnh Maps (chưa làm), hoặc thông tin chủ quán / người kiểm tra.

## Chưa làm

- **Ảnh chưa chứng minh được `absent`** (không có bậc / đường bằng): ảnh chỉ cho `present`. Độ phủ `steep_or_stairs = absent` vẫn phụ thuộc review; đo lại sau `AFTER_PHOTOS_DONE`.
- **TikTok crawl**: `place_search` mới ~450 / 1.438 nơi (memory `tiktok-crawl-resume`); mỗi lần có thêm cặp `place_verify` thì chạy lại `python -m corpus tiktok observe` (cache theo nơi) rồi aggregate → serving → evaluate.
- Labels cho TikTok đã có; precision theo nguồn ở `stats.by_source`. `servable` hiện dùng precision chung của (feature, value) cho mọi nguồn.
- `evaluate` chưa có chỉ số "kết quả đổi hợp lý khi đổi preference" và "unsupported claim rate" (cần Place Decision thật).

## Ghi chú vận hành

- Gemma (UIT) chỉ truy cập được trên mạng UIT; key chung 40 call đồng thời: không chạy TikTok observe / `place_verify` song song với `gmaps observe` (429).
- 9router (`cx/gpt-5.6-*`) thử làm extractor 2026-10-02: 3–4 phút một lô, `REVIEW_VERIFY` lỗi → không dùng cho chạy toàn bộ.
- Docs `CORPUS_SPEC.md`, `CORPUS.md`, `PLACE_DECISION.md`, `DEV_LOG.md` còn sửa đổi chưa commit của session khác (phần crawl, vai trò model, data layout); khi commit docs chỉ stage hunk của mình.
