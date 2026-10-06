# Bàn giao corpus (Maps, dalat) — 2026-10-06

File làm việc tạm (RULE §0.1): xong các bước dưới thì gộp phần còn giá trị vào `docs/CORPUS.md` và xóa file này.
Mô tả hành vi code: `docs/CORPUS.md`. Ở đây chỉ có trạng thái và việc còn lại.

## Trạng thái hiện tại

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
- **Còn thiếu: vòng feedback người dùng → corpus.** Feedback trong app (`far`, `crowded`, `pricey`, `visited`) chỉ chỉnh hồ sơ phiên, không ghi `feature_review`. Đã trình thiết kế cho người dùng, chờ duyệt.
- Sửa kèm hai test cũ bị ontology làm hỏng (version ghim 7, ví dụ `claim_text`). Toàn bộ 1.102 test pass.
