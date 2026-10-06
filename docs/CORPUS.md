# Corpus Place Intelligence

Kho tri thức về địa điểm, xây **offline**, độc lập với mọi chuyến đi; Place Decision và Planning chỉ đọc nó. Vị trí trong luồng: `docs/ARCHITECTURE.md` §3. Code: `src/corpus/`. CLI ở §CLI.

```text
SOURCE ──► OBSERVATION ──► FACT / SIGNAL / ESTIMATE ──► PLACE INTELLIGENCE ──► SERVING INDEX
(review,    (một nhận định   (rule tổng hợp từ           (theo địa điểm,         (thứ Place
 ảnh, video, + span + bối     nhiều observation)          theo khía cạnh)         Decision đọc)
 comment,    cảnh)
 trang, provider)
```

Agent xây từ đầu đến cuối. Gate tất định kiểm soát mọi lần ghi. Người chỉ duyệt một hàng đợi nhỏ, xếp theo rủi ro, ở cuối. Mọi giá trị được phục vụ đều truy về một span nguồn: không có span thì không có observation, không có observation thì không có giá trị. Corpus không lưu dữ liệu người dùng và không coi input hay hành vi của người dùng là bằng chứng về địa điểm.

## Mục tiêu

Xây **corpus Place Intelligence** offline cho planner đọc. Agent xây từ đầu đến cuối; gate tất định kiểm soát mọi lần ghi; người chỉ duyệt một hàng đợi nhỏ, xếp theo rủi ro, ở cuối. Mọi giá trị được phục vụ đều truy về bằng chứng.

Đích: kiến trúc nhỏ nhất mà **đúng** (không bịa địa điểm hay fact), **rẻ** (model miễn phí hoặc rẻ cho khối lượng lớn, model mạnh chỉ ở chỗ cần phán đoán), và cho **output chất lượng cao**, đồng thời mở rộng ra thêm địa điểm và thành phố bằng config, không phải bằng code.

## Phạm vi

Trong: Đà Lạt; inventory Google Maps là **nguồn địa điểm** (địa điểm du lịch: tham quan, ăn uống, hoạt động, mua sắm, dịch vụ cho du khách); review Google Maps là bằng chứng trải nghiệm hiện tại; TikTok là bằng chứng trải nghiệm cho **địa điểm đã có trong tập** (tìm theo từng nơi, `place_search` → `observe`); trích xuất media; entity resolution (POI / ZONE); observation; tổng hợp thành fact / signal / estimate; kiểm tra và định tuyến theo rủi ro; duyệt cuối; serving index; refresh; resolve theo yêu cầu khi người dùng nhập một địa điểm.

Ngoài: mọi dữ liệu người dùng (corpus không lưu và không coi input người dùng là bằng chứng về địa điểm); độ phù hợp của gợi ý (thuộc online); live context (thời tiết, giao thông, thời gian di chuyển); chỗ ở (Planning tra live theo từng request, `docs/PLANNING.md` §Chỗ ở (crawl live) — danh sách khách sạn của Maps bỏ qua khung bản đồ nên cũng không lấy hết được; `config/queries.yaml` không có category chỗ ở); phủ toàn quốc.

## Nguyên tắc

1. **Không bao giờ bịa entity.** Entity chỉ tồn tại sau khi resolve được về một thứ có thật.
2. **Không span, không observation.** Mọi observation trích nguồn và một span định vị (field + offset, hoặc segment + timestamp).
3. **Chưa biết thì giữ là chưa biết.** Thiếu bằng chứng là `unknown`, không bao giờ là `false` hay giá trị mặc định.
4. **Giữ xung đột.** Bất đồng cho ra `uncertain` và giữ lại xung đột.
5. **Model trích xuất; code quyết định.** Fact, signal, estimate chỉ do rule tổng hợp ghi. Không model nào ghi chúng.
6. **Cùng được nhắc không có nghĩa là ở gần nhau.** Xuất hiện trong một video không bao giờ là bằng chứng về khoảng cách.
7. **Vai trò nguồn tách biệt.** Google Maps quyết định tập địa điểm; nguồn khác chỉ thêm bằng chứng cho địa điểm có trong tập. Review Maps, ảnh Maps và TikTok mô tả trải nghiệm và môi trường; fact vận hành đến từ trang official và Google.
8. **Build không bao giờ chờ người.** Việc agent không giải quyết được sẽ kết thúc ở `UNRESOLVED` hoặc không được phục vụ, kèm lý do, và đi vào review.

## Nguồn và mỗi nguồn chứng minh điều gì

| Nguồn | Dùng cho | Không bao giờ dùng cho |
|---|---|---|
| Google Maps | **Tập địa điểm** (phase 1: top theo rating có trọng số số review mỗi category, không có chỗ ở); định danh, vị trí, loại, giờ, trạng thái, website; review và giờ cao điểm là bằng chứng trải nghiệm (xử lý như comment) | Rating dùng làm bằng chứng (chỉ dùng để xếp ứng viên phase 1) |
| Video TikTok | Trải nghiệm, môi trường, mức vận động cho địa điểm đã có | Tạo địa điểm mới; fact vận hành nếu chỉ có một mình nó |
| Comment TikTok | Tín hiệu trải nghiệm lặp lại (độ đông, yên tĩnh, đường đi) | Fact; hiển thị một comment đơn lẻ như sự thật |
| Website / trang chính thức | Giờ, giá, vé, đặt chỗ, quy định, đóng cửa tạm | — |

Video tải về được giữ lại để xem lại nội dung: corpus giữ file video, transcript, timestamp segment, keyframe nhỏ, và URL embed TikTok; bằng chứng phát qua embed tại timestamp của segment.

Dữ liệu thô của từng nguồn lưu file riêng theo nguồn (§1 Discover, Dữ liệu thô).

## Vai trò model

Spec ràng buộc **vai trò**, không ràng buộc model. Mỗi vai trò là một adapter có kiểu với output được validate theo schema; model nào đảm nhận là config, chọn theo **chất lượng trên nhãn review, sau đó đến chi phí trên mỗi entity được phục vụ**. Đổi model của một vai trò là đổi config, và phải qua bộ regression (§Đo chất lượng).

| Vai trò | Làm gì | Yêu cầu |
|---|---|---|
| **Code** | Chuẩn hóa, dedup, rule lọc spam, chấm điểm match, tổng hợp, gate, định tuyến rủi ro | Tất định, có test |
| **ASR** | Âm thanh → transcript có timestamp | Tiếng Việt, có timestamp |
| **Extractor** | Mọi việc model khối lượng lớn: `visible_text` + `visual_summary` của keyframe, mention, observation có span, độ liên quan / đối tượng / stance của comment, nhận định từ trang official, kiểm tra span, đề xuất hành động trong vòng lặp tự động (§Vòng lặp tự động) | Nhận ảnh, output có cấu trúc, throughput cao, chi phí thấp hoặc bằng 0; mỗi call vừa một đơn vị tự nhiên (một video, một lô comment, một đoạn trang) |
| **Judge** | Thay người duyệt (§6): gán nhãn từng nhận định của Extractor, phán nơi bị báo đóng cửa, phán hai mục Maps có phải một nơi; kiểm cấp địa điểm của `qc`. **Judge mạnh** cho giá trị cho phép và mọi quyết định đóng cửa / gộp nơi | Khả năng suy luận mạnh nhất có được, **khác họ model với Extractor** (GPT / Claude / Gemini so với Gemma, `docs/LLM_PROVIDER.md`) |

Model đang đảm nhận từng vai trò và cách kết nối: `docs/LLM_PROVIDER.md`.

Chỉ thêm vai trò hoặc model thứ hai khi nhãn review cho thấy một bước mà các vai trò hiện tại làm chưa đủ tốt.

## Pipeline

```text
DISCOVER     phase 1: category × lưới ô trên Google Maps → Extractor bỏ nơi không dành cho du khách
             → mọi nơi ≥ min_reviews, không có chỗ ở = tập địa điểm
   ↓
EXTRACT      tải video (giữ lại) → segment → ASR → chữ trên keyframe + mô tả hình ảnh
             → mention địa điểm có span, loại POI / ZONE, quan hệ không gian được nói rõ
   ↓
RESOLVE      chuẩn hóa tên → match với Google (query kèm tên thành phố)
             match rõ → POI · khu vực / con đường / cảnh quan → ZONE
             chưa rõ → Judge chọn một phương án có sẵn hoặc bỏ phiếu trắng · không có → UNRESOLVED
   ↓
OBSERVE      review + ảnh Google Maps · segment, comment TikTok · trang official
             → observation (feature | fact_key, value, context, span), một format chung cho mọi nguồn
   ↓
AGGREGATE    chỉ bằng rule → Fact · Signal · Estimate, kèm các thành phần confidence
   ↓
CHECK        gate → định tuyến theo rủi ro → Judge audit entity rủi ro cao
   ↓
PUBLISH      rủi ro thấp + Judge pass → serving index · phần còn lại → hàng đợi review
   ↓
REFRESH      ledger chỉ chạy lại input đã đổi; nguồn quá hạn được tải lại
```

Một địa điểm là **POI** (một điểm xác định được) hoặc **ZONE** (khu vực, con đường, hay cảnh quan trải nghiệm, ví dụ khu săn mây Cầu Đất). Zone nối với POI qua quan hệ, nên "khu này hợp săn mây" không bao giờ thành "nông trại này là chỗ săn mây". Xuất hiện trong cùng một video không bao giờ là bằng chứng hai nơi gần nhau.

Mọi bước đi qua ledger (input hash × processor version): chỉ việc đã đổi mới chạy lại.

## CLI

```
python -m corpus login <tiktok|gmaps> [--profile <tên>]     # đăng nhập tài khoản phụ, một lần mỗi máy
python -m corpus <gmaps|tiktok> <phase|all> [--city dalat] [--headed] [--limit N]
python -m corpus judge <dedup|status|audit|all> [--city dalat] [--limit N]  # Judge thay người duyệt (§6)
python -m corpus build     [--city dalat] [--every N] [--skip <bước>…]  # một lần build tăng dần (dưới đây)
python -m corpus aggregate [--city dalat]                   # observation -> data/intel/places/
python -m corpus serving   [--city dalat]                   # intel -> data/serving/places.json
python -m corpus review    [--port 8765]                    # trang review cho người duyệt
```

| Nguồn | Phase, theo thứ tự |
|---|---|
| `gmaps` | `search` → `filter` → `counts` → `list` (tập địa điểm) → `crawl` → `relevant` → `extremes` → `keywords` → `visit` → `qc` → `observe`; ảnh: `photos` → `photo_observe` |
| `official` | `pages` → `observe` |
| `tiktok` | theo địa điểm: `place_search` → `place_filter` → `place_crawl` → `asr` → `asr_check` → `asr_alt` → `asr_check` → `place_verify` → `observe`; theo query (ngoài phạm vi hiện tại, code vẫn chạy được): `search` → `list` → `filter` → `crawl` → `comments_crawl` |

`all` chạy mọi phase của nguồn đó theo thứ tự khai báo. `--headed` mở cửa sổ trình duyệt để tự giải captcha. `--limit N` chỉ cho `observe` / `photos` / `photo_observe`. `--profile` và `--shard i/n` cho tài khoản TikTok thứ hai trên `place_search` / `place_crawl` / `comments_crawl`.

Phase cần Extractor (`observe`, `asr_check`, `place_verify`, `photo_observe`, `qc`) cần mạng UIT; `judge` và phần kiểm địa điểm của `qc` cần 9router — xem `docs/LLM_PROVIDER.md`. Thứ tự một lần build: observe → `judge all` → `aggregate` → `serving`; `build` chạy đúng chuỗi đó (`src/corpus/build.py`): `gmaps qc` → `gmaps observe` → `gmaps photo_observe` → `tiktok observe` → `official observe` → `judge dedup` → `judge status` → `judge audit` → `aggregate` → `serving`. Mỗi bước bỏ qua phần input không đổi (qc, observe theo input hash; Judge bỏ nhận định đã có nhãn, cặp / nơi đã quyết), nên build sau một đợt crawl chỉ đọc, chấm và tổng hợp phần mới. Bước lỗi (mạng, quota) được báo, build đi tiếp với file đang có; lần build sau làm nốt. `--every N` lặp lại mỗi N phút khi crawl còn chạy; `--skip tiktok` / `--skip "gmaps qc"` bỏ nguồn hoặc bước.

## Ba loại output

| Loại | Ví dụ | Rule | Hiển thị |
|---|---|---|---|
| Fact | giờ, giá, đặt chỗ, quy định vào cửa | Official > provider; bất đồng → `uncertain` + giữ xung đột | Một giá trị, hoặc "chưa xác nhận" kèm cả hai giá trị |
| Signal | độ đông theo thời điểm, yên tĩnh / sôi động, view, đường dốc | Phân phối trên các observation liên quan (1 tác giả 1 phiếu), theo bối cảnh, kèm xu hướng nửa mới / nửa cũ | Một xu hướng kèm mẫu ("62% trong 123 comment về độ đông, 30 creator") |
| Estimate | thời gian tham quan min / typical / long | Rule trên observation | Luôn là một khoảng |

**Bối cảnh quan trọng.** "Đông vào sáng cuối tuần" được lưu là `crowd × weekend × morning`, không phải "đông".

**Confidence** giữ bốn thành phần, không gộp thành một số ẩn; **coverage** theo khía cạnh là `COMPLETE | PARTIAL | NONE`. Cách tính chính xác: §5 Aggregate. Địa điểm không có bằng chứng trải nghiệm (chỉ tìm thấy qua inventory Google) được dùng làm chỗ ăn, anchor, hoặc phương án dự phòng, không được gợi ý như một trải nghiệm.

## Bản ghi địa điểm

```text
Place
├── Identity      tên, alias, loại (POI | ZONE), category, vị trí / hình học
├── Operation     giờ, giá, đặt chỗ, thời gian tham quan (khoảng)
├── Experience    feature (thiên nhiên, view, cà phê, chụp ảnh, hoạt động, …)
├── Environment   trong nhà / ngoài trời, độ đông theo bối cảnh, yên tĩnh / sôi động, nhạy thời tiết
├── Effort        đi bộ, dốc, khó tiếp cận   (thuộc tính của địa điểm, không phải của chuyến đi)
├── Suitability   cặp đôi, gia đình, bạn bè, đi một mình, người lớn tuổi
└── Provenance    tham chiếu bằng chứng, thành phần confidence, độ mới, xung đột, coverage, trạng thái
```

Feature lấy từ một **feature ontology** có version (`config/ontology.yaml`), dùng chung với User Profile. Hai bên dùng chung id, không dùng chung bản ghi: địa điểm lưu "có forest_view, kèm confidence"; profile lưu "thích forest_view, kèm affinity".

## Trạng thái — một bộ chung cho corpus, Admin Web, User Web

| Trạng thái | Ý nghĩa | Hiển thị cho người dùng? |
|---|---|---|
| `VERIFIED` | Qua gate và, nếu rủi ro cao, qua Judge hoặc người | Có |
| `UNCERTAIN` | Có xung đột hoặc bằng chứng yếu | Có, hiển thị là chưa chắc chắn |
| `OUTDATED` | Quá hạn độ mới | Có, kèm cảnh báo, cho đến khi được làm mới |
| `NEEDS_REVIEW` | Judge đánh dấu, hoặc đang chờ người kiểm tra bắt buộc | Không |
| `DISABLED` | Đã đóng cửa, trùng, không hợp lệ, hoặc bị người từ chối | Không |

Trạng thái giữ theo từng khía cạnh, nên một địa điểm có thể có định danh đã xác minh nhưng giờ mở cửa chưa chắc chắn.

## Data model

Lưu trữ hiện tại là **file**, không phải DB (xem §Sai lệch cho bản demo). Mỗi nguồn một thư mục, không gộp nguồn (`RULE.md` §2).

| Đường dẫn | Ghi bởi | Nội dung |
|---|---|---|
| `data/<source>/` (`gmaps/`, `tiktok/`) | `corpus.crawl` | dữ liệu thô đúng như nguồn trả: `search/`, `filter/`, `counts/`, `list/`, `places/`, `photos/`, `videos/` |
| `data/<source>/observations/` | `corpus.observe` | observation theo format chung, một file mỗi địa điểm |
| `data/gmaps/photo_observations/` | `corpus.observe` | observation đọc từ ảnh Maps |
| `data/intel/places/<fid_dir>.json` + `summary.json` | `corpus.aggregate` | Fact / Signal / Estimate theo địa điểm |
| `data/serving/places.json` | `corpus.serving` | bản ghi Place Decision đọc |
| `data/review/` | `corpus.review` | quyết định và nhãn của người duyệt |

Một **observation** (`src/corpus/observe/__init__.py`, dùng chung cho mọi nguồn):

```text
id · place_fid · feature · value · context{time_of_day, day_type, weather}
source_type · source_id · author · observed_at
span{quote, field, start_s, end_s}
extractor · ontology_version
```

`author` là đơn vị bỏ phiếu: một người một phiếu dù nhiều review, nhiều ảnh, hay nhiều video. `span` trỏ vào dữ liệu thô của nguồn, không bao giờ chép nội dung nguồn sang bản ghi địa điểm.

**Feature ontology** (`config/ontology.yaml`, có version): `id`, `group` (`experience` | `environment` | `service` | `effort` | `suitability`), giá trị cho phép, `contexts`, `verify` (`always` | `sampled`), `caution_values`, `check` (`span`), nhãn vi / en + từ đồng nghĩa.

Corpus và User Profile dùng chung **feature id**, không dùng chung bản ghi: corpus lưu `forest_view: present, confidence{…}`; profile lưu `forest_view: affinity, importance`.

## Chi tiết từng bước

### 1. Discover

- **Nội dung (TikTok) theo query — ngoài phạm vi hiện tại vì Google Maps quyết định tập địa điểm; code vẫn chạy được:** nhóm query (chung, category, trải nghiệm, đối tượng, ràng buộc, xu hướng) → thu video mới, caption, hashtag, toàn bộ comment kèm reply (trần tùy chọn `max_comments_per_video`). Search TikTok bằng Playwright với profile đã đăng nhập (bắt JSON API search); video tải từ `playAddr`; comment và reply bắt JSON API comment / reply (mở hết nút "Xem … câu trả lời"). Extractor đọc caption + hashtag của lô mới và đề xuất query mới (xu hướng, tên chỗ mới); code bỏ query trùng. Ngừng mở rộng một nhóm khi số ứng viên mới mỗi lô xuống dưới ngưỡng.
- **Phase 1 — danh sách địa điểm (output hiện tại):** `gmaps search` → `gmaps filter` → `gmaps counts` → `gmaps list`. Mỗi category (`config/queries.yaml`, không có loại chỗ ở) search trên lưới ô tới `grid.max_zoom` = 14 (quét nông có chủ đích: đủ ứng viên, thời gian có giới hạn). `list` bỏ ngoài `area`, bỏ chỗ ở (ô danh sách khách sạn `lodging` và category khớp khách sạn / nhà nghỉ / homestay / resort / villa / căn hộ…; một FID từng mang category chỗ ở ở bất kỳ lần thấy nào là chỗ ở: Maps xếp khách sạn có nhà hàng vào cả hai), chấm `score` = trung bình Bayes `(v·R + m·C) / (v + m)` (R rating, v số review, C rating trung bình của category, m trung vị số review của category: ít review không vượt được nhiều review), chỉ xếp nơi `filter` giữ, gộp bản trùng (cùng tên sau khi bỏ dấu, hoa thường, dấu câu, tên thành phố, cách nhau ≤ `same_name_m` = 1000 m, khác FID: giữ bản nhiều review nhất; chỉ gần nhau mà khác tên thì không gộp vì nhiều quán chung một tòa nhà; cùng tên xa hơn là chi nhánh khác); mỗi FID lấy lần thấy có nhiều review nhất; Maps khi không đăng nhập đôi khi chỉ hiện "4,6 sao" không kèm "(124)" trên thẻ và không bao giờ hiện số trên trang chi tiết, nên `counts` mở trang chi tiết bằng profile đã đăng nhập cho mọi nơi `filter` giữ có rating mà không lần thấy nào có số review, ghi `counts/<city>.json`, `list` lấy số đó thay số trên thẻ; bỏ nơi dưới `min_reviews` = 50 review hoặc không có rating — ngưỡng chất lượng duy nhất, không cắt theo rating hay `score`, không giới hạn số nơi mỗi category (`top_per_category` bỏ trống; đặt số thì giữ chừng đó nơi `score` cao nhất mỗi category); `score` chỉ để xếp thứ tự. Output là tên + định danh, chưa crawl chi tiết / review. Maps không có sắp xếp theo rating nên phải quét lấy ứng viên rồi tự xếp.
- **Phase 2 — tìm chuyên sâu từng địa điểm** (sau phase 1): `gmaps crawl` (chi tiết, giờ, review) + `qc` trên danh sách phase 1; TikTok vào ở đây như nguồn bằng chứng: mỗi nơi trong list Maps → `tiktok place_search` (search `<tên> <thành phố>`, bỏ tên thành phố nếu tên đã có; giữ `videos_per_place` video đầu theo thứ tự TikTok) → `tiktok place_filter` (Extractor, `PLACE_VIDEO_FILTER`: caption + hashtag có nói về **đúng** nơi này không, kèm tên / category / địa chỉ Maps; `no` cho nơi trùng tên, chi nhánh khác, chủ đề khác, chỉ nói về thành phố) → `tiktok place_crawl` (chỉ `yes`: comment + mp4, cùng file với `crawl`) → `tiktok asr` (vai trò ASR: ffmpeg 16 kHz mono, Silero VAD bỏ đoạn không có tiếng người (đệm 0,2 s, gộp đoạn cách < 1 s), chép lời từng đoạn, timestamp theo video) → `tiktok asr_check` (Extractor, `ASR_CHECK`: segment + caption + hashtag + 4 keyframe → chữ trên màn hình `screen_text` và mỗi segment `ok | fixed | garbled | lyrics`; tên riêng chỉ sửa theo tên viết trong caption / hashtag / màn hình, tên place đã map chỉ là gợi ý; code (`guard`) hoàn tác mỗi chỗ thay từ không giống âm ASR (bỏ dấu, độ giống < 0,5; ≥ 0,3 nếu từ mới có trong ngữ cảnh), từ chèn thêm không có trong ASR2, xóa từ phủ định; bản `fixed` giữ < 50% từ ASR → `garbled`; giữ text ASR thô) → `tiktok asr_alt` (segment `garbled` hoặc bị hoàn tác → ASR thứ hai chép lại, `alt_text`) → `asr_check` lần nữa với ASR + ASR2 → `tiktok place_verify` (Extractor, `PLACE_VIDEO_VERIFY`: caption + hashtag + transcript đã kiểm + 4 keyframe + các nơi khác cùng video → video có nói / cho thấy đúng nơi đã map không, kèm bằng chứng; đọc chữ trên màn hình đúng như hiện, không theo cách viết của transcript; nơi được nhắc có thể chứa / thuộc nơi đã map mà không rõ quan hệ → `unsure`; chỉ `yes` là bằng chứng; `no` / `unsure` vào trang review loại `place_verify`, giữ / bỏ của người thắng, `place_verify.evidence_pairs()`).
- **Inventory (Google Maps):** cào Google Maps (mỗi category trên lưới ô bản đồ phủ `area`) bằng Playwright, không ngưỡng rating (search: không đăng nhập, mỗi ô một context mới không cookie vì Google giới hạn theo phiên và danh sách khi chưa đăng nhập vẫn đủ; crawl chi tiết + review: profile đã đăng nhập); FID Maps làm id ứng viên; chi tiết + review + giờ cao điểm lưu file. Đây là tập địa điểm của corpus: ưu tiên tìm đủ danh sách (search mọi category trước), rồi mới crawl chi tiết + review.
- Thành phố là **config** (`config/cities.yaml`): tên ghép vào query TikTok, và khung `area` [lat_min, lng_min, lat_max, lng_max]. Chỉ địa điểm Google nằm trong `area` thuộc thành phố (Maps trả cả địa điểm trùng tên ở tỉnh khác).
- **Mỗi nguồn chạy theo phase độc lập**, mỗi phase một module (`src/corpus/crawl/<source>/<phase>.py`, hàm `run`), chỉ đọc file của phase trước, ghi vào thư mục riêng của phase: `search` (chỉ tìm, lưu kết quả thô) → `list` (gộp, bỏ trùng, không mở trình duyệt) → `filter` (TikTok: Extractor đọc caption + hashtag, trả `yes | no | unsure`; `crawl` chỉ mở video `yes` / `unsure`, chỉ `no` khi caption rõ ràng là chủ đề khác. Maps: chạy trước `list`, Extractor đọc tên + category Maps của mỗi FID khác nhau trong search (trong `area`, không chỗ ở), `no` chỉ khi rõ ràng không dành cho du khách: công ty, cửa hàng gia dụng, bãi xe, cứu hộ…; `list` chỉ xếp `yes` / `unsure`) → `crawl` (mở từng mục trong list) → `qc` (Maps: luật + Judge đọc địa điểm cùng 12 review mẫu + Extractor `REVIEW_QC` đọc **mọi** review (newest, relevant, extremes; lô 25) và gắn cờ `owner_reply`, `spam` (kể cả review đổi lấy quà / giảm giá), `not_a_review`; review kể lạ — dịch máy, sai đơn vị tiền, rất ngắn — vẫn là review; `place.json` không đổi mà chỉ thêm review (relevant / extremes / keywords) → giữ phán quyết địa điểm cũ, Extractor chỉ đọc review chưa đọc (`screened`), không cần Judge). Prompt, schema và thiết lập của mọi task model nằm ở `src/corpus/llm/` (`roles.py`: `Role`; `tasks.py`: `Task`); kết quả lưu `prompt_hash`, đổi prompt thì task chạy lại. Maps `search`: mỗi category × ô bản đồ phủ `area`; cuộn danh sách tới dòng "Bạn đã xem hết danh sách này"; ô đạt `full_at` kết quả hoặc không cuộn tới dòng đó (`end = false`) thì chia 4 ô zoom sâu hơn; `list` bỏ trùng FID và bỏ ngoài `area`. TikTok `crawl` đọc item JSON mới trên trang video (stats và `playAddr` còn hạn). Chạy `python -m corpus <source> <phase|all> --city <key>`.

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
                                         transcript (phase asr + asr_check + asr_alt): {model, vad_model, alt_model, at, total_s,
                                         speech_s, text, segments:[{start_s, end_s, text (ASR thô), alt_text (ASR2), checked_text,
                                         status: ok|fixed|garbled|lyrics, rejected_edits, needs_alt}], check:{model, prompt_hash,
                                         quality: good|partial|unusable|no_speech, screen_text[], transcript_at, alt_hash, at}};
                                         places (phase place_verify): [{fid, name, verdict: yes|no|unsure, evidence:[{source, quote}],
                                         reason, model, prompt_hash, transcript_at, checked_at}]; chỉ `yes` là bằng chứng cho nơi đó
      frames/f1..f4.jpg                  keyframe cho asr_check (tên trên màn hình) và place_verify (rộng 512 px)
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
                                         trước; review dưới 1 năm, tối đa `max_reviews_per_place` 200 (`max_review_age_months` 11: Maps ghi "một năm trước" cho 12–23 tháng; `min_reviews_per_place` 40: 40 review mới nhất luôn được giữ dù cũ hơn, để nơi ít khách vẫn có bằng chứng; place đã lưu bị cắt theo tuổi mà có dưới nửa min(40, số review Maps) được crawl lại)
      place.json                         fid, name, url, lat, lng, category, address, phone, website, description,
                                         hours[], status, attributes[], popular_times[], rating, review_count,
                                         rating_histogram[], price, plus_code, tickets, queries[], reviews_complete, fetched_at;
                                         ghi cuối cùng = place đã xong
    qc/<fid_dir>.json, qc/summary.json   {fid, name, fetched_at, checked_at, model, checks[], llm:{tourism_relevant, in_city,
                                         category_ok, bad_reviews[], field_issues[], verdict}}; chấm lại khi fetched_at đổi
    errors.jsonl
  review/decisions.jsonl                 {at, kind, id, decision, note}; append, quyết định mới nhất của mỗi mục thắng
```

- **Review lúc crawl** (`python -m corpus review`, trang cục bộ `127.0.0.1:8765`, code `src/corpus/review/`): hàng đợi dựng lại từ file mỗi lần mở, chỉ gồm mục cần người: `video_filter`, `place_filter` (`no` / `unsure`: giữ / bỏ), `video_comments` (`comments_complete` false hoặc thiếu: crawl lại / chấp nhận), `place_qc` (qc khác `ok`, không cho du khách, lỗi model: chấp nhận / loại; nơi trong `area` mà ngoài địa giới thành phố — Nam Ban, K'rèn, đèo Ngoạn Mục — là nơi bình thường, không bị gắn cờ), `place_reviews` (`reviews_complete` false: crawl lại / chấp nhận). Quyết định là nhãn, không sửa giá trị đã crawl; `filter` (TikTok) và `list` (Maps) áp giữ / bỏ của người lên kết quả model, `crawl` lấy lại mục có `retry` mới hơn `fetched_at`.

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

Tập đích là inventory Maps (§1). Mention từ nguồn khác (người dùng nhập; TikTok) chỉ match vào tập này hoặc tra thêm một địa điểm Maps theo tên; không có Place ID thì không có entity.

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
- **Review Google Maps** (bản demo, xem §Sai lệch; code `src/corpus/observe/gmaps/`, lệnh `python -m corpus gmaps observe [--limit N]`):
  - `details` có cấu trúc của Maps (Độ ồn, Thời gian đợi/chờ, Điểm đỗ xe, Thông tin đánh giá về mức giá, Đặt chỗ, Nên đặt vé trước, sao Đồ ăn / Dịch vụ) → observation bằng rule, không model; "Đã đến vào" thành `day_type` của mọi observation của review đó. Giá trị Maps cắt "…" chỉ dùng khi là tiền tố rõ nghĩa của đúng một nhãn ("Không rõ" cũng là nhãn, nên "Không…" bỏ).
  - Text: bỏ review rỗng, < 15 ký tự, trùng (tác giả + text), và review mà phase `qc` gắn cờ `owner_reply` / `spam` / `not_a_review`; còn lại → Extractor (`REVIEW_OBSERVE`), mỗi call một lô ≤ 15 review / ≤ 12.000 ký tự của một địa điểm, trả cho từng review nhiều observation (feature + value + context + quote) và `proposed_feature`. Một review cho nhiều observation; cùng feature khác bối cảnh được ghi riêng.
  - `attributes` của place (chủ quán / Google khai: "Phù hợp cho trẻ em", "Không có lối vào cho xe lăn", "Có chỗ ngồi ngoài trời", …) → observation bằng rule (`src/corpus/observe/gmaps/place_rules.py`), `source_type = gmaps_attribute`, một tác giả `gmaps:attributes` (một nguồn có thẩm quyền, xem §5). Lối vào quyết định `wheelchair`; nhà vệ sinh / chỗ ngồi / chỗ đỗ cho xe lăn riêng lẻ không map.
  - `popular_times` (độ đông tương đối theo giờ, 100 = đỉnh của chính nơi đó, Chủ nhật trước), `price` (khoảng giá / người), `hours` ({ngày: [[mở, đóng], …]}; `[]` = đóng cả ngày, `[["00:00", "24:00"]]` = mở cả ngày; dòng dạng lạ bỏ, ngày đó là unknown) và `closure` (`permanent` | `temporary` từ "Bị đóng vĩnh viễn" / "Tạm thời đóng cửa"; trạng thái tức thời như "Đang mở" bỏ) → `place_facts` của file observation, không phải observation. `place` = category, lat, lng, address. `voices` = số tác giả có `details` hoặc text được đọc: mẫu số của `mention_rate` (§5).
  - Câu hỏi dạng trả lời tự do trong `details` ("Độ thân thiện với trẻ em", "Tình trạng có lối đi cho xe lăn", "Các món chay") → `kids`, `wheelchair`, `vegetarian_options` theo bảng câu trả lời viết thường, so nguyên câu.
  - Gate: feature + value có trong ontology, context đúng enum, quote là chuỗi con của review sau chuẩn hóa NFC + khoảng trắng + hoa thường. Câu trả lời hỏng (JSON, schema) → chia đôi lô rồi thử lại, lô một review thử 2 lần; lỗi mạng / API → địa điểm thất bại ngay. Địa điểm thất bại không có file (file cũ bị xóa), ghi `data/gmaps/observe_errors.jsonl`, chạy lại lần sau.
  - Kiểm tra span: observation từ text của feature có `check: span` trong ontology (suitability, effort, `tourist_trap`, `entry_fee`, `condition_change`, `booking_needed`, `weather_exposed`) được đọc lại riêng bằng Extractor (`REVIEW_VERIFY`). Call thấy review (tối đa 1.200 ký tự quanh quote) và đúng một khẳng định: câu `claims[value]` của ontology cho giá trị cần kiểm ("người đi xe lăn không vào được nơi này") kèm quote; khẳng định phủ định mà review nói đúng là `supports`. Chỉ giữ `supports`; còn lại bỏ và đếm `span_check_<verdict>`; câu trả lời hỏng → bỏ observation đó (`span_check_error`), lỗi mạng / API → địa điểm thất bại. Bắt được phủ định ("hông chặt chém"), mỉa mai, nhận xét vị trí ("quán nằm ngay dốc"), ngoại lệ ("miễn phí bé dưới 80cm"). Effort có giá trị phủ định (`steep_or_stairs` / `long_walk` = `absent`, `weather_exposed` = `sheltered`) để sàng lọc cứng có bằng chứng `pass`, không chỉ `fail`; câu kể của người viết ("mình đặt bàn trước", "đường đi hơi xa" khi đi xe) không thành fact về địa điểm.
  - Chỉ xử lý place có trong `data/gmaps/list/<city>.json` (tập địa điểm); thư mục `places/` cũ của place đã bị list loại không được observe, file observation của chúng bị xóa.
  - Review bị qc gắn cờ không cho bằng chứng nào (cả `details` lẫn sao).
  - **Mẫu có chủ đích:** review chỉ đến từ `reviews_extremes.json` (thấp / cao sao nhất) hoặc `reviews_keywords.json` (tìm theo từ khóa) mang `sample = extremes | keywords` trên observation và sao của nó; tác giả của chúng đếm riêng ở `voices_targeted`, không vào `voices`. File observation dựng trước khi có nhãn này được gắn nhãn lại không gọi model.
  - Chạy lại một địa điểm chỉ khi `reviews.json` / `fetched_at` / cờ qc, hai prompt, text ontology (kể cả hint), version ontology hoặc version rule đổi. Cùng prompt + ontology mà có thêm review (relevant / extremes / keywords) → chỉ review mới (hoặc đổi chữ) đi qua model; review đã đọc (`read`: review_id → khóa nội dung) giữ nguyên observation và đề xuất, nên nhãn Judge trên các nhận định đó vẫn dùng được (`stats.reused`); file cũ chưa có `read` coi mọi review của các file review cũ hơn nó là đã đọc. Chỉ có thêm cờ qc mà review không đổi → cắt (`pruned`) observation, sao, `proposed_feature` và `voices` của review bị cờ khỏi file cũ, không gọi model; `qc_dropped` ghi các review đã cắt.
  - Output `data/gmaps/observations/<fid_dir>.json` theo format observation chung (`src/corpus/observe/__init__.py`); span = quote + review id (tham chiếu vào provider store, không chép sang entity). Review cũ hơn `max_review_age_months` chỉ có khi nằm trong 40 review mới nhất (§1 Dữ liệu thô) và được dùng như review mới; độ cũ hiện ở `freshness_days` và `trend.split_at`.
- **Video TikTok** (code `src/corpus/observe/tiktok/`, lệnh `python -m corpus tiktok observe [--limit N]`): chỉ cặp (video, địa điểm) trong `place_verify.evidence_pairs()` là bằng chứng (`yes` của `place_verify`, giữ / bỏ của người thắng). Mỗi cặp một call Extractor (`VIDEO_OBSERVE`): caption + hashtag, chữ trên màn hình, segment transcript `ok` / `fixed` của `asr_check` (đánh số, có giây) và 4 keyframe khi video chỉ được gắn với nơi này (video nhiều nơi: không gửi khung hình, vì không biết khung nào thuộc nơi nào). Gate: feature + value trong ontology, context đúng enum; `speech` → quote nằm trong đúng segment `ref`; `caption` → quote nằm trong caption / hashtag; `frame` → chỉ giá trị trong `FRAME_VALUES` (ảnh chứng minh được: bậc thang, trong nhà / ngoài trời, đông, view, hoa, thiên nhiên, chỗ ngồi ngoài trời, decor, cắm trại, đường xấu; không `absent`, không suitability / chất lượng, không "vắng" hay "rộng": video quảng cáo quay phòng trống, góc rộng). Feature `check: span` đọc lại (`VIDEO_VERIFY`, segment quanh quote ± 1 hoặc đúng khung hình), chỉ giữ `supports`. `source_type` = `tiktok_segment` | `tiktok_caption` | `tiktok_frame` (loại `video`), span có `start_s` / `end_s` (khung hình: giây giữa lát cắt), tác giả = `tiktok:<author_id>` (một phiếu mỗi người đăng dù nhiều video), `observed_at` = ngày đăng, `voices` = số người đăng. Chạy lại một địa điểm khi tập video, lần `asr_check`, hai prompt, `FRAME_VALUES` hoặc ontology đổi; lỗi một cặp → địa điểm không có file lần này, ghi `data/tiktok/observe_errors.jsonl`.
- **Trang official** (crawl `python -m corpus official pages`, `src/corpus/crawl/official/pages.py`; đọc `python -m corpus official observe`, `src/corpus/observe/official/`): website trong bản ghi Maps của nơi trong list là trang của chính nơi đó; trang mạng xã hội, đại lý vé / đặt phòng, link rút gọn không phải (`official_site`). Mở trang chủ không đăng nhập và tối đa 4 trang cùng site có link / địa chỉ nói giá vé, bảng giá, giờ, liên hệ, giới thiệu; đọc chữ hiển thị sau sự kiện `load`; trang chủ không tải được → không có file, ghi `data/official/errors.jsonl`, lần sau thử lại; tải lại sau 90 ngày. Ghi `data/official/pages/<fid_dir>.json` {fid, name, website, fetched_at, pages:[{url, title, text, cut}]}. Đọc: bỏ dòng lặp giữa các trang (menu, footer), cắt đoạn ≤ 6.000 ký tự, chỉ gửi đoạn có số tiền / giờ / chữ vé; Extractor (`OFFICIAL_OBSERVE`) trả vé (`adult` | `child` | `other`, số VND), vào cửa miễn phí cho mọi khách, giờ mở cửa (`HH:MM`, ngày áp dụng; giờ nhận khách cuối, giờ tour không phải). Gate: quote nằm trong trang, số tiền / giờ nằm trong quote, vé `other` bỏ; giá chỉ lấy cho nơi thuộc nhóm bán vé vào cửa (`TICKET_GROUPS`: nature, garden_farm, attraction, amusement, museum, religious, camping, other — trang nhà hàng, thuê xe, spa có bảng giá dịch vụ, không phải vé); site dùng chung cho nhiều nơi trong list (một đơn vị vận hành) chỉ giữ quote có từ riêng của tên nơi trong 500 ký tự quanh nó; miễn phí khi trang có vé người lớn là ngoại lệ (trẻ dưới 90 cm), bỏ. Output `data/official/observations/<fid_dir>.json` (`source = official`): observation `entry_fee` (`source_type = official_page`, một tác giả `official:<fid>`, nguồn có thẩm quyền như `gmaps_attribute`, §5) và `place_facts` {`hours` (ngày trang nêu; khoảng giờ chồng nhau = mâu thuẫn → không có giờ), `tickets_vnd` {adult, child}}. Đọc lại khi trang hoặc prompt đổi.
- **Context** trên mọi observation: `time_of_day`, `day_type`, `weather` (theo lời nguồn, không bao giờ là thời tiết thực tế), mỗi cái là enum hoặc `unknown`. "7h sáng hôm đó đông lắm" → `crowd = high`, `time_of_day = morning`, không phải `crowd = high` cho địa điểm.
- **Review theo từ khóa** (`python -m corpus gmaps keywords`, `src/corpus/crawl/gmaps/keywords.py`): review hiếm khi tự nói dốc, bậc, đi bộ, đối tượng phù hợp, vé hay đặt chỗ, nên ô "Tìm bài đánh giá" của chính Maps được gõ từng từ của `keyword_sets` (`config/queries.yaml`), mỗi bộ từ chỉ cho nơi thuộc nhóm category của nó: "dốc", "bậc thang", "đi bộ", "đường" và "người già", "lớn tuổi", "trẻ em", "em bé" cho nơi trải nghiệm; "vé" cho nơi bán vé vào cửa; "đặt bàn", "đặt trước" cho nhà hàng, quán cà phê, bar. Chỉ mở nơi Maps có nhiều review hơn số crawl giữ, và chỉ tìm từ chưa tìm (bộ từ mới được thêm vào file cũ); giữ `keyword_reviews_per_word` (20) review đầu mỗi từ; một từ xong khi đủ số hoặc Maps báo hết danh sách ("Không có bài đánh giá nào nhắc đến cụm từ …" khi không có kết quả). Ghi `reviews_keywords.json` {fetched_at, keywords:{từ:{complete, reviews}}}; qc, observe, Judge đọc như các file review khác; review của nó là mẫu `keywords` (§4 mẫu có chủ đích).
- **Thời gian khách thường ở** (`python -m corpus gmaps visit`, `src/corpus/crawl/gmaps/visit.py`): với nơi có biểu đồ giờ cao điểm, đọc dòng "Mọi người thường dành … ở đây" Maps in dưới biểu đồ (từ thời gian thực của nhiều khách) bằng regex trên chữ của trang, ghi nguyên văn `visit.json` {fetched_at, complete, text}; trang xong khi biểu đồ hiện (tín hiệu kết thúc), không hiện thì thử lại, lần cuối lưu `complete: false`. Observe đổi thành `place_facts.time_spent` {min_minutes, max_minutes} bằng luật ("tối đa X" → X/2–X; "X–Y giờ"; "Z phút").
- **Ảnh Google Maps** (crawl `python -m corpus gmaps photos`, `src/corpus/crawl/gmaps/photos.py`; đọc `python -m corpus gmaps photo_observe`, `src/corpus/observe/gmaps/photos.py`): mỗi nơi trong list mở thư viện ảnh, tab "Mới nhất" (chỉ vài tháng gần đây) rồi "Tất cả" (thứ tự liên quan, có ảnh nhiều năm trước) tới đủ `photos_per_place` (12; điểm tham quan thuộc `photo_groups` — nature, garden_farm, attraction, amusement, camping, religious, museum — lấy `photos_per_sight` 30, vì bậc thang, lối đi thấy trong ảnh nhiều hơn trong review; nơi đã lưu dừng ở trần cũ, không phải hết gallery, được lấy lại với số mới, `photos.json` ghi `wanted`); mỗi ảnh mở ra để đọc người đăng (contrib id → `author_hash`, cùng hash với review nên một người một phiếu cho cả chữ lẫn ảnh) và tháng chụp ("Ảnh chụp vào: thg 9 2026", không có thì tháng đăng); bỏ ảnh cũ hơn 3 năm (`too_old`), tối đa 3 ảnh một người (`same_author`), metadata phải đọc giống nhau hai lần liên tiếp (header cập nhật từng phần); ảnh chủ quán gắn cờ `owner` (tên người đăng = tên nơi); tải ở 768 px qua tab trình duyệt (request trực tiếp tới máy chủ ảnh bị timeout), ghi `photos/` + `photos.json` (`tabs`, `complete`, `skipped`). Đọc: Extractor (`PHOTO_OBSERVE`) 4 ảnh một call, chỉ được báo `PHOTO_VALUES` (bậc thang dài / dốc phải leo, đường vào đất đá, rất đông, trong nhà / ngoài trời nhìn từ khu khách ngồi, view, biển mây, hoa, thiên nhiên, chỗ ngồi ngoài trời, decor, cắm trại, thú): không bao giờ `absent`, chất lượng, giá hay đối tượng phù hợp; một ảnh một giá trị mỗi feature (hai giá trị → bỏ, `mixed_values`); feature `check: span` đọc lại trên đúng ảnh (`PHOTO_VERIFY`). `source_type = gmaps_photo` (loại `photo`), `observed_at` = tháng chụp, ảnh chủ quán chung một tác giả `gmaps:owner:<fid>`; ghi `data/gmaps/photo_observations/<fid_dir>.json`, `aggregate` đọc cả thư mục này. Headless Chrome phải mang user agent Chrome thường: với "HeadlessChrome" Google trả Maps "chế độ bị hạn chế" (không review, ảnh, giờ) dù đã đăng nhập; `check_signed_in` dừng khi thấy thông báo này.
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

**Signal từ observation** (code `src/corpus/aggregate/`, lệnh `python -m corpus aggregate`): đọc mọi `data/*/observations/*.json`, không biết nguồn; file của version ontology cũ vẫn được đọc tới khi observe chạy lại (giá trị ontology đã bỏ bị loại; đếm `stale_files`, intel ghi `observation_versions`), để đổi ontology không xóa sạch intel; ghi `data/intel/places/<fid_dir>.json` và `data/intel/summary.json` (`places`, `stale_files`, `removed`, đếm coverage). File không thuộc lần build (nơi không còn file observation) bị xóa, đếm ở `removed`: thư mục luôn là đúng một lần build. Mỗi feature:
- Trước khi đếm: observation có nhãn `wrong` (người, nếu không thì Judge, §6) bị bỏ; nhãn `unsure` mà Judge mạnh đọc lại vẫn `unsure` (`unsure_again`) cũng bị bỏ: nguồn không đủ làm bằng chứng. Observation mẫu có chủ đích (`sample`, §4) chỉ được tính cho effort, `visit_duration` và fact của nơi (`entry_fee`, `booking_needed`, `cash_only`, `vegetarian_options`, `setting`, `weather_exposed`, `wheelchair`; `corpus.observe.targeted_ok`), với `voices + voices_targeted` làm mẫu số `mention_rate`; không bao giờ cho cảm nhận (chất lượng, phục vụ, giá trị, độ đông, đối tượng phù hợp) vì mẫu thấp / cao sao nhất làm lệch tỷ lệ, và sao của chúng không vào `rating_trend`. Judge audit không chấm các observation bị bỏ này. Nguồn của chính doanh nghiệp (tác giả `…:owner:…`: ảnh Maps chủ quán đăng, video TikTok từ tài khoản của nơi đó) chỉ được tính cho thứ nó cho thấy hoặc khai với tư cách người vận hành (`OWNER_FEATURES`: cảnh, hoạt động, không gian, đỗ xe, vé, đặt chỗ…; effort chỉ khi `present`), không bao giờ cho chất lượng, độ đông, ồn, sạch hay đối tượng phù hợp. Ảnh Maps không đọc được người đăng chung một tác giả mỗi nơi. Hai mục Maps Judge phán là một nơi (`place_merge`, §6) được tổng hợp dưới mục chuẩn (nhiều review hơn), mục kia không có file intel; `merged` liệt kê các mục đã gộp.
- Phiếu: 1 tác giả 1 phiếu; tác giả nói k giá trị khác nhau → mỗi giá trị 1/k; trùng (tác giả, value, bối cảnh) tính một. `n` = `independent_sources` = số tác giả. `by_context` đếm theo từng giá trị bối cảnh, `by_source` đếm observation thô.
- `agreement` = tỷ lệ giá trị đứng đầu; < 0.6 → `uncertain`, giữ nguyên phân phối.
- `trend`: cắt observation có ngày tại ngày trung vị (hai nửa không chung ngày, `split_at`); `rising | falling | stable` theo tỷ lệ giá trị đứng đầu khi mỗi nửa ≥ 5 tác giả, chênh ≥ 0.2; còn lại `insufficient`. Tương đối vì crawl giữ review mới nhất. `rating_trend` của địa điểm: sao trung bình hai nửa, chênh ≥ 0.5 sao.
- Nguồn có thẩm quyền (`gmaps_attribute`): giá trị nó khai được phục vụ không cần người khi không nguồn nào nói khác (`authority` = giá trị đó); có review (đã qua nhãn) nói khác → `uncertain`, `authority` = null, giữ cả hai phía, vẫn được phục vụ là `UNCERTAIN`. Observation của nguồn thẩm quyền không có ngày người nói: không tính vào `freshness_days` và `trend`.
- `mention_rate` = số tác giả (không tính nguồn thẩm quyền) nói feature / tổng `voices` của các file; `null` khi không có `voices`. Feature chỉ có `present` luôn có `agreement` = 1, nên độ mạnh của nó nằm ở `mention_rate`.
- `checked` = {`authors`: tác giả của giá trị đứng đầu có nhãn `correct`, `of`: số tác giả của giá trị đó (không tính nguồn thẩm quyền), `all`}. Feature `verify: always` không có nguồn thẩm quyền: giá trị cho phép `needs_review` (không phục vụ) tới khi mọi tác giả đã được kiểm đúng; giá trị cảnh báo cần ≥ 2 tác giả hoặc mọi tác giả đã kiểm đúng.
- `identity` của địa điểm: giá trị khác null đầu tiên của `place` qua các file. Trang official thắng Maps: `hours` của ngày trang nêu thay giờ Maps (`hours_source = official`), ngày hai bên nói khác giữ ở `hours_conflict`; `entry_fee` lấy `tickets_vnd` (typical = trung vị vé người lớn vì trang còn liệt kê combo / tour, min = vé thấp nhất kể cả trẻ em, `source = official`). `operation`: `price_range` (Maps, {min_vnd, max_vnd, per, reports} hoặc {level}), `hours`, `closure`, `popular_times` nguyên dạng, `crowd_by_time` = trung bình % độ đông theo `weekday | weekend` × `time_of_day` (giờ → buổi: 4–5 `early_morning`, 6–10 `morning`, 11–13 `noon`, 14–16 `afternoon`, 17–20 `evening`, còn lại `night`; giờ 0% coi là đóng cửa, bỏ — vì vậy trung bình có thể hơi cao ở giờ mở cửa mà vắng) + `peak` (ngày, giờ, %). Đây là độ đông tương đối của chính nơi đó, không so được tuyệt đối giữa hai nơi.
- Coverage theo nhóm ontology (gồm `operation`: `visit_duration`): `NONE` khi không feature nào, `COMPLETE` khi ≥ 3 feature có n ≥ 3, còn lại `PARTIAL`.
- Chất lượng đo được (§Đo chất lượng): `quality` = thống kê nhãn của giá trị đứng đầu (`review.label_stats()`: precision, cận dưới Wilson, `gate`); `servable` = giá trị được phục vụ một mình: có `authority`, hoặc qua ngưỡng nhãn (≥ 30 nhãn, cận dưới ≥ 0,8), hoặc mọi tác giả của nó đã được kiểm đúng (`checked.all`), hoặc người `accept`. Quyết định `feature_review` (id `<fid>#<feature>`, bản mới nhất, `undo` = không có): `disable` → `status = disabled`, `servable = false`; `accept` → `needs_review = false`; `report` / `refresh` → `needs_review = true`.
- `estimates` (`aggregate/estimates.py`, bảng `config/category_defaults.yaml`; luôn là Estimate, không bao giờ là fact hay bộ lọc cứng): `category_group` (từ khóa đầu tiên khớp category Maps), `visit_minutes` {short, typical, long, source} (`time_spent` của Maps trước, `source = maps_time_spent`; rồi `visit_duration` của review khi ≥ 3 tác giả và `signal`; còn lại mặc định của nhóm), `entry_fee` {min_vnd, typical_vnd, max_vnd, n, source} (số tiền trong quote `entry_fee = paid` nằm cùng mệnh đề với chữ vé / vào cổng / tham quan / ticket, không phải mệnh đề về chụp ảnh, gửi xe, thuê đồ, massage, giá theo kg: "50k", "160.000 đồng"…; mỗi tác giả số lớn nhất vì vé người lớn cao nhất; chỉ lấy quote trong 730 ngày gần nhất khi có ≥ 2 tác giả; không có thì vé Maps US$ × `usd_vnd`), `usable_as_default`, `effort_hint` (`low` chỉ cộng điểm xếp hạng: đo 2026-10-02, dốc có ở 16% nhà hàng và 37% quán cà phê có bằng chứng effort).

**Serving record** (code `src/corpus/serving/`, lệnh `python -m corpus serving` → `data/serving/places.json`; ngưỡng `config/serving.yaml`): bản ghi Place Decision đọc (`PLACE_DECISION.md` §2.2). Nơi có `closure` (tạm hoặc hẳn) hoặc Judge phán `closed` / `changed` (`place_status`, §6) là `DISABLED`, không vào file; Judge phán `unclear` → bản ghi `UNCERTAIN` (`closure_reported`). Feature theo khía cạnh (`experience`, `environment`, `service`, `effort`, `suitability`): `disabled` / `needs_review` (`unchecked`) → bỏ; `uncertain` → `UNCERTAIN` (`conflict` | `low_agreement`); chưa `servable` → `UNCERTAIN` (`unmeasured_precision`); còn lại `VERIFIED`, quá `freshness_days` (độ đông 365, khác 730) → `OUTDATED`. Mỗi feature giữ value, phân phối, n, `mention_rate`, confidence, bối cảnh, cận dưới precision, ≤ 5 id bằng chứng. `operation`: giờ (fact, kèm `source`; quá 90 ngày → `OUTDATED`; `hours_conflict` → `UNCERTAIN` kèm `conflict`), giá / người (180 ngày), giá vé (`kind = fact` khi lấy từ trang official, còn lại `estimate`) + thời gian tham quan (`kind = estimate`), đặt chỗ, độ đông theo giờ. `usable_as` = mặc định nhóm category, bỏ `experience` khi coverage experience `NONE`. `check(record, feature, forbidden)` = kiểm tra fail-closed của §6.2 Place Decision: `fail` khi giá trị cấm chắc chắn (`VERIFIED` / `OUTDATED`); `pass` khi giá trị khác chắc chắn và không tác giả nào nói giá trị cấm; còn lại (không bằng chứng, `UNCERTAIN`, có người nói ngược) `unknown`. `area` = khu vực (leader clustering: nơi có nhiều láng giềng nhất trong `area_km` làm tâm). `near_duplicate_group`: cùng nhóm category + cùng `usable_as` + Jaccard ≥ 0,6 trên cặp (feature, value) "loại nơi" (experience + environment trừ chất lượng / đông / sạch / đỗ xe / thời tiết / vệ sinh / muỗi) được ≥ 2 tác giả và ≥ 3% người viết nhắc, so với leader của nhóm (nơi nhiều feature nhất), không nối chuỗi. `mmr()` chọn shortlist: λ·điểm − (1−λ)·độ giống lớn nhất với nơi đã chọn.

Serving record có đủ cho Place Decision hay không được đo bằng `python -m decision evaluate` (`docs/PLACE_DECISION.md` §17), chạy đúng pipeline thật trên 30 Trip State ẩn của `config/eval_trips.yaml`.

### 6. Kiểm tra và định tuyến

**Gate** (code; không model nào vượt qua được):

- Output đúng schema; span được trích tồn tại nguyên văn trong nguồn; timestamp nằm trong media.
- Feature id có trong ontology hiện tại.
- Match POI qua ngưỡng và cách biệt (hoặc `T_min` với lựa chọn của Judge).
- Hình học ZONE bao các POI liên quan.
- Fact / signal / estimate chỉ do rule tổng hợp ghi; nội dung Google chỉ nằm trong provider store (observation từ review Maps chỉ trỏ span vào đó).

**Kiểm tra span.** Với observation tác động cao (mọi `fact_key`, mọi feature có `check: span` trong ontology — an toàn, tiếp cận, đối tượng phù hợp, effort, chặt chém, vé), một call Extractor riêng chỉ thấy đoạn nguồn quanh span và một khẳng định cho đúng giá trị cần kiểm, rồi trả lời `supports | contradicts | insufficient`. Khác `supports` → bỏ, kèm lý do. Hiện làm cho review Maps (§4).

**Judge thay người duyệt** (code `src/corpus/judge/`, lệnh `python -m corpus judge <dedup|status|audit|all>`; prompt `OBS_AUDIT`, `PLACE_STATUS`, `SAME_PLACE` ở `src/corpus/llm/tasks.py`). Judge chỉ ghi nhãn và quyết định (`data/review/`), không bao giờ sửa giá trị; nhãn / quyết định của người cùng nội dung luôn thắng.

- `audit`: gán nhãn `correct | wrong | unsure` cho nhận định model của Extractor (review, ảnh, video; observation do luật — details, attributes — không gán). Đọc **toàn bộ** observation của feature rủi ro (nhóm `effort`, `suitability` và mọi feature `check: span`), mẫu mỗi (feature, value, thư mục nguồn) cho feature khác, lấy tuần tự **30 → 60 → 100** nhãn: dừng khi cận dưới Wilson ≥ 0,8 (qua), đọc **toàn bộ** tầng khi cận trên < 0,8 (trượt, xét từ 30 nhãn như ngưỡng nhãn) hoặc tới 100 nhãn vẫn chưa rõ — nhãn mẫu tính luôn vào phần đọc toàn bộ nên nới mẫu không tốn thêm call; tầng 90% đúng qua ở 100 nhãn thay vì bị đọc hết; lặp tới khi không còn gì (tối đa 5 vòng). Mỗi call ≤ 24 nhận định chữ (≤ 8 ảnh; từ 2026-10-06 để tiết kiệm quota Codex, chưa đo — 16 chữ đã đo), mỗi nhận định một khối đóng `<iN> … </iN>` mang đoạn nguồn riêng của nó (đo 2026-10-05 trên 161 nhận định chấm lại: 16 khối riêng sai 3, 8 như cũ sai 5, `cx/gpt-5.6-terra` sai 14 và chung quota với sol nên không dùng), nhận định của một nơi đi cùng nhau: nơi, định nghĩa feature (`hint` + `claims` của ontology), đoạn nguồn quanh quote (review ≤ 1.500 ký tự, segment ± 2, caption) hoặc chính ảnh / khung hình. `wrong` khi phủ định, mỉa mai, giả định, ngoại lệ, nói về nơi khác / thành phố / giao thông chung, hành động của người viết, quá yếu so với định nghĩa (đi bộ 20 m không phải đi xa; dốc chạy xe không phải bậc phải leo), ảnh không cho thấy; chấp nhận cách nói khác và hệ quả trực tiếp ("không hợp người khó di chuyển" vì nhiều bậc → xe lăn không vào được). Giá trị cho phép (`verify: always`, không phải `caution_values`) đi Judge mạnh. Nhãn ghi `data/review/judge_labels.jsonl` ngay khi về (`by` = model trả lời, `ph` = prompt hash); nhãn `wrong` của Judge dưới prompt cũ được hỏi lại khi prompt đổi. Sau các vòng, **đọc lần hai**: mọi nhận định Judge thường trả `unsure` (người trả `unsure` thì giữ) được gom cho Judge mạnh đọc lại (nhãn `look: 2`); vẫn `unsure` → aggregate bỏ như `wrong`.
  **Engine Gemma** (`JUDGE_ENGINE=gemma` trong `.env`, dùng khi hết quota Codex): cả audit chạy trên Gemma của Extractor (`OBS_AUDIT_GEMMA`), 8 nhận định một call, **một vòng**, không first reader, không Judge mạnh, không đọc lần hai. Prompt khắt khe: mỗi nhận định kèm câu `claims` của giá trị (`claim_text`), đoạn nguồn 500 ký tự, câu trả lời viết lý do nghi ngờ mạnh nhất trước verdict. Đo 2026-10-06 (`logs/judge_exp/gemma_eval.py`, 1.334 nhận định có nhãn sol, chia theo feature, dev/test khác nơi): để lọt 11–16% nhận định sai (prompt thường trên Gemma: 48%), bỏ nhầm ~30% nhận định đúng; ảnh lọt 35%. Vì sai ảnh hưởng thẳng người dùng còn thiếu thì crawl bù được: `wrong` của Gemma bỏ nhận định ngay; `unsure` ghi `look: 2` (aggregate bỏ); `correct` trên ảnh ghi thành `unsure` lượt 1 (giữ như chưa chấm). Khi engine về Codex, `current()` coi mọi nhãn không phải `correct` của Gemma (theo `ph`) là chưa chấm → sol đọc lại. Gemma chỉ chấm nhận định chưa có nhãn và nhãn Gemma không bao giờ thay nhãn người / Codex có trước (`review.labels.stand_in`). `dedup` và `status` không có engine Gemma (mẫu nhỏ, cần Judge Codex); build khi hết quota bỏ hai bước này (`--skip "judge dedup" "judge status"`).
- `status`: nơi có observation `condition_change` báo đóng cửa / chuyển đi / đổi thành nơi khác → Judge cân báo cáo với 15 review mới nhất và trạng thái Maps theo ngày, theo cách khách dùng nơi đó (đồi, hồ, khu vẫn có khách thì vẫn `open` dù một cơ sở trên đó ngừng) → `open | closed | changed | unclear`. `closed` / `changed` chỉ đứng khi Judge mạnh đồng ý, không thì `unclear`. Ghi `decisions.jsonl` kind `place_status`; hỏi lại khi báo cáo, review mới nhất hoặc prompt đổi. Nơi Judge đã phán khác `open` mà nay không còn báo cáo nào (observe chạy lại, qc cắt review) trở về `open`; quyết định của người giữ nguyên.
- `dedup`: cặp mục Maps cách ≤ 300 m có tên chung phần lớn từ riêng (bỏ từ chung "quán", "spa", "thuê xe"…), hoặc trùng tên trong 1,5 km → Judge đọc hai thẻ (tên, category, địa chỉ, điện thoại, 4 đoạn review) → `same_place | part_of | branch | different`. `same_place` chỉ đứng khi Judge mạnh đồng ý; kind `place_merge`, id `<fid>|<fid>`, `note.canonical` = mục nhiều review hơn. `part_of` (bến thuyền của hồ, quán trong sở thú) và `branch` giữ hai nơi.

Giá trị **cảnh báo** hạn chế lựa chọn ("đường dốc", "không hợp người lớn tuổi"): sai chỉ làm mất một gợi ý. Giá trị **cho phép** mở rộng lựa chọn ("hợp người lớn tuổi", "an toàn cho trẻ em"): sai có thể gây hại. Ontology khai báo giá trị nào là cảnh báo (`caution_values`); code phân loại, không model nào quyết định.

Giá trị cho phép chưa được kiểm hết thì không phục vụ (`needs_review`); không còn bước nào chờ người.

### 7. Publish và review

**Serving record** (do `online/retrieval` đọc): entity id, loại, hình học, category; trường lọc được (giá, giờ, effort, trong nhà/ngoài trời, khoảng thời gian tham quan); feature kèm tham chiếu bằng chứng; thành phần confidence; coverage và trạng thái theo khía cạnh; `usable_as` (`experience | meal | anchor | backup`, tính từ category + coverage — nhà hàng chỉ có từ inventory là `meal/anchor/backup`, không phải `experience`).

**Trạng thái:** bộ chung cho corpus, Admin Web, User Web — `docs/CORPUS.md` §6. `NEEDS_REVIEW` và `DISABLED` không bao giờ được phục vụ.

**Người duyệt** không còn là bước bắt buộc: Judge (§6) quyết định mọi mục trước đây chờ người. Trang review (`python -m corpus review`) vẫn cho người gán nhãn và quyết định; nhãn / quyết định của người cùng nội dung thắng Judge, và là bộ regression để đo chính Judge (§Đo chất lượng).

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
| **Mở rộng query** (§1, TikTok theo query) | Extractor | đề xuất query TikTok mới từ caption + hashtag | số ứng viên mới mỗi lô < ngưỡng |
| **Tìm trang official** (§4) | Extractor | search web, chọn link, tải trang, đi theo link nội bộ thuộc whitelist | đủ loại trang whitelist, hoặc 5 trang |
| **Lấp khoảng trống coverage** | Extractor | lấy thêm review Maps (cũ hơn / sắp theo liên quan), tìm trang official, tìm thêm video TikTok `"<tên> <khía cạnh>"` | coverage khía cạnh tăng, hoặc 3 bước |
| **Làm giàu theo yêu cầu** (§3) | Extractor | như lấp khoảng trống coverage, cho entity người dùng vừa nhập | như trên |
| **Hiệu chỉnh** (ngoài build) | Judge | sinh biến thể prompt / ngưỡng → chạy bộ regression | không biến thể nào tốt hơn, hoặc N lượt |

Lấp khoảng trống coverage chạy sau Aggregate cho entity có khía cạnh `PARTIAL | NONE`, ưu tiên theo lưu lượng, và cho key bị Judge báo `contradiction` (§6). Hiệu chỉnh chỉ nhận biến thể khi precision trên bộ regression ≥ bản hiện tại và chi phí ≤ bản hiện tại; bản được nhận vẫn đổi `prompt_hash` / version nên ledger chạy lại phần bị ảnh hưởng.

## Place Decision dùng corpus thế nào

```text
Sở thích người dùng → truy xuất địa điểm (serving index) → địa điểm được gợi ý
   → Vì sao phù hợp: feature → segment video (embed tại timestamp) + xu hướng comment (kèm cỡ mẫu)
   → Giờ / giá / vị trí: bằng chứng official hoặc Google, không trộn với bằng chứng trải nghiệm TikTok
```

**Dữ liệu hiện có cho Place Decision** (`data/intel/places/<fid_dir>.json`, `python -m corpus aggregate`; quy tắc ở ``§4–5 dưới đây):

| Place Decision cần (`docs/PLACE_DECISION.md`) | Field | Nguồn chính | Lưu ý |
|---|---|---|---|
| Sàng lọc cứng §6: trẻ em, nhóm, xe lăn | `features.kids / groups / wheelchair` (`authority`, `needs_review`, `status`) | `attributes` Maps (thẩm quyền) + review đã kiểm span | Không có → `unknown`, fail-closed |
| Sàng lọc cứng §6: dốc, bậc, đường xấu, đi bộ xa | `features.steep_or_stairs / rough_road_access / long_walk` | Review đã kiểm span | Review hiếm khi nhắc → phần lớn `unknown` |
| Ngân sách | `operation.price_range`, `features.value_for_money / entry_fee / tourist_trap` | Maps + review | |
| Hợp bối cảnh §7: độ đông theo ngày / buổi | `operation.crowd_by_time`, `features.crowd.by_context` | `popular_times` Maps + review | % tương đối của chính nơi đó |
| Xếp hạng §8: `preference_fit` | `features.<id>.distribution / n / confidence` | Review + attributes | Review thiên tích cực: tín hiệu phân biệt nằm ở phiếu tiêu cực |
| Thẻ ứng viên §11: vì sao phù hợp, đánh đổi, độ tin cậy | `features.*.observation_ids` → quote, `trend`, `rating_trend`, `coverage` | | |

Planner chỉ đọc serving record; không bao giờ duyệt đồ thị bằng chứng. Thời tiết, giao thông, thời gian di chuyển thực tế được lấy theo từng request và không bao giờ thành dữ liệu corpus.

Khi người dùng nhập một địa điểm chưa có trong registry, cùng bộ matcher chạy theo yêu cầu. Match chắc chắn thì trả về và xếp hàng làm giàu dữ liệu; nếu không, người dùng chọn từ các phương án. Không đoán gì cả.

## Kiểm soát chi phí và hiệu năng

- **Rule trước model.** Spam, trùng lặp, chuẩn hóa, chấm điểm, tổng hợp đều là code.
- **Chỉ hai vai trò model trong build.** Extractor miễn phí hoặc rẻ cho mọi khối lượng; Judge chỉ cho entity rủi ro cao và match mơ hồ. (Agent không thuộc build, nó chạy trong phiên người dùng.)
- **Không trả tiền hai lần.** Mọi call model được khóa theo input hash + processor + prompt hash; call lặp lại trả kết quả đã lưu.
- **Gom lô mục nhỏ** (comment, kiểm tra span) theo số lượng; một video mỗi call Extractor; trang dài chia theo heading; input quá cỡ được chia nhỏ, không bao giờ bị cắt ngầm.
- **I/O gọn.** Id, enum, offset; `pass` là câu trả lời gần như rỗng; prefix prompt ổn định đặt trước để provider cache được.
- **Ngân sách mỗi build:** call Judge, call Google, bước của vòng lặp tự động. Hết ngân sách thì build dừng gọn và chạy tiếp ở lần sau; entity rủi ro cao chưa được audit giữ `NEEDS_REVIEW` (không bao giờ tự publish).
- Báo cáo mỗi build: chi phí và token theo model, **chi phí trên mỗi entity được phục vụ**, tỷ lệ tự publish, kích thước hàng đợi review.

## Đo chất lượng

Không có bộ benchmark gán nhãn tay từ đầu; nhãn đến từ Judge (§6) và từ người khi có. `review.label_stats()` tính precision và cận dưới Wilson theo (feature, value), tách theo thư mục nguồn; nhãn người trên mẫu nhãn Judge đo độ tin của chính Judge.

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

## Sai lệch cho bản demo

| Sai lệch | Demo | Cách sửa khi thương mại |
|---|---|---|
| Nguồn Google | Cào Google Maps có đăng nhập; review Maps dùng làm bằng chứng | Places API theo điều khoản (review chỉ dùng trong phạm vi điều khoản cho phép) |
| Thu thập TikTok | Scraper Playwright có đăng nhập | Truy cập có license |
| Lưu trữ | Lưu file, chưa có DB (§Data model) | PostgreSQL + PostGIS |
| Hình học ZONE | Buffer / hành lang quanh POI liên quan | Dữ liệu bản đồ |

## Đầu vào cần có

API key của các model đang cấu hình trong `.env`; tài khoản TikTok phụ và tài khoản Google phụ (đăng nhập bằng `python -m corpus login`); trần ngân sách hàng tháng cho Judge; một người duyệt.

