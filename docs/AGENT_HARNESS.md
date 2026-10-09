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

Skill là khai báo do repo quản lý, không phải code thực thi hay skill tải từ người dùng. Workflow mô tả bước xử lý; `permit_tool` kiểm capability tại adapter. Trip chạy Clef trước Agent: Clef phân loại `needs_card` / `user_question` và cấp allowlist, Agent tạo card hoặc trả lời theo route, gọi tối đa số tool đọc trong `config/trip.yaml`; code validate argument và `guard` vẫn là đường duy nhất ghi state. Các agent dùng chung cấu hình model nhưng context, schema và quyền riêng.

Trip/Decision có lượt chat. Planning có call riêng cho proposal nội bộ và không nhận `turn` qua router; quyền và kiểm chứng proposal ở `docs/PLANNING.md` §Agent đề xuất nội bộ. `live` cung cấp tool, không có agent LLM riêng. Corpus giữ pipeline offline riêng.

## 2. Router và handoff

| Stage hiện tại | Operation được phép | Kết quả chuyển stage |
|---|---|---|
| `trip` | `turn`, `advance` | `advance` → Decision từ Search Input đã compile trên server |
| `decision` | `turn`, `act`, `advance`, `back` | `advance` → confirm Decision và tạo Planning; `back` → Trip |
| `planning` | `act`, `recommend`, `confirm`, `back` | `confirm` → Plan Output; `back` → Decision |

Lịch ngầm (`preview`) là đọc: harness lấy Decision Output nháp (`decision` read `draft`, không lưu) dưới khóa hành trình, rồi gọi `planning.Tools.preview` ngoài khóa; Planning dựng phương án không tạo phiên và cache theo hash Decision Output (15 phút, tối đa 16), `create` khi `advance` dùng lại đúng bản đã dựng. Web gọi sau mỗi thay đổi ở Chọn nơi, debounce 350 ms.

Request đến stage không active bị từ chối. Router không gọi LLM và không chọn agent từ tên tool hoặc lời model. `advance`, `back`, `recommend`, `confirm` chỉ nhận payload rỗng; client không gửi output để thay handoff đã kiểm.

Lượt chat ở Chọn nơi có mong muốn về chuyến (`turn` stage `decision` mà Decision phát event `trip {texts}`): harness gọi `trip.apply(trip_sid, "refine", {text})` (Trip đọc như một lượt chữ, compile lại, không đổi thẻ màn Hiểu chuyến đi), thay `outputs.trip` bằng Search Input mới rồi `decision.rebase`. Event `view` của lượt được thay bằng view sau rebase (kèm `diff`), lời Trip nối sau lời Decision trong cùng bong bóng (`say {replace}`) và câu kết là `diff.text` của rebase ("Giữ 22 nơi, thay 2 nơi hợp hơn."), event `trip` không ra web. Lời Trip ở đây không kết bằng câu hỏi (không có thẻ nào để trả lời). Trip không compile được (còn thiếu trường bắt buộc) hoặc hành trình không có phiên Trip → lượt vẫn xong, Decision giữ nguyên.

Quay về Decision giữ ID phiên và lựa chọn. Quay về Trip rồi compile lại dùng `rebase` trên phiên Decision đã có. Quay lại vô hiệu output ở bước sau; Planning được dựng lại khi xác nhận Decision. Act Planning giữ Decision Output làm đầu vào và vô hiệu Plan Output đã chốt.

## 3. Phiên, revision và retry

Một `Journey` giữ ID, tài khoản sở hữu (`user_id`), stage, revision, ID phiên các module, output, snapshot và receipt (receipt có `at`). Engine chạy bằng store RAM; adapter từ chối engine có store ghi riêng. `python -m harness serve` dùng `PgStore`: mỗi hành trình một dòng bảng `journeys` (envelope `jsonb` + `stage`, `revision`, `user_id`, `app_version`). Ghi bằng `UPDATE … WHERE revision = <revision đã đọc>`; người ghi thứ hai thua nhận `Conflict` (409) thay vì đè. Tiến trình giữ bản sao các hành trình đã đọc (envelope có thể vài MB). `Store` ghi file `data/harness/sessions/<id>.json` còn dùng cho test và CLI. Phản hồi sau chuyến ghi vào bảng `feedback`.

Nạp dữ liệu file cũ một lần (không gắn tài khoản; mốc phễu suy ra từ trạng thái đã lưu, `docs/ANALYTICS.md`): `python -m harness import-files data/harness/sessions data/harness/feedback.jsonl` (chạy lại không nạp trùng).

Mutation giữ khóa hành trình trong tiến trình, kiểm revision và router, chạy tool, lấy snapshot mới rồi commit. Save lỗi khôi phục snapshot trước mutation. Restart phục hồi module từ snapshot đã commit, không gọi lại LLM để replay phiên.

Request trùng `request_id` và toàn bộ nội dung trả receipt đã lưu dù stage/revision hiện tại đã đổi. Dùng lại ID với nội dung khác hoặc revision cũ cho request mới bị từ chối. Receipt chứa response và event của lần thực thi đã commit.

Client tuần tự mutation theo journey, lưu pending request trong localStorage trước khi gửi, giữ nguyên ID/payload/revision khi retry transport và replay pending trước mutation mới sau reload. Reload tiếp tục stage trên server; chỉ thao tác quay lại rõ ràng từ người dùng gửi `back`. Server session là nguồn sự thật; `decisionId`/`planningId` trong adapter Web tham chiếu journey, không phải ID module độc lập.

Khóa hành trình nằm trong một tiến trình; nhiều tiến trình cùng ghi được chặn bằng kiểm revision ở Postgres. Chưa pruning receipt hoặc có transaction với dịch vụ ngoài. CLI/API module độc lập giữ store phiên riêng và không dùng chung ID với harness.

## 4. API và SSE

```sh
python -m harness serve [--port 8769]
```

Bind `127.0.0.1`; Vite proxy `/api/harness` và `/api/auth` đến cổng 8769 (`HARNESS_PORT` đổi được). Cần `DATABASE_URL`. `./run.sh start` chạy harness, analytics, review và Web; thiết lập ở `README.md`.

**Quyền.** Mọi `/api/harness/*` cần phiên đăng nhập (cookie `tg_session`), thiếu thì 401; `/api/auth/*` là luồng đăng nhập (`docs/ACCOUNTS.md`). Mutation (POST / PATCH / DELETE) phải có header `Origin` khớp `APP_BASE_URL` hoặc khớp `Host`, sai thì 403. Hành trình của tài khoản khác trả 404 như không tồn tại. Ngoại lệ duy nhất: `POST /api/harness/events` nhận lô không phiên nhưng chỉ giữ `page_view` / `landing_cta` (landing public).

| API | Input / việc |
|---|---|
| `POST /api/harness/sessions` | `{experience?, start_with?}` → journey + Trip view, gắn tài khoản đang đăng nhập; `user_id` của Trip = id tài khoản, `remember` = `consents.patterns` của hồ sơ (`docs/TRIP_UNDERSTANDING.md` §17). Phương tiện / người đi cùng trong hồ sơ vào Trip làm prior `source = profile` |
| `DELETE /api/harness/profile/<user_id>` | `{forgotten}`; chỉ `user_id` của chính mình, khác thì 404 |
| `GET /api/harness/sessions/<id>?stage=` | Đọc view module đã có; mặc định stage active |
| `POST /api/harness/sessions/<id>/request` | Mutation JSON; `Accept: text/event-stream` để nhận SSE |
| `GET /api/harness/places?q=` | Tra nơi từ serving index |
| `GET /api/harness/geo?q=` | Ô "Bạn khởi hành từ đâu?": ≤ 6 `{text, address, province, lat, lng, source, fetched_at}` (`live.geosearch` qua Planning); nguồn lỗi → `[]` |
| `GET /api/harness/lodging/suggest?q=` | Ô chỗ ở: ≤ 6 `{kind, id?, text, address, rating?, lat, lng}` — chỗ ở của mình trước (`corpus`: serving nhóm `stay`; `live`: thẻ Maps đã crawl, tra tên tại chỗ), rồi `address` từ `geosearch`; nguồn tìm lỗi → vẫn trả phần của mình |
| `GET /api/harness/transit?mode=&from=&to=&date=[&lat=&lng=]` | Thẻ chuyến (`params` của câu hỏi `inbound` / `outbound`): `{status: ready / pending / unavailable, trips: [Transit], book_url}`; `pending` = đang crawl nền, `book_url` = trang đặt vé đã điền sẵn (`docs/PLANNING.md` §Chuyến xe khách, chuyến bay) |
| `GET /api/harness/transit/events?…` | SSE cùng tham số: một event `{status, trips, book_url}` khi có kết quả; quá 90 giây vẫn chưa xong → `unavailable` |
| `GET /api/harness/sessions/<id>/read/decision/compare?a=&b=` | So sánh |
| `GET /api/harness/sessions/<id>/read/decision/why-not?place=` | Lý do loại |
| `GET /api/harness/sessions/<id>/read/decision/page?group=` | Trang tiếp của một nhóm hiển thị: cửa sổ đang hiện nối thêm `page_size` nơi, lưu trong phiên → `{view}` (`docs/PLACE_DECISION.md` §9.4) |
| `GET /api/harness/sessions/<id>/read/planning/{variants,lodging}` | Đọc phương án / tiến độ chỗ ở |
| `GET /api/harness/sessions/<id>/planning/lodging/events` | SSE cập nhật view sau chờ chỗ ở, tối đa khoảng 10 giây |
| `GET /api/harness/sessions/<id>/preview` | Chỉ ở stage `decision`: lịch ngầm cho lựa chọn hiện tại → `{revision, status, plan}`; `status` = `ready` / `failed` (không xếp được, kèm `back_to_decision`) / `blocked` (Decision chưa xác nhận được) / `empty` |
| `GET /api/harness/trips` | Tóm tắt tối đa 50 hành trình của tài khoản, mới nhất trước: stage, ngày, số người, nơi đã chọn, đã chốt chưa |
| `POST /api/harness/sessions/<id>/feedback` | `{scores (≤10 tên → 1–5), more_search?, note? ≤1000}` → một dòng bảng `feedback` |
| `GET /api/harness/sessions/<id>/today?day=`, `…/companion/suggest?place=&similar=1`, `POST …/companion` | Chế độ Đang đi (`docs/COMPANION.md`) |
| `/api/harness/calendar/{preview,apply,disconnect}` | Xuất Google Calendar có xác nhận (`docs/COMPANION.md`) |
| `/api/harness/me…`, `/api/harness/avatars/<key>` | Tài khoản, hồ sơ, avatar, xóa tài khoản (`docs/ACCOUNTS.md`) |
| `/api/harness/push/…`, `/api/harness/notifications…`, `/api/harness/me/notification-prefs` | Thông báo (`docs/COMPANION.md`) |
| `POST /api/harness/events` | Lô event của web (`docs/ANALYTICS.md`) |
| `POST /api/harness/reports` | `{place_id, text, reporter}` → báo cáo thông tin sai của Decision (`corpus.review.reports`); không đổi corpus ngay |

Request mẫu:

```json
{"request_id":"unique-request-id","stage":"decision","operation":"act","expected_revision":3,"payload":{"type":"select","place_id":"existing-place-id"}}
```

Response `JourneyView`: `id`, `stage`, `revision`, `sessions`, `outputs`, `result` (view hoặc output của module). Body tối đa 64 KiB (avatar 5 MB); input sai trả 400, phiên không có 404, conflict/router hoặc chưa confirm được trả 409. Lỗi sau khi mở SSE gửi event `error` với `data.status` tương ứng để client không giữ pending request đã bị từ chối.

SSE mutation bọc `request_id`, `stage`, `revision`, `event`, `data`. `say`/`preview` có `provisional: true`, dùng revision trước commit; các event còn lại phát sau commit. Event `journey` cuối stream là receipt hoàn tất. Client lọc metadata không khớp và chỉ handoff khi nhận receipt cuối. SSE chỗ ở dùng stage/revision; đây là stream đọc, không có request mutation. Bốn đường `geo`, `lodging/suggest`, `transit`, `transit/events` không cần journey: Trip Understanding hỏi hậu cần trước khi có phiên Planning, nên harness gọi thẳng `planning.Tools` (Planning là chủ Live Context).

## 5. Ngân sách model và kiểm chứng

Edit, show, act của người dùng và router không gọi LLM. Ở Trip, trả lời một thẻ (chip hoặc chữ) và câu gõ tự do đều là một lượt agent: chip và `Bỏ qua` / `Không chắc` quay lại Agent dưới dạng chữ (Trip không tự áp chip). Ô "đáp án khác" là lựa chọn thay cho chip: một `answer` mang chip/giá trị **hoặc** chữ, không cả hai (gửi cả hai bị từ chối). Clef (`trip/infrastructure/clef.py`) gán nhãn lạc đề, phá hoại hoặc câu hỏi số liệu thực tế với xác suất đủ cao thì Trip trả câu cố định mà không gọi Agent, không ghi state, giữ nguyên thẻ đang mở; câu mà bộ từ khóa đã đọc được manh mối thì không bị coi là lạc đề. `decision/heuristics.py` nhận một lệnh chọn/thêm/bỏ/khóa với tên đầy đủ khớp duy nhất trong các địa điểm trên màn. Act vẫn qua kiểm tra nghiệp vụ. Log ghi `clef_reject:off_topic|abuse`, `clef_data` hoặc `heuristic:exact_command`. Adapter `Tools` của Trip và Decision phát thêm event nội bộ `trace {path}` (`agent` / `fallback` / `heuristic:*`); harness bỏ nó trước khi gửi web và ghi vào event dùng cho Admin (`docs/ANALYTICS.md`).

Câu phủ định, điều kiện, nhiều ý không được heuristic hiểu hết hoặc tên trùng đi qua đường Agent hiện có. Prepass vẫn giữ clue đã đọc được và provenance khi Agent lỗi. Heuristic không tự confirm, nới constraint hoặc suy ra fact địa điểm.

`config/agents.yaml`: `max_parallel: 2`, `max_waiting: 16`. Queue chờ nằm trong deadline tổng; permit bao gồm retry. Queue đầy, timeout hoặc output sai schema trả tín hiệu lỗi để module dùng fallback. Đây là quota trong một tiến trình, không bao gồm mọi lệnh Judge/Extractor hoặc server khác dùng chung key UIT.

```sh
python -m pytest -q tests/agents tests/harness tests/trip tests/decision tests/planning
node web/node_modules/typescript/bin/tsc web/src/user/journey.ts --target ES2022 --module ES2022 --lib ES2022,DOM --skipLibCheck --outDir /tmp/tg-journey --types ''
node web/scripts/test_journey.mjs
npm run build --prefix web
```

Test không mạng dùng stream giả và engine thật với serving/live fixture: router, handoff, snapshot/rollback/restart, idempotency, schema, Planning proposal và client retry/SSE. Model thật kiểm riêng theo marker `live`.
