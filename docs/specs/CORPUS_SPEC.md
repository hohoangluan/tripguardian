# Corpus Place Intelligence — Thiết kế chi tiết

Tổng quan ngắn: `docs/CORPUS.md`. File này là thiết kế chi tiết để triển khai.

## Mục tiêu

Xây **corpus Place Intelligence** offline cho planner đọc. Agent xây từ đầu đến cuối; gate tất định kiểm soát mọi lần ghi; người chỉ duyệt một hàng đợi nhỏ, xếp theo rủi ro, ở cuối. Mọi giá trị được phục vụ đều truy về bằng chứng.

Đích: kiến trúc nhỏ nhất mà **đúng** (không bịa địa điểm hay fact), **rẻ** (model miễn phí hoặc rẻ cho khối lượng lớn, model mạnh chỉ ở chỗ cần phán đoán), và cho **output chất lượng cao**, đồng thời mở rộng ra thêm địa điểm và thành phố bằng config, không phải bằng code.

## Phạm vi

Trong: Đà Lạt; inventory Google Maps là **nguồn địa điểm** (địa điểm du lịch: tham quan, ăn uống, hoạt động, mua sắm, dịch vụ cho du khách); review Google Maps là bằng chứng trải nghiệm hiện tại; TikTok (bằng chứng trải nghiệm từ video / comment) **tạm ngoài phạm vi** — code và dữ liệu đã crawl giữ nguyên, quay lại sau khi danh sách và review Maps xong; trích xuất media; entity resolution (POI / ZONE); observation; tổng hợp thành fact / signal / estimate; kiểm tra và định tuyến theo rủi ro; duyệt cuối; serving index; refresh; resolve theo yêu cầu khi người dùng nhập một địa điểm.

Ngoài: mọi dữ liệu người dùng (corpus không lưu và không coi input người dùng là bằng chứng về địa điểm); độ phù hợp của gợi ý (thuộc online); live context (thời tiết, giao thông, thời gian di chuyển); chỗ ở (không gợi ý; chỗ ở người dùng nhập được tra theo yêu cầu, `docs/ARCHITECTURE.md` §9.1 — danh sách khách sạn của Maps bỏ qua khung bản đồ nên cũng không lấy hết được); phủ toàn quốc.

## Nguyên tắc

1. **Không bao giờ bịa entity.** Entity chỉ tồn tại sau khi resolve được về một thứ có thật.
2. **Không span, không observation.** Mọi observation trích nguồn và một span định vị (field + offset, hoặc segment + timestamp).
3. **Chưa biết thì giữ là chưa biết.** Thiếu bằng chứng là `unknown`, không bao giờ là `false` hay giá trị mặc định.
4. **Giữ xung đột.** Bất đồng cho ra `uncertain` và giữ lại xung đột.
5. **Model trích xuất; code quyết định.** Fact, signal, estimate chỉ do rule tổng hợp ghi. Không model nào ghi chúng.
6. **Cùng được nhắc không có nghĩa là ở gần nhau.** Xuất hiện trong một video không bao giờ là bằng chứng về khoảng cách.
7. **Vai trò nguồn tách biệt.** Google Maps quyết định tập địa điểm; nguồn khác chỉ thêm bằng chứng cho địa điểm có trong tập. Review Maps (và TikTok khi quay lại phạm vi) mô tả trải nghiệm và môi trường; fact vận hành đến từ trang official và Google.
8. **Build không bao giờ chờ người.** Việc agent không giải quyết được sẽ kết thúc ở `UNRESOLVED` hoặc không được phục vụ, kèm lý do, và đi vào review.

## Vai trò model

Spec ràng buộc **vai trò**, không ràng buộc model. Mỗi vai trò là một adapter có kiểu với output được validate theo schema; model nào đảm nhận là config, chọn theo **chất lượng trên nhãn review, sau đó đến chi phí trên mỗi entity được phục vụ**. Đổi model của một vai trò là đổi config, và phải qua bộ regression (§Đo chất lượng).

| Vai trò | Làm gì | Yêu cầu |
|---|---|---|
| **Code** | Chuẩn hóa, dedup, rule lọc spam, chấm điểm match, tổng hợp, gate, định tuyến rủi ro | Tất định, có test |
| **ASR** | Âm thanh → transcript có timestamp | Tiếng Việt, có timestamp |
| **Extractor** | Mọi việc model khối lượng lớn: `visible_text` + `visual_summary` của keyframe, mention, observation có span, độ liên quan / đối tượng / stance của comment, nhận định từ trang official, kiểm tra span, đề xuất hành động trong vòng lặp tự động (§Vòng lặp tự động) | Nhận ảnh, output có cấu trúc, throughput cao, chi phí thấp hoặc bằng 0; mỗi call vừa một đơn vị tự nhiên (một video, một lô comment, một đoạn trang) |
| **Judge** | Chốt chặn trước người: chọn trong các phương án match `AMBIGUOUS`; audit hồ sơ entity rủi ro cao; ánh xạ `proposed_feature` vào feature có sẵn; đề xuất biến thể prompt / ngưỡng khi hiệu chỉnh | Khả năng suy luận mạnh nhất có được; ưu tiên **khác họ model với Extractor** để lỗi độc lập (hiện dùng chung, xem `docs/LLM_PROVIDER.md`); số call thấp |

Model đang đảm nhận từng vai trò và cách kết nối: `docs/LLM_PROVIDER.md`.

Chỉ thêm vai trò hoặc model thứ hai khi nhãn review cho thấy một bước mà các vai trò hiện tại làm chưa đủ tốt.

## Pipeline

```text
 DISCOVER ──► EXTRACT ──► RESOLVE ──► OBSERVE ──► AGGREGATE ──► CHECK & ROUTE ──► PUBLISH
 Google Maps  ASR          code +      Extractor   code          gate · rule rủi ro  serving index
 (TikTok:     Extractor    Judge nếu               fact/signal/   Judge audit         │
  tạm ngoài)
              mention      mơ hồ                   estimate                         ▼
                                                                          HÀNG ĐỢI REVIEW (người)
 mọi bước: ledger (input hash × processor version) → chỉ việc đã đổi mới chạy lại
```

### 1. Discover

- **Nội dung (TikTok) — tạm ngoài phạm vi; mô tả code đã có:** nhóm query (chung, category, trải nghiệm, đối tượng, ràng buộc, xu hướng) → thu video mới, caption, hashtag, toàn bộ comment kèm reply (trần tùy chọn `max_comments_per_video`). Search TikTok bằng Playwright với profile đã đăng nhập (bắt JSON API search); video tải từ `playAddr`; comment và reply bắt JSON API comment / reply (mở hết nút "Xem … câu trả lời"). Extractor đọc caption + hashtag của lô mới và đề xuất query mới (xu hướng, tên chỗ mới); code bỏ query trùng. Ngừng mở rộng một nhóm khi số ứng viên mới mỗi lô xuống dưới ngưỡng.
- **Phase 1 — danh sách địa điểm (output hiện tại):** `gmaps search` → `gmaps filter` → `gmaps counts` → `gmaps list`. Mỗi category (`config/queries.yaml`, không có loại chỗ ở) search trên lưới ô tới `grid.max_zoom` = 14 (quét nông có chủ đích: đủ ứng viên, thời gian có giới hạn). `list` bỏ ngoài `area`, bỏ chỗ ở (ô danh sách khách sạn `lodging` và category khớp khách sạn / nhà nghỉ / homestay / resort / villa / căn hộ…; một FID từng mang category chỗ ở ở bất kỳ lần thấy nào là chỗ ở: Maps xếp khách sạn có nhà hàng vào cả hai), chấm `score` = trung bình Bayes `(v·R + m·C) / (v + m)` (R rating, v số review, C rating trung bình của category, m trung vị số review của category: ít review không vượt được nhiều review), chỉ xếp nơi `filter` giữ, gộp bản trùng (cùng tên sau khi bỏ dấu, hoa thường, dấu câu, tên thành phố, cách nhau ≤ `same_name_m` = 1000 m, khác FID: giữ bản nhiều review nhất; chỉ gần nhau mà khác tên thì không gộp vì nhiều quán chung một tòa nhà; cùng tên xa hơn là chi nhánh khác); mỗi FID lấy lần thấy có nhiều review nhất; Maps khi không đăng nhập đôi khi chỉ hiện "4,6 sao" không kèm "(124)" trên thẻ và không bao giờ hiện số trên trang chi tiết, nên `counts` mở trang chi tiết bằng profile đã đăng nhập cho mọi nơi `filter` giữ có rating mà không lần thấy nào có số review, ghi `counts/<city>.json`, `list` lấy số đó thay số trên thẻ; bỏ nơi dưới `min_reviews` = 50 review hoặc không có rating — ngưỡng chất lượng duy nhất, không cắt theo rating hay `score`, không giới hạn số nơi mỗi category (`top_per_category` bỏ trống; đặt số thì giữ chừng đó nơi `score` cao nhất mỗi category); `score` chỉ để xếp thứ tự. Output là tên + định danh, chưa crawl chi tiết / review. Maps không có sắp xếp theo rating nên phải quét lấy ứng viên rồi tự xếp.
- **Phase 2 — tìm chuyên sâu từng địa điểm** (sau phase 1): `gmaps crawl` (chi tiết, giờ, review) + `qc` trên danh sách phase 1; TikTok quay lại phạm vi ở đây như nguồn bằng chứng: mỗi nơi trong list Maps → `tiktok place_search` (search `<tên> <thành phố>`, bỏ tên thành phố nếu tên đã có; giữ `videos_per_place` video đầu theo thứ tự TikTok) → `tiktok place_filter` (Extractor, `PLACE_VIDEO_FILTER`: caption + hashtag có nói về **đúng** nơi này không, kèm tên / category / địa chỉ Maps; `no` cho nơi trùng tên, chi nhánh khác, chủ đề khác, chỉ nói về thành phố) → `tiktok place_crawl` (chỉ `yes`: comment + mp4, cùng file với `crawl`) → `tiktok asr` (vai trò ASR: ffmpeg 16 kHz mono, Silero VAD bỏ đoạn không có tiếng người (đệm 0,2 s, gộp đoạn cách < 1 s), chép lời từng đoạn, timestamp theo video) → `tiktok asr_check` (Extractor, `ASR_CHECK`: mỗi segment `ok | fixed | garbled | lyrics`, gợi ý tên từ place đã map; bản `fixed` giữ < 50% từ ASR bị code coi là viết lại → `garbled`; giữ text ASR thô) → `tiktok place_verify` (Extractor, `PLACE_VIDEO_VERIFY`: caption + hashtag + transcript đã kiểm + 4 keyframe → video có nói / cho thấy đúng nơi đã map không, kèm bằng chứng; chỉ `yes` là bằng chứng).
- **Inventory (Google Maps):** cào Google Maps (mỗi category trên lưới ô bản đồ phủ `area`) bằng Playwright, không ngưỡng rating (search: không đăng nhập, mỗi ô một context mới không cookie vì Google giới hạn theo phiên và danh sách khi chưa đăng nhập vẫn đủ; crawl chi tiết + review: profile đã đăng nhập); FID Maps làm id ứng viên; chi tiết + review + giờ cao điểm lưu file. Đây là tập địa điểm của corpus: ưu tiên tìm đủ danh sách (search mọi category trước), rồi mới crawl chi tiết + review.
- Thành phố là **config** (`config/cities.yaml`): tên ghép vào query TikTok, và khung `area` [lat_min, lng_min, lat_max, lng_max]. Chỉ địa điểm Google nằm trong `area` thuộc thành phố (Maps trả cả địa điểm trùng tên ở tỉnh khác).
- **Mỗi nguồn chạy theo phase độc lập**, mỗi phase một module (`src/corpus/crawl/<source>/<phase>.py`, hàm `run`), chỉ đọc file của phase trước, ghi vào thư mục riêng của phase: `search` (chỉ tìm, lưu kết quả thô) → `list` (gộp, bỏ trùng, không mở trình duyệt) → `filter` (TikTok: Extractor đọc caption + hashtag, trả `yes | no | unsure`; `crawl` chỉ mở video `yes` / `unsure`, chỉ `no` khi caption rõ ràng là chủ đề khác. Maps: chạy trước `list`, Extractor đọc tên + category Maps của mỗi FID khác nhau trong search (trong `area`, không chỗ ở), `no` chỉ khi rõ ràng không dành cho du khách: công ty, cửa hàng gia dụng, bãi xe, cứu hộ…; `list` chỉ xếp `yes` / `unsure`) → `crawl` (mở từng mục trong list) → `qc` (Maps: luật + vai trò Judge). Prompt, schema và thiết lập của mọi task model nằm ở `src/corpus/llm/` (`roles.py`: `Role`; `tasks.py`: `Task`); kết quả lưu `prompt_hash`, đổi prompt thì task chạy lại. Maps `search`: mỗi category × ô bản đồ phủ `area`; cuộn danh sách tới dòng "Bạn đã xem hết danh sách này"; ô đạt `full_at` kết quả hoặc không cuộn tới dòng đó (`end = false`) thì chia 4 ô zoom sâu hơn; `list` bỏ trùng FID và bỏ ngoài `area`. TikTok `crawl` đọc item JSON mới trên trang video (stats và `playAddr` còn hạn). Chạy `python -m corpus <source> <phase|all> --city <key>`.

#### Dữ liệu thô

Code: `src/corpus/crawl/<source>/` (phase như trên), phần dùng chung không theo nguồn ở `src/corpus/crawl/common/`; query và trần số lượng ở `config/queries.yaml`. Gốc `DATA_DIR` (`.env`, mặc định `data/`, gitignored); profile trình duyệt ở `.browser/<source>/` (gitignored).

```text
data/
  tiktok/
    search/<city>/<query_slug>.jsonl     {at, group, query, items:[{video_id, url, author_id, desc, created_at, hashtags, photo}]};
                                         query đã có file thì không search lại
    list/<city>.json                     {at, stats:{raw, duplicates, videos}, items:[{…, queries[]}]}; dựng lại từ search
    filter/<video_id>.json, summary.json {video_id, desc, checked_at, model, prompt_hash, llm:{relevance, reason}}; chấm lại
                                         khi caption hoặc prompt đổi; summary.dropped = video bị loại kèm lý do
    videos/<video_id>/
      info.json                          item JSON thô của trang video (đủ mọi field)
      video.json                         bản đọc được: {video_id, video_url, video_path (tương đối DATA_DIR), caption, hashtags,
                                         author_id, created_at, stats, queries, fetched_at, comments_complete, comments:[{comment_id,
                                         author_hash, text, created_at, likes, reply_count, replies:[…]}]}; reply mất comment cha nằm ở
                                         comments kèm reply_to; reply_count = số reply TikTok báo;
                                         transcript (phase asr + asr_check): {model, vad_model, at, total_s, speech_s, text,
                                         segments:[{start_s, end_s, text (ASR thô), checked_text, status: ok|fixed|garbled|lyrics}],
                                         check:{model, prompt_hash, quality: good|partial|unusable|no_speech, transcript_at, at}};
                                         places (phase place_verify): [{fid, name, verdict: yes|no|unsure, evidence:[{source, quote}],
                                         reason, model, prompt_hash, transcript_at, checked_at}]; chỉ `yes` là bằng chứng cho nơi đó
      frames/f1..f4.jpg                  keyframe cho place_verify (rộng 512 px)
      video.mp4                          ghi cuối cùng = video đã xong
    place_search/<city>/<fid_dir>.json   {at, fid, name, category, query, items:[…như search]}; chỉ ghi khi TikTok báo hết danh sách
                                         hoặc đủ `videos_per_place`; nơi đã có file không search lại
    place_filter/<fid_dir>.json          {fid, name, category, address, query, checked_at, model, prompt_hash, videos:[{video_id, url,
                                         desc, hashtags, llm:{relevance, reason}}]}; chấm lại khi caption / địa chỉ / prompt đổi;
                                         liên kết nơi ↔ video nằm ở đây; summary.json
    errors.jsonl                         {at, id, stage, error}
  gmaps/
    search/<city>/<category_slug>.jsonl  append mỗi ô: {at, query, tile:[lat, lng, zoom], end, lodging, items:[{fid, name, url,
                                         category, rating, reviews, lat, lng}]}; chỉ chỗ trong area (Maps lấp danh sách ngắn bằng chỗ ở thành phố khác: bỏ); còn thô: trùng giữa các ô, chỗ ở, chỗ không liên quan; ô đã có
                                         (đủ end + rating) không tìm lại; dòng định dạng cũ bị bỏ qua
    filter/<fid_dir>.json, summary.json  {fid, name, category, url, checked_at, model, prompt_hash, llm:{relevance, reason}};
                                         chấm lại khi đổi tên / category / prompt; lỗi model → không có file (chấm lần sau)
    counts/<city>.json                   {at, items:{fid:{rating, reviews, at}}}; chỉ nơi thẻ search thiếu số review; nơi đã có không mở lại;
                                         trang không có số (phiên hết hạn) → dừng `LoginRequired`, không ghi
    list/<city>.json                     output phase 1: {at, stats:{raw, outside_area, lodging, duplicates, candidates, not_kept,
                                         same_place, few_reviews, places},
                                         items:[{fid, name, url, lat, lng, category, rating, reviews, score, queries[]}]}; score cao
                                         trước; queries = category mà nơi này lọt top; dựng lại toàn bộ từ search mỗi lần
    places/<fid_dir>/                    fid_dir = FID với ":" đổi thành "_" (Windows)
      reviews.json                       [{review_id, author_hash, author_meta, rating, text, details[], published_text, likes,
                                         photos}]; không lấy phản hồi của chủ (không phải bằng chứng); mới nhất
                                         trước; mọi review dưới 1 năm, không trần số lượng (`max_reviews_per_place` null; `max_review_age_months` 11: Maps ghi "một năm trước" cho 12–23 tháng; `min_reviews_per_place` 0)
      place.json                         fid, name, url, lat, lng, category, address, phone, website, description,
                                         hours[], status, attributes[], popular_times[], rating, review_count,
                                         rating_histogram[], price, plus_code, tickets, queries[], reviews_complete, fetched_at;
                                         ghi cuối cùng = place đã xong
    qc/<fid_dir>.json, qc/summary.json   {fid, name, fetched_at, checked_at, model, checks[], llm:{tourism_relevant, in_city,
                                         category_ok, bad_reviews[], field_issues[], verdict}}; chấm lại khi fetched_at đổi
    errors.jsonl
  review/decisions.jsonl                 {at, kind, id, decision, note}; append, quyết định mới nhất của mỗi mục thắng
```

- **Review lúc crawl** (`python -m corpus review`, trang cục bộ `127.0.0.1:8765`, code `src/corpus/review/`): hàng đợi dựng lại từ file mỗi lần mở, chỉ gồm mục cần người: `video_filter`, `place_filter` (`no` / `unsure`: giữ / bỏ), `video_comments` (`comments_complete` false hoặc thiếu: crawl lại / chấp nhận), `place_qc` (qc khác `ok`, không cho du khách, ngoài thành phố, lỗi model: chấp nhận / loại), `place_reviews` (`reviews_complete` false: crawl lại / chấp nhận). Quyết định là nhãn, không sửa giá trị đã crawl; `filter` (TikTok) và `list` (Maps) áp giữ / bỏ của người lên kết quả model, `crawl` lấy lại mục có `retry` mới hơn `fetched_at`.

- `.jsonl` chỉ append; file khác ghi `*.tmp` rồi `os.replace` (atomic). Không bước nào xóa file.
- Mục có file đánh dấu xong → bỏ qua; thiếu → lần chạy sau tải lại cả mục. Lỗi một mục → `errors.jsonl`, đi tiếp.
- Text Maps (`hours`, `status`, `attributes`, `popular_times`, `rating_histogram`, `price`, `tickets`, `author_meta`, `details`, `published_text`) giữ nguyên văn. Không lưu tên người comment / review: `author_hash` = sha256(id)[:16].
- Crawl thật chạy `--headed`: Maps headless trả trang thiếu (không review, không giờ cao điểm).
- **Rời trang theo tín hiệu kết thúc, không theo timeout.** TikTok: `comments_complete` = API comment trả `has_more=0`, mỗi comment có reply thì API reply của nó trả `has_more=0` (hoặc đủ `reply_count`), và không còn request API đang chờ; reply bị TikTok ẩn vẫn kết thúc danh sách với ít dòng hơn. Maps review (chưa xong thì thử lại, lần cuối lưu kèm cờ): dừng khi đủ `max_reviews_per_place`, đủ `review_count`, quá `max_review_age_months`, hoặc Maps làm rỗng ô loader cuối khung review (`reviews_complete`). Timeout (TikTok 10 vòng không có gì mới, Maps 15 s) chỉ là lưới an toàn và cho `…_complete = false`; TikTok chưa xong thì thử lại, lần cuối vẫn lưu kèm cờ và ghi `errors.jsonl`.
- **Bị chặn / đăng xuất:** TikTok chặn API comment bằng body rỗng (không captcha) → dừng trang ngay, nghỉ `cooldown_s` rồi thử lại. Google có thể kết thúc phiên mà vẫn giữ cookie `SID`; Maps khi đó trả ít kết quả hơn (vẫn có dòng hết danh sách) và không có review → trang nào có link đăng nhập (`accounts.google.com/ServiceLogin`) thì dừng với `LoginRequired`, không lưu.
- Review Maps có hai layout: thường (`aria-label` "… sao", ngày ở `.rsqaWe`) và lưu trú (khách sạn, homestay: điểm "4/5", ngày "… trước trên Google"); cả hai đều đọc được. Chữ icon-font (vùng Unicode riêng) bị bỏ khỏi `address` và `hours`.
- Gặp captcha: chạy `--headed` thì chờ người giải trong cửa sổ (tối đa 5 phút), headless thì dừng. Chưa đăng nhập hoặc hết thời gian chờ → dừng, báo chạy `python -m corpus login <source>`. Không tự động giải captcha. TikTok xử lý video song song, số tab tự dò trong khoảng 1..`tabs` (giảm nửa và nghỉ khi bị chặn; mức đạt lưu ở `tiktok/throttle.json`), mp4 tải ngoài tab; Maps cũng vậy cho place (mức đạt ở `gmaps/throttle.json`) và search (mức đạt ở `gmaps/search_throttle.json`; danh sách bị cắt ngang = bị chặn mềm). Nghỉ ngẫu nhiên `pause_s` giây giữa các mục (`config/queries.yaml`).

### 2. Extract (theo video)

Tải video → segment (theo cảnh + khoảng lặng ASR) → transcript ASR → 1–2 keyframe mỗi segment → Extractor trả `visible_text` (nguyên văn) + `visual_summary`. Giữ file video (để xem lại nội dung), transcript, segment, keyframe nhỏ, URL embed.

Sau đó Extractor đọc caption + transcript + visible text và trả các mention địa điểm, mỗi mention có span, loại đề xuất (`POI` cho một cơ sở có tên, `ZONE` cho khu vực / con đường / cảnh quan hoạt động), và mọi quan hệ không gian được **nói rõ** trong văn bản ("ngay cạnh", "cách 2 km").

### 3. Resolve

Tập đích là inventory Maps (§1). Mention từ nguồn khác (người dùng nhập; TikTok khi quay lại phạm vi) chỉ match vào tập này hoặc tra thêm một địa điểm Maps theo tên; không có Place ID thì không có entity.

```text
mention → chuẩn hóa (bỏ quán/tiệm/cafe…, giữ dạng có dấu + không dấu làm alias)
  → Google Text Search "<tên> <tên thành phố>" → code chấm điểm:
      độ giống tên/alias · khớp category · quan hệ được nói rõ
  điểm ≥ T và cách biệt ≥ M      → POI (RESOLVED)
  có ứng viên nhưng chưa rõ      → AMBIGUOUS → Judge chọn một phương án có sẵn hoặc bỏ phiếu trắng
                                  (lựa chọn của Judge vẫn phải qua ngưỡng sàn T_min)
  khu vực / con đường / cảnh quan → ZONE (hình học = buffer / hành lang quanh các POI liên quan, code tính)
  còn lại                        → UNRESOLVED (giữ lại, không phục vụ, liệt kê trong review)
```

- `entity_id` là vĩnh viễn; Google Place ID là `ExternalIdentifier` có lịch sử, làm mới mỗi 12 tháng.
- Gắn nguồn với entity ở mức segment khi mention có timestamp; mức video khi video chỉ nói về một entity; nếu không thì gắn video với từng entity nhưng không gán comment nào cho riêng một entity.
- **Theo yêu cầu (online):** tên người dùng nhập chạy qua cùng bộ matcher. Chắc chắn → trả entity và chạy vòng lấp khoảng trống coverage cho entity đó (§Vòng lặp tự động). Không chắc → người dùng tự chọn. Những gì người dùng gõ không bao giờ là bằng chứng.

### 4. Observe

Mọi nguồn thành `Observation`; không gì ghi thẳng vào entity.

- **Segment** (Extractor): feature id + value + span + context.
- **Comment:** rule bỏ comment chỉ có emoji / trùng lặp → Extractor, mỗi call một lô comment của một video, trả cho từng comment: có liên quan không, entity đích (chọn trong các entity đã gắn với video, hoặc không có), feature + value + stance + context, với chính comment làm span. Tên địa điểm mới tìm thấy trong comment quay lại bước Resolve.
- **Review Google Maps** (bản demo, xem §Sai lệch): xử lý như comment — rule bỏ review rỗng / trùng → Extractor, mỗi call một lô review của một địa điểm, trả cho từng review: có liên quan không, feature + value + stance + context, span = review (tham chiếu vào provider store, không chép sang entity). Review cũ hơn `max_review_age_months` không được crawl.
- **Trang official:** website lấy từ bản ghi Google = `verified`; không có thì chạy vòng tìm trang official (§Vòng lặp tự động), trang tìm được và code khớp tên + địa chỉ = `probable`; còn lại không dùng. Chỉ tải các loại trang trong whitelist (about, giờ, giá, vé, đặt chỗ, quy định, tin tức, liên hệ). Extractor trích nhận định `fact_key` kèm span.
- **Context** trên mọi observation: `time_of_day`, `day_type`, `weather` (theo lời nguồn, không bao giờ là thời tiết thực tế), mỗi cái là enum hoặc `unknown`. "7h sáng hôm đó đông lắm" → `crowd = high`, `time_of_day = morning`, không phải `crowd = high` cho địa điểm.
- Feature id ngoài ontology được ghi là `proposed_feature`; build vẫn tiếp tục. Judge ánh xạ nó vào một feature id có sẵn (đồng nghĩa) hoặc gom vào nhóm đề xuất mới; code kiểm id có trong ontology. Chỉ nhóm đề xuất mới có ≥ 3 nguồn độc lập mới vào review; ontology chỉ người sửa.

### 5. Aggregate (chỉ code)

| Loại | Ví dụ | Rule |
|---|---|---|
| **Fact** | giờ, giá, đặt chỗ, quy định vào cửa | Ưu tiên: official verified > official probable > provider store. Đồng thuận → giá trị; bất đồng → `uncertain` + xung đột |
| **Signal** | độ đông theo bối cảnh, yên tĩnh/sôi động, view, đường dốc | Phân phối trong một nhóm bối cảnh; mẫu số = observation liên quan đến feature đó |
| **Estimate** | thời gian tham quan (min / typical / long) | Luôn hiển thị là khoảng, không bao giờ là fact |

**Confidence** lưu bốn thành phần (không có một số ẩn duy nhất):

```text
independent_sources   số creator / tác giả khác nhau (nhiều video của một creator = 1)
agreement             tỷ lệ observation đồng ý
freshness             tuổi so với cửa sổ của key (giờ 90 ngày, giá 180 ngày, độ đông 12 tháng)
source_type           official | provider | video | comment
```

**Coverage** theo khía cạnh (`identity`, `operation`, `experience`, `environment`, `effort`, `suitability`): `COMPLETE | PARTIAL | NONE`.

### 6. Kiểm tra và định tuyến

**Gate** (code; không model nào vượt qua được):

- Output đúng schema; span được trích tồn tại nguyên văn trong nguồn; timestamp nằm trong media.
- Feature id có trong ontology hiện tại.
- Match POI qua ngưỡng và cách biệt (hoặc `T_min` với lựa chọn của Judge).
- Hình học ZONE bao các POI liên quan.
- Fact / signal / estimate chỉ do rule tổng hợp ghi; nội dung Google chỉ nằm trong provider store (observation từ review Maps chỉ trỏ span vào đó).

**Kiểm tra span.** Với observation tác động cao (mọi `fact_key`, mọi feature `verify: always` — an toàn, tiếp cận, đối tượng phù hợp), một call Extractor riêng chỉ thấy span (± 1 câu / ± 5 s) và giá trị + bối cảnh được khẳng định, rồi trả lời `supports | contradicts | insufficient`. Khác `supports` → bỏ, kèm lý do.

**Định tuyến rủi ro** theo entity, sau mỗi lần build lại:

| Rủi ro | Điều kiện (code) | Hướng đi |
|---|---|---|
| Thấp | Qua mọi gate, không xung đột, không có giá trị `verify: always`, không do Judge chọn match, `independent_sources` ≥ 2 cho mọi signal được phục vụ | **Tự publish** |
| Cao | Có xung đột, match do Judge chọn, ZONE mới, có giá trị `verify: always`, có signal được phục vụ chỉ từ một nguồn, processor version đổi | **Judge audit** |

**Judge audit** nhận một hồ sơ gọn (≤ 8k token): bản ghi, với mỗi giá trị là các thành phần confidence và phân phối giá trị, 3 trích đoạn ủng hộ + 3 phản bác + 2 ngẫu nhiên, các xung đột được giữ, và tên các địa điểm lân cận. Judge trả `pass` hoặc finding (`unsupported | contradiction | wrong_link | stale`) kèm id bằng chứng. Judge không bao giờ sửa giá trị.

**Tự sửa theo finding** (code thực thi, tối đa một vòng mỗi entity):

```text
unsupported    → loại các observation Judge nêu id → tổng hợp lại
wrong_link     → gỡ EntityLink → resolve lại mention đó
stale          → tải lại nguồn quá hạn → observe lại
contradiction  → vòng lấp khoảng trống coverage cho đúng key đó
                 (fact_key: tìm trang official · signal: tìm thêm nguồn độc lập)
                 → có nguồn mới: tổng hợp lại, nguồn ưu tiên cao hơn thắng
                 → không có: phục vụ UNCERTAIN kèm mọi giá trị xung đột
→ Judge audit lại một lần, chỉ khi tập bằng chứng đã đổi
```

```text
Judge pass                                     → publish
finding sau khi đã tự sửa / bỏ phiếu trắng     → khía cạnh không được phục vụ → hàng đợi review
verify: always, giá trị cảnh báo              → Judge pass + independent_sources ≥ 2 → publish là UNCERTAIN;
                                                 thiếu điều kiện → hàng đợi review
verify: always, giá trị cho phép               → chỉ publish sau khi người Accept
```

Giá trị **cảnh báo** hạn chế lựa chọn ("đường dốc", "không hợp người lớn tuổi"): sai chỉ làm mất một gợi ý. Giá trị **cho phép** mở rộng lựa chọn ("hợp người lớn tuổi", "an toàn cho trẻ em"): sai có thể gây hại. Ontology khai báo giá trị nào là cảnh báo (`caution_values`); code phân loại, không model nào quyết định.

Audit chỉ chạy lại khi fingerprint của hồ sơ (bản ghi + tập bằng chứng + version rule) thay đổi.

### 7. Publish và review

**Serving record** (do `online/retrieval` đọc): entity id, loại, hình học, category; trường lọc được (giá, giờ, effort, trong nhà/ngoài trời, khoảng thời gian tham quan); feature kèm tham chiếu bằng chứng; thành phần confidence; coverage và trạng thái theo khía cạnh; `usable_as` (`experience | meal | anchor | backup`, tính từ category + coverage — nhà hàng chỉ có từ inventory là `meal/anchor/backup`, không phải `experience`).

**Trạng thái:** bộ chung cho corpus, Admin Web, User Web — `docs/CORPUS.md` §6. `NEEDS_REVIEW` và `DISABLED` không bao giờ được phục vụ.

**Hàng đợi review** (bước duy nhất có người, sau mỗi build):

- Nội dung: mục `NEEDS_REVIEW`, giá trị `verify: always` dạng cho phép (và dạng cảnh báo chưa đủ điều kiện tự publish), ứng viên `UNRESOLVED`, nhóm `proposed_feature` mới đủ nguồn, và một **mẫu ngẫu nhiên ẩn (~5%)** các giá trị đã tự publish, đã qua Judge, và các quyết định tự động của Judge (ánh xạ feature, tự sửa), lấy riêng theo từng loại, không đánh dấu.
- Sắp theo rủi ro × lưu lượng (địa điểm planner hiển thị nhiều nhất lên trước).
- Với mỗi mục, người duyệt thấy giá trị, thành phần confidence, bằng chứng (embed segment, comment, trích đoạn official), và finding của Judge. Thao tác: **Accept · Disable · Report error** (trên một giá trị, liên kết, hoặc loại). Không sửa tự do giá trị.
- Mỗi quyết định được lưu thành nhãn. Nhãn tạo thành bộ regression mà prompt hoặc model mới phải qua trước khi output của nó được tự publish, và là input của vòng hiệu chỉnh (§Vòng lặp tự động).

### 8. Refresh

Ledger `PipelineArtifact`: `source_id, stage, input_hash, processor, processor_version, prompt_hash, ontology_version, status, usage (tokens, cost, latency)`. Một bước chỉ chạy lại khi input hoặc processor của nó đổi; đổi ontology thì chạy lại từ observation trở xuống, không chạy lại ASR.

Job định kỳ: làm mới provider store; làm mới Google ID (12 tháng); tải lại nguồn quá hạn; query xu hướng; quét inventory tìm chỗ mới mở. Observation mới được thêm, cũ được giữ; entity bị ảnh hưởng được tổng hợp lại, định tuyến lại, và publish lại.

## Vòng lặp tự động

Mọi vòng lặp dùng một khuôn: **code giữ vòng lặp, số bước tối đa, ngân sách, và điều kiện dừng; model chỉ đề xuất hành động trong một tập đóng, output được validate; code thực thi qua adapter và gate.** Không vòng nào ghi fact / signal / estimate hay tạo entity không có Place ID.

```text
while not stop(state) and budget and steps < N:
    action = model.propose(state, allowed_actions)
    state  = update(state, code.execute(action))
```

| Vòng | Model | Hành động được phép | Dừng khi |
|---|---|---|---|
| **Mở rộng query** (§1, TikTok — tạm ngoài phạm vi) | Extractor | đề xuất query TikTok mới từ caption + hashtag | số ứng viên mới mỗi lô < ngưỡng |
| **Tìm trang official** (§4) | Extractor | search web, chọn link, tải trang, đi theo link nội bộ thuộc whitelist | đủ loại trang whitelist, hoặc 5 trang |
| **Lấp khoảng trống coverage** | Extractor | lấy thêm review Maps (cũ hơn / sắp theo liên quan), tìm trang official (TikTok `"<tên> <khía cạnh>"` khi quay lại phạm vi) | coverage khía cạnh tăng, hoặc 3 bước |
| **Làm giàu theo yêu cầu** (§3) | Extractor | như lấp khoảng trống coverage, cho entity người dùng vừa nhập | như trên |
| **Hiệu chỉnh** (ngoài build) | Judge | sinh biến thể prompt / ngưỡng → chạy bộ regression | không biến thể nào tốt hơn, hoặc N lượt |

Lấp khoảng trống coverage chạy sau Aggregate cho entity có khía cạnh `PARTIAL | NONE`, ưu tiên theo lưu lượng, và cho key bị Judge báo `contradiction` (§6). Hiệu chỉnh chỉ nhận biến thể khi precision trên bộ regression ≥ bản hiện tại và chi phí ≤ bản hiện tại; bản được nhận vẫn đổi `prompt_hash` / version nên ledger chạy lại phần bị ảnh hưởng.

## Data model

```text
Feature            id, group (experience|environment|effort|suitability), value_type,
                   contexts[], verify (always|sampled), caution_values[], labels_vi/en + synonyms   — có version
TikTokVideo        video_id, url, embed_url, author_id, caption, hashtags, published_at, video_ref
VideoSegment       segment_id, video_id, start_s, end_s, transcript, visible_text, visual_summary, keyframe_ref
Comment            comment_id, video_id, parent_id, author_id, text, published_at
OfficialPage       page_id, url, page_type, official_status, fetched_at, text
ProviderPlace      external_id, payload, fetched_at, next_refresh_at        (provider store)
Mention            mention_id, raw_name, proposed_type, span, relations[]
Candidate          candidate_id, normalized_name, mention_ids[], origin (tiktok|inventory|user),
                   status (RESOLVED|AMBIGUOUS|UNRESOLVED), options[] (id, name, score), chosen_id?, judge_picked
Entity             entity_id, type (POI|ZONE), name, aliases[], category, city, geometry?, state
ExternalIdentifier entity_id, provider, external_id, status (active|replaced), last_verified_at
EntityLink         link_id, target (video|segment|comment|page), target_id, entity_id, match_score
Observation        id, entity_id, feature|fact_key, value, stance, context, source_type,
                   source_id, span, extractor+version, support_score?
Fact|Signal|Estimate  entity_id, key, value|distribution|range, conflict?, confidence{4}, observation_ids[],
                   processor (gate chỉ nhận rule tổng hợp)
PlaceIntelligence  entity_id, identity, operation, experience, environment, effort, suitability,
                   coverage{}, state{}, build_version
ReviewDecision     target, decision (accept|disable|report_error), note, reviewer, at
```

Corpus và User Profile dùng chung **feature id**, không dùng chung bản ghi: corpus lưu `forest_view: present, confidence{…}`; profile lưu `forest_view: affinity, importance`.

Lưu trữ: PostgreSQL + PostGIS + pgvector (embedding segment chỉ để rerank tùy chọn; ánh xạ entity → feature → bằng chứng mới là xương sống).

## Kiểm soát chi phí và hiệu năng

- **Rule trước model.** Spam, trùng lặp, chuẩn hóa, chấm điểm, tổng hợp đều là code.
- **Chỉ hai vai trò model.** Extractor miễn phí hoặc rẻ cho mọi khối lượng; Judge chỉ cho entity rủi ro cao và match mơ hồ.
- **Không trả tiền hai lần.** Mọi call model được khóa theo input hash + processor + prompt hash; call lặp lại trả kết quả đã lưu.
- **Gom lô mục nhỏ** (comment, kiểm tra span) theo số lượng; một video mỗi call Extractor; trang dài chia theo heading; input quá cỡ được chia nhỏ, không bao giờ bị cắt ngầm.
- **I/O gọn.** Id, enum, offset; `pass` là câu trả lời gần như rỗng; prefix prompt ổn định đặt trước để provider cache được.
- **Ngân sách mỗi build:** call Judge, call Google, bước của vòng lặp tự động. Hết ngân sách thì build dừng gọn và chạy tiếp ở lần sau; entity rủi ro cao chưa được audit giữ `NEEDS_REVIEW` (không bao giờ tự publish).
- Báo cáo mỗi build: chi phí và token theo model, **chi phí trên mỗi entity được phục vụ**, tỷ lệ tự publish, kích thước hàng đợi review.

## Đo chất lượng

Không có bộ benchmark gán nhãn tay từ đầu; nhãn đến từ review.

| Chỉ số | Nguồn |
|---|---|
| Precision của giá trị tự publish | Mẫu ngẫu nhiên ẩn trong review |
| Precision của giá trị qua Judge | Mẫu ngẫu nhiên ẩn trong review |
| Tỷ lệ Judge bắt lỗi | Tỷ lệ lỗi người xác nhận mà Judge đã đánh dấu |
| Tỷ lệ nhận định không có căn cứ | Phải bằng 0 — gate + test bất biến |
| Coverage | Theo khía cạnh; độ chồng lấn nội dung vs inventory theo category |
| Chi phí | Trên mỗi entity được phục vụ, theo model |

Nếu precision lấy mẫu của một bước rơi dưới ngưỡng, bước đó ngừng tự publish (entity của nó chuyển sang Judge) cho đến khi hiệu chỉnh lại.

**Test bất biến:** không observation nào thiếu span; không fact / signal / estimate nào thiếu observation hoặc do model ghi; xung đột không bao giờ bị làm phẳng; `unknown` không bao giờ thành `false`; nội dung Google chỉ nằm trong provider store; cùng được nhắc không bao giờ tạo quan hệ; `NEEDS_REVIEW` và `DISABLED` không bao giờ được phục vụ.

## Mở rộng

- Thành phố mới = thêm tên thành phố vào config; code không đổi.
- Mọi bước idempotent trên ledger, nên chạy song song theo video / theo entity và tiếp tục được sau lỗi.
- Công sức của người tăng theo **rủi ro và cỡ mẫu**, không theo số địa điểm.
- Đổi model là đổi adapter, phải qua bộ regression.

## Xử lý lỗi

Adapter retry có backoff; adapter TikTok giới hạn tốc độ và xoay session. Output trượt gate được thử lại một lần kèm lý do lỗi, sau đó bỏ kèm lý do (không bao giờ vá bằng cách đoán). Model không khả dụng thì các bước phụ thuộc tạm dừng; không bỏ qua mục nào. Bước lỗi để entry ledger ở `failed` cho lần chạy sau.

## Các phase

| Phase | Việc | Điều kiện xong |
|---|---|---|
| 0. Spike | Chạy model mặc định của mỗi vai trò (ASR, Extractor, Judge) trên video mẫu | Mỗi vai trò chạy trọn trên một mẫu |
| 1. Nền tảng | Ontology v0, schema, Postgres, ledger, adapter (ASR, Extractor, Judge, Google, TikTok), gate | Test fixture pass |
| 2. Discover + extract + resolve | Inventory Maps đủ danh sách (mọi category × lưới ô) + chi tiết + review + qc; matcher cho tên người dùng nhập, ZONE, API theo yêu cầu. TikTok (crawl, mở rộng query, media, mention) tạm ngoài phạm vi | Crawl lặp lại được; báo cáo độ đủ danh sách và precision resolve trên mẫu review |
| 3. Observe + aggregate | Observation từ segment / comment / official, tìm trang official, ánh xạ `proposed_feature`, kiểm tra span, fact / signal / estimate, coverage | Build lại từ observation cho kết quả như cũ; bất biến pass |
| 4. Route + publish + review | Định tuyến rủi ro, Judge audit + tự sửa theo finding, lấp khoảng trống coverage, làm giàu theo yêu cầu, hiệu chỉnh, serving index, hàng đợi review có mẫu ẩn, job refresh | Một lần build đầy đủ chạy không cần người; báo cáo precision mẫu review và chi phí mỗi entity |

## Sai lệch cho bản demo

| Sai lệch | Demo | Cách sửa khi thương mại |
|---|---|---|
| Nguồn Google | Cào Google Maps có đăng nhập; review Maps dùng làm bằng chứng | Places API theo điều khoản (review chỉ dùng trong phạm vi điều khoản cho phép) |
| Thu thập TikTok | Scraper Playwright có đăng nhập | Truy cập có license |
| Lưu trữ | Lưu file, chưa có DB | PostgreSQL như §Data model |
| Hình học ZONE | Buffer / hành lang quanh POI liên quan | Dữ liệu bản đồ |

## Đầu vào cần có

API key của các model đang cấu hình trong `.env`; tài khoản TikTok phụ và tài khoản Google phụ (đăng nhập bằng `python -m corpus login`); trần ngân sách hàng tháng cho Judge; một người duyệt.

