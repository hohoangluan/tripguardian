# Ý tưởng và công việc cập nhật ba module online với Corpus/RAG

Ngày: 2026-10-15. Tài liệu làm việc tạm theo `RULE.md` §0.1. Nền tảng và contract chi tiết:
`NORMALIZED_CORPUS_RAG_ONLINE_PROPOSAL.md`; trạng thái release/test: `CORPUS_NORMALIZATION_HANDOFF.md`.
Không coi ý tưởng dưới đây là chức năng đã ship.

## 1. Mục tiêu

Trip hiểu đúng ý chuyến đi và hỏi ít câu có ích; Decision chọn và giải thích bằng dữ liệu thật;
Planning dựng lịch hợp lệ, giữ lựa chọn của người dùng. Cả ba nhìn cùng corpus binding.
RAG hỗ trợ tìm kiếm và giải thích, không thay verdict của requirements hoặc solver.

## 2. Cấu hình và ranh giới tích hợp

- Harness tạo retrieval theo binding của journey, truyền vào factory ba module. Restore/copy
  mở binding đã lưu; không tự chuyển pointer hoặc suy lineage của journey lịch sử null.
- Structured snapshot/serving quyết định membership, activity, hard requirement, giờ và giá.
  Semantic chỉ rank trong tập `within` đã cho phép; similarity không trở thành VERIFIED.
- Evidence phải đúng place, feature/value, context có verdict, observation và release.
  Thiếu quote/status/coverage trả unknown hoặc reason thiếu; không đọc raw để lấp thiếu.
- LLM gọi theo vai trò Agent; model/key vẫn ở config/.env. Agent nhận payload bounded có
  lineage và phân biệt fact, estimate, semantic hit, user intent. Không được sửa corpus,
  nới physical/hard, tạo ID hoặc tự xác nhận lịch. Prompt không thay code guard.
- Không chạy thêm model/crawl/embedding chỉ để cấu hình kết nối. Benchmark model/live thật
  là phạm vi riêng sau khi test contract bằng stub đạt.

## 3. Trip Understanding

| Ý tưởng | Cần thực thi | Điều kiện đạt |
|---|---|---|
| Nối semantic gap | Looks dùng hybrid retrieval trong catalog ∩ within; giữ pointer/coverage | Không ID ngoài scope; span không có ảnh không sinh ảnh; score không thành fact |
| Ảnh/URL: đúng nơi hay nơi tương tự | Giữ image→Vibe hiện có; thêm lựa chọn rõ “ghé đúng nơi này” để ghi anchor; resolver URL rút gọn cần contract riêng | Không tự biến xác nhận ảnh thành must; không match URL thì missing, không bịa nơi |
| Grounded directions | Tạo 3–4 hướng từ place thật qua hard filter; cấu hình ngưỡng support sau baseline | Không đủ support thì giảm/ẩn hướng; count/photo/evidence cùng release |
| Câu mềm có tác động | Counterfactual trên bản sao Trip State, tối đa hai câu; bỏ field đã nói/declined | Không hỏi lại; phân biệt count delta với thay đổi thứ tự top-K |
| Summary sửa được | Giữ nguồn user/inferred/profile/behavior/default và lý do | Bỏ inferred không tự biến thành avoid; unknown/đã đến không thành không thích |
| Thời gian đúng ngày | Contract ngày + timezone + buffer qua nửa đêm; tách vận tải, khách sạn và khung đi chơi | Physical boundary không nới; default có provenance, không thành giờ đã xác minh |

`docs/TRIP_UNDERSTANDING_QA.md` do người dùng cập nhật là nguồn case của Trip. Agent không
ghi đè file đó. Khi bổ sung test, map từng case sang field/tag, state/output và invariant;
không chép lại ngân hàng case vào tài liệu này.

## 4. Place Decision

| Ý tưởng | Cần thực thi | Điều kiện đạt |
|---|---|---|
| Giải thích có nguồn | Typed evidence read và context Agent bounded; UI đọc khi mở lý do | Claim hiện có VERIFIED/OUTDATED mới là lý do fact; unknown nói rõ thiếu gì |
| Gu tả bằng câu tự do | Semantic rank sau structured filter; không dùng vector cứu hard fail | Tỷ lệ ID ngoài scope và hard false-pass bằng 0 |
| Handoff nguyên nghĩa | Giữ canonical selection, activity, requirement/unknown policy, utility và binding | Rebase/restore/undo không mất selection; lodging fail bị chặn tại Decision |
| Dữ liệu mỏng công bằng | Hiện coverage riêng; đo slot khám phá trước khi thêm vào shortlist | Thiếu vector không đồng nghĩa không hợp; không biến thiếu review thành điểm xấu |

Lodging thay thế phải đọc được dù chỗ đang chọn fail sau rebase; draft phục hồi không phải
output đã xác nhận. Evidence lookup không ghi state/log/revision.

## 5. Planning & Validation

| Ý tưởng | Cần thực thi | Điều kiện đạt |
|---|---|---|
| Dữ liệu cùng release | Structured record và retrieval cùng binding trong factory/restore/Agent | Giờ/giá/evidence không trộn version; validator vẫn quyết định timeline |
| Backup có căn cứ | Chỉ tìm trong backup/allowed pool, evidence để giải thích; thử chèn rồi validate | Không thêm place bằng lời model; không hợp lệ thì không confirm |
| Giá phòng đúng scope | Bổ sung room/night, occupancy/capacity và số phòng khi có dữ liệu | Thiếu occupancy/availability không chứng minh tổng tiền hoặc đủ phòng cho nhóm |
| Address ngoài corpus | Contract unknown safety rõ cho lodging nhập tay/live | Không coi tọa độ hoặc đã đặt là bằng chứng physical/suitability |
| Cache đúng dependency | Binding, config/solver, activity/constraint, giờ/giá/live ảnh hưởng key | Log không đổi lịch giữ hit; dependency thật đổi phải invalidate |
| Agent có giới hạn | Context structured/evidence bounded; proposal chỉ variant/diagnostic/act cho phép | Giữ membership, locked/assigned; mọi proposal chạy validator trước áp dụng |

## 6. Thứ tự và kiểm chứng

1. Hoàn tất wiring public retrieval/binding của ba factory và payload Agent; giữ adapter độc lập.
2. Chốt case từ QA người dùng, viết regression contract và unknown trước thay đổi hành vi.
3. Smoke trên release thật với model/live stub: Trip → chọn nơi → Decision confirm → Planning
   confirm; giữ ID/activity/binding; kiểm evidence và coverage đúng scope.
4. Đo baseline chất lượng/latency cùng release/input/máy; tách retrieval, model, persistence,
   solver. Chưa có số đo thì không cam kết tăng recall hay giảm latency.
5. Sau đó mới làm directions/counterfactual, UI explanation/coverage, room capacity/address
   và redesign thời gian theo từng phạm vi có test riêng.

Các cổng chung: không ID ngoài scope, không hard/physical false-pass, không unsupported
explanation; restore/copy/undo/confirm giữ selection và lineage. Tái kiểm corpus theo
`../NORMALIZED_CORPUS_RECHECK.md`; trạng thái thực hiện chỉ ghi tại handoff để tránh hai bảng tiến độ.
