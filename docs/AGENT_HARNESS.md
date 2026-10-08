# Agent, harness và router

Nền tảng online dùng một hành trình chung cho Trip → Decision → Planning. Module sở hữu state, tool và guard của mình; harness điều phối bằng Python qua public API. Model theo vai trò `Agent`; kết nối ở `docs/LLM_PROVIDER.md`.

## 1. Cấu trúc và quyền

```text
Web → harness.router → harness.dispatch
                       ├─ trip.Tools      → Trip Agent → guard → Trip State
                       ├─ decision.Tools  → Decision Agent → guard → lựa chọn
                       └─ planning.Tools  → solver → Planning Agent nội bộ → kiểm lại

agent của module → agents.run_structured → corpus.llm.AGENT
module → corpus / live qua public API, chỉ đọc Place Intelligence
```

| Package / file | Trách nhiệm |
|---|---|
| `src/agents/runtime.py`, `limit.py` | Stream, deadline, JSON/schema, retry vòng khoảng trắng một lần; giới hạn call trong tiến trình |
| `src/agents/contracts.py` | `ToolSpec`, `SkillSpec`, đọc YAML an toàn và kiểm allowlist tên/quyền |
| `src/{trip,decision,planning}/tools.py` | Public adapter: validate input, gọi engine, xuất/khôi phục snapshot do module sở hữu |
| `src/{trip,decision,planning}/skills.yaml` | Workflow và tool được phép của agent tương ứng |
| `src/harness/contracts.py`, `router.py` | Request/response có kiểu; định tuyến theo stage và operation |
| `src/harness/dispatch.py`, `session.py` | Handoff, revision, receipt, snapshot atomic cho toàn hành trình |
| `src/harness/server.py`, `__main__.py` | HTTP/SSE localhost, CLI |
| `web/src/user/journey.ts` | Client chung: tuần tự mutation, retry và khôi phục pending request |

Skill là khai báo do repo quản lý, không phải code thực thi hay skill tải từ người dùng. Workflow mô tả bước xử lý; `permit_tool` kiểm capability tại adapter. Trip dùng tool loop đọc bị chặn: Clef chỉ cấp allowlist theo câu user, Agent gọi tối đa số bước trong `config/trip.yaml`, code validate argument và chạy tool; `guard` vẫn là đường duy nhất ghi state. Call lập kế hoạch chạy song song với Clef (`trip.agent.runtime.run_agent`): Clef không cấp tool → giữ kết quả call đó, `say` giữ lại tới lúc Clef trả lời; Clef cấp tool → hủy call sớm trước bước tool, nên một lượt không bao giờ giữ hai permit Agent. Các agent dùng chung cấu hình model nhưng context, schema và quyền riêng.

Trip/Decision có lượt chat. Planning có call riêng cho proposal nội bộ và không nhận `turn` qua router; quyền và kiểm chứng proposal ở `docs/PLANNING.md` §Agent đề xuất nội bộ. `live` cung cấp tool, không có agent LLM riêng. Corpus giữ pipeline offline riêng.

## 2. Router và handoff

| Stage hiện tại | Operation được phép | Kết quả chuyển stage |
|---|---|---|
| `trip` | `turn`, `advance` | `advance` → Decision từ Search Input đã compile trên server |
| `decision` | `turn`, `act`, `advance`, `back` | `advance` → confirm Decision và tạo Planning; `back` → Trip |
| `planning` | `act`, `recommend`, `confirm`, `back` | `confirm` → Plan Output; `back` → Decision |

Lịch ngầm (`preview`) là đọc: harness lấy Decision Output nháp (`decision` read `draft`, không lưu) dưới khóa hành trình, rồi gọi `planning.Tools.preview` ngoài khóa; Planning dựng phương án không tạo phiên và cache theo hash Decision Output (15 phút, tối đa 16), `create` khi `advance` dùng lại đúng bản đã dựng. Web gọi sau mỗi thay đổi ở Chọn nơi, debounce 350 ms.

Request đến stage không active bị từ chối. Router không gọi LLM và không chọn agent từ tên tool hoặc lời model. `advance`, `back`, `recommend`, `confirm` chỉ nhận payload rỗng; client không gửi output để thay handoff đã kiểm.

Lượt chat ở Chọn nơi có mong muốn về chuyến (`turn` stage `decision` mà Decision phát event `trip {texts}`): harness gọi `trip.apply(trip_sid, "refine", {text})` (Trip đọc như một lượt chữ, compile lại, không đổi thẻ màn Hiểu chuyến đi), thay `outputs.trip` bằng Search Input mới rồi `decision.rebase`. Event `view` của lượt được thay bằng view sau rebase (kèm `diff`), lời Trip nối sau lời Decision trong cùng bong bóng (`say {replace}`), event `trip` không ra web. Trip không compile được (còn thiếu trường bắt buộc) hoặc hành trình không có phiên Trip → lượt vẫn xong, Decision giữ nguyên.

Quay về Decision giữ ID phiên và lựa chọn. Quay về Trip rồi compile lại dùng `rebase` trên phiên Decision đã có. Quay lại vô hiệu output ở bước sau; Planning được dựng lại khi xác nhận Decision. Act Planning giữ Decision Output làm đầu vào và vô hiệu Plan Output đã chốt.

## 3. Phiên, revision và retry

Một `Journey` giữ ID, stage, revision, ID phiên các module, output, snapshot và receipt. Engine chạy bằng store RAM; adapter từ chối engine có store ghi riêng. Harness ghi phiên vào `data/harness/sessions/<id>.json` (gốc lấy từ `DATA_DIR`). Snapshot module và receipt được ghi cùng envelope qua file tạm rồi replace.

Mutation giữ khóa hành trình trong tiến trình, kiểm revision và router, chạy tool, lấy snapshot mới rồi commit. Save lỗi khôi phục snapshot trước mutation. Restart phục hồi module từ snapshot đã commit, không gọi lại LLM để replay phiên.

Request trùng `request_id` và toàn bộ nội dung trả receipt đã lưu dù stage/revision hiện tại đã đổi. Dùng lại ID với nội dung khác hoặc revision cũ cho request mới bị từ chối. Receipt chứa response và event của lần thực thi đã commit.

Client tuần tự mutation theo journey, lưu pending request trong localStorage trước khi gửi, giữ nguyên ID/payload/revision khi retry transport và replay pending trước mutation mới sau reload. Reload tiếp tục stage trên server; chỉ thao tác quay lại rõ ràng từ người dùng gửi `back`. Server session là nguồn sự thật; `decisionId`/`planningId` trong adapter Web tham chiếu journey, không phải ID module độc lập.

Storage dùng một tiến trình: khóa không bảo vệ nhiều worker ghi cùng hành trình; chưa pruning receipt hoặc có transaction với dịch vụ ngoài. Atomic replace bảo vệ snapshot khỏi ghi dở, không cam kết durability trước mất điện. CLI/API module độc lập giữ store phiên riêng và không dùng chung ID với harness.

## 4. API và SSE

```sh
python -m harness serve [--port 8769]
```

Bind `127.0.0.1`; Vite proxy `/api/harness` đến cổng 8769. `./run.sh start` chạy harness, review và Web; thiết lập ở `README.md`.

| API | Input / việc |
|---|---|
| `POST /api/harness/sessions` | `{experience?, start_with?, user_id?, remember?}` → journey + Trip view; `user_id` / `remember` bật mẫu dài hạn của Trip (`docs/TRIP_UNDERSTANDING.md` §17) |
| `DELETE /api/harness/profile/<user_id>` | `{forgotten}`; xóa mẫu dài hạn đã lưu của user |
| `GET /api/harness/sessions/<id>?stage=` | Đọc view module đã có; mặc định stage active |
| `POST /api/harness/sessions/<id>/request` | Mutation JSON; `Accept: text/event-stream` để nhận SSE |
| `GET /api/harness/places?q=` | Tra nơi từ serving index |
| `GET /api/harness/sessions/<id>/read/decision/compare?a=&b=` | So sánh |
| `GET /api/harness/sessions/<id>/read/decision/why-not?place=` | Lý do loại |
| `GET /api/harness/sessions/<id>/read/decision/page?group=` | Trang tiếp của một nhóm hiển thị: cửa sổ đang hiện nối thêm `page_size` nơi, lưu trong phiên → `{view}` (`docs/PLACE_DECISION.md` §9.4) |
| `GET /api/harness/sessions/<id>/read/planning/{variants,lodging}` | Đọc phương án / tiến độ chỗ ở |
| `GET /api/harness/sessions/<id>/planning/lodging/events` | SSE cập nhật view sau chờ chỗ ở, tối đa khoảng 10 giây |
| `GET /api/harness/sessions/<id>/preview` | Chỉ ở stage `decision`: lịch ngầm cho lựa chọn hiện tại → `{revision, status, plan}`; `status` = `ready` / `failed` (không xếp được, kèm `back_to_decision`) / `blocked` (Decision chưa xác nhận được) / `empty` |
| `GET /api/harness/trips?ids=a,b` | Tóm tắt tối đa 20 hành trình trình duyệt nhớ: stage, ngày, số người, nơi đã chọn, đã chốt chưa; ID lạ bị bỏ qua, không liệt kê hành trình khác |
| `POST /api/harness/sessions/<id>/feedback` | `{scores (≤10 tên → 1–5), more_search?, note? ≤1000}` → ghi một dòng `data/harness/feedback.jsonl` |
| `POST /api/harness/reports` | `{place_id, text, reporter}` → báo cáo thông tin sai của Decision (`corpus.review.reports`); không đổi corpus ngay |

Request mẫu:

```json
{"request_id":"unique-request-id","stage":"decision","operation":"act","expected_revision":3,"payload":{"type":"select","place_id":"existing-place-id"}}
```

Response `JourneyView`: `id`, `stage`, `revision`, `sessions`, `outputs`, `result` (view hoặc output của module). Body tối đa 64 KiB; input sai trả 400, phiên không có 404, conflict/router hoặc chưa confirm được trả 409. Lỗi sau khi mở SSE gửi event `error` với `data.status` tương ứng để client không giữ pending request đã bị từ chối.

SSE mutation bọc `request_id`, `stage`, `revision`, `event`, `data`. `say`/`preview` có `provisional: true`, dùng revision trước commit; các event còn lại phát sau commit. Event `journey` cuối stream là receipt hoàn tất. Client lọc metadata không khớp và chỉ handoff khi nhận receipt cuối. SSE chỗ ở dùng stage/revision; đây là stream đọc, không có request mutation.

## 5. Ngân sách model và kiểm chứng

Chip, edit, show, act của người dùng và router không gọi LLM. `trip/heuristics.py` bypass Agent khi prepass hiểu trọn câu chỉ gồm số ngày, số người, người đi cùng, phương tiện và từ nối trong allowlist; không có clue suy luận hay từ còn chưa hiểu. Câu gõ chỉ lặp lại nhãn một chip (hoặc một vế của nhãn, bỏ dấu và từ đệm) hay `Bỏ qua` / `Không chắc` của thẻ đang mở được xử lý như bấm chip đó (`chip_echo`); không áp dụng cho thẻ agent viết và thẻ có ô nhập chữ. Gửi chữ trong ô "đáp án khác" mà không chọn chip nào được xử lý như một lượt gõ tự do. `decision/heuristics.py` nhận một lệnh chọn/thêm/bỏ/khóa với tên đầy đủ khớp duy nhất trong các địa điểm trên màn. Act vẫn qua kiểm tra nghiệp vụ. Log ghi `heuristic:frame`, `heuristic:chip_echo` hoặc `heuristic:exact_command`.

Câu phủ định, điều kiện, nhiều ý không được heuristic hiểu hết hoặc tên trùng đi qua đường Agent hiện có. Prepass vẫn giữ clue đã đọc được và provenance khi Agent lỗi. Heuristic không tự confirm, nới constraint hoặc suy ra fact địa điểm.

`config/agents.yaml`: `max_parallel: 2`, `max_waiting: 16`. Queue chờ nằm trong deadline tổng; permit bao gồm retry. Queue đầy, timeout hoặc output sai schema trả tín hiệu lỗi để module dùng fallback. Đây là quota trong một tiến trình, không bao gồm mọi lệnh Judge/Extractor hoặc server khác dùng chung key UIT.

```sh
python -m pytest -q tests/agents tests/harness tests/trip tests/decision tests/planning
node web/node_modules/typescript/bin/tsc web/src/user/journey.ts --target ES2022 --module ES2022 --lib ES2022,DOM --skipLibCheck --outDir /tmp/tg-journey --types ''
node web/scripts/test_journey.mjs
npm run build --prefix web
```

Test không mạng dùng stream giả và engine thật với serving/live fixture: router, handoff, snapshot/rollback/restart, idempotency, schema, Planning proposal và client retry/SSE. Model thật kiểm riêng theo marker `live`.
