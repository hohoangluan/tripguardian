# Bàn giao corpus (ngoài TikTok) — 2026-10-05

File làm việc tạm (RULE §0.1): xong các bước dưới thì gộp phần còn giá trị vào `docs/CORPUS.md` và xóa file này.
Mô tả hành vi code: `docs/CORPUS.md` (§CLI, §1 Dữ liệu thô, §4 Observe, §5 Aggregate, §6 Judge). Ở đây chỉ có
trạng thái và việc còn lại.

## Đã xong (local `main`, chưa push)

| Commit | Nội dung |
|---|---|
| `c77ef78` | Mẫu có chủ đích (`sample = extremes \| keywords`) chỉ tính cho effort + fact; `voices_targeted`; judge status mở lại phán quyết cũ khi hết báo cáo; bỏ cờ `in_city` (nơi vùng ven là nơi bình thường — người dùng quyết) |
| `f3011e1` | `python -m corpus build` (qc → observe mọi nguồn → judge → aggregate → serving, tăng dần) |
| `d3664e8`, `162b7a9`, `e545075` | Nguồn `official`: trang web chính thức → giá vé + giờ (site > Maps); giá chỉ cho nhóm bán vé; vé điển hình = trung vị |
| `5db2e4a`, `bbd9562`, `0bb7e64`, `bb23a19`, `63435c7` | Phase `gmaps keywords` (đã kiểm trên Maps thật) + ảnh điểm tham quan 30 tấm; tốc độ ~16 nơi/phút |
| `3f19d0e` | `gmaps qc`: chỉ thêm review mà `place.json` không đổi → giữ phán quyết Judge cũ, Gemma chỉ đọc review mới |
| `e07cee8` | `gmaps observe` tăng dần: review đã đọc giữ observation (nhãn Judge còn dùng được), chỉ review mới qua model |
| `efb4e9f` | Phase `gmaps visit` ("Mọi người thường dành … ở đây" → thời gian tham quan, ưu tiên hơn review / mặc định) + `keyword_sets` theo nhóm category |

## Đang chạy (tách rời, sống qua khi phiên đóng)

Kiểm bằng `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`. Chỉ `python` có trong PATH của `sh` tách rời
(không có `grep` / `sleep`).

| Job | Log | Dấu kết thúc | Ghi chú |
|---|---|---|---|
| `logs/gmaps_chain.sh`: `gmaps keywords` → `gmaps photos` → `gmaps extremes` | `logs/gmaps_chain.log` | `GMAPS_CHAIN_DONE` | Giữ profile `.browser/gmaps`; không chạy phase gmaps có trình duyệt khác cùng lúc |
| `logs/gmaps_chain2.sh`: chờ dấu trên → `gmaps visit --limit 30` (thử) → `gmaps visit` → `gmaps keywords` (từ mới) | `logs/gmaps_chain2.log` | `GMAPS_CHAIN2_DONE` | Thử 30 nơi không đọc được dòng nào → in `VISIT_CHECK_FAILED`, bỏ qua visit toàn bộ |
| `corpus build --skip "gmaps qc" judge tiktok` (lượt tạm) | `logs/build_interim.log` | dòng `build dalat: done` | Chạy bằng code cũ: đọc lại toàn bộ review của nơi có keywords |
| Judge audit (session khác) | `logs/judge_chain.log` | — | Chờ quota Codex; **không dừng** tiến trình có `corpus.judge.audit` |

## Việc tiếp theo, theo thứ tự

1. **Khi `gmaps_chain2.log` có `VISIT_CHECK_FAILED`:** mở một trang có biểu đồ giờ cao điểm bằng profile gmaps, tìm
   đúng câu Maps in (regex `_LINE_JS` trong `src/corpus/crawl/gmaps/visit.py`, parser `parse_time_spent` trong
   `src/corpus/observe/gmaps/place_rules.py`), sửa, xóa `data/gmaps/places/*/visit.json`, chạy lại
   `python -m corpus gmaps visit`. Nếu có dòng đọc được: kiểm vài `visit.json` khớp trang thật.
2. **Khi cả hai chuỗi xong và quota Judge đã hồi** (audit của session kia chạy xong):
   `python -m corpus build --city dalat` (đầy đủ). `gmaps qc` chỉ gọi Gemma cho review mới; `gmaps observe` chỉ đọc
   review mới; Judge chỉ chấm nhận định chưa có nhãn.
3. **Sau build:** đo lại khoảng trống trên nơi trải nghiệm của `data/serving/places.json` (dốc / đi bộ xa / người lớn
   tuổi / đặt chỗ / thời gian tham quan / giá vé; số đo lúc bàn giao: VERIFIED 13 / 2 / 12 / 1, thời gian tham quan
   mặc định 749/781, giá vé trống 604/781) và `python -m decision evaluate`.
4. **Kiểm Judge** sau build: lấy mẫu ~40 nhãn mới (ưu tiên `cx/gpt-6-astra`), đọc review gốc. Lần kiểm 2026-10-05:
   đồng ý 37/40; astra chặt với "phù hợp cho cả gia đình" → trẻ em (an toàn), một lần dễ ("gặp gỡ bạn bè" → nhóm
   đông). Không tự ghi nhãn (nhãn người là của người dùng).
5. **Official:** 43 site không tải được (`data/official/errors.jsonl`: site chết, lỗi chứng chỉ); chạy lại
   `python -m corpus official pages` sau vài ngày; `official observe` cần mạng UIT.

## Chưa quyết / để người dùng

- `src/corpus/crawl/common/throttle.py` có thay đổi chưa commit (`grow_after` 5 → 2) không session nào nhận; giữ
  nguyên tới khi người dùng quyết.
- Đẩy lên remote: chưa push, phải hỏi người dùng.
