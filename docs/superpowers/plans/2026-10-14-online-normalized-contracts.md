# Triển khai contract online của corpus chuẩn hóa

Phạm vi đã được người dùng cho phép: tiếp tục proposal
`../../plans/NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md`; Claude giữ RAG. Làm trên workspace
hiện tại, giữ thay đổi đang có; không commit chung thay đổi của agent khác.

## Bất biến

- Module chỉ dùng public API; online không ghi corpus; dữ liệu thiếu giữ unknown.
- Snapshot, serving và semantic index dùng cùng release và eligible membership.
- Restore không tự chuyển release; legacy giữ trạng thái rõ ràng.
- Activity và requirement/unknown policy giữ nguyên qua handoff; physical không relax.
- Tài liệu tiếng Việt; code/comment/identifier tiếng Anh.

## Task 1: Trip serving reader

Viết regression trong `tests/trip/test_catalog_snapshot.py` và
`tests/trip/test_normalized_readers.py`: serving value/status/context thắng intel,
uncertain không tăng count, OUTDATED giữ trạng thái, ID semantic ngoài catalog/within bị loại.
Sửa `src/trip/infrastructure/catalog.py`, `looks.py` tương ứng; giữ adapter legacy explicit.
Kiểm: `.venv/bin/python -m pytest tests/trip -q`.

## Task 2: Contract release và budget xuyên module

Thêm resolver release ID có validation đường dẫn/manifest/hash, typed binding public ở
`corpus.releases`; giữ resolver mặc định tương thích. Factory Trip/Decision/Planning nhận
root đã resolve, không chọn pointer khác. Harness lưu binding ở Journey, chọn bộ Tools theo
binding cho create/restore/read/advance/rebase/copy; legacy không suy release từ pointer mới.
SearchInput và DecisionOutput giữ binding; Planning output giữ provenance release.
BudgetIntent giữ amount VND/scope/nguồn/evidence/guessed; public `trip.group_budget` quy
đổi tổng nhóm/chuyến khi đủ dữ liệu. Viết regression trước implementation; kiểm trip,
decision, harness và normalization release tests.

## Task 3: Planning semantics và preview cache

Lodging dùng public requirements cho eq/ne, accommodation và unknown policy. Physical
unknown không bypass. Price cap dùng tổng nhóm/chuyến từ contract budget, số đêm explicit;
không đổi giá/person thành room/night nếu thiếu scope. Cache bỏ decision_log, wishlist,
feasibility khi không ảnh hưởng dựng lịch, giữ release/context/activity/config/record/live
dependency; test hit khi log đổi và invalidate khi dependency đổi. Giữ selection/undo/confirm.
Kiểm tests/planning và regression handoff.

## Task 4: Dữ liệu và tài liệu

Validate release `r-761a156dfffa4bc5d8bbc30b-6481f4ed` từ artifact hiện có; không crawl,
model hoặc sinh vector. Kích hoạt atomic nếu validation pass để module mặc định dùng
normalization mới. Không restart process đang chạy ngoài phạm vi kiểm thử.
Sửa tài liệu chính thức ba module/harness, proposal/handoff/coordination theo trạng thái
thật, chạy regression và review diff so baseline `/tmp/tripguardian-online-baseline`.
Không cam kết RAG hoặc latency chưa đo.

## Tiến độ

- Đã đọc proposal, RULE, public API và contract; đã lưu baseline file theo task.
- Task 1: reader đã triển khai/test; có pin version chống delayed loader đổi pointer.
- Task 2: binding/budget/handoff đã triển khai; cần re-review/full suite cuối.
- Task 3: lodging/cache và selected corpus lodging guard đã triển khai; 95 focused test pass.
- Task 4: release validate pass, docs chính thức sửa một phần; chưa activation/Web export,
  dev log/smoke dữ liệu thật. Full suite session 27017 chưa có kết quả cuối.
- Người dùng yêu cầu bàn giao cho phiên sau. Điểm tiếp tục authoritative:
  `../../plans/CORPUS_NORMALIZATION_HANDOFF.md` §Điểm tiếp tục. Dừng code/activation ở đây.
