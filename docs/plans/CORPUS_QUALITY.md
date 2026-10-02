# Kế hoạch: nâng chất lượng corpus cho Place Decision

Plan làm việc tạm (`RULE.md` §0.1): khi xong từng việc, gộp phần còn giá trị vào `docs/specs/CORPUS_SPEC.md` / `docs/CORPUS.md` / `docs/log/DEV_LOG.md`, xóa mục tương ứng ở đây; hết việc thì xóa file.

Hiện trạng (2026-10-02, trưa): code của V1–V6 đã xong và đã ghi vào `CORPUS_SPEC.md` §4–§5 + `DEV_LOG.md` (corpus-observe, corpus-aggregate, corpus-review, corpus-observe-tiktok, corpus-serving). Còn lại là việc máy chạy, việc người, và hai quyết định.

## Đang chạy (máy)

- `scripts/rerun_observe.sh` (bắt đầu 09:10): eval prompt 29/29 → observe Maps ontology v6 trên 1.437 nơi (~3,5 nơi/phút, ~6–7 giờ) → aggregate → serving → evaluate. Log `logs/rerun_observe.log`, kết thúc bằng `RERUN_DONE`. Bản observation cũ: `data/gmaps/observations_before_v6/`.
- `scripts/after_rerun.sh`: chờ `RERUN_DONE` rồi TikTok observe → aggregate → serving → evaluate, in `AFTER_RERUN_DONE`.
- Cả hai chạy tách (`Start-Process`), sống qua khi đóng phiên Claude; cần mạng UIT. Chết giữa chừng thì chạy lại script: mọi bước tiếp tục từ file trên đĩa.

## Việc người

- **Gán nhãn** (`python -m corpus review` + `cd web && npm run dev`, `/admin/labels`): ≥ 30 nhãn đúng/sai cho mỗi giá trị quan trọng; ưu tiên `steep_or_stairs`, `long_walk` (cả `absent`), `weather_exposed`, `booking_needed`, `entry_fee`, `visit_duration`, suitability, rồi nguồn TikTok. Nhãn khóa theo nội dung nên gán ngay bây giờ vẫn giữ sau lần chạy lại (trừ khẳng định lần chạy mới không còn tạo). Sau khi gán: `python -m corpus aggregate && python -m corpus serving && python -m corpus evaluate`.
- Nghiệm thu V1: 5 feature đã sửa (`condition_change`, `long_walk`, `weather_exposed`, `booking_needed`, `visit_duration`) đạt ≥ 85% trên nhãn.

## Quyết định cần người chốt

1. **Feature chỉ có `present`** (`tourist_trap`, `rough_road_access`, `cash_only`…): theo luật "không nhắc không phải âm", ràng buộc cứng "không chặt chém" / "không đường xấu" không bao giờ `pass`, nên `evaluate` cho 0 ứng viên chính ở các chuyến đó. Lựa chọn: (a) giữ fail-closed, chỉ hiển thị mục "chưa xác minh"; (b) coi "≥ N người viết (vd 50) mà không ai nhắc" là `pass` kèm cờ; (c) thêm giá trị phủ định vào ontology (`tourist_trap = absent`: "giá niêm yết rõ, không ép mua").
2. **Effort `absent` hiếm** (13 nơi `steep_or_stairs = absent` trên 1.437): chuyến có người lớn tuổi / xe lăn gần như không có ứng viên chính. Nguồn bổ sung: TikTok (đang chạy, chỉ cho `present` từ ảnh), V4b ảnh Maps (chưa làm), hoặc thông tin chủ quán / người kiểm tra.

## Chưa làm

- **V4b ảnh Maps**: phase `gmaps photos` (crawl ảnh theo địa điểm, `data/gmaps/places/<fid_dir>/photos/`) + Gemma đọc ảnh (bậc thang, mái che, trong nhà / ngoài trời). Làm sau khi xem độ phủ effort sau TikTok observe; ước lượng 1,5–2 ngày code, 1 ngày chạy.
- **TikTok crawl**: `place_search` mới ~450 / 1.438 nơi (memory `tiktok-crawl-resume`); mỗi lần có thêm cặp `place_verify` thì chạy lại `python -m corpus tiktok observe` (cache theo nơi) rồi aggregate → serving → evaluate.
- Labels cho TikTok đã có; precision theo nguồn ở `stats.by_source`. `servable` hiện dùng precision chung của (feature, value) cho mọi nguồn.
- `evaluate` chưa có chỉ số "kết quả đổi hợp lý khi đổi preference" và "unsupported claim rate" (cần Place Decision thật).

## Ghi chú vận hành

- Gemma (UIT) chỉ truy cập được trên mạng UIT; key chung 40 call đồng thời: không chạy TikTok observe / `place_verify` song song với `gmaps observe` (429).
- 9router (`cx/gpt-5.6-*`) thử làm extractor 2026-10-02: 3–4 phút một lô, `REVIEW_VERIFY` lỗi → không dùng cho chạy toàn bộ.
- Docs `CORPUS_SPEC.md`, `CORPUS.md`, `PLACE_DECISION.md`, `DEV_LOG.md` còn sửa đổi chưa commit của session khác (phần crawl, vai trò model, data layout); khi commit docs chỉ stage hunk của mình.
