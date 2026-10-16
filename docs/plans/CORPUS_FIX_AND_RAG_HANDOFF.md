# Bàn giao: sửa chuẩn hóa corpus → RAG online

Ngày cập nhật: 2026-10-15 (giờ Việt Nam). File làm việc tạm (`RULE.md` §0.1), không phải tài liệu chính
thức. Khi xong việc: gộp phần hiện trạng vào `docs/CORPUS.md` / tài liệu module rồi xóa file này.

Đọc trước: `RULE.md`, `docs/plans/ONLINE_AGENT_COORDINATION.md` (Codex làm song song),
`docs/plans/NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md` (§4–5 là phạm vi RAG),
`docs/superpowers/specs/2026-10-14-corpus-normalization-design.md`.

## 1. Phân công

Cập nhật 2026-10-15: người dùng đã giao Codex sửa contract RAG rồi nối ba module/Agent.
Hai mục Claude/Codex dưới đây là phân công ban đầu. Phạm vi cuối là hoàn tất hai MD và
kiểm RAG rồi dừng, không publish/restart; xem trạng thái mới nhất tại
`CORPUS_NORMALIZATION_HANDOFF.md`.

- **Claude:** chỉ RAG (retrieval API, semantic / evidence lookup) + 3 sửa lỗi chuẩn hóa ở §3.
- **Codex:** Trip reader (`trip/api/tools.py`, `looks.py`, `catalog.py`, test reader), proposal,
  phần contract online khác (budget/time, stay, cache).
- Trước khi sửa file, ghi tên file vào §Phản hồi của `ONLINE_AGENT_COORDINATION.md`; đọc lại file
  live, chỉ vá hunk mình giữ. Không checkout/reset/clean, không commit/push khi chưa được yêu cầu.

## 2. Đã xong

| Việc | File | Kiểm chứng |
|---|---|---|
| Trip đọc snapshot qua `corpus.releases.resolve()` như Decision/Planning/index | `src/trip/api/tools.py`, `src/trip/__main__.py`, `tests/trip/test_catalog_snapshot.py` | Trip + boundary: 487 passed. Dev log: `corpus-release-alignment` |
| 3 sửa lỗi chuẩn hóa (§3) | `src/corpus/normalize/run.py`, `src/corpus/aggregate/place.py`, 4 test cuối `tests/normalization/test_normalize.py` | `pytest tests/normalization tests/aggregate tests/serving tests/snapshot` → 152 passed |
| RAG retrieval §5 (cột `served`, `served_only` filter, `corpus.retrieval` engine, hybrid semantic, boundary tests) | `src/corpus/index/compile.py`, `src/corpus/index/query.py`, `src/corpus/retrieval/{__init__,engine}.py`, `tests/index/test_index_query.py`, `tests/retrieval/test_retrieval_boundary.py` | 28/28 passed (7 index + 21 retrieval boundary). Dev log: `corpus-retrieval` |

Chưa ghi dev log cho 3 sửa lỗi chuẩn hóa — viết sau khi job §4 có kết quả.

## 3. Ba lỗi chuẩn hóa đã sửa (vì sao)

Release `r-761a156dfffa4bc5d8bbc30b-6481f4ed` hạ **2.831 feature VERIFIED → UNCERTAIN** (`invalidated_evidence`);
2.453 trong số đó chỉ mất 1 phiếu, 1.752 vẫn còn ≥ 10 phiếu.

1. **Một claim hỏng làm hỏng cả feature.** Normalizer thêm feature vào `normalization_excluded_features`
   khi một claim fail nguồn/span; aggregate hạ cả feature. Nay claim fail nguồn/span ghi vào
   `normalization_dropped_claims` (feature, value). Aggregate chỉ hạ feature khi một value bị bỏ **khác**
   `top_value` (bỏ phiếu trái chiều sẽ thổi phồng agreement — giữ test
   `test_invalidated_conflict_does_not_upgrade_remaining_claim`). Feature có claim bị bỏ vẫn chặn suy
   luận im lặng (có người đã nhắc). `invalid_claim` / `duplicate_claim_conflict` giữ hành vi cũ.
2. **TikTok: transcript chạy lại làm lệch mốc segment.** 4.604/7.572 quote vẫn nằm nguyên văn trong
   transcript, chỉ đổi `start_s/end_s`. Nay quote nguyên văn trong segment lệch ≤ `REANCHOR_S = 2.0` s
   được gắn sang segment đó; span giữ `reanchored_from`; issue `span_reanchored`. Quote và claim ID
   không đổi nên nhãn Judge giữ nguyên.
3. **Review mất text** (161) báo `missing_source` thay vì `invalid_source_span`.

Chưa đổi: 2.071 review + 618 TikTok khớp ≥ 80% (vd. extractor thêm "(?)") vẫn bị loại theo spec §5.5
(không sửa quote cho khớp). 100 quote TikTok thật sự không còn trong transcript và 17 official/không
transcript bị loại đúng.

## 4. Job nền và kết quả đã kiểm

Job đã `success`, release `r-f4f37dcb1a5d89ca04da70cb-0e745d06`, normalization
`f4f37dcb1a5d89ca04da70cb`, 3.208 eligible ID; chưa publish. Report lưu tại
`logs/run/claude-normfix.report.json`, không chỉ ở thư mục tạm. Normalization có 4.585
`span_reanchored`, 2.987 `invalid_source_span`; 2.568 feature UNCERTAIN → VERIFIED,
67 → OUTDATED, không mất feature. Release này được build trước code RAG `served` và chưa có
cột đó; cần release build mới sau khi kiểm contract RAG.

### Đọc đúng audit và nhãn strong

`correct` trong `OBS_AUDIT_GEMMA` nghĩa là **claim được nguồn hỗ trợ**, không phải normalizer
loại đúng. TikTok: 78 correct / 73 wrong / 9 unsure; review vẫn bị loại: 114 / 42 / 4.
Gemma chấm ý nghĩa claim; không thay kiểm quote khớp nguồn. Không nới near-match từ số này.

Người dùng xác nhận lần đánh giá cũ có Sol hỗ trợ và bộ gold. Nhãn hiện có trong
`data/review/judge_labels.jsonl`: 48.507 dòng không phải Gemma, 47.198 content key duy nhất;
không có nhãn người trong `labels.jsonl`. Nhãn strong là mốc đối chiếu của model, không phải
gold người đã xác minh từng claim. Script đánh giá Gemma cũ ở `logs/judge_exp` không có trên
máy này, nên không thể suy calibration hiện tại từ tỷ lệ được ghi trong docs.

Đối chiếu offline theo source/feature/value/quote, không chạy model hoặc sửa nhãn:

| Tập reanchor | correct | wrong | unsure | Chưa có nhãn strong |
|---|---:|---:|---:|---:|
| 4.585 claim normalized | 1.696 | 572 | 111 | 2.206 |
| 3.001 claim có trong aggregate | 1.612 | 0 | 110 | 1.279 |
| 2.203 claim backing value VERIFIED/OUTDATED đang phục vụ | 1.140 | 0 | 46 | 1.017 |

Mẫu 160 TikTok audit chứa 29 claim strong `wrong`, đều không vào aggregate; chỉ 67 claim
backing value đang phục vụ. Report Gemma chỉ giữ 12 ví dụ không-correct, không lưu toàn bộ
verdict theo ID nên chưa tính được confusion matrix trên 67 claim đó. Không gọi tỷ lệ 78/160
là precision của serving hay tỷ lệ reanchor đúng. Với 1.749 review bị loại, chỉ 11 có nhãn
strong (10 correct, 1 unsure); mẫu 160 chỉ có một claim strong correct. Cần bộ gold phù hợp
nếu quyết định thay chuẩn so khớp; mặc định giữ chuẩn hiện tại.

Report đối chiếu phiên này: `logs/run/corpus-continuation.audit.json`. RAG gate phải loại cả
nhãn `wrong`/`unsure_again` khi giữ unserved span, tránh đưa claim đã bị Judge loại trở lại
vibe search. Kết quả code/build mới ghi tại `CORPUS_NORMALIZATION_HANDOFF.md` §Trạng thái tiếp tục mới nhất.

Script: `logs/run/claude-normfix_job.py` (bản chép; chạy lại: `setsid nohup .venv/bin/python -u logs/run/claude-normfix_job.py > logs/run/claude-normfix.log 2>&1 &`). Khởi chạy 22:53 (giờ VN), pid 2007438.

Các bước: `normalize('dalat')` mới → `releases.rebuild(..., publish=False)` → so với release cũ →
`OBS_AUDIT_GEMMA` trên UIT Gemma (`EXTRACTOR_ON_UIT=1`, 8 call song song) chấm mẫu 160 claim TikTok
được gắn lại + 160 review vẫn bị loại, dùng **text nguồn hiện tại**. Không ghi nhãn, không publish.

| File | Nội dung |
|---|---|
| `logs/run/claude-normfix.status.json` | `normalizing` → `rebuilding` → `gemma_check` → `success` / `error` |
| `logs/run/claude-normfix.report.json` | normalization ID + summary, release ID, semantic counts, `feature_status` cũ/mới, `transitions_old_to_new`, `gemma_check` |
| `logs/run/claude-normfix.log` | stdout/traceback |

Activation là bước tương lai, ngoài phạm vi dừng mới nhất trong `CORPUS_NORMALIZATION_HANDOFF.md`:
release phải validate đầy đủ, guard/test sạch và schema index đúng code. Không publish staging
thiếu manifest hoặc tự nới quote match. Deployment đang chạy cần restart để nạp code/factory mới;
journey đã pin giữ release cũ. Không tự restart deployment trong đợt kiểm chứng này.

## 5. RAG — trạng thái triển khai

Quyết định đã chốt và triển khai xong (bước 1–2):

- ✅ **Span có cờ, không xóa:** `compile.py` gate trả span với `served=False` thay vì loại. Reason
  `stale_evidence` → `not_backing_served_feature`. Evidence chỉ `served=True`; vibe search đọc cả hai.
- ✅ **`served_only` filter:** `query.py` `search_spans()` nhận `served_only` param. `SpanHit.served` field.
- ✅ **`corpus.retrieval` engine:** `RetrievalEngine.open(release_id, region)` → `search_names`,
  `get_place`, `semantic(q|image, within, mode)`, `similar`, `evidence`, `coverage`. Hybrid cross-modal
  (bge-m3 span + SigLIP2 photo) + ontology feature boost + RRF merge. 28/28 test passed.
- ✅ **Hard filter ở `requirements`:** Retrieval nhận `within` (tập ID đã qua lọc) **bắt buộc**.

Codex tiếp tục theo lựa chọn mới của người dùng: sửa contract release/scope/gate, chuyển name
search Trip sang public Corpus và thêm typed evidence read cho Decision; kết quả cuối ở
`CORPUS_NORMALIZATION_HANDOFF.md` §Trạng thái tiếp tục mới nhất. Không xem 28 test cũ là bằng chứng cho các
contract mới; xem kiểm chứng phiên tiếp tục.

Còn ngoài phạm vi tích hợp contract:

- Coverage / dữ liệu mỏng trên UI: báo "ảnh không có để so"; nơi mới ít review không bị
   chìm (dải riêng hoặc slot khám phá). Vector cho stay (3/1.510) cần chạy Embedder → hỏi người dùng.

Số đo nền (release cũ): non-stay có photo vector 1.635/1.698, span 1.687/1.698; stay 3/1.510.
Decision chỉ dùng semantic qua `si.vibes` (`src/decision/rank.py` `vibe_fit`, chỉ nâng, không loại).

## 6. Khoảng trống corpus ngoài phạm vi này (đã báo người dùng)

- `details` (`known_for`, `order`, `avoid`, `photo_spot`, `access`, `fit`) = 0/3.208 cả trước chuẩn hóa:
  kế hoạch place-details chưa chạy; cần Extractor trên dữ liệu đã có, không cần crawl.
- `visit_minutes` 1.666/1.698 non-stay là `category_default`.
- Recrawl có mục tiêu (chỉ Maps; TikTok đang dừng vì captcha): giờ mở 285 non-stay, giá/người 795,
  giá/đêm stay 670.
- Nơi mới/ít dữ liệu: non-stay < 30 phiếu: 98, < 5 feature VERIFIED: 34; stay: 90 và 312.

Model/crawl ở mục này cần người dùng đồng ý. GPU: được dùng GPU đang rảnh nếu cần, chỉ khi rảnh.
