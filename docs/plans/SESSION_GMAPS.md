# Session GMAPS — crawl Google Maps (dalat), phủ hết

File làm việc tạm (RULE §0.1). Môi trường server, cookie, cổng DevTools, cách dừng tiến trình: `docs/plans/CORPUS_HANDOFF.md` §▶▶. Hai session kia: `SESSION_TIKTOK.md`, `SESSION_MODEL.md`.

> **2026-10-07 20:00:** việc còn lại để xong corpus nằm ở `CORPUS_HANDOFF.md` §▶▶▶ "Còn gì để xong corpus" — đọc đó trước mục Trạng thái dưới.

## ▶ Chỗ ở (`stay`) — việc mới 2026-10-08 (`docs/CORPUS.md` §Phạm vi, Phase 1)
Code đã có (session DETAIL_LOGISTICS, chưa commit): khối `stay:` trong `config/queries.yaml`, phase `gmaps stay_search`, `gmaps list` ghi thêm `list/<city>_stay.json` (chỗ ở từ mọi file search, ≥ `stay.min_reviews` = 30 review). Thành phố `<city>_stay` = cùng config, đọc danh sách chỗ ở.
1. `python -m corpus gmaps stay_search --city dalat` (không đăng nhập; 5 từ × 18 khu = 90 lượt) → `python -m corpus gmaps list --city dalat` (ghi cả hai danh sách).
2. Runner như mọi nơi nhưng `--city dalat_stay`: `crawl → relevant → extremes → photos → keywords`. Code crawl không đổi.
3. Ghi một dòng vào `CORPUS_HANDOFF.md` §▶▶ để SESSION_MODEL observe.

**Trạng thái 2026-10-08 23:30** (session DETAIL_LOGISTICS chạy hộ theo yêu cầu người dùng):
- Bước 1 xong: 90/90 lượt `stay_search` → `data/gmaps/search/dalat_stay/` (5 file); `list` → `list/dalat_stay.json` **1.524 chỗ ở** (raw 9.772, 1.742 dưới 30 review); `list/dalat.json` giữ nguyên 1.779 nơi. Log `logs/gmaps_stay_search.log`.
- Bước 2 đang chạy từ 23:24: `GMAPS_CITY=dalat_stay logs/gmaps_dist.sh 4` = 8 runner × 8 tab (64 tab), gắn vào hai cửa sổ đăng nhập 9530 / 9533, phase `crawl,relevant,extremes,photos,keywords`, log `logs/gmaps_acc_dalat_stay_s<k>.log`. 1.519 nơi cần crawl lúc bắt đầu. `scripts/gmaps_runner.py` có thêm `GMAPS_CITY` (mặc định `dalat`); `logs/gmaps_dist.sh` gắn tên thành phố vào tên log.
- 23:34 khởi động lại với **giới hạn 300 review mới nhất cho chỗ ở** (người dùng): `config/queries.yaml` `stay.gmaps` ghi đè khóa `gmaps:` khi thành phố là `<city>_stay` (`files.load_config`); relevant 50 / extremes 30 giữ nguyên. Lúc khởi động lại còn 1.437 nơi (150 nơi lưu trước đó thiếu review, crawl lại).
- Tốc độ với giới hạn 300: ~11,5 chỗ ở/phút (81 trong 7 phút lúc 23:35–23:42), 0 captcha → phase `crawl` xong khoảng 01:45 ngày 09/10, rồi runner tự chạy `relevant → extremes → photos → keywords`.

**Xong 2026-10-09 03:41:** cả 8 runner `GMAPS_RUNNER_DONE` (crawl xong 01:01), 0 captcha. 1.517/1.524 chỗ ở có review; extremes 862, photos 845, relevant 104. Bước 3 đã ghi ở `CORPUS_HANDOFF.md` §▶▶▶ nhật ký (2026-10-09 08:40). Việc còn lại thuộc SESSION_MODEL; mục dưới chỉ dùng khi phải chạy lại.

**Theo dõi / làm tiếp (session nào cũng làm được):**
- Tiến độ: `PYTHONPATH=src .venv/bin/python logs/crawl_todo.py` (dòng `crawl dalat_stay` chỉ hiện khi gọi riêng: `grep -h "places left" logs/gmaps_acc_dalat_stay_s*.log | tail -8`); dòng cuối mỗi runner: `tail -n2 logs/gmaps_acc_dalat_stay_s*.log`.
- Captcha / đăng xuất: `grep -h -iE "captcha in the browser|login or captcha" logs/gmaps_acc_dalat_stay_s*.log | tail`; tab nào đang có captcha: `PYTHONPATH=src .venv/bin/python logs/captcha_now.py 9530 9533` → báo người dùng giải ở DevTools 9530 (tài khoản A) / 9533 (B). Không tự giải, không kill runner vì captcha chưa giải. Bị đăng xuất → người dùng đăng nhập lại (§Captcha / đăng nhập).
- Xong khi cả 8 log có `GMAPS_RUNNER_DONE`. Runner chết / treo: `logs/stop_python.sh "scripts/gmaps_runner.py"` → `python3 -I logs/gmaps_close_orphans.py 9530` (và 9533) → `rm -f .browser/attached/*.json` → `GMAPS_CITY=dalat_stay logs/gmaps_dist.sh 4` (chạy lại bỏ qua nơi đã xong). Đừng dùng `logs/gmaps_restart.sh` (nó xóa log `gmaps_acc_s*.log` của danh sách nơi và không đặt `GMAPS_CITY`).
- Còn lại sau khi runner in `GMAPS_RUNNER_DONE`: bước 3 (một dòng vào `CORPUS_HANDOFF.md` §▶▶ cho SESSION_MODEL observe nhóm `stay`).

## Phạm vi (chỉ session này sửa)
- Dữ liệu `data/gmaps/` (trừ `observations/`, `photo_observations/` của SESSION_MODEL), `config/queries.yaml` khối `gmaps:`, `src/corpus/crawl/gmaps/`, `scripts/gmaps_runner.py`, `logs/gmaps_*`, `.browser/gmaps*.json`, cổng DevTools 9520–9530.
- Không chạy observe / judge / build (SESSION_MODEL). `gmaps filter` (model) được chạy, nhưng giới hạn `EXTRACTOR_PARALLEL=64` để không giành host LAN của SESSION_MODEL.

## Trạng thái 2026-10-07 10:40 (đang chạy, không đụng trừ khi dừng hẳn)
- **Đang chạy:** `logs/gmaps_dist.sh 4` = 8 runner (`scripts/gmaps_runner.py`), 4 cho mỗi tài khoản, mỗi runner 8 tab, tất cả **gắn vào 2 cửa sổ đăng nhập** (`CORPUS_ATTACH_URL`): tài khoản A cổng 9530 (`corpus login gmaps --profile gmaps_a`, pid 3182427), B cổng 9533 (`--profile gmaps_b2`, pid 3182426). **Không đóng tab đăng nhập / không kill 2 tiến trình login** — mất phiên là phải nhờ người dùng đăng nhập lại. Phase: crawl → relevant → extremes → photos → keywords, log `logs/gmaps_acc_s<k>.log`.
- Tốc độ: 64 tab, `crawl`/`relevant` chặn bản đồ/ảnh (`text_only`): 15–39 nơi/phút, chậm khi gặp nơi hàng nghìn review. Không captcha từ 09:31. Renderer của 2 trình duyệt đăng nhập được `renice +10` (tiến trình chính để 0) cho người giải captcha khỏi giật; renderer mới thừa hưởng từ zygote.
- Còn lại lúc 10:30 (`PYTHONPATH=src .venv/bin/python logs/crawl_todo.py`): crawl **2.467** nơi (957 là crawl lại cho đủ review), relevant 10, extremes 165, photos 1.242, keywords 67 (photos/extremes tăng khi crawl thêm nơi).
- Sửa code (chưa commit): `_attach` mở tab/đọc cookie qua CDP đúng context đã đăng nhập, khớp tab theo `targetId`, ghi tab của mỗi tiến trình vào `.browser/attached/`, tiến trình gắn sau đóng tab của tiến trình đã chết; captcha chờ người không giới hạn, giải xong đi tiếp không retry, mọi shard nghỉ trong lúc chờ (`Gate.hold/solved`).
- **Rò tab trống chưa rõ gốc:** mỗi lần một phase khởi động/thoát, vài tab `about:blank` trong context đăng nhập rơi khỏi sổ của tiến trình (12:24: 8 tab mỗi cửa sổ). Tạm xử lý bằng `logs/gmaps_tab_janitor.py` (chạy nền, log `logs/gmaps_janitor.log`): đóng tab không tiến trình sống nào nhận trong 2 lần kiểm cách 3 phút. Cần tìm gốc trong `_attach` (`src/corpus/crawl/common/browser.py`). Số tab hợp lệ: phase `photos` 16/runner.
- **12:50:** lượt 1 xong `crawl`, đang `photos`/`extremes`. Còn crawl 924 nơi (đã lưu nhưng thiếu review: danh sách ngừng tải khi máy quá tải), photos 1.940, extremes 120. `logs/gmaps_passes.sh` (log `logs/gmaps_passes.log`) chờ 8 runner xong rồi chạy lại cả lượt, tối đa 3 lượt, dừng khi số crawl còn lại không giảm.
- Kiểm tra: `logs/crawl_watch.sh` (mỗi 3 phút: nơi/3 phút, `/sorry/`, số tab mỗi cửa sổ — đúng là 33, captcha đang treo). Khởi động lại sạch: `logs/gmaps_restart.sh 4`. Dừng một nhóm: `logs/stop_python.sh "<chuỗi>"` (đừng `pkill -f`, đừng `kill` group của script cha).

- **16:00: `min_reviews` 1 → 30** (người dùng): danh sách 4.503 → 1.779 nơi. Còn crawl 186, photos 246, extremes 139, keywords 4. Observe xóa observation của nơi rời danh sách, nên 1.224 file của các nơi dưới 30 review đã chép sang `data/gmaps/observations_under30_backup/` (chép lại vào `observations/` nếu hạ ngưỡng, không phải observe lại). Danh sách cũ: `logs/gmaps_list_min1_20261007.json`. Runner đang chạy giữ danh sách cũ đến hết phase hiện tại.

## Việc, theo thứ tự (người dùng: mở rộng cả rộng lẫn sâu, phủ hết dữ liệu có thể)
1. **Rộng — nơi đã search sẵn:** hạ `gmaps.min_reviews` 50 → 10 (danh sách 1.438 → 2.594 nơi, 1.074 chưa crawl; không tốn model). Đọc ~20 nơi có 1–9 review trong danh sách `min_reviews=1`: phần lớn là nơi thật cho khách → hạ tiếp (tối đa ~5.400 nơi filter giữ). Rồi `python -m corpus gmaps list --city dalat` → runner theo shard với `GMAPS_PHASES=crawl,relevant,extremes,photos,keywords`.
2. **Rộng — search thêm:** `gmaps.grid.max_zoom` 14 → 15, thêm `categories` còn thiếu (đọc danh sách hiện có trong config). `gmaps search` (không cần đăng nhập, `search_tabs`) → `gmaps filter` (model, `EXTRACTOR_PARALLEL=64`) → `list` → bước 1.
3. **Sâu:** tăng `max_reviews_per_place` (200), `relevant_reviews_per_place` (50), `extreme_reviews_per_place` (30), `keyword_reviews_per_word` (20), `photos_per_place` (12) / `photos_per_sight` (30); thêm `keyword_sets`. `extremes` / `relevant` ghi một lần mỗi nơi (chạy lại bỏ qua): muốn nơi cũ lấy thêm thì sửa điều kiện "đã xong" thành so số review đã có với số muốn (giống `photos.needs_fetch`), có test.
4. Mỗi bước xong: báo SESSION_MODEL (ghi một dòng vào `CORPUS_HANDOFF.md` §▶▶) để nó observe phần mới.
5. Ghi mức tab tối đa không bị chặn vào comment `gmaps.tabs` trong config.

## Captcha / đăng nhập
Captcha: người dùng giải qua DevTools (cổng shard 9520+i); không tự giải. Google đăng xuất (log `login or captcha needed` ngay đầu, không có dòng captcha) → nhờ người dùng đăng nhập: `CORPUS_DEBUG_PORT=9530 ... python -m corpus login gmaps`, đóng tab → `.browser/gmaps.json`, chép sang `gmaps_s<i>.json`.
