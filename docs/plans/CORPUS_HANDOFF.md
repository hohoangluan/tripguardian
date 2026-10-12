# Bàn giao corpus (Maps, dalat) — 2026-10-06

File làm việc tạm (RULE §0.1): xong các bước dưới thì gộp phần còn giá trị vào `docs/CORPUS.md` và xóa file này.
Mô tả hành vi code: `docs/CORPUS.md`. Ở đây chỉ có trạng thái và việc còn lại.

## ▶▶ Crawl trên server SSH — đọc trước (cập nhật 2026-10-06 23:30 giờ VN)

**Chia việc cho 3 session (người dùng 2026-10-06):** `docs/plans/SESSION_GMAPS.md` (crawl Maps), `docs/plans/SESSION_TIKTOK.md` (crawl TikTok + ASR), `docs/plans/SESSION_MODEL.md` (observe / judge / build / đo chất lượng, chủ host LAN Extractor). Mỗi session chỉ sửa phạm vi của mình; mục này giữ phần chung (môi trường, quy tắc, số đo). Session nào xong một lô dữ liệu thì ghi một dòng vào "Nhật ký giữa các session" dưới đây.

### ▶▶▶ Còn gì để xong corpus (cập nhật 2026-10-07 21:05) — mọi session đọc mục này trước

**Host Gemma LAN (`192.168.20.150:9090`) đang TẠM DỪNG theo người dùng: không gửi call nào tới đó cho tới khi người dùng nói "bắt đầu".** `.env` `EXTRACTOR_BASE_URL` / `LLM_API_KEY` đã trỏ tới nó (chép từ `*_ANOTHER_HOST`, bản cũ `.env.bak_20261007`); host `:8899` là DeepSeek, không dùng. Trong lúc dừng, mọi lệnh model không có `EXTRACTOR_ON_UIT=1` sẽ gọi host LAN — đừng chạy.

**A. Đang chạy (không đụng; không chạy build / task UIT nào khác, key UIT 40 call):**
1. `logs/model_chain_2.sh` (log `logs/model_chain_2.log`): build `build_lan_8` xong 20:50 (1.779 nơi, mọi bước ok), `judge dedup` (9 cặp trùng) và `judge status` (2 đóng, 3 đổi) xong; đang `JUDGE_ENGINE=gemma EXTRACTOR_ON_UIT=1 judge audit` lặp đến khi hết việc (chọn mẫu), rồi aggregate → serving → snapshot → `decision evaluate`. Chỉ UIT.
2. `logs/model_chain_3.sh` (log `logs/model_chain_3.log`): chờ chuỗi 2 in `MODEL_CHAIN_DONE`, sao lưu nhãn → `data/review/judge_labels.before_read_all.jsonl`, rồi `JUDGE_READ_ALL=1` audit Gemma trên UIT đọc **mọi** nhận định (người dùng: sạch trước, nhận định đúng bị bỏ nhầm ~30% vớt lại sau) → aggregate → serving → snapshot → evaluate. Chỉ UIT. Ước lượng thô hai chuỗi xong ~02:00–05:00 ngày 08/10.
3. `logs/tiktok_nogemma_lane.sh` (log `logs/tiktok_lanes.log` dòng `nogemma`): `place_crawl` 615 video `place_filter` đã giữ (2 tài khoản, 9543/9544) → `asr` trên mọi GPU trống. Không dùng Gemma.
4. TikTok `place_search` (`logs/tiktok_search_1007d_s*.log`, DevTools 9541/9542): còn 1.259 nơi, chờ người giải captcha.

**B. Đã xong hôm nay:** Maps crawl theo danh sách `min_reviews` 30 (crawl / relevant / extremes / keywords xong lúc 20:12; photos còn 19 nơi thiếu ảnh, 135 nơi Maps không tải thêm review được — chấp nhận). Runner Maps sửa lỗi chết khi nhiều runner ghi `throttle.json` (`scripts/gmaps_runner.py`). TikTok `asr` / `asr_alt` cho mọi video đã tải trước 21:00.

**C. Tạm dừng, chạy lại khi người dùng nói "bắt đầu" (đều cần Gemma LAN):**
1. **Maps model** (ưu tiên 1): `logs/gmaps_lan_lane.sh` (log `logs/gmaps_lan_lane.log`) — `gmaps qc` xong 21:00, `gmaps observe` bị dừng giữa chừng (làm tiếp từ chỗ dừng), rồi `photo_observe`. Chạy: `setsid nohup logs/gmaps_lan_lane.sh > logs/gmaps_lan_lane.log 2>&1 < /dev/null &`, chờ `GMAPS_LAN_DONE`.
2. **LAN phụ UIT cho audit** (sau C1, nếu chuỗi 2 / 3 còn chạy audit): code đã có `JUDGE_ALSO_LAN=1` (audit Gemma trên UIT lấy thêm slot host LAN, mỗi call đi endpoint nào rảnh, `audit.Pool`). Chuỗi đang chạy KHÔNG có cờ này; muốn dùng thì dừng chuỗi đang ở bước audit (`kill -- -<pgid>` của script chuỗi, không `pkill -f`) và chạy lại phần còn lại của nó với `JUDGE_ALSO_LAN=1` thêm vào lệnh audit. Nhãn ghi nối tiếp nên dừng giữa chừng không mất gì.
3. **TikTok model** (sau C1 và C2, hoặc khi UIT rảnh): `logs/tiktok_lan_lane.sh` (12 call; mỗi vòng `place_filter` → `place_crawl` song song `asr_check` → `place_verify` → xóa clip → `asr` / `asr_alt` trên GPU). Còn: `place_filter` 1.758 video, `asr_check` 3.099, `place_verify` 4.374 (1.441 chờ ASR / asr_check).

**D. Để corpus xong (theo thứ tự):**
1. A1 + A2 xong (`MODEL_CHAIN_DONE` trong `logs/model_chain_3.log`).
2. C1 xong (observe Maps cho phần review / ảnh mới), C3 xong (video TikTok mới qua `place_verify`).
3. **Build cuối**: `OBSERVE_KEEP_STALE=1 EXTRACTOR_ALSO_UIT=1 python -m corpus build --city dalat --skip "judge audit"` → `JUDGE_READ_ALL=1 JUDGE_ENGINE=gemma EXTRACTOR_ON_UIT=1 JUDGE_ALSO_LAN=1 python -m corpus judge audit --city dalat` → `python -m corpus aggregate --city dalat` → `python -m corpus serving --city dalat` → `python web/scripts/export_snapshot.py` → `python -m decision evaluate`.
4. **Corpus xong khi**: build cuối mọi bước `ok`; `decision evaluate` 0 violation, filled_rate không thấp hơn 0,967 (mốc 06/10); so số VERIFIED / UNCERTAIN với kết quả chuỗi 2 (chấm mẫu) và chuỗi 3 (đọc hết). Rồi gộp phần còn giá trị của `SESSION_*.md` và file này vào `docs/CORPUS.md`, xóa chúng; commit khi người dùng yêu cầu (code chưa commit: `scripts/gmaps_runner.py`, `src/corpus/judge/audit.py`, `src/corpus/llm/roles.py`, `src/corpus/crawl/tiktok/asr.py`, `asr_alt.py`, `src/corpus/__main__.py`, tests, `config/queries.yaml` `min_reviews` 30).

**E. Làm thêm sau khi corpus xong (tùy người dùng):**
- Vớt nhận định đúng bị Gemma bỏ nhầm: các dòng nhãn sau độ dài `judge_labels.before_read_all.jsonl`; cần Judge khác họ model hoặc người duyệt.
- TikTok `place_search` 1.259 nơi còn lại (người ngồi giải captcha) → C3 → build cuối lại. `comments_crawl` 35 video.
- Maps mở rộng (SESSION_GMAPS §Việc): search thêm (`max_zoom` 15, thêm categories), `keyword_sets`, cho `extremes` / `relevant` lấy thêm ở nơi cũ. Nơi lưu trú: người dùng quyết định không thêm.
- Observation của nơi dưới 30 review sao lưu ở `data/gmaps/observations_under30_backup/` (dùng lại nếu hạ `min_reviews`).

Crawl đã chuyển từ máy Windows sang server (`/workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian`, Ubuntu 20.04, không sudo, không màn hình, repo trên NFS). Mục "Đang chạy" ở phần ▶ bên dưới (runner trên Windows) đã hết hiệu lực.

### Quy tắc người dùng đặt cho server
- **Chỉ làm trong thư mục repo**: venv `.venv/`, Chromium `.cache/ms-playwright/`, cache uv `.cache/uv/`, profile/cookie `.browser/`, script và log `logs/` (gitignored). `.venv/` và `.cache/` loại khỏi git bằng `.git/info/exclude`. Ngoại lệ bắt buộc: file tạm lúc chạy của Chromium ở `/tmp` (Chrome không chạy được nếu `TMPDIR` nằm trên NFS).
- Không tự giải captcha (kể cả bằng model). Captcha do người dùng giải qua DevTools (dưới).
- Không commit/push khi chưa được yêu cầu.

### Môi trường
- `.venv` (Python 3.12, `uv`), **`playwright==1.52.0`** (bản mới hơn không có Chromium cho Ubuntu 20.04), `torch` (GPU), `chunkformer`, `silero-vad`, `transformers`, `psutil`, `py-spy`. Máy không có Chrome → mọi lệnh crawl cần `CORPUS_BROWSER_CHANNEL=chromium PLAYWRIGHT_BROWSERS_PATH=$PWD/.cache/ms-playwright`.
- **Cookie trong bộ nhớ** (`CORPUS_PROFILE_STATE=1`): đọc/ghi `.browser/<tên>.json` (`gmaps`, `gmaps_s<i>`, `tiktok`, `tiktok2`). Profile Chrome thư mục trên NFS làm trang Maps >200 s không tải xong — đừng chạy crawl không có biến này. Thư mục `.browser/gmaps_s*`/`gmaps_t` là bản sao cũ, xóa được.
- **Giải captcha / đăng nhập từ xa**: mỗi tiến trình mở cổng DevTools `CORPUS_DEBUG_PORT` (chỉ 127.0.0.1). Người dùng `ssh -L <port>:localhost:<port>`, mở `chrome://inspect` → Configure → `localhost:<port>` → inspect → thao tác trên khung screencast. Cổng: gmaps shard i = `9520+i`, đăng nhập gmaps `9530`, TikTok `9541`/`9542`. (9333, 9338 bị người khác chiếm.) Đăng nhập lại Google: `CORPUS_DEBUG_PORT=9530 ... python -m corpus login gmaps`, người dùng đăng nhập rồi đóng tab → lưu `.browser/gmaps.json`.
- `certs/uit-ca-bundle.pem` đã tạo trên server (`docs/LLM_PROVIDER.md` §Chứng chỉ TLS). **Extractor chạy trên host LAN** với 256 call đồng thời (`docs/LLM_PROVIDER.md` §Host LAN); Agent vẫn ở UIT.

### Đang chạy (không đụng trừ khi dừng hẳn)
- `logs/probe.py` (pid ghi trong `ps`, log `logs/probe.log`): tự dò số tab tối đa không bị chặn cho từng nguồn, mỗi mức giữ 6 phút (gmaps) / 12 phút (TikTok), chặn đầu tiên → dừng, ghi mức, nghỉ 30 phút, chạy tiếp ở mức dưới đến hết.
  - gmaps extremes: mức 36 → 48 → 64 → 80 tab (`6x6`, `6x8`, `8x8`, `10x8` tiến trình × tab). 36 tab sạch, **12,9 nơi/phút**; 48 tab sạch, 12,5 nơi/phút (phép đo lệch do khởi động lại giữa mức); 64 tab (8 × 8) **~18 nơi/phút** (23:25–23:30, sạch). **Extremes xong 23:30** (1.466 file, 0 nơi còn), chưa dò được mức 80 vì hết việc. TikTok 6 tab: ~36 video/phút, sạch.
- `photos` (22 nơi, 3 tab) rồi `keywords` (0 nơi): runner riêng, log `logs/gmaps_photos_1.log`, in `GMAPS_RUNNER_DONE` khi xong. Captcha không tính là chặn (người dùng giải), chỉ `GMAPS_RUNNER_STOPPED` (3 lần không giải / bị đăng xuất). Log từng shard `logs/gmaps_p<n>_s<i>.log`.
  - TikTok `place_crawl` (2 tài khoản, `CORPUS_FIXED_TABS=1`, tab đặt qua `data/tiktok/throttle*.json`): 4 tab sạch, **28,8 video/phút**; đang ở 6 tab, còn ~780 video. Chặn = captcha hoặc lỗi `no item data` > số video tải trong 3 phút (Akamai "Access Denied" không có captcha). Log `logs/tiktok_p<level>_s<shard>.log`.
- Muốn dừng: `kill` pid của `logs/probe.py`, rồi `kill -- -<pid>` từng runner/tiến trình con (mỗi cái chạy trong session riêng). **Đừng dùng `pkill -f <chuỗi>`** — khớp luôn shell đang gõ lệnh.

### Số đo hôm nay (một IP server)
| Nguồn | Cấu hình | Tốc độ | Kết quả |
|---|---|---|---|
| gmaps extremes | 1 tiến trình × 16 tab | ~0 | một tiến trình Python chạm 100% một core ở ~8 tab → timeout. Phải chia tiến trình (`--shard`) |
| gmaps extremes | 6 × 6 = 36 tab | 12–13 nơi/phút | lần 1 (21:32): captcha sau ~10 phút rồi **Google đăng xuất tài khoản**; lần 2 (23:12, vừa đăng nhập lại): sạch 6 phút |
| TikTok place_crawl | 2 × 5 = 10 tab, `pause_s [0.3,1]` | ~33 video/phút | sau 5 phút **Akamai chặn IP** (cả 2 tài khoản), gỡ sau <40 phút |
| TikTok place_crawl | 2 × 2 = 4 tab, `pause_s [1,3]` | 28,8 video/phút | sạch 12 phút |
| Gemma host mới (`ANOTHER_HOST`, LAN) | prompt ngắn ~250 tok | 128 đồng thời ≈ 4.600 req/phút; 192 ≈ 5.400; 320 ≈ 6.300 (p95 5,5 s) | 0 lỗi khi có `max_retries=2` |
| Gemma host mới | prompt dài ~2k tok vào/300 ra (cỡ observe) | 128 ≈ 1.130 req/phút (p95 7 s); 192 ≈ 1.290; 256 ≈ 1.480 (p95 11 s) | 0 lỗi; gối ~192–256 |

Script đo model: `logs/llm_probe.py` (`LEVELS=… LONG=1 RETRIES=2`), kết quả `logs/llm_probe_*.log`.

### Thay đổi code chưa commit (phiên này)
- `src/corpus/crawl/common/browser.py`: `CORPUS_BROWSER_CHANNEL`, `CORPUS_DEBUG_PORT` (captcha/login chờ người qua DevTools), `CORPUS_PROFILE_STATE` (cookie trong bộ nhớ ↔ `.browser/<tên>.json`).
- `src/corpus/crawl/gmaps/{crawl,relevant,extremes,keywords,photos}.py` + `src/corpus/__main__.py`: `--shard i/n --profile <tên>` cho các bước gmaps dùng trình duyệt.
- `scripts/gmaps_runner.py`: `GMAPS_HEADLESS`, `GMAPS_SHARD`, `GMAPS_PHASES`; thêm `crawl`, `relevant` trước `extremes`; captcha không ai giải 3 lần → `GMAPS_RUNNER_STOPPED`.
- `src/corpus/crawl/tiktok/crawl.py`: tải mp4 bằng `httpx` stream với cookie của context (`ctx.request` của Playwright 1.52 nối body theo bình phương: 55 MB chiếm một core nhiều phút; stream ~4 s). `trust_env=False` để không dính `SSL_CERT_FILE`.
- `config/queries.yaml`: `gmaps.tabs` 10 → 24 (trần), `tiktok.tabs` 5 → 8 (trần cho probe), `tiktok.pause_s` `[0.3,1]` → `[1,3]`.
- `src/corpus/llm/roles.py`, `tasks.py`: `Role.parallel_env` / `Role.parallel()`; task Extractor không đặt `parallel` thì lấy `EXTRACTOR_PARALLEL` (bỏ các số 8/24/38/16 cắt theo key UIT). `.env.example` thêm `EXTRACTOR_PARALLEL`; `docs/LLM_PROVIDER.md` thêm §Host LAN.
- `.env` (không theo git): `LLM_API_KEY` / `EXTRACTOR_BASE_URL` / `EXTRACTOR_MODEL` trỏ host LAN, `EXTRACTOR_PARALLEL=256`, giá trị UIT cũ giữ dạng comment `# UIT (fallback)`.
- `throttle.py` (sửa giữ mức RAM-guard) đã có trong `c064005`.

### Việc tiếp theo
Theo từng session: `SESSION_GMAPS.md`, `SESSION_TIKTOK.md`, `SESSION_MODEL.md`. Sau cả ba: các việc của mục ▶ dưới (đo sau build, zip cho team, UI báo cáo…).

### Nhật ký giữa các session (mới nhất ở cuối; một dòng mỗi lô)
- 2026-10-06 23:30 GMAPS: `extremes` xong, +~370 nơi có review cực trị cần observe.
- 2026-10-06 23:40 TIKTOK: `place_crawl` +~1.200 mp4 (còn ~280), chưa ASR.
- 2026-10-07 06:55 TIKTOK: `place_crawl` với `crawl_videos_per_place: null` xong (3.309 mp4 trên đĩa, 9 video lỗi); ASR xong hết mp4 còn lại, `asr_check` lần 1 xong 837 video; đang `asr_check` → `place_verify` (chuỗi `logs/tiktok_verify_chain.sh`) → video mới có `place_verify` chờ SESSION_MODEL observe. `place_search` (3.065 nơi mới + nơi cũ chưa đủ 20 video) đang chạy, cần người giải captcha search ở DevTools 9541/9542; `place_filter` chạy sau mỗi lô search.
- 2026-10-07 TIKTOK (số đo/chặn): 8 tab/tài khoản (16 tab) ~50 video/phút được ~9 phút rồi Akamai trả `no item data` hàng loạt (không captcha); gỡ sau ≤15 phút. `tiktok.tabs` 5, `cooldown_s` 300; `MissWatchThrottle` (crawl.py) coi 6/10 trang rỗng là bị chặn. Search API bị captcha slider riêng (body rỗng) — `collect` giờ chờ người giải; cookie lưu mỗi 60 s (`browser.STATE_SAVE_S`) để tiến trình bị kill không mất captcha đã giải.
- 2026-10-07 06:50 TIKTOK: `place_crawl` xong bản không trần (6.689 video "yes"; chỉ ~9 lỗi); ASR + `asr_check` đã chạy ~2.900 video, `place_verify` chưa. `place_search` 20 video/nơi cho ~4.400 nơi (mới + cũ) đang chạy, ~6 nơi/phút, cần người giải captcha khi hiện (DevTools 9541/9542). Pipeline nền `logs/tiktok_pipeline.sh` (log `logs/tiktok_pipeline.log`) lặp filter → crawl → asr → check → verify; captcha của crawl ở 9543/9544.
- 2026-10-07 09:20 GMAPS+TIKTOK: chạy gắn vào 2 cửa sổ đăng nhập Google (`CORPUS_ATTACH_URL`, sửa `_attach`: tab và cookie đi qua CDP đúng context đã đăng nhập — trước đó mọi lần attach báo "login needed" ngay). `logs/gmaps_dist.sh 4` = 4 runner/tài khoản × 8 tab (64 tab): ~15 nơi/phút sạch, phase `crawl` còn ~3.550 nơi. Captcha giờ chờ người giải không giới hạn, giải xong tab đi tiếp không retry (người dùng); Maps: cổng 9530 (A) / 9533 (B), TikTok search 9541/9542 (trần `place_search_tabs` 8). Theo dõi: `logs/crawl_watch.sh`.
- 2026-10-07 09:40 TIKTOK: `logs/tiktok_pipeline.sh` dừng (`place_crawl` shard 1 treo từ 08:30, ASR chờ theo). Thay bằng `logs/tiktok_lanes.sh` (log `logs/tiktok_lanes.log`): luồng trình duyệt filter → crawl → comments và luồng GPU asr → check → alt → verify → xóa clip chạy song song. GMAPS: sửa rò tab khi nhiều tiến trình gắn chung một trình duyệt (khớp theo `targetId`), `crawl`/`relevant` chặn bản đồ/ảnh (`text_only`), renderer Maps `nice` 10 để giải captcha mượt. Còn lại: `logs/crawl_todo.py`.
- 2026-10-07 10:40 GMAPS+TIKTOK: TikTok `place_search` và `comments_crawl` dừng theo người dùng (captcha dày, giải bị giật); GMAPS 8 runner và TikTok `place_crawl` + ASR/verify chạy tiếp không cần người. Trạng thái, số còn lại và lệnh chạy lại: `SESSION_GMAPS.md`, `SESSION_TIKTOK.md` §Trạng thái. Video mới có `place_verify` liên tục chờ SESSION_MODEL observe.
- 2026-10-07 13:45 MODEL (người dùng yêu cầu): build chạy lại với `EXTRACTOR_ALSO_UIT=1` (`logs/build_lan_7.log`): `gmaps observe` dùng host LAN x38 + UIT x38, ~198 nơi/10 phút (trước 28). Verify TikTok tạm dừng để nhường UIT. GMAPS: `text_only` chuyển sang chặn ảnh theo tab (chặn theo context làm hỏng ảnh của `photos` ở tiến trình khác: 102 lỗi), runner khởi động lại 13:41.
- 2026-10-07 16:00 GMAPS+TIKTOK: `gmaps.min_reviews` 30 (danh sách 1.779 nơi, observation nơi dưới 30 sao lưu ở `data/gmaps/observations_under30_backup/`). Observe còn 646 nơi trên danh sách mới; build `build_lan_7` vẫn chạy theo danh sách cũ (thêm ~1.600 nơi sẽ bị xóa ở lần observe sau). TikTok `asr` xong, `asr_alt` chia 5 GPU.
- 2026-10-07 18:10 MODEL: `build_lan_7` xong 17:14 (serving 3.571 nơi, còn gồm nơi dưới 30 review). Chuỗi `logs/model_chain_2.sh` (log `logs/model_chain_2.log`): build trên danh sách 1.779 nơi → Judge dedup/status trên Gemma UIT → audit engine Gemma trên UIT lặp tới khi hết việc → aggregate → serving → snapshot → `decision evaluate`. Không chạy build hay task UIT khác khi chuỗi đang chạy.
- 2026-10-07 20:00 ALL: checklist "Còn gì để xong corpus" ở đầu §▶▶. TikTok: mọi video đã lọc đã tải (còn 5), video mới chờ `place_filter` 3.473 (model) và `place_search` 1.259 (captcha). Maps: `gmaps_passes.sh` xong.
- 2026-10-07 21:05 ALL: host Gemma LAN tạm dừng theo người dùng; checklist §▶▶▶ viết lại (A đang chạy / C chờ "bắt đầu" / D để xong / E làm thêm).
- 2026-10-08 00:20 GMAPS+MODEL (người dùng cho dùng lại host LAN): (1) crawl Maps **xong**. Crawl lại 135 nơi thiếu review (phần lớn dừng ở 180–350 review dù Maps báo hàng nghìn) không lưu thêm được nơi nào trong 20 phút → chấp nhận, không chạy lại; `photos` còn 3 nơi (từ 19). (2) `gmaps observe` xong trên host LAN (48 nơi mới, 3 lỗi, 1.725 đã có); `photo_observe` đang chạy (`logs/gmaps_lan_lane.sh`). (3) Audit đọc-hết của chuỗi 3 từng treo 70 phút vì `audit.label_with` render cả 46k call trước khi giành slot (đọc 84 GB đĩa, vòng async không xử lý được trả lời); đã sửa (giành slot rồi mới render), chạy lại bằng `logs/model_chain_3b.sh` với `JUDGE_ALSO_LAN=1` (UIT x38 + LAN x38), ~250 call/phút, 46.087 call → xong khoảng 03:30 rồi aggregate → serving → snapshot → evaluate (log `logs/model_chain_3.log`).
- 2026-10-09 08:40 GMAPS → MODEL: crawl chỗ ở `dalat_stay` **xong** (8 runner `GMAPS_RUNNER_DONE` 03:24–03:41, 0 captcha). `list/dalat_stay.json` 1.524 chỗ ở; có `reviews.json` (300 review mới nhất) 1.517, `reviews_extremes.json` 862, `photos.json` 845, `reviews_relevant.json` 104; 7 chỗ ở chưa có review. SESSION_MODEL observe nhóm `stay` (observe / photo_observe đọc cả hai danh sách qua `files.listed`) → aggregate → `python -m corpus serving`; serving ≥ `stay_min` (50) chỗ ở thì Planning tự chuyển sang corpus, khởi động lại harness để nạp serving mới. Chi tiết: `SESSION_MODEL.md` ▶ Chỗ ở.

### Kiểm nhanh (server)
```sh
cd /workingspace_aiclub/WorkingSpace/Personal/vannk/tripguardian
cat logs/probe.log                                         # mức tab, tốc độ, chặn
ls data/gmaps/places/*/reviews_extremes.json | wc -l       # extremes đã có
grep -h "left" logs/tiktok_p*_s*.log | tail -2             # TikTok còn bao nhiêu
ps -u $(id -u) -o pid=,etime=,args= | grep -E "[p]robe.py|[g]maps_runner|[c]orpus tiktok"
```

## ▶ Việc cho phiên sau — đọc mục này trước (cập nhật 2026-10-06 19:05 giờ VN)

Các mục phía dưới là lịch sử và lý do; mục này là trạng thái đúng hiện tại.

### Trạng thái
- **Code:** đã push, `origin/main` = local (`9f6e19d`). Chỉ còn `src/corpus/crawl/common/throttle.py` sửa dở của phiên khác — không commit, không đụng.
- **Data zip cho team:** `tripguardian-data-20261006.zip` (3,71 GB, có ảnh, CRC ok) ở gốc repo, chờ người dùng tự upload Drive.
- **Corpus:** build Gemma xong 10:57 UTC; aggregate + serving + snapshot web chạy lại 11:40 UTC. Serving: VERIFIED 23.004 · UNCERTAIN 6.289 · OUTDATED 2.606 · 771 nơi trải nghiệm. `decision evaluate`: filled_rate **0,967**, 1 trip chưa đủ (`group_food`), 0 violation, 0 unknown trong danh sách chính.
- **Chờ Gemma:** 1.369 claim chưa audit (1.285 chữ, 84 ảnh) + các nơi có review `extremes` mới từ sau build (chưa observe).

### Đang chạy — không đụng (hết hiệu lực: crawl đã chuyển lên server, xem mục ▶▶)
- `logs/gmaps_runner.py` (log `logs/gmaps_runner_17.log`, do `logs/gmaps_after_build.py` của phiên khác bật): luân phiên extremes → photos → keywords. `extremes` còn **607 nơi** (runner đếm lúc 18:02 giờ VN, 1.098 file đã có). Không có job Gemma nào chạy.

### Quy tắc đã chốt với người dùng — không đổi khi chưa hỏi
1. **Gemma là engine duy nhất của corpus.** Sol (Codex) chỉ dùng cho task người dùng giao (gen ảnh…), không chấm, không kiểm corpus. Kiểm chất lượng = tự đọc nguồn, không gọi model, không ghi nhãn người.
2. **Không extract lại cả thành phố** khi đổi prompt/ontology: `OBSERVE_KEEP_STALE=1` (đã đặt trong `logs/quality_pass.py`); luật mới chỉ áp cho dữ liệu mới.
3. **Cổng precision** đo bằng nhãn chính xác khi có ≥30 (`labels.stats`, cột `measured_by`); nhãn Gemma chỉ để lọc claim.
4. **Effort theo im lặng** (`steep_or_stairs`, `long_walk`, `rough_road_access`): 0 người nhắc → `absent`; ≥1 người nhắc `present` → `present`; vừa có vừa không → không xác định.
5. **Báo cáo người dùng:** 8 người khác nhau báo cùng một ý (`REPORTS_MIN`) mới thành bằng chứng (nguồn authoritative).
6. Không chạy hai build hay hai audit cùng lúc; không chạy việc khác trên key UIT khi build (key 40 call, build dùng 38). Build bị kill vì hết RAM thì chạy lại là được — mọi bước resume.

### Việc cần làm, theo thứ tự
1. **Build Gemma** khi crawl `extremes` xong (hoặc sớm hơn nếu cần dữ liệu ngay; không chạy lúc đang nén zip):
   `python -u logs/quality_pass.py > logs/quality_pass.log 2>&1` → xong khi log có `QUALITY_PASS_DONE`. Rồi `python web/scripts/export_snapshot.py` và `python -m decision evaluate`.
2. **Đo sau build** và so mốc ở "Trạng thái": serving status, evaluate; tự đọc ~40 nhãn Gemma `correct` mới đối chiếu review gốc.
3. **Zip lại cho team** nếu dữ liệu đổi đáng kể: `python scripts/pack_data.py` (cần ~4 GB trống, không chạy khi build đang ghi `data/`). Người dùng tự upload.
4. **UI báo cáo** (phiên web): nút "Báo thông tin sai" + ô nhập chữ trên thẻ nơi → `POST /api/reports {place_id, text, reporter}`, `reporter` là id ẩn danh trình duyệt giữ (6–64 ký tự).
5. **Đo lại `REPORTS_MIN`** khi có báo cáo thật (báo cáo vượt ngưỡng có khớp bằng chứng tìm thấy sau không).
6. **Đo luật v10 trên dữ liệu mới** (nhận dạng nơi trong `REVIEW_OBSERVE`, chủ thể ảnh trong `PHOTO_OBSERVE`, 15 feature siết): so ở mức (nơi, feature, value) với nhãn mạnh, **không so ở mức quote** (quote đổi là trượt key, ra số ảo). Giảm claim sai rõ thì mới cân nhắc tắt `OBSERVE_KEEP_STALE` để extract lại cả bộ.
7. **Cần người dùng quyết:** `judge dedup` / `judge status` cho nơi mới (cần sol); 43 website official lỗi (`python -m corpus official pages` sau vài ngày); trip `group_food`; hiệu chỉnh gate / tách cờ `risky`–`second_read` (mục "Chưa quyết"); số phận `throttle.py` của phiên khác.

### Kiểm nhanh
```sh
cd D:/Study/mlai/tripguardian
tail -3 logs/gmaps_runner_17.log                      # crawl còn bao nhiêu nơi
grep -E "^(===|build dalat|ok |FAILED|QUALITY_PASS_DONE)" logs/quality_pass.log
python -m decision evaluate                           # filled_rate, violations
```

## Trạng thái hiện tại (cũ — xem mục ▶ ở trên)

- **Đang chạy (14:35 giờ VN):** crawl Maps (`logs/gmaps_runner.py`, log `logs/gmaps_runner.log`), phase `extremes`, headed; và build `logs/quality_pass.py` → `logs/quality_pass.log` (bắt đầu 07:32 UTC, `corpus build --city dalat --skip "judge dedup" "judge status"`, `OBSERVE_KEEP_STALE=1`, audit trên Gemma). Xong khi log có `QUALITY_PASS_DONE`.
- **Còn lại (đo 07:35 UTC 2026-10-06):**
  - `extremes`: 778 nơi xong, còn ~690 nơi; tốc độ 5,8 nơi/phút → **~2 giờ**.
  - `photos`: còn ~30 nơi. `keywords`: xong (1.151 nơi, 0 nơi thiếu từ).
  - Build đang chạy: observe lại 64 nơi (xem "Phiên này" bên dưới) + nơi có review mới, rồi Gemma audit claim chưa nhãn → **~1–1,5 giờ**.
  - Build cuối sau khi crawl xong (chỉ nơi có review mới): **~1,5–2,5 giờ**.
  - **Corpus xong ước ~11:30–12:00 UTC (18:30–19:00 giờ VN) 2026-10-06.**
- **Judge audit:** xong bằng Gemma (2026-10-06 10:16, mục "Judge" bên dưới). Chuỗi sol cũ (`judge_chain3.sh`) đã dừng, bỏ.
- **Build đầy đủ xong** 2026-10-06 13:22 (2 giờ 52 phút; mọi bước `ok`, dedup/status bỏ qua): `logs/build_gemma.sh` → `logs/build_gemma.log` (`BUILD_GEMMA_DONE`). Observe đọc mới 652 nơi Maps, 167 nơi ảnh, 44 nơi TikTok. Audit Gemma 1 vòng (1 giờ 49 phút): correct 15.414, wrong 11.705, unsure 4.975, ảnh-correct-chờ-sol 3.353, lỗi 4. Lỗi `RuntimeError: Event loop is closed` trong log chỉ là cảnh báo dọn client.
- **Số đo sau build** (nơi trải nghiệm 772; trước → sau): `decision evaluate` filled_rate 0,467 → **0,767**, uncertain_in_main 38 → 4, violations 0, trip chưa đủ 16 → 7 (`elderly_views`, `wheelchair_cafe`, `group_food`, `cross_16..19`). VERIFIED: dốc/bậc 136 → 149, đi bộ xa 43 → 62, đường xấu 184 → 202, người lớn tuổi 60 → 60, **đặt chỗ 266 → 38** (Gemma loại nhầm nhiều claim booking đúng → precision tầng dưới cổng → UNCERTAIN; sol chấm lại sẽ phục hồi). Một phần mức tăng filled_rate có thể do code sau lần đo cũ, không chỉ do build này.

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

1. **Keywords: XONG (2026-10-06).** Config có 11 từ (`config/queries.yaml` → `keyword_sets`), không phải 9. Đã đối chiếu bằng `words_for`/`missing`: 0 nơi thiếu từ. 2 mục `người già` còn `complete: false` (`reviews_keywords.json`), chưa xử lý; chạy lại `gmaps keywords` không chọn được vì từ đã có trong file.
2. **Chạy lại Maps khi mạng ổn:** `python logs/gmaps_runner.py` (headed, thứ tự: extremes → photos → keywords). Nếu có captcha, runner mở cửa sổ; người dùng giải rồi để nó chạy tiếp. Nếu treo 10 phút không ghi file, runner tự dừng phase và chạy lại.
3. **Kiểm chất lượng sau mỗi đợt crawl** (script kiểm nằm ở `tests`/ad hoc; kiểm: số review mỗi danh sách, thứ tự sao, trùng review, file ảnh thiếu). Lần kiểm 2026-10-06: extremes có 8% file bị trộn trước khi sửa `8ae690d`; 20 file đã xóa để crawl lại; các file mới đều đúng thứ tự.
   - Kiểm lại 2026-10-06 (345 file extremes): thứ tự sao đúng hết, 0 review trùng trong một danh sách. 2 file có `complete: false` sau hết lượt thử (`0x317113003135e6b3…` lowest, `0x317113004328df75…` highest): đã xóa để crawl lại. "lowest có sao >2" và "highest có sao <4" là bình thường khi nơi có ít hơn 30 review ở mức đó, không phải lỗi.
   - Sửa `logs/gmaps_runner.py` (log ignore, không commit): khi RAM guard hạ tab, công thức cũ `max(4, limit-3)` làm tab từ 1 **tăng** lên 4. Nay: floor 4 nếu limit ≥ 4, còn lại floor 1.
4. **Build:** đang chạy (xem Trạng thái). Khi Maps crawl thêm dữ liệu, chạy lại đúng lệnh trong `logs/build_gemma.sh` (`python -m corpus build --city dalat --skip "judge dedup" "judge status"`); build tự bỏ qua phần không đổi. Không chạy hai build hay hai audit cùng lúc.
5. **Sau build:** đo khoảng trống trên nơi trải nghiệm của `data/serving/places.json` và `python -m decision evaluate`. Số đo gần nhất (build tạm 2026-10-05 15:47 UTC): dốc VERIFIED 136, đi bộ xa 43, người lớn tuổi 60, đường vào xấu 184, đặt chỗ 266 trên 772 nơi trải nghiệm. Thời gian tham quan mặc định 742/772; giá vé trống 597/772.
6. **Kiểm Judge** sau build: lấy ~40 nhãn Gemma `correct` (chữ) mới, đọc review gốc. Không tự ghi nhãn người.
8. **Khi có quota Codex lại** (thử: `curl` tới `$9ROUTER_API_URL/v1/chat/completions` với `cx/gpt-6.1-sol`): xem mục "Judge" → "Khi sol có quota".
7. **Official:** 43 site lỗi (`data/official/errors.jsonl`). Chạy lại `python -m corpus official pages` sau vài ngày.

## Chất lượng corpus: việc còn lại (ưu tiên cho độ tin cậy)

Đã sửa so với audit 2026-10-05 (kiểm trên dữ liệu 2026-10-06): tác giả TikTok (0/14.469 thiếu), video của chính quán gắn `owner`, ảnh không rõ người đăng = 1 phiếu/nơi, qc chạy, mẫu extremes/keywords không lệch cảm nhận, giá vé official + review gần đây, gộp/đóng cửa cần Judge mạnh.

| # | Việc | Vì sao | Cần |
|---|---|---|---|
| 1 | ~~Sol 6.1 chấm lại nhãn Gemma~~ **BỎ** (người dùng 2026-10-06): sol ra khỏi corpus, giữ quota cho việc họ chỉ định | Gemma lọt 11–16% claim sai (ảnh 35%), loại nhầm ~30% — chấp nhận, bù bằng siết prompt | Xem "Vai trò hai model" |
| 2 | Người kiểm có lấy mẫu chính Judge: ~30 claim mỗi giá trị rủi ro (dốc/bậc, đi bộ xa, thời tiết, đặt chỗ, người già / trẻ em / xe lăn) | Gold hiện chỉ 156 claim; con số "chính xác X%" phải từ người | Người dùng, `/admin/labels`; agent không tự ghi nhãn người |
| 3 | `judge dedup` + `judge status` cho nơi / báo cáo đóng cửa mới | Nơi đóng / trùng làm mất tin ngay | Quota sol |
| 4 | Crawl Maps phần thiếu (extremes ~1.120 nơi, ảnh ~32, kiểm keywords) | Thiếu bằng chứng effort cho bộ lọc cứng | Mạng ổn, headed (bước 1–2 ở trên) |
| 5 | 7 trip chưa đủ: xem thiếu feature nào (người già + view, xe lăn + cafe, nhóm ăn) | filled_rate 0,767 | Sau #1, #4 |
| 6 | 43 website official lỗi | Giá vé / giờ chuẩn nhất | `python -m corpus official pages` |
| 7 | Làm mới định kỳ (crawl → build) | Đóng cửa, đổi giá | Sau #1–#4 |

## Vai trò hai model (người dùng quyết 2026-10-06)

- **Gemma là engine chính của corpus.** `.env` giữ `JUDGE_ENGINE=gemma`; mọi build chạy observe + audit trên Gemma (miễn phí, cần mạng UIT). Audit: 1 vòng, 8 nhận định/call, 38 call song song.
- **Sol ra khỏi corpus hoàn toàn.** Quota gần hết và người dùng giữ phần còn lại cho việc họ chỉ định (gen ảnh hoặc task khác): không dùng sol để chấm corpus, **cũng không dùng để kiểm tra**. 48.507 nhãn mạnh đã có (sol 41.400 + 6.1-sol 4.498 + astra 2.405 + sonnet 204) vẫn đứng và vẫn nuôi gate; `judge dedup` / `judge status` giữ quyết định cũ, build vẫn `--skip` hai bước đó.
- Hệ quả đã chấp nhận (ưu tiên precision): Gemma `wrong`/`unsure` bỏ nhận định ngay, `correct` trên ảnh ghi thành `unsure`. Gemma bỏ oan ~30% nhận định đúng — đó là giá của việc không có sol trong dây chuyền. Cách bù là siết định nghĩa ontology (xem "Chưa quyết"), dùng chính 48,5k nhãn mạnh đã có để đo, không tốn quota.
- **Kiểm chất lượng do trợ lý tự đọc**, không gọi model nào: lấy mẫu nhãn Gemma, đọc review / transcript gốc, báo cáo cái nào sai. Không tự ghi nhãn người vào `judge_labels.jsonl` (quy tắc cũ vẫn giữ).
- Chuỗi đang chạy: `logs/quality_pass.py` → `logs/quality_pass.log`, một bước `corpus build --city dalat --skip "judge dedup" "judge status"`, xong khi có `QUALITY_PASS_DONE`.

## Judge (2026-10-06)

Mô tả hành vi: `docs/CORPUS.md` §6 (đoạn "Engine Gemma"). Code: `src/corpus/judge/audit.py`, prompt `OBS_AUDIT_GEMMA` trong `src/corpus/llm/tasks.py`. Commit `ad00fd5`, `00fcda8`.

- **Đang bật:** `.env` `JUDGE_ENGINE=gemma`. Audit chạy trên Gemma UIT (miễn phí, cần mạng UIT/VPN), 8 nhận định/call, 1 vòng, không đọc lần hai. Sol = `cx/gpt-6.1-sol` (`JUDGE_MODEL`, `JUDGE_STRONG_MODEL=cx/gpt-6-astra,cx/gpt-6.1-sol`).
- **Sol đọc lại MỌI nhãn Gemma không phải `correct`** (commit `6627dd5`). Trước đó `select` chỉ lấy feature risky + stratum fail + mẫu, nên ở stratum đã vượt gate thì wrong/unsure của Gemma không ai đọc lại và claim bị bỏ chỉ dựa vào lời Gemma — đúng chỗ Gemma bỏ oan nhiều nhất (nó gọi ~30% claim đúng là wrong; với prior của stratum đã vượt gate thì phần lớn "wrong" ở đó là claim đúng). Nó còn khiến "nhìn vào" tệ hơn "không nhìn", vì claim không ai chấm trong stratum vượt gate thì được giữ. Nay `select(..., must=…)` và `run` nạp `must` bằng `pending_gemma()` khi không chạy engine Gemma. Đo trên dalat: 17.446 claim loại này, tập chọn 3.875 → 17.258.
- **Lượt Gemma 2026-10-06 06:21 (32.126 claim, 1 vòng):** correct 15.414, wrong 11.705, unsure 4.975, ảnh-correct giữ làm unsure 3.353, 4 call lỗi schema (~32 claim để lượt sau). Build đầy đủ xong 06:22:50; serving: VERIFIED 16.375, UNCERTAIN 10.655, OUTDATED 2.271, nơi trải nghiệm 772.
- **Chuỗi sol đang chạy:** `logs/sol_finish.py` (audit 8.832 claim / 957 call, bắt đầu 06:23 — chạy bằng code *trước* bản sửa `must`) → dedup → status → build. Nối sau: `logs/sol_pass2.log` chờ `SOL_FINISH_DONE` rồi chạy `judge audit` lần hai (lúc này có luật `must`, bỏ qua claim đã có nhãn nên không tốn trùng) + build lại. Xong khi có `SOL_PASS2_DONE`.
- **Gemma chỉ thêm, không thay:** Gemma chỉ chấm claim chưa có nhãn; nhãn người / sol / astra có trước không bao giờ bị chấm lại hay bị che (`audit.current(local=True)`, `review.labels.stand_in`). Nhãn sol sau này thì thay nhãn Gemma.
- **Ưu tiên precision** (người dùng): thiếu dữ liệu thì crawl bù, sai thì ảnh hưởng thẳng người dùng. Gemma `wrong` / `unsure` → bỏ nhận định ngay. Gemma `correct` trên ảnh → ghi `unsure` lượt 1 (giữ như chưa chấm, vì ảnh Gemma lọt sai 35%).
- **Precision Gemma đo trên nhãn sol/astra/sonnet (2026-10-06), tính cho cả corpus:** 1 claim = **0,918** (cân theo số claim mỗi stratum, 292,6k claim); 1 nguồn (review / video / ảnh, 2,31 claim/nguồn) không có claim sai nào = **0,838**. Trên riêng tập đã chấm thì thấp hơn (chữ 0,763 = 25.129/32.942; ảnh 0,677 = 4.736/6.999) vì audit cố ý chọn phần yếu nhất: feature risky + stratum fail; stratum pass chỉ lấy mẫu.
- **Stratum kéo precision xuống** (precision extractor, số claim): `setting=both` 0,24 · `steep_or_stairs=present` 0,39 (2,1k) · `live_music=present` 0,45 · `long_walk=present` 0,51 · `outdoor_seating=present` 0,60 · `local_specialty_food=present` 0,69 (3,2k). Tổng claim thuộc stratum fail = 16,6k, phải kiểm từng cái; risky = 17,7k (theo luật). Việc siết `claims` + ví dụ phản trong ontology cho ~10 feature này **chưa làm** — xem "Chưa quyết".
- **Kết quả lượt Gemma đầu** (2.473 nhận định, 7 phút, 310 call): correct 372, wrong 930, unsure 242, ảnh-correct-chờ-sol 929.
- **Cấu hình Gemma đang chạy là cấu hình tốt nhất đã đo** (2026-10-06): prompt `DOUBT` + cửa sổ 500 ký tự + item gọn = biến thể `doubtlean8` của `logs/judge_exp/gemma_eval.py`; `render(claim=True)` trong `audit.py` đã đúng dạng item gọn đó. Đo: lọt claim sai 11% (dev) / 14% (test), bỏ oan claim đúng 32% / 30%, precision phần đứng 0,955 / 0,942, 298 token/claim, 6,5 s/call — rẻ và nhanh nhất trong các biến thể cùng precision. Không đổi gì. Đã cân nhắc và bỏ: `bal1` (1 claim/call, precision gold 0,977 nhưng bỏ oan 44% → đẩy việc cho sol, 725 token/claim), `QbalF16s` (Qwen, 0,963 nhưng chậm ×3).
- **Tốc độ (2026-10-06):** audit Gemma chạy `parallel=38` (commit `7734d49`), bằng `REVIEW_OBSERVE`; key cho 40 call đồng thời và Gemma chịu được mức đó. Không chạy việc gì khác trên key trong lúc audit.
- **Qwen làm engine thứ hai: bỏ.** `qwen3.8-27b` ở `/qwen/v1` **tính chung vào trần parallel của key** (người dùng đã thử; đo thêm: tổng 48 call đồng thời sinh `RateLimitError` và không thêm throughput). Chất lượng thì ngang: `QbalF16s` trên tập test held-out cho fc 14%, fd 30%, prec~ 0,947, 319 token/claim, 36,2 s/call — so với `doubtlean8` 14%/30%/0,942, 298 token/claim, 12,5 s/call. Mỗi call Qwen chậm ~2,3× trên cùng chunk. Nên không có lý do dùng Qwen: slot để cho Gemma.
- **Chất lượng đo được** (`logs/judge_exp/gemma_eval.py`, tập `gemma_eval_out/{dev,test}.json` = 1.334 nhận định có nhãn sol, chia theo feature, dev/test khác nơi): Gemma lọt 11–16% nhận định sai, bỏ nhầm ~30% nhận định đúng (sol lọt ~3%). Đã thử và loại: gom theo feature + few-shot, 1 nhận định/call, ngưỡng logprob (luôn 0/1), ghép 2–5 call, Qwen3.8-27B (cùng chất lượng, chậm ×3). Key JSON viết tắt làm Gemma điền sai trường.
- **`judge dedup` / `judge status` vẫn dùng sol** (mẫu nhỏ, cần chính xác; người dùng quyết). Build hiện bỏ hai bước này; quyết định cũ (55 status, 115 cặp) vẫn áp dụng.
- **Sol đã có quota lại (2026-10-06 04:40 UTC).** Không cần sửa `.env`: đặt `JUDGE_ENGINE=` rỗng trong môi trường của tiến trình con là đủ (`load_dotenv` không ghi đè biến đã có).
  - `judge dedup` + `judge status` bằng sol: **xong** (`logs/sol_dedup_status.log`). dedup 115 cặp đều cached, không có cặp mới; status 53 nơi bị báo → mới 1 closed, 12 open, 1 unclear (39 cached).
  - Chuỗi còn lại đang chờ sẵn: `logs/sol_finish.py` (log `logs/sol_finish.log`, pid ghi trong log). Nó chờ `BUILD_GEMMA_DONE` trong `logs/build_gemma.log` rồi chạy `judge audit` (sol đọc lại mọi nhãn Gemma không phải `correct`, gồm ảnh, rồi đọc lần hai các `unsure`) → `judge dedup` → `judge status` → `build` đầy đủ (không `--skip`). Một bước lỗi thì dừng chuỗi, log ghi `FAILED <bước>`. Xong khi có `SOL_FINISH_DONE`.
- **Kiểm nhanh:** `tail logs/judge_gemma.log`; đếm nhãn theo model: `python -c "import json,collections;print(collections.Counter((json.loads(l)['by'],json.loads(l)['label']) for l in open('data/review/judge_labels.jsonl',encoding='utf-8')))"`.

## Đã thử và bỏ

- **`gmaps visit` (thời gian tham quan từ Maps):** Maps không in "Mọi người thường dành … ở đây" cho các nơi Đà Lạt (thử 30 nơi, 0 dòng; kiểm tay ZooDoo, spa, vườn: chỉ có biểu đồ giờ đông). Không chạy phase này. Thời gian tham quan vẫn từ review hoặc giá trị mặc định.
- **Tab "Vé" trên Maps:** dữ liệu `tickets` đã có trong `place.json` nhưng chỉ 22/1.792 nơi có khung giá. Không thêm phase mới.

## Gotchas

- Maps chặn ở ~12 tab (captcha) khi chạy ngầm; headed thì người giải. RAM: ~250 MB/tab, GPU process ~1 GB; trên 12 tab máy hết RAM.
- Sh chạy từ PowerShell `Start-Process` chỉ có `python` trong PATH; không có `grep`/`sleep`.
- Một số `tiktok place_crawl` và `scripts/tiktok_place_loop.sh` là của session khác, không đụng.

## Chưa quyết / để người dùng

- **Siết ontology cho ~10 feature precision thấp** (danh sách ở mục "Judge"): thêm `claims` từng value + ví dụ phản, lấy ví dụ từ 11k nhãn `wrong` của sol (có `note`). Các feature đã siết (`weather_exposed`, `booking_needed`, `long_walk`, `steep_or_stairs`) đều có `claims`; các feature yếu còn lại chỉ có hint một dòng. Đổi ontology thì mọi nơi phải observe lại (~72 phút gmaps + tiktok + ảnh, Gemma miễn phí); nhãn cũ không mất vì `label_key` gồm quote.
- **Hai việc đi kèm nếu làm phần trên:**
  - Gate của `judge.verdict` đang so Wilson lower với `GATE_LOWER=0.8` trên nhãn bất kể ai chấm. Nhãn Gemma lệch xuống (bỏ oan 30%): stratum thật 0,85 đo ra chỉ 0,617 → vẫn `fail` → vẫn kiểm toàn bộ. Muốn stratum vượt gate bằng nhãn Gemma thì phải hiệu chỉnh ngưỡng theo (fd, fc) đã đo, tách riêng cho chữ và ảnh.
  - `risky()` coi `span_check` là risky → audit toàn bộ. Nếu bật lượt đọc thứ hai (`REVIEW_VERIFY`) cho các feature yếu thì phải tách cờ (vd `second_read` riêng, `risky` chỉ theo `group` + cờ `audit: full`), không thì khối lượng audit tăng thay vì giảm.

- Các file đã sửa chưa commit: `scripts/free_tiktok_clips.py`, `src/corpus/__main__.py`, `src/corpus/crawl/common/throttle.py` (`grow_after` 5 → 2), `src/corpus/crawl/tiktok/{comments_crawl,place_crawl}.py`, `src/corpus/observe/tiktok/extract.py`. Không phải của phiên này; giữ nguyên tới khi người dùng quyết.
- Đẩy lên remote: chưa push, phải hỏi người dùng.

## Phiên này (2026-10-06 ~14:35 giờ VN) — đang làm gì, phiên sau tiếp thế nào

**Quyết định đã chốt với người dùng**
1. **Gemma là engine duy nhất của corpus**; sol ra khỏi dây chuyền, cả chấm lẫn kiểm (mục "Vai trò hai model"). Kiểm chất lượng do trợ lý tự đọc nguồn, không gọi model, không ghi nhãn người.
2. **Không extract lại cả thành phố** cho prompt/ontology mới. Cờ `OBSERVE_KEEP_STALE=1` (commit `1e89b95`): prompt hay `ontology_version` đổi thì một nơi **không** bị observe lại; chỉ nơi có nguồn mới. Luật mới vì vậy chỉ áp cho dữ liệu mới crawl. Mỗi file observations vẫn ghi `prompt_hash` + `ontology_version` của nó.
3. Audit Gemma chạy `parallel=38`, các task ảnh/video `parallel=24` (commit `7734d49`, `adf3200`).

**Vì sao không extract lại cả bộ** — đo trên 63 nơi đã chạy lại bằng ontology v9, đối chiếu 48,5k nhãn mạnh, tính ở mức (nơi, feature, value): claim sai bị bỏ 34% so với 21% ở feature không siết; claim đúng giữ 80% so với 88%. Precision trong mẫu 59% → 63%, nhóm đối chứng cũng tự tăng 72% → 75%. Tức **siết định nghĩa gần như không hơn mức nhiễu của việc extract lại**, vì phần lớn claim sai là "nguồn nói về quán khác" và "đọc sai ảnh", không phải lỗi định nghĩa. Riêng `setting` bị siết quá tay: chỉ 15/63 nơi còn claim `setting` → đã nới lại.

**Đã sửa, chờ dữ liệu mới để phát huy** (ontology version 10, commit `3644234`, `11a4d2b`, `736b9c6`)
- 15 feature có `claims` từng value + câu "không phải", đào từ chính quote nhãn mạnh gán `wrong`: `scenic_view`, `flower_garden`, `live_music`, `local_specialty_food`, `setting`, `outdoor_seating`, `steep_or_stairs`, `long_walk`, `booking_needed`, `condition_change`, `noise`, `crowd`, `toilet`, `laptop_friendly`, `visit_duration`.
- `REVIEW_OBSERVE`: luật nhận dạng nơi — mô tả hay so sánh với quán khác, chi nhánh khác, khách sạn, "khu này", "ngoài kia", "trên đường tới" đều không cho observation.
- `PHOTO_OBSERVE`: thứ được khai phải là chủ thể của ảnh; sân có mái không phải ngoài trời, ảnh mặt tiền không phải trong nhà, món ăn trên bàn không nói gì về chỗ ngồi.
- 64 nơi từng extract bằng v9 đã bị xóa file observations để dựng lại bằng luật đã sửa (đang chạy trong build hiện tại).

**Phiên sau làm tiếp**
1. Chờ `QUALITY_PASS_DONE` trong `logs/quality_pass.log`. Nếu có dòng `FAILED <bước>` thì đọc bước đó, sửa, chạy lại `python -u logs/quality_pass.py > logs/quality_pass.log 2>&1`.
2. Khi crawl `extremes` xong (hoặc người dùng dừng): chạy lại đúng build đó một lần nữa cho nơi có review mới. **Không chạy hai build hay hai audit cùng lúc**; cũng không chạy việc khác trên key UIT trong lúc build (key cho 40 call đồng thời, build đã dùng 38).
3. Đo và báo: `serving` so mốc VERIFIED 16.375 · UNCERTAIN 10.655 · OUTDATED 2.271 · 772 nơi trải nghiệm; `python -m decision evaluate` so filled_rate 0,767; và tự đọc ~40 nhãn Gemma `correct` mới đối chiếu review gốc.
4. Đáng làm tiếp nếu muốn chất lượng cao hơn: đo riêng xem luật nhận dạng nơi + luật chủ thể ảnh có hạ tỉ lệ claim sai trên **dữ liệu mới** không (so cùng cách ở trên). Nếu có thì mới cân nhắc extract lại cả bộ, lúc đó tắt `OBSERVE_KEEP_STALE`.
5. Việc còn treo: `judge dedup` / `judge status` cho nơi mới (cần sol — hỏi người dùng trước), 43 website official lỗi, 7 trip chưa đủ, và hiệu chỉnh gate cho nhãn Gemma + tách cờ `risky`/`second_read` (mục "Chưa quyết").

**Script của phiên này** (đều trong `logs/`, không vào git)
| File | Việc |
|---|---|
| `quality_pass.py` | build hiện tại (một bước, Gemma, keep-stale) |
| `qwen_probe.py` | đo throughput một endpoint UIT: `[qwen|gemma] <giây> <concurrency...>`, không ghi nhãn |
| `sol_finish.py`, `quota_switch.py` | chuỗi sol và watchdog hết quota — **đã bỏ** theo quyết định 1, giữ lại để tham khảo |

### Cập nhật 2026-10-06 ~18:30 giờ VN — build xong, hai sửa đổi ở tầng aggregate

- Build `quality_pass` **xong** 10:57 UTC (mọi bước `ok`). Lượt audit Gemma: correct 2.933, wrong 4.054, unsure 3.229, ảnh-correct 2.157, 4 call lỗi.
- **Sửa cổng precision** (commit `1154e8a`): `labels.stats()` đo bằng nhãn chính xác (người, sol, astra) khi đã đủ `GATE_MIN_N` = 30, chỉ dùng nhãn Gemma khi chưa đủ; mỗi dòng có `measured_by`. Trước đó trộn nhãn Gemma (bỏ oan ~30%) làm 12 cặp feature/value, 84,6k claim rớt cổng dù nhãn chính xác cho đạt (vd. `food_quality=good` 0,95 → 0,83). VERIFIED 14.796 → 19.765. Tự đọc 36 claim mới VERIFIED: 34 đúng theo định nghĩa.
- **Luật effort theo im lặng** (commit `0744c85`, người dùng chốt): `steep_or_stairs`, `long_walk`, `rough_road_access` — không ai nhắc ở review / video / ảnh → phục vụ `absent` (`inferred: "silence"`); ≥1 người nhắc `present` mà Judge không chấm `wrong` → `present` (`inferred: "mentioned"`); vừa có người nói có vừa có người nói không → giữ mâu thuẫn. Đã đo: ở nơi có thật chỉ 1,5–3,6% người viết nhắc tới, nên im lặng là bằng chứng yếu (nơi 63 người viết vẫn ~39% khả năng có dốc); người dùng chấp nhận và giao việc sửa sai cho feedback. `feature_review` `report` vẫn giữ lại giá trị suy ra, `disable` vẫn xóa.
- Sau hai sửa: VERIFIED 23.004 · UNCERTAIN 6.289 · OUTDATED 2.606; `decision evaluate` filled_rate **0,967** (từ 0,767), còn 1 trip chưa đủ (`group_food`), 0 violation, 0 unknown trong danh sách chính. Sáu trip vừa đủ chỗ là nhờ giả định im lặng = không có.
- **Vòng báo cáo của người dùng → corpus: backend xong** (commit `3280b6e`). `POST /api/reports {place_id, text, reporter}` lưu `data/review/reports.jsonl`; bước build `reports observe` đọc từng báo cáo bằng prompt `REVIEW_OBSERVE`; một (nơi, feature, value) được **8 người khác nhau** báo (`REPORTS_MIN`) thì thành observation `traveller_report`, nguồn authoritative trong aggregate: không ai cãi → phục vụ; review nói ngược → UNCERTAIN, giữ cả hai phía. `x = 8` đo trên nguồn gần nhất (review độc lập nói cùng ý: 1 người 70% đúng, 5 người 81%, 8+ người 89%; cận dưới Wilson chạm 0,80 ở 8). Đo lại khi có báo cáo thật. **Còn thiếu: UI** (nút "Báo thông tin sai" + ô nhập chữ trên thẻ nơi, gửi `reporter` là id ẩn danh trình duyệt giữ) — việc của phiên web.
- **Data zip cho team** 2026-10-06 18:58 giờ VN: `tripguardian-data-20261006.zip` (3,71 GB, 65.796 file, có ảnh, kiểm CRC ok), gồm serving + snapshot web sinh lại hôm nay. Chưa gồm 1.369 claim chưa audit và ~180 nơi có review `extremes` mới (đợi build Gemma kế tiếp).
- Sửa kèm hai test cũ bị ontology làm hỏng (version ghim 7, ví dụ `claim_text`). Toàn bộ 1.102 test pass.
