# Session MODEL — biến dữ liệu thô thành corpus (observe, judge, build, đo chất lượng)

File làm việc tạm (RULE §0.1). Môi trường server: `docs/plans/CORPUS_HANDOFF.md` §▶▶. Hai session crawl: `SESSION_GMAPS.md`, `SESSION_TIKTOK.md`. Quy tắc chất lượng đã chốt (Gemma là engine duy nhất, `OBSERVE_KEEP_STALE`, cổng precision, effort theo im lặng, `REPORTS_MIN`): `CORPUS_HANDOFF.md` §▶ "Quy tắc đã chốt".

> **2026-10-07 20:00:** việc còn lại để xong corpus nằm ở `CORPUS_HANDOFF.md` §▶▶▶ "Còn gì để xong corpus" — đọc đó trước mục Trạng thái dưới.

## ▶ Chỗ ở (`stay`) — việc mới 2026-10-08 (`docs/CORPUS.md` §Phạm vi, Phase 1)
Code đã có (chưa commit): observe / photo_observe / qc đọc **cả** `list/<city>.json` và `list/<city>_stay.json` (`files.listed`), nên observation của chỗ ở không bị xóa như nơi rời danh sách. Nhóm `stay` (`config/category_defaults.yaml`, `usable_as: []`) không vào Place Decision. Aggregate chỉ giữ feature trong `stay_features` (`config/ontology.yaml`, không nằm trong prompt nên không observe lại) cho chỗ ở. `categories.group` chuẩn hóa NFC: 24 nơi có category NFD (vd "Chợ") đổi từ `other` sang nhóm đúng ở lần aggregate tới.
Khi SESSION_GMAPS báo crawl `dalat_stay` xong: build như thường (`python -m corpus build --city dalat`); serving sẽ có chỗ ở với `category_group = stay`. Planning tự chuyển từ crawl live sang corpus khi serving có ≥ `stay_min` chỗ ở (spec §4.2).

## Phạm vi (chỉ session này sửa)
- `src/corpus/observe/`, `src/corpus/judge/`, `src/corpus/aggregate/`, serving, `src/corpus/llm/` (prompt, task, role), `data/*/observations/`, `data/intel/`, `data/serving/`, `web/` snapshot, `docs/CORPUS.md`, `docs/LLM_PROVIDER.md`.
- Chủ host LAN Extractor (`docs/LLM_PROVIDER.md` §Host LAN): được dùng tới 192–256 call đồng thời; hai session crawl dùng ≤64 cho bước model của họ. Không crawl, không mở trình duyệt.

## Trạng thái 2026-10-06 23:40
- Extractor đã trỏ sang host LAN (`.env`: `EXTRACTOR_*`, `EXTRACTOR_PARALLEL=256`; UIT giữ dạng comment để quay lại). Mọi task Extractor không tự đặt `parallel` dùng số này (`Role.parallel`). Test crawl / observe / judge / build pass.
- `certs/uit-ca-bundle.pem` đã tạo trên server (Agent vẫn gọi UIT).
- Dữ liệu mới chưa observe: ~370 file `reviews_extremes.json` crawl trên server hôm nay, ~1.200 video TikTok mới tải, ảnh gmaps 22 nơi.

## Việc, theo thứ tự
1. **Build lần đầu trên server** với host mới: `.venv/bin/python -u -m corpus build --city dalat > logs/build_1.log 2>&1` (qc → observe → judge → aggregate → serving). `logs/quality_pass.py` của máy Windows **không có trên server** (`logs/` không theo git): phần audit Gemma của nó chạy riêng bằng `python -m corpus judge audit --city dalat` (`JUDGE_ENGINE=gemma`, đọc `docs/CORPUS.md` trước). Đo thời gian mỗi bước với 256 call so với số cũ trên UIT (38 call).
2. Sau build: `python web/scripts/export_snapshot.py`, `python -m decision evaluate`, so với mốc ở `CORPUS_HANDOFF.md` §▶ "Trạng thái" (filled_rate 0,967, 0 violation).
3. **Chạy build lặp** khi hai session crawl đổ dữ liệu: `python -m corpus build --city dalat --every <phút>` (`--skip` bỏ bước, ví dụ `"gmaps qc"`), để corpus luôn theo kịp crawl.
4. Có model nhanh và nhiều slot: xét lại các chỗ từng cắt vì giới hạn UIT — audit Gemma toàn bộ claim (1.369 claim chưa audit), `REVIEW_VERIFY` cho mọi claim, observe ảnh nhiều hơn; đo luật v10 trên dữ liệu mới (mục 6 ở §▶).
5. Cập nhật `docs/CORPUS.md` khi hành vi đổi; gộp phần còn giá trị của ba file `SESSION_*.md` và `CORPUS_HANDOFF.md` vào tài liệu chính thức khi xong, rồi xóa chúng.
