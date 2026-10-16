# Đề xuất chuẩn hóa dữ liệu hiện có và contract toàn luồng

Ngày đối chiếu: **14/10/2026, giờ Việt Nam**. Trạng thái: **thiết kế để thảo luận; chưa triển khai**.

File làm việc tạm theo `RULE.md` §0.1, không thay thế tài liệu chính thức. Sau khi triển khai, gộp phần hiện trạng vào tài liệu của từng module rồi xóa spec này. Lượt tạo tài liệu chỉ đọc dữ liệu và code, không chạy migration, build, model hay crawl.

## 1. Mục tiêu và phạm vi đã thống nhất

Chuẩn hóa dữ liệu và semantics đang có để Corpus → Trip Understanding → Decision → Planning dùng cùng định danh, phiên bản, đơn vị và quy tắc bằng chứng. Giữ nền JSON offline + LanceDB online, PostgreSQL cho dữ liệu người dùng. Chưa chuyển toàn corpus sang SQL và chưa viết lại solver.

**Chỉ dùng dữ liệu đã lưu trên máy:** raw, observation, nhãn Judge/người duyệt, intel, serving, ảnh/frame/transcript, metadata và vector có sẵn.

Trong bước này:

- Không crawl, tải lại media, gọi nguồn ngoài hoặc dịch vụ live.
- Không chạy lại Extractor/Judge/ASR; không sinh mô tả, alias, claim hoặc vector bằng model.
- Cho phép chuẩn hóa bằng code tất định, kiểm tra tham chiếu, tái lập aggregate/serving và đóng gói snapshot từ đầu vào có sẵn, sau khi triển khai công cụ an toàn.
- Không thay ID hiện hành hàng loạt; không gộp địa điểm bằng fuzzy match; không tự khôi phục backup vào tập active.
- Không xóa/di chuyển dữ liệu gốc ở đợt đầu. Archive/quarantine trước hết là phân loại trong manifest.
- Thiếu dữ liệu giữ `unknown`; dữ liệu lỗi giữ nguyên bản gốc và ghi lý do không phục vụ.
- Physical constraint không được nới. User Profile vẫn là prior; online không ghi Place Intelligence.

Quy ước thời gian người dùng đã chọn: nếu biết giờ đến/đi nhưng chưa chỉ định giờ check-in/check-out, lấy **check-in sau giờ đến 60 phút**, **check-out trước giờ đi 60 phút**, có nhãn ước lượng và sửa được. Nếu di chuyển/đệm thực tế cần hơn 60 phút, Planning phải báo xung đột. Không suy giờ đến/đi từ giờ khách sạn khi chưa biết.

## 2. Căn cứ và cách xử lý tài liệu mâu thuẫn

Đọc tài liệu/spec mới để xác định hướng sản phẩm; đối chiếu schema, đường ghi/đọc và test để xác định chức năng thực sự có. Ngày sửa file chỉ là tín hiệu, không chứng minh một spec đã triển khai.

| Tài liệu | Dùng để |
|---|---|
| [RULE.md](../../../RULE.md) | Ngôn ngữ, nguồn sự thật, ranh giới, quyền ghi, tài liệu tạm |
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | Bốn module và bất biến toàn hệ thống |
| [CORPUS.md](../../CORPUS.md) | Nguồn, observation, aggregate, serving, snapshot, semantic index |
| [TRIP_UNDERSTANDING.md](../../TRIP_UNDERSTANDING.md), [QA](../../TRIP_UNDERSTANDING_QA.md) | Trip State, Search Input, semantics và khoảng trống contract |
| [PLACE_DECISION.md](../../PLACE_DECISION.md), [PLANNING.md](../../PLANNING.md) | Sàng lọc, tuyển chọn, bàn giao, solver và kiểm chứng |
| [AGENT_HARNESS.md](../../AGENT_HARNESS.md) | Journey, revision, receipt, adapter public |
| [Spec snapshot 13/10](2026-10-13-corpus-snapshot-design.md) | Hướng snapshot đã có code, số đo và việc còn thiếu |
| [Spec Trip mới](2026-10-13-trip-understanding-redesign-design.md) | Hướng hỏi ít; nhiều mục là đề xuất, chưa phải contract runtime |
| [ONLINE_FLOW_OPTIMIZATION.md](../../plans/ONLINE_FLOW_OPTIMIZATION.md) | Canonical cache key, preview và job nền |

Mâu thuẫn cần giải quyết trong tài liệu chính thức khi code được chỉnh:

- Architecture §8 và Decision §5 còn nói chỗ ở không vào Place Intelligence; code hiện đã phục vụ nhóm `stay`, Planning đọc corpus. Giữ thiết kế mới; vẫn tách giá tham khảo khỏi availability/giá ngày đi chưa biết.
- Trip có đoạn nói `entry_point`/`exit_point` neo ngày đầu/cuối; Planning hiện bắt đầu/kết thúc mọi ngày ở chỗ ở. Phải ghi đúng chế độ hiện hành; chuẩn hóa không tự thêm hành trình sân bay/bến xe chưa có.
- Spec snapshot mong dùng lại công thức hiện có; `snapshot/tables.py` thực tế sao chép một số công thức Decision/requirements để tránh phụ thuộc ngược. Test đang kiểm tương đương; đây là phần cần quản lý version hoặc gom đúng tầng public.
- Spec Trip mới dùng check-in/check-out làm mốc chuyến. Áp quy ước ±60 phút ở §1 nhưng giữ giờ khách sạn và giờ vận tải là các ý nghĩa riêng.

## 3. Những gì hiện có

### 3.1 Kho dữ liệu và đường code

Các đường dưới đây tính từ gốc repo. Số lượng là ảnh chụp hiện trạng, không phải hằng số hay chỉ tiêu sau migration.

| Lớp | Vị trí dữ liệu | Vị trí code chính | Hiện trạng |
|---|---|---|---|
| Inventory Maps | `data/gmaps/list/dalat.json`, `dalat_stay.json` | [listing.py](../../../src/corpus/crawl/gmaps/listing.py), [files.py](../../../src/corpus/crawl/common/files.py) | 1.779 dòng địa điểm + 1.524 dòng chỗ ở; **3.298 FID duy nhất**, 5 FID nằm trong cả hai list |
| Raw Maps | `data/gmaps/places/<fid_dir>/` | [crawl.py](../../../src/corpus/crawl/gmaps/crawl.py) | 6.111 `place.json`; có `reviews.json`, `photos.json`/ảnh, `menu.json`/ảnh tùy nơi |
| Raw TikTok | `data/tiktok/videos/<video_id>/`, `place_filter/`, `place_poi/`, `poi_crawl/` | `src/corpus/crawl/tiktok/` | Video metadata, comment/reply, transcript, frame, POI và mapping theo nhiều bước |
| Official | `data/official/pages/`, `observations/` | [pages.py](../../../src/corpus/crawl/official/pages.py), `src/corpus/observe/official/` | Chữ trang đã lưu, URL, thời điểm; 221 file trang theo kiểm kê trước |
| Observation | `data/{gmaps,tiktok,official}/observations/`, `data/gmaps/photo_observations/` | [observe public API](../../../src/corpus/observe/__init__.py) | Format chung: feature/value/context, source, author, thời điểm, span, extractor, ontology version |
| Nhãn/merge | `data/review/` | `src/corpus/review/`, `src/corpus/judge/` | Quyết định người, nhãn Judge, merge và trạng thái nơi; là đầu vào của aggregate/serving |
| Intelligence | `data/intel/places/`, `summary.json` | [aggregate/place.py](../../../src/corpus/aggregate/place.py) | 3.280 nơi; summary ghi 861 file đầu vào khác ontology version hiện hành |
| Serving build | `data/serving/places.json` | [record.py](../../../src/corpus/serving/record.py), [run.py](../../../src/corpus/serving/run.py) | 3.208 record; 72 nơi bị loại bởi đóng cửa/đổi cơ sở |
| Runtime snapshot | `data/snapshot/current`, `<version>/dalat/*.lance` | [snapshot public API](../../../src/corpus/snapshot/__init__.py), [compile.py](../../../src/corpus/snapshot/compile.py), [read.py](../../../src/corpus/snapshot/read.py) | Active `20261013T201524`; 7 bảng; giữ 3 version theo config |
| Semantic index | `data/index/current`, `<version>/`; vector `.npy` + `.json` theo nguồn | [index public API](../../../src/corpus/index/__init__.py), [vectors.py](../../../src/corpus/index/vectors.py), [compile.py](../../../src/corpus/index/compile.py), [query.py](../../../src/corpus/index/query.py) | Active `20261013T025416`; 1.696 place, 29.820 ảnh/frame, 476.666 span |
| Web projection | `web/public/data/snapshot.json`, `covers.json` | [export_snapshot.py](../../../web/scripts/export_snapshot.py), [pick_covers.py](../../../web/scripts/pick_covers.py) | 3.292 nơi trong snapshot web; export ghép intel/raw và thêm inventory fallback |
| User/journey | PostgreSQL; file session cho CLI/test | [harness/contracts.py](../../../src/harness/contracts.py), [session.py](../../../src/harness/session.py), `migrations/` | PostgreSQL phục vụ dữ liệu người dùng; không phải kho crawl |

`fid_dir` là FID thay `:` bằng `_` cho tên file; không phải một entity ID khác. Gốc dữ liệu runtime lấy từ `DATA_DIR`; các đường trên là gốc `data/` đang kiểm kê.

Serving hiện gồm **1.510 chỗ ở + 1.698 nơi khác**. Semantic index giao với serving được 1.692 nơi không phải chỗ ở và 3 chỗ ở; còn 1 ID index không được serving hiện hành phục vụ. Phần thiếu chủ yếu là chỗ ở; không diễn giải thành “Decision thiếu gần nửa corpus”. Có record trong index không đồng nghĩa nơi đó đủ mọi loại vector/bằng chứng.

### 3.2 Trường dữ liệu và giới hạn có sẵn

| Nhóm | Đã có | Chuẩn hóa được từ dữ liệu hiện tại |
|---|---|---|
| Identity | FID, name, address, lat/lng, category, URL; POI TikTok và merge đã kiểm | ID canonical, mapping ID nguồn, biến thể tên có xuất xứ, nhiều vai trò khi có chứng cứ |
| Operation | Giờ, trạng thái, khoảng giá, giá một đêm tham khảo, vé, crowd theo giờ | Kiểu dữ liệu/đơn vị/timezone, freshness riêng, conflict và nguồn theo field |
| Experience | Feature/signal, distribution, context, số tác giả, coverage | Schema thống nhất; giữ nguyên phiếu, mẫu targeted, owner và confidence |
| Detail | Món, hoạt động, chi phí, giờ đẹp, access… khi đã trích xuất/qua gate | Tham chiếu có kiểu; không suy thêm nội dung từ raw bằng model |
| Media | File local, URL nguồn, tác giả hash, owner, tháng; transcript có segment | Registry media, trạng thái file có/thiếu, quan hệ place đã xác minh |
| Evidence | Observation ID, source ID/type, quote/field/giây, nhãn kiểm tra | Tham chiếu nguồn, kiểm toàn vẹn và truy vết đến artifact gốc |
| Estimate | Duration short/typical/long, effort hint, category default | Ghi rõ nguồn estimate; không nâng default thành fact |
| Vector | `.npy`, model/key metadata, item và index hiện có | Tái liên kết/tái đóng gói vector tương thích; thiếu vector giữ thiếu |

Theo kiểm kê cùng ngày: raw hiện hành có mô tả ở 36/3.298 nơi, giờ Maps ở 1.450 nơi, popular times ở 1.208 nơi. Serving duration có 3.169 record từ `category_default`, 39 từ review. Chuẩn hóa không tự tăng coverage các trường này.

Toàn bộ place-level status của serving hiện là `VERIFIED`, nhưng feature vẫn có `UNCERTAIN`/`OUTDATED`; **status địa điểm không xác minh mọi thuộc tính**.

### 3.3 Đường sử dụng xuyên suốt bốn module

| Module | Code hiện có | Contract/hành vi hiện hành |
|---|---|---|
| Trip | [state.py](../../../src/trip/domain/state.py), [compile.py](../../../src/trip/domain/compile.py), [catalog.py](../../../src/trip/infrastructure/catalog.py), [api/tools.py](../../../src/trip/api/tools.py) | `Catalog.from_snapshot`; `SearchInput` có ontology version, context, hard/soft, activity, time preference, vibe và unmapped |
| Decision | [pipeline.py](../../../src/decision/pipeline.py), [frame.py](../../../src/decision/frame.py), [engine.py](../../../src/decision/engine.py), [output.py](../../../src/decision/output.py) | Bảng vector hóa, memo theo phiên, Cand lazy; Decision Output gồm selection/backup/context/log; không gợi ý `stay` |
| Constraint chung | [requirements public API](../../../src/requirements/__init__.py), [checks.py](../../../src/requirements/checks.py) | Applicability trước evidence; `pass/fail/unknown/not_applicable`, scope, `eq/ne`, unknown policy |
| Planning | [places.py](../../../src/planning/places.py), [build.py](../../../src/planning/build.py), [lodging.py](../../../src/planning/lodging.py), [cache.py](../../../src/planning/cache.py), [engine.py](../../../src/planning/engine.py), [validate.py](../../../src/planning/validate.py) | Đọc serving, cache/repair theo ngày, preview, live context và validator độc lập |
| Harness | [contracts.py](../../../src/harness/contracts.py), [dispatch.py](../../../src/harness/dispatch.py) | Journey revision, module snapshots, receipts; chưa có field `corpus_release_id` trong Journey |

## 4. Vấn đề cần giải quyết và phần đáng giữ

| Vấn đề có bằng chứng | Ảnh hưởng | Hướng sửa |
|---|---|---|
| Raw nhiều hơn inventory active; backup nằm cạnh thư mục hiện hành | Dễ glob/đóng gói nhầm; khó biết một file còn được dùng không | Inventory file và lifecycle manifest; không xóa raw |
| `aggregate.run()` glob thư mục observation theo mẫu, không lấy eligibility trực tiếp từ list | Membership build dựa trên file đang tồn tại | Input list explicit, đối chiếu canonical ID/merge và ngoại lệ; báo mọi thay đổi membership |
| 861 file khác ontology version | Khả năng diễn giải không đồng nhất | Compatibility theo feature/value/rule; giữ version gốc |
| Snapshot/index/web có pointer và phạm vi riêng | Khó truy lại cùng trạng thái; web có thể hiện nơi không eligible cho Decision | Một release manifest; serving view và admin/inventory view tách quyền sử dụng |
| Schema nguồn có text/list/object hoặc field thiếu | Parser phải xử lý legacy ở nhiều consumer | Adapter tất định một lần ở biên offline; schema có kiểu sau adapter |
| Snapshot sao chép công thức role/activity/confidence | Công thức có thể drift khi sửa một phía | Chủ sở hữu public rõ, version/hash công thức; giữ oracle test |
| `lodging.sieve()` chỉ xét `ne`, giữ unknown, chưa dùng semantics chung | Hard constraint của chỗ ở khác các bước còn lại | `requirements` public API, scope `accommodation`, unknown policy rõ |
| Search Input budget là VND/người/ngày; `price_cap()` diễn giải như tiền cả chuyến | Sai trần tiền phòng | Contract đơn vị rõ và test chuyển đổi; chưa suy số phòng/loại phòng |
| Preview key hash cả Decision Output có log | Tính lại vì metadata không đổi lịch; thiếu version dependency ở key ngoài | Canonical planning input + release/config/solver/live fingerprint |

861 là **số file input**, không phải 861 place. Khác ontology version không tự chứng minh claim sai; `OUTDATED` là vấn đề độ mới bằng chứng, không đồng nghĩa schema không tương thích.

Giữ các phần đã có: tách nguồn, observation có span, một tác giả một phiếu, targeted/owner policy, official precedence, label gates, fail-closed, snapshot bất biến, Decision memo/oracle và Planning repair/validator. Không refactor chúng chỉ để đổi hình thức lưu.

## 5. Thiết kế chuẩn hóa đề xuất

### 5.1 Mô hình có kiểu, liên kết bằng ID

Đây là contract đề xuất, không phải bảng/module đã tồn tại. Tái sử dụng trường hiện có trước; chỉ thêm metadata cần cho chuẩn hóa và kiểm toán.

| Contract | Nội dung | Nguồn duy nhất được phép |
|---|---|---|
| `Place` | Canonical ID, identity, eligibility, vai trò được hỗ trợ | Inventory, identity hiện có, merge đã duyệt |
| `SourceRecord` | Source, source ID, file/record pointer, URL, fetched_at, content hash | Raw của chính nguồn đó |
| `EvidenceRef` | SourceRecord ID, record/segment/photo ref, field, quote/timestamp | Span và nguồn đã lưu |
| `Claim` | Observation ID, feature/value/context, author, sample/owner, extractor/ontology/rule gốc, nhãn | Observation đã có + nhãn tương ứng |
| `MediaRef` | ID nguồn, local path/URL, author/date, exists, quan hệ place và mức xác minh | Metadata ảnh/video và mapping hiện có |
| `ServingRecord` | Fact/Signal/Estimate, status/confidence theo field, provenance | Aggregate tất định từ Claim và rule hiện hành |

`Claim` là cách chuẩn hóa observation hiện có, không tạo pipeline trích xuất mới. Một số operation fact đi thẳng từ `place_facts`/provider metadata; không ép chúng thành observation giả hoặc bịa author/quote.

Observation/source payload vẫn nằm trong thư mục của chính nguồn; lớp chung chỉ lưu ID và reference. Không tạo file chung chứa toàn bộ review Maps, comment TikTok và trang official.

### 5.2 Identity, alias và membership

- Dùng FID canonical hiện tại; giữ bảng redirect cho các merge đã có. Không xóa ID nguồn hoặc làm mất khả năng tra lịch cũ.
- 5 FID trùng giữa list trải nghiệm và stay phải có classification conflict hoặc vai trò có bằng chứng. Một FID chỉ có một entity; gợi ý stay/trải nghiệm theo policy rõ, không phụ thuộc thứ tự đọc file.
- Tên khác trong raw có thể ghi thành `name_variant` kèm nguồn. Chỉ phục vụ như alias đã xác minh khi mapping cùng entity đủ căn cứ; caption/transcript chỉ nhắc tên chưa đủ.
- Phân biệt `active_inventory`, `served`, `historical`, `backup`, `quarantined`; historical không đồng nghĩa invalid.
- Không đưa 2.813 raw record ngoài list vào serving chỉ vì chúng có tên/tọa độ. Mọi khác biệt inventory/intel/serving phải có reason và merge reference.
- Nơi được giữ trong journey cũ nhưng không còn eligible hiện hành cần trạng thái không phục vụ/cần kiểm lại; không thay âm thầm bằng nơi gần tên.

### 5.3 Schema, version và missingness

Tách riêng `schema_version`, `ontology_version`, `normalizer_version`, `aggregate_rule_version`, `release_id`. Giữ `extractor`, `prompt_hash` và ontology gốc; migration không đổi chúng thành version mới như thể đã chạy lại model.

Compatibility policy tối thiểu:

| Tình huống | Xử lý tất định |
|---|---|
| Đổi tên field nhưng ý nghĩa/giá trị không đổi | Adapter chuyển, lưu nguồn và migration ID |
| Feature/value vẫn giữ nguyên nghĩa qua version | Cho phép sử dụng với version gốc + compatibility result |
| Đổi nghĩa hoặc điều kiện verification | Chưa đủ căn cứ thì không phục vụ claim liên quan; giữ ở quarantine |
| Feature mới không có trong observation cũ | `unknown`; không bổ sung bằng heuristic/model |
| Date/price/hour không parse được | Giữ raw, normalized value `null`, ghi issue |
| Metadata version không có | Ghi `legacy_unversioned`; chỉ nhận phần contract chứng minh được bằng field/nguồn cụ thể |

Missingness đề xuất: `not_collected`, `not_reported`, `missing_field`, `conflicting`, `invalid`, `incompatible_version`, `missing_source`, `unsupported`. Chỉ dùng `not_reported` khi biết phần nguồn đó đã được đọc và không nói; nếu không đủ căn cứ dùng `missing_field`. `OUTDATED` và `not_applicable` tiếp tục là trạng thái/semantics riêng.

### 5.4 Chuẩn hóa đơn vị và thời gian

- Giá: giữ amount/currency/unit/scope, đối tượng áp dụng, ngày quan sát, nguồn. Vé trẻ em, vé người lớn, tiền/người, tiền/đêm không gộp thành một scalar.
- Budget: giữ số tiền/phạm vi user nói trong Trip; giá trị bàn giao có đơn vị rõ. Chỉ tính ngân sách cả nhóm/cả chuyến khi biết đủ days/people và scope; chưa rõ phần gồm tiền phòng thì giữ chưa biết.
- Giá stay hiện chưa bảo đảm cùng đơn vị loại phòng/công suất. Không suy phòng/đêm thành người/đêm; không tuyên bố còn phòng hay giá đúng ngày đi.
- Giờ: raw giữ nguyên; normalized dùng thứ/ngày và khoảng giờ có timezone. `null` = chưa biết, `[]` chỉ nghĩa đóng cả ngày khi nguồn khẳng định. Không dùng parse failure hay popular-times 0 để tạo fact đóng cửa mới.
- Thời điểm crawl/build là timestamp UTC; lịch chuyến dùng timezone `Asia/Ho_Chi_Minh`; date quan sát chỉ có tháng giữ độ chính xác tháng, không bịa ngày.
- Duration: giữ short/typical/long và nguồn `reviews/category_default`; không nội suy thành thời lượng đã xác minh.
- Quy ước ±60 phút dùng phép tính thời điểm đầy đủ, xử lý qua nửa đêm/ngày đầu-cuối. Thiếu giờ vận tải thì giữ unknown hoặc dùng default được công bố, không gắn nhãn user.

### 5.5 Evidence và nhãn kiểm duyệt

- Giữ nguyên observation ID khi claim và span không đổi để nhãn Judge/người không bị mất.
- Nếu cần ID mới do schema, lưu mapping một-một cùng hash claim; không chuyển nhãn sang claim đã đổi nghĩa.
- Kiểm source pointer, review ID, quote/segment/photo và file local. Nếu nguồn bị thiếu, ghi `missing_source`; không lấy backup khác làm bằng chứng thay thế tự động.
- Kiểm quote theo đúng gate/chuẩn hóa nguồn hiện hành; không thêm bước sửa quote để làm nó khớp nguồn.
- Giữ `sample`, author hash, owner và source type: bỏ các trường này sẽ làm thay đổi phiếu/mention rate.
- Giữ xung đột và official precedence, phân biệt `observed_at` với `fetched_at`; build mới không làm bằng chứng trẻ lại.
- Vector/text snippet không nâng claim thành VERIFIED. Observation chưa qua label gate không được index trình bày như bằng chứng được phục vụ.

### 5.6 Một release dùng cho toàn hệ thống

Đề xuất thêm `data/releases/<release_id>/manifest.json` và `data/releases/current`. Đây là đường mới dự kiến, chưa có code đọc/ghi. Các artifact tiếp tục ở nơi hiện hành hoặc staging được định danh; manifest tham chiếu đúng version/hash, không cần sao chép media.

Manifest gồm:

- Schema/ontology/normalizer/aggregate-rule versions; config/code fingerprint cần để tái lập.
- Danh sách input theo nguồn, hash, số record và lifecycle; raw payload vẫn tách nguồn.
- Mapping canonical ID/redirect và eligibility reasons.
- Artifact version/hash: intel, serving, runtime snapshot, semantic index, web projection.
- Quality report: missingness, incompatibility, orphan, coverage, excluded và thay đổi so baseline.
- Semantic coverage tách non-stay/stay, photo/span/style; `ready/partial/unavailable` theo từng loại.

Chỉ đổi pointer sau khi toàn bộ artifact được chọn đã kiểm xong. Semantic index có thể partial nếu manifest nói rõ phần thiếu; không chặn serving chỉ vì chưa có vector cho stay. Mọi semantic hit phải nằm trong eligible ID của release và giữ mức hợp lệ của evidence.

Journey lưu `corpus_release_id`; adapter truyền release qua public API đến Trip/Decision/Planning. Phiên cũ thiếu field dùng chế độ legacy có kiểm tra và thông báo, không giả vờ biết snapshot gốc. Nâng release của journey là revalidation có diff, không tự sửa selection.

Retention phải giữ artifact đang được journey/deployment tham chiếu. Không chạy pruning hiện tại trên staging hoặc xóa version pinned chỉ để giữ đúng 3 bản.

### 5.7 Tái sử dụng index và web

- Đọc vector `.npy`/metadata hoặc index hiện có; giữ model, dimension, item ordering và liên kết input. Tái đóng gói bằng code, không tính embedding mới.
- Chỉ dùng vector khi xác định được nó thuộc đúng media/span và model/không gian tương thích. Metadata không đủ thì báo gap, không tuyên bố vector mới hợp lệ.
- Claim bị loại vì nhãn/version phải bị loại khỏi evidence retrieval tương ứng; nếu vector còn dùng cho gợi ý thì kết quả không được trình bày như fact.
- Search tên có thể thêm bảng normalized name/alias từ dữ liệu sẵn có; không cần model. Full-text/ANN là tối ưu sau benchmark, không phải điều kiện hoàn thành chuẩn hóa.
- Web serving view chỉ đọc cùng eligible projection. Admin có thể xem raw/inventory/quarantine riêng, có nhãn rõ. Không cắt quyền Admin để ép số đếm web bằng serving.
- Covers/thumbnails dùng file hiện có; ảnh thiếu hiện placeholder. Không chạy công cụ chọn ảnh có gọi model trong bước này.

## 6. Nâng cấp contract và code hiện tại

| Việc đề xuất | Vị trí cần chỉnh khi triển khai | Cách làm giới hạn |
|---|---|---|
| Schema và adapter chuẩn hóa offline | `src/corpus/observe/`, `aggregate/`, `serving/`; bổ sung contract public trong corpus | Parse legacy tại biên; consumer nhận schema hiện hành; không sửa raw |
| Input manifest/eligibility | `src/corpus/aggregate/place.py`, `crawl/common/files.py`, `serving/run.py` | Bỏ phụ thuộc glob không kiểm membership; giữ nguồn/canonical và issue report |
| Compatibility/version | `config/ontology.yaml`, `src/corpus/ontology.py`, `observe/__init__.py`, aggregate | Mapping tất định có version; không bump ontology chỉ vì đổi format file |
| Release compiler/reader | `src/corpus/snapshot/compile.py`, `read.py`, `index/compile.py` | Compile staging và resolve manifest; truyền version explicit, giữ API cũ qua adapter |
| Pin release toàn journey | `src/harness/contracts.py`, `dispatch.py`; public `Tools` từng module | Một journey/một release; legacy restore có kiểm tra |
| Budget có đơn vị | `src/trip/domain/state.py`, `budget.py`, `compile.py`; `src/planning/lodging.py`, `objectives.py` | Giữ raw user intent, phép quy đổi có kiểu; không suy phòng/capacity |
| Giờ và ±60 phút | `src/trip/domain/state.py`, `compile.py`, `logistics.py`; `src/planning/frame.py`, config liên quan | Tách ý nghĩa vận tải/khách sạn/khung chơi; provenance default và kiểm feasibility |
| Hard constraint stay | `src/planning/lodging.py`, `src/requirements/__init__.py` | Dùng public `hard_result/allowed`, đúng applicability và unknown policy |
| Canonical planning input | `src/decision/output.py`, `src/planning/engine.py`, `cache.py` | Bỏ log/timestamp không ảnh hưởng lịch khỏi key; thêm release/config/solver/live fingerprint |
| Projection web/đóng gói | `web/scripts/export_snapshot.py`, `scripts/pack_data.py` | Dùng release manifest/allowlist; tách serving/admin/backup; không thay dữ liệu gốc |
| Skill và tool | `src/{trip,decision,planning}/skills.yaml`, runtime skill của Trip, public adapter | Chỉ hướng dẫn đọc contract/unknown đúng nghĩa; không thêm quyền ghi corpus |

`skills.yaml` hiện là capability/workflow declaration; runtime skill diễn giải yêu cầu nằm ở `src/trip/runtime_skills/interpret-trip-requirements/SKILL.md`. Chuẩn hóa không cần thêm supervisor agent hay để LLM trực tiếp duyệt filesystem.

Code/module mới chỉ thêm khi cần cho các việc trên. Không tạo framework repository/plugin/migration tổng quát chưa có consumer. Public boundary phải cho phép corpus không import nội bộ Decision/Planning.

## 7. Trình tự triển khai đề xuất

Đây là trình tự để lập kế hoạch sau, chưa phải lệnh đã có hoặc tác vụ đã chạy.

1. **Chụp baseline đọc-only:** inventory file, versions, hash và số đếm; lưu các output mẫu xuyên Trip → Decision → Planning với live/LLM stub. Tách nội dung corpus khỏi dữ liệu tài khoản.
2. **Báo cáo dry-run:** validation schema, duplicate ID, nguồn thiếu, compatibility, membership, budget/time/constraint discrepancies. Không viết đè input hay pointer.
3. **Adapter và schema có kiểu:** xuất bản chuẩn hóa vào staging riêng. Giữ claim ID/nhãn/source lineage; chạy lại cho cùng input phải cùng kết quả ngữ nghĩa.
4. **Build artifact từ dữ liệu có sẵn:** aggregate/serving/snapshot ở staging; tái dùng vector; tạo web projection và manifest. Không gọi CLI `all/build/observe/index vectors` hoặc công cụ có thể gọi model/network.
5. **Đối chiếu baseline:** phần chỉ đổi format phải tương đương; thay đổi hành vi do sửa semantics có expected diff và regression test. Liệt kê mọi place/claim bị bỏ và lý do.
6. **Tích hợp contract public:** pin release, budget/time có đơn vị, stay constraints và cache key. Test legacy restore, undo/redo và handoff.
7. **Chuyển pointer có kiểm chứng:** chỉ sau khi report đạt tiêu chí; giữ pointer/version cũ để rollback. Không xóa raw, backup hoặc artifact pinned trong đợt này.

Không gọi thẳng `corpus aggregate/serving/snapshot` trên gốc dữ liệu hiện hành để thử migration: aggregate có thể xóa intel dẫn xuất không thuộc build; snapshot compiler đổi `current` và pruning version. Cần root staging và chế độ publish tách biệt trước.

## 8. Đo và tiêu chí chấp nhận

### 8.1 Tính đúng và bảo toàn

- Zero request tới nguồn ngoài; zero call LLM/ASR/Embedder; không tải hoặc crawl dữ liệu.
- Không thay raw/observation/nhãn gốc; đối chiếu content hash trước/sau. Staging/report là đầu ra riêng.
- Mọi place served có canonical ID/eligibility reason; mọi evidence phục vụ có nguồn hoặc trạng thái thiếu minh bạch.
- Không tăng VERIFIED bằng việc đổi format/version. Unknown/conflict/targeted/owner/freshness giữ đúng semantics.
- Các phép đổi tương đương có oracle; các thay đổi chủ đích có diff trước/sau và test nghiệp vụ, không dùng oracle cũ để giữ lỗi.
- Ngân sách được kiểm đơn vị; giờ qua nửa đêm được kiểm; hard constraint stay cùng semantics với Decision/Planning khi cùng applicability.
- Same planning input + same dependency versions → cùng cache key; log đổi không làm mất hit; release/live/config/constraint đổi phải invalidate.
- Journey restore không trộn release; semantic/admin data không vượt eligibility của consumer.
- Chạy chuẩn hóa lần hai không nhân đôi entity/claim; rollback pointer trở lại release cũ không cần chỉnh raw.

### 8.2 Test và benchmark sẵn có để mở rộng

| Nhóm | Vị trí |
|---|---|
| Snapshot/schema và công thức | `tests/snapshot/test_snapshot.py`, `test_tables.py` |
| Serving/detail/menu | `tests/serving/test_serving.py`, `test_serving_details.py`, `test_dishes.py` |
| Trip nạp snapshot và scope | `tests/trip/test_catalog_snapshot.py`, `test_requirement_scope.py` |
| Decision tương đương | `tests/decision/test_equivalence.py`, `reference.py` |
| Planning scope/consistency/boundary | `tests/planning/test_planning_requirement_scope.py`, `test_planning_consistency.py`, `test_planning_boundaries.py` |
| Handoff/restore | `tests/harness/test_dispatch.py`, `test_tools.py` |
| Web projection | `tests/web/test_export_snapshot_details.py` |
| Corpus/Decision latency | `src/bench/latency.py`; kết quả `data/bench/latency/` |
| Planning thuần và sửa lịch | `tests/planning/bench_routes.py`, `bench_edits.py`; bối cảnh số đo ở `docs/PLANNING_PERFORMANCE.md` |

Test/benchmark triển khai chạy trên root tạm và fixture hoặc bản sao chỉ đọc của dữ liệu; live lookup dùng stub, không dùng production journey. Báo riêng cold/warm, p50/p95/p99, memory, cache hit, migration time và dung lượng staging. Đối chiếu cùng input/config/máy; không cam kết speedup trước số đo.

Trong bước này, đo end-to-end tách retrieval, model, solver, live lookup, persistence; phần model/live dùng stub để chuẩn hóa chạy offline. Độ trễ production thật là đo riêng nếu được cho phép sau.

## 9. Kết quả có thể đạt và những gì vẫn thiếu

Có thể đạt từ dữ liệu hiện tại: inventory rõ, schema thống nhất, traceable claim/nhãn, loại bỏ đường đọc nhầm legacy, release chung, semantics budget/time/constraint đúng và cache ít tính lại. Các con số đầu vào/đầu ra có lý do kiểm toán.

Vẫn thiếu nếu nguồn chưa có: alias đã xác minh, duration thực tế, món/dietary/accessibility claim mới, giờ ngày lễ, giá/availability ngày đi, media bị mất và vector chưa tính. Những phần đó tiếp tục hiển thị unknown/partial; không phải lý do để tự crawl hoặc gọi model trong scope này.

Thứ tự ưu tiên: **inventory + contract/semantics → staging migration và release → tích hợp public API → đối chiếu chất lượng/hiệu năng**. Các ý tưởng hỏi ít, agent reasoning sâu, ANN hoặc đổi database là bước thảo luận tiếp theo, không điều kiện của đợt chuẩn hóa này.
