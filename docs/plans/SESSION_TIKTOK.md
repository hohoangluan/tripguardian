# Session TIKTOK — crawl TikTok (dalat), phủ hết

File làm việc tạm (RULE §0.1). Môi trường server, cookie, cổng DevTools, cách dừng tiến trình: `docs/plans/CORPUS_HANDOFF.md` §▶▶. Hai session kia: `SESSION_GMAPS.md`, `SESSION_MODEL.md`.

> **2026-10-09:** clip TikTok phát trên máy mình (trang địa điểm TikTok, `place_poi` → `poi_crawl` → … → `clips`): đọc `docs/plans/TIKTOK_CLIPS_HANDOFF.md`. Không chạy `scripts/tiktok_place_loop.sh` / `free_tiktok_clips.py` trước `clips`.

> **2026-10-07 20:00:** việc còn lại để xong corpus nằm ở `CORPUS_HANDOFF.md` §▶▶▶ "Còn gì để xong corpus" — đọc đó trước mục Trạng thái dưới.

## Phạm vi (chỉ session này sửa)
- Dữ liệu `data/tiktok/` (trừ `observations/` của SESSION_MODEL), `config/queries.yaml` khối `tiktok:`, `src/corpus/crawl/tiktok/`, `logs/tiktok_*`, `.browser/tiktok*.json`, cổng DevTools 9541–9542, GPU cho ASR.
- Bước dùng model của TikTok (`place_filter`, `filter`, `asr_check`, `place_verify`) thuộc session này, chạy với `EXTRACTOR_PARALLEL=64` khi SESSION_MODEL đang build (host LAN chung 256).

> **2026-10-08 (người dùng xác nhận):** chấm ảnh đẹp cho gallery web dùng **Gemma**, không dùng CLIP; khi chạy việc đó thì **tạm dừng luồng model TikTok** (`logs/tiktok_lan_uit_lane.sh`: `asr_check` / `place_verify`) để nhường Gemma. `place_search` (trình duyệt) không dùng Gemma, không phải dừng. Chấm ảnh xong thì chạy lại luồng model TikTok.

## Trạng thái 2026-10-07 10:40
- **`place_search` đang DỪNG** (người dùng: captcha nhiều, giải bị giật, nhường tài nguyên). Kể cả 2 tab/tài khoản vẫn dính slider ngay khi chạy lại lúc 10:00 → tài khoản/IP đang bị TikTok để ý, không phải do số tab. Còn **4.056 nơi**. `place_search_tabs` 3 (trần mới), throttle đặt 2. Chạy lại khi người dùng ngồi giải: `logs/tiktok_crawl.sh place_search <tag>` (DevTools 9541/9542); mỗi tài khoản giải 1 tab là các tab khác tự reload.
- **`comments_crawl` DỪNG** (35 video, dính captcha) — chạy tay khi có người giải.
- **Đang chạy, không cần người:** `logs/tiktok_browser_lane.sh` (filter → `place_crawl` 2 tài khoản, cổng 9543/9544, tối đa 3 tab/tài khoản; không còn search nên vòng hiện tại là vòng cuối, xong thì tạo `logs/tiktok_lanes.browser_done`) và `logs/tiktok_gpu_lane.sh` (asr trên GPU <20% tải → asr_check → asr_alt → asr_check → place_verify → xóa clip đã verify, lặp 5 phút, dừng khi có file done và hết việc). Log chung `logs/tiktok_lanes.log`. `logs/tiktok_pipeline.sh` cũ bỏ (từng treo).
- **11:30: luồng trình duyệt xong** (`place_crawl` hết video đã lọc: vòng 2 1.433/1.444, vòng 3 6/7; lỗi ở `errors.jsonl`). Video mới chỉ có khi `place_search` chạy lại. Luồng GPU vẫn chạy đến hết ASR/verify.
- **13:05: luồng model TẠM DỪNG** (người dùng: dồn Gemma cho build). Chạy lại: `setsid nohup logs/tiktok_llm_lane.sh &` (UIT) khi build xong. Luồng GPU (asr, asr_alt — không dùng Gemma) vẫn chạy.
- **13:00: tách luồng model khỏi GPU** (verify không còn chờ ASR): `logs/tiktok_gpu_lane.sh` (asr → asr_alt, GPU <20% tải) và `logs/tiktok_llm_lane.sh` (asr_check → place_verify → xóa clip, **Gemma UIT x38**; `lan [n]` để dùng host LAN). Host LAN để cho build MODEL (đủ 38/38, người dùng chọn chỉ UIT). Gemma UIT không theo schema ~15% câu `asr_check` (thiếu `screen_text`, không ra JSON): video lỗi để lại cho vòng sau, không ghi sai. Còn lúc 12:50: asr 1.101, asr_check 471, asr_alt 1.613, place_verify 4.402.
- **13:30:** `place_search` chạy lại (`logs/tiktok_crawl.sh place_search search_1007c`, DevTools 9541/9542, mỗi shard 2.028 nơi) cho người dùng giải captcha. ASR thêm 3 tiến trình ngoài luồng GPU (GPU 2/4/7, `--shard i/3`, log `logs/tiktok_extra_asr*.log`), trong lúc luồng GPU kẹt ở `asr_alt` một GPU. `asr` giờ đọc lại video.json trước khi chép và bỏ qua video tiến trình khác đã chép, nên chạy chồng với luồng GPU không chép trùng. Mỗi tiến trình ASR ăn 100% một core CPU, GPU chỉ ~5–10%: nút thắt là CPU (giải mã, VAD), không phải GPU.
- **16:00:** danh sách gmaps còn 1.779 nơi (`min_reviews` 30) → `place_search` chạy lại (`search_1007d`), mỗi shard 677 nơi. `asr` xong hết; `asr_alt` có `--shard i/n` (bỏ qua video tiến trình khác đã nghe), 5 tiến trình ngoài luồng GPU trên GPU 2/3/4/5/7, log `logs/tiktok_extra_asr_alt*.log`. Server tải ~217 trên 40 core: ASR, crawl và giải captcha đều chậm vì CPU.
- Còn lại lúc 10:30: `place_crawl` **1.144** video (~20–29 video/phút ở 3 tab/tài khoản), asr 507, asr_check 2.071, asr_alt 417, place_verify 2.281 (+2.487 chờ ASR), place_filter 19. Video: 8.304 đã lưu, 4.891 mp4 trên đĩa.
- `tiktok.tabs` 5 → **3**/tài khoản: 5 bị Akamai chặn ("no item data", không captcha) sau ~8 phút lúc 09:47.

## Việc, theo thứ tự (người dùng: mở rộng cả rộng lẫn sâu, phủ hết dữ liệu có thể)
1. Ghi mức tab tối đa không bị chặn (từ `logs/probe.log`) vào comment `tiktok.tabs`, đặt `tiktok.tabs` / `pause_s` theo đó.
2. **Sâu — video đã lọc sẵn:** `tiktok.crawl_videos_per_place` 5 → 10 (≈ +2.400 video có trong `place_filter`, không tốn model), rồi bỏ trần (tất cả video "yes") → `place_crawl`.
3. **Rộng:** `tiktok.videos_per_place` 10 → 20 → `place_search` (trình duyệt, `place_search_tabs` 1 vì tài khoản `tiktok2` từng bị chặn) → `place_filter` (model) → `place_crawl`. Nơi gmaps mới (SESSION_GMAPS hạ `min_reviews`) cũng đi đường này khi danh sách gmaps đổi.
4. `comments_crawl` (35 video, `max_comments_per_video` 200 → cân nhắc tăng).
5. **ASR:** `asr` (GPU: 8× RTX 2080 Ti dùng chung, chọn GPU trống bằng `CUDA_VISIBLE_DEVICES`, xem `nvidia-smi`) → `asr_check` → `place_verify` → `python scripts/free_tiktok_clips.py --city dalat --verified` (xóa mp4 đã verify). Vòng lặp mẫu: `scripts/tiktok_place_loop.sh` (gọi `python` — trên server dùng `.venv/bin/python` và các biến môi trường ở §▶▶).
6. Mỗi lô xong: ghi một dòng vào `CORPUS_HANDOFF.md` §▶▶ để SESSION_MODEL observe video mới.

## Captcha
TikTok slider: người dùng giải qua DevTools 9541/9542; không tự giải. Hết phiên đăng nhập → `CORPUS_DEBUG_PORT=9541 ... python -m corpus login tiktok` (hoặc `--profile tiktok2`), đóng tab → `.browser/<tên>.json`.
