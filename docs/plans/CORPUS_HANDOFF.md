# Bàn giao corpus (Maps, dalat) — 2026-10-06

File làm việc tạm (RULE §0.1): xong các bước dưới thì gộp phần còn giá trị vào `docs/CORPUS.md` và xóa file này.
Mô tả hành vi code: `docs/CORPUS.md`. Ở đây chỉ có trạng thái và việc còn lại.

## Trạng thái hiện tại

- **Đang chạy:** crawl Maps (`logs/gmaps_runner.py`, log `logs/gmaps_runner_9.log`), phase `extremes`, headed, 2 tab. Mạng đã ổn (2026-10-06 10:30 giờ VN, `google.com/maps` trả 200 trong ~2,6 s).
- **Đang chạy song song (phiên khác):** `build_gemma.sh` (`corpus build --city dalat --skip "judge dedup" "judge status"`, log `logs/build_gemma.log`, bắt đầu 10:30 giờ VN). Build này chạy trước khi Maps xong, nên phải build lại sau khi crawl xong.
- **Còn lại (ước lượng 2026-10-06):**
  - `extremes` (review 1–2★ và 5★): 345 file, còn ~1.123 nơi (đã xóa 2 file không đủ đánh dấu hoàn tất, xem bước 3).
  - `photos`: còn ~30 nơi.
  - `keywords`: xong. 1.150/1.150 nơi cần từ khóa đã đủ mọi từ của nhóm; 0 nơi thiếu (bước 1).
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
| 1 | Sol 6.1 chấm lại nhãn Gemma không phải `correct` (~20k, gồm ~4.300 ảnh) | Gemma lọt 11–16% claim sai (ảnh 35%), loại nhầm ~30% (vd. đặt chỗ) | Quota Codex; mục "Judge" → "Khi sol có quota" |
| 2 | Người kiểm có lấy mẫu chính Judge: ~30 claim mỗi giá trị rủi ro (dốc/bậc, đi bộ xa, thời tiết, đặt chỗ, người già / trẻ em / xe lăn) | Gold hiện chỉ 156 claim; con số "chính xác X%" phải từ người | Người dùng, `/admin/labels`; agent không tự ghi nhãn người |
| 3 | `judge dedup` + `judge status` cho nơi / báo cáo đóng cửa mới | Nơi đóng / trùng làm mất tin ngay | Quota sol |
| 4 | Crawl Maps phần thiếu (extremes ~1.120 nơi, ảnh ~32, kiểm keywords) | Thiếu bằng chứng effort cho bộ lọc cứng | Mạng ổn, headed (bước 1–2 ở trên) |
| 5 | 7 trip chưa đủ: xem thiếu feature nào (người già + view, xe lăn + cafe, nhóm ăn) | filled_rate 0,767 | Sau #1, #4 |
| 6 | 43 website official lỗi | Giá vé / giờ chuẩn nhất | `python -m corpus official pages` |
| 7 | Làm mới định kỳ (crawl → build) | Đóng cửa, đổi giá | Sau #1–#4 |

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
