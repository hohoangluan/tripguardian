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
- **Build đầy đủ đang chạy** (bắt đầu 10:31): `logs/build_gemma.sh` → `logs/build_gemma.log`, xong khi có `BUILD_GEMMA_DONE`. Ước 45–90 phút (gmaps observe ~25 nơi/phút). Lỗi `RuntimeError: Event loop is closed` trong log là cảnh báo dọn client, không làm build dừng; bước hỏng thật hiện `build dalat: <bước> failed`.

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

## Judge (2026-10-06)

Mô tả hành vi: `docs/CORPUS.md` §6 (đoạn "Engine Gemma"). Code: `src/corpus/judge/audit.py`, prompt `OBS_AUDIT_GEMMA` trong `src/corpus/llm/tasks.py`. Commit `ad00fd5`, `00fcda8`.

- **Đang bật:** `.env` `JUDGE_ENGINE=gemma`. Audit chạy trên Gemma UIT (miễn phí, cần mạng UIT/VPN), 8 nhận định/call, 1 vòng, không đọc lần hai. Sol = `cx/gpt-6.1-sol` (`JUDGE_MODEL`, `JUDGE_STRONG_MODEL=cx/gpt-6-astra,cx/gpt-6.1-sol`).
- **Gemma chỉ thêm, không thay:** Gemma chỉ chấm claim chưa có nhãn; nhãn người / sol / astra có trước không bao giờ bị chấm lại hay bị che (`audit.current(local=True)`, `review.labels.stand_in`). Nhãn sol sau này thì thay nhãn Gemma.
- **Ưu tiên precision** (người dùng): thiếu dữ liệu thì crawl bù, sai thì ảnh hưởng thẳng người dùng. Gemma `wrong` / `unsure` → bỏ nhận định ngay. Gemma `correct` trên ảnh → ghi `unsure` lượt 1 (giữ như chưa chấm, vì ảnh Gemma lọt sai 35%).
- **Kết quả lượt Gemma đầu** (2.473 nhận định, 7 phút, 310 call): correct 372, wrong 930, unsure 242, ảnh-correct-chờ-sol 929.
- **Chất lượng đo được** (`logs/judge_exp/gemma_eval.py`, tập `gemma_eval_out/{dev,test}.json` = 1.334 nhận định có nhãn sol, chia theo feature, dev/test khác nơi): Gemma lọt 11–16% nhận định sai, bỏ nhầm ~30% nhận định đúng (sol lọt ~3%). Đã thử và loại: gom theo feature + few-shot, 1 nhận định/call, ngưỡng logprob (luôn 0/1), ghép 2–5 call, Qwen3.8-27B (cùng chất lượng, chậm ×3). Key JSON viết tắt làm Gemma điền sai trường.
- **`judge dedup` / `judge status` vẫn dùng sol** (mẫu nhỏ, cần chính xác; người dùng quyết). Build hiện bỏ hai bước này; quyết định cũ (55 status, 115 cặp) vẫn áp dụng.
- **Khi sol có quota:** (1) để trống `JUDGE_ENGINE=` trong `.env`; (2) chạy `python -m corpus judge audit --city dalat` (nền: sửa `logs/judge_gemma.sh`, log ra file) — sol tự đọc lại mọi nhãn Gemma không phải `correct` (gồm ảnh), rồi đọc lần hai các `unsure`; (3) `python -m corpus judge dedup --city dalat` và `judge status`; (4) build lại đầy đủ (không `--skip`).
- **Kiểm nhanh:** `tail logs/judge_gemma.log`; đếm nhãn theo model: `python -c "import json,collections;print(collections.Counter((json.loads(l)['by'],json.loads(l)['label']) for l in open('data/review/judge_labels.jsonl',encoding='utf-8')))"`.

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
