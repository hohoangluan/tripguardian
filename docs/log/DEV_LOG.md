# Dev log

Nhật ký thay đổi của **những gì đang có trong code**. Không phải nhật ký thiết kế.

**Lưu giữ:** mỗi mục chỉ giữ **Hiện tại** + **Trước đó**. Khi sửa mới, chuyển Hiện tại → Trước đó và **xóa** bản Trước đó cũ.

**Cách viết:** tiếng Việt, ngắn, chính xác, khớp code và luồng chạy thật. Trước khi lưu, đọc lại code (hoặc chạy thử) và bỏ mọi điều không đúng.

## Mẫu (chép cho mỗi tính năng / module)

```markdown
## <id> — <tên>

- file:
- cách kiểm chứng:

### Hiện tại (<ngày>)
- hành vi:

### Trước đó (<ngày>)
- hành vi:
```

Tính năng mới: chỉ điền Hiện tại; Trước đó = _không có_.  
Sửa sau này: chuyển Hiện tại sang Trước đó, viết Hiện tại mới, bỏ bản Trước đó cũ hơn.

---

## Các mục

## corpus-core — Nền tảng corpus (Phase 1, một phần)

- file: `config/cities.yaml` (còn lại; `src/corpus/core/`, `src/corpus/adapters/` đã xóa)
- cách kiểm chứng: _không còn test_

### Hiện tại (2026-09-29)
- hành vi: đã xóa `core/` và `adapters/` (cùng test, `docker-compose.yml`) theo yêu cầu: làm từ dữ liệu thô trước, thêm lớp khi dữ liệu cho thấy cần.

### Trước đó (2026-09-28)
- hành vi:
  - `core.types`: data model của spec bằng pydantic (frozen, cấm field lạ). `TikTokVideo.video_ref` trỏ tới file video đã tải (video được giữ lại để xem nội dung, không xóa sau ASR). Invariant nằm ngay trong type: observation bắt buộc có span, span text có `quote` khớp độ dài offset, fact có xung đột phải giữ `value = None` và ≥ 2 giá trị, derived cần ≥ 1 observation, relation cần span.
  - `core.ontology`: feature v0 (21 feature) + `FACT_KEYS`; feature `verify: always` khai báo `caution_values`.
  - `core.gate`: trả danh sách lý do trượt cho span (quote nguyên văn tại offset, timestamp trong segment), observation (feature / fact_key / giá trị), match (T, M, `T_min` cho Judge), derived (chỉ processor `aggregate`, observation id tồn tại).
  - `core.loop.bounded_loop`: vòng lặp có số bước tối đa, ngân sách, điều kiện dừng; model trả `None` là dừng.
  - `adapters.db`: Postgres qua pool async; bảng `record` (JSONB theo kind), `provider_place` tách riêng (`save` từ chối `ProviderPlace`), `ledger` (chạy lại khi thất bại hoặc khóa input/processor/prompt/ontology đổi), `llm_cache`.
  - `adapters.llm.Llm`: gọi model theo vai trò qua API tương thích OpenAI, output `json_schema` validate bằng pydantic, cache theo hash toàn bộ request, retry backoff lỗi mạng, sai schema thử lại 1 lần kèm lỗi rồi `InvalidOutput`.
  - Chưa có: adapter ASR, Google, TikTok, media, web; các bước discover → refresh; `api`.

## corpus-review — Trang review mục cần người

- file: `src/corpus/review/` (`decisions.py`, `queue.py`, `server.py`, `page.html`), `tests/review/`
- cách kiểm chứng: `python -m pytest -q tests/review`; `python -m corpus review` rồi mở `http://127.0.0.1:8765`

### Hiện tại (2026-10-02, chiều)
- hành vi: nhãn khóa theo nội dung (`key` = review / video id + feature + value + quote chuẩn hóa), không theo id observation: chạy lại observe không làm mất nhãn, nhãn của khẳng định mà lần chạy mới không còn tạo thì không vào thống kê; `migrate()` ghi key cho bản ghi cũ. Observation của mọi version ontology được tính khi giá trị còn trong ontology. Màn `Gán nhãn` hiện thêm bằng chứng: nghĩa của nhãn (claim + hint), sao / ngày / tác giả / mục chấm điểm Maps của review, các observation khác cùng nơi về feature đó (đồng ý / ngược lại), category / giá / thuộc tính / link Maps. Nguồn TikTok (`tiktok_segment` / `tiktok_caption` / `tiktok_frame`): transcript quanh quote, caption, link video, khung hình (`GET /api/labels/frame`). `stats` có `by_source`. Index cache theo từng file (lúc observe chạy lại không quét lại 1.437 file mỗi request). Kiểm chứng: 14 test review, `npm run build`, API thật.

### Trước đó (2026-10-02)
- hành vi: như bản trước, thêm: (1) `labels.py` + `GET /api/labels/next`, `POST /api/labels`, `GET /api/labels/stats`: lấy mẫu observation từ review chưa gán nhãn (giá trị ít nhãn nhất trước, bỏ observation do rule và file ontology cũ), nhãn `correct | wrong | unsure` ghi nối vào `data/review/labels.jsonl`, thống kê độ chính xác theo (feature, value) với cận dưới Wilson và ngưỡng (`GATE_MIN_N = 30`, `GATE_LOWER = 0.8`); (2) loại quyết định `feature_review` (accept / disable / report / refresh / undo, id `<fid>#<feature>`) và `GET /api/decisions?kind=`; (3) Admin Web (`web/`): màn `Gán nhãn` (`/admin/labels`, phím c / w / u / s), `decisions.ts` ghi quyết định về backend và đọc lại khi mở trang, Vite proxy `/api` tới `127.0.0.1:8765`. `aggregate` chưa đọc nhãn và quyết định. Kế hoạch tiếp: `docs/plans/OPEN_TASKS.md`. Kiểm chứng: 12 test review, chạy thật với Chrome không lỗi console, mẫu lấy từ 249.605 bằng chứng (lần đọc đầu ~4 giây).

## corpus-crawl — Crawl dữ liệu thô TikTok + Google Maps

- file: `src/corpus/crawl/` (`files`, `browser`, `tiktok`, `gmaps`), `src/corpus/__main__.py`, `config/queries.yaml`, `tests/crawl/`, `tests/fixtures/` (`capture.py` lưu lại fixture thật, đã che tài khoản)
- cách kiểm chứng: `python -m pytest -q`; smoke thật `python -m corpus {tiktok|gmaps} --city dalat --headed` với config thu nhỏ

### Hiện tại (2026-10-01)
- hành vi:
  - Lệnh, phase, layout file: `docs/P1_CORPUS.md` §1 Discover (Dữ liệu thô). `python -m corpus login <source>` để đăng nhập lại.
  - Rời trang theo tín hiệu kết thúc (spec §1): TikTok `comments_complete` (mọi danh sách comment / reply trả `has_more=0`, không còn request chờ; body rỗng = bị chặn, dừng ngay); Maps review dừng khi ô loader cuối khung bị làm rỗng (`reviews_complete`); Maps search dừng ở dòng "Bạn đã xem hết danh sách này", ô không tới được dòng đó (`end=false`) thì chia nhỏ như ô đầy.
  - Trang TikTok tự tải lại ngay sau khi mở: item JSON đọc bằng vòng chờ (tối đa 20 s), lỗi "Execution context was destroyed" coi là chưa xong.
  - Maps: sắp xếp review "Mới nhất" được kiểm bằng nhãn nút (text dạng tổ hợp, so sánh sau `normalize('NFC')`), không áp dụng được thì lỗi + thử lại; cuộn bằng cách đưa mục cuối vào tầm nhìn (`scrollBy` / wheel hay không tải thêm); review layout lưu trú ("4/5", "… trước trên Google") đọc được; bỏ chữ icon-font khỏi `address` / `hours`; trang có link đăng nhập → `LoginRequired` (phiên hết hạn mà cookie `SID` vẫn còn).
  - `config/queries.yaml` TikTok `pause_s: [15, 30]`.
  - TikTok `filter` (sau `list`, trước `crawl`): Extractor đọc caption + hashtag (không đọc query / tác giả: model lấy query làm bằng chứng và cho `#comga20k` là liên quan), trả `yes | no | unsure`; `crawl` chỉ mở `yes` / `unsure`. Prompt và thiết lập model: `src/corpus/llm/` (`Role`, `Task`, `prompt_hash`); `gmaps qc` dùng `PLACE_QC` ở cùng chỗ. Lần chạy 2026-09-29 trên 273 video: 244 yes, 12 unsure (chủ yếu thời tiết), 17 no (couple / tâm trạng / thất nghiệp / tai nạn); prompt khắt khe hơn trước đó loại nhầm review quán, săn mây, vlog chuyến đi (35 no).
  - Đo 2026-09-29:
    - Maps (đăng nhập): 200 review / place trong ~22 s, 27/27 trong 9 s, đúng thứ tự mới nhất. Code cũ chỉ lấy 20–50 review, có place sai thứ tự; search cũ dừng ở vòng cuộn thứ 20 (~92 kết quả) nên ô đầy 120 không được chia. Đăng xuất: ô 116 kết quả chỉ còn 40 mà vẫn hiện dòng hết danh sách.
    - TikTok: ~15 video (nhịp cũ, không nghỉ) thì API comment trả body rỗng; hết chặn sau ~21 phút. Comment lấy được 81% `commentCount` (2.487 / 3.081 trên 32 video); phần thiếu là comment / reply TikTok ẩn (danh sách kết thúc `has_more=0` mà ít dòng hơn).
  - Phase 1 (2026-09-29): Maps là nguồn địa điểm; TikTok tạm ngoài phạm vi (code giữ, dữ liệu đã xóa theo yêu cầu). `search` không cần đăng nhập, mỗi lần thử một ô chạy trong context mới không cookie (Google giới hạn theo phiên); song song nhiều tab (`search_tabs`, AIMD; ô bị cắt ngang = bị chặn mềm → giảm tab, nghỉ, tìm lại; mỗi lần thử hỏng một mức tab thì lần thử sau ở mức đó cần gấp đôi chuỗi sạch, tối đa ×32), quét tới zoom 14 (chỉ chia ô khi số chỗ nằm trong chính ô đủ `full_at`: Maps lấp danh sách ngắn bằng chỗ ở thành phố khác, ~43% kết quả thô nằm ngoài area; `list` bỏ chúng), chạy xong từng category rồi mới sang category kế, đọc thêm `category`, `rating`, `reviews` từ thẻ kết quả (bỏ hậu tố "Đường liên kết đã truy cập" khỏi tên); `list` bỏ chỗ ở, xếp theo trung bình Bayes, giữ `top_per_category` = 100 mỗi category (spec §1, Phase 1). Config: 38 category du lịch (gộp loại trùng: nhà hàng → quán ăn, lẩu + nướng → quán lẩu nướng, bỏ làng hoa, cánh đồng hoa, điểm check in, thiền viện, đồi chè, đèo, quán kem, chợ đêm, cửa hàng lưu niệm, vườn cà phê, dinh thự, phòng tranh, công ty du lịch (đại lý / văn phòng, không phải nơi để đi)), bỏ khách sạn / homestay / resort / nhà nghỉ / villa / khu du lịch. Dữ liệu: đã xóa search định dạng cũ, `data/tiktok`, `data/review`; phase 1 chỉ lấy dữ liệu thô (`gmaps search`); lọc (`filter`, Gemma) và `list` để phase sau.
  - Maps `filter` (sau `search`, trước `list`; spec §1): Extractor (`PLACE_FILTER`) đọc tên + category Maps của mỗi FID trong `area`, không chỗ ở; `list` chỉ xếp `yes` / `unsure` (+ giữ / bỏ của người, loại review `place_filter`). Lần chạy 2026-09-29 trên 1.022 nơi: 963 yes, 56 no (công ty, cửa hàng gia dụng / điện máy, bãi xe, nhà vệ sinh, cứu hộ xe, trạm xe buýt, tháp viễn thông), 3 unsure, 0 lỗi; `list` ra 745 nơi.
  - Maps `filter` prompt siết (2026-09-30): chỉ giữ nơi du khách đến vì chính nơi đó; `no` cho mọi chỗ ở (kể cả có cafe / nhà hàng; khu cắm trại không tính là chỗ ở), công ty tour / đại lý du lịch / phòng vé, cửa hàng thường (trang sức, quần áo, điện thoại, siêu thị…); tên nói rõ loại nơi thì tên thắng category. Thử 19 ca mẫu đúng hết; chấm lại 5.956 nơi: 5.368 yes, 520 no, 68 unsure, 0 lỗi; list 1.485 → 1.438 nơi.
  - Maps `list` (2026-09-30): lọc = `filter` (liên quan du lịch) + `min_reviews` 50 + gộp cùng tên chuẩn hóa trong `same_name_m` 1000 m; không cắt theo rating / score / top mỗi category; FID từng mang category chỗ ở ở bất kỳ lần thấy nào bị bỏ (spec §1, Phase 1). Mỗi FID lấy lần thấy nhiều review nhất (thẻ thiếu số làm mất 213 nơi, vd Thung Lũng Vàng 4.712 review). Phase mới `counts`: Maps không đăng nhập đôi khi ẩn "(124)" trên thẻ và luôn ẩn trên trang chi tiết; mở 173 nơi bằng profile đăng nhập, đủ 173 số, 44 nơi ≥ 50. Profile hết phiên mà còn cookie SID → trang "chế độ bị hạn chế", không có số: `counts` dừng `LoginRequired` thay vì ghi rỗng. `is_lodging` chuẩn hóa NFC (410 category Maps gửi dạng NFD). Category `rừng thông` → `khu rừng thông` (query cũ mở thẳng một địa điểm). Search đủ 38/38 category, không thiếu ô. Lần chạy: 5.947 ứng viên, 282 filter bỏ, 52 bản trùng gộp, 4.128 dưới 50 review / không rating → 1.485 nơi. Kiểm độc lập 2 chiều: mọi nơi trong list liên quan du lịch, ≥ 50 review, trong area, không chỗ ở, FID duy nhất khớp URL; mọi nơi đạt điều kiện đều trong list trừ 7 bản trùng đã gộp.
  - TikTok theo địa điểm (2026-09-30): phase `place_search` → `place_filter` → `place_crawl` (spec §1, Phase 2; `config/queries.yaml`: `videos_per_place` 10, `place_search_tabs` 3, `place_search_pause_s`). `place_search` song song theo `Throttle` riêng (`tiktok/place_search_throttle.json`), danh sách không kết thúc → thử lại, lần cuối ghi `errors.jsonl`. `place_filter` chỉ giữ `yes` (video thành bằng chứng cho nơi đó). `place_crawl` dùng chung `crawl.crawl_videos`. Smoke 4 nơi: 40 video → 22 yes, 8 unsure, 10 no; `no` bắt đúng tiệm khác tên gần giống (xe máy "Vũ" / "Tài" với "Vy", Karaoke "Melya" với "Luxury"); `unsure` gồm video tả đúng quán nhưng không ghi tên (bị bỏ).
  - Maps `crawl` chốt số review (2026-09-30): phiên Google hết giữa chừng (nút "Đăng nhập", cookie `SID` còn) → trang chỉ hiện ~8 review; `check_signed_in` chạy lúc tiêu đề hiện nên chưa thấy link (thanh Google render sau) → 28 place lưu 8–20 review. Nay kiểm đăng nhập lại sau khi đọc review; `too_few` (review < nửa min(`review_count`, `max_reviews_per_place`) mà chưa gặp review quá tuổi, `reviews_age_cut`) → thử lại như bị chặn, không lưu; chỉ giữ review dưới 1 năm, tối đa 200 mới nhất, không sàn (`max_reviews_per_place` 200, `max_review_age_months` 11, `min_reviews_per_place` 0; thử bỏ trần thì nơi đông khách dừng giữa danh sách dài và không lưu được gì); dữ liệu cũ đã lọc: bỏ 8.937 review quá 11 tháng ở 385 place; `run` crawl lại place đã lưu mà `too_few`. Nút "Xem thêm" (`button.w8nwRe`) có cho cả review lẫn owner reply (`expandOwnerResponse`), `EXPAND_JS` chỉ bấm nút của review (owner reply không lấy nữa: không phải bằng chứng, spec §1 Dữ liệu thô); `reviews_complete=False` (hết 15 s không có đợt mới, mạng chậm) → thử lại, không giảm tab (giảm tab ở lỗi chậm từng kẹt throttle ở 1 tab: 8 place / 30 phút), lần cuối mới lưu kèm cờ + `errors.jsonl` (như TikTok); `tabs` 10; review kết thúc " …" mà không có nút là text Maps tự cắt, không mở thêm được trong khung này.
  - TikTok ASR + kiểm tra (2026-09-30): phase `asr` → `asr_check` → `place_verify` sau `place_crawl` (spec §1, Phase 2; layout `video.json`: spec Dữ liệu thô). Thử Gemma: transcript giả lập (tên nghe nhầm, lời nhạc nền, đoạn vô nghĩa) chấm đúng hết; trên output vô nghĩa, Gemma vẫn "sửa" "mry o dayay red vui" → "mọi người đi chơi vui" dù prompt cấm → chặn bằng code (`MIN_KEPT` 0,5). 5 video thật đầu tiên: ASR giọng người dùng được, Gemma sửa đúng tên ("siêu thị cô đà lạt" → "GO! Đà Lạt"); 2 video chỉ nhạc → `no_speech`; keyframe đọc được biển hiệu / logo / chữ overlay. Một video map vào 2 spa tên gần giống, cả hai `yes` → prompt nay kèm các nơi khác cùng video (`others`), bằng chứng hợp nơi khác thì không `yes`: chấm lại còn 1 `yes`, 1 `no`. `place_filter` trên 450 place đã search: 4.400 video, 2.717 cặp `yes`.
  - ASR sai và cách sửa (2026-10-01, 608 video đã kiểm: 288 good, 79 partial, 175 no_speech, 66 unusable; segment 2.282 ok, 1.428 fixed, 433 lyrics, 275 garbled): lỗi chính là từ mượn ("mátage" → massage), tên riêng ("PiNi" → "mini" / "pin đi"), nhầm dấu ("sân bay" → săn mây), nhạc nền có lời (cả rap tiếng Anh). Ca "Quỷ Núi" (khu trong quần thể PiNi): `asr_check` ép tên place "mini" → "Quỷ Núi", `place_verify` đọc biển "Pini Dalat" thành "Pin đi" → `no`. Sửa: keyframe + `screen_text` vào `asr_check`, `guard` hoàn tác chỗ thay không giống âm, phase `asr_alt` (PhoWhisper-medium) cho segment không tin được rồi Gemma ghép ASR + ASR2, prompt `place_verify` đọc chữ màn hình đúng như hiện và `unsure` khi quan hệ khu / quần thể không rõ, review loại `place_verify`. Thử lại 5 video: "mini" → "Pini" (theo biển), Quỷ Núi `yes`, ghép ASR2 thêm "phương thức" / "quần thể" và bỏ "bin laden" PhoWhisper bịa. Trang review chưa có tab cho `place_filter` (queue có tạo mục, `page.html` thiếu nhãn).
  - Còn phải làm: review dài không bấm được "Thêm" thì giữ text bị cắt; trang chặn `/sorry` của Google chưa chờ người giải (dừng với `LoginRequired`).
  - Maps (2026-10-01): `min_reviews_per_place` 40 — 40 review mới nhất luôn giữ dù quá `max_review_age_months`; `too_few` coi place bị cắt theo tuổi mà có dưới nửa min(40, số review Maps) là thiếu, nên `gmaps crawl` crawl lại (536 place lúc đổi).

### Trước đó (2026-09-29, tối)
- hành vi:
  - Lệnh, phase, layout file: `docs/P1_CORPUS.md` §1 Discover (Dữ liệu thô). `python -m corpus login <source>` để đăng nhập lại.
  - Rời trang theo tín hiệu kết thúc (spec §1): TikTok `comments_complete` (mọi danh sách comment / reply trả `has_more=0`, không còn request chờ; body rỗng = bị chặn, dừng ngay); Maps review dừng khi ô loader cuối khung bị làm rỗng (`reviews_complete`); Maps search dừng ở dòng "Bạn đã xem hết danh sách này", ô không tới được dòng đó (`end=false`) thì chia nhỏ như ô đầy.
  - Trang TikTok tự tải lại ngay sau khi mở: item JSON đọc bằng vòng chờ (tối đa 20 s), lỗi "Execution context was destroyed" coi là chưa xong.
  - Maps: sắp xếp review "Mới nhất" được kiểm bằng nhãn nút (text dạng tổ hợp, so sánh sau `normalize('NFC')`), không áp dụng được thì lỗi + thử lại; cuộn bằng cách đưa mục cuối vào tầm nhìn (`scrollBy` / wheel hay không tải thêm); review layout lưu trú ("4/5", "… trước trên Google") đọc được; bỏ chữ icon-font khỏi `address` / `hours`; trang có link đăng nhập → `LoginRequired` (phiên hết hạn mà cookie `SID` vẫn còn).
  - `config/queries.yaml` TikTok `pause_s: [15, 30]`.
  - TikTok `filter` (sau `list`, trước `crawl`): Extractor đọc caption + hashtag (không đọc query / tác giả: model lấy query làm bằng chứng và cho `#comga20k` là liên quan), trả `yes | no | unsure`; `crawl` chỉ mở `yes` / `unsure`. Prompt và thiết lập model: `src/corpus/llm/` (`Role`, `Task`, `prompt_hash`); `gmaps qc` dùng `PLACE_QC` ở cùng chỗ. Lần chạy 2026-09-29 trên 273 video: 244 yes, 12 unsure (chủ yếu thời tiết), 17 no (couple / tâm trạng / thất nghiệp / tai nạn); prompt khắt khe hơn trước đó loại nhầm review quán, săn mây, vlog chuyến đi (35 no).
  - Đo 2026-09-29:
    - Maps (đăng nhập): 200 review / place trong ~22 s, 27/27 trong 9 s, đúng thứ tự mới nhất. Code cũ chỉ lấy 20–50 review, có place sai thứ tự; search cũ dừng ở vòng cuộn thứ 20 (~92 kết quả) nên ô đầy 120 không được chia. Đăng xuất: ô 116 kết quả chỉ còn 40 mà vẫn hiện dòng hết danh sách.
    - TikTok: ~15 video (nhịp cũ, không nghỉ) thì API comment trả body rỗng; hết chặn sau ~21 phút. Comment lấy được 81% `commentCount` (2.487 / 3.081 trên 32 video); phần thiếu là comment / reply TikTok ẩn (danh sách kết thúc `has_more=0` mà ít dòng hơn).
  - Phase 1 (2026-09-29): Maps là nguồn địa điểm; TikTok tạm ngoài phạm vi (code giữ, dữ liệu đã xóa theo yêu cầu). `search` không cần đăng nhập, mỗi lần thử một ô chạy trong context mới không cookie (Google giới hạn theo phiên); song song nhiều tab (`search_tabs`, AIMD; ô bị cắt ngang = bị chặn mềm → giảm tab, nghỉ, tìm lại; mỗi lần thử hỏng một mức tab thì lần thử sau ở mức đó cần gấp đôi chuỗi sạch, tối đa ×32), quét tới zoom 14 (chỉ chia ô khi số chỗ nằm trong chính ô đủ `full_at`: Maps lấp danh sách ngắn bằng chỗ ở thành phố khác, ~43% kết quả thô nằm ngoài area; `list` bỏ chúng), chạy xong từng category rồi mới sang category kế, đọc thêm `category`, `rating`, `reviews` từ thẻ kết quả (bỏ hậu tố "Đường liên kết đã truy cập" khỏi tên); `list` bỏ chỗ ở, xếp theo trung bình Bayes, giữ `top_per_category` = 100 mỗi category (spec §1, Phase 1). Config: 38 category du lịch (gộp loại trùng: nhà hàng → quán ăn, lẩu + nướng → quán lẩu nướng, bỏ làng hoa, cánh đồng hoa, điểm check in, thiền viện, đồi chè, đèo, quán kem, chợ đêm, cửa hàng lưu niệm, vườn cà phê, dinh thự, phòng tranh, công ty du lịch (đại lý / văn phòng, không phải nơi để đi)), bỏ khách sạn / homestay / resort / nhà nghỉ / villa / khu du lịch. Dữ liệu: đã xóa search định dạng cũ, `data/tiktok`, `data/review`; phase 1 chỉ lấy dữ liệu thô (`gmaps search`); lọc (`filter`, Gemma) và `list` để phase sau.
  - Maps `filter` (sau `search`, trước `list`; spec §1): Extractor (`PLACE_FILTER`) đọc tên + category Maps của mỗi FID trong `area`, không chỗ ở; `list` chỉ xếp `yes` / `unsure` (+ giữ / bỏ của người, loại review `place_filter`). Lần chạy 2026-09-29 trên 1.022 nơi: 963 yes, 56 no (công ty, cửa hàng gia dụng / điện máy, bãi xe, nhà vệ sinh, cứu hộ xe, trạm xe buýt, tháp viễn thông), 3 unsure, 0 lỗi; `list` ra 745 nơi.
  - Maps `filter` prompt siết (2026-09-30): chỉ giữ nơi du khách đến vì chính nơi đó; `no` cho mọi chỗ ở (kể cả có cafe / nhà hàng; khu cắm trại không tính là chỗ ở), công ty tour / đại lý du lịch / phòng vé, cửa hàng thường (trang sức, quần áo, điện thoại, siêu thị…); tên nói rõ loại nơi thì tên thắng category. Thử 19 ca mẫu đúng hết; chấm lại 5.956 nơi: 5.368 yes, 520 no, 68 unsure, 0 lỗi; list 1.485 → 1.438 nơi.
  - Maps `list` (2026-09-30): lọc = `filter` (liên quan du lịch) + `min_reviews` 50 + gộp cùng tên chuẩn hóa trong `same_name_m` 1000 m; không cắt theo rating / score / top mỗi category; FID từng mang category chỗ ở ở bất kỳ lần thấy nào bị bỏ (spec §1, Phase 1). Mỗi FID lấy lần thấy nhiều review nhất (thẻ thiếu số làm mất 213 nơi, vd Thung Lũng Vàng 4.712 review). Phase mới `counts`: Maps không đăng nhập đôi khi ẩn "(124)" trên thẻ và luôn ẩn trên trang chi tiết; mở 173 nơi bằng profile đăng nhập, đủ 173 số, 44 nơi ≥ 50. Profile hết phiên mà còn cookie SID → trang "chế độ bị hạn chế", không có số: `counts` dừng `LoginRequired` thay vì ghi rỗng. `is_lodging` chuẩn hóa NFC (410 category Maps gửi dạng NFD). Category `rừng thông` → `khu rừng thông` (query cũ mở thẳng một địa điểm). Search đủ 38/38 category, không thiếu ô. Lần chạy: 5.947 ứng viên, 282 filter bỏ, 52 bản trùng gộp, 4.128 dưới 50 review / không rating → 1.485 nơi. Kiểm độc lập 2 chiều: mọi nơi trong list liên quan du lịch, ≥ 50 review, trong area, không chỗ ở, FID duy nhất khớp URL; mọi nơi đạt điều kiện đều trong list trừ 7 bản trùng đã gộp.
  - TikTok theo địa điểm (2026-09-30): phase `place_search` → `place_filter` → `place_crawl` (spec §1, Phase 2; `config/queries.yaml`: `videos_per_place` 10, `place_search_tabs` 3, `place_search_pause_s`). `place_search` song song theo `Throttle` riêng (`tiktok/place_search_throttle.json`), danh sách không kết thúc → thử lại, lần cuối ghi `errors.jsonl`. `place_filter` chỉ giữ `yes` (video thành bằng chứng cho nơi đó). `place_crawl` dùng chung `crawl.crawl_videos`. Smoke 4 nơi: 40 video → 22 yes, 8 unsure, 10 no; `no` bắt đúng tiệm khác tên gần giống (xe máy "Vũ" / "Tài" với "Vy", Karaoke "Melya" với "Luxury"); `unsure` gồm video tả đúng quán nhưng không ghi tên (bị bỏ).
  - Maps `crawl` chốt số review (2026-09-30): phiên Google hết giữa chừng (nút "Đăng nhập", cookie `SID` còn) → trang chỉ hiện ~8 review; `check_signed_in` chạy lúc tiêu đề hiện nên chưa thấy link (thanh Google render sau) → 28 place lưu 8–20 review. Nay kiểm đăng nhập lại sau khi đọc review; `too_few` (review < nửa min(`review_count`, `max_reviews_per_place`) mà chưa gặp review quá tuổi, `reviews_age_cut`) → thử lại như bị chặn, không lưu; chỉ giữ review dưới 1 năm, tối đa 200 mới nhất, không sàn (`max_reviews_per_place` 200, `max_review_age_months` 11, `min_reviews_per_place` 0; thử bỏ trần thì nơi đông khách dừng giữa danh sách dài và không lưu được gì); dữ liệu cũ đã lọc: bỏ 8.937 review quá 11 tháng ở 385 place; `run` crawl lại place đã lưu mà `too_few`. Nút "Xem thêm" (`button.w8nwRe`) có cho cả review lẫn owner reply (`expandOwnerResponse`), `EXPAND_JS` chỉ bấm nút của review (owner reply không lấy nữa: không phải bằng chứng, spec §1 Dữ liệu thô); `reviews_complete=False` (hết 15 s không có đợt mới, mạng chậm) → thử lại, không giảm tab (giảm tab ở lỗi chậm từng kẹt throttle ở 1 tab: 8 place / 30 phút), lần cuối mới lưu kèm cờ + `errors.jsonl` (như TikTok); `tabs` 10; review kết thúc " …" mà không có nút là text Maps tự cắt, không mở thêm được trong khung này.
  - TikTok ASR + kiểm tra (2026-09-30): phase `asr` → `asr_check` → `place_verify` sau `place_crawl` (spec §1, Phase 2; layout `video.json`: spec Dữ liệu thô). Thử Gemma: transcript giả lập (tên nghe nhầm, lời nhạc nền, đoạn vô nghĩa) chấm đúng hết; trên output vô nghĩa, Gemma vẫn "sửa" "mry o dayay red vui" → "mọi người đi chơi vui" dù prompt cấm → chặn bằng code (`MIN_KEPT` 0,5). 5 video thật đầu tiên: ASR giọng người dùng được, Gemma sửa đúng tên ("siêu thị cô đà lạt" → "GO! Đà Lạt"); 2 video chỉ nhạc → `no_speech`; keyframe đọc được biển hiệu / logo / chữ overlay. Một video map vào 2 spa tên gần giống, cả hai `yes` → prompt nay kèm các nơi khác cùng video (`others`), bằng chứng hợp nơi khác thì không `yes`: chấm lại còn 1 `yes`, 1 `no`. `place_filter` trên 450 place đã search: 4.400 video, 2.717 cặp `yes`.
  - ASR sai và cách sửa (2026-10-01, 608 video đã kiểm: 288 good, 79 partial, 175 no_speech, 66 unusable; segment 2.282 ok, 1.428 fixed, 433 lyrics, 275 garbled): lỗi chính là từ mượn ("mátage" → massage), tên riêng ("PiNi" → "mini" / "pin đi"), nhầm dấu ("sân bay" → săn mây), nhạc nền có lời (cả rap tiếng Anh). Ca "Quỷ Núi" (khu trong quần thể PiNi): `asr_check` ép tên place "mini" → "Quỷ Núi", `place_verify` đọc biển "Pini Dalat" thành "Pin đi" → `no`. Sửa: keyframe + `screen_text` vào `asr_check`, `guard` hoàn tác chỗ thay không giống âm, phase `asr_alt` (PhoWhisper-medium) cho segment không tin được rồi Gemma ghép ASR + ASR2, prompt `place_verify` đọc chữ màn hình đúng như hiện và `unsure` khi quan hệ khu / quần thể không rõ, review loại `place_verify`. Thử lại 5 video: "mini" → "Pini" (theo biển), Quỷ Núi `yes`, ghép ASR2 thêm "phương thức" / "quần thể" và bỏ "bin laden" PhoWhisper bịa. Trang review chưa có tab cho `place_filter` (queue có tạo mục, `page.html` thiếu nhãn).
  - Còn phải làm: review dài không bấm được "Thêm" thì giữ text bị cắt; trang chặn `/sorry` của Google chưa chờ người giải (dừng với `LoginRequired`).

## corpus-observe — Observation từ review Google Maps

- file: `config/ontology.yaml`, `src/corpus/ontology.py`, `src/corpus/observe/` (`__init__.py`, `gmaps/details.py`, `gmaps/place_rules.py`, `gmaps/prep.py`, `gmaps/gate.py`, `gmaps/extract.py`), `REVIEW_OBSERVE` + `REVIEW_VERIFY` trong `src/corpus/llm/tasks.py`, `scripts/observe_prompt_eval.py`, `scripts/rerun_observe.sh`, `tests/test_ontology.py`, `tests/observe/`
- cách kiểm chứng: `python -m pytest -q tests/test_ontology.py tests/observe`; `python -m corpus gmaps observe --limit 20` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: ontology v6 (54 feature): `condition_change` chỉ còn `declined` (`improved` đúng ~30%, đa số "xe mới" của tiệm thuê xe); `long_walk` cần lời nói về đi bộ / khoảng cách / thời gian đi bộ; `weather_exposed` `sheltered` cần mái che / trong nhà của chính nơi đó (không phải nhân viên che dù, xe thuê); thêm phản ví dụ cho `booking_needed` (đặt bàn được xác nhận), `visit_duration` (liệu trình spa), `steep_or_stairs` absent ("đi thẳng xe lên"); `entry_fee` giữ số tiền trong quote; feature mới `tasting_available`, `costume_rental`, `small_space`, `toilet`, `mosquitoes` (đề xuất ≥ 50 lần trong `proposed_top`). Rule v4: `place_facts.tickets` (giá vé US$ của Maps); category lấy từ `list` khi trang place không có (41 nơi). Kiểm chứng: `scripts/observe_prompt_eval.py` 29/29 (thêm 8 câu cho lỗi v5, thoát mã 1 khi lỗi cũ quay lại); chạy lại toàn bộ bằng `scripts/rerun_observe.sh` (chờ mạng UIT, chặn nếu eval trượt, giữ bản cũ ở `data/gmaps/observations_before_v6`). Thử 9router (`cx/gpt-5.6-*`) làm extractor: 3–4 phút cho một lô 16 câu và `REVIEW_VERIFY` trả lỗi, không dùng cho 8.500 lô.

### Trước đó (2026-10-01, đêm)
- hành vi: ontology v5 (49 feature, 6 nhóm): thêm nhóm `operation` với `visit_duration` (Estimate); `steep_or_stairs` / `long_walk` thêm `absent`, `weather_exposed` thêm `sheltered`; `check: span` thêm `booking_needed`, `weather_exposed`; hint loại câu kể của người viết ("mình đặt bàn trước", "đường đi hơi xa", "xe mới"). Prompt: phủ định không bao giờ thành `present`. Rule v3: thêm attribute sân thượng, sân chơi, nhạc sống, đi bộ đường dài; `place_facts.hours` / `closure`; file observation có `place` và `voices`. Lý do: kiểm tay ~150 observation v4: `booking_needed` ~50%, `weather_exposed` ~60% (đảo nghĩa "mái che kín"), `long_walk` ~65%. Kiểm chứng: 16 câu chuẩn 18/18 đúng; 6 place thật v4 → v5: bỏ 3/3 `booking yes` sai ở một quán, weather sai giảm 7 → 3, recall effort gần như giữ; `absent` vẫn hiếm (1 / 6 place).

## corpus-aggregate — Signal + xu hướng theo địa điểm

- file: `src/corpus/aggregate/` (`__init__.py`, `place.py`, `estimates.py`), `config/category_defaults.yaml`, `tests/aggregate/`
- cách kiểm chứng: `python -m pytest -q tests/aggregate`; `python -m corpus aggregate`

### Hiện tại (2026-10-02)
- hành vi: mỗi feature có `quality` (độ chính xác đo bằng nhãn của giá trị đứng đầu), `servable` (nguồn thẩm quyền, qua ngưỡng nhãn, hoặc người `accept`), `review_decision`; quyết định `feature_review` của người: `disable` → `status = disabled`, `accept` bỏ `needs_review`, `report` / `refresh` đặt `needs_review`. File observation ontology cũ vẫn được đọc tới khi observe chạy lại (trước đây bị bỏ: đổi ontology là xóa sạch intel); intel ghi `observation_versions`. `estimates` (`aggregate/estimates.py`, `config/category_defaults.yaml`): nhóm category, thời gian tham quan [ngắn, thường, dài] (review khi ≥ 3 tác giả đồng ý, còn lại mặc định theo category), giá vé VND (số tiền trong quote `entry_fee`, mỗi tác giả một giá trị lớn nhất, hoặc vé Maps), `usable_as` mặc định, `effort_hint` (chỉ để xếp hạng: dốc có ở 16% nhà hàng, 37% quán cà phê đã có bằng chứng). Lần chạy: 1.437 nơi, 100% có thời gian tham quan (51 từ review), 241 có giá vé.

### Trước đó (2026-10-01, đêm)
- hành vi: thêm `mention_rate` mỗi feature (tác giả nói / `voices`), `identity` (category, lat, lng, address), `operation.hours` / `closure`. Lý do: feature chỉ `present` có `agreement` luôn 1 (1/250 review nói view đẹp vẫn là "có view"); Place Decision cần giờ mở cửa, đóng cửa, vị trí. Quy tắc: `docs/P1_CORPUS.md` §5 Aggregate.

## corpus-observe-tiktok — Observation từ video TikTok

- file: `src/corpus/observe/tiktok/extract.py`, `VIDEO_OBSERVE` + `VIDEO_VERIFY` trong `src/corpus/llm/tasks.py`, `tests/observe/tiktok/`
- cách kiểm chứng: `python -m pytest -q tests/observe/tiktok`; `python -m corpus tiktok observe --limit 5` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: mỗi cặp (video, địa điểm) trong `place_verify.evidence_pairs()` → một call đọc caption, segment transcript `ok` / `fixed` (đánh số, có giây) và 4 keyframe khi video chỉ nói về nơi đó. Gate: quote lời nói phải nằm trong đúng segment, quote caption trong caption / hashtag, observation từ khung hình chỉ cho giá trị ảnh chứng minh được (`FRAME_VALUES`: bậc thang, trong nhà / ngoài trời, đông, view, hoa, thiên nhiên, chỗ ngồi ngoài trời, decor, cắm trại, đường xấu; không `absent`, không suitability, không "vắng" vì video quảng cáo quay phòng trống). Feature `check: span` đọc lại (`VIDEO_VERIFY`: segment quanh quote hoặc đúng khung hình). Một phiếu mỗi người đăng, ngày = ngày đăng. Ghi `data/tiktok/observations/<fid_dir>.json`; `aggregate` đọc không đổi code (loại nguồn `video`). Thử 5 nơi: trích đúng "giá cả rất là bình dân", "nằm trong căn nhà cổ hơn trăm năm tuổi", "nhớ đặt lịch trước"; lỗi đã sửa: cầu thang trong ảnh bị gán `nature`, chó trong ảnh thành `animals`. Chạy chung key Gemma với `gmaps observe` gặp 429 → `scripts/after_rerun.sh` chạy sau khi observe Maps xong.

### Trước đó
_không có_

## corpus-serving — Serving record cho Place Decision

- file: `src/corpus/serving/` (`record.py`, `groups.py`, `run.py`), `config/serving.yaml`, `config/eval_trips.yaml`, `tests/serving/`
- cách kiểm chứng: `python -m pytest -q tests/serving`; `python -m corpus serving` rồi `python -m decision evaluate`

### Hiện tại (2026-10-02)
- hành vi: `serving` đọc intel → `data/serving/places.json`: trạng thái theo khía cạnh (`VERIFIED` khi `servable` và còn mới; chưa đo / xung đột / đồng thuận thấp → `UNCERTAIN` kèm lý do; quá cửa sổ độ mới → `OUTDATED`; `NEEDS_REVIEW`, `DISABLED` không xuất hiện), nơi đóng cửa (tạm hoặc hẳn) không vào; giờ / giá là fact có độ mới, thời gian tham quan / giá vé / `effort_hint` là estimate; `usable_as` = mặc định category trừ `experience` khi coverage `NONE`; `check()` fail-closed (pass cần giá trị chắc chắn mà không ai nói ngược). Khu vực: leader clustering bán kính 1,2 km quanh nơi đông nhất (118 khu). Gần trùng: cùng nhóm category + vai trò, Jaccard ≥ 0,6 trên feature "loại nơi" được ≥ 2 người và ≥ 3% người viết nhắc, so với leader (không nối chuỗi: single linkage cho một nhóm 416 nơi). MMR. 1.394 nơi trong ~11 s.
- đo: `serving/evaluate.py` đã bỏ; `python -m decision evaluate` chạy đúng pipeline thật thay nó. Lần chạy gần nhất: 0 vi phạm ràng buộc cứng, 0 `unknown` trong danh sách chính, gần trùng 0%; 18/30 chuyến không đủ 8 nơi vì mọi điều kiện effort / thời tiết / chặt chém chưa có giá trị `pass` nào được đo (chưa có nhãn, `absent` hiếm).

### Trước đó
_không có_

## corpus-photos — Ảnh Google Maps làm bằng chứng

- file: `src/corpus/crawl/gmaps/photos.py`, `src/corpus/observe/gmaps/photos.py`, `PHOTO_OBSERVE` + `PHOTO_VERIFY` trong `src/corpus/llm/tasks.py`, `src/corpus/crawl/common/browser.py` (user agent), `scripts/after_photos.sh`, `tests/crawl/gmaps/test_gmaps_photos.py`, `tests/observe/gmaps/test_gmaps_photo_observe.py`
- cách kiểm chứng: `python -m pytest -q tests/crawl/gmaps tests/observe/gmaps`; `python -m corpus gmaps photos --limit 5` rồi `python -m corpus gmaps photo_observe --limit 5` (mạng UIT)

### Hiện tại (2026-10-02)
- hành vi: quy tắc ở `docs/P1_CORPUS.md` §4 Observe (Ảnh Google Maps). Phát hiện khi dò: Chrome headless bị Google cho Maps "chế độ bị hạn chế" (không tab review / ảnh) dù đăng nhập → `open_profile` / `open_sessions` dùng user agent Chrome thường, `check_signed_in` dừng khi gặp thông báo. Thử 4 nơi: lần đầu `setting` suy từ ảnh món ăn, một ảnh vừa `indoor` vừa `outdoor`, "vài bậc ở cửa" thành `steep_or_stairs` → prompt chỉ cho `setting` từ khu khách ngồi / đi, bậc thang phải là leo dài, gate bỏ ảnh có hai giá trị. Ảnh cận cảnh vẫn đôi khi thành `indoor` (yếu; aggregate đếm theo người đăng). Thư viện "Tất cả" của nhiều nơi phần lớn là ảnh cũ (một nơi 30 ảnh cũ / 0 giữ). Tốc độ crawl ~2,6 nơi/phút ở 3 tab.

### Trước đó
_không có_

## corpus-ontology-v7 — Giá trị phủ định cho ràng buộc cứng

- file: `config/ontology.yaml`, `REVIEW_OBSERVE` trong `src/corpus/llm/tasks.py`, `scripts/observe_prompt_eval.py`
- cách kiểm chứng: `python scripts/observe_prompt_eval.py` (37/37, 2026-10-02)

### Hiện tại (2026-10-02)
- hành vi: `tourist_trap`, `rough_road_access`, `cash_only` có thêm `absent` ("không chặt chém, đúng giá niêm yết", "đường nhựa, xe vào tận cổng", "có chuyển khoản"); "giá rẻ, hợp lý" vẫn chỉ là `value_for_money`. Lý do: `evaluate` cho 0 ứng viên chính ở chuyến "không chặt chém" / "không đường xấu" vì im lặng không phải bằng chứng (người dùng chọn phương án thêm giá trị phủ định). Chạy lại observe toàn bộ từ 10:24.

### Trước đó
_không có_

## trip — Trip Understanding: hội thoại ngắn tới Search Input

- file: `src/trip/` (toàn bộ), `config/trip.yaml`, `tests/trip/`, `web/src/user/tu/`, `web/src/user/screens/Understand.tsx`
- cách kiểm chứng: `python -m pytest -q tests/trip`; `python -m pytest -m live tests/trip/test_live.py` (Gemma thật); `python -m trip serve` + `/app/understand`

### Hiện tại (2026-10-09, chiều)
- hành vi: như bản trước, thêm hai phase sau lời kể. (1) Chỉ lượt agent đọc lời kể đầu tiên được hỏi bằng lời (`meta.told`; tool `ask_*` chỉ có ở lượt đó, prompt ưu tiên `ask_choice`; câu hỏi rơi vào văn bản kết bằng "… không?" kèm chip Có / Không). Trả lời câu làm rõ, bỏ qua nó, hoặc agent không cần hỏi → vào thẳng phase quiz (`domain/questions.py`, flashcard chip, không gọi model) rồi review; thẻ F mời trắc nghiệm bỏ. Lời chào / "không đi nữa" không ghi được gì thì chưa tính là kể. Thẻ chủ đề tính là kể. Agent lỗi giữ thẻ đang mở để bấm lại. (2) Next không còn bị chặn bởi tín hiệu sức khỏe mở: `_show` ghi lựa chọn chặt nhất của thẻ an toàn (`questions.strictest`, source `inferred`) rồi biên dịch, chỉ thêm giới hạn, không nới. Đo events 2 ngày: `trip.turn` qua agent p50 5,7 s / p90 22 s, lượt không gọi model ~20 ms.

### Trước đó (2026-10-09)
- hành vi: sửa các lỗi T-1…T-8 của phiên test người mới, agent chạy trên Gemma host LAN. (1) Ngân sách giữ đúng lời người dùng: `budget_vnd` + `budget_scope` (`trip_total | per_day | per_person | per_person_day`, prepass đọc "tổng", "cả chuyến", "cho 2 người", "/người/ngày"); không nói phạm vi thì ≥ 2 triệu tính cả chuyến (có ✎); `compile` chia theo số ngày và số người thành `Context.budget_vnd` (VND/người/ngày), chưa biết số người thì `unknown` (`domain/budget.py`). Web: "5 triệu cho cả chuyến · ≈ 830 nghìn/người/ngày". (2) Lời sửa được prepass đọc trước agent; câu hỏi thật của agent hiện trong chat kèm lựa chọn trả lời nhanh. (3) Trả lời xong thì đóng thẻ; "Bỏ qua" / "Chưa chắc" xử lý không gọi model, ghi vào `meta.declined`, agent không được hỏi lại; bấm nút mà agent lỗi thì không bao giờ ra `FALLBACK_SAY`. (4) `liked_groups` (`nature | sights | chill | meal`, "thích cà phê" → `chill`) và `month_part` ("cuối tháng 10") vào SearchInput. (5) Thẻ chủ đề ở Khám phá là lượt `theme` ghi soft / nhóm cố định (`config/trip.yaml` `themes`), không qua model. (6) Ngày đi chọn bằng lịch (`ask_text` `kind: "date"`). (7) Khối suy nghĩ của Gemma (`<|channel>thought…`) bị lọc khi stream; câu hỏi Gemma viết thành chữ được đổi thành thẻ. Đo trên Gemma: lượt gõ đầu 6–7 s, bấm lựa chọn 1,5–4 s, bỏ qua / ngày / chủ đề < 0,1 s.

## decision — Place Decision: Search Input tới Decision Output

- file: `src/decision/` (toàn bộ), `config/decision.yaml`, `config/eval_trips.yaml`, `tests/decision/`, `web/src/user/pd/`, `web/src/user/screens/{Shortlist,PlaceDetail,Compare,Curate,Feasibility}.tsx`
- cách kiểm chứng: `python -m pytest -q tests/decision`; `python -m pytest -m live tests/decision/test_decision_live.py`; `python -m decision serve` + `/app/shortlist`; `python -m decision evaluate`

### Hiện tại (2026-10-09)
- hành vi: sửa D-1…D-7. (1) Agent chạy trên Gemma host LAN (0,7–1,6 s; 9router trước đó 10–16 s nên mọi lượt rơi xuống từ khóa). Prompt `DECISION_TURN` tách op `travel / crowd / price`; runtime nhận JSON bọc ```json; agent lỗi thì trả "Trợ lý đang bận…", `NONE` chỉ khi thật sự không khớp; "bỏ mấy chỗ đông đi" ẩn các nơi có cảnh báo đông (`Profile.hide_crowded`). Analytics có `decision_fallback`. (2) `fit.crowd_evidence` trừ điểm theo bằng chứng đông / chờ lâu khi chuyến tránh đông; nơi có cảnh báo đông không được "Hợp nhất". (3) Độ mạnh bằng chứng theo log số người (bão hòa ở 30), trải nghiệm ít được nhắc tính ít hơn, "Hợp nhất" cần `top_min_pref` 0,25; `liked_groups` cộng điểm nhóm và chọn tab mở đầu (`view.focus`). (4) `decision.day_visit`: khu cắm trại tính một lần ghé trong ngày, khoảng qua đêm để riêng (`stay`); ghi vào `confirmed[].visit` cho Planning. (5) Cảnh báo chung của chuyến hiện một lần (`view.notes`), thẻ tối đa 2 cảnh báo riêng. (6) Giá "dưới 100k/người", vé vào cửa khi không có khoảng giá, ngân sách người dùng hiện ở đầu trang. (7) Chat thành cột bên, nút Khóa / So sánh / Bỏ có chữ, thanh dưới nói còn chỗ cho bao nhiêu nơi thay vì "Lịch sẵn sàng".

### Trước đó (2026-10-08)
- hành vi: như bản trước, thêm ba điểm. (1) Không cắt ở shortlist nữa: mỗi nhóm hiển thị có thứ hạng đầy đủ (nơi đã chọn → nơi MMR `top` → mọi nơi còn lại theo `score`), view chỉ mang cửa sổ đang hiện (`window.py`, `State.shown`, `page_size` 24) kèm `total`; `read page` nối trang tiếp. Dữ liệu thật chuyến 3 ngày: 116 / 193 / 424 / 545 nơi, view 114 KB. (2) Dựng lại thì gộp ít xáo trộn: nơi còn khớp đứng nguyên ô, ô trống nhận nơi mới hợp nhất, cửa sổ phần lớn lỗi thời thì thay hết; view có `change` mỗi nhóm cho web chạy chuyển cảnh. `first_shortlist` = số card `top` + anchor. (3) Lượt chữ: op `soft` / `unmapped` thay bằng `trip`; engine phát event `trip`, harness chuyển cho Trip `refine` rồi `rebase` (`docs/AGENT_HARNESS.md` §2). Đo trên journey thật: "không thích quán giống Miền Du Mục" → 4 soft `avoid` từ nét của nơi đó, nhóm cà phê giữ 23 / thay 1, ăn uống giữ 22 / thay 2.
- web: lưới tự tải khi cuộn (3 thẻ khung, dòng "Đã xem hết"), nhãn "Hợp nhất", header "N nơi hợp… · Chat để thu hẹp" kèm "−N nơi" khi số đổi, tab "+N mới", chuyển cảnh `useStagedList` + FLIP. Đĩa xoay làm lại: nửa đĩa 180° quay vòng không có điểm đầu, cánh là mảnh vành khuyên khép thành vòng liền, tối đa 7 cánh để ảnh to, ít nơi thì cánh to hơn (180° / số nơi, tối đa 45°); lăn / kéo trên đĩa xoay đĩa, phần nội dung cuộn như trang; nhóm thành tab có chữ, bỏ hàng "Nơi trước / Nơi sau" (trước đây lăn ở đâu cũng xoay đĩa, cánh hình thang nhỏ, nút nhóm chồng nhau ở 1280×720, hàng điều hướng bị cắt ở 1440×900).
- sau lượt chat có mong muốn: câu trả lời kết bằng `diff(rebuilt=True)` ("Giữ 45 nơi, thay 3 nơi hợp hơn"); thay đổi không xê dịch gì thì không có câu báo (trước đây "0 nơi, 0 phút…"); `rebase` giữ lịch sử hoàn tác; `why-not` chỉ chỗ của nơi nằm dưới phần đã tải; prompt agent chỉ có lý do cho trang đầu mỗi nhóm. `backup_pool` và hai bản đo offline chỉ dùng nơi `top`.

## planning — Lịch trình từ Decision Output tới Plan Output

- file: `src/live/`, `src/planning/`, `config/planning.yaml`, `config/live.yaml`, `tests/live/`, `tests/planning/`, `src/harness/dispatch.py`, `web/src/user/planning/`, `web/src/user/pd/previewQueue.ts`, `web/src/user/screens/Plan.tsx`
- cách kiểm chứng: `python -m pytest -q tests/live tests/planning`; `python -m planning build|variants|lodging <decision_output.json>`; `python -m planning serve` (web qua `/api/planning`); `python -m planning evaluate` (cần OSRM, không chạy trong CI)

### Hiện tại (2026-10-10)
- hành vi: cá nhân hóa thời lượng theo hoạt động/sở thích có bằng chứng, chọn giờ phù hợp từ ngữ cảnh; thử chuyển sang ngày khả thi ở cả hai phía trước khi rút phần flexible. `set_visit`/`clear_visit` giữ hoặc xóa riêng giờ/thời lượng; clock lock, undo/redo, proposal và replay giữ chỉnh sửa, act xung đột không commit. Validator kiểm giờ/thời lượng thực và missing requested visit; hard `eq`/`ne` fail-closed, physical không bỏ qua qua `relaxed`. Drawer sửa điểm ghé chuyển đúng ngày hiển thị sang index backend. Preview gom request trùng, reuse ma trận tập con và route còn hợp lệ, namespace theo hành trình; cache không kéo dài TTL nguồn kể cả cache disk. Web chỉ chạy một preview và giữ lựa chọn mới nhất. Kiểm chứng: 802 test Planning/Harness/Decision pass (109 skip, 2 deselected), 5 test editor, 7 test queue, web build pass; review Tasks 1–4 đạt.

### Trước đó (2026-10-09, chiều)
- hành vi: như bản trước, thêm: ô gõ chỗ ở / xuất phát (`live/geocode/photon.py`) chỉ giữ kết quả Photon `countrycode = VN` (khung `VN_BBOX` trùm cả Nam Ninh, Hải Nam, Thái Lan nên trước đó ra "大沙田 南宁市", "儋州市"); hỏi dư ×3 rồi cắt về `limit`; khóa cache thêm `country` để bỏ các entry cũ.

## landing — Landing 3D (máy tính) + Dùng ứng dụng (điện thoại)

- file: `web/src/user/screens/{Landing,GetApp}.tsx`, `web/src/user/landing/{scene,terrain,device}.ts`, `web/src/user/landing/{places,points,stats}.json` (sinh bằng `web/scripts/pick_landing_places.py`), `web/src/user/css/landing.css`, `web/src/user/UserApp.tsx`; phụ thuộc `three`
- cách kiểm chứng: `npm run build --prefix web` (chunk `scene` riêng chứa three.js); mở `/` ở 1440×900 và 1024×768, cuộn qua 6 đoạn; giả UA iPhone mở `/` phải thấy trang Dùng ứng dụng; bật `prefers-reduced-motion` thấy khung tĩnh + 4 chương xếp lưới

### Hiện tại (2026-10-09)
- hành vi: như bản trước, sửa câu chữ cho đúng sản phẩm: hero và Hỏi nhanh nói "Đăng nhập bằng Google, miễn phí" (bỏ "Không cần tài khoản"); số nơi làm tròn "hơn 1.700" để không lệch app; bỏ "Khám phá Đà Lạt · chưa mở" khỏi Sắp có. Điện thoại: trang "Mở trên máy tính" với Chép link, mã QR của link hiện tại (`ui/qr.ts`, bộ mã hóa tại chỗ) và nút chia sẻ khi trình duyệt có; nút cửa hàng chỉ hiện khi đã có link. App dùng Lora cho tiêu đề như landing.

### Trước đó (2026-10-08, khuya)
- hành vi: máy tính thấy sân khấu sticky với thung lũng Đà Lạt 3D lúc bình minh (three.js thuần, tải lười): bầu trời hồng đào, sương, đồi thông, hai hồ, phố mái ngói; 1.773 đốm sáng là toạ độ thật của mọi nơi; 5 nơi được chọn là bưu thiếp in ảnh thật, tuyến là đường chấm. Cuộn qua 6 đoạn theo bước sản phẩm (Mở đầu → Tìm hiểu → Lựa chọn → Lựa chọn · lý do → Lịch trình → Đánh giá), thanh bước bên phải 5 mục. Đoạn Đánh giá diễn 4 câu của màn Phản hồi. Ô nhập ở Mở đầu là ô thật. Sau sân khấu: bento ảnh thật, Hỏi nhanh cạnh Sắp có, CTA, footer. Chữ: Lora + Be Vietnam Pro, giọng "TripGuardian" / "bạn". Điện thoại vào `/` thấy trang Dùng ứng dụng (link cửa hàng từ `VITE_APP_IOS_URL` / `VITE_APP_ANDROID_URL`, chưa có thì `Sắp có` + `chưa mở`; `Gửi link sang máy tính`; `Tiếp tục với bản web` → `/app`).

## user-web — Giao diện người dùng chính thức (landing + `/app`)

- file: `web/src/user/` (`UserApp.tsx`, `screens/`, `ui/`, `css/`, `store.ts`, `lib.ts`, `landing/`), `web/src/App.tsx`; backend `src/harness/{dispatch,server,session}.py` (`preview`, `summaries`, `feedback`, `report`), `src/planning/engine.py` (`preview`, cache theo hash Decision Output), `src/decision/{engine,tools}.py` (`draft`, `report`)
- cách kiểm chứng: `npm run build:prod --prefix web`; `python -m pytest -q tests/harness tests/planning tests/decision tests/trip`; chạy harness + Vite rồi `node web/scripts/shots_app.mjs <url>` (đi trọn luồng với agent thật, chụp `web/shots/app/`)

### Hiện tại (2026-10-09)
- hành vi: như bản trước, thêm: (1) Hiểu chuyến đi: thẻ quiz (mọi thẻ không phải `frame` / `conversation` / `ask:`) tự hiện thành flashcard; flashcard có chip không hiện lại đoạn hội thoại; `Khác, tự gõ` đưa con trỏ vào ô gõ thay vì gửi câu rỗng. `Xem gợi ý` (cột phải), `Xem gợi ý luôn` (dưới tóm tắt) và bước `Lựa chọn` trên thanh bước không còn khóa theo `ready`; bấm bước khi đang chờ AI thì chuyển khi lượt xong. (2) Chọn nơi bỏ dòng "X và Y khá giống nhau". (3) `PlaceSheet` có tab `Video` (clip người đã đến, chỉ khi có) tách khỏi `Đánh giá`. (4) Clip tự phục vụ: `web/scripts/make_clips.py` (NVENC, fallback libx264) làm bản 540×960 ~1 Mbit/s faststart ở `data/thumbs/tiktok/<id>/video.mp4`, `web/server.mjs` gửi bản này khi có (URL giữ nguyên), `./run.sh prod` chạy nó nền; 155 clip web dùng nặng 6,3 GB bản gốc (trung vị 8,5 MB, tối đa 256 MB).

### Trước đó (2026-10-08, tối)
- hành vi: như bản trước; câu mở của Hiểu chuyến đi thành cuộc trò chuyện (`screens/TripChat.tsx`, `UI_SPEC_USER_WEB` §Trang 3 Mở đầu): AI hỏi, người dùng gõ (câu ở landing là tin nhắn đầu), lúc AI đọc hiện chấm gõ + lời stream + `“quote” → trường` từ sự kiện `preview`; xong thì dừng ở `Mình đã hiểu như này` (mỗi dòng có nguồn và nút sửa, giới hạn / nơi muốn đến bỏ được, chip sở thích có ×) + `Mình cần hỏi thêm một số ý` (`unknowns`), người dùng sửa bằng lời hoặc bấm `Đúng rồi, hỏi tiếp` mới sang chồng thẻ. Chuyển câu: thẻ rơi ngay khi bấm (trước: chờ 380 ms rồi mới gửi, thẻ cũ hiện lại và bị chia hai lần trong lúc chờ máy chủ), chồng thẻ nghiêng lên + chấm chờ trong lúc chờ, thẻ mới chờ thẻ cũ rơi xong; khoá thẻ theo lần nhận thẻ thay vì `hist.length` nên không chia lại khi lịch sử cập nhật; lượt trả lời vào lịch sử ngay nên `câu N` đúng từ lúc thẻ mới hiện; trang tự cuộn về đầu chồng thẻ khi thẻ mới khuất.

## detail-logistics — Xem chi tiết, hiện hết gợi ý, hỏi hậu cần, chỗ ở theo gu

- file: `web/src/user/ui/{PlaceSheet,PlaceInput,TransitPick}.tsx`, `web/src/user/screens/{Understand,Lodging,Plan}.tsx`, `web/src/user/tu/`, `web/scripts/pick_covers.py`; `src/decision/pipeline.py` (danh sách đầy đủ, cửa sổ, gộp ít xáo trộn); `src/trip/domain/logistics.py`; `src/live/{flights,buses}/`, `src/live/geocode/photon.py`; `src/planning/{logistics,lodging}.py`; `src/harness/server.py` (`/geo`, `/lodging/suggest`, `/transit` + SSE); corpus nhóm `stay` (`config/queries.yaml` `stay:`, `listing.build_stay`); `scripts/prewarm_transit.py`
- cách kiểm chứng: `python -m pytest -q tests/live tests/planning tests/harness tests/decision tests/trip`; `node web/scripts/shots_sheet.mjs <base> <journey>` (modal, 1440 / 390); `node web/scripts/shots_app.mjs <base>` (toàn luồng: xuất phát → máy bay → chọn chuyến → chưa có chỗ ở → chọn nơi → "Bạn ở đâu?" → lịch)

### Hiện tại (2026-10-08)
- hành vi:
  - "Xem chi tiết" là một modal `PlaceSheet` (`?place=<id>`, Back / Esc đóng, ảnh bay vào chỗ bằng View Transitions / FLIP) mở từ đĩa, lưới, anchor, trợ lý, thanh "Đã chọn"; tab Hình ảnh hiện ≤ 12 ảnh/nơi do `pick_covers.py` chọn (YOLO + pHash + Gemma `photo_rank`; 1.704 nơi có gallery), thumbnail WebP cho mọi ảnh mới (`make_thumbs.py`).
  - Chọn nơi hiện hết ứng viên qua lọc: cuộn tải thêm 24 nơi/lần; chat thu hẹp giữ nơi còn khớp đúng chỗ (`docs/P3_PLACE_DECISION.md` §9.2–9.4).
  - Trip Understanding hỏi hậu cần trước `ready` (`docs/P2_TRIP_UNDERSTANDING.md` §Hậu cần); web: ô gõ có gợi ý cho xuất phát / chỗ ở, danh sách chuyến bay / xe khách thật (cache, thiếu thì crawl nền + SSE, lỗi thì mở trang đặt vé + nhập tay giờ), các dòng mới trên vé chuyến.
  - Chỗ ở: corpus có nhóm `stay` chỉ Planning đọc; Planning xếp chỗ ở theo gu trước, vị trí sau (`docs/P4_PLANNING.md` ⓐ); chưa có chỗ ở thì web hiện "Bạn ở đâu?" một lần trước lịch; đã đặt thì lịch neo thẳng vào chỗ đó.
  - Đo 2026-10-08: chuyến bay SGN→DLI `pending` → `ready` sau ~18 s (5 chuyến), lần sau từ cache; xe khách ~1,5 s.

### Trước đó
- _không có_

## tiktok-place-poi — Địa điểm TikTok (POI) của từng nơi Maps

- file: `src/corpus/crawl/tiktok/{place_poi,poi_crawl,clips}.py`, `crawl.py` (`poi_of`, `video.json.poi`), `place_filter.py` (`places_by_video` đọc `poi_crawl/`), `src/corpus/llm/tasks.py` (`PLACE_POI_MATCH`), `scripts/free_tiktok_clips.py`, `web/server.mjs` (mp4 có Range), `web/scripts/export_snapshot.py`, `web/src/user/ui/PlaceSheet.tsx` (`<video>` khi `local`), `tests/crawl/tiktok/test_tiktok_{place_poi,poi_crawl}.py`
- cách kiểm chứng: `python -m pytest tests/crawl/tiktok -q`; `python -m corpus tiktok place_poi --city dalat` rồi đọc mẫu `data/tiktok/place_poi/dalat.json`

### Hiện tại (2026-10-09)
- hành vi:
  - Mô tả phase và layout file: `docs/P1_CORPUS.md` §1 (Phase 2, `place_poi/`). `video.json` mới có `poi`; video cũ đọc `poi` từ `info.json` (5.722 / 11.356 video có gắn).
  - Đo 2026-10-09, Đà Lạt: 983 nơi có ứng viên, 709 nơi được gán; 2 lần đọc lệch nhau ở 91 cặp (`unsure`). Một lần đọc đơn: 43 / 983 nơi đổi kết quả giữa hai lần chạy giống nhau, có ca sai kiểu "Nhà Hàng Datanla" = khu du lịch thác. Mẫu 20 nơi đã gán (trước luật một POI một nơi): 17 đúng rõ.
  - Thử trang POI (`tiktok.com/place/<slug>-<poi_id>`): mở được khi không đăng nhập, không captcha; `/api/poi/item_list/` trả 25–30 item / trang kèm `playAddr` h264 tải được bằng phiên ẩn danh; một quán 1.009 video / 44 trang trong ~6 phút, không bị chặn.
  - `poi_crawl` lô đầu 20 nơi: 90 video / nơi liệt kê trong 12–16 s, 187 video tải; 1 nơi dính 403 cả 10 lần tải cùng lúc, chạy lại thì được. Tỉ lệ `place_verify` = yes của video trang POI: chưa đo.

### Trước đó
- _không có_

## accounts — Tài khoản, Postgres (`docs/ACCOUNTS.md`)

- file: `src/db/`, `migrations/`, `src/accounts/`, `src/harness/server.py`, `run.sh` (`db`, `db-backup`), `web/src/user/{account.ts,screens/Auth.tsx,screens/Account.tsx}`
- cách kiểm chứng: `./run.sh db` (chạy lại → `nothing new`); `TEST_DATABASE_URL=<DATABASE_URL> python -m pytest -q tests/db tests/accounts tests/harness`; walk Playwright với `TG_TEST_LOGIN=1` + `APP_BASE_URL` http

### Hiện tại (2026-10-09)
- hành vi: Postgres riêng (container `tripguardian-pg`, 127.0.0.1:5433, role `tg_app` / `tg_analytics`, migration SQL đánh số). `/app` cần đăng nhập Google (code + PKCE, state server + cookie), cookie `tg_session` 30 ngày trượt, đồng ý điều khoản lần đầu. Hồ sơ (avatar 256 px WebP, tên, thành phố, phương tiện, người đi cùng) là prior `source = profile` cho Trip. Xóa tài khoản giữ dữ liệu ẩn danh. Mọi `/api/harness/*` cần phiên (401), mutation kiểm `Origin` (403), hành trình người khác 404; hành trình lưu ở bảng `journeys` (`PgStore`, kiểm revision khi ghi), feedback ở bảng `feedback`; `import-files` nạp file cũ.

### Trước đó
- _không có_ (tài khoản giả lập trong localStorage, hành trình ở `data/harness/sessions/*.json`)

## companion — Đang đi, Calendar, thông báo (`docs/P5_COMPANION.md`)

- file: `src/companion/`, `src/notify/`, `config/{companion,notifications}.yaml`, `web/src/user/{today.ts,notify.ts,screens/Today.tsx,screens/Inbox.tsx}`, `web/public/{sw.js,manifest.webmanifest}`
- cách kiểm chứng: `TEST_DATABASE_URL=… python -m pytest -q tests/companion tests/notify`; `python -m notify run --once`; walk màn Hôm nay ở 1440 và 390 px

### Hiện tại (2026-10-09)
- hành vi: như bản trước, sửa C-1…C-7, E-1, E-2. Trước ngày đi, Hôm nay ở chế độ xem trước "còn N ngày"; Đã đến / Bỏ qua chỉ được cho đúng ngày của điểm đó, chuyến không chuyển `active` sớm. "Còn N phút" tính tới điểm kế tiếp trong cùng ngày; giờ bình minh / hoàng hôn ghi ngày. Gợi ý gần đây theo giờ (giờ ăn → chỗ ăn, săn mây chỉ sáng sớm), đa dạng loại, bỏ nơi trùng ngọn đồi đang đứng (`config/companion.yaml`). Check-in ngoài lịch hiện trong `today.extra` sau khi tải lại. Harness: chỉ `harness.Missing` mới là 404, `KeyError` khác là 500 có log. Chốt xong vào `/app/done` thấy lịch đã chốt, Thêm vào Google Calendar, Chia sẻ lịch; khảo sát chỉ hiện khi chuyến đã xong. Hồ sơ đọc trạng thái chuyến từ server, link `?journey=` mở đúng chuyến; lỗi tải dữ liệu hiện "TripGuardian đang cập nhật" + Thử lại.

### Trước đó (2026-10-09)
- hành vi: chốt lịch tạo `trips` / `trip_stops`; màn `/app/today` với Đã đến tự nguyện, bỏ qua, Hợp / Không hợp, gợi ý "Ở đây" chỉ từ serving (hard filter fail-closed, giờ chưa xác nhận giữ nguyên), "Tôi đang ở nơi khác", dòng "Phần còn lại hơi chật" với phương án `on_delay` qua Planning khi người dùng xác nhận. Google Calendar: calendar riêng mỗi chuyến, không reminder, xem trước → xác nhận theo `preview_hash`, lệch thì chỉ báo `drifted`. Thông báo 9 loại, giờ yên lặng 22–7, 1 / 3 mỗi ngày, tạm im sau 3 lần bỏ qua, biến thể thiếu dữ liệu thì không gửi, bandit khi đủ 200 lượt; web push + hộp thông báo; worker `python -m notify run`.

## analytics — Event và Analytics (`docs/ANALYTICS.md`)

- file: `src/harness/events.py`, `src/analytics/`, `web/src/user/events.ts`, `web/src/admin/{analytics.ts,screens/Analytics.tsx,AnalyticsTabs.tsx,Sessions.tsx,Insights.tsx,Dashboard.tsx,Places.tsx}`
- cách kiểm chứng: `TEST_DATABASE_URL=… python -m pytest -q tests/analytics tests/harness/test_events.py`; `python -m analytics serve` rồi mở `/admin/analytics`

### Hiện tại (2026-10-09)
- hành vi: như bản trước, tab Agent có `decision_fallback` (số lượt, số lượt hỏi agent, số lượt rơi xuống từ khóa, tỉ lệ, lý do) đọc từ log phiên Decision trong `journeys.envelope`.

### Trước đó (2026-10-09)
- hành vi: harness ghi event sau mỗi mutation (`<stage>.<operation>[.<act>]`, latency, path agent / fallback / heuristic, lỗi, chất lượng lịch khi chốt) và các event đọc; web gửi lô event allowlist (sendBeacon). Server analytics private :8770 với role chỉ đọc: phễu (so sánh phiên bản), Trip, Quyết định, Lịch trình, Thực tế, Thông báo, Agent, Chất lượng, phiên + phát lại, Hôm nay, Insights, nhu cầu một nơi; job `python -m analytics cluster` nhóm ý người dùng viết mỗi tuần.


## geo-search — Ô gợi ý nơi xuất phát và chỗ ở theo địa chỉ

- file: `src/live/geocode/{address,photon}.py`, `src/live/settings.py` (`suggest_timeout_s`), `src/planning/logistics.py`, `web/src/user/ui/PlaceInput.tsx`, `web/src/user/tu/types.ts`
- cách kiểm chứng: `python -m pytest -q tests/live/test_address.py tests/live/test_geosearch.py tests/planning/test_planning_logistics.py`; gõ `55/13/19 đường 18b, bình hưng hòa, tphcm` vào ô xuất phát

### Hiện tại (2026-10-09)
- hành vi: Photon bỏ đường cao tốc, công trình, lô đất, tuyến metro và gắn `kind` cho từng dòng; timeout 4 giây rồi sang Nominatim. Chuỗi bắt đầu bằng số nhà được `address.search` mở rộng `tphcm` / `hcm` / `hn`, tìm sâu nhất bản đồ có (hẻm → số ngắn hơn → đường, ưu tiên phường đã gõ) và đặt lên đầu dòng `approx: true` mang chuỗi người dùng gõ + toạ độ của dòng thật; khớp đủ thì không đánh dấu. Ô gợi ý hiện nhãn "Gần đúng" và icon theo loại, dùng chung `geoRow` / `lodgingRow`.

### Trước đó (2026-10-09)
- _không có_

## plan-journey — Lịch trình: hành trình là trang chính, kéo thả, chi tiết theo giờ

- file: `web/src/user/screens/{Plan,PlanDetail,Lodging}.tsx`, `web/src/user/ui/{RouteStory,PlanAlerts}.tsx`, `web/src/user/planning/view.ts` (`placeAt`, `alertsOf`), `web/scripts/test_plan_view.mjs`
- cách kiểm chứng: biên dịch `planning/view.ts` rồi `node --test web/scripts/test_plan_view.mjs`; `npx tsc --noEmit -p web/tsconfig.json`; mở `/app/plan`, kéo một thẻ sang thẻ khác và lên tên ngày
- ghi chú: kéo thả đã thử trên trang xem trước với dữ liệu mẫu, chưa thử trên một hành trình thật

### Hiện tại (2026-10-09)
- hành vi: Hành trình là trang chính: thanh chỗ ở (3 thẻ đề xuất, bấm chọn), dải lưu ý nổi bật, sơ đồ có giờ từng nơi, dự phòng. Kéo thẻ để `reorder` / `move_place`, mũi tên và `Alt + ← →` thay chuột, `Tour` lần đầu. "Xem chi tiết theo giờ" mở trang timeline + bản đồ + cột bên như giao diện cũ.

### Trước đó (2026-10-09)
- _không có_
