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
| `corpus build --skip judge tiktok` (lượt tạm, code mới) | `logs/build_interim2.log` | dòng `build dalat: done` | Không gọi Judge; lượt cũ `build_interim.log` đã dừng sau khi đọc lại toàn bộ 47 nơi |
| Judge audit (session khác, `mlai-12`) | `logs/judge_chain.log` | `JUDGE_CHAIN_DONE` | Dùng quota Codex; **không dừng** tiến trình có `corpus.judge.audit`, không chạy `build` đầy đủ hay `judge audit` trước dấu này (hai audit cùng lúc tốn gấp đôi quota, ghi nhãn trùng) |

## Việc tiếp theo, theo thứ tự

1. **`gmaps visit` không dùng được (kiểm 2026-10-05):** Maps (tài khoản này, Đà Lạt) không in dòng "Mọi người thường
   dành … ở đây" — đã mở ZooDoo (10.717 review), spa, vườn, và thử 30 nơi: chỉ có biểu đồ giờ đông. Không chạy phase
   này; thời gian tham quan vẫn từ review / mặc định. Gợi ý thay: tab **"Vé"** trên trang Maps có giá vé người lớn
   (vd. ZooDoo 151.200 ₫ + giá trang chính thức) — nguồn giá vé đáng crawl.
   Chuỗi Maps hiện tại: `logs/gmaps_chain3.sh` (headed, người giải captcha trong cửa sổ): keywords → photos →
   extremes, dấu `GMAPS_CHAIN3_DONE`. Chuỗi 1–2 đã dừng giữa chừng vì Google đòi đăng nhập/captcha.
2. **Khi cả hai chuỗi xong và `logs/judge_chain.log` có `JUDGE_CHAIN_DONE`:**
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
