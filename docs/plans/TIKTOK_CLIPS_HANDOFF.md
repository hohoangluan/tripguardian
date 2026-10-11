# Bàn giao — clip TikTok phát trên máy mình (theo trang địa điểm TikTok)

File làm việc tạm (RULE §0.1); xong việc thì gộp phần còn giá trị vào `docs/CORPUS.md` rồi xóa. Môi trường server (venv, biến `CORPUS_*`, cách dừng tiến trình): `docs/plans/CORPUS_HANDOFF.md` §▶▶. Hành vi từng phase: `docs/CORPUS.md` §1 Phase 2 (`place_poi`, `poi_crawl`, `clips`).

## Mục tiêu (người dùng, 2026-10-09)
Mỗi địa điểm có **6 clip** TikTok chất lượng nhất để người dùng xem ngay trên web, phát từ server của mình (không qua embed TikTok). Video lấy qua **trang địa điểm TikTok** (`tiktok.com/place/x-<poi_id>`), không qua search (search dính captcha, đang dừng).

## Đã xong (2026-10-09, chưa commit)
- Thử trang địa điểm: mở được **không đăng nhập, không captcha**; `/api/poi/item_list/` trả ~30 video/trang kèm `playAddr` h264 tải được bằng phiên ẩn danh.
- `video.json` có trường `poi`; video cũ đọc `poi` từ `info.json`.
- Phase `tiktok place_poi` (Extractor `PLACE_POI_MATCH`, đọc 2 lần đảo thứ tự, một POI một nơi, tính các mục Judge đã gộp): **709 / 983 nơi** có POI → `data/tiktok/place_poi/dalat.json`. Mẫu 20 nơi: 17 đúng rõ.
- Phase `tiktok poi_crawl` (trình duyệt ẩn danh, xếp hạng trong code, tải `poi_download`=10 video/nơi) và `tiktok clips` (6 video `place_verify` = yes còn mp4, mỗi tác giả một video) → `data/tiktok/clips/dalat.json`. `places_by_video` đọc cả `poi_crawl/`, nên `asr_check` / `place_verify` / `observe` xử lý luôn video mới.
- `scripts/free_tiktok_clips.py` không xóa clip trong `clips/dalat.json`.
- Web: `Video.local`; `PlaceSheet` phát `<video>` từ `/media/tiktok/<id>/video.mp4` khi `local`, còn lại vẫn iframe TikTok (luôn có @tác giả + "Mở trên TikTok"). `web/server.mjs` phục vụ đúng mp4 của clip (Range, 206/416; file khác vẫn 404). `web/scripts/export_snapshot.py` ưu tiên `clips/dalat.json`.
- Test: `tests/crawl/tiktok/test_tiktok_place_poi.py`, `test_tiktok_poi_crawl.py` (113 test TikTok pass). `tsc -b` pass.
- File đã sửa: `src/corpus/crawl/tiktok/{place_poi,poi_crawl,clips}.py` (mới), `crawl.py`, `place_filter.py`, `__init__.py`; `src/corpus/llm/{tasks,__init__}.py`; `src/corpus/__main__.py`; `config/queries.yaml` (`poi_*`, `clips_per_place`); `scripts/free_tiktok_clips.py`; `web/server.mjs`, `web/scripts/export_snapshot.py`, `web/src/data/types.ts`, `web/src/user/ui/PlaceSheet.tsx`, `web/src/user/css/sheet.css`; `docs/CORPUS.md`, `docs/log/DEV_LOG.md`.

## Trạng thái lúc bàn giao lại (2026-10-09 ~09:20) — người dùng yêu cầu dừng, chuyển model lớn hơn làm tiếp
- Lô thử 20 nơi: `poi_crawl` xong 20/20 (187 video, 1 nơi 403 lúc tải, chạy lại được). ASR xong 169 video.
- **Không còn tiến trình nào chạy** (đã dừng chuỗi `asr_check` → `place_verify` → `clips`). `data/tiktok/clips/dalat.json` **chưa có**; `place_verify` và `clips` **chưa chạy** cho lô này. `asr_check` còn khoảng 300 video chưa kiểm (gồm ~170 video của lô thử); phase bỏ qua phần đã làm nên chạy lại là tiếp tục.
- **Chưa biết tỉ lệ đạt** (bao nhiêu trong 10 video / nơi qua `place_verify` = yes, số nơi đủ 6). Có số thì mới quyết `poi_download` 10 → 14.

## Vấn đề gặp phải (đo 2026-10-09)
1. **Tải mp4 không phải nút thắt.** `download_video` 10–17 MB/s ở 5–10 luồng (1 luồng 4,7 MB/s); cả lô 20 nơi (2 GB) xong 271 s ⇒ 689 nơi còn lại ≈ 2,5 giờ crawl. Mỗi nơi tốn ~10 s mở trang + tải. Giữ `downloads: 4`; đĩa ghi 107 MB/s, đủ. Chưa thử nâng `poi_tabs` (cẩn thận Akamai).
2. **`asr_check` là nút thắt, và lỗi không do tải.** Host Gemma (LAN :9090) chạy 23–38 yêu cầu, KV cache 89–95 %, đang có người khác dùng. Guided decoding (`response_format` json_schema) **lặp khoảng trắng đến hết `max_tokens`** (4000 token ≈ 180 s mỗi lần, `ATTEMPTS`=4 ⇒ ~12 phút và chiếm 1 trong 38 slot). Trong lô này 89 / ~100 lỗi `asr_check` là kiểu lặp này (trước đó log ghi `missing screen_text` / `no JSON object` — cùng nguyên nhân: JSON bị cắt).
   - Vị trí lặp: ngay sau `"quality": "good"` (trường `screen_text` bắt buộc nhưng nằm cuối lược đồ, mô hình không muốn viết) — hoặc, khi đưa `screen_text` lên đầu, ngay sau `"screen_text": `.
   - Thử trên video `7229979796145540358` (8 segment, 7200 ký tự): giữ nguyên ⇒ lặp (max_tokens 1500 / 4000 / 8000 đều lặp); đổi thứ tự trường ⇒ lặp; `temperature` 0.3 ⇒ lặp; `structured_outputs` + `disable_any_whitespace` ⇒ lặp. **Bỏ `screen_text` khỏi `required` ⇒ kết thúc sạch 2/2 lần** (`finish=stop`, ~1900 token), nhưng khi đó không có `screen_text` trong câu trả lời.
   - **Chưa kiểm:** khi `screen_text` tùy chọn, mô hình có vẫn điền chữ đọc được trên màn hình ở video có chữ không (đang định thử đúng điều này thì bị dừng). Đây là điều quyết định có đổi lược đồ hay không: `screen_text` là ngữ cảnh cho `guard` của `asr_check` (tên riêng được sửa theo chữ trên màn hình) nên mất nó thì chất lượng sửa tên giảm. Các hướng thay: `screen_text` thành chuỗi (không phải mảng); tách thành 2 lời gọi (đọc chữ trên màn hình riêng); `minItems` / cho phép `null`; đổi `max_tokens` + giảm số segment mỗi lời gọi cho video dài.
3. 2 lỗi `BadRequestError`: prompt 28 769 token + 4000 > 32 768 (video có quá nhiều segment / transcript quá dài). Cần chia segment hoặc bỏ video quá dài thay vì gọi một lần. 3 lỗi `answered segments [0,1,2,3] for 1 segment` (mô hình bịa thêm segment) — thử lại là đủ, chưa xử lý.
4. `asr_check` cho cả `place_verify` đều dùng host dùng chung: 38 song song là đã sát trần (xem memory "LAN host KV-cache saturation"). Đừng tăng `EXTRACTOR_PARALLEL`.

## Đã sửa trong session này (chưa commit)
- `src/corpus/llm/tasks.py`: `Task.ask` (đường guided) đọc theo stream (`read_stream`) và ngắt khi gặp `RUNAWAY_WS`=300 ký tự trắng liên tiếp ⇒ ném `Runaway`, chỉ gọi lại thêm 1 lần (`RUNAWAYS`=2). Video lặp giờ lỗi sau ~40 s thay vì ~12 phút. **Không làm hết lỗi** (video vẫn không được kiểm): chỉ giải phóng slot sớm. Tác động chung: mọi `Task` guided đều đi qua stream (fallback đọc `message.content` nếu client không trả stream, để test cũ chạy). Cần cân nhắc: giữ thay đổi này ở `tasks.py` hay làm riêng cho `ASR_CHECK` — file này còn thay đổi chưa commit của việc khác.
- `tests/test_llm_task.py`: 3 test (ngắt vòng lặp và hỏi lại; vòng lặp lần hai thì lỗi sau 2 lời gọi; JSON in thụt lề không bị coi là lặp). `pytest tests/test_llm_task.py tests/test_llm_judge_parsing.py tests/crawl/tiktok tests/observe`: 205 pass.
- Chưa sửa `docs/` chính thức; khi chốt cách xử lý `screen_text`, cập nhật `docs/CORPUS.md` (phần `asr_check`) và `docs/LLM_PROVIDER.md` nếu đổi cách gọi stream.

## Việc cần làm tiếp (theo thứ tự)
1. **Quyết lược đồ `ASR_CHECK`** (xem mục 2): chạy `ASR_CHECK.ask` với `screen_text` tùy chọn trên ~10 video, trong đó ít nhất 3 video trước đó có `transcript.check.screen_text` khác rỗng (liệt kê bằng `video.json`), so `screen_text` mới với cũ; nếu mất chữ đáng kể thì thử `screen_text` dạng chuỗi hoặc tách lời gọi. Đổi `prompt_hash` chỉ khi đổi prompt; đổi lược đồ không làm các video đã kiểm bị kiểm lại.
2. Chạy lại `.venv/bin/python -u -m corpus tiktok asr_check --city dalat` đến khi `llm_errors` ≈ 0 (đo bằng `errors.jsonl`, stage `asr_check`). Rồi `place_verify`, `clips`; đọc `clips` summary (`full`) và ghi tỉ lệ yes / video tải vào `DEV_LOG.md` mục `tiktok-place-poi`.
3. Xử lý video quá dài (lỗi 400, mục 3).
4. Chỉ khi có `clips/dalat.json`: `free_tiktok_clips.py --verified --dry-run` rồi chạy thật; rồi Session A tiếp 689 nơi theo lô 50 (bên dưới), hoặc song song nếu host không quá tải.

Công cụ đã dùng (scratchpad session, có thể mất): script gọi thẳng `ASR_CHECK` với `max_tokens`/`temperature`/lược đồ thay đổi. Dựng lại: lấy `video.json`, `frames()`, `segment_lines()`, gọi `client.chat.completions.create(..., response_format=json_schema)` như `Task.ask`.

## Thứ tự bắt buộc (cả mọi session)
`poi_crawl` → `asr` → `asr_check` → `place_verify` → **`clips`** → mới được chạy `free_tiktok_clips.py --verified`. Xóa clip trước `clips` là mất clip để phát (phải tải lại). Không chạy `scripts/tiktok_place_loop.sh` cũ trong lúc này (nó xóa clip mà không qua `clips`).

---

## Tách việc cho các session song song

### Session A — CRAWL (trình duyệt + tải mp4), không dùng model/GPU
Phạm vi ghi: `data/tiktok/poi_crawl/`, `data/tiktok/videos/<id>/{info.json,video.json,video.mp4}` (chỉ video mới), `data/tiktok/poi_crawl_throttle.json`, `config/queries.yaml` khối `poi_*`.
1. Chạy hết 689 nơi còn lại theo lô, mỗi lô 50 nơi (~500 video, ~5 GB):
   `CORPUS_BROWSER_CHANNEL=chromium PLAYWRIGHT_BROWSERS_PATH=$PWD/.cache/ms-playwright .venv/bin/python -u -m corpus tiktok poi_crawl --city dalat --limit 50 >> logs/poi_crawl_dalat.log 2>&1`
2. Theo dõi: `tail logs/poi_crawl_dalat.log`, `grep '"poi_crawl"\|"download"' data/tiktok/errors.jsonl | tail`. 403 lúc tải: lần chạy sau tự làm lại nơi đó. Trang trống liên tục (throttle ghi `blocked`) = Akamai chặn mềm: dừng 15 phút (`docs/plans/SESSION_TIKTOK.md`, memory "TikTok Akamai block recovery"); trần `poi_tabs` 3.
3. Không cần người giải captcha. Nếu thấy captcha ở trang địa điểm (lỗi `LoginRequired`) thì dừng và báo người dùng, không chạy tiếp.
4. Đĩa: mp4 ~10 MB; giữ tổng chờ kiểm ≤ ~20 GB (Session B dọn sau `clips`).

### Session B — MODEL / GPU (kiểm chứng + chọn clip + dọn đĩa)
Phạm vi ghi: `video.json` trường `transcript` / `places`, `data/tiktok/clips/`, xóa mp4 bằng `free_tiktok_clips.py`.
1. Lặp mỗi khi Session A xong một lô: `asr` (GPU rảnh: `nvidia-smi`, `CUDA_VISIBLE_DEVICES=<g> ... asr --shard i/n`) → `asr_check` → `place_verify` → `clips` → `PYTHONPATH=src .venv/bin/python scripts/free_tiktok_clips.py --city dalat --verified --dry-run` rồi chạy thật.
2. `asr_check` / `place_verify` dùng Extractor (host LAN Gemma :9090). Nếu SESSION_MODEL đang build thì hỏi người dùng trước khi chạy song song.
3. Ghi một dòng vào `CORPUS_HANDOFF.md` §▶▶ mỗi lô: video mới có `place_verify` = yes là bằng chứng mới → SESSION_MODEL cần `tiktok observe` + `aggregate`.
4. Đo và ghi vào `DEV_LOG.md` mục `tiktok-place-poi`: tỉ lệ yes / video tải, số nơi đủ 6 clip.

### Session C — WEB (chỉ sau khi `clips/dalat.json` có dữ liệu)
Phạm vi ghi: `web/`, `web/public/data/snapshot.json`.
1. `python web/scripts/export_snapshot.py` (tạo lại cả snapshot từ `data/` hiện tại — mọi dữ liệu khác cũng mới theo) → kiểm `places[].videos[].local`.
2. Xem bằng dev (`./run.sh`, `http://127.0.0.1:5173/app`): mở một nơi có clip local, tab Đánh giá → "Clip của người đã đến": hover phát im lặng, bấm mở trình xem dọc, tua được, có @tác giả + "Mở trên TikTok". Chụp bằng `web/scripts/shots_sheet.mjs`. Chỉ thiết kế máy tính (điện thoại thấy GetApp).
3. Build kiểm thử ra thư mục tạm, **không ghi `web/dist`** (đang là site live). Đưa lên live (`./run.sh prod` dựng lại `web/dist`) **chỉ khi người dùng đồng ý**; site công khai sẽ phát lại video của người đăng từ server mình (đã luôn ghi tác giả + link gốc).
4. Kiểm qua tunnel Cloudflare: mp4 lớn qua Range có trả 206 không (`curl -I -H 'Range: bytes=0-99' https://tripguardian.visioncare-host.uk/media/tiktok/<id>/video.mp4`).

### Việc sau, không gấp (một session bất kỳ)
- 274 nơi chưa có POI (không có video bằng chứng nào gắn POI, hoặc model không chắc): cần cách khác để tìm POI (search POI của TikTok dính captcha; chưa thử).
- Nơi < 6 clip sau lô đầu: lấy thêm video kế tiếp trên trang địa điểm (hiện `poi_crawl` coi nơi đã có file là xong; cần cờ chạy lại cho nơi thiếu).
- Làm mới định kỳ (video mới trên trang địa điểm): chưa có.
- Commit: nhánh `feat/agent-harness-router` còn nhiều thay đổi chưa commit của các việc khác; chỉ commit đúng danh sách file ở mục "Đã xong" khi người dùng yêu cầu.
