# Bàn giao corpus (Maps, dalat) — 2026-10-06

File làm việc tạm (RULE §0.1): xong các bước dưới thì gộp phần còn giá trị vào `docs/CORPUS.md` và xóa file này.
Mô tả hành vi code: `docs/CORPUS.md`. Ở đây chỉ có trạng thái và việc còn lại.

## Trạng thái hiện tại

- **Đang tạm dừng:** crawl Maps (`logs/gmaps_runner.py`). Mạng yếu, không tải được trang. Không có tiến trình gmaps nào đang chạy.
- **Còn lại (ước lượng 2026-10-06):**
  - `extremes` (review 1–2★ và 5★): 344 nơi đã có file, còn ~1.120 nơi.
  - `photos`: còn ~32 nơi (1.435/1.467 đã có).
  - `keywords`: 1.151 nơi đã có `reviews_keywords.json`. Chưa kiểm xem đủ 7 nhóm từ hay chưa; xem bước 1 bên dưới.
- **Judge (`mlai-12`):** đợi quota Codex. Dấu hoàn thành: `logs/judge_chain.log` có `JUDGE_CHAIN_DONE`. Không dừng tiến trình `corpus.judge.audit`.

## Commit (local `main`, chưa push)

| Commit | Nội dung |
|---|---|
| `d9b74ea` | Chạy ngầm: captcha thì dừng (không đợi 5 phút) |
| `dbc5e59` | Chặn ảnh, tile bản đồ, font trong keywords/extremes (~700 → ~400 MB/tab); chờ trang `/sorry/` biến mất khi headed |
| `0faad35` | Headed: số tab cố định (đã bỏ ở `e6628d2`) |
| `8ae690d` | Sửa extremes: đợi danh sách đã sắp xếp thay danh sách mặc định; kiểm thứ tự sao, sai thì thử lại |
| `e6628d2` | Bỏ tab cố định, trở lại bộ điều chỉnh tab tự động (cần khi mạng yếu) |

Các commit trước (`c77ef78` … `d8195aa`) xem `git log`.

## Việc tiếp theo, theo thứ tự

1. **Kiểm keywords đủ chưa:** đếm nơi có đủ 9 từ trong `reviews_keywords.json`. Nếu thiếu thì chạy `python -m corpus gmaps keywords --city dalat --headed` để bổ sung.
2. **Chạy lại Maps khi mạng ổn:** `python logs/gmaps_runner.py` (headed, thứ tự: extremes → photos → keywords). Nếu có captcha, runner mở cửa sổ; người dùng giải rồi để nó chạy tiếp. Nếu treo 10 phút không ghi file, runner tự dừng phase và chạy lại.
3. **Kiểm chất lượng sau mỗi đợt crawl** (script kiểm nằm ở `tests`/ad hoc; kiểm: số review mỗi danh sách, thứ tự sao, trùng review, file ảnh thiếu). Lần kiểm 2026-10-06: extremes có 8% file bị trộn trước khi sửa `8ae690d`; 20 file đã xóa để crawl lại; các file mới đều đúng thứ tự.
4. **Khi `JUDGE_CHAIN_DONE` và Maps xong:** `python -m corpus build --city dalat` (đầy đủ). Trước đó có thể chạy lượt tạm `build --skip judge tiktok` (không gọi Judge).
5. **Sau build:** đo khoảng trống trên nơi trải nghiệm của `data/serving/places.json` và `python -m decision evaluate`. Số đo gần nhất (build tạm 2026-10-05 15:47 UTC): dốc VERIFIED 136, đi bộ xa 43, người lớn tuổi 60, đường vào xấu 184, đặt chỗ 266 trên 772 nơi trải nghiệm. Thời gian tham quan mặc định 742/772; giá vé trống 597/772.
6. **Kiểm Judge** sau build: lấy ~40 nhãn mới (ưu tiên `cx/gpt-6-astra`), đọc review gốc. Không tự ghi nhãn người.
7. **Official:** 43 site lỗi (`data/official/errors.jsonl`). Chạy lại `python -m corpus official pages` sau vài ngày.

## Đã thử và bỏ

- **`gmaps visit` (thời gian tham quan từ Maps):** Maps không in "Mọi người thường dành … ở đây" cho các nơi Đà Lạt (thử 30 nơi, 0 dòng; kiểm tay ZooDoo, spa, vườn: chỉ có biểu đồ giờ đông). Không chạy phase này. Thời gian tham quan vẫn từ review hoặc giá trị mặc định.
- **Tab "Vé" trên Maps:** dữ liệu `tickets` đã có trong `place.json` nhưng chỉ 22/1.792 nơi có khung giá. Không thêm phase mới.

## Gotchas

- Maps chặn ở ~12 tab (captcha) khi chạy ngầm; headed thì người giải. RAM: ~250 MB/tab, GPU process ~1 GB; trên 12 tab máy hết RAM.
- Sh chạy từ PowerShell `Start-Process` chỉ có `python` trong PATH; không có `grep`/`sleep`.
- Một số `tiktok place_crawl` và `scripts/tiktok_place_loop.sh` là của session khác, không đụng.

## Chưa quyết / để người dùng

- Các file đã sửa chưa commit: `scripts/free_tiktok_clips.py`, `src/corpus/__main__.py`, `src/corpus/crawl/common/throttle.py` (`grow_after` 5 → 2), `src/corpus/crawl/tiktok/{comments_crawl,place_crawl}.py`, `src/corpus/observe/tiktok/extract.py`. Không phải của phiên này; giữ nguyên tới khi người dùng quyết.
- Đẩy lên remote: chưa push, phải hỏi người dùng.
