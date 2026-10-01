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

### Hiện tại (2026-09-29)
- hành vi: hàng đợi 4 loại mục và tác dụng của quyết định: `docs/specs/CORPUS_SPEC.md` §1 (Review lúc crawl). Server chỉ nghe `127.0.0.1`. Trang: danh sách theo loại + chi tiết (TikTok nhúng video, Maps có link), phím ↑ ↓ / 1–2 / N. Dữ liệu TikTok và quyết định review đã xóa cùng TikTok (tạm ngoài phạm vi); loại `place_*` dùng lại ở phase 2.

### Trước đó
_không có_

## corpus-crawl — Crawl dữ liệu thô TikTok + Google Maps

- file: `src/corpus/crawl/` (`files`, `browser`, `tiktok`, `gmaps`), `src/corpus/__main__.py`, `config/queries.yaml`, `tests/crawl/`, `tests/fixtures/` (`capture.py` lưu lại fixture thật, đã che tài khoản)
- cách kiểm chứng: `python -m pytest -q`; smoke thật `python -m corpus {tiktok|gmaps} --city dalat --headed` với config thu nhỏ

### Hiện tại (2026-09-29, tối)
- hành vi:
  - Lệnh, phase, layout file: `docs/specs/CORPUS_SPEC.md` §1 (Discover, Dữ liệu thô). `python -m corpus login <source>` để đăng nhập lại.
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
  - Còn phải làm: review dài không bấm được "Thêm" thì giữ text bị cắt; trang chặn `/sorry` của Google chưa chờ người giải (dừng với `LoginRequired`).

### Trước đó (2026-09-29, sáng)
- hành vi:
  - `python -m corpus login <source>` mở Chrome với profile `.browser/<source>/` để người đăng nhập; `tiktok` / `gmaps` crawl theo `config/queries.yaml`, ghi file vào `DATA_DIR` (layout: `docs/specs/CORPUS_SPEC.md` §1, Dữ liệu thô).
  - TikTok: bắt JSON API search; mỗi video ghi `info.json`, `video.json` (url, đường dẫn mp4, caption, hashtag, stats, comment lồng reply; mặc định lấy hết trang; bỏ trùng theo `comment_id`; tác giả chỉ còn `author_hash`), rồi `video.mp4` tải từ `playAddr`. Video có `commentCount` > 0 mà lấy được 0 comment thì không đánh dấu xong.
  - Maps: search `<category> <tên thành phố>`, mở từng place bằng URL, mở bảng giờ, tab Giới thiệu, tab review sắp xếp Mới nhất; ghi `reviews.json` rồi `place.json`. Selector nằm trong `gmaps.py`.
  - Captcha: `--headed` chờ người giải tối đa 5 phút; headless dừng với `LoginRequired`. `errors.jsonl` chỉ giữ dòng đầu của lỗi (call log Playwright chứa cookie phiên).
  - Smoke 2026-09-29 (`--headed`): reply: 1 video 11/11 (7 comment + 4 reply, khớp `reply_count`, không reply mồ côi); TikTok 1 query → 3 video (3–52 MB), 12/30/100 comment (trần cũ 100), chạy lại không tải trùng; lấy hết comment trên 2 video: 276/347 comment cấp 1 (`commentCount` 571/606 gồm cả reply), TikTok gửi lặp trang nên bỏ trùng theo `comment_id`; Maps `thác` → 4 place, 3 place đủ 7 dòng giờ, 2 place có giờ cao điểm 7 ngày, mỗi place 10 review. Headless: Maps trả trang thiếu (0 review), TikTok hay gặp captcha.
  - TikTok chạy một lệnh: search lần lượt từng query, video đưa ngay vào các tab dùng chung (một video chỉ lấy một lần mỗi lượt), rồi một lượt nữa cho video chưa xong; cuối in tổng kết. Số tab tự dò (AIMD, `throttle.py`): +1 sau 5 video sạch, tối đa `tabs`; trang lỗi HTTP / timeout → giảm nửa, nghỉ `cooldown_s` (gấp đôi nếu chặn liên tiếp, tối đa `max_cooldown_s`), thử lại tối đa 3 lần (cả search). Mức đạt lưu `data/tiktok/throttle.json`. Tab comment chặn luồng media (chặn cả ảnh / font làm mất nút comment); mp4 tải ngoài tab (`downloads` luồng); chờ theo response API thay vì chờ cố định. `LoginRequired` ở một tab dừng cả lệnh.
  - Độ đủ comment (2026-09-29, 10 video): lấy được ~82% `commentCount`. Phần thiếu do TikTok không trả: API reply báo `total` nhưng trả 0 comment cho reply bị ẩn; API comment báo `total=23` nhưng trả 12 và `has_more=0`. 1 tab và 3 tab song song cho cùng kết quả (song song 36 s so với 56 s).
  - **Google Maps chưa xong** (tạm dừng để hoàn thiện TikTok trước). Còn phải làm:
    - chưa chạy full crawl, mới smoke 1 category (`thác`, 4 place, 10 review/place);
    - headless trả trang thiếu, hiện phải chạy `--headed`;
    - trang chặn của Google (`/sorry`) chưa chờ người giải như TikTok, chỉ dừng với `LoginRequired`;
    - chưa kiểm: điểm dừng cuộn feed ("Bạn đã xem hết danh sách này"); `Thác Prenn` có 0 dòng giờ (chưa rõ do place không có giờ hay selector trượt);
    - `address` còn lẫn ký tự icon ở đầu; review dài không bấm được "Thêm" thì giữ text bị cắt;
    - lấy hết review (hiện trần `max_reviews_per_place`).


