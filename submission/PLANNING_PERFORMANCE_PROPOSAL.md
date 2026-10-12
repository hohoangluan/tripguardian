# TripGuardian — Đề xuất tối ưu tính toán khi sửa lịch

> Bản bàn giao ngày 11/10/2026. Nội dung đã triển khai; runtime hiện tại ở `docs/PLANNING.md` §Tính lại và cache, kết quả benchmark synthetic và giới hạn ở `TECHNICAL_REPORT.md` §7. Các phần hiện trạng dưới đây là ghi nhận lúc bàn giao.

## 1. Mục tiêu và phạm vi

Trả lịch đã kiểm nhanh khi người dùng chỉnh sửa, giảm tính lại phần không đổi và giữ UI nhất quán với lịch hiện tại.

Trong phạm vi: tính lại theo phụ thuộc, local repair, cache trong RAM, gợi ý chạy nền, kiểm revision, metrics hiện tại và gộp input liên tục. Giữ đường thao tác trực tiếp không gọi LLM.

Ngoài phạm vi: đổi file JSON/Postgres/schema lưu trữ, nén dữ liệu, đổi cách lưu lịch sử, lưu checkpoint ra đĩa, thay solver, thêm dependency hoặc huấn luyện model. Không tự đổi objective weights trong đợt này.

## 2. Hiện trạng đã kiểm tra

| Phần | Hiện trạng |
|---|---|
| Phạm vi thao tác | `scope.py` đã có NONE, RELAYOUT, VARIANT và nhóm chỗ ở; cần áp dụng phạm vi tới cả kết quả phụ |
| Di chuyển và route | Đã có ma trận dùng chung, ID index và route cache; không cần làm lại |
| Sửa ngày | `repair_day` có thể vét cạn mọi permutation cho ngày nhỏ |
| Dựng view | `_active_itinerary` gọi `recommendations.recommend`, gồm nhiều lần thử chèn và validate |
| Metrics UI | `_view` chưa trả metrics lịch hiện tại; màn Plan đọc chi phí variant ban đầu |
| Proposal | `_proposal_trial` dựng ActCtx từ nơi ban đầu, thiếu backup đã thêm cho `move_place` |
| LLM | `act` trực tiếp đã tất định; `recommend` là operation proposal riêng |

Lần kiểm gần nhất trong phiên chat: 44 test pass, 1 fail ở `view.metrics` thiếu. Script offline xác nhận coffee được giữ; chi phí confirm đúng với giá đã khai báo; proposal di chuyển backup trả `unknown place 'cafe'`. Đây là kết quả tại thời điểm kiểm, không thay thế lần chạy mới khi bắt đầu triển khai.

Một lỗi trong fixture cần xử lý rõ: test đòi tổng 150.000đ nhưng record bữa ăn chưa khai báo 50.000đ. Nếu mục tiêu test là cộng hai giá đã biết, khai báo cả hai; đồng thời giữ test riêng cho giá chưa biết. Không bịa giá để đạt assertion.

## 3. Luồng xử lý đề xuất

```text
Thao tác có cấu trúc
  → xác định ngày/phụ thuộc bị ảnh hưởng
  → áp dụng trên nháp
  → sửa lịch liên quan + validate + metrics hiện tại
  → dựng view hợp lệ + lưu phiên theo cơ chế hiện có
  → trả UI

Gợi ý bổ sung
  → lấy snapshot tính toán và token phiên bản
  → chạy ngoài đường cập nhật lịch chính
  → chỉ trả kết quả khi token còn khớp
  → cập nhật phần gợi ý, không tự sửa lịch
```

`Engine.recommend` (proposal LLM) và `recommendations.recommend` (gợi ý tùy chọn tất định) là hai việc khác nhau. Tách gợi ý chạy nền không có nghĩa gọi thêm LLM.

### Phạm vi tính lại

| Thay đổi | Công việc |
|---|---|
| Lock/unlock | State và quyền sửa; dùng lại timeline khi ngữ cảnh không đổi |
| Reorder/add/drop/swap | Ngày liên quan, metrics và kiểm tổng chuyến |
| Move | Ngày nguồn và ngày đích |
| Pace/objective | Dựng lại phương án với tập nơi đang hoạt động; dùng lại phần có key khớp |
| Day window | Thử sửa ngày đó trước; khi không đủ thì dựng lại phương án với ngày khóa được giữ |
| Chỗ ở | Các ngày có điểm đầu/cuối đổi; dùng lại ma trận còn hợp lệ |
| Hard constraint | Trip compile, Decision screen và Planning validate theo phạm vi thực sự bị đổi |

Không bắt Trip/Decision chạy lại chỉ vì người dùng đổi thứ tự một ngày.

## 4. Các bước triển khai

### Bước 1 — Sửa tính nhất quán trước

Files chính: `src/planning/engine.py`, `web/src/user/planning/types.ts`, `web/src/user/screens/Plan.tsx`.

- Dùng cùng tập nơi/activity hiện tại cho timeline, validator, metrics và ActCtx của proposal.
- Trả metrics lịch hiện tại; UI đọc metrics này thay vì metrics variant gốc sau sửa.
- Dựng kết quả nháp trước khi commit; lỗi không làm session mất khả năng load.
- Test thêm café coffee, swap meal→café, đổi pace/objective/window, chọn lại variant sau drop, proposal move backup và replay. Kiểm đủ giá/unknown count, membership và activity.

### Bước 2 — Đo và đưa gợi ý ra khỏi đường dựng view

Files chính: `src/planning/engine.py`, `recommendations.py`, `tools.py`, API transport và PlanningProvider.

- Đo thời gian layout, validate, metrics, suggestions, dựng view và toàn operation; benchmark offline với nguồn giả lập, không ghi dữ liệu crawl.
- `_view` chỉ render kết quả đã có; không tự thực hiện tìm kiếm gợi ý mỗi lần load.
- Timeline và metrics trả trước; suggestions có trạng thái pending/ready/unavailable để UI không hiểu danh sách rỗng là không có ứng viên.
- Adapter public cung cấp đọc kết quả nền qua transport hiện có, mang journey revision và token của ngữ cảnh Planning. Tránh deep import từ harness vào Planning.
- Test chặn worker gợi ý bằng Event: act/load vẫn trả lịch; nhiều lần load không làm tăng số lượt tìm kiếm; worker lỗi không hỏng lịch và không hứa gợi ý chưa validate.

### Bước 3 — Local repair trước tìm kiếm rộng

Files chính: `src/planning/repair.py`, `engine.py`, ngưỡng trong `config/planning.yaml` và `settings.py`.

- Giữ thứ tự nơi còn lại khi drop; thử các vị trí chèn khi add/swap; mô phỏng thứ tự user yêu cầu khi reorder.
- Chọn kết quả bằng tiêu chí khả thi, bữa ăn và phí timing/diff hiện có. Chỉ dùng sửa nhanh khi lịch đáp ứng các kiểm tra; nếu không thì mở rộng tìm kiếm có giới hạn.
- Ngưỡng/số lượt tìm kiếm nằm trong config. Proposal tối ưu rộng hơn chỉ chạy theo yêu cầu; không tự xáo lịch sau khi UI đã nhận kết quả.
- Test ca chèn vừa, chèn cần mở rộng để tránh giờ đóng, lịch không thể xếp và nơi đã khóa. Đếm lượt simulate cho ca chèn đơn giản để chứng minh giảm công việc, không dùng giới hạn milliseconds dễ flaky.

### Bước 4 — Cache trong RAM theo ngày và phụ thuộc

Files chính: `src/planning/build.py`, `engine.py`, `recommendations.py`.

- Mở rộng cache hiện có một cách trực tiếp, không xây framework. Dùng lại timeline/metrics/kiểm ngày và gợi ý chỉ khi ngữ cảnh khớp.
- Key xét membership/order, activity và tính explicit, visit/pins/relaxed, pace, day window/date, objective/weights, requirement/time preference, config, travel và live context liên quan. Không chỉ dùng số ngày hoặc state position.
- Kết quả gợi ý còn phụ thuộc budget, tập đã ghé toàn chuyến và backup_pool. Undo/redo hoặc thay dữ liệu phải vô hiệu hóa đúng phần này.
- Giới hạn kích thước cache trong RAM. Không thêm dữ liệu tính toán vào snapshot persisted.
- Test sửa ngày 2 giữ ngày 1; đổi activity/pace/hard/time preference không dùng kết quả cũ; thay live context và replay vẫn đúng. Global duplicate/anchor/budget vẫn được kiểm, confirm kiểm lại toàn lịch.

### Bước 5 — Xử lý input liên tục và kết quả cũ

Files chính: `web/src/user/planning/planning.tsx`, `api.ts`, `types.ts`; adapter nếu cần token.

- Chỉ debounce control phát giá trị liên tục; không gom mất các act thêm/bỏ/chuyển và lịch sử undo.
- Serialize các act có thứ tự; hủy hoặc bỏ kết quả nền không còn khớp revision/token và Planning session hiện tại. Token phải xử lý cả undo/redo, không giả định position luôn tăng.
- Không thay view revision mới bằng kết quả read/SSE cũ. Worker chạy trên snapshot, không giữ session lock trong toàn thời gian tìm kiếm.
- Test đổi nhanh, đổi session, undo trong lúc worker chạy, lỗi worker và kết quả đến sai thứ tự.

### Bước 6 — Kiểm chứng và cập nhật tài liệu

- Chạy regressions liên quan, toàn `tests/planning` và tests biên Trip/Decision/harness; chạy web build.
- So sánh trước/sau trên cùng fixture, cấu hình và máy: p50/p95 cold/warm, số simulate, cache hit và thời gian tới lịch đã kiểm; đo suggestions-ready riêng. Báo cả timing penalty, travel và số vi phạm để thấy đánh đổi chất lượng.
- Đo riêng bootstrap khỏi thời gian sửa. Không hứa số lần tăng tốc trước benchmark.
- Khi đổi local repair có chủ ý làm lịch mẫu đổi, review golden trước khi cập nhật; không chạy UPDATE_GOLDEN để che regression.
- Cập nhật `docs/PLANNING.md`, tài liệu Web/contract nếu đổi và `TECHNICAL_REPORT.md` theo code cuối. Report hiện vẫn ghi hướng này chưa triển khai.

## 5. Điều kiện hoàn thành

- UI, metrics, validator và proposal thống nhất tập nơi/activity sau mọi act và replay.
- Load/view không chạy lại tìm kiếm gợi ý; act không chờ worker bổ sung.
- Sửa nhỏ giảm lượt mô phỏng; trường hợp khó còn fallback và báo vi phạm trung thực.
- Cache không vượt hard constraint, không giữ giá trị cũ khi phụ thuộc đổi; confirm vẫn kiểm toàn lịch.
- Kết quả nền cũ không xuất hiện trên revision mới; direct act không gọi LLM.
- Không đổi định dạng/lưu trữ dữ liệu hoặc session; giữ nguyên staged revert hiện có.

Lệnh test khởi đầu phù hợp môi trường đã dùng: `/tmp/tripguardian-requirements-venv/bin/python -m pytest tests/planning tests/trip/test_requirement_intent.py tests/trip/test_requirement_scope.py tests/decision/test_requirement_activities.py -q`. Web: `npm run build` tại `web/`. Kiểm dependencies và baseline mới trước khi chạy; không suy kết quả từ log cũ.
