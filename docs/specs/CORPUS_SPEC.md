# Corpus Place Intelligence — Thiết kế chi tiết

Tổng quan ngắn: `docs/CORPUS.md`. File này là thiết kế chi tiết để triển khai.

## Mục tiêu

Xây **corpus Place Intelligence** offline cho planner đọc. Agent xây từ đầu đến cuối; gate tất định kiểm soát mọi lần ghi; người chỉ duyệt một hàng đợi nhỏ, xếp theo rủi ro, ở cuối. Mọi giá trị được phục vụ đều truy về bằng chứng.

Đích: kiến trúc nhỏ nhất mà **đúng** (không bịa địa điểm hay fact), **rẻ** (model miễn phí hoặc rẻ cho khối lượng lớn, model mạnh chỉ ở chỗ cần phán đoán), và cho **output chất lượng cao**, đồng thời mở rộng ra thêm địa điểm và thành phố bằng config, không phải bằng code.

## Phạm vi

Trong: Đà Lạt; khám phá (TikTok + inventory Google Places); trích xuất media; entity resolution (POI / ZONE); observation; tổng hợp thành fact / signal / estimate; kiểm tra và định tuyến theo rủi ro; duyệt cuối; serving index; refresh; resolve theo yêu cầu khi người dùng nhập một địa điểm.

Ngoài: mọi dữ liệu người dùng (corpus không lưu và không coi input người dùng là bằng chứng về địa điểm); độ phù hợp của gợi ý (thuộc online); live context (thời tiết, giao thông, thời gian di chuyển); lưu file video TikTok; phủ toàn quốc.

## Nguyên tắc

1. **Không bao giờ bịa entity.** Entity chỉ tồn tại sau khi resolve được về một thứ có thật.
2. **Không span, không observation.** Mọi observation trích nguồn và một span định vị (field + offset, hoặc segment + timestamp).
3. **Chưa biết thì giữ là chưa biết.** Thiếu bằng chứng là `unknown`, không bao giờ là `false` hay giá trị mặc định.
4. **Giữ xung đột.** Bất đồng cho ra `uncertain` và giữ lại xung đột.
5. **Model trích xuất; code quyết định.** Fact, signal, estimate chỉ do rule tổng hợp ghi. Không model nào ghi chúng.
6. **Cùng được nhắc không có nghĩa là ở gần nhau.** Xuất hiện trong một video không bao giờ là bằng chứng về khoảng cách.
7. **Vai trò nguồn tách biệt.** TikTok mô tả trải nghiệm và môi trường; fact vận hành đến từ trang official và Google.
8. **Build không bao giờ chờ người.** Việc agent không giải quyết được sẽ kết thúc ở `UNRESOLVED` hoặc không được phục vụ, kèm lý do, và đi vào review.

## Vai trò model

Spec ràng buộc **vai trò**, không ràng buộc model. Mỗi vai trò là một adapter có kiểu với output được validate theo schema; model nào đảm nhận là config, chọn theo **chất lượng trên nhãn review, sau đó đến chi phí trên mỗi entity được phục vụ**. Đổi model của một vai trò là đổi config, và phải qua bộ regression (§Đo chất lượng).

| Vai trò | Làm gì | Yêu cầu |
|---|---|---|
| **Code** | Chuẩn hóa, dedup, rule lọc spam, chấm điểm match, tổng hợp, gate, định tuyến rủi ro | Tất định, có test |
| **ASR** | Âm thanh → transcript có timestamp | Tiếng Việt, có timestamp |
| **Extractor** | Mọi việc model khối lượng lớn: `visible_text` + `visual_summary` của keyframe, mention, observation có span, độ liên quan / đối tượng / stance của comment, nhận định từ trang official, kiểm tra span | Nhận ảnh, output có cấu trúc, throughput cao, chi phí thấp hoặc bằng 0; mỗi call vừa một đơn vị tự nhiên (một video, một lô comment, một đoạn trang) |
| **Judge** | Chốt chặn trước người: chọn trong các phương án match `AMBIGUOUS`; audit hồ sơ entity rủi ro cao | Khả năng suy luận mạnh nhất có được; **khác họ model với Extractor** để lỗi độc lập; số call thấp |

Model đang đảm nhận từng vai trò và cách kết nối: `docs/LLM_PROVIDER.md`.

Chỉ thêm vai trò hoặc model thứ hai khi nhãn review cho thấy một bước mà các vai trò hiện tại làm chưa đủ tốt.

## Pipeline

```text
 DISCOVER ──► EXTRACT ──► RESOLVE ──► OBSERVE ──► AGGREGATE ──► CHECK & ROUTE ──► PUBLISH
 TikTok       ASR          code +      Extractor   code          gate · rule rủi ro  serving index
 lưới Maps    Extractor    Judge nếu               fact/signal/   Judge audit         │
              mention      mơ hồ                   estimate                         ▼
                                                                          HÀNG ĐỢI REVIEW (người)
 mọi bước: ledger (input hash × processor version) → chỉ việc đã đổi mới chạy lại
```

### 1. Discover

- **Nội dung (TikTok):** nhóm query (chung, category, trải nghiệm, đối tượng, ràng buộc, xu hướng) → thu video mới, caption, hashtag, comment (có giới hạn). Ngừng mở rộng một nhóm khi số ứng viên mới mỗi lô xuống dưới ngưỡng.
- **Inventory (Google Places):** lưới category × khu vực, không ngưỡng rating → Place ID làm ứng viên; nội dung vào provider store. Địa điểm inventory chưa có match TikTok sẽ kích hoạt một lần tìm ngược trên TikTok theo tên.
- Vùng (bounding box, lưới, category, query mồi) là **config**. Thêm thành phố = thêm một file config.

### 2. Extract (theo video)

Tải tạm → segment (theo cảnh + khoảng lặng ASR) → transcript ASR → 1–2 keyframe mỗi segment → Extractor trả `visible_text` (nguyên văn) + `visual_summary` → xóa video. Giữ transcript, segment, keyframe nhỏ, URL embed.

Sau đó Extractor đọc caption + transcript + visible text và trả các mention địa điểm, mỗi mention có span, loại đề xuất (`POI` cho một cơ sở có tên, `ZONE` cho khu vực / con đường / cảnh quan hoạt động), và mọi quan hệ không gian được **nói rõ** trong văn bản ("ngay cạnh", "cách 2 km").

### 3. Resolve

```text
mention → chuẩn hóa (bỏ quán/tiệm/cafe…, giữ dạng có dấu + không dấu làm alias)
  → Google Text Search trong vùng → code chấm điểm:
      độ giống tên/alias · khớp category · nằm trong vùng · quan hệ được nói rõ
  điểm ≥ T và cách biệt ≥ M      → POI (RESOLVED)
  có ứng viên nhưng chưa rõ      → AMBIGUOUS → Judge chọn một phương án có sẵn hoặc bỏ phiếu trắng
                                  (lựa chọn của Judge vẫn phải qua ngưỡng sàn T_min)
  khu vực / con đường / cảnh quan → ZONE (hình học = buffer / hành lang quanh các POI liên quan, code tính)
  còn lại                        → UNRESOLVED (giữ lại, không phục vụ, liệt kê trong review)
```

- `entity_id` là vĩnh viễn; Google Place ID là `ExternalIdentifier` có lịch sử, làm mới mỗi 12 tháng.
- Gắn nguồn với entity ở mức segment khi mention có timestamp; mức video khi video chỉ nói về một entity; nếu không thì gắn video với từng entity nhưng không gán comment nào cho riêng một entity.
- **Theo yêu cầu (online):** tên người dùng nhập chạy qua cùng bộ matcher. Chắc chắn → trả entity và xếp hàng làm giàu dữ liệu. Không chắc → người dùng tự chọn. Những gì người dùng gõ không bao giờ là bằng chứng.

### 4. Observe

Mọi nguồn thành `Observation`; không gì ghi thẳng vào entity.

- **Segment** (Extractor): feature id + value + span + context.
- **Comment:** rule bỏ comment chỉ có emoji / trùng lặp → Extractor, mỗi call một lô comment của một video, trả cho từng comment: có liên quan không, entity đích (chọn trong các entity đã gắn với video, hoặc không có), feature + value + stance + context, với chính comment làm span. Tên địa điểm mới tìm thấy trong comment quay lại bước Resolve.
- **Trang official:** website lấy từ bản ghi Google = `verified`; tìm qua search và khớp tên = `probable`; còn lại không dùng. Chỉ tải các loại trang trong whitelist (about, giờ, giá, vé, đặt chỗ, quy định, tin tức, liên hệ). Extractor trích nhận định `fact_key` kèm span.
- **Context** trên mọi observation: `time_of_day`, `day_type`, `weather` (theo lời nguồn, không bao giờ là thời tiết thực tế), mỗi cái là enum hoặc `unknown`. "7h sáng hôm đó đông lắm" → `crowd = high`, `time_of_day = morning`, không phải `crowd = high` cho địa điểm.
- Feature id ngoài ontology được ghi là `proposed_feature` để review; build vẫn tiếp tục.

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
- Hình học ZONE nằm trong vùng và bao các POI liên quan.
- Fact / signal / estimate chỉ do rule tổng hợp ghi; nội dung Google chỉ nằm trong provider store.

**Kiểm tra span.** Với observation tác động cao (mọi `fact_key`, mọi feature `verify: always` — an toàn, tiếp cận, đối tượng phù hợp), một call Extractor riêng chỉ thấy span (± 1 câu / ± 5 s) và giá trị + bối cảnh được khẳng định, rồi trả lời `supports | contradicts | insufficient`. Khác `supports` → bỏ, kèm lý do.

**Định tuyến rủi ro** theo entity, sau mỗi lần build lại:

| Rủi ro | Điều kiện (code) | Hướng đi |
|---|---|---|
| Thấp | Qua mọi gate, không xung đột, không có giá trị `verify: always`, không do Judge chọn match, `independent_sources` ≥ 2 cho mọi signal được phục vụ | **Tự publish** |
| Cao | Có xung đột, match do Judge chọn, ZONE mới, có giá trị `verify: always`, có signal được phục vụ chỉ từ một nguồn, processor version đổi | **Judge audit** |

**Judge audit** nhận một hồ sơ gọn (≤ 8k token): bản ghi, với mỗi giá trị là các thành phần confidence và phân phối giá trị, 3 trích đoạn ủng hộ + 3 phản bác + 2 ngẫu nhiên, các xung đột được giữ, và tên các địa điểm lân cận. Judge trả `pass` hoặc finding (`unsupported | contradiction | wrong_link | stale`) kèm id bằng chứng. Judge không bao giờ sửa giá trị.

```text
Judge pass                           → publish
Judge finding / bỏ phiếu trắng       → khía cạnh không được phục vụ → hàng đợi review
giá trị verify: always (mọi trường hợp) → chỉ publish sau khi người Accept
```

Audit chỉ chạy lại khi fingerprint của hồ sơ (bản ghi + tập bằng chứng + version rule) thay đổi.

### 7. Publish và review

**Serving record** (do `online/retrieval` đọc): entity id, loại, hình học, category; trường lọc được (giá, giờ, effort, trong nhà/ngoài trời, khoảng thời gian tham quan); feature kèm tham chiếu bằng chứng; thành phần confidence; coverage và trạng thái theo khía cạnh; `usable_as` (`experience | meal | anchor | backup`, tính từ category + coverage — nhà hàng chỉ có từ inventory là `meal/anchor/backup`, không phải `experience`).

**Trạng thái:** bộ chung cho corpus, Admin Web, User Web — `docs/CORPUS.md` §6. `NEEDS_REVIEW` và `DISABLED` không bao giờ được phục vụ.

**Hàng đợi review** (bước duy nhất có người, sau mỗi build):

- Nội dung: mục `NEEDS_REVIEW`, giá trị `verify: always`, ứng viên `UNRESOLVED`, `proposed_feature`, và một **mẫu ngẫu nhiên ẩn (~5%)** các giá trị đã tự publish và đã qua Judge, không đánh dấu.
- Sắp theo rủi ro × lưu lượng (địa điểm planner hiển thị nhiều nhất lên trước).
- Với mỗi mục, người duyệt thấy giá trị, thành phần confidence, bằng chứng (embed segment, comment, trích đoạn official), và finding của Judge. Thao tác: **Accept · Disable · Report error** (trên một giá trị, liên kết, hoặc loại). Không sửa tự do giá trị.
- Mỗi quyết định được lưu thành nhãn. Nhãn dùng để hiệu chỉnh ngưỡng và prompt, và tạo thành bộ regression mà prompt hoặc model mới phải qua trước khi output của nó được tự publish.

### 8. Refresh

Ledger `PipelineArtifact`: `source_id, stage, input_hash, processor, processor_version, prompt_hash, ontology_version, status, usage (tokens, cost, latency)`. Một bước chỉ chạy lại khi input hoặc processor của nó đổi; đổi ontology thì chạy lại từ observation trở xuống, không chạy lại ASR.

Job định kỳ: làm mới provider store; làm mới Google ID (12 tháng); tải lại nguồn quá hạn; query xu hướng; quét inventory tìm chỗ mới mở. Observation mới được thêm, cũ được giữ; entity bị ảnh hưởng được tổng hợp lại, định tuyến lại, và publish lại.

## Data model

```text
Feature            id, group (experience|environment|effort|suitability), value_type,
                   contexts[], verify (always|sampled), labels_vi/en + synonyms   — có version
TikTokVideo        video_id, url, embed_url, author_id, caption, hashtags, published_at
VideoSegment       segment_id, video_id, start_s, end_s, transcript, visible_text, visual_summary, keyframe_ref
Comment            comment_id, video_id, parent_id, author_id, text, published_at
OfficialPage       page_id, url, page_type, official_status, fetched_at, text
ProviderPlace      external_id, payload, fetched_at, next_refresh_at        (provider store)
Mention            mention_id, raw_name, proposed_type, span, relations[]
Candidate          candidate_id, normalized_name, mention_ids[], origin (tiktok|inventory|user),
                   status (RESOLVED|AMBIGUOUS|UNRESOLVED), options[], match_score
Entity             entity_id, type (POI|ZONE), name, aliases[], category, geometry?, state
ExternalIdentifier entity_id, provider, external_id, status (active|replaced), last_verified_at
EntityLink         target (video|segment|comment|page), target_id, entity_id, match_score
Observation        id, entity_id, feature|fact_key, value, stance, context, source_type,
                   source_id, span, extractor+version, support_score?
Fact|Signal|Estimate  entity_id, key, value|distribution|range, conflict?, confidence{4}, observation_ids[]
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
- **Ngân sách mỗi build:** call Judge, call Google. Hết ngân sách thì build dừng gọn và chạy tiếp ở lần sau; entity rủi ro cao chưa được audit giữ `NEEDS_REVIEW` (không bao giờ tự publish).
- Báo cáo mỗi build: chi phí và token theo model, **chi phí trên mỗi entity được phục vụ**, tỷ lệ tự publish, kích thước hàng đợi review.

## Đo chất lượng

Không có bộ benchmark gán nhãn tay từ đầu; nhãn đến từ review.

| Chỉ số | Nguồn |
|---|---|
| Precision của giá trị tự publish | Mẫu ngẫu nhiên ẩn trong review |
| Precision của giá trị qua Judge | Mẫu ngẫu nhiên ẩn trong review |
| Tỷ lệ Judge bắt lỗi | Tỷ lệ lỗi người xác nhận mà Judge đã đánh dấu |
| Tỷ lệ nhận định không có căn cứ | Phải bằng 0 — gate + test bất biến |
| Coverage | Theo khía cạnh; độ chồng lấn nội dung vs inventory theo category × khu vực |
| Chi phí | Trên mỗi entity được phục vụ, theo model |

Nếu precision lấy mẫu của một bước rơi dưới ngưỡng, bước đó ngừng tự publish (entity của nó chuyển sang Judge) cho đến khi hiệu chỉnh lại.

**Test bất biến:** không observation nào thiếu span; không fact / signal / estimate nào thiếu observation hoặc do model ghi; xung đột không bao giờ bị làm phẳng; `unknown` không bao giờ thành `false`; nội dung Google chỉ nằm trong provider store; cùng được nhắc không bao giờ tạo quan hệ; `NEEDS_REVIEW` và `DISABLED` không bao giờ được phục vụ.

## Mở rộng

- Thành phố mới = config vùng mới + query mồi; code không đổi.
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
| 2. Discover + extract + resolve | Crawl, lưới inventory, media, mention, matcher, ZONE, Judge chọn match mơ hồ, API theo yêu cầu | Crawl lặp lại được; báo cáo precision resolve trên mẫu review |
| 3. Observe + aggregate | Observation từ segment / comment / official, kiểm tra span, fact / signal / estimate, coverage | Build lại từ observation cho kết quả như cũ; bất biến pass |
| 4. Route + publish + review | Định tuyến rủi ro, Judge audit, serving index, hàng đợi review có mẫu ẩn, job refresh | Một lần build đầy đủ chạy không cần người; báo cáo precision mẫu review và chi phí mỗi entity |

## Sai lệch cho bản demo

| Sai lệch | Demo | Cách sửa khi thương mại |
|---|---|---|
| Provider store của Google | Lưu và làm mới nội dung Places | Điều khoản Google chỉ cho lưu Place ID (lat/lng ≤ 30 ngày): lấy theo request; ranh giới provider store cô lập thay đổi này |
| Thu thập TikTok | Scraper tự viết | Truy cập có license sau cùng adapter |
| Hình học ZONE | Buffer / hành lang quanh POI liên quan | Dữ liệu bản đồ |

## Đầu vào cần có

`GOOGLE_MAPS_API_KEY` và API key của các model đang cấu hình trong `.env`; Cloudflare tunnel trên máy build cho call đi ra; trần ngân sách hàng tháng cho Places và Judge; một người duyệt.

