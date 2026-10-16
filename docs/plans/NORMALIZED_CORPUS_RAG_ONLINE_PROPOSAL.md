# Đề xuất Trip Understanding, Decision và Planning dùng corpus chuẩn hóa / RAG

Ngày cập nhật: 2026-10-15. Đây là đề xuất xuyên module kèm trạng thái triển khai; không phải mọi
chức năng bên dưới đều đã có. **Bàn giao phiên tiếp theo:**
`CORPUS_NORMALIZATION_HANDOFF.md` §Điểm tiếp tục ghi code đã làm, test, pointer và việc còn lại. Phạm vi người dùng chọn: hoàn tất contract normalization trước, rồi dùng dữ liệu
nhất quán để cải thiện ba module; chưa ưu tiên thêm reasoning sâu hoặc redesign toàn sản phẩm.

Thiết kế nền: `../superpowers/specs/2026-10-14-corpus-normalization-design.md`.
Ý tưởng Trip: `../superpowers/specs/2026-10-13-trip-understanding-redesign-design.md`, đặc biệt §12.
Hiện trạng build và regression: `CORPUS_NORMALIZATION_HANDOFF.md`.

## 1. Kết luận đề xuất

Ưu tiên **retrieval nhìn cùng một release, đúng eligible ID và đúng bằng chứng**. Corpus chuẩn
hóa không tự làm một claim đáng tin hơn, không tự bổ sung giờ/giá/món ăn còn thiếu, và không
chứng minh một sở thích của người dùng.

Đề xuất đi theo contract xuyên module, mỗi bước chạy được và kiểm được:

1. Release / lineage chung và pin theo journey.
2. Public retrieval API có kiểu; structured filter, semantic rank và evidence lookup phân vai.
3. Budget / time / activity / unknown được bàn giao nguyên nghĩa.
4. Trip hỏi có ích hơn, Decision giải thích có bằng chứng hơn, Planning dựng lịch có kiểm chứng.
5. Đo chất lượng và độ trễ trước khi tăng quyền hoặc mức reasoning cho Agent.

Cách đổi đồng loạt cả ba module ít bước tương thích hơn nhưng khó tìm nguồn regression và
rollback. Nên chọn cách tích hợp từng contract xuyên cả ba module, thay vì sửa trọn Trip rồi
mới phát hiện Decision / Planning hiểu field khác nghĩa.

## 2. Đã có và còn thiếu

| Phần | Hiện trạng đã kiểm | Việc còn lại |
|---|---|---|
| Corpus offline | Release `r-761a156dfffa4bc5d8bbc30b-6481f4ed` đã build/validate từ dữ liệu/vector đã lưu; 3.208 eligible IDs, chưa publish | Kiểm report và quyết định activation; không dùng staging cũ thiếu manifest |
| Reader mặc định | Có public `corpus.releases.resolve`; Claude đã nối snapshot Trip vào resolver | Factory và CLI Trip đã được Codex nối thêm root đó sang Looks để snapshot/index không chọn release riêng |
| Journey | Có `corpus_binding`, pin/restore/handoff/copy; factory chia sẻ retrieval cùng binding | Legacy null chưa có lineage lịch sử; xem kiểm chứng mới nhất ở handoff |
| Catalog Trip | Đã dùng serving value/status/context/membership; Looks lọc catalog ∩ within | Grounded directions/counterfactual câu mềm mới và benchmark chất lượng |
| Decision | Structured filter; typed evidence read/HTTP và Agent context cùng scope/binding; handoff giữ activity | UI explanation/coverage và benchmark chất lượng |
| Planning | Budget/nights, stay guard/recovery/cache; proposal Agent nhận bounded corpus context | Room occupancy/address unknown safety và benchmark live |

Release ban đầu có đủ 3.208 ID trong metadata index, 29.820 photo row, 205.045 span row (trước rebuild có `served`) và 1.041
nơi có style. Coverage vẫn partial, tách 1.510 stay / 1.698 non-stay. Không dùng câu “gần một
nửa corpus chưa có semantic index” làm số đo coverage mới: ID trong metadata, số row và số
nơi thật sự có vector của từng modality là các mẫu số khác nhau. Vector cho một nơi cũng
không có nghĩa nơi đó có đủ bằng chứng cho mọi feature.

## 3. Một release / một journey

### 3.1 Lifecycle và manifest

Manifest của một release liên kết input theo từng nguồn, normalization, intelligence, serving
snapshot, semantic index và web projection; giữ schema/ontology/config/code fingerprint,
membership, redirects, count và lý do loại. Dùng cơ chế release hiện có, không tạo một hệ
build ID song song.

Raw lịch sử / archive, cache, backup và active artifact có vai trò khác nhau. Runtime chỉ đọc
artifact được release manifest tham chiếu. Không glob raw/backup để lấp chỗ thiếu trong serving;
không xóa lịch sử chỉ để số đếm khớp. Các nguồn vẫn tách thư mục theo `RULE.md`.

Rebuild snapshot và index vào cùng staging, tái dùng vector có model/dimension/provenance
hợp lệ. Coverage thiếu phải báo `partial/unavailable`, không tự sinh embedding mới hoặc tìm
raw khác để biến release thành “đủ”. Activation chỉ sau validation; giữ release đang được
journey/deployment tham chiếu để rollback và restore.

### 3.2 Pin và restore

- Journey mới lưu `corpus_release_id` và region; Tools của Trip/Decision/Planning nhận binding
  qua public contract. Caller không tự cung cấp đường filesystem tùy ý.
- Restore dùng đúng release đã pin. Missing/corrupt release trả lỗi có hướng xử lý; không tự
  đổi sang release mới, sửa selection, hoặc suy ra release cũ từ pointer hiện tại.
- Journey legacy chưa có release ID giữ trạng thái legacy rõ ràng. Chuyển release phải có
  revalidation và diff: ID redirect, evidence, constraints, giá/giờ và draft bị ảnh hưởng.
- Resolve một lần lúc tạo Engine chỉ tránh trộn reader của Engine đó; **chưa thay thế pin
  theo journey**. Trước khi có binding theo journey, activation cần restart toàn harness để
  các module nạp cùng version. Build `publish=false` không cần restart.

## 4. Public retrieval API chung

Đề xuất một public API của Corpus, có typed input/output và scope bắt buộc: release, region,
eligible membership, activity khi cần, limit và cursor. Agent/tool không đọc tùy ý `data/...`.
Tái dùng `corpus.snapshot`, `corpus.index`, `corpus.serving` và `requirements` hiện có; Corpus
không import nội bộ Trip/Decision/Planning, không tạo framework mới chưa có consumer.

| API đề xuất | Chức năng | Output cần có |
|---|---|---|
| `search_places` | Tên/category/alias đã có bằng chứng; lọc trong scope | Canonical ID, tên, kiểu match, release, trang tiếp |
| `filter_places` | Structured requirement theo activity/applicability và unknown policy | Allowed/rejected/unknown, reason và evidence status; không chỉ bool |
| `semantic_search` | Photo/span/style cho preference và vibe | Ranked IDs, score và pointer media/span, trạng thái coverage; score không phải Fact |
| `get_place` | Serving record của canonical ID trong release | Identity, operation, feature/status, estimates và provenance |
| `get_place_evidence` | Bằng chứng đúng place/feature/context | Quote/span/source/observed time, gate/status và release; bounded payload |
| `explain_unknown` | Giải thích bằng code vì sao chưa kết luận | Reason thật từ metadata: thiếu, chưa xác minh, mâu thuẫn, cũ hoặc không áp dụng |
| `similar_places` | Xếp hạng nơi tương tự trong tập được phép | IDs/score/reason; không vượt hard-filtered pool |

Không gọi nhiều API chỉ để tăng số tool. Một tool có thể kết hợp filter → rank → evidence
lookup, nhưng kết quả giữ ranh giới ba loại thông tin để reviewer và user hiểu số nào đã được
chứng minh. Mỗi kết quả trả release binding để phát hiện reader/cache lệch version.

## 5. Hybrid retrieval phân vai

| Nhu cầu | Đường dữ liệu | Guard |
|---|---|---|
| Hard constraint | Structured snapshot + public `requirements` | Scope trước evidence; unknown fail-closed theo policy; similarity không chứng minh an toàn |
| Preference / vibe | Semantic photo/span/style + feature đã phục vụ | Chỉ xếp hạng trong allowed pool; không nâng vector hit thành VERIFIED |
| Giải thích | Evidence lookup đúng canonical ID, feature và context | Không ghép quote của nơi khác, version khác hoặc claim đã bị loại |
| Planning | Hours, visit estimates, crowd, price, freshness từ structured record; live context riêng | Solver/validator kết luận; LLM không nới physical constraint |

Skill chỉ dạy khi nào dùng các đường này và cách xử lý thiếu dữ liệu. Threshold, quyền, scope,
provenance và fail-closed nằm trong tool/code; không chuyển sang prompt để Agent tự quyết.

## 6. Trip Understanding: hiểu nhiều, hỏi có ích

### 6.1 Nền tảng trước redesign

Catalog và Looks đọc cùng release; kết quả semantic không vượt Catalog membership hoặc tập
caller đã lọc. Count/board chỉ dùng feature được phục vụ và đủ bằng chứng; uncertain/conflict/
missing không thành giá trị chắc chắn. OUTDATED giữ status và freshness, không được “làm trẻ”
bởi thời điểm build mới.

Giữ contract ngày, người đi cùng, di chuyển và care đã chốt trong spec redesign. Normalized
data hỗ trợ kiểm coverage và ý nghĩa câu hỏi, không thay thế thông tin chuyến user cần cung cấp.

### 6.2 Grounded directions và câu mềm

- Agent đề xuất 3–4 hướng; code tìm nơi thật, lọc scope/hard và điền count/photo/evidence.
  Chỉ hiện tab khi còn đủ hướng có support theo ngưỡng cấu hình. Semantic thiếu thì dùng
  structured feature/category có bằng chứng, hoặc không hiện hướng; không bịa ảnh/nơi.
- Counterfactual câu hỏi chạy trên bản sao Trip State và cùng release. Chọn tối đa hai câu mềm
  có tác động đáng kể, không hỏi lại field user đã nói hoặc đã declined.
- `chip_effects` hiện đo **count delta**, chưa đo thứ tự top-K. Có thể dùng count metric trước;
  nếu muốn ranking metric, cần typed read-only preview thực sự và benchmark. Không gọi hai
  metric bằng cùng một tên hoặc đặt ngưỡng chưa được đo như cam kết chất lượng.

### 6.3 Summary và inferred intent

Summary tách user / inferred / profile / behavior / default, giữ lý do và khả năng sửa. ✕ một
suy luận chỉ hủy suy luận, không tự trở thành `avoid`. Dwell là prior yếu, không phải fact hoặc
hard constraint; explicit intent của chuyến hiện tại thắng.

Bàn giao budget amount/currency/scope và provenance, phép quy đổi có đủ days/people hay chưa.
Giữ scalar tương thích khi cần nhưng không bỏ raw intent. Time dùng ngày + timezone, xử lý
buffer qua nửa đêm; default 14:00/12:00 trong redesign được công bố, không thành giờ khách sạn
đã xác minh hoặc giới hạn vận tải mới. Adapter Agent dùng `Chat`/`AIMessageChunk` hiện hành.

## 7. Decision: chọn đúng và giải thích được

- Lọc structured trước, xếp semantic sau trong allowed pool. Anchor/user lock vẫn qua constraint;
  không dùng lời Agent hoặc vibe để cứu một nơi fail physical/hard.
- Infer activity mặc định theo venue; activity explicit thắng. Café `coffee` không tự thành meal
  hoặc được chứng minh có món chay chỉ vì metadata `usable_as` hỗ trợ meal.
- Explanation gắn từng “hợp / hy sinh / chưa biết” với serving evidence hoặc phép tính chuyến.
  Evidence không đủ thì nói chưa biết, không lấy điểm semantic hoặc độ nổi tiếng làm lý do fact.
- Handoff giữ nguyên canonical selection, activity, requirement intent/unknown policy, utility
  basis và release. Đổi release hoặc điều kiện có diff; overload không làm mất selection.
- Khi feedback cập nhật Session Profile, chỉ xếp lại nơi chưa chọn; không suy “không bấm” là
  không thích, và không nâng pattern thành constraint.

## 8. Planning: lịch hợp lệ từ dữ liệu đúng nghĩa

- Dùng structured record của cùng release cho giờ, duration range, giá và freshness. Vector/span
  dùng giải thích hoặc gợi ý backup; không điều khiển validity của timeline.
- `lodging.sieve()` hiện chỉ kiểm `ne` và giữ unknown. Cần dùng public `requirements` cho cả
  `eq/ne`, đúng accommodation applicability và unknown policy; thiếu bằng chứng không thành an toàn.
- `price_cap()` hiện coi budget scalar như tổng chuyến. Cần thống nhất VND/người/ngày, tổng nhóm/
  chuyến và room/night/capacity. Không chia tiền phòng thành người/đêm nếu thiếu occupancy hoặc
  scope; không coi giá tham khảo là giá đúng ngày đi hay availability.
- Giờ khách sạn, vận tải và khung đi chơi có ý nghĩa riêng. Physical boundary không có đường
  nới; thiếu giờ vẫn unknown hoặc default có provenance rõ theo contract đã chốt.
- Cache preview dựa trên input ảnh hưởng lịch và dependency versions: release, config/solver,
  constraint/activity và live context. Decision log hoặc transcript không đổi lịch thì không
  làm mất hit; release/giờ/giá/live đổi phải invalidate.
- Thẻ, lịch đang chọn và kết quả confirm dùng cùng timeline/metrics. Giữ restored/locked/assigned,
  selection gốc và undo/replay; phương án vi phạm không được ép thành confirmable.

## 9. Các bước thảo luận / triển khai đề xuất

| Bước | Kết quả độc lập | Cổng kiểm chứng |
|---|---|---|
| A. Release và pin | Một binding qua journey/Tools của ba module, legacy policy | Pointer đổi không trộn snapshot/index; restore không đổi selection; missing release fail-closed |
| B. Retrieval và evidence | Typed API + eligible scope + structured/semantic/evidence vai trò rõ | ID ngoài scope không lọt; uncertain/claim lỗi không tăng VERIFIED; source/feature đúng |
| C. Semantics online | Budget/time/activity và stay constraints thống nhất | Đơn vị/qua nửa đêm/scope/unknown; cùng evidence cho cùng verdict ở các module |
| D. Trip hiệu quả hơn | Grounded directions và câu mềm có đo tác động; summary theo provenance | Case input đầu, không hỏi lại, không suy disliked từ unknown, số liệu và ảnh có nguồn |
| E. Decision/Planning và cache | Explanation/backup chính xác, giữ lựa chọn và ít tính lại | Handoff, undo/replay/confirm; cache hit khi chỉ log đổi, invalidate khi dependency đổi |

Chốt input/output và legacy migration của từng bước trước khi code. Không xem deck/UI, behavior
learning, thinking escalation hoặc benchmark model thật là điều kiện hoàn tất chuẩn hóa reader.

## 10. Đo để biết cải thiện thật

Baseline và bản mới dùng cùng input, config, release và máy; live/model dùng stub cho kiểm
semantics. Chỉ đo production latency của model/live khi có phạm vi riêng được đồng ý.

- **Coverage:** eligible canonical IDs; photo/span/style riêng cho stay/non-stay; excluded IDs
  và lý do; evidence thiếu/invalid/stale. Không dùng inventory count làm semantic denominator.
- **Retrieval:** tỷ lệ ID ngoài scope, hard false-pass và unsupported explanation phải bằng 0;
  đo recall/ranking trên ca đã gán nhãn, riêng structured và semantic.
- **Trip:** field accuracy, câu bị hỏi lại, số câu trước ready, câu có tác động thật, user sửa
  inferred intent; p50/p95 lượt đầu, tách model / retrieval / persistence.
- **Decision/Planning:** selection giữ qua handoff, fail-closed stay, time/unit correctness,
  valid confirm, unknown cost; cache hit và p50/p95 cold/warm theo phần tính.
- **An toàn migration:** raw/source hash không đổi; build không crawl/model mới; rollback/restore
  được; kiểm public boundary và các suite tương ứng.

Không cam kết giảm latency hoặc tăng recall chỉ vì dữ liệu được gọi là “normalized”. Dữ liệu
nguồn vẫn có thể thiếu; kết quả đúng phải thể hiện thiếu đó thay vì che bằng reasoning.

## 11. Ranh giới hiện tại và điểm dừng

Theo yêu cầu người dùng, Codex đã tiếp nhận sửa contract RAG của Claude và nối public API
vào ba factory, harness và context Agent. Reader dùng binding thực; Trip name/cues, Decision
evidence read và Planning proposal cùng release/scope. Chi tiết kiểm chứng, build/smoke và
điểm dừng mới nhất chỉ ghi tại `CORPUS_NORMALIZATION_HANDOFF.md` §Trạng thái tiếp tục mới nhất.

Phạm vi cuối: hoàn tất hai tài liệu `ONLINE_MODULES_RAG_UPDATE_IDEAS.md` và
`../NORMALIZED_CORPUS_RECHECK.md`, kiểm RAG rồi dừng; chưa publish/restart/export Web.
Các ý tưởng directions/counterfactual, room occupancy/address safety và benchmark live chưa
được triển khai trong đợt này. Không sửa `../TRIP_UNDERSTANDING_QA.md` do người dùng đang viết.
