# Tái kiểm Corpus và dữ liệu normalized

Đối chiếu ngày 2026-10-15. Báo cáo này tách tính toàn vẹn dữ liệu, độ đúng của claim và khả năng
phục vụ online. Contract: `CORPUS.md` §Chuẩn hóa và release offline. Trạng thái build/activation,
release mới nhất và kết quả test: `plans/CORPUS_NORMALIZATION_HANDOFF.md`.

## 1. Nguồn kiểm tra

- Normalization `f4f37dcb1a5d89ca04da70cb`: manifest trong `data/normalization/<id>/`.
- Job Claude: `logs/run/claude-normfix.{status,report}.json`; code script đã có trong repo,
  không chỉ ở scratchpad. Job đã success; release của job là `r-f4f37dcb1a5d89ca04da70cb-0e745d06`.
- Đối chiếu nhãn/serving offline: `logs/run/corpus-continuation.audit.json`.
- Build và smoke tiếp tục: `logs/run/corpus-continuation-build.{status,report}.json`,
  `logs/run/corpus-continuation-smoke.report.json`; test có status/log cùng tiền tố continuation.

Không chạy model mới, sửa nhãn hoặc nới quote match trong lượt đối chiếu này. Nhãn/nguồn có
thể còn lỗi; pass integrity không tự đồng nghĩa claim đúng.

## 2. Kết quả normalization và thay đổi serving

| Chỉ số | Kết quả |
|---|---:|
| Input / eligible document | 7.703 / 7.703 |
| Claim giữ trong normalized documents | 1.478.058 |
| `span_reanchored` | 4.585 |
| `invalid_source_span` | 2.987 |
| Eligible serving ID | 3.208 |
| Feature UNCERTAIN → VERIFIED / OUTDATED | 2.568 / 67 |
| Feature mất sau normalize fix | 0 |

Reanchor chỉ gắn quote còn nguyên văn vào segment lệch tối đa 2 giây, giữ provenance mốc cũ.
Không sửa quote hoặc chấp nhận near-match để tăng số giữ. Claim bị loại không được phục hồi
từ backup/raw bởi runtime; không có bằng chứng giữ unknown.

## 3. Đọc đúng Gemma audit và bộ nhãn strong

Prompt audit đánh **claim có được nguồn hỗ trợ hay không**:

| Mẫu | correct | wrong | unsure |
|---|---:|---:|---:|
| TikTok reanchor, n=160 | 78 | 73 | 9 |
| Review vẫn bị normalizer loại, n=160 | 114 | 42 | 4 |

`correct` không có nghĩa “normalizer loại đúng”. Review bị loại có thể có ý nghĩa đúng nhưng
quote không khớp nguyên văn. Verdict semantic không thay kiểm chứng span/source.

Người dùng xác nhận lần hiệu chỉnh trước có Sol hỗ trợ và bộ gold. Dữ liệu hiện có 48.507
dòng nhãn không phải Gemma, 47.198 content key duy nhất; không có nhãn người trong
`labels.jsonl`. Đây là nhãn strong của model theo content key source/feature/value/quote,
không phải việc người đã kiểm lại toàn nguồn hiện tại. Script eval Gemma cũ không có trên
máy này. Không áp tỷ lệ bỏ nhầm khoảng 30% của lần trước như calibration của mẫu mới.

| Tập reanchor | Strong correct | Strong wrong | Strong unsure | Chưa có strong |
|---|---:|---:|---:|---:|
| 4.585 claim normalized | 1.696 | 572 | 111 | 2.206 |
| 3.001 claim trong aggregate | 1.612 | 0 | 110 | 1.279 |
| 2.203 claim backing value VERIFIED/OUTDATED | 1.140 | 0 | 46 | 1.017 |

572 claim strong wrong không vào aggregate của release đã đối chiếu. Đây là kiểm tra gate
trên nhãn đã có, **không phải precision toàn serving**: còn 1.017 claim backing value firm
chưa có strong và nhãn unsure chưa phải phán quyết đúng.

Mẫu 160 TikTok gồm 29 claim strong wrong đã bị aggregate loại; chỉ 67 claim backing value
firm. Report Gemma chỉ lưu 12 ví dụ không-correct, không lưu verdict đầy đủ theo claim ID,
nên chưa dựng được confusion matrix cho riêng 67 claim này. Ví dụ có lỗi rõ (parking bị gán
outdoor seating) lẫn ca có thể thiếu ngữ cảnh (hái dâu tại vườn); không suy verdict của toàn
73 ca từ 12 ví dụ. Trong 1.749 review bị loại chỉ 11 có strong, không đủ để quyết định nới matcher.

## 4. Cổng integrity và release

1. Kiểm manifest normalization: city, membership/canonical ID, redirects, input/source hash,
   normalized artifact hash, schema/ontology và reason từng claim bị loại.
2. Rebuild staging từ normalization/vector đã lưu. Không đổi nguồn, sinh vector mới hoặc
   publish staging thiếu manifest; compiler fingerprint đổi giữa build phải báo lỗi.
3. Dùng public `corpus.releases.validate`: artifact hash, snapshot/index/serving membership
   phải cùng eligible set. Pin release/version theo public Binding; missing/corrupt fail-closed.
4. Index phải có `served` và metadata claim đúng nguồn. `served=False` chỉ giữ normalized
   claim hợp lệ; quote/source sai, thiếu source identity, nhãn wrong/unsure_again hoặc model/
   dimension không tương thích bị loại khỏi cả evidence lẫn vibe.
5. Evidence kiểm đúng value/status/context và observation ID; context histogram chưa có
   verdict không trở thành fact. Semantic score không được nâng VERIFIED.
6. Smoke ba module bằng stub model/live, giữ selection/activity/binding tới Planning confirm;
   kiểm restore/copy qua pointer đổi và guard lodging tại Decision/Planning.
7. Activation atomic chỉ sau validation/kiểm chứng. Giữ release đang được journey tham chiếu;
   export Web projection và split snapshot cùng release. Deployment nhận code mới cần restart;
   journey đã pin không tự chuyển release.

### Kết quả kiểm chứng 2026-10-15

Release mới `r-f4f37dcb1a5d89ca04da70cb-ea26fde5` build/validate thành công, source và
compiler fingerprint không đổi, model/network=0, chưa publish. Có 370.303 span, 246.872
served; 29.820 photo row. Membership snapshot/index/serving khớp 3.208 eligible ID.

Smoke read-only qua public factories dùng chung retrieval đạt: Trip tìm Zin’s Cafe →
Decision select/confirm → Planning chọn variant/confirm, giữ ID/activity/binding.
Evidence có observation/source đúng serving value và release; semantic trả hit đúng scope.
Model/live dùng stub: chưa đo embedding recall, latency live hoặc chất lượng LLM.
Coverage đếm nơi: photo 1.638/3.208, span 1.691/3.208. Báo cáo và script/log tại
`logs/run/corpus-continuation-smoke.*`; bộ cuối RAG/normalization/wiring đạt 185 passed,
6 skipped (exit 0). Không có activation hoặc restart deployment trong phạm vi này.

## 5. Cách đo coverage và việc còn cần làm

Coverage phải đếm **nơi có vector**, riêng photo/span/style và stay/non-stay, cùng eligible
denominator. Số row không phải số nơi; có vector cũng không chứng minh đủ evidence mọi feature.
Index chưa có cột served phải rebuild artifact, không gọi là code RAG đã được deployment dùng.

- Giữ exact-match normalization cho tới khi có bộ adjudication phù hợp cho near-match.
- Nếu đánh giá Gemma lại: lưu từng claim ID/content key, source hash/context, verdict/doubt;
  tách mẫu phục vụ thật khỏi mẫu đã bị gate loại; giữ tập gold kiểm riêng dev/test theo nơi.
- Đo false-pass/false-negative theo feature/value/source và strong label; không đo bằng tỷ lệ
  correct thô trên hỗn hợp claim. Không biến nhãn Gemma thành gold độc lập của chính Gemma.
- Stay thiếu vector, room occupancy/availability, giờ/giá thiếu và dữ liệu place details là
  các khoảng trống riêng. Model/crawl/embedding bổ sung cần phạm vi được cho phép; không che
  thiếu dữ liệu bằng reasoning hoặc ước lượng không có provenance.
